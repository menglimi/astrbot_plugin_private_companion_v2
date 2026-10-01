"""Synchronous local commands; a side effect never uses the read lease registry."""

from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode, require, stamp
from companion_v2.storage.runtime import StorageTransactionNestingError

from . import codec
from .models import AtomRef, Proposal, owner_key
from .proposal_input import validate
from .operation_receipts import output as receipt_output, status as receipt_status
from .wire_binding import MemoryWireBinding, _WireIssue
from .wire_evidence import MemoryWireEvidence
from .wire_operations import (PROPOSAL_CAPABILITY, check_output, operation_key, operation_row,
                              task_issue, wire_receipt)


class MemoryProposalWireV1(MemoryWireBinding):
    schema_version = "memory.proposal.v1"
    capability_id = PROPOSAL_CAPABILITY
    extra_request_fields = frozenset({"idempotency_key"})

    def __init__(self, memory, *, require_running, **binding):
        super().__init__(memory, **binding)
        if not callable(require_running):
            raise ValueError("commands require the trusted host lifecycle fence")
        self.require_running = require_running
        self.evidence = MemoryWireEvidence(memory)

    def offer_source(self, context, source, *, expires_at=None, start=0, end=None):
        """Trusted host API: capture real source attribution, never caller metadata."""
        self.require_running()
        expiry = self.memory.tasks.now() + timedelta(minutes=10)
        if expires_at is not None:
            expiry = min(expiry, expires_at)
        with self.memory.runtime.transaction():
            captured = self.memory.writer.access.capture(context, source, start=start, end=end)
            session_id = "memory-command-evidence-" + uuid4().hex
            self.memory.query.begin(context, session_id, expires_at=expiry)
            reference = self.evidence.offer(context, session_id, captured)
            self.require_running()
            return reference

    def _fence(self, context, call, action, policy_revision):
        self.require_running()
        self.memory.writer.access.check(context, action)
        if self._policy_revision(context) != policy_revision:
            raise _WireIssue("memory_policy_changed")
        if self.memory.tasks.now() >= call["deadline"]:
            raise _WireIssue("deadline_expired", "timeout")

    def _proposal(self, context, payload, values):
        operation = payload["operation"]
        evidence = tuple(self.evidence.resolve(context, ref) for ref in payload.get("evidence_refs", []))
        target = AtomRef(payload["target_atom_id"], payload["expected_revision"]) if operation in ("correct", "retract") else None
        original = None
        if target:
            row = self.memory.writer._head(context, target)
            if row["namespace"] != payload["namespace"]:
                raise _WireIssue("target_unavailable")
            original = codec.proposal(json.loads(row["record_json"])["proposal"])
        common = dict(operation=operation, namespace=payload["namespace"], purpose=payload["purpose"],
                      visibility=payload["visibility"], evidence=evidence, target=target,
                      defer_until_boundary=payload.get("defer_until_boundary", False))
        if operation == "retract":
            # Retraction describes the actual target. It cannot silently change its attributes.
            for name, value in values.items():
                if name in payload and getattr(original, name) != value:
                    raise _WireIssue("retraction_target_mismatch")
            return replace(original, **common, dependencies=())
        if operation == "no_op":
            return Proposal(**common)
        values = dict(values)
        values.setdefault("representation", values["predicate"] + ": " + values["object"])
        if original:
            # These fields are intentionally absent from this wire profile.
            values.update(single_value=original.single_value, context_mode=original.context_mode,
                          dependencies=original.dependencies)
        return Proposal(**common, **values)

    def _output(self, context, payload, item, receipt, policy_revision):
        return receipt_output(self.memory.writer, context, item, receipt, proposal_id=payload["proposal_id"],
                              generation=self.provider_generation, policy=policy_revision)

    def resolve_pending(self, context, operation_id, *, decision, deadline_at, max_output_bytes=65536):
        """Trusted boundary decision; never infer acceptance from a timer or a lookup."""
        from .wire_binding import _time, _token, _integer
        request = {"request_id": "boundary-" + uuid4().hex, "trace_id": "boundary-" + uuid4().hex}
        try:
            self.require_running()
            _token(operation_id, "operation_id")
            _integer(max_output_bytes, "max_output_bytes", minimum=1)
            if decision not in ("accept", "discard"):
                raise _WireIssue("invalid_pending_decision")
            call = {"deadline": _time(deadline_at, "deadline_at"), "budget": {"max_output_bytes": max_output_bytes}}
            policy = self._policy_revision(context)
            with self.memory.runtime.transaction(require_outermost=True):
                self._fence(context, call, "memory.propose", policy)
                row = self.memory.runtime.read_one("SELECT * FROM memory_operations WHERE operation_id = ? AND owner_key = ? AND caller_id = ?",
                    (operation_id, owner_key(context), self.memory.writer.caller(context)))
                wire = wire_receipt(row)
                if wire is None:
                    raise _WireIssue("target_unavailable")
                if row["state"] == "pending":
                    original = json.loads(row["context_json"])
                    if original != json.loads(encode(context)):
                        raise _WireIssue("memory_pending_context_changed")
                    method = self.memory.writer.commit_pending if decision == "accept" else self.memory.writer.discard_pending
                    receipt = require(method(context, operation_id))
                    wire = receipt["wire"]
                output = wire["output"]
                result = self._envelope(request, status=receipt_status(output),
                    reason_code="proposal_pending" if receipt_status(output) == "pending" else None, output=output)
                check_output(self, call, result)
                self._fence(context, call, "memory.propose", policy)
            return result
        except _WireIssue as issue:
            return self._envelope(request, status=issue.status, reason_code=issue.reason_code)
        except TaskError as error:
            issue = task_issue(error)
            return self._envelope(request, status=issue.status, reason_code=issue.reason_code)
        except StorageTransactionNestingError:
            return self._envelope(request, status="rejected", reason_code="outer_transaction_required")
        except sqlite3.Error:
            return self._envelope(request, status="uncertain", reason_code="memory_commit_uncertain",
                                  output={"operation_id": operation_id, "commit_state": "uncertain"})
        except (ValueError, TypeError, KeyError):
            return self._envelope(request, status="rejected", reason_code="invalid_request")

    def handle(self, context, request):
        identifier = proposal_id = None
        try:
            # Refuse closed/taken-over hosts before opening their storage.
            self.require_running()
            call = self._validate_envelope(context, request)
            payload = request["payload"]
            values = validate(context, payload)
            key = operation_key(request["idempotency_key"])
            identifier = self.memory.writer.operation_id(context, payload["namespace"], key)
            proposal_id = payload["proposal_id"]
            action = {"correct": "memory.correct", "retract": "memory.retract"}.get(payload["operation"], "memory.propose")
            policy_revision = self._policy_revision(context)
            with self.memory.runtime.transaction(require_outermost=True) as connection:
                self._fence(context, call, action, policy_revision)
                row = operation_row(self.memory, context, payload["namespace"], identifier)
                if row is not None:
                    wire = wire_receipt(row)
                    if wire is None or wire["payload_hash"] != digest(payload):
                        raise _WireIssue("idempotency_conflict")
                    output = wire["output"]
                else:
                    item = self._proposal(context, payload, values)
                    receipt = require(self.memory.writer.submit(context, item, operation_key=key))
                    output = self._output(context, payload, item, receipt, policy_revision)
                    wire = {"payload_hash": digest(payload), "output": output}
                    connection.execute("UPDATE memory_operations SET result_json = ? WHERE operation_id = ?",
                                       (encode({**receipt, "wire": wire}), identifier))
                    # Recheck evidence after all preparation, before the outer COMMIT.
                    for reference in payload.get("evidence_refs", []):
                        evidence = self.evidence.resolve(context, reference)
                        self.memory.writer.access.evidence(context, evidence, action=action)
                    if item.retention == "protected":
                        self.memory.writer.access.check(context, "memory.protect")
                    for dependency in item.dependencies:
                        require(self.memory.writer.read(context, dependency))
                result = self._envelope(request, status=receipt_status(output),
                    reason_code="proposal_pending" if receipt_status(output) == "pending" else None, output=output)
                check_output(self, call, result)
                self._fence(context, call, action, policy_revision)
            return result
        except _WireIssue as issue:
            return self._envelope(request, status=issue.status, reason_code=issue.reason_code)
        except TaskError as error:
            issue = task_issue(error)
            return self._envelope(request, status=issue.status, reason_code=issue.reason_code)
        except StorageTransactionNestingError:
            return self._envelope(request, status="rejected", reason_code="outer_transaction_required")
        except sqlite3.Error:
            # A COMMIT acknowledgement may be lost. Never promise failure or retry.
            return self._envelope(request, status="uncertain", reason_code="memory_commit_uncertain",
                output={"operation_id": identifier, "proposal_id": proposal_id, "commit_state": "uncertain"})
        except (TypeError, ValueError, KeyError):
            return self._envelope(request, status="rejected", reason_code="invalid_request")

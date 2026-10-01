"""Persistent wire receipts share the authoritative memory operation journal."""

import json
import sqlite3

from companion_v2.execution.models import TaskError

from .models import owner_key
from .operation_receipts import status as receipt_status
from .proposal_input import private_payload
from .wire_binding import MemoryWireBinding, _WireIssue, _token, _TOKEN


PROPOSAL_CAPABILITY = "memory.proposal.submit"


def operation_key(key):
    return "wire:memory.proposal.submit:v1:" + _token(key, "idempotency_key")


def operation_row(memory, context, namespace, identifier):
    return memory.runtime.read_one("""SELECT * FROM memory_operations
        WHERE operation_id = ? AND owner_key = ? AND caller_id = ? AND namespace = ?""",
        (identifier, owner_key(context), memory.writer.caller(context), namespace))


def wire_receipt(row):
    return json.loads(row["result_json"]).get("wire") if row else None


def task_issue(error):
    code = error.code if _TOKEN.fullmatch(error.code) else "memory_operation_failed"
    if code in ("memory_disabled", "authorization_denied", "capability_consent_missing",
                "capability_consent_revoked", "capability_consent_expired", "memory_audience_denied"):
        return _WireIssue(code, "permission_denied")
    if code in ("host_not_running", "supervisor_fenced", "supervisor_not_started"):
        return _WireIssue(code, "unavailable")
    return _WireIssue(code)


def check_output(adapter, call, result):
    """Count the complete successful result, including its correlation envelope."""
    limit = min(call["budget"].get("max_output_bytes", adapter.max_output_bytes), adapter.max_output_bytes)
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")) > limit:
        raise _WireIssue("output_budget_exceeded")


class MemoryOperationWireV1(MemoryWireBinding):
    schema_version = "memory.operation-query.v1"
    capability_id = "memory.operation.get"

    def handle(self, context, request):
        try:
            call = self._validate_envelope(context, request)
            payload = request["payload"]
            required = {"namespace", "visibility", "purpose"}
            private_payload(payload, required=required,
                allowed=required | {"operation_id", "capability_id", "idempotency_key"})
            if "operation_id" in payload:
                if "capability_id" in payload or "idempotency_key" in payload:
                    raise _WireIssue("invalid_operation_lookup")
                identifier = _token(payload["operation_id"], "operation_id")
            else:
                if payload.get("capability_id") != PROPOSAL_CAPABILITY:
                    raise _WireIssue("invalid_original_capability")
                identifier = self.memory.writer.operation_id(context, payload["namespace"],
                    operation_key(payload.get("idempotency_key")))
            self.binding_authority(context)
            with self.memory.runtime.read_snapshot():
                wire = wire_receipt(operation_row(self.memory, context, payload["namespace"], identifier))
                if wire is None:
                    # Absence or loss of authority is not proof that no commit occurred.
                    raise _WireIssue("target_unavailable")
                output = wire["output"]
                result = self._envelope(request, status=receipt_status(output),
                    reason_code="proposal_pending" if receipt_status(output) == "pending" else None, output=output)
                check_output(self, call, result)
                self.binding_authority(context)
                if self.memory.tasks.now() >= call["deadline"]:
                    raise _WireIssue("deadline_expired", "timeout")
                return result
        except _WireIssue as issue:
            return self._envelope(request, status=issue.status, reason_code=issue.reason_code)
        except TaskError as error:
            issue = task_issue(error)
            return self._envelope(request, status=issue.status, reason_code=issue.reason_code)
        except sqlite3.Error:
            return self._envelope(request, status="unavailable", reason_code="operation_lookup_unavailable")
        except (TypeError, ValueError, KeyError):
            return self._envelope(request, status="rejected", reason_code="invalid_request")

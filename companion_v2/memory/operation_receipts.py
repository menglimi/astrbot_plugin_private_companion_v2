"""Keep wire receipts current when a durable pending decision is resolved."""

from dataclasses import asdict
import json

from companion_v2.execution.models import digest, stamp
from .models import owner_key


def policy_revision(writer, context):
    settings = writer.access.settings
    return "policy-" + (settings.read(context)[1] if settings else digest(asdict(writer.access.policy_for(context))))


def output(writer, context, item, receipt, *, proposal_id, generation, policy=None):
    state = receipt["state"]
    result = dict(operation_id=receipt["operation_id"], proposal_id=proposal_id,
        proposal_state="skipped" if state == "discarded" else state,
        owner_ref="owner-" + owner_key(context), policy_revision=policy or policy_revision(writer, context),
        commit_state="committed" if state == "persisted" else "not_committed",
        original_capability_id="memory.proposal.submit", original_provider_generation=generation)
    if state == "persisted":
        revision = writer.runtime.read_one("SELECT MAX(sequence) n FROM memory_changes WHERE owner_key = ?",
                                          (owner_key(context),))["n"]
        result.update(atom_id=receipt["atom_id"], revision=receipt["revision"], memory_revision=revision,
            effective_retention=item.retention, retention_until=stamp(item.valid_to) if item.retention == "short" else None,
            valid_from=stamp(item.valid_from) if item.valid_from else None, valid_to=stamp(item.valid_to) if item.valid_to else None)
    return result


def resolved(writer, context, item, receipt):
    row = writer.runtime.read_one("SELECT result_json FROM memory_operations WHERE operation_id = ?", (receipt["operation_id"],))
    wire = json.loads(row["result_json"]).get("wire") if row else None
    if wire:
        original = wire["output"]
        wire["output"] = output(writer, context, item, receipt, proposal_id=original["proposal_id"],
                                generation=original["original_provider_generation"])
        return {**receipt, "wire": wire}
    return receipt


def status(output):
    return "pending" if output["proposal_state"] in ("pending", "quarantined") else "succeeded"

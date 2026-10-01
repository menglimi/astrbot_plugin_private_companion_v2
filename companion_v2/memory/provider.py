"""The Memory owner adapter used by the process-local provider registry."""

from __future__ import annotations

from uuid import uuid4

from companion_v2.capabilities.read_providers import ReadCapability, ReadLimits, ReadProvider
from companion_v2.execution.models import ProviderBinding, TaskError
from companion_v2.identity_policy.personas import RuntimeIdentity

from .wire import EvidenceBudget, runtime_scope_from_task_context


CAPABILITY = ReadCapability(
    capability_id="memory.query",
    capability_version="1.0",
    input_schema="memory.query.v1",
    output_schema="memory.result.v1",
    permissions=("memory.read",),
    profile="private-facts.utf8-budget.v1",
    limits=ReadLimits(65536, 65536),
)

OPERATION_CAPABILITY = ReadCapability(
    capability_id="memory.operation.get", capability_version="1.0",
    input_schema="memory.operation-query.v1", output_schema="memory.result.v1",
    permissions=("memory.read",), profile="private-operation-receipts.v1",
    limits=ReadLimits(65536, 65536),
    supports_pending=True,
)


def utf8_evidence_budget(value):
    """Conservative byte-token budget for this profile, not billed model usage."""
    return len(value.encode("utf-8"))


def scope_projector(runtime_identity: RuntimeIdentity):
    if not isinstance(runtime_identity, RuntimeIdentity):
        raise ValueError("memory wire requires an explicit trusted runtime identity")

    def scope_for_context(context):
        if context.actor.principal.host_id != runtime_identity.host_id:
            raise TaskError("provider_scope_unavailable", "the caller belongs to another host")
        return runtime_scope_from_task_context(
            context, ecosystem_id=runtime_identity.ecosystem_id,
            runtime_instance_id=runtime_identity.runtime_instance_id,
            host_kind=runtime_identity.host_kind,
        )

    return scope_for_context


def make_provider(memory, binding: ProviderBinding, *, runtime_identity: RuntimeIdentity):
    scope_for_context = scope_projector(runtime_identity)

    wire = memory.bind_query_wire_v1(
        provider_id=binding.provider,
        provider_generation=binding.generation,
        scope_for_context=scope_for_context,
        token_count=utf8_evidence_budget,
        default_evidence_budget=EvidenceBudget(8, 2400, 800),
        max_input_bytes=CAPABILITY.limits.max_input_bytes,
        max_output_bytes=CAPABILITY.limits.max_output_bytes,
    )

    def invoke(context, request):
        result = wire.handle(context, request)
        if result["status"] in ("succeeded", "partial"):
            result["warnings"].append("evidence_tokens_estimated_utf8_bytes")
        return result

    return ReadProvider(CAPABILITY, invoke, wire.binding_authority, scope_for_context)


def make_operation_provider(memory, binding: ProviderBinding, *, runtime_identity: RuntimeIdentity):
    project = scope_projector(runtime_identity)
    wire = memory.bind_operation_wire_v1(provider_id=binding.provider, provider_generation=binding.generation,
        scope_for_context=project, max_input_bytes=OPERATION_CAPABILITY.limits.max_input_bytes,
        max_output_bytes=OPERATION_CAPABILITY.limits.max_output_bytes)
    return ReadProvider(OPERATION_CAPABILITY, wire.handle, wire.binding_authority, project)


def make_commands(memory, *, runtime_identity: RuntimeIdentity, require_running):
    """Local host commands have their own generation, outside read leases."""
    return memory.bind_proposal_wire_v1(provider_id="companion_v2.memory",
        provider_generation="command-" + uuid4().hex, scope_for_context=scope_projector(runtime_identity),
        require_running=require_running)


def make_subscriptions(memory, *, runtime_identity: RuntimeIdentity, require_running):
    from .subscriptions import MemorySubscriptions
    return MemorySubscriptions(memory, provider_id="companion_v2.memory", provider_generation="stream-" + uuid4().hex,
        scope_for_context=scope_projector(runtime_identity), require_running=require_running)

"""The shelf as a read-provider capability, not a second permission system.

The asset owner registers here; the shelf never stores a work's text or images. Two
capabilities are declared so a catalog listing and an asset read can be authorized
separately: discovering what a provider holds is not the same as reading it.

The invoke envelope follows the registry's contract exactly: the request must echo the
selected capability, version, provider and generation, and the result must echo the same
plus its request and trace ids. Anything else is refused by the registry, not here.
"""

from __future__ import annotations

import json

from companion_v2.capabilities.read_providers import ReadCapability, ReadLimits, ReadProvider
from companion_v2.execution.models import ProviderBinding, TaskError, digest
from companion_v2.foundation.refs import ScopeKind
from companion_v2.identity_policy.personas import RuntimeIdentity

from .models import EntryKind, EntryState
from .service import role_owner


CATALOG_CAPABILITY = ReadCapability(
    capability_id="library.catalog",
    capability_version="1.0",
    input_schema="library.catalog.v1",
    output_schema="library.catalog-result.v1",
    permissions=("library.catalog",),
    profile="shelf-catalog.private.v1",
    limits=ReadLimits(16384, 65536),
    features=("catalog.list",),
)

READ_CAPABILITY = ReadCapability(
    capability_id="library.read",
    capability_version="1.0",
    input_schema="library.read.v1",
    output_schema="library.read-result.v1",
    permissions=("library.read",),
    profile="shelf-asset.bounded.v1",
    limits=ReadLimits(16384, 262144),
    features=("asset.excerpt",),
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def scope_projector(runtime_identity):
    """The one trusted scope projection both shelf capabilities share."""
    if not isinstance(runtime_identity, RuntimeIdentity):
        raise ValueError("the shelf wire requires an explicit trusted runtime identity")

    def scope_for_context(context):
        if context.actor.principal.host_id != runtime_identity.host_id:
            raise TaskError("provider_scope_unavailable", "the caller belongs to another host")
        return {
            "schema_version": "library.scope.v1",
            "ecosystem_id": runtime_identity.ecosystem_id,
            "runtime_instance_id": runtime_identity.runtime_instance_id,
            "host_kind": runtime_identity.host_kind,
            "installation_id": context.scope.installation_id,
            "kind": context.scope.kind.value,
            "bot_id": context.scope.bot_id,
            "account_id": context.scope.account_id,
            "role": context.role_binding.role.subject_id,
            "session_id": context.scope.session_id if context.scope.kind is ScopeKind.GROUP else "",
        }

    return scope_for_context


def _envelope(capability, binding, request, *, payload, warnings=()):
    """One bound result; the registry re-checks every echoed field."""
    return {
        "schema_version": capability.output_schema,
        "capability_id": binding.capability,
        "capability_version": binding.version,
        "provider_id": binding.provider,
        "provider_generation": binding.generation,
        "request_id": request["request_id"],
        "trace_id": request["trace_id"],
        "status": "succeeded",
        "reason_code": None,
        "retryable": False,
        "degraded": False,
        "warnings": list(warnings),
        "output": payload,
    }


def _rejected(capability, binding, request, code, reason, *, retryable=False):
    return {
        "schema_version": capability.output_schema,
        "capability_id": binding.capability,
        "capability_version": binding.version,
        "provider_id": binding.provider,
        "provider_generation": binding.generation,
        "request_id": request["request_id"],
        "trace_id": request["trace_id"],
        "status": "rejected",
        "reason_code": code,
        "retryable": retryable,
        "degraded": False,
        "warnings": [reason],
        "output": None,
    }


def _entry_projection(entry):
    """What a catalog listing is allowed to say: no asset bytes, no review bodies."""
    return {
        "entry_id": entry.entry_id,
        "kind": entry.kind.value,
        "title": entry.title,
        "author": entry.author,
        "origin": entry.origin.value,
        "state": entry.state.value,
        "revision": entry.revision,
        "metadata": dict(entry.metadata),
        "source": ({"provider_id": entry.source.provider_id, "provider_version": entry.source.provider_version,
                    "asset_ref": entry.source.asset_ref} if entry.source else None),
    }


def _operation(request, code):
    """The registry passes the whole envelope; the shelf's own fields ride in ``payload``."""
    payload = request.get("payload") if type(request) is dict else None
    if type(payload) is not dict:
        raise TaskError(code, "the shelf needs a bounded request payload")
    return payload


def make_catalog_provider(archive, binding: ProviderBinding, *, runtime_identity):
    """List the shelf's entries for the bound role."""
    project = scope_projector(runtime_identity)

    def invoke(context, request):
        try:
            payload = _operation(request, "library_request_invalid")
        except TaskError:
            return _rejected(CATALOG_CAPABILITY, binding, request, "library_request_invalid",
                             "the shelf needs a bounded request payload")
        operation = payload.get("operation")
        if operation not in ("list", "get"):
            return _rejected(CATALOG_CAPABILITY, binding, request, "library_operation_unsupported",
                             "unsupported catalog operation")
        if operation == "get":
            entry_id = payload.get("entry_id")
            if type(entry_id) is not str or not entry_id:
                return _rejected(CATALOG_CAPABILITY, binding, request, "library_request_invalid",
                                 "a catalog lookup needs its entry id")
            try:
                entry = archive.get_entry(context, entry_id)
            except TaskError as error:
                return _rejected(CATALOG_CAPABILITY, binding, request, error.code, str(error) or error.code)
            return _envelope(CATALOG_CAPABILITY, binding, request,
                             payload={"entries": [_entry_projection(entry)]})
        requested = payload.get("kind")
        if requested is not None and requested not in {kind.value for kind in EntryKind}:
            return _rejected(CATALOG_CAPABILITY, binding, request, "library_request_invalid",
                             "unsupported entry kind")
        try:
            entries = archive.list_entries(context, after_id=payload.get("after_id", "") or "",
                                           kind=requested)
        except TaskError as error:
            return _rejected(CATALOG_CAPABILITY, binding, request, error.code, str(error) or error.code)
        return _envelope(CATALOG_CAPABILITY, binding, request,
                         payload={"entries": [_entry_projection(entry) for entry in entries]})

    return ReadProvider(CATALOG_CAPABILITY, invoke, _authority(archive), project)


def make_read_provider(archive, binding: ProviderBinding, *, runtime_identity):
    """Hand back the provider-owned asset reference after re-checking the entry is readable."""
    project = scope_projector(runtime_identity)

    def invoke(context, request):
        try:
            payload = _operation(request, "library_request_invalid")
        except TaskError:
            return _rejected(READ_CAPABILITY, binding, request, "library_request_invalid",
                             "the shelf needs a bounded request payload")
        entry_id = payload.get("entry_id")
        if type(entry_id) is not str or not entry_id:
            return _rejected(READ_CAPABILITY, binding, request, "library_request_invalid",
                             "a shelf read needs its entry id")
        try:
            entry = archive.get_entry(context, entry_id)
        except TaskError as error:
            return _rejected(READ_CAPABILITY, binding, request, error.code, str(error) or error.code)
        if entry.source is None:
            return _rejected(READ_CAPABILITY, binding, request, "library_asset_unavailable",
                             "a manual entry has no provider asset")
        if entry.state is EntryState.WITHDRAWN:
            return _rejected(READ_CAPABILITY, binding, request, "library_entry_withdrawn",
                             "the provider withdrew this work")
        try:
            consent = archive.consent(context, entry_id, subject=context.actor.subject)
        except TaskError as error:
            return _rejected(READ_CAPABILITY, binding, request, error.code, str(error) or error.code)
        if consent is not None and consent.state.value == "revoked":
            return _rejected(READ_CAPABILITY, binding, request, "library_consent_revoked",
                             "this entry's consent was revoked")
        # The reference is the whole answer: the provider fetches its own bytes.
        return _envelope(READ_CAPABILITY, binding, request, payload={
            "entry_id": entry.entry_id, "kind": entry.kind.value, "state": entry.state.value,
            "excerpt_chars": archive.settings.read(context, archive.tasks.now())["reading_excerpt_chars"],
            "source": {"provider_id": entry.source.provider_id,
                       "provider_version": entry.source.provider_version,
                       "asset_ref": entry.source.asset_ref}})

    return ReadProvider(READ_CAPABILITY, invoke, _authority(archive), project)


def _authority(archive):
    """The shelf's own owner/authorization attestation, re-read on every admit."""

    def authorize(context):
        owner = archive.owner(context)
        settings = archive.settings.read(context, archive.tasks.now())
        return owner, digest(["library-authority.v1", owner, settings])
    return authorize


__all__ = ["CATALOG_CAPABILITY", "READ_CAPABILITY", "make_catalog_provider", "make_read_provider",
           "scope_projector"]

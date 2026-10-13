"""Resolve Content targets from original V2 tasks, never model-supplied identities."""

import json

from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import ScopeKind
from companion_v2.conversation.messages import source_from_document
from . import authoring_service as orchestration
from . import cover_assets as cover


ACTIONS = frozenset("content.work." + name for name in
                    ("create", "save_candidate", "adopt", "retract", "list", "describe", "read"))


def request_key(context, work_id):
    return "content.authoring.request:" + digest([context.key, work_id])


def record_authoring_request(runtime, context, work_id, request):
    """Remember what one work's candidate was written against.

    The model reads a fixed version and then writes a candidate in the same task, so
    the host keeps that request at relationship scope: a save submitted without a
    prior read is a fresh candidate, and a save that contradicts the stored request is
    a stale continuation.
    """
    if request is None or work_id is None:
        return None
    key = request_key(context, work_id)
    with runtime.transaction() as connection:
        connection.execute("INSERT INTO runtime_metadata(key, value) VALUES (?, ?) "
                           "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                           (key, encode(request)))
    return key


def recorded_authoring_request(runtime, context, work_id):
    if work_id is None:
        return None
    row = runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (request_key(context, work_id),))
    if row is None:
        return None
    try:
        value = json.loads(row["value"])
    except (TypeError, ValueError):
        return None
    return value if type(value) is dict else None


def document(value):
    return json.loads(encode(value))


def owner_for(context):
    if context.scope.kind is not ScopeKind.PRIVATE:
        raise TaskError("content_scope_unavailable", "Content requires its original authorized private relationship")
    return {"installation_id": context.scope.installation_id, "bot_id": context.scope.bot_id,
            "role_id": context.role_binding.role.subject_id,
            "owner_key": "relationship:" + digest(context.actor.subject)}


class ContentAccess:
    def __init__(self, application):
        self.application = application
        self.messages, self.runtime = application.messages, application.runtime

    def read_source(self, reference, context, *, expected_hash=None, observed_at=None):
        scope = reference.scope
        if (scope.installation_id, scope.bot_id, scope.account_id, scope.platform, scope.kind) != (
                context.scope.installation_id, context.scope.bot_id, context.scope.account_id,
                context.scope.platform, ScopeKind.PRIVATE):
            raise TaskError("content_source_scope", "Content inputs must retain the original relationship and bot")
        at = self.messages.tasks.now() if observed_at is None else observed_at
        role = require(self.messages.tasks.identity.resolve_role(scope, observed_at=at))
        if role.role != context.role_binding.role:
            raise TaskError("content_source_role", "Content inputs belong to a different original role")
        record = require(self.messages.sources.read(reference, resolved=context.actor, capability="text",
            observed_at=at, authorizer=self.messages.tasks.identity))
        if not set(context.audience.recipients).issubset(record.audience.recipients):
            raise TaskError("content_source_audience", "Content cannot broaden its source audience")
        if expected_hash is not None and record.content_hash != expected_hash:
            raise TaskError("content_source_changed", "Content source differs from its original immutable version")
        # Native tool originals additionally retain their owner's current grant.
        row = self.runtime.read_one("""SELECT i.*, b.context_json FROM extension_tool_invocations i
            JOIN conversation_batches b ON b.batch_id=i.batch_id
            WHERE json_extract(i.result_source_json, '$.source_id')=?
            AND json_extract(i.result_source_json, '$.version.lineage_id')=?
            AND json_extract(i.result_source_json, '$.version.revision')=?""",
            (reference.source_id, reference.version.lineage_id, reference.version.revision))
        if row is not None:
            from companion_v2.execution.models import TaskContext
            external = self.application.external
            if external is None or row["state"] != "succeeded" or digest(record) != row["result_hash"]:
                raise TaskError("content_source_unavailable", "the original tool material is unavailable")
            external._admit(external._descriptor(row), TaskContext.restore(json.loads(row["context_json"])), at)
        native = self.runtime.read_one("""SELECT value FROM runtime_metadata
            WHERE key LIKE 'astrbot.core-tool.%' AND json_extract(value, '$.source.source_id')=?
            AND json_extract(value, '$.source.version.lineage_id')=?
            AND json_extract(value, '$.source.version.revision')=?""",
            (reference.source_id, reference.version.lineage_id, reference.version.revision))
        if native is not None:
            from companion_v2.execution.models import TaskContext
            saved = json.loads(native["value"])
            external = self.application.external
            provider = external.providers.get(saved["action"]) if external is not None else None
            if (provider is None or saved["state"] != "succeeded" or digest(record) != saved["source_hash"]
                    or saved["provider_json"] != encode(provider.descriptor)):
                raise TaskError("content_source_unavailable", "the original native tool material is unavailable")
            external.admit(provider.descriptor, TaskContext.restore(json.loads(saved["context_json"])), at)
        return record

    def reference(self, value, context, *, observed_at=None):
        try:
            data = dict(value)
            expected = data.pop("content_hash", None)
            reference = source_from_document(data)
            if document(reference) != data:
                raise ValueError("noncanonical reference")
        except (KeyError, ValueError, TypeError) as error:
            raise TaskError("content_source_invalid", "Content sources must be complete immutable references") from error
        self.read_source(reference, context, expected_hash=expected, observed_at=observed_at)
        return reference

    def target(self, invocation):
        context = invocation.context
        owner = owner_for(context)
        from companion_v2.conversation.native_tool_sources import input_row, native_invocation, native_turn
        if native_turn(invocation.parent_task_id):
            native_invocation(self.runtime, invocation)
            references = ()
            if invocation.descriptor.tool.action in ("content.work.create", "content.work.save_candidate"):
                original = input_row(self.messages, context, invocation.parent_task_id)
                references = (source_from_document(json.loads(original["source_json"])),)
            sources = [{**document(reference), "content_hash": self.read_source(reference, context).content_hash}
                       for reference in references]
            return {"schema": "content.host-context.v1", "owner": owner,
                    "contributor": {"kind": "role_output", "role": document(context.role_binding.role),
                                    "requested_by": document(context.actor.subject)}, "sources": sources}
        row = self.runtime.read_one("SELECT * FROM extension_tool_invocations WHERE invocation_id=?",
                                    (invocation.invocation_id,))
        if row is None or (row["parent_task_id"], row["tool_call_id"], row["arguments_json"]) != (
                invocation.parent_task_id, invocation.tool_call_id, invocation.arguments_json):
            raise TaskError("content_task_mismatch", "Content requires its actual original tool invocation")
        batch = self.messages.batch(row["batch_id"])
        if batch["origin_key"] != context.key or batch["generation_task_id"] != invocation.parent_task_id:
            raise TaskError("content_task_mismatch", "Content tool belongs to a different original conversation")
        references = ()
        if invocation.descriptor.tool.action in ("content.work.create", "content.work.save_candidate"):
            request = self.messages._request(batch, context, self.messages.tasks.now())
            references = tuple(dict.fromkeys(material.source for material in request.context.materials
                                              if material.source is not None))
            if len(references) > 64:
                raise TaskError("content_source_limit", "Content must retain all original sources within its contract")
        sources = [{**document(reference), "content_hash": self.read_source(reference, context).content_hash}
                   for reference in references]
        return {"schema": "content.host-context.v1", "owner": owner,
                "contributor": {"kind": "role_output", "role": document(context.role_binding.role),
                                "requested_by": document(context.actor.subject)}, "sources": sources}

    def checker(self, invocation, request, target, guard):
        def check(access):
            guard()
            if (type(access) is not dict or set(access) != {"action", "owner", "origin", "work_id",
                    "stored_audience", "sources", "contributor"}
                    or access["owner"] != target["owner"] or access["origin"].get("request") != request
                    or access["origin"].get("request_id") != invocation.invocation_id
                    or any(access["origin"].get(name) != request["context"][context_name] for name, context_name
                           in (("actor", "actor"), ("role", "role_binding"), ("audience", "audience")))
                    or access["contributor"] is not None and access["contributor"] != target["contributor"]):
                raise TaskError("content_access_mismatch", "Content access differs from its original trusted task")
            action = invocation.descriptor.tool.action.removeprefix("content.work.")
            allowed = {"describe": {"read"}, "read": {"read"}, "list": {"list", "read"}}.get(action, {action})
            if access["action"] not in allowed:
                raise TaskError("content_access_action", "Content cannot change the authorized operation")
            stored = access["stored_audience"]
            if stored is not None:
                current = document(invocation.context.audience)
                if (stored.get("recipients") != current["recipients"] or any(
                        stored.get("scope", {}).get(name) != current["scope"][name] for name in
                        ("installation_id", "platform", "kind", "native_scope_id", "bot_id", "account_id"))):
                    raise TaskError("content_work_audience", "Content work belongs to another original audience")
            if type(access["sources"]) is not list or len(access["sources"]) > 64:
                raise TaskError("content_source_invalid", "Content must retain a bounded original source set")
            for source in access["sources"]:
                self.reference(source, invocation.context)
            guard()
        return check

    def continuation(self, invocation, arguments):
        """Validate a candidate save against the version this work read last.

        A save submitted without a prior read is a fresh candidate and carries no
        continuation obligation. Once a request is on record, the save must reuse that
        fixed version: a human revision in between moves the head, and the earlier draft
        belongs to the version it read rather than to the newer one.
        """
        if invocation.descriptor.tool.action != "content.work.save_candidate":
            return None
        request = recorded_authoring_request(self.runtime, invocation.context, arguments.get("work_id"))
        if request is None:
            return None
        return orchestration.continuation(request, arguments)

    def authoring(self, invocation):
        """The host-side writing preferences this relationship runs under.

        Output length follows the selected model route and Content's own manuscript
        contract; V2 does not impose a second character or candidate-count ceiling.
        """
        settings = orchestration.effective_settings(self.runtime, invocation.context)
        return {"enabled": settings.enabled, "direction_prompt": settings.direction_prompt}

    def record_cover(self, invocation, arguments, *, version_id, content_hash):
        """Attach a picture the caller named to the version it belongs to.

        The association is recorded only against an immutable version the provider just
        confirmed, so a late image cannot land on a newer draft. Nothing is generated,
        sent or disclosed here, and a work without a cover intent records nothing.
        """
        intent = cover.CoverIntent.from_arguments(arguments)
        if intent is None:
            return None
        if intent.work_id != arguments.get("work_id") or intent.version_id != version_id:
            raise TaskError("content_cover_stale", "a cover must attach to the version it was drawn for")
        service = cover.ContentCoverService(self.runtime, context=invocation.context)
        return service.associate(work_id=intent.work_id, version_id=version_id, basis_hash=content_hash,
                                 purpose=intent.purpose,
                                 asset={"asset_id": intent.asset_id, "owner": "image.native",
                                        "content_hash": intent.content_hash},
                                 at=self.messages.tasks.now())

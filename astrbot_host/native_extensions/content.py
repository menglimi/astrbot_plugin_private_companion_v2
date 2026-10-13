"""AstrBot lease binding for the independent Content owner; no plugin imports."""

from contextlib import contextmanager
from dataclasses import replace
import inspect
import json

from companion_v2.capabilities.native import json_document
from companion_v2.conversation.content.access import (ACTIONS, ContentAccess, document, owner_for,
                                                       record_authoring_request)
from companion_v2.conversation.content.sources import ContentSources
from companion_v2.execution.models import TaskContext, TaskError, encode


class ContentConsumer:
    def __init__(self, registry, application):
        self.registry, self.application = registry, application
        self.access = ContentAccess(application)
        self.declarations = {entry[0].descriptor.tool.action: entry[0] for entry in registry._entries.values()
                             if entry[0].descriptor.tool.action in ACTIONS}
        if not self.declarations:
            raise ValueError("Content consumer requires the loaded native Content declaration")
        declaration = next(iter(self.declarations.values()))
        if declaration.descriptor.binding.provider != "content.native" or declaration.descriptor.source_owner != "content.native":
            raise ValueError("Content tools require their original declared owner")
        self.port = registry._entries[declaration.host_tool_id][1].port
        for name in ("bind_content_context", "content_state", "content_events"):
            method = getattr(self.port, name, None)
            if not callable(method) or inspect.iscoroutinefunction(method):
                raise ValueError("Content requires its synchronous local host and governance ports")
        self.sources = ContentSources(self.access, state=self.state, events=self.events, admit=self.admit,
            live=self.live, binding={key: value for key, value in document(declaration.descriptor.binding).items()
                                    if key != "capability"})

    def live(self):
        if self.registry._closed or self.registry.application is not self.application:
            raise TaskError("content_provider_unavailable", "the Content consumer lease has closed")
        for declaration in self.declarations.values():
            if self.registry.current_declaration(declaration.host_tool_id) != declaration:
                raise TaskError("content_provider_changed", "the original Content instance or declaration changed")

    def admit(self, binding, context, at):
        self.live()
        self.application.require_running()
        declaration = self.declarations.get(binding.get("capability"))
        if declaration is None or document(declaration.descriptor.binding) != binding:
            raise TaskError("content_provider_changed", "Content material requires its original provider binding")
        self.application.external._admit(declaration.descriptor, context, at)

    def state(self, owner, work_id, version_id):
        self.live()
        if owner["installation_id"] != self.application.runtime.installation_id:
            raise TaskError("content_scope_unavailable", "Content governance crossed installations")
        request = {"schema": "content.state-query.v1", "owner": owner, "work_id": work_id, "version_id": version_id}
        result = json_document(self.port.content_state(request, before_dispatch=self.live))
        if (type(result) is not dict or set(result) != {"schema", "owner", "work_id", "version_id", "state", "revision", "content_hash", "sources"}
                or result["schema"] != "content.work-state.v1" or any(result[key] != request[key] for key in ("owner", "work_id", "version_id"))
                or result["state"] not in ("active", "retracted", "unavailable")
                or type(result["sources"]) is not list or len(result["sources"]) > 64):
            raise TaskError("content_state_invalid", "Content governance differs from its original work query")
        if result["state"] == "active" and (type(result["revision"]) is not int or result["revision"] < 1
                or version_id is None and (result["content_hash"] is not None or result["sources"])
                or version_id is not None and (not isinstance(result["content_hash"], str) or len(result["content_hash"]) != 64)):
            raise TaskError("content_state_invalid", "Content governance requires an immutable version and revision")
        self.live()
        return result

    def events(self, after, limit):
        self.live()
        request = {"schema": "content.governance-query.v1", "installation_id": self.application.runtime.installation_id,
                   "after_seq": after, "limit": limit}
        result = json_document(self.port.content_events(request, before_dispatch=self.live))
        if (type(result) is not dict or set(result) != {"schema", "installation_id", "after_seq", "events", "next_after"}
                or result["schema"] != "content.governance-page.v1"
                or any(result[key] != request[key] for key in ("installation_id", "after_seq"))
                or type(result["events"]) is not list or len(result["events"]) > limit):
            raise TaskError("content_event_invalid", "Content event page differs from its installation cursor")
        cursor = after
        for event in result["events"]:
            if (type(event) is not dict or set(event) != {"seq", "event_id", "owner", "work_id", "revision", "operation_id", "state"}
                    or type(event["seq"]) is not int or event["seq"] <= cursor
                    or type(event["revision"]) is not int or event["revision"] < 1
                    or not all(isinstance(event[key], str) and event[key] for key in ("event_id", "work_id", "operation_id"))
                    or type(event["owner"]) is not dict or set(event["owner"]) != {"installation_id", "bot_id", "role_id", "owner_key"}):
                raise TaskError("content_event_invalid", "Content events require fixed owner and operation identities")
            cursor = event["seq"]
        if type(result["next_after"]) is not int or result["next_after"] != cursor:
            raise TaskError("content_event_invalid", "Content event cursor cannot skip unseen withdrawal events")
        return result

    def dashboard_summary(self, context, at):
        """Project counts from governed Content anchors without copying work text."""
        self.live()
        self.application.messages.authorize(context, at)
        self.sources.synchronize()
        owner = owner_for(context)
        rows = self.application.runtime.read_all(
            """SELECT payload_json, created_at FROM sources WHERE owner=? AND installation_id=?
               AND state='active' AND json_extract(json_extract(payload_json, '$'), '$.owner')=?""",
            ("content.governance", self.application.runtime.installation_id, encode(owner)))
        works = {}
        latest_at = None
        for row in rows:
            try:
                payload = json.loads(json.loads(row["payload_json"]))
                if (type(payload) is not dict or payload.get("schema") != "companion.content-source.v1" or payload.get("owner") != owner
                        or TaskContext.restore(payload["context"]).key != context.key
                        or type(payload.get("work_id")) is not str or not payload["work_id"]):
                    continue
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            works[payload["work_id"]] = max(works.get(payload["work_id"], ""), row["created_at"])
            latest_at = max(latest_at or "", row["created_at"])
        candidate = self.application.runtime.read_one(
            """SELECT COUNT(*) AS total, MAX(COALESCE(i.finished_at, i.created_at)) AS updated_at
               FROM extension_tool_invocations i JOIN conversation_batches b ON b.batch_id=i.batch_id
               WHERE b.origin_key=? AND i.action='content.work.save_candidate' AND i.state='succeeded'""",
            (context.key,))
        candidate_count = int(candidate["total"] if candidate is not None else 0)
        candidate_at = candidate["updated_at"] if candidate is not None else None
        native = self.application.runtime.read_one("""SELECT COUNT(*) AS total, MAX(t.updated_at) AS updated_at
            FROM runtime_metadata n JOIN execution_tasks t ON t.task_id=json_extract(n.value, '$.task_id')
            WHERE n.key LIKE 'astrbot.core-tool.%' AND json_extract(n.value, '$.origin_key')=?
            AND json_extract(n.value, '$.action')='content.work.save_candidate'
            AND json_extract(n.value, '$.state')='succeeded'""", (context.key,))
        candidate_count += int(native["total"] if native is not None else 0)
        if native is not None and native["updated_at"]:
            candidate_at = max(candidate_at or "", native["updated_at"])
        if candidate_at:
            latest_at = max(latest_at or "", candidate_at)
        return {"available": True, "works_count": len(works), "candidate_count": candidate_count,
                "updated_at": latest_at or None}

    @contextmanager
    def bind(self, invocation, request, guard):
        guard()
        target = self.access.target(invocation)
        check = self.access.checker(invocation, request, target, guard)
        # The continuation handshake is a host-side obligation: a candidate that answers
        # a fixed version must be saved against that same version. Providers that ignore
        # the extra argument keep the plain tool contract.
        continuation = self.access.continuation(invocation, json.loads(invocation.arguments_json))
        extra = {"authoring": self.access.authoring(invocation)}
        if continuation is not None:
            extra["continuation"] = continuation.document()
        with self.port.bind_content_context(request, target=target, check_access=check, **extra):
            guard()
            yield

    def adopt(self, invocation, native):
        arguments = json.loads(invocation.arguments_json)
        action = invocation.descriptor.tool.action
        result = native.result
        references = []
        self.sources.synchronize()
        if action in ("content.work.create", "content.work.save_candidate", "content.work.adopt", "content.work.retract"):
            receipt = result.get("receipt", {})
            if (set(result) != {"receipt"} or receipt.get("operation_id") != native.operation_id
                    or receipt.get("action") != action.removeprefix("content.work.")
                    or receipt.get("origin", {}).get("request_id") != invocation.invocation_id
                    or action != "content.work.create" and receipt.get("work_id") != arguments["work_id"]):
                raise TaskError("content_receipt_mismatch", "Content result belongs to another original operation")
            # Control receipts remain readable after withdrawal. They contain no
            # manuscript and cannot be substituted for a version read.
            if action != "content.work.retract":
                self.sources.anchor(invocation.context, document(invocation.descriptor.binding),
                                    receipt["work_id"], receipt["version_id"])
        elif action == "content.work.read":
            if (result.get("work_id"), result.get("version_id"), result.get("offset")) != (
                    arguments["work_id"], arguments["version_id"], arguments.get("offset", 0)):
                raise TaskError("content_version_changed", "Content page must retain the requested fixed version and offset")
            segments = result.get("segments")
            content_hash = result.get("content_hash")
            if (type(segments) is not list or len(segments) > 100
                    or not isinstance(content_hash, str) or len(content_hash) != 64):
                raise TaskError("content_page_invalid", "Content page requires bounded segments and its immutable hash")
            end = result["offset"]
            for segment in segments:
                legacy_fields = {"chapter_id", "chapter_offset", "start", "end", "text"}
                if (type(segment) is not dict or set(segment) not in (
                        legacy_fields, legacy_fields | {"chapter_title"})
                        or "chapter_title" in segment and type(segment["chapter_title"]) is not str
                        or not isinstance(segment["text"], str) or segment["start"] != end
                        or type(segment["end"]) is not int or segment["end"] - end != len(segment["text"])):
                    raise TaskError("content_page_invalid", "Content segments must retain their original Unicode ranges")
                end = segment["end"]
            if end != result.get("end_offset") or end > result["offset"] + arguments.get("limit", 2048):
                raise TaskError("content_page_invalid", "Content page exceeds its requested range")
            references.append(self.sources.anchor(invocation.context, document(invocation.descriptor.binding),
                arguments["work_id"], arguments["version_id"], expected_hash=content_hash))
            # Reading a fixed version is what makes the next candidate a continuation:
            # the host remembers the version that was read so the save must answer it.
            record_authoring_request(self.application.runtime, invocation.context, arguments["work_id"],
                                     {"action": "continue", "brief": "", "feedback": "",
                                      "base_version": arguments["version_id"]})
        else:
            items = result.get("items") if action == "content.work.list" else [result]
            if type(items) is not list or len(items) > arguments.get("limit", 50):
                raise TaskError("content_page_invalid", "Content catalogue is outside its requested budget")
            for item in items:
                if action == "content.work.describe" and item.get("work_id") != arguments["work_id"]:
                    raise TaskError("content_version_changed", "Content description belongs to another original work")
                references.append(self.sources.anchor(invocation.context, document(invocation.descriptor.binding),
                                                      item["work_id"], item["head_version"]))
        response = self.registry._source_response(invocation, native)
        return replace(response, dependencies=tuple(references))

    def close(self):
        self.sources.close()


__all__ = ["ACTIONS", "ContentConsumer"]

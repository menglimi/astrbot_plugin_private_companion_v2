"""The published native-provider JSON protocol, awaiting plugin assembly.

The host injects trusted owner/source/contributor resolution and AccessPort.
This adapter does not resolve identities from model arguments or load V1 code.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable

from .models import Call, Chapter, ContentError, JsonObject, Origin, Receipt, WorkOwner, canonical, digest, identifier, source_union
from .service import ContentService

SCHEMA = "companion.native-provider.v1"
PLUGIN_ID = "astrbot_plugin_private_companion.content"
PROVIDER_ID = "content.native"
_PREFIX = "content.work."
_MUTATIONS = {"create", "save_candidate", "adopt", "retract"}


def _object(properties: dict, required: list[str]) -> dict:
    return dict(type="object", properties=properties, required=required, additionalProperties=False)


_STR = {"type": "string"}
_INT = {"type": "integer"}
_CHAPTERS = {"type": "array", "items": _object(
    {"chapter_id": _STR, "text": _STR, "title": _STR}, ["chapter_id", "text"])}
_PARAMETERS = {
    "create": _object({"title": _STR, "work_type": _STR, "chapters": _CHAPTERS}, ["title", "work_type", "chapters"]),
    "save_candidate": _object({"work_id": _STR, "base_revision": _INT, "base_version": _STR,
                               "chapters": _CHAPTERS}, ["work_id", "base_revision", "base_version", "chapters"]),
    "adopt": _object({"work_id": _STR, "version_id": _STR, "expected_revision": _INT},
                     ["work_id", "version_id", "expected_revision"]),
    "retract": _object({"work_id": _STR, "expected_revision": _INT}, ["work_id", "expected_revision"]),
    "list": _object({"after_id": _STR, "limit": _INT}, []),
    "describe": _object({"work_id": _STR}, ["work_id"]),
    "read": _object({"work_id": _STR, "version_id": _STR, "offset": _INT, "limit": _INT}, ["work_id", "version_id"]),
}
_DESCRIPTIONS = {
    "create": "保存明确要求留存的作品和首个正文版本；保存不表示发送。",
    "save_candidate": "基于明确的作品版本保存候选稿，保留原依据；不会覆盖当前正文。",
    "adopt": "在当前修订仍匹配时采用候选稿；旧任务不能覆盖较新的人工修订。",
    "retract": "撤回作品的本地可读性，保留历史操作回执；不表示已撤回平台消息。",
    "list": "分页发现当前有权读取的作品，不包含正文。",
    "describe": "取得作品当前修订和正文版本标识。",
    "read": "按固定版本和字符范围取回真实原文，不表示已读完或已经分享。",
}


@dataclass(frozen=True)
class ResolvedTarget:
    owner: WorkOwner
    contributor: JsonObject
    sources: tuple[JsonObject, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.owner, WorkOwner) or not isinstance(self.contributor, JsonObject):
            raise ContentError("invalid_resolved_target")
        source_union(self.sources)


def _check_arguments(schema: dict, value: object) -> None:
    kind = schema["type"]
    expected = {"object": dict, "array": list, "integer": int, "string": str}[kind]
    if type(value) is not expected:
        raise ContentError("invalid_content_arguments")
    if kind == "object":
        if set(value) - schema["properties"].keys() or set(schema["required"]) - value.keys():
            raise ContentError("invalid_content_arguments")
        for key, item in value.items():
            _check_arguments(schema["properties"][key], item)
    elif kind == "array":
        for item in value:
            _check_arguments(schema["items"], item)


def _value(item):
    if isinstance(item, (JsonObject, Receipt)):
        return item.value()
    if is_dataclass(item):
        return {field.name: _value(getattr(item, field.name)) for field in fields(item)}
    if isinstance(item, tuple):
        return [_value(child) for child in item]
    return item


def _receipt_value(receipt: Receipt) -> dict:
    """Keep the wire acknowledgement small after a durable local commit.

    Full original refs and envelopes remain in the owner's transaction. Large
    source sets must not make every reconciliation response unreturnable.
    """
    def origin(value: JsonObject | None):
        if value is None:
            return None
        data = value.value()
        return {"request_id": data["request_id"], "fingerprint": digest(value.encoded)}

    value = receipt.value()
    value["origin"] = origin(receipt.origin)
    value["version_origin"] = origin(receipt.version_origin)
    value.pop("sources")
    value["source_fingerprints"] = [digest(source.encoded) for source in receipt.sources]
    return value


def package_hash() -> str:
    """Fingerprint only this native package's source, never a user data path."""
    value = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        value.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return value.hexdigest()


class NativeContentProvider:
    def __init__(self, service: ContentService, *, resolve: Callable[[dict], ResolvedTarget],
                 package_version: str, artifact_hash: str | None = None,
                 configuration_revision: str = "1",
                 now: Callable[[], datetime] | None = None) -> None:
        if not callable(resolve):
            raise ContentError("resolver_required")
        self.service, self.resolve = service, resolve
        self.version = identifier(package_version)
        self.artifact_hash = artifact_hash or package_hash()
        if len(self.artifact_hash) != 64 or any(char not in "0123456789abcdef" for char in self.artifact_hash):
            raise ContentError("invalid_artifact_hash")
        self.generation = "content-" + digest(canonical(dict(
            version=self.version, artifact_hash=self.artifact_hash,
            configuration_revision=identifier(configuration_revision))))
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._closed = False
        self._workers: set[asyncio.Task] = set()

    def _live(self) -> None:
        if self._closed:
            raise ContentError("provider_closed")

    def manifest(self) -> dict:
        self._live()
        tools = [dict(action=_PREFIX + action, capability=_PREFIX + action,
                      source_owner=PROVIDER_ID, description=_DESCRIPTIONS[action],
                      parameters=parameters, side_effect="local" if action in _MUTATIONS else "none",
                      timeout_seconds=15) for action, parameters in _PARAMETERS.items()]
        return json.loads(canonical(dict(
            schema=SCHEMA, plugin_id=PLUGIN_ID, provider_id=PROVIDER_ID, generation=self.generation,
            package=dict(extension_id="content", package_id=PLUGIN_ID, publisher_id="menglimi",
                         package_version=self.version, artifact_hash=self.artifact_hash,
                         capabilities=[tool["capability"] for tool in tools], dataset_owners=[PROVIDER_ID]),
            tools=tools)))

    def _request(self, request: dict) -> tuple[dict, str, datetime]:
        self._live()
        value = JsonObject.capture(request).value()
        required = {"schema", "invocation_id", "parent_task_id", "tool_call_id", "action", "origin_key",
                    "context", "binding", "arguments", "arguments_hash", "deadline_at"}
        if set(value) != required or value["schema"] != SCHEMA:
            raise ContentError("invalid_native_request")
        for key in ("invocation_id", "parent_task_id", "tool_call_id", "origin_key", "arguments_hash", "action"):
            identifier(value[key])
        action = value["action"].removeprefix(_PREFIX)
        if value["action"] != _PREFIX + action or action not in _PARAMETERS:
            raise ContentError("unsupported_content_action")
        if value["binding"] != dict(capability=value["action"], provider=PROVIDER_ID,
                                     version=self.version, generation=self.generation):
            raise ContentError("native_binding_mismatch")
        context = value["context"]
        if (type(context) is not dict or set(context) != {"actor", "role_binding", "audience"}
                or any(type(item) is not dict or not item for item in context.values())):
            raise ContentError("invalid_native_context")
        try:
            deadline = datetime.fromisoformat(value["deadline_at"])
            if deadline.tzinfo is None or deadline.utcoffset() is None:
                raise ValueError("timezone required")
        except (TypeError, ValueError) as exc:
            raise ContentError("invalid_deadline") from exc
        _check_arguments(_PARAMETERS[action], value["arguments"])
        return value, action, deadline

    @staticmethod
    def _origin(value: dict) -> Origin:
        identity = {key: value[key] for key in (
            "schema", "invocation_id", "parent_task_id", "tool_call_id", "action", "origin_key", "arguments_hash")}
        identity["arguments_fingerprint"] = digest(canonical(value["arguments"]))
        identity["binding"] = {key: value["binding"][key] for key in ("capability", "provider", "version")}
        return Origin(value["invocation_id"], JsonObject.capture(value),
                      JsonObject.capture(value["context"]["actor"]),
                      JsonObject.capture(value["context"]["role_binding"]),
                      JsonObject.capture(value["context"]["audience"]), JsonObject.capture(identity))

    def _dispatch(self, value: dict, action: str, call: Call,
                  target: ResolvedTarget, lookup: bool):
        if lookup:
            if action not in _MUTATIONS:
                raise ContentError("no_persisted_operation")
            return self.service.lookup_request(call, target.owner, value["invocation_id"])
        arguments = dict(value["arguments"])
        if action in _MUTATIONS:
            arguments["operation_key"] = value["invocation_id"]
        if action in {"create", "save_candidate"}:
            arguments["chapters"] = tuple(Chapter(**chapter) for chapter in arguments["chapters"])
            arguments.update(contributor=target.contributor, sources=target.sources)
        method = {"list": "list_works", "describe": "get_work", "read": "read_version"}.get(action, action)
        return getattr(self.service, method)(call, target.owner, **arguments)

    @staticmethod
    def _response(value: dict, result) -> dict:
        receipt = result if isinstance(result, Receipt) else None
        return {**{key: value[key] for key in ("schema", "invocation_id", "origin_key", "arguments_hash", "binding")},
                "state": "succeeded", "effect": "committed" if receipt else "none",
                "operation_id": receipt.operation_id if receipt else None,
                "receipt_ref": "content.native.operation:" + receipt.operation_id if receipt else None,
                "result": {"receipt": _receipt_value(receipt)} if receipt else _value(result), "artifacts": []}

    async def _run(self, request: dict, before_dispatch, *, lookup: bool) -> dict:
        value, action, deadline = self._request(request)
        if not callable(before_dispatch):
            raise ContentError("guard_required")
        cancelled = Event()

        def guard() -> None:
            self._live()
            if cancelled.is_set():
                raise ContentError("operation_cancelled")
            if self.now() >= deadline:
                raise ContentError("deadline_expired")
            checked = before_dispatch()
            if checked is not None:
                if inspect.iscoroutine(checked):
                    checked.close()
                raise ContentError("synchronous_guard_required")

        guard()
        target = self.resolve(json.loads(canonical(value)))
        if not isinstance(target, ResolvedTarget):
            raise ContentError("invalid_resolved_target")
        guard()
        call = Call(self._origin(value), guard)
        worker = asyncio.create_task(asyncio.to_thread(self._dispatch, value, action, call, target, lookup))
        self._workers.add(worker)
        try:
            try:
                result = await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancelled.set()
                # Cancellation can race with COMMIT. Keep even a second cancel
                # from cancelling the worker's result while the transaction settles.
                settlement = asyncio.gather(worker, return_exceptions=True)
                while True:
                    try:
                        result = (await asyncio.shield(settlement))[0]
                        break
                    except asyncio.CancelledError:
                        continue
                if not isinstance(result, Receipt) or result.effect != "committed":
                    raise
            # A committed control receipt contains no manuscript. Later loss of
            # access cannot erase that fact; new I/O and readable material still
            # require the current guard. The host governs receipt adoption.
            if not isinstance(result, Receipt) or result.effect != "committed":
                guard()
            response = self._response(value, result)
            if len(canonical(response).encode("utf-8")) > 65_536:
                raise ContentError("native_response_too_large")
            return response
        finally:
            self._workers.discard(worker)

    async def execute(self, request: dict, *, before_dispatch) -> dict:
        return await self._run(request, before_dispatch, lookup=False)

    async def lookup(self, request: dict, *, before_dispatch) -> dict:
        return await self._run(request, before_dispatch, lookup=True)

    async def close(self) -> None:
        self._closed = True
        await asyncio.gather(*tuple(self._workers), return_exceptions=True)
        await asyncio.to_thread(self.service.close)

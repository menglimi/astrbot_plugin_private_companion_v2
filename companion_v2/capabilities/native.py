"""JSON/bytes values shared with the V2 plugin's internal extension ports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import re

from companion_v2.execution.models import SideEffect, TaskError, TaskResult, encode
from .models import CapabilityPackageDescriptor, _opaque


SCHEMA = "companion.native-provider.v1"
MAX_DOCUMENT_BYTES = 65536
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
MAX_ARTIFACTS = 8


def json_document(value, *, maximum=MAX_DOCUMENT_BYTES):
    """Copy plain finite JSON only, never runtime-owned Python objects."""
    def check(item, depth=0):
        if depth > 24:
            raise ValueError("native JSON nesting exceeds the contract")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("native JSON keys must be strings")
            for child in item.values():
                check(child, depth + 1)
        elif type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif type(item) not in (str, int, float, bool, type(None)):
            raise ValueError("native payload must be plain JSON")
    check(value)
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
    if len(text.encode("utf-8")) > maximum:
        raise ValueError("native document exceeds its byte budget")
    return json.loads(text)


@dataclass(frozen=True)
class NativeManifest:
    plugin_id: str
    provider_id: str
    generation: str
    package: CapabilityPackageDescriptor
    document_json: str

    @property
    def tools(self):
        return tuple(json.loads(self.document_json)["tools"])


def parse_manifest(value, *, plugin_id, version):
    value = json_document(value)
    if (type(value) is not dict or set(value) != {"schema", "plugin_id", "provider_id", "generation", "package", "tools"}
            or value["schema"] != SCHEMA or value["plugin_id"] != plugin_id):
        raise ValueError("native provider identity or schema mismatch")
    for name in ("plugin_id", "provider_id", "generation"):
        _opaque(value[name], field=name)
    package = value["package"]
    if (type(package) is not dict or set(package) != {"extension_id", "package_id", "publisher_id", "package_version",
            "artifact_hash", "capabilities", "dataset_owners"}
            or package["package_id"] != plugin_id or package["package_version"] != version
            or type(package["capabilities"]) is not list or type(package["dataset_owners"]) is not list):
        raise ValueError("native package differs from the loaded Star")
    package = CapabilityPackageDescriptor(**{**package, "capabilities": tuple(package["capabilities"]),
                                              "dataset_owners": tuple(package["dataset_owners"])})
    tools = value["tools"]
    # A manifest declares installed tools, not a single model request. Its total
    # UTF-8 byte budget is checked by json_document before parsing the catalog.
    if (type(tools) is not list or not tools
            or any(type(tool) is not dict or set(tool) != {"action", "capability", "source_owner", "description",
                       "parameters", "side_effect", "timeout_seconds"} for tool in tools)):
        raise ValueError("native tools require a bounded complete declaration")
    if len({tool["action"] for tool in tools}) != len(tools):
        raise ValueError("native actions must be unique")
    for tool in tools:
        if type(tool["timeout_seconds"]) not in (int, float):
            raise ValueError("native timeout must be a JSON number")
        if SideEffect(tool["side_effect"]) is SideEffect.MESSAGE_DELIVERY:
            raise ValueError("platform sending belongs to the V2 sender")
        if tool["capability"] not in package.capabilities or tool["source_owner"] not in package.dataset_owners:
            raise ValueError("native tool exceeds its package")
    return NativeManifest(plugin_id, value["provider_id"], value["generation"], package, encode(value))


@dataclass(frozen=True)
class NativeArtifact:
    artifact_id: str
    operation_id: str
    content_hash: str
    mime_type: str
    size_bytes: int
    content: bytes | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        for name in ("artifact_id", "operation_id", "mime_type"):
            _opaque(getattr(self, name), field=name)
        if (type(self.content_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", self.content_hash) is None
                or type(self.size_bytes) is not int or not 0 < self.size_bytes <= MAX_ARTIFACT_BYTES):
            raise ValueError("native artifact requires a bounded size and SHA-256")
        if self.content is not None and (type(self.content) is not bytes or len(self.content) != self.size_bytes
                or hashlib.sha256(self.content).hexdigest() != self.content_hash):
            raise ValueError("native artifact bytes differ from their original receipt")

    def with_content(self, content):
        if type(content) is not bytes:
            raise ValueError("native artifact readers must return bytes")
        return replace(self, content=content)

    def metadata(self):
        return {name: getattr(self, name) for name in
                ("artifact_id", "operation_id", "content_hash", "mime_type", "size_bytes")}


@dataclass(frozen=True)
class NativeResult:
    state: str
    effect: str
    operation_id: str | None
    receipt_ref: str | None
    result_json: str
    artifacts: tuple[NativeArtifact, ...] = ()

    @property
    def result(self):
        return json.loads(self.result_json)

    def metadata(self, binding):
        return {"schema": SCHEMA, "binding": asdict(binding), "operation_id": self.operation_id,
                "receipt_ref": self.receipt_ref, "result": self.result,
                "artifacts": [artifact.metadata() for artifact in self.artifacts]}


def invocation_request(invocation):
    return json_document({"schema": SCHEMA, "invocation_id": invocation.invocation_id,
        "parent_task_id": invocation.parent_task_id, "tool_call_id": invocation.tool_call_id,
        "action": invocation.descriptor.tool.action, "origin_key": invocation.context.key,
        "context": json.loads(encode(invocation.context)), "binding": asdict(invocation.descriptor.binding),
        "arguments": json.loads(invocation.arguments_json), "arguments_hash": invocation.arguments_hash,
        "deadline_at": invocation.deadline_at.isoformat()})


def parse_result(value, *, request, side_effect):
    value = json_document(value)
    keys = {"schema", "invocation_id", "origin_key", "arguments_hash", "binding", "state", "effect",
            "operation_id", "receipt_ref", "result", "artifacts"}
    if type(value) is not dict or set(value) != keys or any(value[key] != request[key] for key in
            ("schema", "invocation_id", "origin_key", "arguments_hash", "binding")):
        raise TaskError("native_receipt_mismatch", "native result differs from its original invocation")
    if value["state"] not in ("succeeded", "failed", "unknown"):
        raise ValueError("native result requires an explicit outcome")
    expected = "none" if side_effect is SideEffect.NONE else {
        "succeeded": "committed", "failed": "not_committed", "unknown": "unknown"}[value["state"]]
    if value["effect"] != expected or (side_effect is SideEffect.NONE and value["operation_id"] is not None):
        raise ValueError("native effect receipt differs from its declared contract")
    TaskResult("uncertain" if value["state"] == "unknown" else value["state"], value["effect"],
               operation_id=value["operation_id"], receipt_ref=value["receipt_ref"])
    if value["state"] == "failed" and value["receipt_ref"] is None:
        raise ValueError("known failure requires an owner receipt")
    if (type(value["artifacts"]) is not list or len(value["artifacts"]) > MAX_ARTIFACTS
            or (value["state"] == "succeeded" and type(value["result"]) is not dict)
            or (value["state"] != "succeeded" and (value["result"] is not None or value["artifacts"]))):
        raise ValueError("native materials must belong to one successful operation")
    artifact_keys = {"artifact_id", "operation_id", "content_hash", "mime_type", "size_bytes"}
    if any(type(item) is not dict or set(item) != artifact_keys for item in value["artifacts"]):
        raise ValueError("native artifact references contain metadata only")
    artifacts = tuple(NativeArtifact(**item) for item in value["artifacts"])
    if (len({artifact.artifact_id for artifact in artifacts}) != len(artifacts)
            or any(artifact.operation_id != value["operation_id"] for artifact in artifacts)
            or sum(artifact.size_bytes for artifact in artifacts) > MAX_ARTIFACT_BYTES):
        raise ValueError("native artifacts exceed their original operation or shared budget")
    return NativeResult(value["state"], value["effect"], value["operation_id"], value["receipt_ref"],
                        encode(value["result"]), artifacts)

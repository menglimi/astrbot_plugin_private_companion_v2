"""Shared wire envelope validation against a trusted private host binding."""

from dataclasses import asdict
from datetime import datetime
import json
import re

from companion_v2.execution.models import TaskContext, digest
from companion_v2.foundation.refs import ScopeKind, normalize_utc
from .models import owner_key


RESULT_SCHEMA_VERSION = "memory.result.v1"
CAPABILITY_VERSION = "1.0"
_TOKEN = re.compile(r"^[^\s\x00-\x1f\x7f]+$")
_FEATURE = re.compile(r"^[a-z][a-z0-9_.-]*@[1-9][0-9]*$")
_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-5][0-9](?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-5][0-9])$")
_EXTENSION_NAME = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
_EXTENSION_VERSION = re.compile(r"^[1-9][0-9]*\.[0-9]+$")
_TOP_LEVEL = frozenset({
    "schema_version", "capability_id", "capability_version", "provider_id",
    "provider_generation", "request_id", "trace_id", "deadline_at", "scope",
    "required_features", "budget", "payload",
})
_BUDGET_FIELDS = frozenset({
    "max_input_bytes", "max_model_calls", "max_output_bytes", "max_tokens",
    "max_candidates", "max_concurrency",
})
_RETENTIONS = frozenset({"session", "short", "durable", "protected"})


def runtime_scope_from_task_context(context: TaskContext, *, ecosystem_id, runtime_instance_id, host_kind):
    """Project a resolved private TaskContext using only trusted binding fields."""
    scope = context.scope
    if scope.kind is not ScopeKind.PRIVATE or not scope.is_resolved:
        raise ValueError("wire memory scope requires a resolved private TaskContext")
    principal = context.actor.principal
    return {
        "ecosystem_id": _token(ecosystem_id, "ecosystem_id"),
        "installation_id": scope.installation_id,
        "runtime_instance_id": _token(runtime_instance_id, "runtime_instance_id"),
        "host_kind": _token(host_kind, "host_kind"),
        "host_id": principal.host_id,
        "bot_id": scope.bot_id,
        "platform": scope.platform,
        "account_id": scope.account_id,
        "conversation_ref": scope.conversation_id,
        "platform_conversation_id": scope.native_scope_id,
        "session_id": scope.session_id,
        "user_id": principal.native_account_id,
        "group_id": None,
        "persona_id": context.role_binding.role.subject_id,
        "persona_binding_revision": context.role_binding.revision,
    }


class _WireIssue(ValueError):
    def __init__(self, reason_code, status="rejected"):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.status = status


def _token(value, name, *, maximum=256):
    if type(value) is not str or not 1 <= len(value) <= maximum or not _TOKEN.fullmatch(value):
        raise _WireIssue("invalid_" + name)
    return value


def _integer(value, name, *, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise _WireIssue("invalid_" + name)
    return value


def _time(value, name, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not str or not _TIME.fullmatch(value):
        raise _WireIssue("invalid_" + name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
        return normalize_utc(parsed, field=name)
    except (TypeError, ValueError):
        raise _WireIssue("invalid_" + name) from None


def _unique_list(value, name, *, maximum, item_validator):
    if type(value) is not list or len(value) > maximum:
        raise _WireIssue("invalid_" + name)
    encoded = set()
    checked = []
    for item in value:
        item_validator(item)
        marker = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if marker in encoded:
            raise _WireIssue("duplicate_" + name)
        encoded.add(marker)
        checked.append(item)
    return checked


class MemoryWireBinding:
    extra_request_fields = frozenset()

    def __init__(self, memory, *, provider_id, provider_generation, scope_for_context,
                 max_input_bytes=65536, max_output_bytes=65536):
        self.memory = memory
        self.provider_id = _token(provider_id, "provider_id")
        self.provider_generation = _token(provider_generation, "provider_generation")
        if not callable(scope_for_context):
            raise ValueError("trusted scope projection is required")
        if (type(max_input_bytes) is not int or max_input_bytes < 1
                or type(max_output_bytes) is not int or max_output_bytes < 1):
            raise ValueError("wire byte budgets must be positive integers")
        self.scope_for_context = scope_for_context
        self.max_input_bytes, self.max_output_bytes = max_input_bytes, max_output_bytes

    def _envelope(self, request, *, status, reason_code=None, output=None, warnings=(), retryable=False):
        request_id = request.get("request_id") if type(request) is dict else None
        trace_id = request.get("trace_id") if type(request) is dict else None
        request_id = request_id if type(request_id) is str and len(request_id) <= 256 and _TOKEN.fullmatch(request_id) else "invalid-request"
        trace_id = trace_id if type(trace_id) is str and len(trace_id) <= 256 and _TOKEN.fullmatch(trace_id) else "invalid-trace"
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "capability_id": self.capability_id,
            "capability_version": CAPABILITY_VERSION,
            "provider_id": self.provider_id,
            "provider_generation": self.provider_generation,
            "request_id": request_id,
            "trace_id": trace_id,
            "status": status,
            "reason_code": reason_code,
            "retryable": retryable,
            "degraded": status == "partial",
            "warnings": list(warnings),
            "output": output,
        }

    def _validate_envelope(self, context: TaskContext, request):
        fields = _TOP_LEVEL | self.extra_request_fields
        if type(request) is not dict or set(request) - fields or not fields.difference({"required_features"}).issubset(request):
            raise _WireIssue("invalid_request")
        if request["schema_version"] != self.schema_version or request["capability_id"] != self.capability_id:
            raise _WireIssue("unsupported_schema_version")
        if request["capability_version"] != CAPABILITY_VERSION:
            raise _WireIssue("unsupported_capability_version")
        request_id = _token(request["request_id"], "request_id")
        trace_id = _token(request["trace_id"], "trace_id")
        provider_id = _token(request["provider_id"], "provider_id")
        provider_generation = _token(request["provider_generation"], "provider_generation")
        if provider_id != self.provider_id or provider_generation != self.provider_generation:
            raise _WireIssue("provider_binding_mismatch", "unavailable")
        if "required_features" in request:
            features = _unique_list(request["required_features"], "required_features", maximum=32,
                                    item_validator=lambda item: self._validate_feature(item))
            if features:
                raise _WireIssue("required_feature_unavailable", "unavailable")
        deadline = _time(request["deadline_at"], "deadline_at")
        now = normalize_utc(self.memory.tasks.now(), field="wire clock")
        if deadline <= now:
            raise _WireIssue("deadline_expired", "timeout")
        try:
            request_bytes = len(json.dumps(request, ensure_ascii=False, allow_nan=False,
                                          separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError, UnicodeError):
            raise _WireIssue("invalid_request") from None
        if type(request.get("budget")) is not dict:
            raise _WireIssue("invalid_budget")
        budget = request["budget"]
        if set(budget) - _BUDGET_FIELDS or not {"max_input_bytes", "max_model_calls"}.issubset(budget):
            raise _WireIssue("invalid_budget")
        requested_input = _integer(budget["max_input_bytes"], "input_budget", minimum=1)
        max_input = min(requested_input, self.max_input_bytes)
        _integer(budget["max_model_calls"], "model_call_budget")
        for name in ("max_output_bytes", "max_tokens", "max_candidates", "max_concurrency"):
            if name in budget:
                _integer(budget[name], name + "_budget", minimum=1 if name in ("max_output_bytes", "max_concurrency") else 0)
        if request_bytes > max_input:
            raise _WireIssue("input_budget_exceeded")
        if type(request.get("scope")) is not dict:
            raise _WireIssue("scope_mismatch", "permission_denied")
        if context.scope.kind is not ScopeKind.PRIVATE:
            raise _WireIssue("private_memory_only", "unavailable")
        try:
            expected_scope = self.scope_for_context(context)
        except Exception:
            raise _WireIssue("trusted_scope_unavailable", "unavailable") from None
        if type(expected_scope) is not dict or self._validate_runtime_scope(expected_scope) is None:
            raise _WireIssue("trusted_scope_unavailable", "unavailable")
        if self._validate_runtime_scope(request["scope"]) is None or request["scope"] != expected_scope:
            raise _WireIssue("scope_mismatch", "permission_denied")

        return {"request_id": request_id, "trace_id": trace_id, "deadline": deadline, "budget": budget}

    @staticmethod
    def _validate_runtime_scope(value):
        required = {
            "ecosystem_id", "installation_id", "runtime_instance_id", "host_kind",
            "bot_id", "platform", "account_id", "conversation_ref",
            "platform_conversation_id", "session_id", "user_id", "group_id",
            "persona_id", "persona_binding_revision",
        }
        allowed = required | {"host_id", "conversation_id"}
        if set(value) - allowed or not required.issubset(value):
            return None
        for name in ("ecosystem_id", "installation_id", "runtime_instance_id", "host_kind", "bot_id", "persona_id"):
            _token(value[name], "scope_" + name)
        if value["host_kind"] in {"plugin_hosted", "standalone_service", "embedded_app", "split_services"}:
            raise _WireIssue("invalid_scope_host_kind", "unavailable")
        for name in ("platform", "account_id", "conversation_ref", "platform_conversation_id", "session_id", "user_id", "group_id", "host_id", "conversation_id"):
            if name not in value:
                continue
            if value[name] is not None:
                _token(value[name], "scope_" + name)
        _integer(value["persona_binding_revision"], "persona_binding_revision")
        if value["platform"] is None:
            if any(value.get(name) is not None for name in ("account_id", "platform_conversation_id", "user_id", "group_id", "conversation_id")):
                raise _WireIssue("invalid_runtime_scope")
        elif value["account_id"] is None:
            raise _WireIssue("invalid_runtime_scope")
        if value["platform_conversation_id"] is not None and value["conversation_ref"] is None:
            raise _WireIssue("invalid_runtime_scope")
        if value["group_id"] is not None and (value["conversation_ref"] is None or value["platform_conversation_id"] is None):
            raise _WireIssue("invalid_runtime_scope")
        if value.get("conversation_id") is not None and value["conversation_id"] != value["platform_conversation_id"]:
            raise _WireIssue("invalid_runtime_scope")
        return value

    @staticmethod
    def _validate_feature(value):
        if type(value) is not str or not _FEATURE.fullmatch(value):
            raise _WireIssue("invalid_required_feature")

    def _policy_revision(self, context):
        if self.memory.settings:
            return "policy-" + self.memory.settings.read(context)[1]
        return "policy-" + digest(asdict(self.memory.writer.access.policy_for(context)))

    def binding_authority(self, context):
        """Return the current owner and policy fence used by a provider lease."""
        self.memory.writer.access.check(context, "memory.read")
        return owner_key(context), self._policy_revision(context)

"""Host-owned, process-local discovery and leases for synchronous read providers.

This is an internal application API, not the review control wire or a Python
sandbox. Only trusted assembly registers handlers; callers supply an already
authenticated TaskContext. Effects and asynchronous work use TaskSupervisor.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import inspect
import json
import re
from uuid import uuid4

from companion_v2.execution.models import ProviderBinding, TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import normalize_utc

from .models import CapabilityPackageDescriptor
from .repositories import CapabilityRepository


def _token(value):
    if type(value) is not str or not 1 <= len(value) <= 256 or re.search(r"[\s\x00-\x1f\x7f]", value):
        raise ValueError("provider identifiers must be bounded opaque tokens")
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ReadLimits:
    max_input_bytes: int = 65536
    max_output_bytes: int = 65536

    def __post_init__(self):
        if any(type(value) is not int or not 1 <= value <= 1048576 for value in asdict(self).values()):
            raise ValueError("read provider byte limits must be between 1 and 1048576")

    def intersect(self, other):
        return ReadLimits(min(self.max_input_bytes, other.max_input_bytes),
                          min(self.max_output_bytes, other.max_output_bytes))


@dataclass(frozen=True)
class ReadCapability:
    capability_id: str
    capability_version: str
    input_schema: str
    output_schema: str
    permissions: tuple[str, ...]
    profile: str
    features: tuple[str, ...] = ()
    limits: ReadLimits = ReadLimits()
    supports_pending: bool = False

    def __post_init__(self):
        for name in ("capability_id", "capability_version", "input_schema", "output_schema", "profile"):
            _token(getattr(self, name))
        if not isinstance(self.limits, ReadLimits) or not self.permissions or type(self.supports_pending) is not bool:
            raise ValueError("read capabilities require permissions and finite limits")
        for values in (self.permissions, self.features):
            if not isinstance(values, tuple) or len(values) > 32 or len(set(values)) != len(values):
                raise ValueError("provider permissions/features must be bounded unique tuples")
            for value in values:
                _token(value)


@dataclass(frozen=True)
class ReadProvider:
    capability: ReadCapability
    invoke: object
    authorize: object
    scope_for_context: object
    package: CapabilityPackageDescriptor | None = None

    def __post_init__(self):
        if not isinstance(self.capability, ReadCapability):
            raise ValueError("a read provider requires a fixed capability descriptor")
        for port in (self.invoke, self.authorize, self.scope_for_context):
            if not callable(port) or inspect.iscoroutinefunction(port):
                raise ValueError("read provider ports must be trusted synchronous functions")
        if self.package is not None and (not isinstance(self.package, CapabilityPackageDescriptor)
                or self.capability.capability_id not in self.package.capabilities):
            raise ValueError("the pinned package must declare this capability")


@dataclass(frozen=True)
class ReadRegistration:
    """Runtime-issued registration; an old registration cannot remove a new one."""
    binding: ProviderBinding
    capability: ReadCapability


@dataclass(frozen=True)
class ReadBinding:
    binding_ref: str
    provider: ProviderBinding
    capability: ReadCapability
    owner_ref: str
    scope_json: str
    limits: ReadLimits
    expires_at: datetime

    @property
    def scope(self):
        return json.loads(self.scope_json)


@dataclass(frozen=True)
class _Lease:
    public: ReadBinding
    context_key: str
    authority: str


class ReadProviderRegistry:
    """One host-thread registry with finite leases and no per-binding timers.

    Registration does not imply readiness: the application guard and current
    supervisor generation are checked on every discovery, binding and invocation.
    The small fixed catalog is bounded at registration, not after reading it.
    """

    def __init__(self, tasks, *, require_running, max_providers=32, max_bindings=256):
        if not callable(require_running):
            raise ValueError("a host lifecycle guard is required")
        for value, maximum in ((max_providers, 32), (max_bindings, 4096)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("registry capacity must be finite")
        self.tasks, self.require_running = tasks, require_running
        self.packages = CapabilityRepository(tasks.runtime)
        self.max_providers, self.max_bindings = max_providers, max_bindings
        self._providers, self._leases = {}, {}
        self._closed = False

    def register(self, provider_id, capability, factory):
        """Trusted assembly only. No imports, downloads or choice changes occur."""
        _token(provider_id)
        if self._closed:
            raise TaskError("provider_registry_closed", "provider registration has stopped")
        if not isinstance(capability, ReadCapability) or not callable(factory):
            raise ValueError("registration requires a descriptor and provider factory")
        key = (capability.capability_id, capability.capability_version, provider_id)
        if key in self._providers:
            raise TaskError("provider_registration_conflict", "unregister the original provider before replacing it")
        if len(self._providers) >= self.max_providers:
            raise TaskError("provider_registry_full", "read provider catalog is full")
        binding = ProviderBinding(key[0], key[2], key[1], "read-" + uuid4().hex)
        provider = factory(binding)
        if not isinstance(provider, ReadProvider) or provider.capability != capability:
            raise ValueError("provider factory must implement the registered descriptor")
        registration = ReadRegistration(binding, capability)
        self._providers[key] = (registration, provider)
        return registration

    def unregister(self, registration):
        key = self._key(registration.binding)
        entry = self._providers.get(key)
        if entry is None or entry[0] != registration:
            return False
        del self._providers[key]
        self._leases = {ref: lease for ref, lease in self._leases.items()
                        if lease.public.provider != registration.binding}
        return True

    @staticmethod
    def _key(binding):
        return binding.capability, binding.version, binding.provider

    def _running(self):
        if self._closed:
            raise TaskError("provider_registry_closed", "read provider intake has stopped")
        self.require_running()
        require(self.tasks.check_generation())

    def _admit(self, context, registration, provider):
        self._running()
        at = self.tasks.now()
        decisions = []
        for action in provider.capability.permissions:
            decision = require(self.tasks.authorize_context(context, action=action, observed_at=at))
            decisions.append((decision.tier.value, decision.policy_revision,
                              decision.identity_policy_revision))
        package_state = None
        if provider.package is not None:
            package = provider.package
            installed = require(self.packages.installation(extension_id=package.extension_id))
            if (installed.package_id, installed.package_version, installed.artifact_hash) != (
                    package.package_id, package.package_version, package.artifact_hash):
                raise TaskError("provider_package_changed", "the original provider package has changed")
            catalog = require(self.packages.descriptor(extension_id=package.extension_id,
                package_id=package.package_id, package_version=package.package_version))
            if catalog != package:
                raise TaskError("provider_package_changed", "provider descriptor differs from the trusted catalog")
            selected = require(self.packages.require_role_enabled(extension_id=package.extension_id,
                role=context.role_binding.role, bot_id=context.scope.bot_id))
            consent = require(self.packages.authorize(extension_id=package.extension_id,
                capability_id=registration.binding.capability, subject=context.actor.subject, scope=context.scope))
            package_state = (installed.revision, selected.revision, consent.revision)
        # Domain owners return their stable owner and current policy revision.
        try:
            owner_ref, revision = provider.authorize(context)
            _token(owner_ref)
            _token(revision)
        except TaskError:
            raise
        except Exception:
            raise TaskError("provider_authorization_unavailable", "the provider cannot attest current authorization") from None
        try:
            scope = provider.scope_for_context(context)
            if type(scope) is not dict:
                raise ValueError("invalid scope")
            scope_json = _json(scope)
            if len(scope_json.encode("utf-8")) > provider.capability.limits.max_input_bytes:
                raise ValueError("scope exceeds input budget")
        except Exception:
            raise TaskError("provider_scope_unavailable", "the provider has no trusted scope projection") from None
        if self._providers.get(self._key(registration.binding)) != (registration, provider):
            raise TaskError("provider_binding_unavailable", "the original provider registration has changed")
        return owner_ref, digest([decisions, revision, package_state]), scope_json

    @outcome
    def discover(self, context, *, capability_id):
        """List authorized entries for one capability; never allocate a binding."""
        self._running()
        entries = []
        for registration, provider in tuple(self._providers.values()):
            if registration.binding.capability != capability_id:
                continue
            try:
                owner, _, _ = self._admit(context, registration, provider)
            except TaskError:
                continue
            entries.append({"provider": asdict(registration.binding),
                            "capability": asdict(registration.capability), "owner_ref": owner})
        self._running()
        return tuple(sorted(entries, key=lambda item: (item["provider"]["provider"], item["provider"]["version"])))

    @outcome
    def bind(self, context, *, capability_id, capability_version, provider_id,
             required_features=(), limits=ReadLimits(), ttl_seconds=300):
        self._running()
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 600 or not isinstance(limits, ReadLimits):
            raise TaskError("provider_binding_invalid", "binding requires finite limits and a lease of at most 600 seconds")
        if (not isinstance(required_features, tuple) or len(required_features) > 32
                or any(type(item) is not str for item in required_features)
                or len(set(required_features)) != len(required_features)):
            raise TaskError("provider_features_invalid", "required features must be a bounded unique tuple")
        entry = self._providers.get((capability_id, capability_version, provider_id))
        if entry is None:
            raise TaskError("provider_unavailable", "the explicitly selected read provider is unavailable")
        registration, provider = entry
        owner, authority, scope = self._admit(context, registration, provider)
        if not set(required_features).issubset(provider.capability.features):
            raise TaskError("provider_feature_unavailable", "the selected provider does not support the required features")
        now = self.tasks.now()
        self._leases = {ref: lease for ref, lease in self._leases.items() if lease.public.expires_at > now}
        if len(self._leases) >= self.max_bindings:
            raise TaskError("provider_bindings_full", "release a binding or wait for its lease to expire")
        public = ReadBinding("read-binding-" + uuid4().hex, registration.binding, provider.capability,
                             owner, scope, limits.intersect(provider.capability.limits), now + timedelta(seconds=ttl_seconds))
        self._leases[public.binding_ref] = _Lease(public, context.key, authority)
        return public

    def _lease(self, context, binding_ref):
        self._running()
        lease = self._leases.get(binding_ref)
        if lease is None:
            raise TaskError("provider_binding_unavailable", "read binding is released, expired or unavailable")
        if lease.context_key != context.key:
            raise TaskError("provider_binding_scope_mismatch", "read binding belongs to another caller or scope")
        entry = self._providers.get(self._key(lease.public.provider))
        try:
            if lease.public.expires_at <= self.tasks.now():
                raise TaskError("provider_binding_expired", "read binding lease has expired")
            if entry is None or entry[0].binding != lease.public.provider:
                raise TaskError("provider_binding_unavailable", "original provider generation is unavailable")
            owner, authority, scope = self._admit(context, *entry)
            if (owner, authority, scope) != (lease.public.owner_ref, lease.authority, lease.public.scope_json):
                raise TaskError("provider_binding_stale", "owner, policy or scope changed; bind again")
        except TaskError:
            self._leases.pop(binding_ref, None)
            raise
        return lease.public, entry[1]

    @outcome
    def invoke(self, context, binding_ref, request):
        bound, provider = self._lease(context, binding_ref)
        try:
            payload = _json(request)
            if len(payload.encode("utf-8")) > bound.limits.max_input_bytes:
                raise TaskError("provider_input_budget_exceeded", "request exceeds its bound input budget")
            # Isolate provider mutations from the caller and the post-call checks.
            original = json.loads(payload)
            expected = {"schema_version": bound.capability.input_schema,
                "capability_id": bound.provider.capability, "capability_version": bound.provider.version,
                "provider_id": bound.provider.provider, "provider_generation": bound.provider.generation}
            if type(original) is not dict or any(original.get(key) != value for key, value in expected.items()):
                raise TaskError("provider_request_binding_mismatch", "request differs from its selected provider binding")
            if _json(original.get("scope")) != bound.scope_json:
                raise TaskError("provider_binding_scope_mismatch", "request scope differs from the trusted binding")
            _token(original.get("request_id"))
            _token(original.get("trace_id"))
            if type(original.get("deadline_at")) is not str:
                raise ValueError("invalid deadline")
            deadline = normalize_utc(datetime.fromisoformat(original["deadline_at"].replace("Z", "+00:00").replace("z", "+00:00")),
                                     field="read deadline")
            if deadline > bound.expires_at:
                raise TaskError("provider_deadline_exceeds_lease", "request cannot outlive its read binding")
            if deadline <= self.tasks.now():
                raise TaskError("provider_deadline_expired", "read request deadline has expired")
            budget = original["budget"]
            if type(budget) is not dict:
                raise ValueError("invalid budget")
            if len(payload.encode("utf-8")) > budget.get("max_input_bytes", bound.limits.max_input_bytes):
                raise TaskError("provider_input_budget_exceeded", "request exceeds its negotiated input budget")
            for field, maximum in asdict(bound.limits).items():
                value = budget.get(field, maximum)
                if type(value) is not int or not 1 <= value <= maximum:
                    raise TaskError("provider_budget_exceeds_binding", "request budget exceeds its negotiated binding")
            features = original.get("required_features", [])
            if (type(features) is not list or len(features) > 32 or any(type(item) is not str for item in features)
                    or len(set(features)) != len(features)):
                raise ValueError("invalid features")
            if not set(features).issubset(bound.capability.features):
                raise TaskError("provider_feature_unavailable", "request requires an unsupported feature")
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
            if isinstance(error, TaskError):
                raise
            raise TaskError("provider_request_invalid", "read request is not a valid bounded envelope") from None
        try:
            result = provider.invoke(context, json.loads(payload))
        except Exception:
            raise TaskError("provider_invocation_failed", "read provider failed; private error details omitted") from None
        self._lease(context, binding_ref)
        if self.tasks.now() >= deadline:
            raise TaskError("provider_deadline_expired", "read result completed after its deadline")
        expected.update(schema_version=bound.capability.output_schema,
                        request_id=original["request_id"], trace_id=original["trace_id"])
        if (type(result) is not dict or any(result.get(key) != value for key, value in expected.items())
                or type(result.get("status")) is not str
                or result.get("status") not in {"succeeded", "partial", "rejected", "permission_denied",
                    "unavailable", "timeout", "uncertain", "failed", "cancelled"}
                    | ({"pending"} if bound.capability.supports_pending else set())):
            raise TaskError("provider_result_invalid", "read result does not match the original call")
        has_output = result["status"] in ("succeeded", "partial", "pending")
        if result["status"] == "pending" and (result.get("retryable") is not False or not result.get("reason_code")):
            raise TaskError("provider_result_invalid", "pending lookup results cannot invite retries")
        if (type(result.get("retryable")) is not bool or type(result.get("degraded")) is not bool
                or result["degraded"] != (result["status"] == "partial")
                or type(result.get("warnings")) is not list
                or any(type(warning) is not str for warning in result["warnings"])
                or (has_output and type(result.get("output")) is not dict)
                or (not has_output and result.get("output") is not None)):
            raise TaskError("provider_result_invalid", "read result has an inconsistent result envelope")
        try:
            if set(result) != set(expected) | {"status", "reason_code", "retryable", "degraded", "warnings", "output"}:
                raise ValueError("invalid result fields")
            if result["reason_code"] is not None:
                _token(result["reason_code"])
            result_json = _json(result)
            result_bytes = len(result_json.encode("utf-8"))
        except (TypeError, ValueError, RecursionError):
            raise TaskError("provider_result_invalid", "read result is not a JSON document") from None
        if result_bytes > budget.get("max_output_bytes", bound.limits.max_output_bytes):
            raise TaskError("provider_output_budget_exceeded", "read result exceeds its bound output budget")
        return json.loads(result_json)

    @outcome
    def release(self, context, binding_ref):
        lease = self._leases.get(binding_ref)
        if lease is None:
            return False
        if lease.context_key != context.key:
            raise TaskError("provider_binding_scope_mismatch", "only the original caller can release this binding")
        del self._leases[binding_ref]
        return True

    def close(self):
        self._closed = True
        self._leases.clear()
        self._providers.clear()

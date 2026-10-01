"""Persist host mappings and derive authority only from configured native routes."""

from dataclasses import asdict, replace
from datetime import datetime
import json
import logging

from companion_v2.execution.models import TaskContext, TaskError, digest, encode, require, stamp
from companion_v2.foundation.refs import AudienceRef, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier, GrantState
from companion_v2.identity_policy.personas import ConversationRoute, PersonaBinding, PersonaDirectory, SelectorKind
from companion_v2.identity_policy.repository import PersistentIdentityDirectory
from companion_v2.relationships.private_access import (DEFAULT_FOR_CAPABILITY, REVOCABLE_ABSENCE_CODES,
                                                        REVOCABLE_CAPABILITIES)
from .group_settings import GroupTarget


logger = logging.getLogger(__name__)


MANIFEST = "astrbot.multi.manifest.v1"
HOST_ID = "astrbot-native"
DELIVERY = "message.delivery"


class MultiAuthority:
    def __init__(self, runtime, settings, *, now):
        self.runtime, self.settings, self.now = runtime, settings, now
        self.identities, self.personas = PersistentIdentityDirectory(runtime), PersonaDirectory(runtime)
        # 私聊权限默认值的读取器；由会话在应用装配好之后挂上。没挂上时保持旧行为
        # （配置能力表里有的就签发），不让"没挂"变成"新用户全都没权限"。
        self.private_access = None
        from .group_authority import GroupAuthority
        self.groups = GroupAuthority(self)
        from .group_delivery import GroupDeliveryAuthority
        self.group_delivery = GroupDeliveryAuthority(self)

    def attach_private_access(self, settings):
        self.private_access = settings

    def _defaults(self, context):
        if self.private_access is None:
            return None
        try:
            return self.private_access.defaults(context)
        except Exception:  # noqa: BLE001 - 读不到默认值时退回"按能力表签发"，不阻断登录
            return None

    def read(self, key):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (key,))
        return json.loads(row["value"]) if row else None

    def write(self, key, value):
        with self.runtime.transaction() as connection:
            connection.execute("INSERT INTO runtime_metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, encode(value)))

    def require_manifest(self, current=None):
        manifest = self.read(MANIFEST)
        if manifest is None:
            raise TaskError("host_not_initialized", "initialize the shared installation first")
        if current is None:
            return manifest
        if isinstance(current, str):
            if manifest["fingerprint"] != current:
                raise TaskError("host_configuration_changed", "review and initialize the changed host configuration before startup")
            return manifest
        current_binding = current.get("binding_contract") if isinstance(current, dict) else None
        pinned_binding = manifest.get("binding_contract")
        if current_binding is not None and pinned_binding is not None:
            differences = self._binding_differences(pinned_binding, current_binding)
        elif isinstance(current_binding, dict):
            differences = self._legacy_binding_differences(manifest.get("identities"))
        else:
            differences = ("binding",)
        if differences:
            names = ", ".join(differences)
            raise TaskError("host_binding_changed", "the fixed run profile binding changed: " + names)
        if manifest.get("fingerprint") != current.get("fingerprint"):
            logger.warning("[CompanionV2] 固定共享运行档的模型或运行参数已变化，按当前参数继续连接")
        return manifest

    @staticmethod
    def _binding_differences(pinned, current):
        labels = {"accounts": "account", "private_targets": "private_target",
                  "group_targets": "group_target", "personas": "persona"}
        return tuple(label for field, label in labels.items() if pinned.get(field) != current.get(field))

    def _legacy_binding_differences(self, stored_identities):
        """Validate older manifests that pinned only the full configuration hash."""
        if not isinstance(stored_identities, dict):
            return ("binding",)
        expected = {}
        for target in self.settings.all_targets:
            expected["target:" + target.target_id] = asdict(target)
            expected["account:" + digest([target.platform_id, target.account_id])] = target.bot_id
        for persona in self.settings.personas:
            expected["persona:" + digest([persona.bot_id, persona.persona_id])] = persona.role_id
        for key in tuple(stored_identities):
            if key.startswith(("target:", "account:", "persona:")) and stored_identities.get(key) != expected.get(key):
                prefix = key.partition(":")[0]
                return ({"target": "private_target", "account": "account", "persona": "persona"}[prefix],)
        if any(key not in stored_identities or stored_identities[key] != value for key, value in expected.items()):
            return ("account", "private_target", "persona")
        return ()

    def principal(self, target, participant_id=None):
        return AuthenticatedHostPrincipal(self.runtime.installation_id, HOST_ID, target.platform_id,
            participant_id if participant_id is not None else target.participant_id, target.bot_id, target.account_id)

    def actor(self, target, participant_id=None):
        actor = require(self.identities.resolve_authenticated(self.principal(target, participant_id), observed_at=self.now()))
        if (actor.subject != self.subject(target, participant_id)
                or actor.binding_id != self.identity_id(target, participant_id) or actor.binding_revision != 1):
            raise TaskError("host_identity_changed", "the configured participant identity changed")
        return actor

    def subject(self, target, participant_id=None):
        participant = participant_id if participant_id is not None else target.participant_id
        return SubjectRef(self.runtime.installation_id, SubjectKind.HUMAN, "onebot-user:" + participant)

    def identity_id(self, target, participant_id=None):
        return "host-multi-person:" + digest(self.principal(target, participant_id))

    def ensure_actor(self, target, participant_id=None):
        identifier = self.identity_id(target, participant_id)
        if self.runtime.read_one("SELECT 1 FROM identity_bindings WHERE binding_id = ?", (identifier,)) is None:
            self.identities.bind(binding_id=identifier, principal=self.principal(target, participant_id),
                subject=self.subject(target, participant_id), valid_from=datetime.fromisoformat(self.require_manifest()["valid_from"]),
                expected_revision=self.identities.revision)
        return self.actor(target, participant_id)

    def initialize(self, manifest):
        with self.runtime.transaction():
            old = self.read(MANIFEST)
            if old is None:
                if self.runtime.read_one("SELECT 1 FROM identity_bindings LIMIT 1", ()):
                    raise TaskError("host_store_in_use", "shared host initialization requires its own installation")
                old = {"identities": {}, "valid_from": stamp(self.now())}
            else:
                self.require_manifest(manifest)
            identities = dict(old["identities"])
            mappings = {}
            for target in self.settings.all_targets:
                mappings["target:" + target.target_id] = asdict(target)
                mappings["account:" + digest([target.platform_id, target.account_id])] = target.bot_id
            for persona in self.settings.personas:
                mappings["persona:" + digest([persona.bot_id, persona.persona_id])] = persona.role_id
            for key, value in mappings.items():
                if key in identities and identities[key] != value:
                    raise TaskError("host_identity_conflict", "an existing native identity cannot silently move to a different owner")
                identities[key] = value
            at = datetime.fromisoformat(old["valid_from"])
            for target in self.settings.targets:
                identifier = self.identity_id(target)
                row = self.runtime.read_one("SELECT 1 FROM identity_bindings WHERE binding_id = ?", (identifier,))
                if row is None:
                    self.identities.bind(binding_id=identifier, principal=self.principal(target), subject=self.subject(target),
                        valid_from=at, expected_revision=self.identities.revision)
                self.actor(target)
            replayed = old.get("fingerprint") == manifest["fingerprint"]
            self.write(MANIFEST, {**manifest, "identities": identities, "valid_from": old["valid_from"]})
            return {"initialized": True, "replayed": replayed, "installation_id": self.runtime.installation_id}

    @staticmethod
    def binding_id(scope):
        return "host-multi-role:" + scope.key

    @staticmethod
    def grant_id(scope, capability):
        return "host-multi-grant:" + digest([scope.key, capability])

    @staticmethod
    def context_key(target, role_id):
        return "host.multi.context:" + digest([target.target_id, role_id])

    def _scope(self, target, scope, role):
        if (scope.installation_id != self.runtime.installation_id or scope.kind.value != "private"
                or (scope.platform, scope.account_id, scope.bot_id, scope.native_scope_id, scope.session_id)
                != (target.platform_id, target.account_id, target.bot_id, target.participant_id, target.participant_id)
                or role.installation_id != self.runtime.installation_id
                or not any(p.bot_id == target.bot_id and p.role_id == role.subject_id for p in self.settings.personas)):
            raise TaskError("host_target_mismatch", "scope and role must come from this configured private target")

    def provision_scope(self, target, scope, role):
        self._scope(target, scope, role)
        actor = self.actor(target)
        at = datetime.fromisoformat(self.require_manifest()["valid_from"])
        with self.runtime.transaction():
            route = self.personas.register_route(ConversationRoute(scope, user=actor.subject), observed_at=self.now())
            identifier = self.binding_id(scope)
            if self.personas.binding(identifier) is None:
                selector = next(s for s, _ in route.selectors() if s.kind is SelectorKind.SESSION)
                self.personas.set_binding(PersonaBinding(identifier, selector, role, 0, at,
                    "astrbot-multi-host", "configured-private-target"), expected_revision=0, observed_at=self.now())
            resolution = require(self.personas.resolve(scope, observed_at=self.now()))
            if resolution.selected.binding_id != identifier or resolution.binding.role != role:
                raise TaskError("host_persona_binding_changed", "the configured private role binding changed")
            # 私聊权限的默认值：决定"新用户一开始有没有这两项权限"。
            # 默认关的能力**不签发**——没有授权就是没有权限，页面也会如实显示"未授权"；
            # 默认开的能力即使不在配置能力表里也签发（表管的是宿主能力，不是这两项按人权限）。
            pending = self._defaults(TaskContext(actor, resolution.binding, AudienceRef(scope, (actor.subject,))))
            for capability in self.settings.capabilities:
                identifier = self.grant_id(scope, capability)
                if capability in DEFAULT_FOR_CAPABILITY and pending is not None \
                        and not pending[DEFAULT_FOR_CAPABILITY[capability]]:
                    continue
                if self.runtime.read_one("SELECT 1 FROM identity_grants WHERE grant_id = ?", (identifier,)) is None:
                    self.identities.issue_grant(grant_id=identifier, subject=actor.subject, scope=scope, capability=capability,
                        tier=AuthorizationTier.STANDARD, valid_from=at, expected_revision=self.identities.revision)
                # A persisted revoke/expiry is not undone by an input or restart.
                access = self.identities.authorize(actor, scope=scope, capability=capability, observed_at=self.now())
                if capability in REVOCABLE_CAPABILITIES and access.failure is not None \
                        and access.failure.code in REVOCABLE_ABSENCE_CODES:
                    # 对话/主动权限是操作员按人收的：收回就是决定，不是宿主坏了。
                    # 这里放行，让收信闸把它变成"按配置回一句"；另一张 grant 顶替仍要报错。
                    continue
                current = require(access)
                if current.grant_id != identifier:
                    raise TaskError("host_grant_changed", "the original host grant is no longer current")
            if pending is not None:
                # 默认开、却不在能力表里的那几项（通常就是 proactive.contact）
                for capability, key in sorted(DEFAULT_FOR_CAPABILITY.items()):
                    if capability in self.settings.capabilities or not pending[key]:
                        continue
                    if self.runtime.read_one("SELECT 1 FROM identity_grants WHERE grant_id = ?",
                                             (self.grant_id(scope, capability),)) is None:
                        self.identities.issue_grant(grant_id=self.grant_id(scope, capability), subject=actor.subject,
                            scope=scope, capability=capability, tier=AuthorizationTier.STANDARD, valid_from=at,
                            expected_revision=self.identities.revision)
            self.write(self.context_key(target, role.subject_id), scope.document())
            return TaskContext(actor, resolution.binding, AudienceRef(scope, (actor.subject,)))

    def select(self, target, scope, role):
        with self.runtime.transaction():
            self.provision_scope(target, scope, role)
            key = "host.multi.active:" + target.target_id
            old = self.read(key)
            if old and old != scope.document():
                previous = ScopeRef.restore(old)
                binding = self.personas.binding(self.binding_id(previous))
                if binding is not None:
                    # Keep original source scopes assigned to their original role,
                    # while fencing all in-flight work from the departed context.
                    self.personas.set_binding(replace(binding, revision=binding.revision + 1),
                        expected_revision=binding.revision, observed_at=self.now())
            self.write(key, scope.document())
            return self.context(target.target_id, role.subject_id)

    def context(self, target_id, role_id):
        target = self.settings.target(target_id)
        if isinstance(target, GroupTarget):
            raise TaskError("host_group_context_requires_event", "a group context requires its actual authenticated speaker")
        stored = self.read(self.context_key(target, role_id))
        if stored is None:
            raise TaskError("host_context_unavailable", "the private persona has no resolved host conversation yet")
        scope = ScopeRef.restore(stored)
        role = SubjectRef(scope.installation_id, SubjectKind.BOT, role_id)
        self._scope(target, scope, role)
        actor = self.actor(target)
        binding = require(self.personas.resolve(scope, observed_at=self.now())).binding
        if binding.role != role:
            raise TaskError("host_persona_binding_changed", "the private persona binding changed")
        return TaskContext(actor, binding, AudienceRef(scope, (actor.subject,)))

    def authorize_delivery(self, target_id, expires_at):
        """正式版：不再需要投递授权，这里只回报"无需授权"。"""
        target = self.settings.target(target_id)
        if isinstance(target, GroupTarget):
            raise TaskError("host_group_authorization_required", "use the independent group delivery authorization")
        return {"target_id": target_id, "authorized": True, "expires_at": None, "required": False}

    def revoke_delivery(self, target_id):
        if isinstance(self.settings.target(target_id), GroupTarget):
            raise TaskError("host_group_authorization_required", "use the independent group delivery revocation")
        return {"target_id": target_id, "authorized": True, "required": False}

    def delivery_access(self, target):
        """正式版：私聊投递不再需要授权。仍校验目标本身（配置里认得的那个私聊对象）。"""
        if isinstance(target, GroupTarget):
            raise TaskError("host_group_authorization_required", "private delivery authorization cannot authorize a group")
        self.actor(target)
        return {"target_id": target.target_id, "authorized": True, "required": False}

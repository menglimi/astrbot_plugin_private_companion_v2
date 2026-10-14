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
from companion_v2.identity_policy.grants import PERSON_PERMISSION_GRANT_PREFIX
from companion_v2.relationships.private_access import (DEFAULT_FOR_CAPABILITY, REVOCABLE_ABSENCE_CODES,
                                                        REVOCABLE_CAPABILITIES)
from companion_v2.storage.codec import scope_values
from .group_settings import GroupTarget


logger = logging.getLogger(__name__)


MANIFEST = "astrbot.multi.manifest.v1"
VERIFIED_RUNTIME = "astrbot.multi.verified_runtime.v1"
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
            # Runtime parameters may change without moving an identity. Keep
            # the reviewed binding immutable, and acknowledge the verified
            # parameters separately so load/start and later restarts stay quiet.
            with self.runtime.transaction():
                accepted = self.read(VERIFIED_RUNTIME)
                if not accepted or accepted.get("fingerprint") != current.get("fingerprint"):
                    self.write(VERIFIED_RUNTIME, {"fingerprint": current.get("fingerprint"),
                               "verified_at": stamp(self.now())})
                    logger.info("[CompanionV2] 已采用更新的模型与运行参数，账号和角色绑定核验通过")
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
        if actor.subject != self.subject(target, participant_id):
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

    def _legacy_staging_receipt_matches(self):
        receipt = self.runtime.read_one(
            """SELECT owner, installation_id, platform, scope_kind, native_scope_id, bot_id, account_id, state
               FROM operations WHERE operation_id = ?""", ("astrbot-staging-bootstrap",))
        if (receipt is None or receipt["owner"] != "host.staging.bootstrap"
                or receipt["installation_id"] != self.runtime.installation_id
                or receipt["scope_kind"] != "private" or receipt["state"] != "completed"):
            return False
        return any((target.platform_id, target.participant_id, target.bot_id, target.account_id)
                   == (receipt["platform"], receipt["native_scope_id"], receipt["bot_id"], receipt["account_id"])
                   for target in self.settings.targets)

    def initialize(self, manifest, *, reviewed=False, allow_legacy_staging=False):
        with self.runtime.transaction():
            old = self.read(MANIFEST)
            if old is None:
                occupied = self.runtime.read_one("SELECT 1 FROM identity_bindings LIMIT 1", ()) is not None
                if occupied and not (allow_legacy_staging and self._legacy_staging_receipt_matches()):
                    raise TaskError("host_store_in_use", "shared host initialization requires its own installation")
                old = {"identities": {}, "valid_from": stamp(self.now())}
            elif not reviewed:
                self.require_manifest(manifest)
            identities = dict(old["identities"])
            mappings = {}
            for target in self.settings.all_targets:
                mappings["target:" + target.target_id] = asdict(target)
                mappings["account:" + digest([target.platform_id, target.account_id])] = target.bot_id
            for persona in self.settings.personas:
                mappings["persona:" + digest([persona.bot_id, persona.persona_id])] = persona.role_id
            for key, value in mappings.items():
                if key in identities and identities[key] != value and not (reviewed and key.startswith("persona:")):
                    raise TaskError("host_identity_conflict", "an existing native identity cannot silently move to a different owner")
                # A Dashboard-reviewed edit may regroup personas into a role.
                # Historical role scopes remain immutable; subsequent native
                # sessions receive a new scope containing the selected role ID.
                identities[key] = value
            at = datetime.fromisoformat(old["valid_from"])
            for target in self.settings.targets:
                if target.participant_id == "*":
                    continue
                principal = self.principal(target)
                existing = self.identities.resolve_authenticated(principal, observed_at=at)
                if existing.failure is None:
                    if existing.unwrap().subject != self.subject(target):
                        raise TaskError("host_identity_changed", "the configured participant identity changed")
                elif existing.failure.code == "unbound_identity":
                    self.identities.bind(binding_id=self.identity_id(target), principal=principal,
                        subject=self.subject(target), valid_from=at, expected_revision=self.identities.revision)
                else:
                    require(existing)
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

    def remember_target(self, target):
        from dataclasses import asdict
        self.write("host.multi.target:" + target.target_id,
                   {"kind": "group" if isinstance(target, GroupTarget) else "private", "value": asdict(target)})

    def target(self, target_id):
        try:
            return self.settings.target(target_id)
        except Exception:
            saved = self.read("host.multi.target:" + target_id)
            if not isinstance(saved, dict) or not isinstance(saved.get("value"), dict):
                raise
            if saved.get("kind") == "group":
                return GroupTarget(**saved["value"])
            if saved.get("kind") == "private":
                from .multi_settings import PrivateTarget
                return PrivateTarget(**saved["value"])
            raise TaskError("host_target_unavailable", "the native conversation route is unavailable")

    def _scope(self, target, scope, role):
        if (scope.installation_id != self.runtime.installation_id or scope.kind.value != "private"
                or (scope.platform, scope.account_id, scope.bot_id, scope.native_scope_id, scope.session_id)
                != (target.platform_id, target.account_id, target.bot_id, target.participant_id, target.participant_id)
                or role.installation_id != self.runtime.installation_id
                or not any(p.bot_id == target.bot_id and p.role_id == role.subject_id for p in self.settings.personas)):
            raise TaskError("host_target_mismatch", "scope and role must come from this configured private target")

    def provision_scope(self, target, scope, role):
        self._scope(target, scope, role)
        self.remember_target(target)
        actor = self.ensure_actor(target)
        at = datetime.fromisoformat(self.require_manifest()["valid_from"])
        with self.runtime.transaction():
            exact = self.runtime.read_one(
                """SELECT role_id, revision FROM role_bindings WHERE installation_id = ? AND platform = ?
                   AND scope_kind = ? AND native_scope_id = ? AND bot_id = ? AND account_id = ?
                   AND conversation_id = ? AND session_id = ?""", scope_values(scope))
            route = self.personas.register_route(ConversationRoute(scope, user=actor.subject), observed_at=self.now(),
                adopt_exact_revision=exact["revision"] if exact is not None else None)
            identifier = self.binding_id(scope)
            if self.personas.binding(identifier) is None:
                existing = self.personas.resolve(scope, observed_at=self.now())
                if existing.failure is None:
                    if existing.unwrap().binding.role != role:
                        raise TaskError("host_persona_binding_changed", "the configured private role binding changed")
                elif existing.failure.code == "role_binding_missing":
                    selector = next(s for s, _ in route.selectors() if s.kind is SelectorKind.SESSION)
                    self.personas.set_binding(PersonaBinding(identifier, selector, role, 0, at,
                        "astrbot-multi-host", "configured-private-target"), expected_revision=0, observed_at=self.now())
                else:
                    require(existing)
            resolution = require(self.personas.resolve(scope, observed_at=self.now()))
            if resolution.binding.role != role:
                raise TaskError("host_persona_binding_changed", "the configured private role binding changed")
            # 私聊权限的默认值：决定"新用户一开始有没有这两项权限"。
            # 默认关的能力**不签发**——没有授权就是没有权限，页面也会如实显示"未授权"；
            # 默认开的能力即使不在配置能力表里也签发（表管的是宿主能力，不是这两项按人权限）。
            pending = self._defaults(TaskContext(actor, resolution.binding, AudienceRef(scope, (actor.subject,))))
            decided = {grant.capability for grant in self.identities.grants_for_subject(actor.subject)
                       if grant.subject == actor.subject and grant.scope == scope
                       and grant.grant_id.startswith(PERSON_PERMISSION_GRANT_PREFIX)}
            for capability in self.settings.capabilities:
                identifier = self.grant_id(scope, capability)
                if capability in DEFAULT_FOR_CAPABILITY and pending is not None \
                        and not pending[DEFAULT_FOR_CAPABILITY[capability]]:
                    continue
                if capability not in decided and self.runtime.read_one(
                        "SELECT 1 FROM identity_grants WHERE grant_id = ?", (identifier,)) is None:
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
                if capability in REVOCABLE_CAPABILITIES:
                    continue
                if current.grant_id != identifier:
                    raise TaskError("host_grant_changed", "the original host grant is no longer current")
            if pending is not None:
                # 默认开、却不在能力表里的那几项（通常就是 proactive.contact）
                for capability, key in sorted(DEFAULT_FOR_CAPABILITY.items()):
                    if capability in self.settings.capabilities or not pending[key] or capability in decided:
                        continue
                    if self.runtime.read_one("SELECT 1 FROM identity_grants WHERE grant_id = ?",
                                             (self.grant_id(scope, capability),)) is None:
                        self.identities.issue_grant(grant_id=self.grant_id(scope, capability), subject=actor.subject,
                            scope=scope, capability=capability, tier=AuthorizationTier.STANDARD, valid_from=at,
                            expected_revision=self.identities.revision)
            self.write(self.context_key(target, role.subject_id), scope.document())
            template = self.settings.template_for(target)
            if template is not None and template.target_id != target.target_id:
                self.write(self.context_key(template, role.subject_id), scope.document())
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
        target = self.target(target_id)
        if isinstance(target, GroupTarget):
            raise TaskError("host_group_context_requires_event", "a group context requires its actual authenticated speaker")
        stored = self.read(self.context_key(target, role_id))
        if stored is None:
            # Wildcard private targets are materialized per native participant.
            # Their context is therefore keyed by the materialized target ID,
            # while callers may still hold the account-level template.  Resolve
            # the existing runtime records through StorageRuntime and match the
            # stable route plus the role binding instead of inventing a second
            # persistence path.
            prefix = "host.multi.context:"
            for row in self.runtime.read_all(
                    "SELECT value FROM runtime_metadata WHERE substr(key, 1, ?) = ?",
                    (len(prefix), prefix)):
                try:
                    candidate = json.loads(row["value"])
                    scope = ScopeRef.restore(candidate)
                except (TypeError, ValueError, KeyError):
                    continue
                if (scope.kind.value != "private"
                        or scope.platform != target.platform_id
                        or scope.account_id != target.account_id
                        or scope.bot_id != target.bot_id
                        or (target.participant_id != "*"
                            and scope.native_scope_id != target.participant_id)):
                    continue
                resolution = self.personas.resolve(scope, observed_at=self.now())
                if resolution.failure is None and resolution.unwrap().binding.role.subject_id == role_id:
                    stored = candidate
                    break
        if stored is None:
            raise TaskError("host_context_unavailable", "the private persona has no resolved host conversation yet")
        scope = ScopeRef.restore(stored)
        role = SubjectRef(scope.installation_id, SubjectKind.BOT, role_id)
        resolved_target = self.settings.private_target(scope.platform, scope.account_id, scope.native_scope_id)
        # A wildcard target is materialized for each native private route.  The
        # materialized target is intentionally different from its template, but
        # it still belongs to the same account/persona mapping.  Comparing the
        # two objects directly made every dynamic private context unusable after
        # the first message.
        template = self.settings.template_for(resolved_target) if resolved_target is not None else None
        same_route_family = (template is not None and template.platform_id == target.platform_id
                             and template.account_id == target.account_id
                             and template.bot_id == target.bot_id)
        exact_route = resolved_target is not None and resolved_target.target_id == target.target_id
        if (resolved_target is None or resolved_target.bot_id != target.bot_id
                or (not exact_route and not same_route_family)):
            raise TaskError("host_context_unavailable", "the private conversation no longer belongs to this account mapping")
        self._scope(resolved_target, scope, role)
        actor = self.actor(resolved_target, scope.native_scope_id)
        binding = require(self.personas.resolve(scope, observed_at=self.now())).binding
        if binding.role != role:
            raise TaskError("host_persona_binding_changed", "the private persona binding changed")
        return TaskContext(actor, binding, AudienceRef(scope, (actor.subject,)))

    def authorize_delivery(self, target_id, expires_at):
        """正式版：不再需要投递授权，这里只回报"无需授权"。"""
        target = self.target(target_id)
        if isinstance(target, GroupTarget):
            raise TaskError("host_group_authorization_required", "use the independent group delivery authorization")
        return {"target_id": target_id, "authorized": True, "expires_at": None, "required": False}

    def revoke_delivery(self, target_id):
        if isinstance(self.target(target_id), GroupTarget):
            raise TaskError("host_group_authorization_required", "use the independent group delivery revocation")
        return {"target_id": target_id, "authorized": True, "required": False}

    def delivery_access(self, target):
        """正式版：私聊投递不再需要授权。仍校验目标本身（配置里认得的那个私聊对象）。"""
        if isinstance(target, GroupTarget):
            raise TaskError("host_group_authorization_required", "private delivery authorization cannot authorize a group")
        self.actor(target)
        return {"target_id": target.target_id, "authorized": True, "required": False}

"""Explicit account, participant and persona mappings for one shared installation."""

from dataclasses import asdict, dataclass, field

from companion_v2.adapters.astrbot.native import HostAccount, account_number
from companion_v2.adapters.astrbot.staging_config import ALLOWED_CAPABILITIES, REQUIRED_CAPABILITIES
from companion_v2.execution.models import digest
from companion_v2.conversation.forwards.models import ForwardIntakePolicy
from companion_v2.conversation.segmentation import SegmentationPolicy
from .settings import HostControlError, HostSettings, PROFILE_PATTERN, _boolean, _section, _text
from .group_settings import GroupTarget, parse_group_targets


@dataclass(frozen=True)
class PrivateTarget:
    target_id: str
    platform_id: str
    account_id: str
    bot_id: str
    participant_id: str

    @property
    def route_key(self):
        return self.platform_id, self.account_id, self.participant_id


@dataclass(frozen=True)
class PersonaMapping:
    bot_id: str
    persona_id: str
    role_id: str


@dataclass(frozen=True)
class MultiHostSettings:
    enabled: bool
    installation_key: str
    targets: tuple[PrivateTarget, ...]
    personas: tuple[PersonaMapping, ...]
    account_bindings: tuple[HostAccount, ...]
    capabilities: tuple[str, ...]
    common: HostSettings
    group_targets: tuple[GroupTarget, ...] = ()
    group_delivery_mode: str = "onebot_group"
    _legacy_group_delivery_shape: bool = field(default=False, compare=False, repr=False)
    _storage_installation_id: str | None = field(default=None, compare=False, repr=False)

    @property
    def all_targets(self):
        return self.targets + self.group_targets

    @property
    def installation_id(self):
        return self._storage_installation_id or "astrbot-private-companion-v2:multi:" + self.installation_key

    @property
    def profile_id(self):
        return self.installation_key

    @property
    def accounts(self):
        return self.account_bindings

    @property
    def fingerprint(self):
        data = asdict(self)
        if not self.common.streaming:
            data["common"].pop("streaming")
        if self.common.segmentation == SegmentationPolicy():
            data["common"].pop("segmentation")
        if self.common.forward_intake == ForwardIntakePolicy():
            data["common"].pop("forward_intake")
        elif self.common.forward_intake.parse_nested:
            # The default predates this field. Preserve custom intake fingerprints
            # written before the switch existed; an explicit False is serialized.
            data["common"]["forward_intake"].pop("parse_nested")
        if not self.common.budget_soft.enabled:
            data["common"].pop("budget_soft")  # A disabled daily soft ceiling is not an identity pin.
        data["common"].pop("voice_reply_enabled")  # Delivery presentation can change without re-pinning identity.
        data["common"].pop("voice_reply_policy")
        # Routing is adopted at assembly/request boundaries, not an identity pin.
        for field in ("additional_providers", "fallback_provider_id", "replacement_rules", "fallback_on_refusal"):
            data["common"].pop(field)
        if not self.group_targets:
            data.pop("group_targets")  # Preserve already initialized private-only installations.
        data.pop("_legacy_group_delivery_shape")
        data.pop("_storage_installation_id")
        if self._legacy_group_delivery_shape:
            data.pop("group_delivery_mode")  # Reproduce manifests pinned before group delivery was fixed.
        return digest(data)

    @property
    def binding_contract(self):
        """Stable routing identity, separate from model and runtime settings."""
        return {
            "accounts": sorted(
                ({"platform_id": item.platform_id, "account_id": item.self_id, "bot_id": item.bot_id}
                 for item in self.accounts),
                key=lambda item: (item["platform_id"], item["account_id"], item["bot_id"])),
            "private_targets": sorted(
                (asdict(item) for item in self.targets),
                key=lambda item: item["target_id"]),
            "group_targets": sorted(
                (asdict(item) for item in self.group_targets),
                key=lambda item: item["target_id"]),
            "personas": sorted(
                (asdict(item) for item in self.personas),
                key=lambda item: (item["bot_id"], item["persona_id"])),
        }

    def delivery_mode_for(self, target):
        return "onebot_group" if isinstance(target, GroupTarget) else "onebot_private"

    @classmethod
    def parse(cls, config):
        section = _section(config, "multi_host")
        enabled = _boolean(section.get("enabled", False))
        key = _text(section.get("installation_id", "main"), required=True)
        if not PROFILE_PATTERN.fullmatch(key):
            raise HostControlError("host_installation_invalid", "installation ID must be a stable lowercase identifier")
        base = {"model": _section(config, "model"), "runtime": _section(config, "runtime"),
                "segmentation": _section(config, "segmentation"),
                "voice_reply": _section(config, "voice_reply"),
                "staging": {"enabled": enabled, "profile_id": "multi-" + key,
                            "delivery_mode": section.get("delivery_mode", "onebot_private")}}
        # The shared model/runtime profile contains no per-target identity.
        base["staging"]["profile_id"] = key if key != "preview-1" else "multi-preview"
        common = HostSettings.parse(base)
        targets, personas = [], []
        fields = ("target_id", "platform_id", "account_id", "bot_id", "participant_id")
        for name, names, kind, result in (("targets", fields, PrivateTarget, targets),
                ("personas", ("bot_id", "persona_id", "role_id"), PersonaMapping, personas)):
            values = section.get(name, [])
            if type(values) is not list:
                raise HostControlError("host_mappings_invalid", "host mappings must be lists")
            for value in values:
                if type(value) is not dict or set(value) - set(names) - {"__template_key"} or set(names) - set(value):
                    raise HostControlError("host_mappings_invalid", "host mapping fields are incomplete or unknown")
                result.append(kind(**{field: _text(value[field], required=True) for field in names}))
        groups = parse_group_targets(section.get("group_targets", []))
        raw_accounts = section.get("accounts")
        if raw_accounts is not None and type(raw_accounts) is not list:
            raise HostControlError("host_mappings_invalid", "Bot accounts must be a list")
        account_by_route = {}
        legacy_group_delivery_shape = "group_delivery_mode" not in section
        raw_group_mode = ("onebot_group" if legacy_group_delivery_shape
                          else _text(section.get("group_delivery_mode"), required=True))
        if raw_group_mode not in ("preview", "onebot_group"):
            raise HostControlError("host_group_delivery_invalid", "group delivery must be preview or onebot_group")
        try:
            for row in raw_accounts or ():
                if type(row) is not dict or set(row) != {"platform_id", "account_id", "bot_id"}:
                    raise ValueError()
                account = HostAccount(_text(row["platform_id"], required=True),
                    account_number(_text(row["account_id"], required=True)),
                    _text(row["bot_id"], required=True))
                route = account.platform_id, account.self_id
                if route in account_by_route:
                    raise ValueError()
                account_by_route[route] = account
            for target in (*targets, *groups):
                account = HostAccount(target.platform_id, account_number(target.account_id), target.bot_id)
                route = account.platform_id, account.self_id
                previous = account_by_route.setdefault(route, account)
                if previous != account:
                    raise ValueError()
        except ValueError:
            raise HostControlError("host_mappings_conflict", "registered Bot accounts must be unique and match legacy windows") from None
        account_bindings = tuple(sorted(account_by_route.values(), key=lambda a: (a.platform_id, a.self_id)))
        if not account_bindings or not personas:
            raise HostControlError("host_mappings_required", "register at least one Bot account and persona")
        accounts = {(item.platform_id, item.self_id): item.bot_id for item in account_bindings}
        routes, ids, roles = set(), set(), {}
        try:
            for target in targets:
                HostAccount(target.platform_id, account_number(target.account_id), target.bot_id)
                if target.participant_id != "*":
                    account_number(target.participant_id)
                if not PROFILE_PATTERN.fullmatch(target.target_id) or target.target_id in ids or target.route_key in routes:
                    raise ValueError()
                ids.add(target.target_id)
                routes.add(target.route_key)
                account = target.platform_id, target.account_id
                if accounts.setdefault(account, target.bot_id) != target.bot_id:
                    raise ValueError()
            for target in groups:
                if target.target_id in ids:
                    raise ValueError()
                ids.add(target.target_id)
                account = target.platform_id, target.account_id
                if accounts.setdefault(account, target.bot_id) != target.bot_id:
                    raise ValueError()
            for persona in personas:
                mapping = persona.bot_id, persona.persona_id
                if mapping in roles or persona.bot_id not in accounts.values():
                    raise ValueError()
                roles[mapping] = persona.role_id
            if not {p.bot_id for p in personas}.issubset(set(accounts.values())):
                raise ValueError()
        except ValueError:
            raise HostControlError("host_mappings_conflict", "accounts, target routes and native persona mappings must be unambiguous") from None
        capabilities = section.get("capabilities", [*sorted(REQUIRED_CAPABILITIES), "memory.read", "memory.propose",
                                                    "memory.reflect", "memory.subscribe"])
        if (type(capabilities) is not list or any(type(item) is not str for item in capabilities)
                or len(set(capabilities)) != len(capabilities)
                or not REQUIRED_CAPABILITIES.issubset(capabilities) or not set(capabilities).issubset(ALLOWED_CAPABILITIES)):
            raise HostControlError("host_capabilities_invalid", "configure registered non-core capabilities including reply prerequisites")
        return cls(enabled, key, tuple(sorted(targets, key=lambda t: t.target_id)),
                   tuple(sorted(personas, key=lambda p: (p.bot_id, p.persona_id))), account_bindings, tuple(sorted(capabilities)),
                   common, groups, "onebot_group", legacy_group_delivery_shape or raw_group_mode == "preview")

    def require_ready(self):
        if not self.enabled:
            raise HostControlError("host_disabled", "enable the shared host before initialization or startup")
        if not self.common.provider_id:
            raise HostControlError("host_provider_required", "select the shared model provider")

    def target(self, target_id):
        found = next((item for item in self.all_targets if item.target_id == target_id), None)
        if found is None:
            raise HostControlError("host_target_unavailable", "the conversation target is not configured")
        return found

    def private_target(self, platform_id, account_id, participant_id):
        exact = next((item for item in self.targets if item.route_key ==
                      (platform_id, account_id, participant_id)), None)
        if exact is not None:
            return exact
        template = next((item for item in self.targets if item.route_key ==
                         (platform_id, account_id, "*")), None)
        if template is None:
            return None
        account = next((item for item in self.accounts if
                        (item.platform_id, item.self_id) == (platform_id, account_id)), None)
        if account is None or account.bot_id != template.bot_id:
            return None
        identifier = "private-" + digest([platform_id, account_id, participant_id])[:24]
        return PrivateTarget(identifier, platform_id, account_id, template.bot_id, participant_id)

    def group_target(self, platform_id, account_id, group_id):
        exact = next((item for item in self.group_targets if item.route_key ==
                      (platform_id, account_id, group_id)), None)
        if exact is not None:
            return exact
        template = next((item for item in self.group_targets if item.route_key ==
                         (platform_id, account_id, "*")), None)
        if template is None:
            return None
        account = next((item for item in self.accounts if
                        (item.platform_id, item.self_id) == (platform_id, account_id)), None)
        if account is None or account.bot_id != template.bot_id:
            return None
        identifier = "group-" + digest([platform_id, account_id, group_id])[:24]
        return GroupTarget(identifier, platform_id, account_id, template.bot_id, group_id)

    def template_for(self, target):
        rows = self.group_targets if isinstance(target, GroupTarget) else self.targets
        peer = target.group_id if isinstance(target, GroupTarget) else target.participant_id
        field = "group_id" if isinstance(target, GroupTarget) else "participant_id"
        account_rows = (item for item in rows if item.platform_id == target.platform_id
                        and item.account_id == target.account_id and item.bot_id == target.bot_id)
        exact = next((item for item in account_rows if getattr(item, field) == peer), None)
        if exact is not None:
            return exact
        return next((item for item in rows if getattr(item, field) == "*"
                     and item.platform_id == target.platform_id and item.account_id == target.account_id
                     and item.bot_id == target.bot_id), None)

"""Explicit group targets; a group is never a private participant."""

from dataclasses import dataclass

from companion_v2.adapters.astrbot.native import HostAccount, account_number
from .settings import HostControlError, PROFILE_PATTERN, _text


@dataclass(frozen=True)
class GroupTarget:
    target_id: str
    platform_id: str
    account_id: str
    bot_id: str
    group_id: str

    @property
    def route_key(self):
        return self.platform_id, self.account_id, self.group_id


def parse_group_targets(values):
    fields = ("target_id", "platform_id", "account_id", "bot_id", "group_id")
    if type(values) is not list:
        raise HostControlError("host_mappings_invalid", "group targets must be a list")
    targets, routes = [], set()
    for value in values:
        if type(value) is not dict or set(value) - set(fields) - {"__template_key"} or set(fields) - set(value):
            raise HostControlError("host_mappings_invalid", "group target fields are incomplete or unknown")
        target = GroupTarget(**{field: _text(value[field], required=True) for field in fields})
        try:
            HostAccount(target.platform_id, target.account_id, target.bot_id)
            if target.group_id != "*":
                account_number(target.group_id)
            if not PROFILE_PATTERN.fullmatch(target.target_id) or target.route_key in routes:
                raise ValueError()
        except ValueError:
            raise HostControlError("host_mappings_conflict", "group routes must be canonical and unique") from None
        routes.add(target.route_key)
        targets.append(target)
    return tuple(sorted(targets, key=lambda t: t.target_id))

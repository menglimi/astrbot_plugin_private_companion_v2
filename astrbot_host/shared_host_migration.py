"""Upgrade legacy single-target plugin settings to the shared host contract."""

from __future__ import annotations

from copy import deepcopy

from companion_v2.execution.models import digest
from .identity_derivation import LEGACY_BOT_ID, LEGACY_ROLE_ID


def migrate_single_target_config(config: object) -> tuple[dict, bool]:
    if not isinstance(config, dict):
        return {}, False
    candidate = deepcopy(dict(config))
    legacy = candidate.get("staging", {})
    old_target = candidate.get("target", {})
    shared = candidate.setdefault("multi_host", {})
    if type(legacy) is not dict or type(old_target) is not dict or type(shared) is not dict:
        return candidate, False

    changed = False
    was_enabled = legacy.get("enabled") is True
    targets = shared.setdefault("targets", [])
    personas = shared.setdefault("personas", [])
    if type(targets) is not list or type(personas) is not list:
        return candidate, False
    groups = shared.setdefault("group_targets", [])
    if type(groups) is not list:
        return candidate, False

    platform_id = str(old_target.get("platform_id", "default") or "default").strip()
    account_id = str(old_target.get("account_id", "") or "").strip()
    participant_id = str(old_target.get("participant_id", "") or "").strip()
    # Once the shared mappings exist, the disabled single-target section is
    # compatibility metadata. Re-importing it on every reload overwrites the
    # operator's reviewed directory and makes the saved manifest conflict.
    import_old_target = was_enabled or not (targets or groups or personas or shared.get("accounts"))
    if import_old_target and platform_id and account_id.isdecimal() and participant_id.isdecimal():
        registered_accounts = shared.get("accounts", [])
        if type(registered_accounts) is not list:
            return candidate, False
        account_rows = [row for row in [*registered_accounts, *targets, *groups] if type(row) is dict
                        and row.get("platform_id") == platform_id and row.get("account_id") == account_id]
        mapped_bot_id = next((str(row.get("bot_id", "")).strip() for row in account_rows
                              if str(row.get("bot_id", "")).strip()), "")
        bot_id = mapped_bot_id or str(old_target.get("bot_id", "") or "").strip() or LEGACY_BOT_ID
        persona_id = str(old_target.get("persona_id", "") or "").strip() or "[%None]"
        role_id = str(old_target.get("role_id", "") or "").strip() or LEGACY_ROLE_ID
        if not any(type(row) is dict and
                   (row.get("platform_id"), row.get("account_id"), row.get("participant_id")) ==
                   (platform_id, account_id, participant_id) for row in targets):
            targets.append({"target_id": "legacy-" + digest([platform_id, account_id, participant_id])[:20],
                            "platform_id": platform_id, "account_id": account_id, "bot_id": bot_id,
                            "participant_id": participant_id})
            changed = True
        if not any(type(row) is dict and row.get("bot_id") == bot_id
                   and row.get("persona_id") == persona_id for row in personas):
            personas.append({"bot_id": bot_id, "persona_id": persona_id, "role_id": role_id})
            changed = True

    if shared.get("enabled") is not True and was_enabled:
        shared["enabled"] = True
        changed = True
    if legacy.get("enabled") is not False:
        legacy["enabled"] = False
        changed = True

    for rows, template_key in ((targets, "private_target"), (personas, "persona_mapping"),
                               (groups, "group_target")):
        for row in rows:
            if type(row) is dict and "__template_key" not in row:
                row["__template_key"] = template_key
                changed = True
    return candidate, changed


def recover_repeated_single_target(config: object, pinned_binding: object) -> tuple[dict, bool]:
    """Undo only a generated legacy target outside the saved shared binding.

    The disabled old route must also be covered by a wildcard for the same Bot,
    and removing that one row must reproduce the complete saved binding. Real
    account, persona, group or ownership edits still require a reviewed save.
    """
    from .multi_settings import MultiHostSettings
    from .settings import HostControlError

    candidate = deepcopy(dict(config)) if isinstance(config, dict) else {}
    if not isinstance(pinned_binding, dict):
        return candidate, False
    legacy, old_target, shared = (candidate.get(name) for name in ("staging", "target", "multi_host"))
    if (not all(isinstance(section, dict) for section in (legacy, old_target, shared))
            or legacy.get("enabled") is not False):
        return candidate, False
    platform = str(old_target.get("platform_id", "default") or "default").strip()
    account = str(old_target.get("account_id", "") or "").strip()
    participant = str(old_target.get("participant_id", "") or "").strip()
    if not account.isascii() or not account.isdecimal() or not participant.isascii() or not participant.isdecimal():
        return candidate, False
    identifier = "legacy-" + digest([platform, account, participant])[:20]
    targets = shared.get("targets")
    if not isinstance(targets, list) or any(not isinstance(row, dict) for row in targets):
        return candidate, False
    generated = [row for row in targets if row.get("target_id") == identifier
                 and (row.get("platform_id"), row.get("account_id"), row.get("participant_id"))
                 == (platform, account, participant)]
    if len(generated) != 1:
        return candidate, False
    extra = generated[0]
    if not any((row.get("platform_id"), row.get("account_id"), row.get("bot_id"), row.get("participant_id"))
               == (platform, account, extra.get("bot_id"), "*") for row in targets):
        return candidate, False
    shared["targets"] = [row for row in targets if row is not extra]
    try:
        if MultiHostSettings.parse(candidate).binding_contract == pinned_binding:
            normalized, _ = migrate_single_target_config(candidate)
            return normalized, True
    except (HostControlError, ValueError, TypeError):
        pass
    return deepcopy(dict(config)), False

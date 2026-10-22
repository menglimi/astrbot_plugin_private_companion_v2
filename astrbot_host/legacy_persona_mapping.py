"""Read native choices only for V1-authorized windows during upgrade review."""

import inspect

from companion_v2.adapters.astrbot.native import bounded_native_lookup, configured_default_persona_id
from companion_v2.execution.models import TaskError
from companion_v2.legacy.configuration_migration import legacy_authorized_windows, legacy_persona_storage_shared
from .identity_derivation import derive_role_id
from .legacy_config import v1_setting
from .session_topology import session_route


async def _group_window_origins(controller, windows):
    allowed = {(row["platform_id"], row["native_scope_id"])
               for row in windows if row["scope_kind"] == "group"}
    if not allowed:
        return {}
    topology = getattr(controller, "session_topology", None)
    reader = getattr(topology, "_native_sessions", None)
    if callable(reader):
        native, _issues = await reader({platform for platform, _ in allowed}, scope_kind="group")
    else:
        native = getattr(controller.context.conversation_manager, "session_conversations", {})
    result = {}
    for umo in native:
        route = session_route(umo)
        if route and route[1] == "group" and (route[0], route[2]) in allowed:
            result.setdefault((route[0], route[2]), set()).add(umo)
    return result


async def _window_persona(controller, umo):
    context = controller.context
    manager = context.conversation_manager
    native = getattr(controller, "native_types", None)
    cid = await bounded_native_lookup(manager.get_curr_conversation_id(umo), operation="conversation_id")
    override = getattr(native, "session_persona_override_lookup", None)
    selected = await bounded_native_lookup(override(umo), operation="session_settings") if callable(override) else None
    if selected in (None, ""):
        snapshot = getattr(native, "persona_snapshot_lookup", None)
        if cid is not None and not callable(snapshot):
            raise TaskError("host_persona_snapshot_unavailable", "无法只读核对原生窗口人格。")
        conversation_persona = (await bounded_native_lookup(snapshot(context, umo, cid), operation="persona")
                                if callable(snapshot) else None)
        lookup = getattr(native, "persona_selection_lookup", None)
        if callable(lookup):
            result = lookup(context, umo, conversation_persona)
            selected = await bounded_native_lookup(result, operation="persona") if inspect.isawaitable(result) else result
        else:
            selected = conversation_persona or configured_default_persona_id(context, umo)
    if (type(selected) is not str or not selected.strip() or len(selected) > 120
            or any(ord(char) < 32 for char in selected)):
        raise TaskError("host_persona_invalid", "原生窗口人格不可识别。")
    if await bounded_native_lookup(manager.get_curr_conversation_id(umo), operation="conversation_verify") != cid:
        raise TaskError("host_conversation_changed", "核对时原生窗口已切换。")
    return selected


async def legacy_account_inventory(controller, source, accounts, personas):
    """Keep confirmed role IDs and old single-role ownership without catalog-wide adoption."""
    default = getattr(getattr(controller.context, "persona_manager", None), "default_persona", None) or "[%None]"
    current = controller.config.get("multi_host", {})
    mappings = current.get("personas", []) if isinstance(current, dict) else []
    mappings = mappings if isinstance(mappings, list) else []
    result = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        account_id, bot_id = account.get("account_id"), account.get("bot_id")
        try:
            roles = {name: derive_role_id(account_id, name) for name in [*personas, "[%None]"]}
        except (TypeError, ValueError):
            continue
        existing = {row["persona_id"]: row["role_id"] for row in mappings
                    if isinstance(row, dict) and row.get("bot_id") == bot_id
                    and type(row.get("persona_id")) is str and type(row.get("role_id")) is str}
        roles.update({name: role for name, role in existing.items() if name in roles})
        roles[""] = roles["[%None]"]
        result.append({**account, "persona_roles": roles, "default_persona_id": default,
                       "default_role_id": roles["[%None]"]})
    # A removed old persona must not suppress discovery of otherwise authorized
    # windows. Scope and persona availability are separate checks.
    windows = legacy_authorized_windows(source, accounts=result)
    single = legacy_persona_storage_shared(source)
    group_windows = await _group_window_origins(controller, windows)
    for account in result:
        verified = []
        for window in windows:
            if (window["platform_id"], window["account_id"]) != (account["platform_id"], account["account_id"]):
                continue
            kind = "FriendMessage" if window["scope_kind"] == "private" else "GroupMessage"
            umo = f"{account['platform_id']}:{kind}:{window['native_scope_id']}"
            origins = {umo}
            if window["scope_kind"] == "group":
                origins.update(group_windows.get((account["platform_id"], window["native_scope_id"]), ()))
            for origin in sorted(origins):
                try:
                    selected = await _window_persona(controller, origin)
                except (TaskError, AttributeError, TypeError, ValueError):
                    continue
                verified.append({"scope_kind": window["scope_kind"],
                    "native_scope_id": window["native_scope_id"], "persona_id": selected,
                    "unified_msg_origin": origin})
        account["native_windows"] = verified
        if not single:
            continue
        primary = v1_setting(source, "basic_config.plugin_specific_persona_id", "")
        primary = primary.strip() if type(primary) is str else ""
        primary = primary or account["default_persona_id"]
        names = list(dict.fromkeys([primary, *(row["persona_id"] for row in verified)]))
        existing = {row["persona_id"]: row["role_id"] for row in mappings
                    if isinstance(row, dict) and row.get("bot_id") == account["bot_id"]
                    and row.get("persona_id") in names and type(row.get("role_id")) is str}
        existing_roles = set(existing.values())
        # An upgraded installation may already have data under the original ID.
        # Preserve each explicit mapping; never merge two existing role stores.
        shared = (next(iter(existing_roles)) if len(existing_roles) == 1 else
                  account["persona_roles"].get(primary, account["default_role_id"]))
        for name in names:
            if name in account["persona_roles"] and name not in existing:
                account["persona_roles"][name] = shared
    return result

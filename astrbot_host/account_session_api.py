"""Dashboard-owned account bindings and native session controls."""

from __future__ import annotations

from copy import deepcopy
import json
import logging

from astrbot.api.web import request
from astrbot.core import sp

from companion_v2.adapters.astrbot.native import account_number
from companion_v2.execution.models import TaskError, digest
from .multi_settings import MultiHostSettings
from .native import remember_session_settings
from .settings import HostControlError


PREFIX = "/astrbot_plugin_private_companion/accounts"
logger = logging.getLogger(__name__)


class AccountSessionWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.get, ["GET"], "Read account bindings and native session topology"),
                (PREFIX, self.save, ["POST"], "Apply reviewed account and group bindings"),
                (PREFIX + "/group-target", self.save_group_target, ["POST"],
                 "Enable or disable one discovered group target"),
                (PREFIX + "/session", self.save_session, ["POST"], "Manage a discovered native session")]

    @staticmethod
    def _admin():
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard as an administrator")
        if request.query:
            raise TaskError("account_config_invalid", "query fields are not allowed")

    def _view(self):
        controller = self.controller
        section = controller.config.get("multi_host", {})
        targets = deepcopy(section.get("targets", []))
        groups = deepcopy(section.get("group_targets", []))
        personas = deepcopy(section.get("personas", []))
        enabled = bool(section.get("enabled", False))
        accounts = {(row["platform_id"], row["account_id"], row["bot_id"]):
                    {name: row[name] for name in ("platform_id", "account_id", "bot_id")}
                    for row in [*section.get("accounts", []), *targets, *groups]}
        return {"mode": "multi", "enabled": enabled,
                "accounts": list(accounts.values()), "personas": personas, "sessions": targets, "groups": groups}

    async def _discovered(self):
        from .setup_api import SetupWebAPI
        response = await SetupWebAPI(self.controller).api_targets()
        if response.get("status") != "ok":
            data = response.get("data") if isinstance(response.get("data"), dict) else {}
            code = data.get("code") or response.get("message") or "setup_targets_unavailable"
            reason = response.get("reason") or "the native session directory could not be read"
            raise TaskError(code, reason)
        return response["data"]

    async def get(self):
        try:
            self._admin()
            return {"status": "ok", "data": {**self._view(), "discovered": await self._discovered()}}
        except (TaskError, HostControlError) as error:
            return self._error(error.code, str(error))

    @staticmethod
    def _error(code, reason):
        from .web_api import outcome_response
        from companion_v2.foundation.outcome import Outcome
        return outcome_response(Outcome.failed(code, reason))

    @staticmethod
    async def _body():
        raw = await request.body()
        if len(raw) > 65536:
            raise TaskError("account_config_invalid", "configuration is too large")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TaskError("account_config_invalid", "configuration must be UTF-8 JSON") from error
        if type(data) is not dict:
            raise TaskError("account_config_invalid", "configuration must be an object")
        return data

    async def save_session(self):
        try:
            self._admin()
            body = await self._body()
            if (set(body) - {"session_key", "llm_enabled", "session_enabled", "persona_id"} or len(body) < 2
                    or type(body.get("session_key")) is not str):
                raise TaskError("account_config_invalid", "select a native session and its settings")
            if any(field in body and type(body[field]) is not bool for field in ("llm_enabled", "session_enabled")):
                raise TaskError("account_config_invalid", "session switches must be booleans")
            async with self.controller._control_lock:
                if self.controller._terminated:
                    raise TaskError("staging_host_terminated", "the plugin has stopped")
                row = await self.controller.session_topology.select(body["session_key"])
                if row is None or not row["native"]:
                    raise TaskError("account_session_unavailable", "the selected native session is no longer available")
                if "persona_id" in body:
                    from .persona_catalog import available_personas
                    persona = body["persona_id"]
                    if type(persona) is not str or persona not in ["", "[%None]", *await available_personas(self.controller.context)]:
                        raise TaskError("host_persona_unavailable", "select a currently loaded AstrBot persona")
                    if row["managed"] and persona and not any(
                            item["bot_id"] == row["bot_id"] and item["persona_id"] == persona
                            for item in self._view()["personas"]):
                        raise TaskError("account_session_persona_unmapped", "add this persona to the Bot bindings first")
                umo = row["unified_msg_origin"]
                services = dict(await sp.get_async(scope="umo", scope_id=umo,
                                                   key="session_service_config", default={}) or {})
                for field in ("llm_enabled", "session_enabled"):
                    if field in body:
                        services[field] = body[field]
                if "persona_id" in body:
                    if body["persona_id"]:
                        services["persona_id"] = body["persona_id"]
                    else:
                        services.pop("persona_id", None)
                await sp.put_async(scope="umo", scope_id=umo, key="session_service_config", value=services)
                remember_session_settings(umo, services)
            return {"status": "ok", "data": {"saved": True, "requires_reload": False}}
        except (TaskError, HostControlError) as error:
            return self._error(error.code, str(error))
        except OSError:
            return self._error("account_config_save_failed", "the account settings could not be saved")

    async def save_group_target(self):
        try:
            self._admin()
            controller = self.controller
            body = await self._body()
            fields = {"platform_id", "account_id", "bot_id", "group_id", "enabled"}
            if set(body) != fields or type(body.get("enabled")) is not bool:
                raise TaskError("account_config_invalid", "select one group target and its desired state")
            enabled = body["enabled"]
            platform_id, account_id, bot_id, group_id = (body[name] for name in
                ("platform_id", "account_id", "bot_id", "group_id"))
            if any(type(value) is not str or len(value) > 128
                   for value in (platform_id, account_id, bot_id, group_id)):
                raise TaskError("account_config_invalid", "group target identity fields must be nonempty text")
            if not platform_id.strip() or not group_id.strip():
                raise TaskError("account_config_invalid", "group target identity fields must be nonempty text")
            if enabled and (not account_id.strip() or not bot_id.strip()):
                raise TaskError("account_group_target_route_unresolved",
                                "the native group session is not associated with one connected Bot account yet")
            if not account_id.strip() or not bot_id.strip():
                raise TaskError("account_config_invalid", "group target identity fields must be nonempty text")
            account_id = account_number(account_id)
            group_id = account_number(group_id)
            current = self._view()
            route = (platform_id, account_id, bot_id, group_id)
            group_rows = deepcopy(current["groups"])
            existing = next((row for row in group_rows if
                (row["platform_id"], row["account_id"], row["bot_id"], row["group_id"]) == route), None)
            if enabled and existing is None:
                account_key = (platform_id, account_id, bot_id)
                if account_key not in {(row["platform_id"], row["account_id"], row["bot_id"])
                                       for row in current["accounts"]}:
                    raise TaskError("account_group_target_account_required",
                                    "bind this Bot account and persona in account management first")
                discovered = await self._discovered()
                if not any(row.get("scope_kind") == "group"
                           and row.get("platform_id") == platform_id
                           and row.get("account_id") in ("", account_id)
                           and row.get("group_id") == group_id
                           for row in discovered.get("targets", [])):
                    issue = next((item for item in discovered.get("directory", {}).get("issues", [])
                                  if item.get("platform_id") in ("", platform_id)), None)
                    if issue:
                        raise TaskError(issue["code"], issue["reason"])
                    raise TaskError("account_group_target_unavailable",
                                    "select a group currently present in the native session directory")
                target_id = "group-" + digest((platform_id, account_id, group_id))[:20]
                group_rows.append({"target_id": target_id, "platform_id": platform_id,
                                   "account_id": account_id, "bot_id": bot_id, "group_id": group_id})
            elif enabled:
                target_id = existing["target_id"]
            elif existing is None:
                return {"status": "ok", "data": {"saved": True, "configured": False, "target_id": None}}
            else:
                target_id = existing["target_id"]
                group_rows.remove(existing)

            candidate = deepcopy(dict(controller.config))
            section = candidate.setdefault("multi_host", {})
            if type(section) is not dict:
                raise TaskError("account_config_invalid", "group targets require a valid shared host configuration")
            section["group_targets"] = group_rows
            MultiHostSettings.parse(candidate)
            result = await controller.apply_bindings(candidate)
            return {"status": "ok", "data": {"saved": True, "configured": enabled,
                                                   "target_id": target_id if enabled else None,
                                                   "requires_reload": result["requires_reload"],
                                                   "requires_initialize": result["requires_initialize"]}}
        except (TaskError, HostControlError) as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError):
            return self._error("account_config_invalid", "the selected group target could not be validated")
        except OSError:
            return self._error("account_config_save_failed", "the group access setting could not be saved")
        except Exception as error:
            logger.exception("V2 group target update failed")
            detail = " ".join(str(error).split())
            reason = f"{type(error).__name__}: {detail[:512]}" if detail else type(error).__name__
            return self._error("account_group_target_apply_failed", reason)

    async def save(self):
        try:
            self._admin()
            controller = self.controller
            body = await self._body()
            if set(body) - {"enabled", "accounts", "sessions", "personas", "groups"}:
                raise TaskError("account_config_invalid", "configuration has unknown fields")
            enabled = body.get("enabled", True)
            if type(enabled) is not bool:
                raise TaskError("account_config_invalid", "enabled must be a boolean")
            current = self._view()
            sync_private_targets = "sessions" not in body
            accounts = body.get("accounts")
            sessions = body.get("sessions", current["sessions"])
            personas = body.get("personas")
            groups = body.get("groups", current["groups"])
            if accounts is None:
                accounts = []
            if personas is None:
                personas = current["personas"]
            if any(type(rows) is not list or any(type(row) is not dict for row in rows)
                   for rows in (accounts, sessions, personas, groups)):
                raise TaskError("account_config_invalid", "account bindings must be lists of objects")
            discovered = await self._discovered()
            known = {(row["platform_id"], row["account_id"], row["bot_id"]): row for row in discovered["accounts"]}

            def account_key(row):
                raw = str(row.get("account_key", ""))
                return tuple(raw.split("|")) if raw else tuple(str(row.get(key, "")).strip()
                    for key in ("platform_id", "account_id", "bot_id"))

            selected = {account_key(row) for row in accounts}
            if not selected and not body.get("accounts"):
                selected = set(known)
            if not selected or any(key not in known for key in selected):
                raise TaskError("account_config_invalid", "select currently connected Bot accounts")
            private, group_rows = [], []
            for rows, old, peer_field, kind, output in ((sessions, current["sessions"], "participant_id", "private", private),
                                                      (groups, current["groups"], "group_id", "group", group_rows)):
                existing = {(row["platform_id"], row["account_id"], row[peer_field]): row for row in old}
                for row in rows:
                    key = account_key(row)
                    peer = row.get(peer_field)
                    peer = "*" if peer == "*" else account_number(peer)
                    if kind == "group" and peer == "*":
                        previous = existing.get((key[0], key[1], peer))
                        if "groups" not in body and previous is not None and key in selected:
                            output.append({"target_id": previous["target_id"],
                                           "platform_id": key[0], "account_id": key[1],
                                           "bot_id": key[2], peer_field: peer})
                        continue
                    route = (key[0], key[1], peer)
                    previous = existing.get(route)
                    if key not in selected:
                        # A removed account must not be retained by its old windows.
                        # Reject newly supplied references to unselected accounts.
                        if previous is not None and account_key(previous) == key:
                            continue
                        raise TaskError("account_config_invalid", "each window must select a configured Bot account")
                    if kind == "group" and previous is None and not any(
                            item.get("scope_kind") == "group" and item["platform_id"] == key[0]
                            and item.get("account_id") in ("", key[1]) and item.get("group_id") == peer
                            for item in discovered["targets"]):
                        issue = next((item for item in discovered.get("directory", {}).get("issues", [])
                                      if item.get("platform_id") in ("", key[0])), None)
                        if issue:
                            raise TaskError(issue["code"], issue["reason"])
                        raise TaskError("account_config_invalid", "select a group from the native session directory")
                    output.append({"target_id": previous["target_id"] if previous else kind + "-" + digest(route)[:20],
                                   "platform_id": key[0], "account_id": key[1], "bot_id": key[2], peer_field: peer})
            if sync_private_targets:
                # Keep existing private routes and stable IDs. Only accounts with
                # no private target receive a discovery template; groups stay explicit.
                represented = {account_key(row) for row in private}
                for key in sorted(selected - represented):
                    private.append({"target_id": "private-" + digest((key[0], key[1], "*"))[:20],
                                   "platform_id": key[0], "account_id": key[1],
                                   "bot_id": key[2], "participant_id": "*"})
            mapped = []
            available = {(row["bot_id"], row["persona_id"]) for row in discovered["personas"]}
            old_roles = {(row["bot_id"], row["persona_id"]): row["role_id"] for row in current["personas"]}
            selected_bots = {key[2] for key in selected}
            for row in personas:
                key = (str(row.get("bot_id", "")), str(row.get("persona_id", "")))
                if key[0] not in selected_bots:
                    if key in old_roles:
                        continue
                    raise TaskError("account_config_invalid", "each persona must select a configured Bot account")
                if key not in available:
                    raise TaskError("host_persona_unavailable", "select a currently loaded AstrBot persona")
                role_id = str(row.get("role_id", old_roles.get(key, ""))).strip()
                if not role_id or len(role_id) > 128:
                    raise TaskError("account_config_invalid", "each registered persona needs a role name")
                mapped.append({"bot_id": key[0], "persona_id": key[1],
                               "role_id": role_id})
            candidate = deepcopy(dict(controller.config))
            section = candidate.setdefault("multi_host", {})
            section.update(enabled=enabled, accounts=[{"platform_id": key[0], "account_id": key[1], "bot_id": key[2]}
                                                      for key in sorted(selected)],
                           targets=private, personas=mapped, group_targets=group_rows)
            MultiHostSettings.parse(candidate)
            result = await controller.apply_bindings(candidate)
            try:
                discovered = await self._discovered()
            except (TaskError, HostControlError):
                # The configuration is already persisted. A subsequent native
                # directory read must not turn that save into a failure receipt.
                result = {**result, "directory_refresh_pending": True}
            return {"status": "ok", "data": {**result, "configuration": {**self._view(), "discovered": discovered}}}
        except (TaskError, HostControlError) as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError):
            return self._error("account_config_invalid", "the selected account bindings could not be validated")
        except OSError:
            return self._error("account_config_save_failed", "the account bindings could not be saved")

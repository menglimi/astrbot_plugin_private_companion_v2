"""Small, human-oriented configuration surface for the account topology page."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astrbot.api.web import request

from companion_v2.execution.models import TaskError
from .group_settings import parse_group_targets
from .multi_settings import MultiHostSettings


PREFIX = "/astrbot_plugin_private_companion_v2/accounts"


class AccountSessionWebAPI:
    """Translate the three columns into the existing multi_host contract.

    The page owns only the routing fields. Stable internal IDs are generated here,
    and the candidate configuration is parsed before it is written.
    """

    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.get, ["GET"], "Read account and session configuration"),
                (PREFIX, self.save, ["POST"], "Save account and session configuration")]

    @staticmethod
    def _admin():
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard as an administrator")

    def _config_path(self) -> Path | None:
        # AstrBot exposes the loaded config object, but not its path on Context.
        # The normal plugin data directory is the documented fallback used by the
        # test host; a host may provide an explicit path for real persistence.
        explicit = getattr(self.controller, "config_path", None)
        if explicit:
            return Path(explicit).resolve()
        return None

    def _view(self):
        section = self.controller.config.get("multi_host", {})
        if not isinstance(section, dict):
            section = {}
        if not hasattr(self.controller, "target_inventory"):
            return {"enabled": False, "mode": "single", "binding": self.controller.binding_state(),
                    "accounts": [], "personas": [], "sessions": [], "groups": [],
                    "discovered": {"accounts": [], "personas": [], "targets": []}}
        targets = list(section.get("targets", [])) if isinstance(section.get("targets", []), list) else []
        personas = list(section.get("personas", [])) if isinstance(section.get("personas", []), list) else []
        return {"enabled": bool(section.get("enabled", False)),
                "accounts": self._accounts(targets), "personas": personas,
                "sessions": targets,
                "groups": list(section.get("group_targets", [])) if isinstance(section.get("group_targets", []), list) else []}

    async def _discovered(self):
        """Use the same live inventory as the setup guide for page choices."""
        from .setup_api import SetupWebAPI
        setup = SetupWebAPI(self.controller)
        data = (await setup.api_targets()).get("data", {})
        accounts = data.get("accounts", [])
        if not accounts and hasattr(self.controller, "settings") and self.controller.settings:
            accounts = [{"platform_id": item.platform_id, "account_id": item.account_id,
                         "bot_id": item.bot_id} for item in self.controller.settings.accounts]
        personas = data.get("personas", [])
        if not personas and getattr(self.controller, "settings", None):
            personas = [{"bot_id": item.bot_id, "persona_id": item.persona_id,
                         "role_id": item.role_id, "label": item.persona_id}
                        for item in self.controller.settings.personas]
        return {"accounts": accounts, "personas": personas, "targets": data.get("targets", [])}

    @staticmethod
    def _accounts(targets):
        seen, result = set(), []
        for item in targets:
            key = (item.get("platform_id", ""), item.get("account_id", ""), item.get("bot_id", ""))
            if key in seen:
                continue
            seen.add(key)
            result.append({"platform_id": key[0], "account_id": key[1], "bot_id": key[2]})
        return result

    async def get(self):
        from .web_api import outcome_response
        from companion_v2.foundation.outcome import Outcome
        try:
            self._admin()
            if not hasattr(self.controller, "target_inventory"):
                raise TaskError("account_config_mode_required", "account and session editing is available for the shared host")
            result = self._view()
            discovered = await self._discovered()
            result["discovered"] = discovered
            return {"status": "ok", "data": result}
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))

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

    async def save(self):
        from .web_api import outcome_response
        from companion_v2.foundation.outcome import Outcome
        try:
            self._admin()
            if not hasattr(self.controller, "target_inventory"):
                raise TaskError("account_config_mode_required", "account and session editing is available for the shared host")
            if request.query:
                raise TaskError("account_config_invalid", "query fields are not allowed")
            if getattr(self.controller, "session", None) is not None:
                raise TaskError("account_config_running", "stop the host before changing account bindings")
            body = await self._body()
            enabled = body.get("enabled", True)
            if type(enabled) is not bool:
                raise TaskError("account_config_invalid", "enabled must be a boolean")
            accounts = body.get("accounts", [])
            sessions = body.get("sessions", [])
            personas = body.get("personas", [])
            if not all(isinstance(x, dict) for x in (accounts, sessions, personas)):
                raise TaskError("account_config_invalid", "accounts, personas and sessions must be lists")
            discovered = await self._discovered()
            known = {(str(x.get("platform_id", "")).strip(), str(x.get("account_id", "")).strip(), str(x.get("bot_id", "")).strip()): x for x in discovered["accounts"]}
            normalized_accounts = []
            for item in accounts:
                key = str(item.get("account_key", "")).strip()
                parts = key.split("|", 2)
                candidate = tuple(parts) if len(parts) == 3 else (str(item.get("platform_id", "")).strip(), str(item.get("account_id", "")).strip(), str(item.get("bot_id", "")).strip())
                if candidate not in known:
                    raise TaskError("account_config_invalid", "账号必须来自 AstrBot 当前已连接目录")
                normalized_accounts.append(known[candidate])
            accounts = normalized_accounts
            account_map = {(x["platform_id"], x["account_id"], x["bot_id"]): x for x in accounts}
            if any(not all(key) for key in account_map):
                raise TaskError("account_config_invalid", "each account needs platform, login account and Bot")
            target_rows, target_ids = [], set()
            for index, item in enumerate(sessions, 1):
                raw_key = str(item.get("account_key", "")).strip()
                parts = raw_key.split("|", 2)
                key = tuple(parts) if len(parts) == 3 else (str(item.get("platform_id", "")).strip(), str(item.get("account_id", "")).strip(), str(item.get("bot_id", "")).strip())
                participant = str(item.get("participant_id", "")).strip()
                if key not in account_map or not participant:
                    raise TaskError("account_config_invalid", "each session must select an existing account and participant")
                reachable = {(str(x.get("platform_id", "")), str(x.get("account_id", "")), str(x.get("bot_id", "")), str(x.get("participant_id") or x.get("group_id") or "")) for x in discovered["targets"]}
                if (*key, participant) not in reachable and not participant.isdigit():
                    raise TaskError("account_config_invalid", "新私聊对象必须填写数字账号；群聊窗口必须来自探测目录")
                target_id = f"target-{index}"
                if target_id in target_ids:
                    raise TaskError("account_config_invalid", "session identifiers must be unique")
                target_ids.add(target_id)
                target_rows.append({"target_id": target_id, "platform_id": key[0], "account_id": key[1], "bot_id": key[2], "participant_id": participant})
            persona_rows, persona_keys = [], set()
            for index, item in enumerate(personas, 1):
                bot_id = str(item.get("bot_id", "")).strip()
                persona_id = str(item.get("persona_id", "")).strip()
                role_id = str(item.get("role_id", "role-" + str(index))).strip()
                if not bot_id or not persona_id or not role_id or (bot_id, persona_id) in persona_keys:
                    raise TaskError("account_config_invalid", "each native persona mapping must be unique and complete")
                persona_keys.add((bot_id, persona_id))
                persona_rows.append({"bot_id": bot_id, "persona_id": persona_id, "role_id": role_id})
            candidate = dict(self.controller.config)
            old = dict(candidate.get("multi_host", {}))
            old.update({"enabled": enabled, "installation_id": old.get("installation_id", "main"),
                        "targets": target_rows, "personas": persona_rows, "group_targets": old.get("group_targets", []),
                        "capabilities": old.get("capabilities", [])})
            candidate["multi_host"] = old
            MultiHostSettings.parse(candidate)
            path = self._config_path()
            saver = getattr(self.controller, "save_plugin_config", None)
            if callable(saver):
                saver(candidate)
            else:
                raise TaskError("account_config_persistence_unavailable", "AstrBot did not expose a plugin configuration writer")
            return {"status": "ok", "data": {"saved": True, "requires_reload": True, "configuration": self._view()}}
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except Exception as error:  # noqa: BLE001
            return outcome_response(Outcome.failed("account_config_invalid", "the selected bindings could not be validated"))

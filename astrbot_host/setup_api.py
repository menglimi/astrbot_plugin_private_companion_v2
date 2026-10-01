"""Authenticated, persistent first-run setup routes for the Companion V2 host."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from uuid import uuid4

from astrbot.api.web import request

from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome

from .binding_store import PendingBinding, binding_path, read_binding, write_binding
from .identity_derivation import derive_bot_id, derive_role_id
from .persona_catalog import available_personas
from .setup_state import SETUP_STEPS, SetupStateStore


PREFIX = "/astrbot_plugin_private_companion_v2/setup"
TEST_MESSAGE = "V2 主动消息通路测试已送达。此消息由「开始使用」中的主动测试按钮触发。"


class SetupWebAPI:
    def __init__(self, controller):
        self.controller = controller
        self.progress = SetupStateStore(controller.data_root)
        self._test_lock = asyncio.Lock()

    def routes(self):
        return [
            (PREFIX + "/status", self.status, ["GET"], "Read persistent Companion V2 setup progress"),
            (PREFIX + "/targets", self.api_targets, ["GET"], "Read connected OneBot accounts and native personas"),
            (PREFIX + "/mode", self.mode, ["POST"], "Select the Companion V2 account and persona mode"),
            (PREFIX + "/binding/confirm", self.confirm_binding, ["POST"], "Confirm the Companion V2 core administrator window"),
            (PREFIX + "/model", self.model, ["POST"], "Choose the initial Companion V2 text provider"),
            (PREFIX + "/host/start", self.reconnect_host, ["POST"], "Reconnect a completed Companion V2 setup"),
            (PREFIX + "/prepare", self.prepare, ["POST"], "Prepare the confirmed Companion V2 profile"),
            (PREFIX + "/complete", self.complete, ["POST"], "Record a completed Companion V2 setup section"),
            (PREFIX + "/proactive-test", self.proactive_test, ["POST"], "Send the user-requested one-time proactive test"),
        ]

    @staticmethod
    def _admin():
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard as an administrator")
        if request.query:
            raise TaskError("setup_request_invalid", "setup routes do not accept query overrides")
        return username

    @staticmethod
    async def _body(expected: set[str]) -> dict:
        raw = await request.body()
        if len(raw) > 4096:
            raise ValueError("request is too large")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = value
            return result

        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite value")))
        if type(value) is not dict or set(value) != expected:
            raise ValueError("unexpected fields")
        return value

    @staticmethod
    def _response(result: Outcome):
        from .web_api import outcome_response
        return outcome_response(result)

    @staticmethod
    def _error(code: str, reason: str):
        return SetupWebAPI._response(Outcome.failed(code, reason))

    def _active_mode(self) -> str:
        return "multiple" if bool(getattr(self.controller, "_multi_host", False)) else "single"

    def _mode_requires_reload(self, mode: dict | None) -> bool:
        if not mode:
            return False
        wants_multi = mode["accounts"] == "multiple" or mode["personas"] == "multiple"
        config = getattr(self.controller, "config", {})
        staging = config.get("staging", {}) if isinstance(config, dict) else {}
        multi_host = config.get("multi_host", {}) if isinstance(config, dict) else {}
        enabled = bool((multi_host if wants_multi else staging).get("enabled", False))
        is_multi = self._active_mode() == "multiple"
        return wants_multi != is_multi or not enabled

    def _binding(self) -> dict:
        getter = getattr(self.controller, "binding_state", None)
        if not callable(getter):
            return {"bound": False, "confirmed": False, "pending": False}
        return getter()

    def _model_providers(self) -> list[dict]:
        context = self.controller.context
        providers = []
        try:
            inventory = list(context.get_all_providers() or [])
        except Exception:
            return providers
        for provider in inventory:
            try:
                meta = provider.meta() if callable(getattr(provider, "meta", None)) else None
                identifier = str(getattr(meta, "id", "") or getattr(provider, "id", "") or "").strip()
                if not identifier:
                    continue
                name = str(getattr(meta, "name", "") or getattr(provider, "name", "") or identifier)
                expected_type = getattr(getattr(self.controller, "native_types", None), "provider", None)
                if expected_type is not None and type(provider) is expected_type:
                    providers.append({"id": identifier, "name": name[:120]})
            except (AttributeError, TypeError, ValueError):
                continue
        return sorted({item["id"]: item for item in providers}.values(),
                      key=lambda item: (item["name"].lower(), item["id"]))

    def _configured_provider_id(self) -> str:
        config = getattr(self.controller, "config", {})
        section = config.get("model", {}) if isinstance(config, dict) else {}
        return str(section.get("provider_id", "")) if isinstance(section, dict) else ""

    def _status_document(self) -> dict:
        state = self.progress.read()
        binding = self._binding()
        status = self.controller.status()
        mode_matches = bool(state["mode"]) and not self._mode_requires_reload(state["mode"])
        confirmed = bool(binding.get("bound") and not binding.get("pending"))
        prepared = bool(getattr(self.controller, "runtime", None)
                        and (getattr(self.controller, "session", None)
                             or getattr(self.controller, "last_session", None)))
        completed = list(state["completed"])
        skipped = list(state["skipped"])
        if not state["mode"]:
            step = "mode"
        elif not mode_matches:
            step = "mode"
        elif not confirmed:
            step = "binding"
        elif state["ready"]:
            step = "complete"
        elif "model" not in completed and "model" not in skipped:
            step = "model"
        elif not self._configured_provider_id():
            step = "model"
        else:
            step = next((name for name in SETUP_STEPS if name not in completed and name not in skipped),
                        "proactive_test")
        return {"step": step, "mode": state["mode"], "active_mode": self._active_mode(),
                "mode_requires_reload": self._mode_requires_reload(state["mode"]),
                "binding": binding, "binding_confirmed": confirmed, "prepared": prepared,
                "completed": completed, "skipped": skipped,
                "model": {"provider_id": self._configured_provider_id(),
                          "providers": self._model_providers()},
                "proactive_test": state["proactive_test"], "ready": state["ready"],
                "settings_error": getattr(getattr(self.controller, "settings_error", None), "code", None),
                "host": status}

    async def status(self):
        try:
            self._admin()
            return self._response(Outcome.success(self._status_document()))
        except TaskError as error:
            return self._error(error.code, str(error))
        except (ValueError, OSError, UnicodeError):
            return self._error("setup_progress_unavailable", "the saved setup progress cannot be read")

    async def api_targets(self):
        try:
            self._admin()
            context = self.controller.context
            manager = getattr(context, "platform_manager", None)
            enumerator = getattr(manager, "get_insts", None)
            platforms = list(enumerator() or []) if callable(enumerator) else []
            if not platforms:
                fallback = getattr(context, "platform", None)
                platforms = [fallback] if fallback is not None else []
            accounts = []
            for platform in platforms:
                try:
                    metadata = platform.meta()
                    platform_id = str(metadata.id)
                    if metadata.name != "aiocqhttp":
                        continue
                    client = platform.get_client()
                    connections = getattr(client, "_wsr_api_clients", {})
                    if not isinstance(connections, dict):
                        continue
                    for raw_id in connections:
                        account_id = str(raw_id).strip()
                        if not account_id.isdigit():
                            continue
                        accounts.append({"platform_id": platform_id, "account_id": account_id,
                                         "bot_id": derive_bot_id(account_id)})
                except (AttributeError, TypeError, ValueError):
                    continue
            accounts = sorted({(item["platform_id"], item["account_id"], item["bot_id"]): item
                               for item in accounts}.values(),
                              key=lambda item: (item["platform_id"], int(item["account_id"])))
            persona_names = await available_personas(context)
            choices = []
            for account in accounts:
                names = persona_names or ["[%None]"]
                for persona_id in names:
                    choices.append({"bot_id": account["bot_id"], "persona_id": persona_id,
                                    "role_id": derive_role_id(account["account_id"], persona_id),
                                    "label": persona_id})
            configured = getattr(getattr(self.controller, "settings", None), "targets", ())
            targets = [{"platform_id": item.platform_id, "account_id": item.account_id,
                        "bot_id": item.bot_id, "participant_id": item.participant_id}
                       for item in configured]
            return self._response(Outcome.success({"accounts": accounts, "personas": choices,
                                                    "targets": targets}))
        except TaskError as error:
            return self._error(error.code, str(error))
        except Exception:
            return self._error("setup_targets_unavailable", "connected account and persona inventory is unavailable")

    async def mode(self):
        try:
            self._admin()
            data = await self._body({"accounts", "personas"})
            if (data["accounts"] not in ("single", "multiple")
                    or data["personas"] not in ("single", "multiple")):
                raise ValueError("invalid mode")
            config = self.controller.config
            if not isinstance(config, dict):
                raise TaskError("setup_config_unavailable", "the plugin configuration cannot be edited here")
            save = getattr(self.controller, "save_plugin_config", None)
            if not callable(save):
                raise TaskError("setup_config_save_unavailable", "restart the plugin with Dashboard configuration support")
            candidate = deepcopy(config)
            multi = data["accounts"] == "multiple" or data["personas"] == "multiple"
            staging = candidate.setdefault("staging", {})
            shared = candidate.setdefault("multi_host", {})
            if type(staging) is not dict or type(shared) is not dict:
                raise TaskError("setup_config_invalid", "the plugin mode settings have an invalid shape")
            staging["enabled"] = not multi
            shared["enabled"] = multi
            save(candidate)
            state = self.progress.select_mode(accounts=data["accounts"], personas=data["personas"])
            return self._response(Outcome.success({"mode": state["mode"],
                "mode_requires_reload": self._mode_requires_reload(state["mode"]),
                "active_mode": self._active_mode()}))
        except TaskError as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError, UnicodeError, OSError):
            return self._error("setup_mode_invalid", "select one account mode and one persona mode")

    async def confirm_binding(self):
        try:
            self._admin()
            await self._body(set())
            if self._mode_requires_reload(self.progress.read()["mode"]):
                raise TaskError("setup_mode_reload_required", "restart the plugin to apply the selected mode first")
            confirm = getattr(self.controller, "confirm_binding", None)
            if not callable(confirm):
                raise TaskError("setup_binding_unavailable", "the active host cannot confirm a private window")
            result = confirm()
            if result.get("confirmed") is not True:
                raise TaskError(result.get("reason", "setup_binding_missing"),
                                result.get("detail", "send companion_bind from the core administrator private window first"))
            return self._response(Outcome.success({"binding": self._binding(), "confirmed": True}))
        except TaskError as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError, OSError):
            return self._error("setup_binding_confirmation_failed", "the pending private window could not be confirmed")

    async def model(self):
        try:
            self._admin()
            data = await self._body({"provider_id"})
            provider_id = data["provider_id"]
            if type(provider_id) is not str or not provider_id.strip() or len(provider_id) > 512:
                raise ValueError("invalid provider")
            status = self._status_document()
            if status["step"] != "model":
                raise TaskError("setup_step_order_invalid", "confirm the core administrator window before choosing a model")
            available = {item["id"] for item in status["model"]["providers"]}
            provider = self.controller.context.get_provider_by_id(provider_id)
            expected_type = getattr(getattr(self.controller, "native_types", None), "provider", None)
            if provider_id not in available or expected_type is None or type(provider) is not expected_type:
                raise TaskError("host_provider_unavailable", "choose a loaded AstrBot text provider supported by V2")
            config = self.controller.config
            if not isinstance(config, dict):
                raise TaskError("setup_config_unavailable", "the plugin configuration cannot be edited here")
            save = getattr(self.controller, "save_plugin_config", None)
            if not callable(save):
                raise TaskError("setup_config_save_unavailable", "restart the plugin with Dashboard configuration support")
            candidate = deepcopy(config)
            model_settings = candidate.setdefault("model", {})
            if type(model_settings) is not dict:
                raise TaskError("setup_config_invalid", "the plugin model settings have an invalid shape")
            model_settings["provider_id"] = provider_id
            save(candidate)
            refresh = getattr(self.controller, "refresh_settings", None)
            if callable(refresh):
                refresh()
            settings_error = getattr(self.controller, "settings_error", None)
            if settings_error is not None:
                raise TaskError(settings_error.code, str(settings_error))
            initialized = await self.controller.initialize_profile()
            if initialized.failure is not None:
                raise TaskError(initialized.failure.code, initialized.failure.reason)
            state = self.progress.complete("model")
            return self._response(Outcome.success({"provider_id": provider_id,
                "completed": state["completed"], "prepared": True,
                "status": self._status_document()}))
        except TaskError as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError, OSError, UnicodeError):
            return self._error("setup_model_invalid", "choose a loaded AstrBot text provider and retry")

    async def reconnect_host(self):
        try:
            self._admin()
            await self._body(set())
            state = self.progress.read()
            if not state["ready"]:
                raise TaskError("setup_completion_required", "complete the first-run setup before reconnecting")
            if self._mode_requires_reload(state["mode"]):
                raise TaskError("setup_mode_reload_required", "restart the plugin to apply the selected mode first")
            binding = self._binding()
            if not binding.get("bound") or binding.get("pending"):
                raise TaskError("setup_binding_confirmation_required", "confirm the core administrator private window first")
            refresh = getattr(self.controller, "refresh_settings", None)
            if callable(refresh):
                refresh()
            settings_error = getattr(self.controller, "settings_error", None)
            if settings_error is not None:
                raise TaskError(settings_error.code, str(settings_error))
            result = await self.controller.start()
            if result.failure is not None:
                raise TaskError(result.failure.code, result.failure.reason)
            return self._response(Outcome.success({"started": True, "status": self._status_document()}))
        except TaskError as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError, OSError, UnicodeError):
            return self._error("setup_reconnect_failed", "the completed V2 host could not reconnect")

    async def prepare(self):
        try:
            self._admin()
            await self._body(set())
            refresh = getattr(self.controller, "refresh_settings", None)
            if callable(refresh):
                refresh()
            if self._mode_requires_reload(self.progress.read()["mode"]):
                raise TaskError("setup_mode_reload_required", "restart the plugin to apply the selected mode first")
            binding = self._binding()
            if not binding.get("bound") or binding.get("pending"):
                raise TaskError("setup_binding_confirmation_required", "confirm the core administrator private window first")
            if getattr(self.controller, "settings_error", None) is not None:
                error = self.controller.settings_error
                raise TaskError(error.code, str(error))
            result = await self.controller.initialize_profile()
            if result.failure is not None:
                raise TaskError(result.failure.code, result.failure.reason)
            return self._response(Outcome.success({"prepared": True, "profile": result.unwrap(),
                                                  "status": self._status_document()}))
        except TaskError as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError, OSError):
            return self._error("setup_prepare_failed", "the confirmed V2 profile could not be prepared")

    async def complete(self):
        try:
            self._admin()
            data = await self._body({"step", "skipped"})
            step, skipped = data["step"], data["skipped"]
            if step not in SETUP_STEPS or type(skipped) is not bool:
                raise ValueError("invalid setup step")
            if step == "model" and skipped:
                raise TaskError("setup_model_required", "choose a V2 text provider before continuing")
            state = self.progress.read()
            if state["mode"] is None or self._mode_requires_reload(state["mode"]):
                raise TaskError("setup_mode_required", "select and activate an account/persona mode first")
            binding = self._binding()
            if not binding.get("bound") or binding.get("pending"):
                raise TaskError("setup_binding_confirmation_required", "confirm the core administrator private window first")
            prepared = bool(getattr(self.controller, "runtime", None)
                            and (getattr(self.controller, "session", None)
                                 or getattr(self.controller, "last_session", None)))
            position = SETUP_STEPS.index(step)
            if any(name not in state["completed"] + state["skipped"] for name in SETUP_STEPS[:position]):
                raise TaskError("setup_step_order_invalid", "finish the previous setup section first")
            if step != "model" and not prepared:
                refresh = getattr(self.controller, "refresh_settings", None)
                if callable(refresh):
                    refresh()
                settings_error = getattr(self.controller, "settings_error", None)
                if settings_error is not None:
                    raise TaskError(settings_error.code, str(settings_error))
                result = await self.controller.initialize_profile()
                if result.failure is not None:
                    raise TaskError(result.failure.code, result.failure.reason)
                prepared = True
            if step == "model":
                refresh = getattr(self.controller, "refresh_settings", None)
                if callable(refresh):
                    refresh()
                settings_error = getattr(self.controller, "settings_error", None)
                if settings_error is not None:
                    raise TaskError(settings_error.code, str(settings_error))
                settings = getattr(self.controller, "settings", None)
                model_settings = getattr(settings, "common", settings)
                if not getattr(model_settings, "provider_id", ""):
                    raise TaskError("setup_model_required", "choose a V2 text provider in Model and connections first")
                if not prepared:
                    result = await self.controller.initialize_profile()
                    if result.failure is not None:
                        raise TaskError(result.failure.code, result.failure.reason)
            state = self.progress.complete(step, skipped=skipped)
            return self._response(Outcome.success({"completed": state["completed"],
                "skipped": state["skipped"], "step": step, "skipped_this_step": skipped,
                "prepared": bool(getattr(self.controller, "runtime", None)
                                  and (getattr(self.controller, "session", None)
                                       or getattr(self.controller, "last_session", None)))}))
        except TaskError as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError, OSError, UnicodeError):
            return self._error("setup_request_invalid", "finish or skip the current setup section")

    def _test_route(self):
        binding = self._binding()
        if not binding.get("bound") or binding.get("pending"):
            raise TaskError("setup_binding_confirmation_required", "confirm the core administrator private window first")
        platform_id = binding.get("platform_id")
        account_id = binding.get("account_id")
        participant_id = binding.get("participant_id")
        if not all(type(value) is str and value.isdigit() for value in (account_id, participant_id)):
            raise TaskError("setup_binding_invalid", "the core administrator window has incomplete OneBot identity")
        if self._active_mode() == "multiple":
            settings = getattr(self.controller, "settings", None)
            if settings is None or not any((target.platform_id, target.account_id, target.participant_id)
                                           == (platform_id, account_id, participant_id)
                                           for target in getattr(settings, "targets", ())):
                raise TaskError("setup_core_window_not_configured",
                                "add this private window to the shared host before testing active delivery")
        platform = self.controller.context.get_platform_inst(platform_id)
        if platform is None:
            raise TaskError("setup_platform_unavailable", "the bound platform instance is not loaded")
        client = platform.get_client()
        api = getattr(getattr(client, "_api", None), "_wsr_api", None)
        if (api is None or not callable(getattr(api, "call_action", None))
                or not getattr(client, "_wsr_api_clients", {}).get(account_id)):
            raise TaskError("setup_account_unavailable", "the bound Bot account has no active OneBot reverse connection")
        return api, account_id, participant_id

    @staticmethod
    def _acknowledged(result) -> bool:
        if not isinstance(result, dict):
            return False
        message_id = result.get("message_id")
        if isinstance(message_id, bool) or not isinstance(message_id, (str, int)):
            return False
        try:
            return int(message_id) > 0 and str(int(message_id)) == str(message_id)
        except (TypeError, ValueError):
            return False

    async def proactive_test(self):
        async with self._test_lock:
            return await self._run_proactive_test()

    async def _run_proactive_test(self):
        try:
            self._admin()
            await self._body(set())
            saved = self.progress.read()
            if saved["ready"]:
                return self._response(Outcome.success({"state": "delivered", "ready": True,
                                                       "replay_allowed": False}))
            if saved["proactive_test"] is not None:
                raise TaskError("setup_test_non_replayable",
                                "the proactive test already started; its result cannot be replayed")
            api, account_id, participant_id = self._test_route()
            active = await self.controller.start()
            if active.failure is not None:
                raise TaskError(active.failure.code, active.failure.reason)
            started = datetime.now(timezone.utc).isoformat()
            try:
                state = self.progress.begin_proactive_test(attempt_id=uuid4().hex, started_at=started)
            except ValueError as error:
                raise TaskError("setup_test_non_replayable", str(error)) from error
            try:
                result = await api.call_action("send_private_msg", self_id=int(account_id),
                                               user_id=int(participant_id), message=TEST_MESSAGE)
                delivered = self._acknowledged(result)
            except Exception:
                delivered = False
            state = self.progress.finish_proactive_test(delivered=delivered,
                                                        finished_at=datetime.now(timezone.utc).isoformat())
            return self._response(Outcome.success({"state": state["proactive_test"]["state"],
                "ready": state["ready"], "replay_allowed": False}))
        except TaskError as error:
            return self._error(error.code, str(error))
        except (ValueError, TypeError, KeyError, OSError, UnicodeError):
            return self._error("setup_test_failed", "the active message test could not be started")

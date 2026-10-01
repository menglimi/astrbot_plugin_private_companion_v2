"""Authenticated model routing, TTS bindings and native image controls."""

import asyncio
import inspect
import json
import re
from copy import deepcopy
from pathlib import Path
from time import monotonic

from astrbot.api.web import request
from companion_v2.conversation.reply_management import ReplyManagement
from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.model_gateway.management import ModelManagement

from .management_identity import dashboard_operator
from .native_extensions.image_settings import read_image_settings, write_image_settings
from .native_extensions.images import IMAGE_ACTIONS
from .reply_api import ReplyWebAPI
from .token_sources import read_token_sources
from .voice import _read_audio


PREFIX = "/astrbot_plugin_private_companion_v2/model"
VOICE_FIELDS = {"zh": "voice_zh_provider_id", "ja": "voice_ja_provider_id", "en": "voice_en_provider_id"}
VOICE_CHANGES = frozenset((*VOICE_FIELDS.values(), "voice_timeout_seconds"))
LANGUAGES = {"zh": "中文", "ja": "日语", "en": "英语"}
IMAGE_SETTINGS = "model_image_routes.json"
TTS_PROVIDER_SYSTEM_KEYS = frozenset({"id", "provider", "type", "provider_type", "enable", "hint", "provider_source_id"})
PROVIDER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}")


def _is_tts_provider_config(config):
    return isinstance(config, dict) and str(config.get("provider_type") or "").strip().lower() in {"text_to_speech", "tts"}


def _is_secret_key(key):
    lowered = str(key).lower()
    return any(word in lowered for word in ("api_key", "secret", "token", "password", "subscription_key"))


def _field_type(default, meta):
    declared = str(meta.get("type") or "").lower()
    if declared in {"bool", "int", "float", "string", "object", "list"}:
        return declared
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int) and not isinstance(default, bool):
        return "int"
    if isinstance(default, float):
        return "float"
    return "string"


def _schema_fields(source, field_metadata):
    fields = []
    for key, default in source.items():
        if key in TTS_PROVIDER_SYSTEM_KEYS:
            continue
        meta = field_metadata.get(key) if isinstance(field_metadata.get(key), dict) else {}
        raw_options = meta.get("options") if isinstance(meta.get("options"), list) else []
        labels = meta.get("labels") if isinstance(meta.get("labels"), list) else []
        options = []
        for index, option in enumerate(raw_options):
            if isinstance(option, dict):
                value = str(option.get("value", "") or "")
                options.append({"value": value, "label": str(option.get("label") or value)})
            else:
                label = str(labels[index]) if index < len(labels) and labels[index] else str(option or "")
                options.append({"value": str(option or ""), "label": label})
        fields.append({"key": key, "type": _field_type(default, meta),
            "label": str(meta.get("description") or key)[:120], "hint": str(meta.get("hint") or "")[:300],
            "options": options, "secret": _is_secret_key(key), "default": default})
    return fields


def _document(raw, keys, *, limit=32000):
    if len(raw) > limit:
        raise ValueError("model request is too large")

    def unique(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError("duplicate field")
            data[key] = value
        return data

    def finite(_value):
        raise ValueError("nonfinite value")

    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=finite)
    if type(data) is not dict or set(data) != keys:
        raise ValueError("unexpected or missing model fields")
    return data


class ModelWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [
            (PREFIX + "/catalog", self.catalog, ["GET"], "Read AstrBot text provider catalog"),
            (PREFIX, self.status, ["GET"], "Read model task configuration"),
            (PREFIX + "/maintenance", self.maintenance, ["GET"], "Read role-level token and cache diagnostics"),
            (PREFIX + "/test/storage", self.storage_test, ["POST"], "Run read-only SQLite integrity diagnostics"),
            (PREFIX + "/configure", self.configure, ["POST"], "Save one model task configuration"),
            (PREFIX + "/test", self.test, ["POST"], "Probe one registered text provider"),
            (PREFIX + "/voice", self.voice, ["GET"], "Read live TTS bindings"),
            (PREFIX + "/voice/save", self.voice_save, ["POST"], "Save live TTS bindings"),
            (PREFIX + "/voice/test", self.voice_test, ["POST"], "Probe one loaded TTS provider"),
            (PREFIX + "/tts/providers", self.tts_providers, ["GET"], "Read manageable TTS provider configs"),
            (PREFIX + "/tts/providers/create", self.tts_provider_create, ["POST"], "Create one TTS provider from a template"),
            (PREFIX + "/tts/providers/update", self.tts_provider_update, ["POST"], "Update one TTS provider config"),
            (PREFIX + "/tts/providers/clone", self.tts_provider_clone, ["POST"], "Clone one TTS provider for a language"),
            (PREFIX + "/image", self.image, ["GET"], "Read native image actions"),
            (PREFIX + "/image/save", self.image_save, ["POST"], "Save native image switches"),
            (PREFIX + "/image/test", self.image_test, ["POST"], "Check native image registration"),
            (PREFIX + "/image/config", self.image_config, ["GET"], "Read the image extension route configuration"),
            (PREFIX + "/image/config/save", self.image_config_save, ["POST"], "Save the image extension route configuration"),
        ]

    async def catalog(self):
        """Read the live AstrBot text provider list without requiring V2 runtime."""
        from .web_api import outcome_response
        try:
            username = request.username
            if type(username) is not str or not username.strip() or username.startswith("api_key:"):
                raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
            if request.query:
                raise TaskError("model_request_invalid", "model catalog does not accept query overrides")
            context = self.controller.context
            providers = []
            for provider in list(context.get_all_providers() or []):
                meta = provider.meta() if callable(getattr(provider, "meta", None)) else None
                identifier = str(getattr(meta, "id", "") or getattr(provider, "id", "") or "").strip()
                if not identifier:
                    continue
                name = str(getattr(meta, "name", "") or getattr(meta, "label", "") or identifier)
                capabilities = sorted({"text", "conversation.reply"})
                providers.append({"id": identifier, "name": name[:120], "capabilities": capabilities,
                                  "loaded": True, "source": "astrbot"})
            configured = getattr(getattr(context, "provider_manager", None), "providers_config", None) or []
            configured_ids = {str(item.get("id")) for item in configured if isinstance(item, dict)}
            for item in providers:
                item["configured"] = item["id"] in configured_ids
            providers.sort(key=lambda item: (not item["configured"], item["name"].lower(), item["id"]))
            return {"status": "ok", "data": {"providers": providers, "source": "astrbot.provider_manager"}}
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except Exception:
            return outcome_response(Outcome.failed("model_catalog_unavailable", "AstrBot provider list is unavailable"))

    def _authorized(self):
        controller = self.controller
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
        if request.query:
            raise TaskError("model_request_invalid", "model routes do not accept target overrides")
        if controller._terminated:
            raise TaskError("staging_host_terminated", "plugin is stopped")
        session = controller.session or controller.last_session
        if session is None or controller.runtime is None:
            raise TaskError("staging_not_initialized", "load the V2 profile first")
        operator = dashboard_operator(controller.runtime, username, at=controller.now())
        manager = ModelManagement(session.application, session.profile.target)
        status = require(manager.status(operator))
        return session, operator, manager, status

    @staticmethod
    def _response(result):
        from .web_api import outcome_response
        return outcome_response(result)

    async def _run(self, action):
        try:
            data = None
            if action == "configure":
                data = _document(await request.body(),
                    {"kind", "operation_key", "edit_token", "changes", "reset"})
            async with self.controller._control_lock:
                _session, operator, manager, status = self._authorized()
                result = (Outcome.success(status) if action == "status" else manager.maintenance(operator)
                          if action == "maintenance" else manager.configure(operator, data))
            if action == "maintenance" and result.is_success:
                payload = dict(result.unwrap())
                payload["external_token_sources"] = read_token_sources()
                result = Outcome.success(payload)
            return self._response(result)
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid UTF-8 model request"))

    async def status(self):
        return await self._run("status")

    async def maintenance(self):
        return await self._run("maintenance")

    async def storage_test(self):
        try:
            data = _document(await request.body(), {"check"}, limit=1024)
            if data["check"] != "sqlite":
                raise ValueError("unsupported storage check")
            async with self.controller._control_lock:
                _session, operator, manager, _status = self._authorized()
                started = monotonic()
                result = await asyncio.to_thread(manager.check_storage, operator)
                if result.is_success:
                    result = Outcome.success({**result.unwrap(),
                        "elapsed_ms": round((monotonic() - started) * 1000)})
                return self._response(result)
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid storage check request"))

    async def configure(self):
        return await self._run("configure")

    async def test(self):
        try:
            data = _document(await request.body(), {"provider_id"}, limit=1024)
            provider_id = data["provider_id"]
            if type(provider_id) is not str or not provider_id or len(provider_id) > 128:
                raise ValueError("invalid provider id")
            async with self.controller._control_lock:
                _session, _operator, _manager, status = self._authorized()
                if provider_id not in {item["id"] for item in status["providers"]}:
                    raise TaskError("model_provider_unavailable", "provider has no V2 adapter")
                base = getattr(self.controller, "controller", self.controller)
                model = next((item for item in (base.session or base.last_session).models
                              if item.provider_id == provider_id), None)
                if model is None:
                    raise TaskError("model_provider_unavailable", "provider has no live V2 adapter")
            started = monotonic()
            try:
                await asyncio.wait_for(model.probe(), timeout=30)
                result, code = "ok", ""
            except asyncio.TimeoutError:
                result, code = "unknown", "model_probe_timeout"
            except Exception:
                result, code = "unknown", "model_probe_failed"
            async with self.controller._control_lock:
                self._authorized()
                base = getattr(self.controller, "controller", self.controller)
                if model not in (base.session or base.last_session).models:
                    raise TaskError("model_provider_changed", "provider changed during probe")
            return self._response(Outcome.success({"provider_id": provider_id, "status": result,
                "latency_ms": round((monotonic() - started) * 1000), "code": code}))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid probe request"))

    def _voice_projection(self, session, operator):
        status = require(ReplyManagement(session.application, session.profile.target).status(operator))
        settings = status["settings"]
        catalog = ReplyWebAPI(self.controller)._tts_catalog()
        return {"languages": [{"k": lang, "n": label, "bind": settings[field]}
                              for lang, label in LANGUAGES.items() for field in (VOICE_FIELDS[lang],)],
                "providers": catalog["providers"], "catalog_state": catalog["state"],
                "timeout_seconds": settings["voice_timeout_seconds"],
                "voice_enabled": settings["voice_enabled"], "edit_token": status["edit_token"]}

    async def voice(self):
        try:
            async with self.controller._control_lock:
                session, operator, _manager, _status = self._authorized()
                return self._response(Outcome.success(self._voice_projection(session, operator)))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))

    async def voice_save(self):
        try:
            data = _document(await request.body(), {"operation_key", "edit_token", "changes"})
            changes = data["changes"]
            if type(changes) is not dict or not changes or set(changes) - VOICE_CHANGES:
                raise ValueError("invalid voice changes")
            for name, value in changes.items():
                if name == "voice_timeout_seconds":
                    if type(value) is not int or not 1 <= value <= 120:
                        raise ValueError("invalid voice timeout")
                elif type(value) is not str or len(value) > 128:
                    raise ValueError("invalid voice binding")
            async with self.controller._control_lock:
                session, operator, _manager, _status = self._authorized()
                saved = require(ReplyManagement(session.application, session.profile.target).configure(operator, data))
                return self._response(Outcome.success({**self._voice_projection(session, operator),
                    "replayed": saved["replayed"]}))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid voice settings request"))

    async def voice_test(self):
        try:
            data = _document(await request.body(), {"provider_id", "language"}, limit=1024)
            provider_id = data["provider_id"]
            language = data["language"]
            if (type(provider_id) is not str or not provider_id or len(provider_id) > 128
                    or type(language) is not str or language not in LANGUAGES):
                raise ValueError("invalid TTS provider id")
            async with self.controller._control_lock:
                session, operator, _manager, _status = self._authorized()
                projection = self._voice_projection(session, operator)
                if provider_id not in {p["id"] for p in projection["providers"]}:
                    raise TaskError("model_voice_provider_unavailable", "TTS provider is not loaded")
                provider = self.controller.context.get_provider_by_id(provider_id)
                if (provider is None or provider not in self.controller.context.get_all_tts_providers()
                        or not callable(getattr(provider, "get_audio", None))):
                    raise TaskError("model_voice_provider_unavailable", "TTS provider is not available")
                timeout = projection["timeout_seconds"]
            started = monotonic()

            async def synthesize():
                method = provider.get_audio
                sample = {"zh": "你好。", "ja": "こんにちは。", "en": "Hello."}[language]
                result = method(sample) if inspect.iscoroutinefunction(method) else await asyncio.to_thread(method, sample)
                path = await result if inspect.isawaitable(result) else result
                if isinstance(path, (list, tuple)):
                    path = path[0] if path else None
                return await asyncio.to_thread(_read_audio, path)

            try:
                audio = await asyncio.wait_for(synthesize(), timeout=timeout)
                result, code = ("ok", "") if audio is not None else ("unavailable", "model_voice_audio_invalid")
            except asyncio.TimeoutError:
                result, code = "unknown", "model_voice_probe_timeout"
            except Exception:
                result, code = "unknown", "model_voice_probe_failed"
            async with self.controller._control_lock:
                self._authorized()
                if provider is not self.controller.context.get_provider_by_id(provider_id):
                    raise TaskError("model_voice_provider_changed", "TTS provider changed during probe")
            return self._response(Outcome.success({"provider_id": provider_id, "status": result,
                "latency_ms": round((monotonic() - started) * 1000), "code": code}))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid voice probe request"))

    def _image_projection(self):
        registry = self.controller.native_extensions
        path = Path(self.controller.data_root) / IMAGE_SETTINGS
        enabled = registry.image_enabled if registry is not None else read_image_settings(path)
        declarations = registry.declarations() if registry is not None else ()
        base = getattr(self.controller, "controller", self.controller)
        session = base.session or base.last_session
        external = getattr(getattr(session, "application", None), "external", None)
        rows = []
        for action in sorted(IMAGE_ACTIONS):
            owners = [item for item in declarations if item.descriptor.tool.action == action]
            owner = owners[0] if len(owners) == 1 else None
            current = bool(owner and registry.current_declaration(owner.host_tool_id) == owner)
            registered = bool(owner and external and external.providers.get(action)
                              and external.providers[action].descriptor == owner.descriptor)
            rows.append({"action": action, "enabled": enabled[action],
                         "owner": owner.descriptor.package.extension_id if owner else "",
                         "provider_id": owner.descriptor.binding.provider if owner else "",
                         "loaded": bool(owner), "current": current, "registered": registered,
                         "state": "disabled" if not enabled[action] else
                                  "ready" if current and registered else "unavailable"})
        return {"actions": rows, "enabled": dict(enabled),
                "authorization": "checked_for_each_invocation"}

    async def image(self):
        try:
            async with self.controller._control_lock:
                self._authorized()
                return self._response(Outcome.success(self._image_projection()))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))

    async def image_save(self):
        try:
            data = _document(await request.body(), {"enabled"}, limit=1024)
            enabled = data["enabled"]
            if type(enabled) is not dict or set(enabled) != IMAGE_ACTIONS or any(
                    type(value) is not bool for value in enabled.values()):
                raise ValueError("invalid native image switches")
            async with self.controller._control_lock:
                self._authorized()
                registry = self.controller.native_extensions
                write_image_settings(Path(self.controller.data_root) / IMAGE_SETTINGS, enabled)
                if registry is not None:
                    registry.set_image_enabled(enabled)
                return self._response(Outcome.success(self._image_projection()))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid image settings request"))

    async def image_test(self):
        try:
            data = _document(await request.body(), {"action"}, limit=1024)
            if type(data["action"]) is not str or data["action"] not in IMAGE_ACTIONS:
                raise ValueError("invalid native image action")
            async with self.controller._control_lock:
                self._authorized()
                row = next(item for item in self._image_projection()["actions"] if item["action"] == data["action"])
                return self._response(Outcome.success({**row, "check": "registration_only"}))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid image check request"))

    # ---------- TTS provider management (AstrBot ProviderManager is the owner) ----------
    def _provider_manager(self):
        manager = getattr(self.controller.context, "provider_manager", None)
        if manager is None:
            raise TaskError("tts_provider_unsupported", "this AstrBot build has no provider manager")
        return manager

    def _tts_templates(self):
        from astrbot.core.config.default import CONFIG_METADATA_2
        provider_metadata = CONFIG_METADATA_2.get("provider_group", {}).get("metadata", {}).get("provider", {})
        field_metadata = provider_metadata.get("items", {}) if isinstance(provider_metadata.get("items"), dict) else {}
        source_map = provider_metadata.get("config_template", {}) if isinstance(provider_metadata.get("config_template"), dict) else {}
        templates = {}
        for label, source in source_map.items():
            if not _is_tts_provider_config(source) or not str(source.get("type") or "").strip():
                continue
            provider_type = str(source["type"]).strip()
            templates[provider_type] = {"label": str(label)[:80], "type": provider_type,
                "provider": str(source.get("provider") or "")[:80],
                "fields": _schema_fields(source, field_metadata)}
        return templates

    def _tts_provider_payload(self):
        manager = self._provider_manager()
        templates = self._tts_templates()
        loaded = set()
        try:
            for provider in self.controller.context.get_all_tts_providers():
                identifier = provider.meta().id
                if type(identifier) is str and identifier:
                    loaded.add(identifier)
        except Exception:
            loaded = set()
        items = []
        for config in list(getattr(manager, "providers_config", None) or []):
            if not _is_tts_provider_config(config):
                continue
            provider_type = str(config.get("type") or "").strip()
            template = templates.get(provider_type) or {"label": provider_type, "fields": []}
            merged = config
            merger = getattr(manager, "get_merged_provider_config", None)
            if callable(merger):
                try:
                    merged = merger(config) or config
                except Exception:
                    merged = config
            known = {field["key"] for field in template["fields"]}
            fields = []
            for field in template["fields"]:
                value = merged.get(field["key"])
                entry = dict(field)
                if field["secret"]:
                    entry.update({"value": "", "set": bool(value)})
                else:
                    entry.update({"value": value, "set": value is not None and value != ""})
                fields.append(entry)
            for key, value in sorted(merged.items()):
                if key in known or key in TTS_PROVIDER_SYSTEM_KEYS:
                    continue
                fields.append({"key": key, "type": _field_type(value, {}), "label": key, "hint": "",
                    "options": [], "secret": _is_secret_key(key), "default": None,
                    **({"value": "", "set": bool(value)} if _is_secret_key(key) else {"value": value, "set": True})})
            items.append({"id": str(config.get("id") or "")[:128], "type": provider_type,
                "label": str(template["label"]), "enable": config.get("enable") is True,
                "loaded": str(config.get("id") or "") in loaded, "fields": fields})
        items.sort(key=lambda item: (not item["enable"], not item["loaded"], item["id"]))
        return {"items": items, "templates": sorted(templates.values(), key=lambda template: template["label"])}

    def _coerce_tts_value(self, field, value):
        ftype = field["type"]
        if ftype == "bool":
            if type(value) is bool:
                return value
            return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
        if ftype in {"int", "float"}:
            text = str(value if value is not None else "").strip()
            if not text:
                raise TaskError("tts_provider_invalid", field["label"] + " is required")
            try:
                return int(text) if ftype == "int" else float(text)
            except ValueError:
                raise TaskError("tts_provider_invalid", field["label"] + " must be a number")
        if ftype in {"object", "list"}:
            text = str(value or "").strip()
            if not text:
                return {} if ftype == "object" else []
            try:
                parsed = json.loads(text)
            except ValueError:
                raise TaskError("tts_provider_invalid", field["label"] + " must be valid JSON")
            if ftype == "object" and not isinstance(parsed, dict):
                raise TaskError("tts_provider_invalid", field["label"] + " must be a JSON object")
            if ftype == "list" and not isinstance(parsed, list):
                raise TaskError("tts_provider_invalid", field["label"] + " must be a JSON list")
            return parsed
        return str(value if value is not None else "")[:12000]

    def _tts_provider_by_id(self, manager, provider_id):
        getter = getattr(manager, "get_provider_config_by_id", None)
        current = deepcopy(getter(provider_id)) if callable(getter) else None
        if not _is_tts_provider_config(current):
            current = next((deepcopy(item) for item in getattr(manager, "providers_config", None) or []
                            if isinstance(item, dict) and str(item.get("id") or "") == provider_id), None)
        if not _is_tts_provider_config(current):
            raise TaskError("tts_provider_missing", "TTS provider not found")
        return current

    async def tts_providers(self):
        try:
            async with self.controller._control_lock:
                self._authorized()
                payload = self._tts_provider_payload()
            return self._response(Outcome.success(payload))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except Exception:
            return self._response(Outcome.failed("tts_provider_failed", "the TTS provider catalog could not be read"))

    async def tts_provider_create(self):
        try:
            data = _document(await request.body(), {"type", "id"}, limit=2048)
            provider_type = str(data["type"] or "").strip()[:80]
            provider_id = str(data["id"] or "").strip()[:80]
            if not PROVIDER_ID_PATTERN.fullmatch(provider_id):
                raise TaskError("tts_provider_invalid", "Provider ID only allows letters, digits, dot, underscore, colon and dash")
            async with self.controller._control_lock:
                self._authorized()
                manager = self._provider_manager()
                template = self._tts_templates().get(provider_type)
                if template is None:
                    raise TaskError("tts_provider_invalid", "unsupported TTS provider type")
                if provider_id in {str(item.get("id") or "") for item in getattr(manager, "providers_config", None) or []}:
                    raise TaskError("tts_provider_exists", "Provider ID already exists")
                config = {field["key"]: field["default"] for field in template["fields"]}
                config.update({"id": provider_id, "type": provider_type, "provider": template["provider"],
                               "provider_type": "text_to_speech", "enable": False})
                creator = getattr(manager, "create_provider", None)
                if not callable(creator):
                    raise TaskError("tts_provider_unsupported", "dynamic provider creation is unavailable")
                await creator(config)
                payload = self._tts_provider_payload()
            return self._response(Outcome.success(payload))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except Exception:
            return self._response(Outcome.failed("tts_provider_failed", "the TTS provider could not be created"))

    async def tts_provider_update(self):
        try:
            data = _document(await request.body(), {"provider_id", "values"}, limit=32768)
            provider_id = str(data["provider_id"] or "").strip()[:128]
            values = data["values"]
            if type(values) is not dict or not values:
                raise ValueError("empty provider update")
            async with self.controller._control_lock:
                self._authorized()
                manager = self._provider_manager()
                current = self._tts_provider_by_id(manager, provider_id)
                template = self._tts_templates().get(str(current.get("type") or "").strip()) or {"fields": []}
                fields = {field["key"]: field for field in template["fields"]}
                fields.setdefault("enable", {"key": "enable", "type": "bool", "label": "enable", "secret": False})
                for key, value in current.items():
                    if key in TTS_PROVIDER_SYSTEM_KEYS or key in fields:
                        continue
                    fields[key] = {"key": key, "type": _field_type(value, {}), "label": key, "secret": _is_secret_key(key)}
                normalized = deepcopy(current)
                for key, value in values.items():
                    field = fields.get(str(key))
                    if field is None:
                        continue
                    if field.get("secret") and (value is None or value == ""):
                        continue
                    normalized[field["key"]] = self._coerce_tts_value(field, value)
                if normalized != current:
                    updater = getattr(manager, "update_provider", None)
                    if not callable(updater):
                        raise TaskError("tts_provider_unsupported", "dynamic provider updates are unavailable")
                    await updater(provider_id, normalized)
                payload = self._tts_provider_payload()
            return self._response(Outcome.success(payload))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid provider update"))
        except Exception:
            return self._response(Outcome.failed("tts_provider_failed", "the TTS provider could not be saved"))

    async def tts_provider_clone(self):
        try:
            data = _document(await request.body(), {"provider_id", "language"}, limit=2048)
            provider_id = str(data["provider_id"] or "").strip()[:128]
            language = str(data["language"] or "").strip()
            if language not in {"zh", "ja", "en"}:
                raise ValueError("invalid clone language")
            async with self.controller._control_lock:
                self._authorized()
                manager = self._provider_manager()
                source = self._tts_provider_by_id(manager, provider_id)
                ids = {str(item.get("id") or "") for item in getattr(manager, "providers_config", None) or []}
                base = re.sub(r"[^A-Za-z0-9._:-]+", "-", provider_id).strip("._:-") or "tts"
                candidate = base[:72] + "-" + language
                index = 1
                while candidate in ids:
                    index += 1
                    candidate = base[:72] + "-" + language + "-" + str(index)
                config = deepcopy(source)
                config["id"] = candidate
                config["enable"] = False
                creator = getattr(manager, "create_provider", None)
                if not callable(creator):
                    raise TaskError("tts_provider_unsupported", "dynamic provider creation is unavailable")
                await creator(config)
                payload = {**self._tts_provider_payload(), "created_id": candidate}
            return self._response(Outcome.success(payload))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid provider clone"))
        except Exception:
            return self._response(Outcome.failed("tts_provider_failed", "the TTS provider could not be cloned"))

    # ---------- image extension route configuration (owned by the extension) ----------
    def _image_extension_api(self):
        registry = self.controller.native_extensions
        api = registry.image_extension_api() if registry is not None else None
        if api is None:
            raise TaskError("model_image_config_unavailable", "the image extension is not loaded")
        return api

    async def image_config(self):
        try:
            async with self.controller._control_lock:
                self._authorized()
                api = self._image_extension_api()
                data = api.native_configuration()
            if not isinstance(data, dict) or type(data.get("revision")) is not str or not isinstance(data.get("sections"), dict):
                raise TaskError("model_image_config_failed", "unexpected image configuration payload")
            return self._response(Outcome.success(data))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except Exception:
            return self._response(Outcome.failed("model_image_config_failed", "the image configuration could not be read"))

    async def image_config_save(self):
        try:
            # 路线配置里现在有说明性文本（guidance 六键，扩展给的单键上限是 4000 字），
            # 而保存提交的是整份路线数组，所以请求体比其它配置大得多：32 条路线写满
            # 说明时能到几百 KB。这是传输闸门，不是业务规则——业务边界仍然只有扩展
            # 的 image_config_limits 一处。页面在发出前用同一个数字先挡一次
            # （pages/陪伴小屋/models-page.js 的 IMAGE_SAVE_LIMIT），改这里要一起改。
            data = _document(await request.body(), {"revision", "changes"}, limit=262144)
            revision, changes = data["revision"], data["changes"]
            if type(revision) is not str or not 8 <= len(revision) <= 128:
                raise ValueError("invalid revision")
            if type(changes) is not dict or not changes:
                raise ValueError("empty configuration changes")
            async with self.controller._control_lock:
                self._authorized()
                api = self._image_extension_api()
                try:
                    result = api.save_native_configuration(revision, changes)
                except Exception as error:
                    text = str(error)
                    if "configuration_conflict" in text:
                        raise TaskError("model_image_config_conflict", "the configuration changed elsewhere; refresh and retry")
                    if "configuration_busy" in text:
                        raise TaskError("model_image_config_busy", "the image extension is executing tasks; retry later")
                    if "invalid_configuration" in text:
                        raise TaskError("model_image_config_invalid", "the image extension rejected the values")
                    raise TaskError("model_image_config_failed", "the image extension rejected the save")
            if not isinstance(result, dict) or type(result.get("revision")) is not str:
                raise TaskError("model_image_config_failed", "unexpected save result")
            return self._response(Outcome.success(result))
        except TaskError as error:
            return self._response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
            return self._response(Outcome.failed("model_request_invalid", "invalid image configuration request"))
        except Exception:
            return self._response(Outcome.failed("model_image_config_failed", "the image configuration could not be saved"))

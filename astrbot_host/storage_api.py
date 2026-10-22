"""Dashboard inventory, retention and data-location controls for V2 storage."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from astrbot.api.web import request
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.storage.management import cleanup_backups, cleanup_plan, inventory, retention_policy

from .backup_api import MAX_REQUEST_BYTES
from .management_identity import dashboard_operator
from .storage_location import (finish_backup_relocation, relocate_backup_storage,
                               selected_backup_directory, selected_backup_root, selected_root)


PREFIX = "/astrbot_plugin_private_companion/storage"


class StorageWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.status, ["GET"], "Read V2 storage usage and retention"),
                (PREFIX, self.update, ["POST"], "Save V2 storage location and cleanup policy")]

    def _operator(self):
        username = request.username
        if (type(username) is not str or not username.strip() or username != username.strip()
                or username.startswith("api_key:") or len(username) > 128):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard as an administrator")
        runtime = getattr(self.controller, "runtime", None)
        if runtime is not None:
            dashboard_operator(runtime, username, at=self.controller.now())

    def _backup_context(self, selected_path):
        controller = self.controller
        runtime = getattr(controller, "runtime", None)
        installation_id = getattr(runtime, "installation_id", None)
        if type(installation_id) is not str:
            settings = getattr(controller, "settings", None)
            installation_id = getattr(settings, "installation_id", None)
        if type(installation_id) is not str:
            configuration = getattr(controller, "configuration", None)
            scope = getattr(configuration, "scope", None)
            installation_id = getattr(scope, "installation_id", None)
        plugin_root = Path(controller.data_root).resolve()
        if runtime is not None:
            runtime_root = Path(runtime.data_root).resolve()
        else:
            profile_root = getattr(controller, "profile_root", None)
            runtime_root = (Path(profile_root) / "runtime").resolve() if profile_root is not None else plugin_root
        backup_directory = selected_backup_directory(
            runtime_root, selected_path, installation_id, plugin_root=plugin_root)
        backup_root = selected_backup_root(plugin_root, selected_path)
        return runtime_root, installation_id, backup_directory, backup_root

    @staticmethod
    def _body(raw):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = value
            return result

        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))

    def _status(self):
        controller = self.controller
        configuration = controller.config if isinstance(controller.config, dict) else {}
        policy = retention_policy(configuration)
        default_root = Path(getattr(controller, "default_data_root", controller.data_root)).resolve()
        storage = configuration.get("storage", {})
        selected = storage.get("path", "") if isinstance(storage, dict) else ""
        selected_backup = storage.get("backup_path", "") if isinstance(storage, dict) else ""
        desired = selected_root(default_root, selected)
        active = Path(controller.data_root).resolve()
        _, installation_id, backup_directory, backup_root = self._backup_context(selected_backup)
        active_inventory = inventory(active, backup_directory=backup_root or backup_directory)
        desired_inventory = active_inventory if desired == active else inventory(desired)
        plan = cleanup_plan(active, **policy, backup_directory=backup_directory,
                            installation_id=installation_id)
        return {"active_root": str(active), "selected_path": selected,
                "desired_root": str(desired), "restart_required": desired != active,
                "selected_backup_path": selected_backup, "backup_root": str(backup_directory),
                "inventory": active_inventory,
                "destination_free_bytes": desired_inventory["free_bytes"],
                "policy": policy, "cleanup_preview": plan}

    async def status(self):
        from .web_api import outcome_response
        try:
            async with self.controller._control_lock:
                self._operator()
                return {"status": "ok", "data": self._status()}
        except (TaskError, ValueError) as error:
            code = error.code if isinstance(error, TaskError) else "storage_settings_invalid"
            return outcome_response(Outcome.failed(code, str(error)))
        except OSError:
            return outcome_response(Outcome.failed("storage_location_unavailable",
                                                   "the selected V2 data location is not available"))

    async def update(self):
        from .web_api import outcome_response
        try:
            raw = await request.body()
            if len(raw) > MAX_REQUEST_BYTES or request.query:
                raise ValueError("request too large or query provided")
            document = self._body(raw)
            if type(document) is not dict:
                raise ValueError("object required")
            action = document.get("action")
            async with self.controller._control_lock:
                self._operator()
                if action == "clean" and set(document) == {"action"}:
                    policy = retention_policy(self.controller.config)
                    storage = self.controller.config.get("storage", {}) if isinstance(self.controller.config, dict) else {}
                    selected_backup = storage.get("backup_path", "") if isinstance(storage, dict) else ""
                    runtime_root, installation_id, backup_directory, _ = self._backup_context(selected_backup)
                    result = cleanup_backups(runtime_root, **policy, backup_directory=backup_directory,
                                             installation_id=installation_id)
                    return {"status": "ok", "data": {**self._status(), "cleanup_result": result}}
                if action != "save" or set(document) != {
                    "action", "path", "backup_path", "retention_count", "retention_days"
                }:
                    raise ValueError("unexpected fields")
                selected = document["path"]
                selected_backup = document["backup_path"]
                count, days = document["retention_count"], document["retention_days"]
                if (type(selected) is not str or type(count) is not int or type(days) is not int
                        or type(selected_backup) is not str or len(selected_backup) > 2048
                        or not 1 <= count <= 200 or not 1 <= days <= 3650):
                    raise ValueError("invalid storage settings")
                default_root = Path(getattr(self.controller, "default_data_root", self.controller.data_root)).resolve()
                selected_root(default_root, selected)
                save = getattr(self.controller, "save_plugin_config", None)
                if not callable(save):
                    raise TaskError("storage_config_save_unavailable", "plugin configuration cannot be saved")
                previous = deepcopy(dict(self.controller.config))
                candidate = deepcopy(previous)
                storage = candidate.get("storage")
                if not isinstance(storage, dict):
                    storage = {}
                previous_storage = previous.get("storage", {})
                previous_backup = previous_storage.get("backup_path", "") if isinstance(previous_storage, dict) else ""
                runtime_root, installation_id, _, _ = self._backup_context(previous_backup)
                transfers = relocate_backup_storage(Path(self.controller.data_root), previous_backup,
                                                     selected_backup.strip())
                candidate["storage"] = {**storage, "path": selected.strip(),
                                        "backup_path": selected_backup.strip(),
                                        "retention_count": count, "retention_days": days}
                try:
                    save(candidate)
                except Exception as error:
                    raise TaskError("storage_config_save_failed", "storage settings could not be saved") from error
                next_backup_directory = selected_backup_directory(
                    runtime_root, selected_backup, installation_id,
                    plugin_root=Path(self.controller.data_root))
                if getattr(self.controller, "runtime", None) is not None:
                    self.controller.runtime.backup_directory = next_backup_directory
                if transfers:
                    try:
                        finish_backup_relocation(transfers)
                    except OSError:
                        pass
                return {"status": "ok", "data": self._status()}
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, UnicodeError, RecursionError, TypeError, KeyError):
            return outcome_response(Outcome.failed("storage_request_invalid", "storage settings are invalid"))
        except OSError:
            return outcome_response(Outcome.failed("storage_operation_failed", "storage files could not be read or updated"))

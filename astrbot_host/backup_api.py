"""Authenticated whole-installation backup and restore for the pinned V2 profile.

Restoring is deliberately a two-phase operation: the request is staged, and the
host applies it on the next start before the store is opened. See
``companion_v2/storage/backup.py`` for why the live connection is never rebuilt.
"""

import json

from astrbot.api.web import request
from companion_v2.execution.models import TaskError
from companion_v2.foundation.outcome import Outcome
from companion_v2.storage.backup import (
    BACKUP_FORMAT, PENDING_FILENAME, InstallationBackup, apply_pending, current_schema_version,
)
from companion_v2.storage.management import retention_policy

from .management_identity import dashboard_operator


PREFIX = "/astrbot_plugin_private_companion/backup"
MAX_REQUEST_BYTES = 65536


class BackupWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.listing, ["GET"], "List completed V2 installation snapshots"),
                (PREFIX + "/create", self.create, ["POST"], "Write a verified snapshot of this installation"),
                (PREFIX + "/inspect", self.inspect, ["GET"], "Verify one snapshot without restoring it"),
                (PREFIX + "/restore/preview", self.preview, ["GET"], "Show what restoring one snapshot would replace"),
                (PREFIX + "/restore", self.restore, ["POST"], "Stage a restore; the host applies it on restart"),
                (PREFIX + "/pending", self.pending, ["GET"], "Report a restore waiting for a restart")]

    @staticmethod
    def _query(allowed):
        keys = set(request.query.keys())
        if keys - set(allowed) or any(len(request.query.getlist(key)) != 1 for key in keys):
            raise ValueError()
        return {key: request.query.get(key) for key in allowed if key in request.query}

    @staticmethod
    def _body(raw, allowed):
        def unique(pairs):
            values = {}
            for key, value in pairs:
                if key in values:
                    raise ValueError()
                values[key] = value
            return values
        arguments = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if type(arguments) is not dict or set(arguments) != set(allowed):
            raise ValueError()
        return arguments

    async def _run(self, method, arguments):
        """Backups are installation-scoped, so they need an operator but no target."""
        from .web_api import outcome_response
        controller = self.controller
        async with controller._control_lock:
            try:
                if controller._terminated:
                    raise TaskError("staging_host_terminated", "plugin is stopped")
                username = request.username
                if type(username) is not str or not username.strip():
                    raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
                session = controller.session or controller.last_session
                if session is None or controller.runtime is None:
                    raise TaskError("staging_not_initialized", "load the explicit V2 profile before managing backups")
                dashboard_operator(controller.runtime, username, at=controller.now())
                backup = InstallationBackup(controller.runtime, now=controller.now,
                                            **retention_policy(controller.config))
                result = getattr(backup, method)(**arguments)
                # 还原预览与执行都带上「这一步会影响谁」。还原是整根替换，
                # 多目标下同时替换该安装下所有目标的资料；用户最容易误以为
                # 「只还原我当前看的这个角色」。
                if method in ("preview_restore", "restore") and result.is_success:
                    document = result.unwrap()
                    if isinstance(document, dict):
                        result = Outcome.success({**document, "scope": self._installation_scope()})
                return outcome_response(result)
            except TaskError as error:
                return outcome_response(Outcome.failed(error.code, str(error)))
            except (TypeError, ValueError, KeyError):
                return outcome_response(Outcome.failed("backup_request_invalid", "invalid backup arguments"))

    def _installation_scope(self):
        """这次还原覆盖的目标与角色数量。按运行档的形状判，不按模式名猜。"""
        settings = getattr(self.controller, "settings", None)
        targets = getattr(settings, "all_targets", None)
        if targets is not None:
            personas = getattr(settings, "personas", ()) or ()
            return {"mode": "multi", "targets": len(targets),
                    "roles": len({(getattr(item, "bot_id", None), getattr(item, "role_id", None)) for item in personas}),
                    "restart_required": True}
        return {"mode": "single", "targets": 1,
                "roles": 1 if getattr(settings, "role_id", None) else 0, "restart_required": True}

    async def listing(self):
        from .web_api import outcome_response
        try:
            self._query([])
        except ValueError:
            return outcome_response(Outcome.failed("backup_request_invalid", "invalid backup query"))
        return await self._run("listing", {})

    async def pending(self):
        from .web_api import outcome_response
        try:
            self._query([])
        except ValueError:
            return outcome_response(Outcome.failed("backup_request_invalid", "invalid backup query"))
        return await self._run("pending", {})

    async def create(self):
        from .web_api import outcome_response
        try:
            raw = await request.body()
            if len(raw) > MAX_REQUEST_BYTES or request.query:
                raise ValueError()
            arguments = self._body(raw, {"note"}) if raw else {"note": ""}
        except (ValueError, UnicodeError, RecursionError):
            return outcome_response(Outcome.failed("backup_request_invalid", "invalid backup note"))
        return await self._run("create", arguments)

    def _snapshot_id(self):
        query = self._query(["snapshot_id"])
        snapshot_id = query.get("snapshot_id", "")
        if not snapshot_id:
            raise ValueError()
        return snapshot_id

    async def inspect(self):
        from .web_api import outcome_response
        try:
            snapshot_id = self._snapshot_id()
        except ValueError:
            return outcome_response(Outcome.failed("backup_request_invalid", "a snapshot id is required"))
        return await self._run("inspect", {"snapshot_id": snapshot_id})

    async def preview(self):
        from .web_api import outcome_response
        try:
            snapshot_id = self._snapshot_id()
        except ValueError:
            return outcome_response(Outcome.failed("backup_request_invalid", "a snapshot id is required"))
        return await self._run("preview_restore", {"snapshot_id": snapshot_id})

    async def restore(self):
        from .web_api import outcome_response
        try:
            raw = await request.body()
            if len(raw) > MAX_REQUEST_BYTES or request.query:
                raise ValueError()
            arguments = self._body(raw, {"snapshot_id", "confirmed_hash"})
        except (ValueError, UnicodeError, RecursionError):
            return outcome_response(Outcome.failed("backup_request_invalid", "invalid restore command"))
        return await self._run("restore", arguments)


def apply_staged_restore(data_root, *, installation_id: str, backup_directory=None) -> dict:
    """Apply a staged restore before the store is opened. No live connection exists.

    This is called from the host's assembly path before ``StorageRuntime.open``,
    which is the only moment the database file can be replaced without orphaning
    the shared connection. It reads the data root's current schema revision from
    the file itself, because the runtime is not available yet. Errors come back as
    a plain document rather than raising, so a failed restore leaves the original
    data root in place and start-up can continue.
    """
    from pathlib import Path
    root = Path(data_root)
    if not (root / PENDING_FILENAME).is_file():
        return {"applied": False, "reason": "no_pending_restore"}
    schema_version = current_schema_version(root)
    if schema_version is None:
        return {"applied": False, "reason": "backup_store_unreadable"}
    return apply_pending(root, installation_id=installation_id, schema_version=schema_version,
                         backup_directory=backup_directory)

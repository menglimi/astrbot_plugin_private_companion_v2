"""Read retained V1 work in the existing migration workspace."""

from pathlib import Path

from astrbot.api.web import request
from companion_v2.foundation.outcome import Outcome
from companion_v2.legacy.archived_work import archived_work_inventory, archived_work_rows


class LegacyArchiveWebAPI:
    def __init__(self, legacy):
        self.legacy = legacy

    def routes(self, prefix):
        return [(prefix + "/archived-work", self.read, ["GET"], "Inspect retained V1 work and delivery history")]

    async def read(self):
        from .web_api import outcome_response
        query = request.query
        if set(query.keys()) - {"archive_id", "area", "table", "offset"}:
            return outcome_response(Outcome.failed("legacy_archive_query_invalid", "归档查询参数无效。"))
        arguments = dict(query.items())
        def work(migration, root, session):
            archive_root = Path(self.legacy.controller.data_root) / "legacy-v1-archives"
            if not arguments:
                return Outcome.success(archived_work_inventory(archive_root))
            return Outcome.success(archived_work_rows(archive_root, arguments.get("archive_id"),
                arguments.get("area"), arguments.get("table"), int(arguments.get("offset", "0"))))
        return await self.legacy._run(work, offload_sync=True)

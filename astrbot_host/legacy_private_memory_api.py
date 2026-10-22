"""Dashboard migration of an exact V1 person into the selected private role."""

import json

from astrbot.api.web import request

from companion_v2.execution.models import digest, encode, stamp
from companion_v2.foundation.outcome import Outcome
from companion_v2.legacy.private_memory import build_private_memory_plan
from companion_v2.memory.private_legacy_import import import_private_memory


class PrivateMemoryMigrationAPI:
    def __init__(self, legacy):
        self.legacy = legacy

    def routes(self, prefix):
        return [(prefix + "/private-memory-plan", self.plan, ["GET"], "Preview V1 person-private historical memory"),
                (prefix + "/private-memory-apply", self.apply, ["POST"], "Import the selected person's V1 private history")]

    def _plan(self, migration, root, session):
        context, _ = self.legacy._data_context(session)
        if getattr(context.scope.kind, "value", context.scope.kind) != "private":
            return Outcome.failed("legacy_private_memory_private_target_required", "请选择对应的 V2 私聊角色。")
        source = build_private_memory_plan(root, migration.v1_configuration)
        if source.source_error:
            return Outcome.failed(source.source_error, "V1 本体私聊记忆来源暂不可读。")
        records = source.matching(account_id=context.scope.account_id,
            native_actor_id=context.actor.principal.native_account_id)
        target = self.legacy._memory_target(context)
        token = digest([source.source_fingerprint, target, [r["person_id"] for r in records]])
        result = source.document()
        result.update({"plan_token": token, "matched_person_count": len(records),
            "matched_material_count": sum(len(r["materials"]) for r in records),
            "requires_role_confirmation": True,
            "destination": {"account_id": context.scope.account_id,
                "participant_id": context.actor.principal.native_account_id,
                "role_id": context.role_binding.role.subject_id}})
        return Outcome.success((result, source, records, target))

    async def plan(self):
        from .web_api import outcome_response
        if set(request.query.keys()) - {"v1_root"}:
            return outcome_response(Outcome.failed("legacy_request_invalid", "invalid private memory query"))
        def work(migration, root, session):
            result = self._plan(migration, root, session)
            return Outcome.success(result.unwrap()[0]) if result.is_success else result
        return await self.legacy._run(work, root_override=request.query.get("v1_root"), offload_sync=True)

    async def apply(self):
        from .web_api import outcome_response
        try:
            raw = await request.body()
            if len(raw) > 8192:
                raise ValueError()
            arguments = json.loads(raw.decode("utf-8"))
            if (not isinstance(arguments, dict) or set(arguments) - {"plan_token", "confirmed", "v1_root"}
                    or arguments.get("confirmed") is not True or not isinstance(arguments.get("plan_token"), str)):
                raise ValueError()
        except (ValueError, UnicodeError):
            return outcome_response(Outcome.failed("legacy_request_invalid", "请确认旧记忆属于当前私聊角色。"))

        def work(migration, root, session):
            planned = self._plan(migration, root, session)
            if not planned.is_success:
                return planned
            document, source, records, target = planned.unwrap()
            if document["plan_token"] != arguments["plan_token"]:
                return Outcome.failed("legacy_plan_stale", "来源或目标已变化，请重新试算。")
            if not records:
                return Outcome.failed("legacy_private_memory_identity_unmatched", "没有与当前账号及私聊对象对应的 V1 本体记忆。")
            result = import_private_memory(session.application.memory.query.legacy, source, records, target)
            runtime = session.application.runtime
            with runtime.transaction() as connection:
                connection.execute("INSERT INTO runtime_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("legacy_private_memory_import:" + digest(target), encode({"at": stamp(self.legacy.controller.now()),
                        "source_root": self.legacy._migration_root_identity(root), **result})))
            return Outcome.success(result)
        return await self.legacy._run(work, root_override=arguments.get("v1_root"), offload_sync=True)

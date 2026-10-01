"""Daily/sleep admission, original-material selection and deliberate retries."""

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.execution.models import TaskContext, TaskError, encode
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.model_gateway.models import ProviderResponse
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.role_work import RoleActivity, RoleActivityState
from companion_v2.role_work.journal import JournalDraft, JournalKind, JournalState, MaterialKind
from companion_v2.role_work.journal.writing import writing_profiles
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, ROLE, SCOPE
from tests.test_role_tool_loop import answered


class JournalTriggerFixture(HostFixture):
    def setUp(self):
        super().setUp()
        self.profiles += writing_profiles("primary", max_output_tokens=100)
        self.registry = FieldRegistry(version="journal.trigger.v1", fields=configuration_fields(self.profiles))
        self.owner = RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, ROLE.subject_id)

    async def setup_triggers(self, **options):
        self.writing_grant = self.grant(self.important, SCOPE, "role.journal.write")
        self.host_instance = await self.start(self.host(**options))
        self.app = self.host_instance.application
        self.trigger = self.host_instance.inbound.ingest(self.event("journal-trigger"), capability="text").unwrap()
        self.task_context = TaskContext(self.important, self.trigger.runtime_scope.persona,
                                       AudienceRef(SCOPE, (self.important.subject,)))
        self.model_behavior = self.prose

    async def prose(self, envelope):
        values = envelope.original.context.materials
        kind = json.loads(next(item.payload for item in values if item.purpose == "writing_date"))["kind"]
        return answered(encode(dict(body="只记下一点今天的感受。", form="随记",
                                    recall="fragments" if kind == "dream" else None, afterglow="")))

    def target(self, day="2026-09-21", kind=JournalKind.DIARY):
        return self.app.journal_triggers.target(self.task_context, kind, day, "Asia/Shanghai")

    def activities(self, count):
        for index in range(count):
            self.app.role_life.add_activity(RoleActivity(f"item-{index:03d}", ROLE.subject_id, SCOPE, NOW,
                RoleActivityState.ACTIVE, description=f"真实活动记录 {index}"))

    async def daily(self, **changes):
        options = dict(local_date="2026-09-21", timezone="Asia/Shanghai", role_instruction="原角色人格")
        options.update(changes)
        return await self.app.journal_triggers.daily(self.task_context, self.trigger, **options)

    async def reopen(self):
        await self.app.close()
        self.runtime.close()
        self.runtime = self.open_runtime()
        self.host_instance = await self.start(self.host(runtime=self.runtime), task_generation=1, model_generation=1)
        self.app = self.host_instance.application


class JournalTriggerTests(JournalTriggerFixture, unittest.IsolatedAsyncioTestCase):
    async def test_large_inventory_batches_every_original_without_reclassifying_selected_material(self):
        await self.setup_triggers()
        for index in range(12):
            self.app.role_life.add_activity(RoleActivity(f"long-{index:02d}", ROLE.subject_id, SCOPE, NOW,
                RoleActivityState.ACTIVE, description=(f"实际活动{index}。" * 600)))
        offered = []
        async def model(envelope):
            if envelope.original.output_format == "journal_selection":
                data = json.loads(next(m.payload for m in envelope.original.context.materials if m.purpose == "material_candidates"))
                offered.extend(x["id"] for x in data)
                return answered(json.dumps({"material_ids":[data[-1]["id"]]}))
            return await self.prose(envelope)
        self.model_behavior = model
        result = (await self.daily()).unwrap()
        self.assertEqual(result.state, "written", result)
        materials = self.app.journal_material_collector.for_day(self.task_context, self.target()).materials
        self.assertTrue(set(m.material_id for m in materials).issubset(offered))
        saved = self.app.role_journal.get(self.target().key)
        self.assertEqual(len(saved.draft.materials), 1)
        self.assertIn(saved.draft.materials[0], materials)
        self.assertGreater(len(self.called), 2)

    async def test_unknown_batch_selection_blocks_retry_and_is_reported_unknown(self):
        await self.setup_triggers()
        for index in range(12):
            self.app.role_life.add_activity(RoleActivity(f"long-{index:02d}", ROLE.subject_id, SCOPE, NOW,
                RoleActivityState.ACTIVE, description="实际记录。" * 700))
        async def unknown(envelope):
            return ProviderResponse("unknown")
        self.model_behavior = unknown
        result = (await self.daily()).unwrap()
        self.assertEqual(result.state, "unknown", result)
        again = await self.daily(retry_of=result.operation_id, retry_id="deliberate-retry")
        self.assertEqual(again.failure.code, "journal_trigger_unresolved")
        self.assertEqual(len(self.called), 1)

    async def test_daily_uses_collected_originals_and_repeated_ticks_do_not_recollect(self):
        await self.setup_triggers()
        self.activities(2)
        first = (await self.daily()).unwrap()
        self.assertEqual(first.state, "written")
        self.assertIsNone(first.selection_task_id)
        saved = self.app.role_journal.get(self.target().key)
        self.assertEqual(len(saved.draft.materials), 2)
        self.assertEqual(self.called[0].original.role_instruction, "原角色人格")
        self.activities(3)  # The repeated first two registrations are idempotent.
        with patch.object(self.app.journal_material_collector, "for_day", side_effect=AssertionError("recollected")):
            repeated = (await self.daily()).unwrap()
        self.assertEqual((repeated.operation_id, repeated.state, repeated.replayed),
                         (first.operation_id, "written", True))
        self.assertEqual(len(self.called), 1)
        self.assertEqual(self.sent, [])

    async def test_simultaneous_same_date_has_one_model_and_one_admission(self):
        await self.setup_triggers()
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(envelope):
            entered.set()
            await release.wait()
            return await self.prose(envelope)
        self.model_behavior = delayed
        first = asyncio.create_task(self.daily())
        await asyncio.wait_for(entered.wait(), 2)
        second = (await self.daily()).unwrap()
        self.assertEqual((second.state, second.replayed), ("accepted", True))
        release.set()
        self.assertEqual((await first).unwrap().state, "written")
        self.assertEqual(len(self.called), 1)
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM operations WHERE owner = 'role.journal.trigger'", ())), 1)

    async def test_sixty_five_candidates_selects_last_original_before_writing(self):
        await self.setup_triggers()
        self.activities(65)
        chosen = []
        async def model(envelope):
            if envelope.original.output_format == "journal_selection":
                candidates = json.loads(next(item.payload for item in envelope.original.context.materials
                                             if item.purpose == "material_candidates"))
                self.assertEqual(len(candidates), 65)
                self.assertEqual(candidates[-1]["activity"], "item-064")
                chosen.extend((candidates[-1]["id"], candidates[0]["id"]))
                return answered(encode({"material_ids": chosen}))
            return await self.prose(envelope)
        self.model_behavior = model
        result = (await self.daily()).unwrap()
        self.assertEqual(result.state, "written")
        self.assertIsNotNone(result.selection_task_id)
        saved = self.app.role_journal.get(self.target().key)
        self.assertEqual(tuple(item.material_id for item in saved.draft.materials), tuple(chosen))
        self.assertEqual([ref.lineage_id for ref in saved.draft.activities], ["item-064", "item-000"])
        self.assertEqual(len(self.called), 2)
        self.assertEqual([item.original.output_format for item in self.called], ["journal_selection", "journal"])
        self.assertEqual(self.sent, [])

    async def test_invalid_selection_fails_without_fallback_body_or_implicit_retry(self):
        await self.setup_triggers()
        self.activities(65)
        async def model(envelope):
            return answered(encode({"material_ids": ["invented"]}))
        self.model_behavior = model
        first = (await self.daily()).unwrap()
        self.assertEqual(first.state, "failed")
        self.assertIsNone(first.writing_task_id)
        self.assertEqual(self.app.role_journal.head(self.target().key).state, JournalState.ABSENT)
        self.assertEqual((await self.daily()).unwrap().state, "failed")
        self.assertEqual(len(self.called), 1)

    async def test_explicit_material_ids_skip_selection_and_preserve_references(self):
        await self.setup_triggers()
        self.activities(65)
        candidates = self.app.journal_material_collector.for_day(self.task_context, self.target())
        selected = (candidates.materials[-1].material_id,)
        result = (await self.daily(material_ids=selected)).unwrap()
        self.assertEqual(result.state, "written")
        self.assertIsNone(result.selection_task_id)
        self.assertEqual(self.app.role_journal.get(self.target().key).draft.materials, (candidates.materials[-1],))
        self.assertEqual(len(self.called), 1)

    async def test_known_failure_requires_explicit_retry_and_repeated_retry_keeps_its_receipt(self):
        await self.setup_triggers()
        async def invalid(envelope):
            return answered("invalid JSON")
        self.model_behavior = invalid
        failed = (await self.daily()).unwrap()
        self.assertEqual(failed.state, "failed")
        self.model_behavior = self.prose
        self.assertEqual((await self.daily()).unwrap().state, "failed")
        retried = (await self.daily(retry_of=failed.operation_id, retry_id="reviewed-retry")).unwrap()
        self.assertEqual(retried.state, "written")
        replay = (await self.daily(retry_of=failed.operation_id, retry_id="reviewed-retry")).unwrap()
        self.assertEqual((replay.operation_id, replay.replayed), (retried.operation_id, True))
        changed = await self.daily(retry_of=failed.operation_id, retry_id="different-retry")
        self.assertEqual(changed.failure.code, "idempotency_key_conflict")
        self.assertEqual(len(self.called), 2)

    async def test_unknown_model_processing_blocks_explicit_and_automatic_retry(self):
        await self.setup_triggers()
        async def unknown(envelope):
            return ProviderResponse("unknown")
        self.model_behavior = unknown
        first = (await self.daily()).unwrap()
        self.assertEqual(first.state, "unknown")
        self.assertEqual((await self.daily()).unwrap().state, "unknown")
        retry = await self.daily(retry_of=first.operation_id, retry_id="retry")
        self.assertEqual(retry.failure.code, "journal_trigger_unresolved")
        self.assertEqual(len(self.called), 1)

    async def test_restart_retains_failed_and_admitted_operations_without_recollecting(self):
        await self.setup_triggers()
        async def invalid(envelope):
            return answered("invalid JSON")
        self.model_behavior = invalid
        failed = (await self.daily()).unwrap()
        other_target = self.target("2026-09-20")
        admitted = self.app.journal_triggers._admit(self.task_context, other_target, "原角色人格", None, None)
        await self.reopen()
        with patch.object(self.app.journal_material_collector, "for_day", side_effect=AssertionError("recollected")):
            replayed = (await self.daily()).unwrap()
            interrupted = (await self.daily(local_date="2026-09-20")).unwrap()
        self.assertEqual((replayed.state, replayed.operation_id), ("failed", failed.operation_id))
        self.assertEqual((interrupted.state, interrupted.operation_id), ("accepted", admitted.operation.operation_id))
        retry = await self.daily(local_date="2026-09-20", retry_of=interrupted.operation_id, retry_id="retry")
        self.assertEqual(retry.failure.code, "journal_trigger_unresolved")
        self.assertEqual(len(self.called), 1)

    async def test_sleep_completion_uses_completion_local_date_and_never_creates_activities(self):
        await self.setup_triggers()
        result = (await self.app.journal_triggers.sleep_completed(self.task_context, self.trigger,
            started_at=NOW - timedelta(hours=9), completed_at=NOW, timezone="Asia/Shanghai",
            role_instruction="原角色人格")).unwrap()
        self.assertEqual(result.state, "written")
        draft = self.app.role_journal.get(self.target(kind=JournalKind.DREAM).key).draft
        self.assertEqual(draft.context.key.local_date, "2026-09-21")
        self.assertEqual(draft.materials[-1].kind, MaterialKind.ACTION)
        self.assertEqual(draft.materials[-1].source, self.trigger.source)
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_activities", ()), ())
        invalid = await self.app.journal_triggers.sleep_completed(self.task_context, self.trigger,
            started_at=NOW, completed_at=NOW + timedelta(seconds=1), timezone="Asia/Shanghai",
            role_instruction="原角色人格")
        self.assertEqual(invalid.failure.code, "journal_sleep_time_invalid")
        self.assertEqual(len(self.called), 1)

    async def test_existing_and_deleted_dates_are_skipped_before_collection(self):
        await self.setup_triggers()
        self.app.role_journal.save(JournalDraft(self.target(), body="人工正文"), expected_revision=0, operation_id="manual")
        self.app.role_journal.delete(self.target("2026-09-20"), expected_revision=0, operation_id="delete")
        with patch.object(self.app.journal_material_collector, "for_day", side_effect=AssertionError("recollected")):
            self.assertEqual((await self.daily()).unwrap().state, "active")
            self.assertEqual((await self.daily(local_date="2026-09-20")).unwrap().state, "deleted")
        self.assertEqual(self.called, [])

    async def test_manual_edit_during_selection_prevents_writing(self):
        await self.setup_triggers()
        self.activities(65)
        async def model(envelope):
            self.app.role_journal.save(JournalDraft(self.target(), body="人工正文"), expected_revision=0, operation_id="manual")
            return answered(encode({"material_ids": []}))
        self.model_behavior = model
        result = (await self.daily()).unwrap()
        self.assertEqual(result.state, "failed")
        self.assertIsNone(result.writing_task_id)
        self.assertEqual(self.app.role_journal.get(self.target().key).draft.body, "人工正文")
        self.assertEqual(len(self.called), 1)

    async def test_read_grant_revocation_during_selection_prevents_body_and_settles_receipt(self):
        await self.setup_triggers()
        self.activities(65)
        async def model(envelope):
            self.identity.revoke_grant(self.writing_grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
            return answered(encode({"material_ids": []}))
        self.model_behavior = model
        result = (await self.daily()).unwrap()
        self.assertEqual(result.state, "failed")
        self.assertIsNone(result.writing_task_id)
        self.assertEqual(self.app.role_journal.head(self.target().key).state, JournalState.ABSENT)
        self.grant(self.important, SCOPE, "role.journal.write")
        self.model_behavior = self.prose
        self.assertEqual((await self.daily()).unwrap().state, "failed")
        self.assertEqual(len(self.called), 1)

    async def test_read_grant_revocation_during_body_prevents_commit(self):
        await self.setup_triggers()
        async def model(envelope):
            self.identity.revoke_grant(self.writing_grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
            return await self.prose(envelope)
        self.model_behavior = model
        self.assertEqual((await self.daily()).unwrap().state, "failed")
        self.assertEqual(self.app.role_journal.head(self.target().key).state, JournalState.ABSENT)

    async def test_invalid_route_or_source_hash_rejected_before_admission(self):
        await self.setup_triggers()
        original = self.trigger
        self.trigger = replace(original, principal=self.standard.principal)
        self.assertEqual((await self.daily()).failure.code, "journal_context_mismatch")
        self.trigger = replace(original, input_hash="wrong")
        self.assertEqual((await self.daily()).failure.code, "journal_source_changed")
        self.trigger = original
        self.assertEqual((await self.daily(local_date="2026-09-22")).failure.code, "journal_trigger_in_future")
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations WHERE owner = 'role.journal.trigger'", ()), ())
        self.assertEqual(self.called, [])

    async def test_shutdown_cancels_direct_invocation_before_owned_storage_closes(self):
        await self.setup_triggers(owns_runtime=True)
        entered = asyncio.Event()
        async def delayed(envelope):
            entered.set()
            await asyncio.Event().wait()
        self.model_behavior = delayed
        job = asyncio.create_task(self.daily())
        await asyncio.wait_for(entered.wait(), 2)
        report = await self.app.close()
        self.assertEqual((report.state, report.storage_closed), ("stopped", True))
        self.assertEqual(self.app.active_handles, ())
        with self.assertRaises(asyncio.CancelledError):
            await job

    async def test_other_private_window_cannot_start_second_attempt_or_read_original_receipt(self):
        await self.setup_triggers()
        async def invalid(envelope):
            return answered("invalid JSON")
        self.model_behavior = invalid
        first = (await self.daily()).unwrap()
        scope = replace(SCOPE, session_id="another-session", conversation_id="another-conversation")
        self.personas.register_route(ConversationRoute(scope, user=self.important.subject), observed_at=NOW)
        self.grant(self.important, scope, "text")
        self.grant(self.important, scope, "role.journal.write")
        event = self.host_instance.inbound.ingest(self.event("other", scope=scope), capability="text").unwrap()
        context = TaskContext(self.important, event.runtime_scope.persona, AudienceRef(scope, (self.important.subject,)))
        result = await self.app.journal_triggers.daily(context, event, local_date="2026-09-21",
            timezone="Asia/Shanghai", role_instruction="原角色人格")
        self.assertEqual(result.failure.code, "operation_id_conflict")
        target = self.app.journal_triggers.target(context, JournalKind.DIARY, "2026-09-21", "Asia/Shanghai")
        with self.assertRaises(TaskError) as denied:
            self.app.journal_triggers.inspect(context, target, first.operation_id)
        self.assertEqual(denied.exception.code, "journal_context_mismatch")
        self.assertEqual(len(self.called), 1)

    async def test_selection_replay_has_metadata_only_and_new_apis_close_with_host(self):
        await self.setup_triggers()
        self.activities(65)
        candidates = self.app.journal_material_collector.for_day(self.task_context, self.target())
        chosen = (candidates.materials[-1].material_id,)
        async def model(envelope):
            return answered(encode({"material_ids": chosen}))
        self.model_behavior = model
        arguments = dict(role_instruction="原角色人格", request_id="selection-only")
        first = (await self.app.journal_writer.select(self.task_context, self.trigger, candidates, **arguments)).unwrap()
        self.assertEqual(first.material_ids, chosen)
        replay = (await self.app.journal_writer.select(self.task_context, self.trigger, candidates, **arguments)).unwrap()
        self.assertEqual(first.run.task.task_id, replay.run.task.task_id)
        self.assertIsNone(replay.material_ids)
        self.assertEqual(len(self.called), 1)
        await self.app.close()
        for invoke in (self.app.journal_writer.select, self.app.journal_writer.write_collected):
            result = await invoke(self.task_context, self.trigger, candidates, **arguments)
            self.assertEqual(result.failure.code, "task_runner_closed")

    async def test_new_role_revision_cannot_misread_old_child_status_as_retryable(self):
        await self.setup_triggers()
        async def invalid(envelope):
            return answered("invalid JSON")
        self.model_behavior = invalid
        first = (await self.daily()).unwrap()
        self.identity.bind_role(scope=SCOPE, role=ROLE, expected_revision=self.task_context.role_binding.revision,
                                observed_at=NOW)
        binding = self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap()
        context = replace(self.task_context, role_binding=binding)
        event = replace(self.trigger, runtime_scope=replace(self.trigger.runtime_scope, persona=binding))
        with self.assertRaises(TaskError) as denied:
            self.app.journal_triggers.inspect(context, self.target(), first.operation_id)
        self.assertEqual(denied.exception.code, "journal_context_mismatch")
        retry = await self.app.journal_triggers.daily(context, event, local_date="2026-09-21",
            timezone="Asia/Shanghai", role_instruction="原角色人格", retry_of=first.operation_id, retry_id="retry")
        self.assertEqual(retry.failure.code, "journal_context_mismatch")
        self.assertEqual(len(self.called), 1)

    async def test_insufficient_background_capacity_waits_with_original_date_receipt(self):
        await self.setup_triggers()
        entered, release = asyncio.Event(), asyncio.Event()
        async def model(envelope):
            entered.set()
            await release.wait()
            return await self.prose(envelope)
        self.model_behavior = model
        blocker = asyncio.create_task(self.daily(local_date="2026-09-20"))
        await asyncio.wait_for(entered.wait(), 2)
        queued = asyncio.create_task(self.daily())
        await self.until(lambda: bool(self.app.background_waiting._pending))
        first = (await self.daily()).unwrap()
        self.assertEqual((first.state, first.replayed), ("accepted", True))
        self.assertEqual(len(self.called), 1)
        release.set()
        self.assertEqual((await blocker).unwrap().state, "written")
        completed = (await asyncio.wait_for(queued, 2)).unwrap()
        self.assertEqual((completed.state, completed.operation_id), ("written", first.operation_id))
        self.assertEqual((await self.daily()).unwrap().state, "written")
        self.assertEqual(len(self.called), 2)


if __name__ == "__main__":
    unittest.main()

"""Synthetic writing through the real task, budget, archive and host boundaries."""

import asyncio
from dataclasses import replace
import json
import unittest

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.execution.models import TaskContext, digest, encode
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef, SourceRef, VersionRef
from companion_v2.model_gateway.models import ProviderResponse
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.role_work.journal import (DreamRecall, JournalContext, JournalDerivatives, JournalDraft, JournalKey, JournalKind,
    JournalMaterial, JournalOrigin, JournalRef, JournalState, MaterialKind, RoleJournalService)
from companion_v2.role_work.models import (RoleActivity, RoleActivityState, RoleArtifact,
    RoleArtifactJournalMeaning as Meaning, RoleArtifactKind)
from companion_v2.role_work.journal.writing import writing_profiles
from companion_v2.sources.models import SourceRecord
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, ROLE, SCOPE
from tests.test_role_tool_loop import answered


def body(text="读了关于模型和系统的一篇文章。还有一个问题没想通。", *, recall=None, afterglow=""):
    return json.dumps(dict(body=text, form="随记", recall=recall, afterglow=afterglow), ensure_ascii=False)


class JournalWritingTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profiles += writing_profiles("primary", max_output_tokens=100)
        self.registry = FieldRegistry(version="host.journal.v1", fields=configuration_fields(self.profiles))
        self.owner = RoleOwnerRef(SCOPE.installation_id, SCOPE.bot_id, ROLE.subject_id)

    async def setup_writer(self, **host_options):
        self.host_instance = await self.start(self.host(**host_options))
        self.app = self.host_instance.application
        self.writer = self.app.journal_writer
        self.journal = self.app.role_journal
        self.trigger = self.host_instance.inbound.ingest(self.event("journal-trigger"), capability="text").unwrap()
        self.task_context = TaskContext(self.important, self.trigger.runtime_scope.persona,
                                       AudienceRef(SCOPE, (self.important.subject,)))
        async def model(envelope):
            return answered(body())
        self.model_behavior = model

    def target(self, day="2026-09-21", kind=JournalKind.DIARY):
        return JournalContext(JournalKey(self.owner, kind, day), SCOPE, "Asia/Shanghai")

    def source(self, name="work", text="写了一个短篇", scope=SCOPE):
        ref = SourceRef(name, "fixture", scope, VersionRef(name, 1), NOW)
        self.journal.sources.publish(SourceRecord(ref, AudienceRef(scope, (self.important.subject,)),
                                                  digest(text), text), observed_at=NOW).unwrap()
        return ref

    async def write(self, *, target=None, request="write", **changes):
        return await self.writer.write(self.task_context, self.trigger, target or self.target(),
            role_instruction="保留的角色人格", request_id=request, **changes)

    async def test_creation_publication_and_reading_keep_their_semantics_through_save_and_reopen(self):
        await self.setup_writer()
        ref = self.source()
        materials = (
            JournalMaterial("wrote", MaterialKind.ACTION, "完成《巡夜人》开篇。", "story-1", "2026-09-21", ref),
            JournalMaterial("scene", MaterialKind.CREATIVE_TEXT, "小说里我向守门人借了一盏灯。", "story-1", "2026-09-21", ref),
            JournalMaterial("posted", MaterialKind.ACTION, "发布了一段随想。", "post-1", "2026-09-21", ref),
            JournalMaterial("post", MaterialKind.PUBLISHED_TEXT, "我坐火车去海边。", "post-1", "2026-09-21", ref),
            JournalMaterial("read", MaterialKind.READING, "一篇讨论模型系统的文章。", "article-1", "2026-09-21", ref),
        )
        result = (await self.write(materials=materials)).unwrap().task
        self.assertEqual((result.state, result.effect, result.attempt_no), ("succeeded", "committed", 1))
        entry = RoleJournalService(self.open_runtime(), now=self.clock.now).get(self.target().key)
        self.assertEqual(entry.draft.materials, materials)
        self.assertEqual(entry.draft.summary, "")
        self.assertIsNone(self.journal.derivatives(self.target().key))
        envelope = self.called[0]
        self.assertEqual(envelope.original.role_instruction, "保留的角色人格")
        self.assertEqual(envelope.original.output_format, "journal")
        offered = json.loads(next(m.payload for m in envelope.original.context.materials if m.purpose == "writing_materials"))
        self.assertEqual([m["kind"] for m in offered], [m.kind.value for m in materials])
        self.assertEqual((offered[0]["origin"], offered[1]["origin"]), ("story-1", "story-1"))
        self.assertEqual(envelope.tools, ())
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.runtime.read_all("SELECT * FROM sources", ())), 2)

    async def test_thin_dream_can_be_only_afterglow_or_fragments(self):
        await self.setup_writer()
        for index, (recall, text, afterglow) in enumerate((
                ("afterglow", "", "只记得有一点轻松，梦已经想不起来。"),
                ("fragments", "我记得一段通向云里的窄楼梯。", ""))):
            async def model(envelope):
                return answered(body(text, recall=recall, afterglow=afterglow))
            self.model_behavior = model
            target = self.target("2026-09-2" + str(index), JournalKind.DREAM)
            result = (await self.write(target=target, request="dream-" + str(index))).unwrap().task
            self.assertEqual(result.state, "succeeded")
            entry = self.journal.get(target.key)
            self.assertEqual((entry.draft.body, entry.draft.afterglow, entry.draft.recall),
                             (text, afterglow, DreamRecall(recall)))

    async def test_classified_artifact_contents_reach_writing_and_derivation_with_original_dependencies(self):
        await self.setup_writer()
        self.grant(self.important, SCOPE, "role.journal.write")
        for meaning, text in ((Meaning.CREATIVE_TEXT, "小说里我乘着纸船到了月亮。"),
                              (Meaning.READING, "文章讨论模型与系统的区别。")):
            identifier = meaning.value
            activity = RoleActivity(identifier, ROLE.subject_id, SCOPE, NOW, RoleActivityState.ACTIVE)
            self.app.role_life.add_activity(activity)
            source = self.source(identifier, text)
            self.app.role_life.add_artifact(RoleArtifact(identifier, identifier, RoleArtifactKind.TEXT,
                source, NOW, journal_meaning=meaning), owner=self.owner)
        producer = self.app.journal_artifact_material_producer
        catalog = producer.for_day(self.target())
        contents = producer.contents_for_day(self.task_context, self.target())
        materials = catalog.materials + contents.materials
        async def model(envelope):
            return answered(body("今天写了一个乘纸船去月亮的故事，又收存了一篇文章。"))
        self.model_behavior = model
        result = (await self.write(materials=materials)).unwrap().task
        self.assertEqual(result.state, "succeeded")
        offered = json.loads(next(m.payload for m in self.called[0].original.context.materials
                                  if m.purpose == "writing_materials"))
        self.assertEqual([m["kind"] for m in offered], ["action", "reading", "creative_text", "reading"])
        self.assertEqual(offered[0]["origin"], offered[2]["origin"])
        self.assertEqual(offered[1]["origin"], offered[3]["origin"])
        restored = RoleJournalService(self.open_runtime(), now=self.clock.now)
        entry = restored.get(self.target().key)
        self.assertEqual(entry.draft.materials, materials)
        creative_id = contents.materials[0].material_id
        async def derive(envelope):
            return answered(encode({"summary": "写了纸船的故事，收存了一篇文章。", "continuity": "",
                "dream_fragments": [{"text": "故事里的月亮纸船。", "material_ids": [creative_id]}]}))
        self.model_behavior = derive
        result = (await self.writer.derive(self.task_context, self.trigger, entry.reference,
            role_instruction="保留的角色人格", request_id="artifact-extraction")).unwrap().task
        self.assertEqual(result.state, "succeeded")
        self.assertEqual(restored.derivatives(self.target().key).material.fragment_origins, ((creative_id,),))
        self.journal.sources.revoke(contents.source_refs[0], expected_governance_revision=1, observed_at=NOW).unwrap()
        with self.assertRaises(ValueError):
            restored.derivatives(self.target().key)
        self.assertEqual(self.sent, [])

    async def test_recent_context_uses_original_subjective_body_and_retains_shared_origins(self):
        await self.setup_writer()
        ref = self.source()
        excerpt = JournalMaterial("scene", MaterialKind.CREATIVE_TEXT, "小说里那座灯塔还没有亮。", "story-1", "2026-09-20", ref)
        target = self.target("2026-09-20")
        prior = JournalDraft(target, body="写到灯塔那里时，我还没想好人物该不该进去。",
                             sources=(ref,), materials=(excerpt,))
        self.journal.save(prior, expected_revision=0, operation_id="old-diary")
        await self.write(materials=(replace(excerpt, material_id="next-scene", local_date="2026-09-21"),))
        context = self.called[0].original.context.materials
        recent = [json.loads(m.payload) for m in context if m.purpose == "recent_journal"]
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["body"], prior.body)
        self.assertEqual(recent[0]["materials"][0]["kind"], "creative_text")
        self.assertEqual(recent[0]["materials"][0]["origin"], "story-1")
        self.assertEqual(self.journal.get(self.target().key).draft.journals, (JournalRef(target.key, 1),))

    async def test_recent_journals_never_cross_private_conversation_scope(self):
        await self.setup_writer()
        other_scope = replace(SCOPE, native_scope_id="native-b", conversation_id="conversation-b",
                              session_id="session-b")
        other_target = None
        for day in range(20, 29):
            other_target = JournalContext(self.target(f"2026-09-{day}").key, other_scope, "Asia/Shanghai")
            self.journal.save(JournalDraft(other_target, body="另一个私聊窗口的私人正文。"),
                              expected_revision=0, operation_id=f"other-window-{day}")
        same_scope_prior = self.target("2026-09-19")
        self.journal.save(JournalDraft(same_scope_prior, body="当前私聊窗口自己的旧正文。"),
                          expected_revision=0, operation_id="same-window")

        current_target = self.target("2026-10-01")
        await self.write(target=current_target)
        recent = [m for m in self.called[0].original.context.materials if m.purpose == "recent_journal"]
        recent_bodies = [json.loads(m.payload)["body"] for m in recent]
        self.assertEqual(recent_bodies, ["当前私聊窗口自己的旧正文。"])

        explicit_target = self.target("2026-10-02")
        result = await self.write(target=explicit_target, request="cross-window-explicit",
                                  recent=(JournalRef(other_target.key, 1),))
        self.assertEqual(result.failure.code, "journal_context_mismatch")
        self.assertEqual(len(self.called), 1)
        self.assertEqual(self.journal.head(explicit_target.key).state, JournalState.ABSENT)

    async def test_writing_rejects_materials_from_other_scope_or_future_dates(self):
        await self.setup_writer()
        other_scope = replace(SCOPE, native_scope_id="native-b", conversation_id="conversation-b",
                              session_id="session-b")
        foreign_source = self.source("foreign-window", scope=other_scope)
        foreign_material = JournalMaterial("foreign", MaterialKind.REFLECTION, "另一个窗口里的私人内容。",
                                           "foreign-window", "2026-09-21", foreign_source)
        foreign = await self.write(materials=(foreign_material,))
        self.assertEqual(foreign.failure.code, "journal_context_mismatch")

        local_source = self.source("local-source")
        future_material = JournalMaterial("future", MaterialKind.REFLECTION, "未来日期的材料。",
                                          "future-origin", "2026-09-22", local_source)
        future = await self.write(materials=(future_material,), request="future-material")
        self.assertEqual(future.failure.code, "journal_context_mismatch")
        self.assertEqual(self.called, [])

    async def test_writing_rejects_activity_from_other_private_scope(self):
        await self.setup_writer()
        other_scope = replace(SCOPE, native_scope_id="native-b", conversation_id="conversation-b",
                              session_id="session-b")
        activity = RoleActivity("other-window-activity", ROLE.subject_id, other_scope, NOW,
                                RoleActivityState.ACTIVE, description="另一个窗口的活动")
        self.app.role_life.add_activity(activity)
        source = self.source("activity-source")
        material = JournalMaterial("activity", MaterialKind.ACTION, "完成一个活动。", "activity-origin",
                                   "2026-09-21", source, VersionRef(activity.activity_id, activity.revision))
        result = await self.write(materials=(material,))
        self.assertEqual(result.failure.code, "journal_context_mismatch")
        self.assertEqual(self.called, [])

    async def test_derivatives_are_a_separate_call_with_parent_and_material_provenance(self):
        await self.setup_writer()
        ref = self.source()
        material = JournalMaterial("scene", MaterialKind.CREATIVE_TEXT, "门变成了一小块糖。", "story", "2026-09-21", ref)
        await self.write(materials=(material,))
        parent = self.journal.get(self.target().key)
        async def derive(envelope):
            self.assertEqual(envelope.original.output_format, "journal_derivatives")
            return answered(encode({"summary": "想到故事里的变化。", "continuity": "还没想好结尾。",
                "dream_fragments": [{"text": "故事里变成糖的门。", "material_ids": ["scene"]}]}))
        self.model_behavior = derive
        result = (await self.writer.derive(self.task_context, self.trigger, parent.reference,
            role_instruction="保留的角色人格", request_id="derive")).unwrap().task
        self.assertEqual(result.state, "succeeded")
        self.assertEqual(self.journal.get(parent.reference.key), parent)
        derived = RoleJournalService(self.open_runtime(), now=self.clock.now).derivatives(parent.reference.key)
        self.assertEqual(derived.material.fragment_origins, (("scene",),))
        self.assertEqual(len(self.called), 2)

    async def test_failed_or_malformed_result_never_creates_fallback_and_never_replays(self):
        await self.setup_writer()
        for index, reply in enumerate(("不是合法的结构化正文", "{}", '{"body":"a","body":"b"}')):
            async def model(envelope):
                return answered(reply)
            self.model_behavior = model
            target = self.target("2026-09-1" + str(index))
            first = (await self.write(target=target, request=str(index), recent=())).unwrap().task
            self.assertEqual(first.state, "failed")
            self.assertEqual(self.journal.head(target.key).state, JournalState.ABSENT)
            replay = (await self.write(target=target, request=str(index), recent=())).unwrap().task
            self.assertEqual(replay.task_id, first.task_id)
        self.assertEqual(len(self.called), 3)
        self.assertEqual(self.runtime.read_all("SELECT * FROM role_journal_operations", ()), ())

    async def test_unknown_provider_outcome_leaves_day_absent_without_second_dispatch(self):
        await self.setup_writer()
        async def model(envelope):
            return ProviderResponse("unknown")
        self.model_behavior = model
        result = (await self.write()).unwrap().task
        self.assertEqual(result.state, "failed")
        self.assertEqual((await self.write()).unwrap().task.task_id, result.task_id)
        self.assertEqual(len(self.called), 1)
        self.assertEqual(self.journal.head(self.target().key).state, JournalState.ABSENT)

    async def test_bad_derivative_reference_keeps_saved_body_and_prior_material(self):
        await self.setup_writer()
        await self.write()
        parent = self.journal.get(self.target().key)
        material = JournalDerivatives(parent.reference, summary="已保存的摘要")
        self.journal.save_derivatives(material, operation_id="first-derive")
        async def model(envelope):
            return answered(encode({"summary": "", "continuity": "", "dream_fragments": [
                {"text": "伪造的素材来源", "material_ids": ["not-offered"]}]}))
        self.model_behavior = model
        result = (await self.writer.derive(self.task_context, self.trigger, parent.reference,
            role_instruction="保留的角色人格", request_id="derive", expected_revision=1)).unwrap().task
        self.assertEqual(result.state, "failed")
        self.assertEqual(self.journal.get(parent.reference.key), parent)
        self.assertEqual(self.journal.derivatives(parent.reference.key).material, material)

    async def test_manual_edit_or_delete_during_generation_fences_late_body(self):
        await self.setup_writer()
        for day, delete in (("2026-09-19", False), ("2026-09-20", True)):
            entered, release = asyncio.Event(), asyncio.Event()
            async def model(envelope):
                entered.set()
                await release.wait()
                return answered(body("迟到正文"))
            self.model_behavior = model
            target = self.target(day)
            job = asyncio.create_task(self.write(target=target, request=day, recent=()))
            await asyncio.wait_for(entered.wait(), 2)
            if delete:
                self.journal.delete(target, expected_revision=0, operation_id="delete-day")
            else:
                self.journal.save(JournalDraft(target, body="人工写的内容", origin=JournalOrigin.MANUAL),
                                  expected_revision=0, operation_id="manual")
            release.set()
            result = (await job).unwrap().task
            self.assertEqual(result.state, "failed")
            self.assertEqual(self.journal.head(target.key).revision, 1)
            if delete:
                self.assertEqual(self.journal.head(target.key).state, JournalState.DELETED)
            else:
                self.assertEqual(self.journal.get(target.key).draft.body, "人工写的内容")

    async def test_source_revocation_during_generation_prevents_commit_and_retains_usage(self):
        await self.setup_writer()
        entered, release = asyncio.Event(), asyncio.Event()
        async def model(envelope):
            entered.set()
            await release.wait()
            return answered(body())
        self.model_behavior = model
        job = asyncio.create_task(self.write())
        await asyncio.wait_for(entered.wait(), 2)
        self.journal.sources.revoke(self.trigger.source, expected_governance_revision=1,
                                    observed_at=self.clock.now()).unwrap()
        release.set()
        self.assertNotEqual((await job).unwrap().task.state, "succeeded")
        self.assertEqual(self.journal.head(self.target().key).state, JournalState.ABSENT)
        call = self.runtime.read_one("SELECT * FROM model_calls", ())
        self.assertEqual(call["actual_tokens"], 15)

    async def test_editing_parent_during_extraction_prevents_late_derivatives(self):
        await self.setup_writer()
        await self.write()
        parent = self.journal.get(self.target().key)
        entered, release = asyncio.Event(), asyncio.Event()
        async def model(envelope):
            entered.set()
            await release.wait()
            return answered(encode({"summary": "迟到摘要", "dream_fragments": [], "continuity": ""}))
        self.model_behavior = model
        job = asyncio.create_task(self.writer.derive(self.task_context, self.trigger, parent.reference,
            role_instruction="保留的角色人格", request_id="derive"))
        await asyncio.wait_for(entered.wait(), 2)
        self.journal.save(replace(parent.draft, body="新正文", origin=JournalOrigin.MANUAL),
                          expected_revision=1, operation_id="edit")
        release.set()
        self.assertNotEqual((await job).unwrap().task.state, "succeeded")
        self.assertIsNone(self.journal.derivatives(parent.reference.key))

    async def test_background_capacity_keeps_foreground_available_and_shutdown_tracks_writer(self):
        await self.setup_writer()
        entered, release = asyncio.Event(), asyncio.Event()
        async def model(envelope):
            if envelope.original.output_format == "conversation":
                return answered("我在。")
            entered.set()
            await release.wait()
            return answered(body())
        self.model_behavior = model
        job = asyncio.create_task(self.write())
        await asyncio.wait_for(entered.wait(), 2)
        queued = asyncio.create_task(self.write(target=self.target("2026-09-20"), request="other-day"))
        await self.until(lambda: bool(self.app.background_waiting._pending))
        self.assertFalse(queued.done())
        batch = self.host_instance.receive(self.event("foreground")).unwrap()
        self.advance(self.app, 1)
        self.assertEqual((await self.done(self.app, batch))["state"], "complete")
        self.assertEqual(len(self.sent), 1)
        report = await self.app.close()
        self.assertEqual(report.state, "stopped")
        self.assertEqual(self.app.active_handles, ())
        with self.assertRaises(asyncio.CancelledError):
            await queued
        self.assertNotEqual((await job).unwrap().task.state, "succeeded")
        self.assertEqual(self.journal.head(self.target().key).state, JournalState.ABSENT)
        self.assertEqual((await self.write(request="after-stop")).failure.code, "task_runner_closed")

    async def test_wrong_role_is_rejected_before_model_dispatch(self):
        await self.setup_writer()
        wrong = replace(self.target(), key=replace(self.target().key, owner=replace(self.owner, persona_id="other")))
        result = await self.write(target=wrong)
        self.assertEqual(result.failure.code, "journal_context_mismatch")
        self.assertEqual(self.called, [])

    async def test_successful_request_survives_restart_as_metadata_without_regeneration(self):
        await self.setup_writer()
        task = (await self.write()).unwrap().task
        await self.app.close()
        self.runtime.close()
        app = (await self.start(self.host(runtime=self.open_runtime()), task_generation=1, model_generation=1)).application
        result = await app.journal_writer.write(self.task_context, self.trigger, self.target(),
            role_instruction="保留的角色人格", request_id="write")
        self.assertEqual(result.unwrap().task.task_id, task.task_id)
        self.assertEqual(result.unwrap().task.state, "succeeded")
        self.assertEqual(len(self.called), 1)
        self.assertNotIn("读了关于模型", encode(result.unwrap().task))

    async def test_shutdown_waits_for_invocation_before_closing_owned_store(self):
        await self.setup_writer(owns_runtime=True)
        entered = asyncio.Event()
        async def model(envelope):
            entered.set()
            await asyncio.Event().wait()
        self.model_behavior = model
        job = asyncio.create_task(self.write())
        await asyncio.wait_for(entered.wait(), 2)
        report = await self.app.close()
        self.assertTrue(report.storage_closed)
        result = await job
        self.assertNotEqual(result.unwrap().task.state, "succeeded")
        service = RoleJournalService(self.open_runtime(), now=self.clock.now)
        self.assertEqual(service.head(self.target().key).state, JournalState.ABSENT)


if __name__ == "__main__":
    unittest.main()

"""Completed role receipts become reviewable, revisioned growth progress."""

from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from companion_v2.configuration.registry import FieldRegistry
from companion_v2.execution.models import TaskContext, TaskError
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.role_work.growth.management import RoleGrowthManagement
from companion_v2.role_work.growth.progress import growth_progress_profile, parse_progress
from companion_v2.role_work.growth.progress_management import GrowthProgressManagement
from companion_v2.role_work.journal.models import JournalContext, JournalDraft, JournalKey, JournalKind
from companion_v2.role_work.models import RoleActivity, RoleActivityState
from tests.test_host_application import HostFixture
from tests.test_management_access import NOW, SCOPE
from tests.test_role_tool_loop import answered


class GrowthProgressTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profiles += (growth_progress_profile("primary", max_output_tokens=64),)
        self.registry = FieldRegistry(version="growth-progress.v1",
                                      fields=configuration_fields(self.profiles))

    async def setup_growth(self):
        host = await self.start()
        app = host.application
        source = host.inbound.ingest(self.event("growth-source"), capability="text").unwrap().source
        context = TaskContext(self.important, self.identity.resolve_role(SCOPE, observed_at=NOW).unwrap(),
                              AudienceRef(SCOPE, (self.important.subject,)))
        app.state_maintenance.bind(context, "原角色人格提示")
        manager = RoleGrowthManagement(app.role_growth)
        token = manager.list(operator=self.core, context=context).unwrap()["create_token"]
        proposed = manager.create(operator=self.core, context=context, view_token=token,
            operation_key="growth-proposal", kind="goal", title="练习水彩", description="记录练习过程。",
            sources=(source,)).unwrap()["item"]
        active = manager.command(operator=self.core, context=context, growth_id=proposed["growth_id"],
            expected_revision=proposed["revision"], view_token=proposed["view_token"],
            operation_key="growth-confirm", action="confirm").unwrap()["item"]
        return app, context, manager, active, source

    @staticmethod
    def complete(app, context, identifier="walk"):
        activity = app.role_life.add_activity(RoleActivity(identifier,
            context.role_binding.role.subject_id, context.scope, app.now(), RoleActivityState.ACTIVE,
            description="到河边写生"))
        operation_id = "complete-" + identifier
        app.role_life.transition_activity(activity.activity_id, owner=activity.owner,
            expected_revision=activity.revision, state=RoleActivityState.COMPLETED,
            operation_id=operation_id, observed_at=app.now(), checkpoint="记录了桥边的颜色。")
        return operation_id

    async def propose(self, app, context, active, operation_id):
        async def respond(envelope):
            self.assertEqual(envelope.original.output_format, "role_growth_progress")
            return answered(json.dumps({"growth_id": active["growth_id"],
                                        "progress_note": "完成一次河边写生，并记录颜色。"}, ensure_ascii=False))
        self.model_behavior = respond
        report = await app.growth_progress.run(context, "原角色人格提示", "activity", operation_id)
        self.assertEqual(report["state"], "succeeded", report)
        return GrowthProgressManagement(app)

    async def test_completed_receipt_requires_review_before_growth_changes(self):
        app, context, _, active, _ = await self.setup_growth()
        operation_id = self.complete(app, context)
        review = await self.propose(app, context, active, operation_id)
        items = review.list(operator=self.core, context=context).unwrap()["items"]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual((item["base_revision"], item["actions"]), (2, ["accept", "reject"]))
        owner = app.role_growth_context.reader.owner(context)
        self.assertEqual(app.role_growth.record(active["growth_id"], owner=owner).revision, 2)
        accepted = review.command(operator=self.core, context=context, review_id=item["review_id"],
            action="accept", expected_revision=item["base_revision"], view_token=item["view_token"],
            operation_key="accept-progress").unwrap()
        self.assertEqual((accepted["state"], accepted["applied_revision"]), ("accepted", 3))
        self.assertTrue(review.command(operator=self.core, context=context, review_id=item["review_id"],
            action="accept", expected_revision=item["base_revision"], view_token=item["view_token"],
            operation_key="accept-progress").unwrap()["replayed"])
        record = app.role_growth.record(active["growth_id"], owner=owner)
        self.assertEqual((record.state.value, record.revision, record.changed_by),
                         ("active", 3, self.core.subject))
        material = app.role_growth_context.reader.read(
            ({"growth_id": record.growth_id, "revision": record.revision},), context, app.now())
        self.assertEqual(json.loads(material[0].payload)["progress_note"], record.progress_note)
        self.assertEqual((await app.growth_progress.run(context, "原角色人格提示", "activity", operation_id))["state"],
                         "already_attempted")
        self.assertEqual(len([call for call in self.called
            if call.original.output_format == "role_growth_progress"]), 1)

    async def test_background_scan_submits_completed_receipt_for_review(self):
        app, context, _, active, _ = await self.setup_growth()
        async def respond(envelope):
            self.assertEqual(envelope.original.output_format, "role_growth_progress")
            return answered(json.dumps({"growth_id": active["growth_id"],
                                        "progress_note": "完成一次河边写生。"}, ensure_ascii=False))
        self.model_behavior = respond
        self.complete(app, context)
        app.growth_progress.next_checks.clear()
        app.growth_progress.advance()
        await self.until(lambda: app.growth_progress.results.get(context.key, {}).get("state") == "succeeded")
        items = GrowthProgressManagement(app).list(operator=self.core, context=context).unwrap()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["base_revision"], 2)
        self.assertEqual(app.role_growth.record(active["growth_id"],
            owner=app.role_growth_context.reader.owner(context)).revision, 2)

    async def test_unfinished_receipt_and_invalid_model_selection_do_not_create_review(self):
        app, context, _, active, _ = await self.setup_growth()
        activity = app.role_life.add_activity(RoleActivity("planned",
            context.role_binding.role.subject_id, context.scope, app.now(), RoleActivityState.ACTIVE))
        app.role_life.transition_activity(activity.activity_id, owner=activity.owner,
            expected_revision=1, state=RoleActivityState.PAUSED,
            operation_id="pause-planned", observed_at=app.now())
        result = await app.growth_progress.run(context, "原角色人格提示", "activity", "pause-planned")
        self.assertEqual(result["state"], "no_active_target")
        self.assertEqual(app.runtime.read_all("SELECT * FROM role_growth_progress_reviews", ()), ())
        with self.assertRaises(TaskError):
            parse_progress('{"growth_id":"other","progress_note":"done"}', {active["growth_id"]})

    async def test_journal_receipt_does_not_publish_body_as_completed_event(self):
        app, context, _, active, _ = await self.setup_growth()
        key = JournalKey(app.life_context.owner(context), JournalKind.DIARY, NOW.date().isoformat())
        app.role_journal.save(JournalDraft(JournalContext(key, context.scope, "UTC"),
            body="梦里已经掌握全部水彩技法。"), expected_revision=0,
            operation_id="journal-save", observed_at=app.now())
        prepared = app.growth_progress.prepare(context, "原角色人格提示", "journal", "journal-save")
        self.assertNotIn("梦里已经掌握", json.dumps(prepared["receipt"], ensure_ascii=False))
        self.assertIn("不证明", prepared["receipt"]["statements"][0])
        async def decline(_):
            return answered('{"growth_id":null,"progress_note":null}')
        self.model_behavior = decline
        report = await app.growth_progress.run(context, "原角色人格提示", "journal", "journal-save")
        self.assertEqual(report["state"], "succeeded")
        self.assertEqual(GrowthProgressManagement(app).list(operator=self.core, context=context).unwrap()["items"], [])
        self.assertEqual(app.role_growth.record(active["growth_id"],
            owner=app.role_growth_context.reader.owner(context)).revision, 2)

    async def test_reject_and_revision_conflict_leave_ledger_unchanged(self):
        app, context, manager, active, _ = await self.setup_growth()
        review = await self.propose(app, context, active, self.complete(app, context))
        item = review.list(operator=self.core, context=context).unwrap()["items"][0]
        rejected = review.command(operator=self.core, context=context, review_id=item["review_id"],
            action="reject", expected_revision=2, view_token=item["view_token"],
            operation_key="reject-progress").unwrap()
        self.assertEqual((rejected["state"], rejected["applied_revision"]), ("rejected", None))
        self.assertEqual(review.list(operator=self.core, context=context).unwrap()["items"], [])
        self.assertEqual(app.role_growth.record(active["growth_id"],
            owner=app.role_growth_context.reader.owner(context)).revision, 2)
        second = await self.propose(app, context, active, self.complete(app, context, "second"))
        pending = second.list(operator=self.core, context=context).unwrap()["items"][0]
        manager.command(operator=self.core, context=context, growth_id=active["growth_id"],
            expected_revision=2, view_token=active["view_token"],
            operation_key="pause-growth", action="pause").unwrap()
        stale = second.list(operator=self.core, context=context).unwrap()["items"][0]
        self.assertEqual(stale["unavailable_reason"], "growth_revision_conflict")
        denied = second.command(operator=self.core, context=context, review_id=pending["review_id"],
            action="accept", expected_revision=2, view_token=pending["view_token"],
            operation_key="stale-accept")
        self.assertEqual(denied.failure.code, "growth_revision_conflict")

    async def test_revoked_source_and_other_participant_cannot_accept(self):
        app, context, _, active, source = await self.setup_growth()
        review = await self.propose(app, context, active, self.complete(app, context))
        item = review.list(operator=self.core, context=context).unwrap()["items"][0]
        other_scope = replace(SCOPE, native_scope_id="native-other",
                              conversation_id="conversation-other", session_id="session-other")
        self.personas.register_route(ConversationRoute(other_scope, user=self.standard.subject),
                                     observed_at=NOW)
        other = TaskContext(self.standard,
            self.identity.resolve_role(other_scope, observed_at=NOW).unwrap(),
            AudienceRef(other_scope, (self.standard.subject,)))
        self.assertEqual(review.list(operator=self.core, context=other).unwrap()["items"], [])
        app.role_journal.sources.revoke(source, expected_governance_revision=1,
                                        observed_at=app.now()).unwrap()
        hidden = review.list(operator=self.core, context=context).unwrap()["items"][0]
        self.assertEqual((hidden["progress_note"], hidden["actions"], hidden["unavailable_reason"]),
                         (None, ["reject"], "source_revoked"))
        denied = review.command(operator=self.core, context=context, review_id=item["review_id"],
            action="accept", expected_revision=2, view_token=item["view_token"],
            operation_key="revoked-accept")
        self.assertEqual(denied.failure.code, "source_revoked")
        self.assertEqual(review.command(operator=self.core, context=context, review_id=item["review_id"],
            action="reject", expected_revision=2, view_token=hidden["view_token"],
            operation_key="dismiss-revoked").unwrap()["state"], "rejected")

    async def test_scan_skips_other_private_scope_for_same_role(self):
        app, context, _, _, _ = await self.setup_growth()
        other_scope = replace(SCOPE, native_scope_id="native-other",
                              conversation_id="conversation-other", session_id="session-other")
        self.personas.register_route(ConversationRoute(other_scope, user=self.important.subject),
                                     observed_at=NOW)
        other = TaskContext(self.important, self.identity.resolve_role(other_scope, observed_at=NOW).unwrap(),
                            AudienceRef(other_scope, (self.important.subject,)))
        self.complete(app, other, "other-scope")
        expected = self.complete(app, context, "original-scope")
        self.assertEqual(app.growth_progress._next_receipt(context), ("activity", expected))

    async def test_transient_receipt_failure_retries_same_row_and_restart_keeps_review(self):
        app, context, _, active, _ = await self.setup_growth()
        operation_id = self.complete(app, context)
        with patch.object(app.growth_progress, "prepare",
                          side_effect=TaskError("source_unavailable", "temporary")):
            with self.assertRaises(TaskError) as failure:
                app.growth_progress._next_receipt(context)
        self.assertEqual(failure.exception.code, "source_unavailable")
        self.assertEqual(app.growth_progress._next_receipt(context), ("activity", operation_id))
        review = await self.propose(app, context, active, operation_id)
        original = review.list(operator=self.core, context=context).unwrap()["items"][0]
        await app.close()
        restarted = await self.start(self.host(runtime=self.open_runtime()), 1, 1)
        current = restarted.application
        recovered = GrowthProgressManagement(current).list(operator=self.core, context=context).unwrap()["items"]
        self.assertEqual(recovered[0]["review_id"], original["review_id"])
        self.assertTrue(app.growth_progress.closed)
        with self.assertRaises(TaskError):
            await app.growth_progress.run(context, "原角色人格提示", "activity", operation_id)


if __name__ == "__main__":
    unittest.main()

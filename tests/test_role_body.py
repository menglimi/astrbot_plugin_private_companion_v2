"""A single role body across private windows, without widening source audiences."""

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from companion_v2.conversation.state_context import ConversationStateContext
from companion_v2.execution.models import TaskContext, TaskError, TaskSpec, digest, encode
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.identity_policy.private_domain import source_ref
from companion_v2.role_work.state.management import StateManagement
from companion_v2.role_work.state.maintenance import KIND
from tests.test_management_access import SCOPE
from tests.test_role_cycle import assertion
from tests.test_role_state import StateFixture, state_data


class RoleBodyTests(StateFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.host1, self.app, self.ctx, self.manager = self.setup_state()
        self.configure(self.manager, enabled=True, mood_enabled=True, cycle_enabled=True, cycle_initialization="first_day")
        self.other = self.new_window("other", self.standard)

    def new_window(self, name, actor):
        scope = replace(SCOPE, native_scope_id=name, conversation_id=name, session_id=name)
        self.personas.register_route(ConversationRoute(scope, user=actor.subject), observed_at=self.clock.now())
        self.grant(actor, scope, "conversation.reply")
        binding = self.identity.resolve_role(scope, observed_at=self.clock.now()).unwrap()
        context = TaskContext(actor, binding, AudienceRef(scope, (actor.subject,)))
        self.configure(StateManagement(self.app, context), enabled=True, cycle_enabled=True, cycle_initialization="first_day")
        return context

    def write(self, context=None, key="write", revision=None, **values):
        context = context or self.ctx
        current = self.app.role_state.records.get(context, "current")
        return self.app.role_state.write(context, data=state_data(**values),
            expected_revision=revision if revision is not None else current["revision"] if current else 0, operation_key=key)

    async def test_all_simulated_persona_state_follows_the_role_across_windows(self):
        self.write(energy=42, hunger="有些饿", health="精神还好", sleep="有点困", cycle=assertion(),
            mood="心情平和", location="在自己的房间", busy="整理今天的想法", presence="休息中",
            online_mode="away", conditions=[
                {"kind": "busy", "text": "在自己的安排里", "expires_at": None},
                {"kind": "mood", "text": "心情渐渐平缓", "expires_at": None}])
        first = self.app.role_state.read(self.ctx)
        other = self.app.role_state.read(self.other)
        self.assertEqual(first["values"], other["values"])
        self.assertEqual(first["cycle_timeline"], other["cycle_timeline"])
        self.assertNotIn("changed_by", other)
        self.clock.advance(timedelta(days=5))
        self.write(self.other, key="next-window", energy=43)
        self.assertEqual(self.app.role_state.read(self.ctx)["cycle_timeline"]["anchor_date"], first["cycle_timeline"]["anchor_date"])
        self.assertEqual(self.app.role_state.read(self.ctx)["cycle_timeline"]["cycle_day"], 6)
        self.assertEqual(self.app.role_state.read(self.ctx)["values"]["energy"], 43)

    async def test_global_compare_and_swap_but_operation_keys_remain_window_owned(self):
        first = self.write(key="same", revision=0, hunger="饿")
        with self.assertRaises(TaskError) as caught:
            self.write(self.other, key="stale", revision=0, hunger="不饿")
        self.assertEqual(caught.exception.code, "record_revision_conflict")
        second = self.write(self.other, key="same", hunger="想吃点东西")
        self.assertNotEqual(first["operation_id"], second["operation_id"])
        self.assertEqual(second["revision"], 2)
        replay = self.write(key="same", revision=0, hunger="饿")
        self.assertTrue(replay["replayed"])
        self.assertEqual(self.app.role_state.read(self.ctx)["values"]["hunger"], "想吃点东西")

    async def test_persona_state_is_shared_without_sharing_its_private_source(self):
        source = self.source(self.app, self.ctx)
        self.app.role_state.write(self.ctx, data=state_data(energy=48, hunger="有些饿", health="精神还好",
            sleep="有点困", cycle=assertion(), mood="心情平和", location="在自己的房间",
            busy="整理今天的想法"),
            expected_revision=0, operation_key="private", sources=(source,))
        same_human = self.new_window("same-human-new-session", self.important)
        for context in (self.other, same_human):
            view = self.app.role_state.read(context)
            self.assertEqual(view["values"]["energy"], 48)
            self.assertEqual(view["values"]["hunger"], "有些饿")
            self.assertEqual(view["values"]["health"], "精神还好")
            self.assertEqual(view["values"]["sleep"], "有点困")
            self.assertIsNotNone(view["values"]["cycle"])
            self.assertIn("cycle_timeline", view)
            self.assertEqual(view["values"]["mood"], "心情平和")
            self.assertEqual(view["values"]["location"], "在自己的房间")
            self.assertEqual(view["values"]["busy"], "整理今天的想法")
        record = self.app.role_state.records.get(self.ctx, "current")
        self.assertFalse(self.app.role_state.evidence.shared(self.ctx, (source,)))
        self.assertTrue(self.app.role_state.evidence.visible(self.other, record["sources"], at=self.clock.now()))
        settings = self.app.role_state.settings(self.other)[0]
        cycle_preview, _ = self.app.role_state.cycles.preview(self.other, settings, self.clock.now())
        self.assertIsNotNone(cycle_preview)
        old = self.app.role_state.records.get(self.ctx, "current")["cycle_clock"]
        self.write(self.other, key="independent-body", energy=30)
        # A window may update the shared role body but cannot reset or fabricate its clock.
        self.assertEqual(self.app.role_state.records.get(self.ctx, "current")["cycle_clock"]["anchor_date"], old["anchor_date"])
        self.assertIn("cycle_timeline", self.app.role_state.read(self.other))
        self.assertIn("cycle_timeline", self.app.role_state.read(self.ctx))

    async def test_public_body_carry_rechecks_revocation_without_accepting_foreign_user_sources(self):
        self.write(hunger="饿", cycle=assertion())
        original = source_ref(self.app.role_state.records.get(self.ctx, "current")["sources"][0])
        with self.assertRaises(TaskError) as caught:
            self.app.role_state.write(self.other, data=state_data(), expected_revision=1,
                operation_key="foreign-direct", sources=(original,))
        self.assertEqual(caught.exception.code, "domain_source_scope")
        self.app.role_state.write(self.other, data=state_data(hunger="仍然饿"), expected_revision=1,
            operation_key="projected", sources=(original,), projected_inputs=True)
        self.assertEqual(self.app.role_state.read(self.ctx)["values"]["hunger"], "仍然饿")
        self.revoke_source(self.app, original)
        for context in (self.ctx, self.other):
            with self.assertRaises(TaskError):
                self.app.role_state.read(context)

    async def test_shared_snapshot_uses_original_version_and_invalidates_unsent_work(self):
        self.write(energy=40, cycle=assertion())
        consumer = ConversationStateContext(self.app.role_state)
        captured = consumer.capture(self.other, self.clock.now())
        before = consumer.contributions(captured, self.other, self.clock.now())
        self.assertEqual(before[0].source.scope, self.other.scope)
        self.clock.advance(timedelta(days=1))
        self.write(key="new", energy=50)
        with self.assertRaises(TaskError):
            consumer.contributions(captured, self.other, self.clock.now())
        self.assertEqual(consumer.contributions(captured, self.other, self.clock.now(), historical=True), before)

    async def test_legacy_adoption_keeps_old_snapshot_receipts_and_sources(self):
        service = self.app.role_state
        with patch.object(service.records, "change", service.records.legacy.change):
            old = self.write(key="old", energy=11, cycle=assertion())
        consumer = ConversationStateContext(service)
        snapshot = consumer.capture(self.ctx, self.clock.now())
        snapshot = {k: v for k, v in snapshot.items() if k not in ("projection_version", "storage", "sleep", "source")}
        before = consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True)
        legacy = service.records.legacy.get(self.ctx, "current")
        self.assertEqual(service.read(self.other)["state"], "unknown")
        self.write(key="adopt", energy=12)
        self.assertEqual(service.records.storage(self.ctx), "role")
        self.assertEqual(service.records.legacy.get(self.ctx, "current"), legacy)
        self.assertEqual(consumer.contributions(snapshot, self.ctx, self.clock.now(), historical=True), before)
        self.assertTrue(self.write(key="old", revision=0, energy=11, cycle=assertion())["replayed"])
        self.assertEqual(service.records.receipt(self.ctx, old["operation_id"])["revision"], 1)

    async def test_two_windows_prepared_at_one_revision_cannot_overwrite_each_other(self):
        await self.start(self.host1)
        maintenance = self.app.state_maintenance
        for context in (self.ctx, self.other):
            maintenance.bind(context, "原角色")
        job = maintenance.prepare(self.other, "原角色", "held")
        spec = TaskSpec("held", self.other, KIND, digest(job), "held", self.clock.now(), self.clock.now() + timedelta(minutes=3))
        maintenance.pending["held"] = job
        self.assertTrue(maintenance.validate(spec, self.clock.now()).is_success)
        self.write(energy=60)
        self.assertEqual(maintenance.validate(spec, self.clock.now()).failure.code, "state_changed")

    async def test_cycle_natural_seed_and_enablement_follow_role_while_permissions_remain_per_window(self):
        self.assertEqual(self.app.role_state.cycles.seed(self.ctx), self.app.role_state.cycles.seed(self.other))
        self.write(cycle=assertion(), energy=20)
        self.configure(StateManagement(self.app, self.other), enabled=False)
        with self.assertRaises(TaskError):
            self.app.role_state.read(self.other)
        self.assertEqual(self.app.role_state.read(self.ctx)["state"], "disabled")

    async def test_persona_settings_share_while_platform_presentation_stays_window_scoped(self):
        other_manager = StateManagement(self.app, self.other)
        old = other_manager.status(self.core).unwrap()
        self.configure(self.manager, cycle_menstrual_days=4, cycle_variation_enabled=True, hunger_enabled=False,
                       typing_enabled=True, maintenance_minutes=40)
        settings, _ = self.app.role_state.settings(self.other)
        self.assertEqual(settings["cycle_menstrual_days"], 4)
        self.assertTrue(settings["cycle_variation_enabled"])
        self.assertFalse(settings["hunger_enabled"])
        self.assertFalse(settings["typing_enabled"])
        self.assertEqual(settings["maintenance_minutes"], 40)
        stale = other_manager.command(self.core, dict(action="configure", operation_key="stale-config",
            edit_token=old["edit_token"], changes={"cycle_menstrual_days": 8}))
        self.assertEqual(stale.failure.code, "configuration_revision_conflict")
        self.configure(other_manager, health_enabled=False)
        self.assertTrue(self.app.role_state.settings(self.ctx)[0]["enabled"])
        self.assertEqual(self.app.role_state.settings(self.ctx)[0]["maintenance_minutes"], 40)
        self.assertFalse(self.app.role_state.settings(self.ctx)[0]["health_enabled"])
        self.assertEqual(self.app.role_state.settings(self.ctx)[0]["cycle_menstrual_days"], 4)

    async def test_legacy_window_token_cannot_overwrite_another_windows_adopted_same_revision(self):
        service = self.app.role_state
        with patch.object(service.records, "change", service.records.legacy.change):
            self.write(energy=10)
            self.write(self.other, energy=20)
            self.write(self.other, key="second", energy=21)
        manager = StateManagement(self.app, self.other)
        old = manager.status(self.core).unwrap()["state"]
        self.write(key="adopt", energy=50)
        self.assertEqual(service.read(self.other)["revision"], old["revision"])
        attempt = manager.command(self.core, dict(action="state.write", operation_key="obsolete",
            expected_revision=old["revision"], view_token=old["view_token"], data=state_data(energy=21)))
        self.assertEqual(attempt.failure.code, "state_view_stale")

    async def test_cycle_calibration_detects_settings_changed_from_another_window(self):
        before = self.manager.status(self.core).unwrap()
        command = dict(action="cycle.align", operation_key="reviewed-calibration",
            expected_revision=before["state"]["revision"], view_token=before["state"]["view_token"],
            settings_token=before["cycle_settings_token"], data={"applicability": "applicable", "day": 2})
        other_manager = StateManagement(self.app, self.other)
        self.configure(other_manager, cycle_timezone="UTC", cycle_menstrual_days=6)
        stale = self.manager.command(self.core, command)
        self.assertEqual(stale.failure.code, "role_cycle_settings_conflict")
        current = self.manager.status(self.core).unwrap()
        self.assertEqual(current["state"]["revision"], before["state"]["revision"])
        self.assertNotEqual(current["cycle_settings_token"], command["settings_token"])
        accepted = self.manager.command(self.core, command | {"settings_token": current["cycle_settings_token"]})
        self.assertTrue(accepted.is_success, accepted.failure)
        own = self.app.role_state.read(self.ctx)["cycle_timeline"]
        shared = self.app.role_state.read(self.other)["cycle_timeline"]
        self.assertEqual(own, shared)
        self.assertEqual((own["timezone"], own["cycle_day"], own["phase_days"]), ("UTC", 2, 6))
        self.assertEqual(self.called, [])
        self.assertEqual(self.sent, [])

    async def test_projection_is_governed_and_withdrawal_reaches_derived_reply_material(self):
        self.write(energy=20, hunger="有点饿")
        original = source_ref(self.app.role_state.records.get(self.ctx, "current")["sources"][0])
        consumer = ConversationStateContext(self.app.role_state)
        snapshot = consumer.capture(self.other, self.clock.now())
        projection = consumer.contributions(snapshot, self.other, self.clock.now())[0].source
        repository = self.app.role_state.access.sources
        self.assertTrue(repository.validate_reference(projection, observed_at=self.clock.now()).is_success)
        self.assertNotEqual(projection, original)
        self.revoke_source(self.app, original)
        self.assertFalse(repository.validate_reference(projection, observed_at=self.clock.now()).is_success)
        with self.assertRaises(TaskError):
            consumer.contributions(snapshot, self.other, self.clock.now(), historical=True)

    async def test_cycle_episode_and_variation_do_not_restart_on_another_window(self):
        self.configure(self.manager, cycle_discomfort_enabled=True, cycle_variation_enabled=True)
        self.write(cycle=assertion() | {"feeling": {"episode_id": None, "trend": "continuing"}})
        before = self.app.role_state.read(self.ctx)
        episode = before["cycle_feeling"]["episode_id"]
        self.clock.advance(timedelta(minutes=20))
        self.write(self.other, key="continuing", cycle=assertion() | {"feeling": {"episode_id": episode, "trend": "easing"}})
        after = self.app.role_state.read(self.ctx)
        self.assertEqual(after["cycle_feeling"]["episode_id"], episode)
        self.assertEqual(after["cycle_feeling"]["trend"], "easing")
        self.assertEqual(after["cycle_timeline"]["phase_plan"], before["cycle_timeline"]["phase_plan"])


if __name__ == "__main__":
    unittest.main()

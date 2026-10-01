"""Growth prompt material stays behind current identity and source governance."""

from dataclasses import replace
from datetime import datetime, timedelta
import json
import unittest

from companion_v2.conversation.growth_context import ConversationRoleGrowthContext, MAX_GROWTH_RECORDS, MAX_PAYLOAD_CHARS
from companion_v2.conversation.messages import ConversationMessages
from companion_v2.conversation.foreground import ModelDraft
from companion_v2.execution.models import TaskError, Lane, digest
from companion_v2.foundation.refs import AudienceRef, SourceRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.models import AuthorizationTier
from companion_v2.model_gateway.models import Amount, ProviderResponse
from companion_v2.role_work.growth import GrowthKind, GrowthState, PersistentRoleGrowthLedger, RoleGrowthContextReader, RoleGrowthRecord
from companion_v2.sources.models import SourceRecord
from tests.test_conversation_messages import MessageFixture
from tests.test_management_access import NOW, SCOPE


class RoleGrowthContextTests(MessageFixture, unittest.IsolatedAsyncioTestCase):
    def components(self, runtime, *, takeover=False):
        tasks, messages, delivery = super().components(runtime, takeover=takeover)
        reader = RoleGrowthContextReader(PersistentRoleGrowthLedger(runtime, now=self.clock.now), tasks)
        messages.role_growth_context = ConversationRoleGrowthContext(reader)
        return tasks, messages, delivery

    def setUp(self):
        super().setUp()
        self.reader = self.messages.role_growth_context.reader
        self.ledger = self.reader.ledger

    def create_growth(self, growth_id="growth-a", *, state=GrowthState.ACTIVE, context=None,
                      expires_at=None, sources=None, **changes):
        context = context or self.context
        evidence = self.event("evidence-" + growth_id, context=context, expires_at=expires_at)
        scope = context.scope
        owner = self.reader.owner(context)
        record = RoleGrowthRecord(
            growth_id=growth_id, owner=owner, scope=scope, kind=GrowthKind.GOAL,
            title="稳定练习水彩风景", description="在周末继续练习构图。",
            progress_note="已经收集了几张参考图。", sources=sources or (evidence.source,),
            created_at=NOW, updated_at=NOW, proposed_by=context.actor.subject,
        )
        record = replace(record, **changes)
        self.ledger.add(record)
        if state is not GrowthState.PROPOSED:
            record = self.ledger.confirm(growth_id, owner=owner, scope=scope, expected_revision=1,
                operation_id="confirm-" + growth_id, actor=context.actor.subject, observed_at=record.updated_at)
            if state is not GrowthState.ACTIVE:
                record = self.ledger.transition(growth_id, owner=owner, scope=scope, expected_revision=2,
                    operation_id="close-" + growth_id, actor=context.actor.subject, state=state,
                    observed_at=record.updated_at)
        return record

    def revise(self, record):
        return self.ledger.revise(record.growth_id, owner=record.owner, scope=record.scope,
            expected_revision=record.revision, operation_id="correction-" + record.growth_id,
            title="更正后的目标", description="重新审阅。", progress_note="待确认的新进展。",
            sources=record.sources, actor=self.context.actor.subject, observed_at=self.clock.now())

    @staticmethod
    def materials(request):
        return [item for item in request.context.materials if item.owner == "role.growth"
                and item.purpose != "role_growth_context"]

    def snapshot(self, batch):
        return json.loads(self.messages.batch(batch)["contributions_json"])["role_growth"]

    async def test_confirmed_current_growth_enters_prompt_from_sealed_reference(self):
        self.create_growth()
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        snapshot = self.snapshot(batch)
        self.assertEqual(snapshot["references"], [{"growth_id": "growth-a", "revision": 2}])
        request = self.messages._request(self.messages.batch(batch), self.context, NOW)
        materials = [item for item in request.context.materials if item.owner == "role.growth"]
        self.assertEqual([item.purpose for item in materials], ["role_growth_context", "role_growth_goal"])
        self.assertEqual(json.loads(materials[1].payload)["progress_note"], "已经收集了几张参考图。")
        self.assertIn("不是用户的目标", request.instruction)

    async def test_proposals_are_not_prompt_material(self):
        self.create_growth(state=GrowthState.PROPOSED)
        self.create_growth("achieved", state=GrowthState.ACHIEVED)
        self.create_growth("retired", state=GrowthState.RETIRED)
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.assertEqual(self.snapshot(batch)["references"], [])

    async def test_revoked_identity_binding_is_rechecked_after_capture(self):
        self.create_growth()
        snapshot = self.messages.role_growth_context.capture(self.context, NOW)
        self.identity.revoke_binding(self.context.actor.binding_id,
            expected_revision=self.identity.revision, revoked_at=NOW)
        with self.assertRaises(TaskError) as error:
            self.reader.read(snapshot["references"], self.context, NOW)
        self.assertEqual(error.exception.code, "binding_revoked")

    async def test_source_revocation_after_capture_blocks_prompt_reconstruction(self):
        record = self.create_growth()
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        self.messages.sources.revoke(record.sources[0], expected_governance_revision=1,
                                     observed_at=NOW).unwrap()
        with self.assertRaises(TaskError) as error:
            self.messages._request(self.messages.batch(batch), self.context, NOW)
        self.assertEqual(error.exception.code, "source_revoked")

    async def test_revision_after_capture_cannot_replace_the_sealed_growth(self):
        record = self.create_growth()
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        owner = record.owner
        self.ledger.revise(record.growth_id, owner=owner, scope=record.scope, expected_revision=2,
            operation_id="revise-growth-a", title=record.title, description=record.description,
            progress_note="新的修订需要重新确认。", sources=record.sources,
            actor=self.important.subject, observed_at=NOW + timedelta(seconds=1))
        with self.assertRaises(TaskError) as error:
            self.messages._request(self.messages.batch(batch), self.context, NOW + timedelta(seconds=2))
        self.assertEqual(error.exception.code, "growth_context_changed")

    async def test_expanded_audience_cannot_reuse_private_growth_snapshot(self):
        self.create_growth()
        snapshot = self.messages.role_growth_context.capture(self.context, NOW)
        expanded = replace(self.context, audience=AudienceRef(SCOPE,
            (self.important.subject, SubjectRef(SCOPE.installation_id, SubjectKind.HUMAN, "bystander"))))
        self.assertEqual(self.messages.role_growth_context.capture(expanded, NOW)["state"], "unavailable")
        with self.assertRaises(TaskError) as error:
            self.messages.role_growth_context.contributions({**snapshot, "context_key": expanded.key}, expanded, NOW)
        self.assertEqual(error.exception.code, "growth_context_private_audience_required")

    async def test_read_grant_revocation_blocks_queued_send_but_fresh_chat_can_continue(self):
        self.create_growth()
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
            expected_revision=self.policy.revision, observed_at=NOW)
        for action in ("conversation.reply", "configuration.read"):
            self.grant(self.important, SCOPE, action)
        grant = self.grant(self.important, SCOPE, "role.growth.read")
        batch = await self.generate()
        self.assertEqual(len(self.materials(self.called[-1][1].original)), 1)
        self.delivery.queue_next(self.context, batch, deadline_at=self.deadline).unwrap()
        self.identity.revoke_grant(grant.grant_id, expected_revision=self.identity.revision, revoked_at=NOW)
        await self.runner().run_once(Lane.FOREGROUND)
        self.assertEqual(self.sent, [])
        fresh = await self.generate(self.event("fresh"))
        self.assertEqual(self.snapshot(fresh)["reason"], "authorization_revoked")
        self.assertEqual(self.materials(self.called[-1][1].original), [])
        await self.deliver_next(fresh)
        self.assertEqual(len(self.sent), 1)

    async def test_revision_during_model_generation_discards_stale_draft(self):
        record = self.create_growth()
        async def change(envelope):
            self.assertEqual(len(self.materials(envelope.original)), 1)
            self.revise(record)
            return ProviderResponse("generated", ModelDraft("旧进展生成的回答。", ()), Amount(15, 40), "usage")
        self.responses["primary"] = change
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        task = (await self.runner().run_once(Lane.FOREGROUND)).unwrap().task
        self.assertEqual(task.state, "failed")
        self.assertEqual(self.parts(batch), ())
        self.assertEqual(self.sent, [])
        self.assertEqual((self.call_rows()[0]["state"], self.call_rows()[0]["actual_tokens"]), ("discarded", 15))

    async def test_expiration_between_parts_preserves_receipt_and_hides_history_body(self):
        self.create_growth(expires_at=NOW + timedelta(seconds=1))
        batch = await self.generate()
        await self.deliver_next(batch)
        receipt = dict(self.runtime.read_one("SELECT * FROM conversation_delivery_receipts", ()))
        self.clock.advance(timedelta(seconds=2))
        denied = self.delivery.queue_next(self.context, batch, deadline_at=self.deadline)
        self.assertEqual(denied.failure.code, "source_expired")
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(self.history()[0]["body_available"])
        self.assertEqual(dict(self.runtime.read_one("SELECT * FROM conversation_delivery_receipts", ())), receipt)

    async def test_cross_subject_scope_and_source_audience_are_checked(self):
        own = self.create_growth()
        other_context = self.context_for(self.standard)
        self.grant(self.standard, other_context.scope, "role.growth.read")
        other = self.create_growth("other-user", context=other_context)
        consumer = self.messages.role_growth_context
        own_snapshot = consumer.capture(self.context, NOW)
        self.assertEqual(own_snapshot["references"], [{"growth_id": own.growth_id, "revision": own.revision}])
        self.assertEqual(consumer.capture(other_context, NOW)["references"],
                         [{"growth_id": other.growth_id, "revision": other.revision}])
        with self.assertRaises(TaskError):
            self.reader.read(own_snapshot["references"], other_context, NOW)
        wrong_source_record = self.create_growth("wrong-source", sources=other.sources)
        hidden_source = replace(own.sources[0], source_id="hidden", version=replace(own.sources[0].version, lineage_id="hidden"))
        self.messages.sources.publish(SourceRecord(hidden_source, AudienceRef(SCOPE, (self.standard.subject,)),
            digest("hidden body"), "hidden body"), observed_at=NOW).unwrap()
        hidden = self.create_growth("hidden-audience", sources=(hidden_source,))
        snapshot = consumer.capture(self.context, NOW)
        self.assertEqual(snapshot["references"], own_snapshot["references"])
        self.assertEqual(snapshot["skipped"], 2)
        for record, code in ((wrong_source_record, "growth_context_scope"), (hidden, "source_audience_denied")):
            with self.subTest(record=record.growth_id), self.assertRaises(TaskError) as error:
                self.reader.read([{"growth_id": record.growth_id, "revision": record.revision}], self.context, NOW)
            self.assertEqual(error.exception.code, code)

    async def test_same_participant_new_session_and_new_persona_do_not_inherit_growth(self):
        self.create_growth()
        new_context = self.context_for(self.important, replace(SCOPE, session_id="new-session"))
        self.assertEqual(self.reader.candidates(new_context, NOW).items, ())
        current = self.personas.binding("base")
        other = SubjectRef(SCOPE.installation_id, SubjectKind.BOT, "other-role")
        self.personas.set_binding(replace(current, role=other, revision=current.revision + 1),
            expected_revision=current.revision, observed_at=NOW)
        with self.assertRaises(TaskError) as error:
            self.reader.candidates(self.context, NOW)
        self.assertEqual(error.exception.code, "role_binding_changed")
        self.context = self.context_for(self.important)
        self.assertEqual(self.reader.candidates(self.context, NOW).items, ())

    async def test_budgets_pin_whole_records_and_exclude_future_material(self):
        self.create_growth("large", description="长" * 8000, progress_note="长" * 8000)
        self.create_growth("future", updated_at=NOW + timedelta(seconds=10))
        for index in range(MAX_GROWTH_RECORDS + 1):
            self.create_growth("item-" + str(index))
        batch = self.accept()
        self.messages.seal(self.context, batch, deadline_at=self.deadline).unwrap()
        snapshot = self.snapshot(batch)
        self.assertEqual(len(snapshot["references"]), MAX_GROWTH_RECORDS)
        self.assertEqual(snapshot["skipped"], 1)
        self.assertTrue(snapshot["truncated"])
        self.create_growth("new-after-seal")
        await self.generate(batch=batch)
        self.assertEqual(self.snapshot(batch), snapshot)
        self.assertLessEqual(sum(len(m.payload) for m in self.materials(self.called[-1][1].original)), MAX_PAYLOAD_CHARS)

    async def test_reopen_rebuilds_only_original_selection_and_rechecks_revision(self):
        record = self.create_growth()
        batch = await self.generate()
        self.create_growth("new")
        _, messages, delivery = self.components(self.open_runtime())
        request = messages._request(messages.batch(batch), self.context, NOW)
        self.assertEqual(len(self.materials(request)), 1)
        self.revise(record)
        denied = delivery.queue_next(self.context, batch, deadline_at=self.deadline)
        self.assertEqual(denied.failure.code, "growth_context_changed")

    async def test_missing_consumer_corrupt_snapshots_and_observed_claim_cannot_bypass_owner(self):
        record = self.create_growth()
        batch = await self.generate()
        row = self.messages.batch(batch)
        saved = json.loads(row["contributions_json"])
        self.assertNotIn(record.title, row["contributions_json"])
        with self.assertRaises(TaskError) as error:
            ConversationMessages(self.tasks)._request(row, self.context, NOW)
        self.assertEqual(error.exception.code, "growth_context_unavailable")
        snapshot = saved["role_growth"]
        reference = snapshot["references"][0]
        for invalid in (None, snapshot | {"context_key": "other"}, snapshot | {"captured_at": "2026-09-21"},
                        snapshot | {"references": [reference, reference]},
                        snapshot | {"references": [reference | {"revision": True}]}):
            with self.subTest(snapshot=invalid), self.assertRaises(TaskError):
                self.messages._request(dict(row) | {"contributions_json": json.dumps(saved | {"role_growth": invalid})},
                                       self.context, NOW)
        request = self.called[-1][1].original
        self.assertTrue(all(item.source is None for item in self.materials(request)))
        self.assertNotIn(record.sources[0], request.context.evidence_sources)


class GrowthSelectionAndHistoryTests(RoleGrowthContextTests):
    """Skills reach the prompt in a useful order, and carry their own development."""

    def source_at(self, identifier, issued_at):
        """Publish a source issued at a chosen time, so a record may be backdated.

        ``self.event`` always stamps its source at NOW, and a growth record whose
        timestamps precede its evidence is refused, so recency has to be built from
        an explicitly dated source.
        """
        reference = SourceRef("source-dated-" + digest([identifier]),
                              "conversation", self.context.scope,
                              VersionRef(digest([identifier]), 1), issued_at)
        body = "private input " + identifier
        self.messages.sources.publish(
            SourceRecord(reference, self.context.audience, digest(body), body),
            observed_at=issued_at).unwrap()
        return reference

    def skill(self, growth_id, *, at, **changes):
        """One confirmed skill whose single source is dated to match it."""
        changes.setdefault("sources", (self.source_at(growth_id, at),))
        return self.create_growth(growth_id, kind=GrowthKind.SKILL,
                                  created_at=at, updated_at=at, **changes)

    def note_payloads(self, candidates):
        return [json.loads(item.payload) for item in candidates.items]

    def test_the_most_recently_developed_skill_comes_first(self):
        older = self.skill("skill-old", at=NOW - timedelta(days=30))
        newer = self.skill("skill-new", at=NOW - timedelta(days=1))
        candidates = self.reader.candidates(self.context, NOW)
        self.assertEqual(len(candidates.items), 2, candidates.items)
        # "skill-new" was developed most recently, so it must be the one a limited
        # context budget keeps. Ordering by id alone would have kept "skill-old".
        self.assertEqual(candidates.items[0].reference["growth_id"], newer.growth_id)
        self.assertEqual(candidates.items[1].reference["growth_id"], older.growth_id)

    def test_an_active_skill_outranks_a_paused_one_at_the_same_time(self):
        self.skill("skill-paused", at=NOW, state=GrowthState.PAUSED)
        self.skill("skill-active", at=NOW, state=GrowthState.ACTIVE)
        candidates = self.reader.candidates(self.context, NOW)
        self.assertEqual([item.reference["growth_id"] for item in candidates.items],
                         ["skill-active", "skill-paused"])

    def test_the_order_is_total_so_two_runs_agree(self):
        for name in ("skill-c", "skill-a", "skill-b"):
            self.skill(name, at=NOW)
        first = [item.reference["growth_id"] for item in
                 self.reader.candidates(self.context, NOW).items]
        second = [item.reference["growth_id"] for item in
                  self.reader.candidates(self.context, NOW).items]
        self.assertEqual(first, second)
        self.assertEqual(first, ["skill-a", "skill-b", "skill-c"])

    def revise_note(self, record, index, note):
        """Revise a progress note and re-confirm it.

        A revision returns the record to PROPOSED — the change has to be confirmed
        again before it counts — and only ACTIVE/PAUSED records enter a prompt, so an
        unconfirmed revision is deliberately invisible to the reader.
        """
        revised = self.ledger.revise(record.growth_id, owner=record.owner, scope=record.scope,
            expected_revision=record.revision, operation_id=f"rev-{index}", title=record.title,
            description=record.description, progress_note=note,
            sources=record.sources, actor=self.context.actor.subject, observed_at=NOW)
        return self.ledger.confirm(revised.growth_id, owner=revised.owner, scope=revised.scope,
            expected_revision=revised.revision, operation_id=f"confirm-{index}",
            actor=self.context.actor.subject, observed_at=NOW)

    def test_a_skill_carries_its_earlier_progress_notes(self):
        record = self.skill("skill-water", at=NOW)
        first = self.revise_note(record, 2, "能把静物画完了。")
        self.revise_note(first, 3, "第一次画了风景。")
        payload = self.note_payloads(self.reader.candidates(self.context, NOW))[0]
        self.assertEqual(payload["progress_note"], "第一次画了风景。")
        notes = [item["progress_note"] for item in payload["progress_history"]]
        # Oldest first, and the current note is not repeated inside its own history.
        self.assertEqual(notes, ["已经收集了几张参考图。", "能把静物画完了。"])
        revisions = [item["revision"] for item in payload["progress_history"]]
        # Creation lands on revision 2 (propose + confirm), and each later note costs
        # two more (revise + confirm); what matters is that they rise and stay older.
        self.assertEqual(revisions, [2, 4])
        self.assertEqual(revisions, sorted(revisions))
        self.assertEqual(len(set(revisions)), len(revisions))

    def test_history_is_capped_and_keeps_the_newest_notes(self):
        from companion_v2.role_work.growth.context import HISTORY_NOTES
        current = self.skill("skill-long", at=NOW)
        for index in range(2, HISTORY_NOTES + 4):
            current = self.revise_note(current, index, f"第{index}次进展。")
        payload = self.note_payloads(self.reader.candidates(self.context, NOW))[0]
        self.assertEqual(len(payload["progress_history"]), HISTORY_NOTES)
        revisions = [item["revision"] for item in payload["progress_history"]]
        # Strictly increasing, and every entry is genuinely older than the record.
        self.assertEqual(revisions, sorted(revisions))
        self.assertEqual(len(set(revisions)), len(revisions))
        self.assertLess(revisions[-1], current.revision)
        # The oldest note was dropped, the newest history entry was kept.
        self.assertNotIn("已经收集了几张参考图。",
                         [item["progress_note"] for item in payload["progress_history"]])
        self.assertTrue(payload["progress_history"][-1]["progress_note"].endswith("次进展。"))

    def test_progress_whose_evidence_was_withdrawn_is_not_replayed_from_history(self):
        # The note that has to disappear rests on a source the *current* revision no
        # longer names, so revoking it leaves the record readable but not its history.
        withdrawn_source = self.source_at("withdrawn-evidence", NOW)
        live_source = self.source_at("live-evidence", NOW)
        record = self.skill("skill-hidden", at=NOW, sources=(withdrawn_source,))
        hidden_note = "这段进展的依据后来被撤回了。"
        with_source = self.revise_note(record, 2, hidden_note)
        current = self.ledger.revise(with_source.growth_id, owner=with_source.owner,
            scope=with_source.scope, expected_revision=with_source.revision,
            operation_id="rev-live", title=with_source.title, description=with_source.description,
            progress_note="最近的一次进展。", sources=(live_source,),
            actor=self.context.actor.subject, observed_at=NOW)
        current = self.ledger.confirm(current.growth_id, owner=current.owner, scope=current.scope,
            expected_revision=current.revision, operation_id="confirm-live",
            actor=self.context.actor.subject, observed_at=NOW)
        self.assertGreater(current.revision, with_source.revision)
        # Before the withdrawal both the founding note and the later one are visible.
        before = self.note_payloads(self.reader.candidates(self.context, NOW))[0]
        self.assertEqual([item["progress_note"] for item in before["progress_history"]],
                         ["已经收集了几张参考图。", hidden_note])
        self.messages.sources.revoke(withdrawn_source, expected_governance_revision=1, observed_at=NOW)
        after = self.note_payloads(self.reader.candidates(self.context, NOW))[0]
        # Both notes rested on the withdrawn source, so history empties while the
        # current note — which rests on the live source — still reaches the prompt.
        self.assertEqual(after["progress_history"], [])
        self.assertEqual(after["progress_note"], "最近的一次进展。")

    def test_a_goal_still_reaches_the_prompt_without_a_history(self):
        # The narrative field must not become a requirement for simpler records.
        self.create_growth("goal-plain", kind=GrowthKind.GOAL)
        payload = self.note_payloads(self.reader.candidates(self.context, NOW))[0]
        self.assertEqual(payload["progress_history"], [])
        self.assertEqual(payload["kind"], "goal")

    def test_the_instruction_permits_qualitative_comparison_and_forbids_numbers(self):
        from companion_v2.conversation.growth_context import ROLE_GROWTH_INSTRUCTION
        for required in ("progress_history", "前后对比", "定性"):
            self.assertIn(required, ROLE_GROWTH_INSTRUCTION)
        for forbidden in ("不得由此推出等级、分数、熟练度数值", "不编造数值熟练度"):
            self.assertIn(forbidden, ROLE_GROWTH_INSTRUCTION)

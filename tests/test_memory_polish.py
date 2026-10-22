import json
import unittest
from dataclasses import replace
from contextlib import closing
from unittest.mock import patch
import sqlite3

from companion_v2.execution.models import digest, encode
from companion_v2.memory.models import AtomRef, Proposal, MemoryPolicy
from companion_v2.memory.management import MemoryManagement
from companion_v2.memory.service import MemoryService
from companion_v2.sources.privacy import redact_text, REDACTED
from tests.memory_support import MemoryFixture
from tests.test_host_application import HostFixture
from tests.test_role_tool_loop import answered, requested, call


class CoreMemoryTests(MemoryFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.service = MemoryService(self.tasks)
        self.manager = MemoryManagement(self.service, self.core)

    def snapshot(self):
        return self.service.context.capture(self.context, "pin-check", (), self.deadline)

    def test_unrelated_topic_gets_pinned_fact_independently_of_retention(self):
        pinned = self.remember(self.proposed(context_mode="pinned"))
        self.remember(replace(self.proposed(), predicate="别的偏好", retention="protected"), "protected")
        snapshot = self.snapshot()
        self.assertEqual(snapshot["core_ids"], [pinned.atom_id])
        contributions = self.service.context.contributions(snapshot, self.context)
        self.assertEqual(len([m for m in contributions if m.purpose == "pinned_memory"]), 1)

    def test_query_failure_keeps_core_context_and_source_handles(self):
        pinned = self.remember(self.proposed(context_mode="pinned"))
        with patch.object(self.service.query.fact_index, "candidates", side_effect=sqlite3.DatabaseError()):
            snapshot = self.snapshot()
        self.assertEqual(snapshot["state"], "ready")
        self.assertEqual(snapshot["core_ids"], [pinned.atom_id])
        self.assertEqual(snapshot["recall_unavailable"], "memory_index_unavailable")

    def test_cold_recall_keeps_pinned_context_and_reports_incomplete_memory(self):
        pinned = self.remember(self.proposed(context_mode="pinned"))
        self.remember(replace(self.proposed(), predicate="另一个事实"), key="second")
        self.service.query.fact_index.sync_items = 1
        snapshot = self.snapshot()
        self.assertEqual(snapshot["core_ids"], [pinned.atom_id])
        self.assertTrue(snapshot["recall_pending"])
        contributions = self.service.context.contributions(snapshot, self.context)
        self.assertTrue(any(item.purpose == "pinned_memory" for item in contributions))
        self.assertTrue(any(item.purpose == "memory_coverage" and "尚未完成" in item.payload for item in contributions))

    def test_pin_unpin_is_cas_versioned_and_keeps_original_human_evidence(self):
        ref = self.remember()
        item = self.manager.list(self.context).unwrap()["items"][0]
        args = dict(atom_id=ref.atom_id, expected_revision=ref.revision, view_token=item["view_token"], operation_key="pin", action="pin")
        receipt = self.manager.command(self.context, **args).unwrap()
        self.assertEqual(self.manager.command(self.context, **args).unwrap(), receipt)
        self.assertEqual(self.snapshot()["core_ids"], [ref.atom_id])
        current = self.memory.read(self.context, AtomRef(ref.atom_id, 2)).unwrap()
        self.assertEqual(current["attribution"], "user")
        self.assertEqual(current["evidence"][0]["source_kind"], "human_message")
        item = self.manager.list(self.context).unwrap()["items"][0]
        self.manager.command(self.context, atom_id=ref.atom_id, expected_revision=2,
            view_token=item["view_token"], operation_key="unpin", action="unpin").unwrap()
        self.assertEqual(self.snapshot()["core_ids"], [])
        self.assertEqual(self.memory.read(self.context, AtomRef(ref.atom_id, 3)).unwrap()["object"], "不喝咖啡")

    def test_core_budget_reports_omission_and_source_withdrawal_invalidates_snapshot(self):
        first = self.remember(self.proposed(context_mode="pinned"))
        self.remember(replace(self.proposed(context_mode="pinned"), predicate="另一件事"), "second")
        self.service = MemoryService(self.tasks, policy=MemoryPolicy(core_items=1))
        snapshot = self.snapshot()
        self.assertTrue(snapshot["core_omitted"])
        evidence = self.memory._valid(self.context, self.memory._head(self.context, first))[1].evidence[0]
        self.messages.sources.revoke(evidence.source, expected_governance_revision=1, observed_at=self.clock.now()).unwrap()
        with self.assertRaises(Exception):
            self.service.context.contributions(snapshot, self.context)
        self.assertEqual(self.snapshot()["core_ids"], [])

    def test_fact_fields_are_cleaned_before_any_memory_write(self):
        secret = "sk-" + "A" * 24
        ref = self.remember(replace(self.proposed(), predicate="api_key", object=secret,
            representation="api_key=" + secret, qualifiers={"password": "synthetic-secret"}))
        fact = self.memory.read(self.context, ref).unwrap()
        self.assertEqual(fact["object"], REDACTED)
        dump = "\n".join(self.runtime.read_one("SELECT record_json FROM memory_atoms WHERE atom_id = ?", (ref.atom_id,)))
        self.assertNotIn(secret, dump)
        self.assertNotIn("synthetic-secret", dump)

    def test_chat_clear_needs_no_dashboard_operator_and_echoes_a_fresh_code(self):
        self.remember()
        context = self.context_for(self.important)
        manager = MemoryManagement(self.service, None)
        preview = manager.preview_clear(context).unwrap()
        self.assertEqual(preview["counts"], {"active": 1, "already_inactive": 0})
        self.assertEqual(preview["operator_id"], self.important.subject.subject_id)
        code = MemoryManagement.confirmation_code(preview["revision_token"])
        self.assertEqual(len(code), 6)
        self.assertNotEqual(code, MemoryManagement.confirmation_code(preview["revision_token"] + "stale"))
        cleared = manager.clear(context, expected_revision_token=preview["revision_token"],
                                operation_key="chat-clear").unwrap()
        self.assertEqual(cleared["forgotten_count"], 1)
        self.assertEqual(cleared["physical_erasure"], "not_performed")
        self.assertEqual(manager.list(context).unwrap()["operator_id"], self.important.subject.subject_id)

    def test_bulk_clear_scrubs_active_and_retracted_history_and_replay_is_safe(self):
        original = self.proposed()
        active = self.remember(original, "clear-active")
        correction = replace(
            original,
            operation="correct",
            target=active,
            object="开始喝茶",
            representation="用户后来表示开始喝茶。",
            evidence=(self.evidence("最近开始喝茶"),),
        )
        active = self.memory.submit(self.context, correction, operation_key="clear-correction").unwrap()
        active = AtomRef(active["atom_id"], active["revision"])

        retracted_proposal = replace(
            self.proposed(),
            predicate="临时偏好",
            object="喜欢奶茶",
            representation="用户喜欢奶茶。",
            evidence=(self.evidence("我喜欢奶茶"),),
        )
        retracted = self.remember(retracted_proposal, "clear-retracted")
        withdrawal = replace(
            retracted_proposal,
            operation="retract",
            target=retracted,
            evidence=(self.evidence("撤回奶茶偏好"),),
        )
        self.memory.submit(self.context, withdrawal, operation_key="clear-retraction").unwrap()

        manager = MemoryManagement(self.service, self.core)
        preview = manager.preview_clear(self.context).unwrap()
        self.assertEqual(preview["counts"], {"active": 1, "already_inactive": 1})
        args = {
            "expected_revision_token": preview["revision_token"],
            "operation_key": "clear-all-private-memory",
        }
        cleared = manager.clear(self.context, **args).unwrap()
        self.assertEqual(cleared["forgotten_count"], 2)

        for atom_id in (active.atom_id, retracted.atom_id):
            history = manager.revisions(self.context, atom_id=atom_id, limit=64).unwrap()["items"]
            self.assertTrue(history)
            self.assertTrue(all(item["state"] == "invalidated" and item["content"] is None for item in history))
            rows = self.runtime.read_all(
                "SELECT record_json FROM memory_revisions WHERE atom_id = ?", (atom_id,)
            )
            self.assertTrue(all(json.loads(row["record_json"]) == {"forgotten": True} for row in rows))

        later_proposal = replace(
            original,
            predicate="新记忆",
            object="清理后写入",
            representation="清理后写入的新记忆。",
            evidence=(self.evidence("清理后新记忆"),),
        )
        later = self.remember(later_proposal, "after-clear")
        replay = manager.clear(self.context, **args).unwrap()
        self.assertEqual(replay, cleared)
        self.assertTrue(self.memory.read(self.context, later).is_success)

    def test_bulk_clear_preview_is_compare_and_swap_guarded(self):
        original = self.remember()
        manager = MemoryManagement(self.service, self.core)
        preview = manager.preview_clear(self.context).unwrap()
        after_preview = replace(
            self.proposed(),
            predicate="后续偏好",
            object="新加入",
            representation="之后加入的记忆。",
            evidence=(self.evidence("预览后新增"),),
        )
        self.remember(after_preview, "after-preview")
        result = manager.clear(
            self.context,
            expected_revision_token=preview["revision_token"],
            operation_key="stale-clear",
        )
        self.assertEqual(result.failure.code, "memory_clear_stale")
        self.assertTrue(self.memory.read(self.context, original).is_success)

    def test_search_projection_removes_only_the_forgotten_relationship(self):
        index = self.service.query.index
        index.sync("private:personal:facts", [{"id": "first", "text": "secret pear"}],
                   relationship_owner="relationship-a")
        index.sync("private:shared:facts", [{"id": "second", "text": "public plum"}],
                   relationship_owner="relationship-b")

        index.remove_owner("relationship-a")
        first, _, _ = index.rank("private:personal:facts", "pear", allowed={"first"})
        second, _, _ = index.rank("private:shared:facts", "plum", allowed={"second"})
        self.assertEqual(first, [])
        self.assertEqual(second, ["second"])

    def test_rendered_fact_budget_prioritizes_core_and_deduplicates(self):
        first = self.remember(self.proposed(context_mode="pinned"))
        second = self.remember(replace(self.proposed(), predicate="其他偏好"), "other")
        core = self.memory.read(self.context, first).unwrap()
        payload = {key: value for key, value in core.items() if key not in ("source", "evidence")}
        budget = len(encode(payload))
        self.service = MemoryService(self.tasks, policy=MemoryPolicy(inclusion_chars=budget))
        snapshot = self.snapshot()
        snapshot["references"] = [
            {"atom_id": second.atom_id, "revision": second.revision},
            {"atom_id": first.atom_id, "revision": first.revision},
            {"atom_id": first.atom_id, "revision": first.revision},
        ]
        materials = self.service.context.contributions(snapshot, self.context)
        facts = [m for m in materials if m.purpose in ("pinned_memory", "current_memory")]
        self.assertEqual([json.loads(m.payload)["atom_id"] for m in facts], [first.atom_id])
        self.assertLessEqual(sum(len(m.payload) for m in facts), budget)
        self.assertTrue(any(m.purpose == "memory_coverage" for m in materials))

    def test_history_keeps_old_values_only_while_their_evidence_is_authorized(self):
        proposal = self.proposed()
        ref = self.remember(proposal)
        corrected = replace(proposal, operation="correct", target=ref, object="喝茶",
                            representation="后来改喝茶。", evidence=(self.evidence("改喝茶"),))
        self.memory.submit(self.context, corrected, operation_key="historical-change").unwrap()
        page = self.manager.revisions(self.context, atom_id=ref.atom_id, limit=1).unwrap()
        self.assertEqual(page["items"][0]["object"], "不喝咖啡")
        self.assertEqual(page["next_revision"], 1)
        self.memory.sources.revoke(proposal.evidence[0].source, expected_governance_revision=1,
                                   observed_at=self.clock.now()).unwrap()
        hidden = self.manager.revisions(self.context, atom_id=ref.atom_id).unwrap()
        self.assertIsNone(hidden["items"][0]["content"])
        self.assertEqual(hidden["items"][1]["object"], "喝茶")
        self.assertFalse(self.manager.revisions(self.context_for(self.core), atom_id=ref.atom_id).is_success)

    def test_clear_removes_real_query_partitions_and_receipt_survives_cache_failure(self):
        proposal = self.proposed()
        self.remember(proposal)
        self.query(kind="all").unwrap()
        args = dict(expected_revision_token=self.manager.preview_clear(self.context).unwrap()["revision_token"],
                    operation_key="cleanup-cache-failure")
        with patch("companion_v2.memory.search.SearchIndex.remove_owner", side_effect=sqlite3.OperationalError()):
            result = self.manager.clear(self.context, **args).unwrap()
        self.assertEqual(result["forgotten_count"], 1)
        self.assertEqual(result["search_projection"], "cleanup_pending")
        replay = self.manager.clear(self.context, **args).unwrap()
        self.assertEqual(replay["operation_id"], result["operation_id"])
        with closing(sqlite3.connect(self.service.query.index.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 0)
        self.assertEqual(self.memory.submit(self.context, proposal, operation_key="no-resurrection").failure.code,
                         "memory_evidence_forgotten")

    def test_empty_clear_still_has_a_receipt_and_preview_binds_operator(self):
        preview = self.manager.preview_clear(self.context).unwrap()
        another = self.context_for(self.core)
        self.assertNotEqual(preview["revision_token"],
                            self.manager.preview_clear(another).unwrap()["revision_token"])
        args = dict(expected_revision_token=preview["revision_token"], operation_key="empty-clear")
        result = self.manager.clear(self.context, **args).unwrap()
        self.assertEqual(result["forgotten_count"], 0)
        self.remember()
        self.assertEqual(self.manager.clear(self.context, **args).unwrap(), result)
        self.assertEqual(len(self.query().unwrap()["items"]), 1)


class SourcePrivacyTests(unittest.TestCase):
    def test_redacts_credentials_preserving_json_and_ordinary_prose(self):
        secret = "ghp_" + "Z" * 30
        source = json.dumps({"api_key": secret, "note": "今天想看密码学这本书"}, ensure_ascii=False)
        cleaned = redact_text(source)
        self.assertEqual(json.loads(cleaned)["api_key"], REDACTED)
        self.assertIn("今天想看密码学这本书", cleaned)
        self.assertEqual(redact_text(cleaned), cleaned)
        self.assertEqual(redact_text("密码是 abc123。其他话\n保持换行"), "密码是 [REDACTED]。其他话\n保持换行")
        self.assertNotIn("private-body", redact_text("-----BEGIN PRIVATE KEY-----\nprivate-body\n-----END PRIVATE KEY-----"))

    def test_redacts_common_service_tokens_and_database_url_passwords(self):
        secrets = (
            "xoxb-" + "A" * 32,
            "mfa." + "B" * 30,
            "123456789:" + "C" * 32,
            "AKIA" + "D" * 16,
            "eyJ" + "E" * 20 + "." + "F" * 20 + "." + "G" * 20,
        )
        for secret in secrets:
            with self.subTest(secret_prefix=secret[:8]):
                self.assertNotIn(secret, redact_text("凭据 " + secret))
        astrbot_token = "abk_" + "C" * 32
        self.assertNotIn(astrbot_token, redact_text(astrbot_token))
        url = "postgresql://alice:synthetic-db-password@db.local/app"
        cleaned = redact_text(url)
        self.assertNotIn("synthetic-db-password", cleaned)
        self.assertIn("[REDACTED]", cleaned)

    def test_chinese_adjacent_tokens_and_numeric_json_remain_safe_and_parseable(self):
        secret = "sk-" + "H" * 30
        self.assertEqual(redact_text("凭据" + secret + "结束"), "凭据[REDACTED]结束")
        for value in ("not-a-token", 123456):
            source = json.dumps({"note": "密码学书籍", "password": value}, ensure_ascii=False)
            clean = redact_text(source)
            self.assertEqual(json.loads(clean), {"note": "密码学书籍", "password": REDACTED})
            self.assertEqual(redact_text(clean), clean)
        self.assertEqual(redact_text("password=alpha"), "password=[REDACTED]")
        self.assertEqual(redact_text("password=[REDACTED]"), "password=[REDACTED]")


class MemorySourceHostTests(HostFixture, unittest.IsolatedAsyncioTestCase):
    async def send_reply(self, text="我当时说窗外在下雨。", *, status="delivered"):
        async def model(envelope):
            return answered(text)
        async def send(envelope):
            return self.receipt(envelope, status)
        self.model_behavior, self.send_behavior = model, send
        host = await self.start()
        batch = host.receive(self.event("source", text="聊一聊窗外的天气")).unwrap()
        self.advance(host.application)
        await self.done(host.application, batch)
        return host.application, batch, self.context(host.application, batch)

    def recall(self, app, context, query="窗外"):
        app.memory.query.begin(context, "sources")
        return app.memory.query.query(context, "sources", query_intent=query, kind="sources").unwrap()

    async def test_confirmed_reply_is_searchable_after_query_expiry_and_keeps_bot_attribution(self):
        app, batch, context = await self.send_reply()
        self.advance(app, 700)
        result = self.recall(app, context)
        bot = [v for v in result["items"] if v["source_kind"] == "bot_message"]
        self.assertEqual(len(bot), 1)
        self.assertEqual(bot[0]["speaker_id"], context.role_binding.role.subject_id)
        raw = app.memory.query.source(context, "sources", handle=bot[0]["handle"]).unwrap()
        self.assertEqual(raw["text"], "我当时说窗外在下雨。")
        evidence = app.memory.query.resolve(context, "sources", bot[0]["handle"])
        result = app.memory.writer.submit(context, Proposal("add", predicate="天气", object="雨天",
            representation="用户说下雨", evidence=(evidence,)), operation_key="wrong-owner")
        self.assertEqual(result.failure.code, "memory_attribution_unproven")

    async def test_unknown_reply_is_not_a_memory_source(self):
        app, batch, context = await self.send_reply(status="unknown")
        result = self.recall(app, context)
        self.assertFalse(any(v["source_kind"] == "bot_message" for v in result["items"]))

    async def test_withdrawn_input_invalidates_bot_quote_and_existing_handle(self):
        app, batch, context = await self.send_reply()
        bot = next(v for v in self.recall(app, context)["items"] if v["source_kind"] == "bot_message")
        key = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))["event_key"]
        app.messages.withdraw(context, key).unwrap()
        self.assertFalse(app.memory.query.source(context, "sources", handle=bot["handle"]).is_success)
        self.assertFalse(any(v["source_kind"] == "bot_message" for v in self.recall(app, context)["items"]))

    async def test_inbound_redaction_preserves_replay_conflicts_and_never_indexes_secret(self):
        host = await self.start()
        app = host.application
        secret = "sk-" + "Q" * 24
        event = self.event("credential", text="api_key=" + secret + "\n明天去公园")
        batch = host.receive(event).unwrap()
        self.assertEqual(host.receive(event).unwrap(), batch)
        self.assertFalse(host.receive({**event, "text": "api_key=" + "sk-" + "R" * 24 + "\n明天去公园"}).is_success)
        self.advance(app)
        await self.done(app, batch)
        context = self.context(app, batch)
        result = self.recall(app, context, "公园")
        self.assertNotIn(secret, encode(result))
        self.assertIn(REDACTED, encode(result))
        for row in app.runtime.read_all("SELECT payload_json FROM sources", ()):
            self.assertNotIn(secret, row["payload_json"])
        self.assertNotIn(secret, encode(self.called[0].original))

    async def test_outbound_memory_quote_is_redacted_without_changing_sent_text(self):
        secret = "sk-" + "M" * 24
        app, batch, context = await self.send_reply("这是测试凭据 api_key=" + secret)
        result = self.recall(app, context, "测试凭据")
        bot = next(v for v in result["items"] if v["source_kind"] == "bot_message")
        self.assertNotIn(secret, bot["excerpt"])
        self.assertIn(REDACTED, bot["excerpt"])
        self.assertIn(secret, self.sent[0].text)  # The memory boundary does not rewrite platform history.

    async def test_bot_sourced_fact_can_be_read_in_a_snapshot_and_follows_withdrawal(self):
        app, batch, context = await self.send_reply()
        bot = next(v for v in self.recall(app, context)["items"] if v["source_kind"] == "bot_message")
        evidence = app.memory.query.resolve(context, "sources", bot["handle"])
        saved = app.memory.writer.submit(context, Proposal(
            "add", subject="entity:quoted-bot", predicate="当时说过", object="窗外在下雨",
            representation="Bot 当时说窗外在下雨。", attribution="bot", evidence=(evidence,),
        ), operation_key="bot-quote").unwrap()
        ref = AtomRef(saved["atom_id"], saved["revision"])
        self.advance(app, 700)
        self.assertTrue(app.memory.writer.read(context, ref).is_success)
        key = app.runtime.read_one("SELECT event_key FROM conversation_inputs WHERE batch_id = ?", (batch,))["event_key"]
        app.messages.withdraw(context, key).unwrap()
        self.assertFalse(app.memory.writer.read(context, ref).is_success)

    async def test_pinned_tool_correction_continues_and_quote_survives_query_expiry(self):
        async def model(envelope):
            materials = envelope.original.context.materials
            history = envelope.tool_history
            correcting = envelope.original.event.event_id == "correct"
            handles = json.loads(next(m.payload for m in materials if m.purpose == "current_input_handles"))
            if correcting and not history:
                return requested(call("lookup", "memory.query", query_intent="杯子"))
            if not history or (correcting and len(history) == 1):
                proposal = dict(operation="add", predicate="杯子颜色", object="蓝色",
                                representation="用户的杯子是蓝色。", evidence_handles=handles,
                                context_mode="pinned", single_value=True)
                if correcting:
                    prior = json.loads(next(m.payload for m in materials if m.purpose == "pinned_memory"))
                    proposal.update(operation="correct", object="绿色", representation="用户的杯子是绿色。",
                                    target_atom_id=prior["atom_id"], expected_revision=prior["revision"])
                return requested(call("remember", "memory.proposal.submit", proposal=proposal))
            self.assertTrue(any(m.purpose == "pinned_memory" for m in materials))
            if correcting:
                self.assertEqual(json.loads(history[0].result_json)["state"], "superseded")
                if len(history) == 2:
                    return requested(call("original", "memory.sources", handle=handles[0]))
            return answered("杯子记忆已经更正为绿色。" if correcting else "杯子记忆已保存。")
        self.model_behavior = model
        host = await self.start()
        app = host.application
        for identifier, message in (("seed", "记住，我的杯子是蓝色"), ("correct", "我的杯子改为绿色，持续记住")):
            batch = host.receive(self.event(identifier, text=message)).unwrap()
            self.advance(app)
            self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.advance(app, 700)
        context = self.context(app, batch)
        before = dict(app.runtime.read_one("SELECT * FROM memory_sessions WHERE session_id = ?", ("memory:" + batch,)))
        result = self.recall(app, context, "绿色")
        self.assertEqual(dict(app.runtime.read_one("SELECT * FROM memory_sessions WHERE session_id = ?", ("memory:" + batch,))), before)
        quotes = [v for v in result["items"] if v["source_kind"] == "bot_message"]
        self.assertEqual(len(quotes), 1)
        self.assertIn("更正为绿色", quotes[0]["excerpt"])

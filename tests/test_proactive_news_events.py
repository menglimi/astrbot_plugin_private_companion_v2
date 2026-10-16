"""Synthetic news source, durable polling, and automatic contact tests."""

import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from astrbot_host.news import (DEFAULT_AI_NEWS_FEED_LABEL, DEFAULT_AI_NEWS_FEED_URL,
                               NewsJsonPort, NewsRssPort, configured_news_port)
from astrbot_host.news_parsing import parse_rss_news
from companion_v2.proactive.external_materials import parse_news_response
from companion_v2.proactive.news_events import SOURCE_OWNER
from companion_v2.proactive.diagnostic_models import DiagnosticSourceError
from companion_v2.proactive.inspirations import SNAPSHOT_KEY
from companion_v2.conversation.messages import source_from_document
from companion_v2.conversation.reply_management import ReplyManagement
from companion_v2.conversation.segment_control import LLM_SEGMENT_MARKER
from companion_v2.conversation.text_processing import TEXT_DEFAULTS
from companion_v2.execution.models import TaskError, encode
from companion_v2.proactive.material_pool import read_shared_material_pool
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import SCHEMA_VERSION, SCHEMA_VERSION_V37, V37_SCHEMA_STATEMENTS
from tests.contact_schedule_support import ContactScheduleFixture
from tests.test_role_tool_loop import answered


class NewsPort:
    fingerprint = "fixture-news-v1"
    source_label = "news.example"

    def __init__(self, clock, batches):
        self.clock, self.batches, self.calls = clock, list(batches), 0

    async def fetch(self):
        self.calls += 1
        value = self.batches.pop(0)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value()
        return parse_news_response({"items": value})


class NewsContactTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def test_real_diagnostic_refetches_without_consuming_poll_or_seen(self):
        article = self.article("real-test")
        port = NewsPort(self.clock, [[article], [article]])
        app, context = await self.setup_news(port)
        events = app.contact_schedule.news_events
        preferences = self.preferences(app, context)
        events._save(context, events._settings(context, preferences), self.clock.now(), checked=True, seen=("already-seen",))
        before = dict(events._row(context))
        for identifier in ("test-1", "test-2"):
            candidate, stages = await events.diagnostic_candidate(context, preferences, test_id=identifier)
            self.assertEqual(stages[0]["state"], "passed")
            events.validate(context, candidate[2], self.clock.now())
        self.assertEqual(port.calls, 2)
        self.assertEqual(dict(events._row(context)), before)

    async def test_failed_real_diagnostic_does_not_use_previous_cached_articles(self):
        port = NewsPort(self.clock, [[self.article()], OSError("offline")])
        app, context = await self.setup_news(port)
        events = app.contact_schedule.news_events
        preferences = self.preferences(app, context)
        await events.probe(context, preferences)
        with self.assertRaises(DiagnosticSourceError) as caught:
            await events.diagnostic_candidate(context, preferences, test_id="failed-fetch")
        self.assertEqual((caught.exception.stage, caught.exception.state), ("news_fetch", "failed"))
        self.assertEqual(self.contact_calls(), [])

    def article(self, identifier="story-a", *, age=timedelta(minutes=10)):
        return {"id": identifier, "title": "有日期的资讯 " + identifier,
                "url": "https://news.example/" + identifier + "?utm_source=feed",
                "summary": "公开摘要，不是完整报道", "source": "示例媒体",
                "published_at": (self.clock.now() - age).isoformat()}

    async def setup_news(self, port, *, enabled=True):
        host, batch = await self.scheduled(news_port=port)
        self.news_host = host
        app = host.application
        self.settings(app, {"news_share_enabled": enabled, "chat.enabled": False}).unwrap()
        return app, self.context(app, batch)

    async def test_overnight_news_waits_on_a_stable_activity_slot_while_materials_refresh(self):
        self.clock.advance(timedelta(hours=21, minutes=11))  # Local 05:11 in Shanghai.
        port = NewsPort(self.clock, [[self.article()], lambda: [self.article("daytime")]])
        app, context = await self.setup_news(port)
        self.settings(app, {"quiet_enabled": False, "quiet_timezone": "Asia/Shanghai",
            "interval_seconds": 3600, "proactive_hour_activity_enabled": True,
            "proactive_hour_activity_curve": ",".join("0.05" if hour == 5 else "1.00" for hour in range(24))}).unwrap()
        events = app.contact_schedule.news_events

        with patch("companion_v2.proactive.rhythm.sample", return_value=0.5) as draw:
            for seconds in (60, 1, 14, 15):
                self.advance(app, seconds)
                app.contact_schedule.advance()
                await asyncio.sleep(0)
            self.assertEqual(self.contact_calls(), [])
            self.assertEqual(self.contacts(app), ())
            seeds = [tuple(call.args[0]) for call in draw.call_args_list
                     if call.args[0][1] == "hour-activity"]
            self.assertGreaterEqual(len(seeds), 4)
            self.assertEqual(len(set(seeds)), 1)

            # Collection is independent of permission to interrupt the user.
            events.maintain(context, self.preferences(app, context))
            await asyncio.gather(*tuple(events._maintenance_workers.values()))
            pool = events.role_materials(self.preferences(app, context).values, self.clock.now())
            self.assertEqual(pool["state"], "ready")
            self.assertGreater(len(pool["items"]), 0)
            self.assertEqual(self.contacts(app), ())

            self.advance(app, 5 * 3600)
            await self.automatic_delivery(app)
            self.assertEqual(json.loads(self.contacts(app)[0]["record_json"])["purpose"], "news")
            self.assertEqual(len(self.contact_calls()), 1)

    async def test_news_patrol_builds_one_shared_pool_for_multiple_private_contacts(self):
        article = self.article("curious-find")
        article["category"] = "趣事"
        port = NewsPort(self.clock, [[article]])
        app, first = await self.setup_news(port, enabled=False)
        events = app.contact_schedule.news_events
        first_preferences = self.preferences(app, first)

        events.maintain(first, first_preferences)
        workers = tuple(events._maintenance_workers.values())
        self.assertEqual(len(workers), 1)
        await asyncio.gather(*workers)

        pool = read_shared_material_pool(app.contact_schedule, first, observed_at=self.clock.now(),
                                         settings=first_preferences.values)
        self.assertEqual(pool["state"], "ready")
        self.assertEqual(pool["count"], 1)
        self.assertEqual(pool["items"][0]["title"], "有日期的资讯 curious-find")
        self.assertEqual(pool["items"][0]["category"], "趣事")
        self.assertEqual(pool["items"][0]["source"], "共享资讯池")
        self.assertNotIn("recipient", pool["items"][0])

        second = self.other_window_context("friend-b")
        second_preferences = self.preferences(app, second)
        events.maintain(second, second_preferences)
        await asyncio.sleep(0)
        self.assertEqual(port.calls, 1, "windows using the same feed reuse the shared patrol result")
        second_pool = read_shared_material_pool(app.contact_schedule, second, observed_at=self.clock.now(),
                                                settings=second_preferences.values)
        self.assertEqual(second_pool["items"][0]["id"], pool["items"][0]["id"])

    async def test_role_material_refresh_needs_no_private_window_and_reads_global_feed(self):
        port = NewsPort(self.clock, [[self.article("role-shared")]])
        app, context = await self.setup_news(port, enabled=False)
        settings = dict(self.preferences(app, context).values)
        events = app.contact_schedule.news_events

        events.maintain_role(settings)
        await asyncio.gather(*tuple(events._maintenance_workers.values()))
        pool = events.role_materials(settings, self.clock.now())

        self.assertEqual(pool["state"], "ready")
        self.assertEqual([item["title"] for item in pool["items"]], ["有日期的资讯 role-shared"])
        self.assertEqual(port.calls, 1)

    async def test_opt_in_material_and_source_recheck(self):
        article = self.article()
        article["category"] = "趣事"
        port = NewsPort(self.clock, [[article]])
        app, context = await self.setup_news(port, enabled=False)
        # Isolate news opt-in from autonomous relationship expressions that no
        # longer need a matching phrase in the preceding user message.
        self.settings(app, {purpose + ".enabled": False for purpose in
                            ("affection", "care", "play", "repair", "invitation")}).unwrap()
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(port.calls, 0)
        self.settings(app, {"news_share_enabled": True}).unwrap()
        app.contact_schedule.advance()
        await self.automatic_delivery(app)
        self.assertEqual(port.calls, 1)
        call = self.contact_calls()[0].original
        material = next(item for item in call.context.materials if item.owner == SOURCE_OWNER)
        body = json.loads(material.payload)
        self.assertEqual(body["event"], "external_news_item")
        self.assertEqual(body["source"], "示例媒体")
        self.assertEqual(body["category"], "趣事")
        self.assertEqual(body["url"], "https://news.example/story-a")
        self.assertNotIn("_receipt", body)
        contact_body = self.contacts(app)[0]["body"]
        self.assertNotIn("https://", contact_body)
        saved = json.loads(self.contacts(app)[0]["record_json"])
        self.assertEqual(saved["news_provenance"]["source"], "示例媒体")
        self.assertEqual(saved["news_provenance"]["category"], "趣事")
        self.assertEqual(saved["news_provenance"]["url"], body["url"])
        self.assertEqual(datetime.fromisoformat(saved["news_provenance"]["published_at"]),
                         datetime.fromisoformat(body["published_at"]))
        self.assertIn("news_event", json.loads(self.contacts(app)[0]["record_json"])["automatic_origin"])
        self.settings(app, {"news_share_enabled": False}).unwrap()
        self.assertFalse(app.proactive.sources.validate_reference_for_audience(
            material.source, recipient=context.actor.subject, observed_at=self.clock.now()).is_success)

    async def test_confirmed_diagnostic_keeps_news_origin_prompt_and_program_attribution(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, context = await self.setup_news(port)
        self.settings(app, {"external_event_self_link_enabled": False}).unwrap()
        self.advance(app, 60)

        candidate = await app.contact_schedule.diagnostic_candidate(context, "news", at=self.clock.now())
        result = await app.proactive.contact(context, candidate["opportunity"], candidate["intents"],
            role_instruction=candidate["role_instruction"], selection_seed="confirmed-news-diagnostic",
            administrator_test=True, diagnostic_source_backed=True,
            diagnostic_origin=candidate["diagnostic_origin"])

        self.assertIsNone(result.failure, result.failure)
        await self.automatic_delivery(app)
        contact = self.contacts(app)[0]
        self.assertNotIn("https://", contact["body"])
        saved = json.loads(contact["record_json"])
        self.assertEqual(saved["news_provenance"]["url"], "https://news.example/story-a")
        self.assertIn("news_event", saved["diagnostic_origin"])
        request = self.contact_calls()[0].original
        self.assertIn("新闻按来源标题、摘要与发布时间分享", request.instruction)
        self.assertIn("沿用原人格", request.instruction)
        self.assertIn("不固定兴奋、卖萌", request.instruction)
        self.assertTrue(any(item.owner == SOURCE_OWNER for item in request.context.materials))

    async def test_news_sharing_prompt_and_natural_punctuation_create_separate_parts(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, _ = await self.setup_news(port)
        self.configure_presentation(app, {"enabled": True, "llm_controlled": False,
            "part_gap_mode": "fixed", "part_gap_ms": 0, **TEXT_DEFAULTS,
            "content_cleanup_enabled": True, "content_cleanup_scope": "all",
            "content_cleanup_words": '["。", "！", "<newline>"]'}, "news-rule-parts")
        self.settings(app, {"proactive_intensity_body_chars": 120}).unwrap()

        async def excited_sharing(envelope):
            self.assertIn("把新闻当作看到值得分享的内容后想说的一段话", envelope.original.instruction)
            self.assertIn("不固定兴奋、卖萌", envelope.original.instruction)
            self.assertIn("无需压成一句", envelope.original.instruction)
            self.assertIn("已配置规则分段", envelope.original.instruction)
            self.assertNotIn(LLM_SEGMENT_MARKER, envelope.original.instruction)
            return answered(json.dumps({
                "decision": "send",
                "text": "这个变化好有意思！\n\n我有点好奇后面会怎样。",
            }, ensure_ascii=False))

        self.model_behavior = excited_sharing
        sent_before = len(self.sent)
        self.advance(app, 60)
        await self.automatic_delivery(app)

        contact = self.contacts(app)[0]
        await self.until(lambda: len(app.proactive._delivery_rows(contact["task_id"])) == 2
                         and all(row["state"] == "delivered"
                                 for row in app.proactive._delivery_rows(contact["task_id"])))
        saved = json.loads(contact["record_json"])
        parts = [part["text"] for part in saved["parts"]]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "这个变化好有意思")
        self.assertEqual(parts[1], "我有点好奇后面会怎样")
        self.assertEqual([item.text for item in self.sent[sent_before:]], parts)
        self.assertEqual([item.sequence for item in self.sent[sent_before:]], [0, 1])
        self.assertEqual(contact["body"], "".join(parts))
        self.assertNotIn("出处", contact["body"])
        self.assertNotIn("https://", contact["body"])
        self.assertEqual(saved["news_provenance"]["url"], "https://news.example/story-a")

    def configure_presentation(self, app, changes, key):
        manager = ReplyManagement(app, self.contact_context())
        status = manager.status(self.core).unwrap()
        return manager.configure(self.core, {"operation_key": key, "edit_token": status["edit_token"],
                                             "changes": changes}).unwrap()

    async def test_news_model_boundaries_survive_cleanup_and_later_settings_changes(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, _ = await self.setup_news(port)
        self.configure_presentation(app, {"enabled": True, "llm_controlled": True,
            "part_gap_mode": "fixed", "part_gap_ms": 0, **TEXT_DEFAULTS,
            "content_cleanup_enabled": True, "content_cleanup_scope": "all",
            "content_cleanup_words": '["<newline>", "。", "！"]'}, "news-model-parts")

        async def model(envelope):
            self.assertIn("即使正文偏好少标点", envelope.original.instruction)
            self.assertIn(LLM_SEGMENT_MARKER, envelope.original.instruction)
            self.configure_presentation(app, {"enabled": False}, "news-next-turn-disabled")
            return answered(json.dumps({"decision": "send",
                "text": "我看到一个有趣的点\n" + LLM_SEGMENT_MARKER + "\n有点想知道接下来会怎样"},
                ensure_ascii=False))

        self.model_behavior = model
        sent_before = len(self.sent)
        self.advance(app, 60)
        await self.automatic_delivery(app)
        contact = self.contacts(app)[0]
        await self.until(lambda: len(app.proactive._delivery_rows(contact["task_id"])) == 2
                         and all(row["state"] == "delivered"
                                 for row in app.proactive._delivery_rows(contact["task_id"])))
        saved = json.loads(contact["record_json"])
        self.assertTrue(saved["segmentation_settings"]["enabled"])
        self.assertEqual([item.text for item in self.sent[sent_before:]],
                         [part["text"] for part in saved["parts"]])
        self.assertEqual(saved["parts"][0]["text"], "我看到一个有趣的点")
        self.assertEqual(saved["parts"][1]["text"], "有点想知道接下来会怎样")
        self.assertNotIn(LLM_SEGMENT_MARKER, contact["body"])
        self.assertNotIn("https://", contact["body"])

    async def test_disabled_news_segmentation_keeps_paragraphs_in_one_message(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, _ = await self.setup_news(port)
        self.configure_presentation(app, {"enabled": False, **TEXT_DEFAULTS,
                                         "content_cleanup_enabled": False}, "news-single-message")
        body = "看到这个消息就想分享给你。\n\n我有点好奇它接下来会怎样。"

        async def model(envelope):
            self.assertIn("作为一条消息发送", envelope.original.instruction)
            self.assertNotIn(LLM_SEGMENT_MARKER, envelope.original.instruction)
            return answered(json.dumps({"decision": "send", "text": body}, ensure_ascii=False))

        self.model_behavior = model
        sent_before = len(self.sent)
        self.advance(app, 60)
        await self.automatic_delivery(app)
        contact = self.contacts(app)[0]
        saved = json.loads(contact["record_json"])
        self.assertEqual(len(saved["parts"]), 1)
        self.assertEqual(saved["parts"][0]["text"], body)
        self.assertEqual([item.text for item in self.sent[sent_before:]], [contact["body"]])

    async def test_source_followup_after_restart_uses_the_original_receipt_backed_archive(self):
        from tests.test_semantic_integration import SemanticPort

        port = NewsPort(self.clock, [[self.article()]])
        app, context = await self.setup_news(port)
        self.advance(app, 60)
        await self.automatic_delivery(app)
        self.settings(app, {"automatic_enabled": False, "news_share_enabled": False}).unwrap()
        original = self.contacts(app)[0]
        saved = json.loads(original["record_json"])
        reference = next(source_from_document(item) for item in saved["sources"]
                         if item["owner"] == SOURCE_OWNER)
        await app.close()
        self.clock.advance(timedelta(hours=1))

        host = await self.start(self.host(runtime=self.open_runtime(), news_port=port), 1, 1)
        restarted = host.application
        restarted.attach_semantics(SemanticPort()).store.configure({"enabled": False}, 0)
        # The share's live evidence cannot be renewed into a current send or read.
        current = restarted.proactive.sources.read(reference, resolved=context.actor, capability="text",
            observed_at=self.clock.now(), authorizer=restarted.tasks.identity)
        self.assertEqual(current.failure.code, "source_expired")

        async def reply(envelope):
            history = [json.loads(item.payload) for item in envelope.original.context.materials
                       if item.owner == "delivery.history"]
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["text"], original["body"])
            self.assertNotIn("provenance", history[0])
            inspirations = [json.loads(item.payload) for item in envelope.original.context.materials
                            if item.owner == "proactive.inspirations"]
            self.assertEqual(len(inspirations), 1)
            items = inspirations[0]["items"]
            item = next(item for item in items if item["contact_id"] == original["contact_id"])
            self.assertEqual(item["text"], original["body"])
            self.assertEqual(item["thought"], saved["thought_summary"])
            self.assertEqual(item["provenance"], saved["news_provenance"])
            self.assertIn("主动灵感清单只属于当前私聊窗口", envelope.original.instruction)
            self.assertNotIn("conversation.news", {item.owner for item in envelope.original.context.materials})
            news = item["provenance"]
            return answered(news["source"] + " · " + news["published_at"][:10] + "\n" + news["url"])

        self.model_behavior = reply
        sent_before = len(self.sent)
        batch = host.receive(self.event("news-source-followup", text="这条AI新闻的原文链接在哪？")).unwrap()
        self.advance(restarted)
        self.assertEqual((await self.done(restarted, batch))["state"], "complete")
        self.assertEqual(port.calls, 1)
        reply_text = "".join(item.text for item in self.sent[sent_before:])
        self.assertIn("示例媒体", reply_text)
        self.assertIn(saved["news_provenance"]["published_at"][:10], reply_text)
        self.assertIn("https://news.example/story-a", reply_text)
        sealed = json.loads(restarted.messages.batch(batch)["contributions_json"])[SNAPSHOT_KEY]
        self.assertNotIn("https://", encode(sealed))
        await restarted.close()
        again = (await self.start(self.host(runtime=self.open_runtime(), news_port=port), 2, 2)).application
        # The dependency survives even when semantic recall is not attached.
        restored = again.messages.batch(batch)
        request = again.messages._request(restored, context, self.clock.now(), include_tools=False, historical=True)
        self.assertIn("proactive.inspirations", {item.owner for item in request.context.materials})
        again.proactive.sources.revoke(reference, expected_governance_revision=1,
                                       observed_at=self.clock.now()).unwrap()
        with self.assertRaises(TaskError):
            again.messages._request(restored, context, self.clock.now(), include_tools=False, historical=True)

    async def test_unknown_share_has_no_recallable_provenance(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, context = await self.setup_news(port)

        async def unconfirmed(envelope):
            return self.receipt(envelope, "unknown")

        self.send_behavior = unconfirmed
        self.advance(app, 60)
        await self.until(lambda: len(self.contacts(app)) == 1)
        contact = self.contacts(app)[0]
        await self.delivery_state(app, contact["task_id"], "unknown")
        self.assertIn("news_provenance", json.loads(contact["record_json"]))
        self.assertEqual(app.background_history.recent(context).unwrap(), ())
        inspirations = app.proactive.inspirations
        self.assertEqual(inspirations.read(inspirations.capture(context, self.clock.now()), context, self.clock.now()), ())
        sent_count = len(self.sent)
        app.record_receipt(self.receipt(self.sent[-1])).unwrap()
        items = inspirations.read(inspirations.capture(context, self.clock.now()), context, self.clock.now())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["provenance"]["url"], "https://news.example/story-a")
        self.assertEqual(len(self.sent), sent_count)

    async def test_changed_or_revoked_news_provenance_is_hidden_from_history(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, context = await self.setup_news(port)
        self.advance(app, 60)
        await self.automatic_delivery(app)
        contact = self.contacts(app)[0]
        self.assertEqual(len(app.background_history.recent(context).unwrap()), 1)
        inspirations = app.proactive.inspirations
        snapshot = inspirations.capture(context, self.clock.now())
        self.assertEqual(len(inspirations.read(snapshot, context, self.clock.now())), 1)
        saved = json.loads(contact["record_json"])
        reference = next(source_from_document(item) for item in saved["sources"]
                         if item["owner"] == SOURCE_OWNER)
        saved["news_provenance"]["url"] = "https://news.example/another-story"
        with app.runtime.transaction() as connection:
            connection.execute("UPDATE proactive_contacts SET record_json = ? WHERE contact_id = ?",
                               (encode(saved), contact["contact_id"]))
        self.assertEqual(app.background_history.recent(context).unwrap(), ())
        self.assertEqual(inspirations.capture(context, self.clock.now())["entries"], [])
        with self.assertRaises(TaskError):
            inspirations.read(snapshot, context, self.clock.now())
        with app.runtime.transaction() as connection:
            connection.execute("UPDATE proactive_contacts SET record_json = ? WHERE contact_id = ?",
                               (contact["record_json"], contact["contact_id"]))
        self.clock.advance(timedelta(hours=1))
        self.assertEqual(len(app.background_history.recent(context).unwrap()), 1)
        app.proactive.sources.revoke(reference, expected_governance_revision=1,
                                    observed_at=self.clock.now()).unwrap()
        self.assertEqual(app.background_history.recent(context).unwrap(), ())
        self.assertEqual(inspirations.capture(context, self.clock.now())["entries"], [])
        with self.assertRaises(TaskError):
            inspirations.read(snapshot, context, self.clock.now())

    async def test_prompt_contribution_reuses_the_single_receipt_validation_pass(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, context = await self.setup_news(port)
        self.advance(app, 60)
        await self.automatic_delivery(app)
        inspirations = app.proactive.inspirations
        contact = self.contacts(app)[0]
        delivered_ids = {row["delivery_id"] for row in app.proactive._delivery_rows(contact["task_id"])}

        with (patch.object(inspirations, "_entry", wraps=inspirations._entry) as validate_entry,
              patch.object(app.proactive.delivery, "_row", wraps=app.proactive.delivery._row) as read_delivery):
            material = inspirations.capture_contribution(context, self.clock.now())

        self.assertIsNotNone(material)
        self.assertEqual(validate_entry.call_count, 1)
        queried_ids = [call.args[0] for call in read_delivery.call_args_list]
        self.assertTrue(delivered_ids)
        self.assertTrue(all(queried_ids.count(delivery_id) == 1 for delivery_id in delivered_ids))
        self.assertIn("https://news.example/story-a", material.payload)

    async def test_casual_reply_does_not_receive_private_source_details(self):
        from tests.test_semantic_integration import SemanticPort

        port = NewsPort(self.clock, [[self.article()]])
        app, _ = await self.setup_news(port)
        self.advance(app, 60)
        await self.automatic_delivery(app)
        self.settings(app, {"automatic_enabled": False}).unwrap()
        app.attach_semantics(SemanticPort()).store.configure({"enabled": False}, 0)

        async def casual(envelope):
            owners = {item.owner for item in envelope.original.context.materials}
            self.assertNotIn("proactive.inspirations", owners)
            self.assertNotIn("conversation.news", owners)
            history = [json.loads(item.payload) for item in envelope.original.context.materials
                       if item.owner == "delivery.history"]
            self.assertTrue(history)
            self.assertTrue(all("provenance" not in item for item in history))
            return answered("对，我也想看看它接下来会怎么发展。")

        self.model_behavior = casual
        batch = self.news_host.receive(self.event("news-casual-followup", text="这个变化还挺有意思的。")).unwrap()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertNotIn(SNAPSHOT_KEY, json.loads(app.messages.batch(batch)["contributions_json"]))
        self.assertEqual(port.calls, 1)

    async def test_window_list_preserves_multiple_shares_for_an_earlier_source_followup(self):
        from tests.test_semantic_integration import SemanticPort

        port = NewsPort(self.clock, [[self.article()], lambda: [self.article("story-b")]])
        app, context = await self.setup_news(port)
        self.settings(app, {"external_event_self_link_enabled": False}).unwrap()

        async def share(envelope):
            material = next(item for item in envelope.original.context.materials if item.owner == SOURCE_OWNER)
            title = json.loads(material.payload)["title"]
            return answered(json.dumps({"decision": "send", "text": "这个点让我挺好奇的：" + title}, ensure_ascii=False))

        self.model_behavior = share
        self.advance(app, 60)
        await self.automatic_delivery(app)
        self.advance(app, 180 * 60)
        await self.automatic_delivery(app, count=2)
        self.settings(app, {"automatic_enabled": False}).unwrap()
        inspirations = app.proactive.inspirations
        snapshot = inspirations.capture(context, self.clock.now())
        items = inspirations.read(snapshot, context, self.clock.now())
        self.assertEqual({item["provenance"]["url"] for item in items},
                         {"https://news.example/story-a", "https://news.example/story-b"})
        other = self.other_window_context()
        self.grant(self.important, other.scope, "text")
        self.assertEqual(inspirations.capture(other, self.clock.now())["entries"], [])
        with self.assertRaises(TaskError):
            inspirations.read(snapshot, other, self.clock.now())
        app.attach_semantics(SemanticPort()).store.configure({"enabled": False}, 0)

        async def earlier_source(envelope):
            material = next(item for item in envelope.original.context.materials if item.owner == "proactive.inspirations")
            entries = json.loads(material.payload)["items"]
            self.assertEqual(len(entries), 2)
            self.assertIn("不能默认拿最新一条顶替", envelope.original.instruction)
            earlier = next(item for item in entries if item["provenance"]["title"].endswith("story-a"))
            return answered(earlier["provenance"]["url"])

        self.model_behavior = earlier_source
        sent_before = len(self.sent)
        batch = self.news_host.receive(self.event("earlier-news-source", text="前面那条 story-a 的原文在哪？")).unwrap()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual("".join(item.text for item in self.sent[sent_before:]), "https://news.example/story-a")
        self.assertEqual(port.calls, 2)

    async def test_missing_original_share_does_not_fetch_another_article(self):
        from tests.test_semantic_integration import SemanticPort

        port = NewsPort(self.clock, [])
        app, _ = await self.setup_news(port)
        self.settings(app, {"automatic_enabled": False}).unwrap()
        app.attach_semantics(SemanticPort()).store.configure({"enabled": False}, 0)

        async def missing(envelope):
            material = next(item for item in envelope.original.context.materials if item.owner == "proactive.inspirations")
            self.assertEqual(json.loads(material.payload)["items"], [])
            self.assertIn("不拿新拉取的另一条资讯替代原出处", envelope.original.instruction)
            self.assertNotIn("conversation.news", {item.owner for item in envelope.original.context.materials})
            return answered("这边没有留下那条分享的出处，你指的是哪一条？")

        self.model_behavior = missing
        batch = self.news_host.receive(self.event("missing-news-source", text="你刚提到最新那条AI新闻的原文链接在哪？")).unwrap()
        self.assertEqual((await self.done(app, batch))["state"], "complete")
        self.assertEqual(port.calls, 0)

    async def test_partially_confirmed_share_lists_only_the_confirmed_bubble(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, context = await self.setup_news(port)
        self.configure_presentation(app, {"enabled": True, "llm_controlled": True,
            "part_gap_mode": "fixed", "part_gap_ms": 0, "content_cleanup_enabled": False}, "news-partial-share")

        async def share(envelope):
            return answered(json.dumps({"decision": "send", "text": "看到一个有趣的变化\n" +
                LLM_SEGMENT_MARKER + "\n我还想看看后续怎样"}, ensure_ascii=False))

        async def partial(envelope):
            return self.receipt(envelope, "unknown" if envelope.sequence == 1 else "delivered")

        self.model_behavior, self.send_behavior = share, partial
        self.advance(app, 60)
        await self.until(lambda: len(self.contacts(app)) == 1)
        contact = self.contacts(app)[0]
        await self.delivery_state(app, contact["task_id"], "unknown")
        snapshot = app.proactive.inspirations.capture(context, self.clock.now())
        items = app.proactive.inspirations.read(snapshot, context, self.clock.now())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], json.loads(contact["record_json"])["parts"][0]["text"])
        self.assertNotIn("我还想看看后续怎样", items[0]["text"])
        self.assertEqual((items[0]["confirmed_parts"], items[0]["part_count"]), (1, 2))
        self.assertEqual(items[0]["provenance"]["url"], "https://news.example/story-a")

    async def test_withdrawal_during_source_followup_discards_the_derived_reply(self):
        from tests.test_semantic_integration import SemanticPort

        port = NewsPort(self.clock, [[self.article()]])
        app, _ = await self.setup_news(port)
        self.advance(app, 60)
        await self.automatic_delivery(app)
        self.settings(app, {"automatic_enabled": False}).unwrap()
        saved = json.loads(self.contacts(app)[0]["record_json"])
        reference = next(source_from_document(item) for item in saved["sources"] if item["owner"] == SOURCE_OWNER)
        app.attach_semantics(SemanticPort()).store.configure({"enabled": False}, 0)

        async def withdrawn(envelope):
            self.assertIn("proactive.inspirations", {item.owner for item in envelope.original.context.materials})
            app.proactive.sources.revoke(reference, expected_governance_revision=1,
                                        observed_at=self.clock.now()).unwrap()
            return answered(saved["news_provenance"]["url"])

        self.model_behavior = withdrawn
        sent_before = len(self.sent)
        batch = self.news_host.receive(self.event("withdrawn-news-source", text="这条消息的出处呢？")).unwrap()
        self.assertEqual((await self.done(app, batch))["state"], "blocked")
        self.assertEqual(len(self.sent), sent_before)
        self.assertEqual(app.runtime.read_one("SELECT state FROM model_calls ORDER BY rowid DESC LIMIT 1", ())[0], "discarded")

    async def test_news_self_link_cooldown_blocks_cached_candidates_and_allows_current_delivery(self):
        port = NewsPort(self.clock, [[self.article()], []])
        app, context = await self.setup_news(port)
        self.settings(app, {"external_event_self_link_enabled": True,
                            "external_event_self_link_cooldown_hours": 12}).unwrap()
        self.advance(app, 60)
        await self.automatic_delivery(app)

        events = app.contact_schedule.news_events
        at = self.clock.now()
        preferences = app.proactive.preferences.read(context, observed_at=at).unwrap()
        settings_hash = events._settings(context, preferences)
        event = {"id": "news-cached-cooldown-test", "opened_at": at.isoformat(),
                 "expires_at": (at + timedelta(minutes=30)).isoformat(),
                 "settings_hash": settings_hash, "key": "cached-key", "feed": "news.example",
                 "article": {"source": "示例媒体", "title": "缓存资讯", "summary": "摘要",
                             "url": "https://news.example/cached", "published_at": at.isoformat()}}
        events._save(context, settings_hash, at, checked=True, event=event)

        self.assertIsNone(events.select(context, preferences, at))
        self.assertIsNone(await events.prepare(context, {"settings_hash": settings_hash}))
        self.assertEqual(len(self.contacts(app)), 1)

    async def test_restart_deduplicates_article_and_accepts_new_one(self):
        old = self.article()
        port = NewsPort(self.clock, [[old], [old], lambda: [self.article("story-b")]])
        app, _ = await self.setup_news(port)
        self.settings(app, {"external_event_self_link_enabled": False}).unwrap()
        self.advance(app, 60)
        await self.automatic_delivery(app)
        await app.close()
        restarted = (await self.start(self.host(runtime=self.open_runtime(), news_port=port), 1, 1)).application
        restarted.contact_schedule.advance()
        self.assertEqual(port.calls, 1)
        self.clock.advance(timedelta(minutes=180))
        restarted.contact_schedule.advance()
        await self.until(lambda: port.calls == 2 and not restarted.contact_schedule.active_handles)
        self.assertEqual(len(self.contacts(restarted)), 1)
        self.clock.advance(timedelta(minutes=180))
        restarted.contact_schedule.advance()
        await self.automatic_delivery(restarted, count=2)
        self.assertEqual(port.calls, 3)

    async def test_reenable_expires_pending_item_without_forgetting_seen_urls(self):
        port = NewsPort(self.clock, [[self.article()], [self.article(), self.article("story-b")]])
        app, context = await self.setup_news(port)
        events = app.contact_schedule.news_events

        def select():
            at = self.clock.now()
            preferences = app.proactive.preferences.read(context, observed_at=at).unwrap()
            return events.select(context, preferences, at)

        first = await events.prepare(context, select()[1])
        old_source = first[1][0].thought.evidence.sources[0]
        self.assertEqual(port.calls, 1)
        self.settings(app, {"news_share_enabled": False}).unwrap()
        self.assertIsNone(select())
        self.settings(app, {"news_share_enabled": True}).unwrap()
        self.assertFalse(app.proactive.sources.validate_reference_for_audience(
            old_source, recipient=context.actor.subject, observed_at=self.clock.now()).is_success)

        immediate = await events.prepare(context, select()[1])
        self.assertIsNone(immediate, "reenabling a contact reuses the shared feed until its patrol interval expires")
        self.assertEqual(port.calls, 1)
        self.clock.advance(timedelta(minutes=180))
        second = await events.prepare(context, select()[1])
        self.assertEqual(port.calls, 2)
        self.assertNotEqual(first[0].opportunity_id, second[0].opportunity_id)
        row = app.runtime.read_one("SELECT seen_json, event_json FROM proactive_news_polls", ())
        self.assertEqual(len(json.loads(row["seen_json"])), 2)
        self.assertEqual(json.loads(row["event_json"])["article"]["url"],
                         "https://news.example/story-b")

    async def test_error_backoff_survives_restart(self):
        port = NewsPort(self.clock, [OSError("offline"), [self.article()]])
        app, _ = await self.setup_news(port)
        self.advance(app, 60)
        await self.until(lambda: port.calls == 1 and not app.contact_schedule.active_handles)
        self.assertEqual(self.contacts(app), ())
        await app.close()
        restarted = (await self.start(self.host(runtime=self.open_runtime(), news_port=port), 1, 1)).application
        restarted.contact_schedule.advance()
        self.assertEqual(port.calls, 1)
        self.clock.advance(timedelta(minutes=5))
        restarted.contact_schedule.advance()
        await self.automatic_delivery(restarted)
        self.assertEqual(port.calls, 2)

    async def test_disable_during_fetch_discards_article(self):
        entered, release = asyncio.Event(), asyncio.Event()
        test = self

        class DelayedPort(NewsPort):
            async def fetch(self):
                self.calls += 1
                entered.set()
                await release.wait()
                return parse_news_response({"items": [test.article()]})

        port = DelayedPort(self.clock, [])
        app, _ = await self.setup_news(port)
        self.advance(app, 60)
        await asyncio.wait_for(entered.wait(), 3)
        self.settings(app, {"news_share_enabled": False}).unwrap()
        release.set()
        await self.until(lambda: not app.contact_schedule.active_handles)
        self.assertEqual(self.contacts(app), ())
        self.assertIsNone(app.runtime.read_one("SELECT * FROM proactive_news_polls", ()))

    async def test_stale_and_undated_news_are_refused(self):
        old = self.article(age=timedelta(hours=25))
        undated = self.article("undated")
        del undated["published_at"]
        port = NewsPort(self.clock, [[old, undated]])
        app, _ = await self.setup_news(port)
        self.advance(app, 60)
        await self.until(lambda: port.calls == 1 and not app.contact_schedule.active_handles)
        calls = self.contact_calls()
        self.assertEqual(calls, [])
        self.assertEqual(self.contacts(app), ())
        row = app.runtime.read_one("SELECT event_json FROM proactive_news_polls", ())
        self.assertIsNone(row["event_json"] if row else None)


class NewsAdapterTests(unittest.TestCase):
    def test_feed_projection_accepts_an_article_without_optional_category(self):
        from types import SimpleNamespace
        from companion_v2.proactive.news_events import NewsContactEvents

        article = SimpleNamespace(title="有日期的资讯", summary="公开摘要", source="示例媒体",
            url="https://news.example/story", published_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
        projected = NewsContactEvents._feed_item(article)

        self.assertIsNotNone(projected)
        self.assertEqual(projected["category"], "")

    def test_explicit_https_json_feed_and_environment(self):
        with self.assertRaises(ValueError):
            NewsJsonPort(url="http://news.example/feed")
        with self.assertRaises(ValueError):
            NewsJsonPort(url="https://127.0.0.1/feed")
        with patch.dict("os.environ", {"COMPANION_V2_NEWS_URL": "https://news.example/feed"}, clear=True):
            port = configured_news_port()
        self.assertEqual(port.source_label, "news.example")
        self.assertEqual(port.headers, {})

    def test_core_ai_news_rss_is_the_host_default_without_forwarding_environment_secrets(self):
        with patch.dict("os.environ", {"COMPANION_V2_NEWS_API_KEY": "unrelated-secret"}, clear=True):
            router = configured_news_port({"news": {"source_kind": "host"}})
        port = router.for_settings({"news_source_kind": "host"})
        self.assertIsInstance(port, NewsRssPort)
        self.assertEqual(port.url, DEFAULT_AI_NEWS_FEED_URL)
        self.assertEqual(port.source_label, DEFAULT_AI_NEWS_FEED_LABEL)
        self.assertEqual(port.headers, {})

    def test_core_ai_news_rss_schema_and_parser_match_the_daily_feed(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "_conf_schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["news"]["items"]["source_kind"]["default"], "rss")
        self.assertEqual(schema["news"]["items"]["feed_url"]["default"], DEFAULT_AI_NEWS_FEED_URL)
        payload = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel><title>橘鸦AI早报</title><item>
        <guid>2026-10-02</guid><title>2026-10-02</title>
        <link>https://daily.juya.uk/issues/2026-10-02/</link>
        <category>人工智能</category>
        <pubDate>Fri, 02 Oct 2026 02:01:50 GMT</pubDate>
        <description>OpenAI 发布新模型与工具。</description>
        </item></channel></rss>""".encode("utf-8")
        batch = parse_rss_news(payload, source_label="daily.juya.uk")
        self.assertEqual(len(batch.items), 1)
        item = batch.items[0]
        self.assertEqual(item.source, DEFAULT_AI_NEWS_FEED_LABEL)
        self.assertEqual(item.title, "2026-10-02")
        self.assertEqual(item.url, "https://daily.juya.uk/issues/2026-10-02/")
        self.assertEqual(item.summary, "OpenAI 发布新模型与工具。")
        self.assertEqual(item.published_at.isoformat(), "2026-10-02T02:01:50+00:00")
        self.assertEqual(item.category, "人工智能")


class NewsStorageTests(unittest.TestCase):
    def test_v37_upgrade_and_partial_migration(self):
        with TemporaryDirectory(prefix="companion-v2-news-") as temporary:
            root = Path(temporary) / "v2-data"
            runtime = StorageRuntime.open(data_root=root, installation_id="news-test")
            with runtime.transaction() as connection:
                connection.execute("INSERT INTO runtime_metadata VALUES (?, ?)", ("news-test-marker", "kept"))
            database = runtime.database_path
            runtime.close()
            with closing(sqlite3.connect(database)) as connection:
                metadata = [(key, SCHEMA_VERSION_V37 if key == "schema_version" else value)
                            for key, value in connection.execute("SELECT key, value FROM runtime_metadata")]
                migrations = connection.execute("SELECT * FROM schema_migrations WHERE "
                    "CAST(substr(from_version, length('companion-v2.storage.v') + 1) AS INTEGER) < 37").fetchall()
                # Recreate this empty synthetic fixture from the actual v37
                # schema; later ALTERs must not leak into a supposed old database.
                with closing(sqlite3.connect(":memory:")) as legacy:
                    for statement in V37_SCHEMA_STATEMENTS:
                        legacy.execute(statement)
                    legacy.executemany("INSERT INTO runtime_metadata VALUES (?, ?)", metadata)
                    legacy.executemany("INSERT INTO schema_migrations VALUES (?, ?, ?, ?, ?)", migrations)
                    legacy.commit()
                    legacy.backup(connection)
            upgraded = StorageRuntime.open(data_root=root, installation_id="news-test")
            self.assertEqual(upgraded.read_one("SELECT value FROM runtime_metadata WHERE key = ?",
                                               ("schema_version",))[0], SCHEMA_VERSION)
            self.assertEqual(upgraded.read_one("SELECT value FROM runtime_metadata WHERE key = ?",
                                               ("news-test-marker",))[0], "kept")
            upgraded.close()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'",
                                   (SCHEMA_VERSION_V37,))
                connection.commit()
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=root, installation_id="news-test")


if __name__ == "__main__":
    unittest.main()

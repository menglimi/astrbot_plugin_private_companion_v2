"""Synthetic news source, durable polling, and automatic contact tests."""

import asyncio
from contextlib import closing
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from astrbot_host.news import NewsJsonPort, configured_news_port
from companion_v2.proactive.external_materials import parse_news_response
from companion_v2.proactive.news_events import SOURCE_OWNER
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import (REQUIRED_TABLES, SCHEMA_VERSION, SCHEMA_VERSION_V37,
                                         V37_REQUIRED_TABLES)
from tests.contact_schedule_support import ContactScheduleFixture


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
    def article(self, identifier="story-a", *, age=timedelta(minutes=10)):
        return {"id": identifier, "title": "有日期的资讯 " + identifier,
                "url": "https://news.example/" + identifier + "?utm_source=feed",
                "summary": "公开摘要，不是完整报道", "source": "示例媒体",
                "published_at": (self.clock.now() - age).isoformat()}

    async def setup_news(self, port, *, enabled=True):
        host, batch = await self.scheduled(news_port=port)
        app = host.application
        self.settings(app, {"news_share_enabled": enabled, "chat.enabled": False}).unwrap()
        return app, self.context(app, batch)

    async def test_opt_in_material_and_source_recheck(self):
        port = NewsPort(self.clock, [[self.article()]])
        app, context = await self.setup_news(port, enabled=False)
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
        self.assertEqual(body["url"], "https://news.example/story-a")
        self.assertNotIn("_receipt", body)
        self.assertIn("news_event", json.loads(self.contacts(app)[0]["record_json"])["automatic_origin"])
        self.settings(app, {"news_share_enabled": False}).unwrap()
        self.assertFalse(app.proactive.sources.validate_reference_for_audience(
            material.source, recipient=context.actor.subject, observed_at=self.clock.now()).is_success)

    async def test_restart_deduplicates_article_and_accepts_new_one(self):
        old = self.article()
        port = NewsPort(self.clock, [[old], [old], lambda: [self.article("story-b")]])
        app, _ = await self.setup_news(port)
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

    async def test_stale_dated_news_is_refused_but_undated_news_reaches_the_model(self):
        old = self.article(age=timedelta(hours=25))
        undated = self.article("undated")
        del undated["published_at"]
        port = NewsPort(self.clock, [[old, undated]])
        app, _ = await self.setup_news(port)
        self.advance(app, 60)
        await self.until(lambda: port.calls == 1 and not app.contact_schedule.active_handles)
        # 超过 24 小时的带日期条目仍然被拒；没有发布日期的条目交给模型
        # 按"只保留可用日期"的材料规则自行取舍。
        calls = self.contact_calls()
        self.assertEqual(len(calls), 1)
        material = next(m for m in calls[0].original.context.materials if m.owner == SOURCE_OWNER)
        payload = json.loads(material.payload)
        self.assertEqual(payload["title"], "有日期的资讯 undated")
        self.assertIsNone(payload["published_at"])
        self.assertNotIn("story-a", json.dumps(payload))
        self.assertEqual(len(self.contacts(app)), 1)


class NewsAdapterTests(unittest.TestCase):
    def test_explicit_https_json_feed_and_environment(self):
        with self.assertRaises(ValueError):
            NewsJsonPort(url="http://news.example/feed")
        with self.assertRaises(ValueError):
            NewsJsonPort(url="https://127.0.0.1/feed")
        with patch.dict("os.environ", {"COMPANION_V2_NEWS_URL": "https://news.example/feed"}, clear=True):
            port = configured_news_port()
        self.assertEqual(port.source_label, "news.example")
        self.assertEqual(port.headers, {})


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
                connection.execute("PRAGMA foreign_keys=OFF")
                connection.execute('DROP TABLE "proactive_news_polls"')
                connection.execute("DELETE FROM schema_migrations WHERE migration_id = 'companion-v2.storage.v37-to-v38'")
                # 模拟一份真实的 v37 库：v37 之后新增的表、迁移记录，以及 v46
                # 追加到 model_calls 的用量列都必须先退场，否则降级副本会被
                # v37 校验当作半截迁移或降级拷贝拒绝。
                for table in sorted(REQUIRED_TABLES - V37_REQUIRED_TABLES - {"proactive_news_polls"}):
                    connection.execute(f'DROP TABLE "{table}"')
                # 用数值比较删 v37 及以后的记录：字典序会把 v5 排到 v37 之后。
                connection.execute("DELETE FROM schema_migrations WHERE "
                                   "CAST(substr(from_version, length('companion-v2.storage.v') + 1) AS INTEGER) >= 37",
                                   ())
                for column in ("input_tokens", "cached_input_tokens", "cache_creation_tokens",
                               "output_tokens"):
                    connection.execute(f"ALTER TABLE model_calls DROP COLUMN {column}")
                connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'",
                                   (SCHEMA_VERSION_V37,))
                connection.commit()
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

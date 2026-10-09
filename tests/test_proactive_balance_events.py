"""Synthetic service-balance contact and host JSON adapter checks."""

import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from unittest.mock import patch
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from astrbot_host.service_balance import ServiceBalancePort, configured_balance_port
from companion_v2.proactive.balance_events import (BalanceObservation, SOURCE_OWNER, balance_level,
                                                    display_amount)
from companion_v2.storage.runtime import StorageOpenError, StorageRuntime
from companion_v2.storage.schema import SCHEMA_VERSION, SCHEMA_VERSION_V36
from tests.execution_support import remove_v37
from tests.contact_schedule_support import ContactScheduleFixture


class BalancePort:
    def __init__(self, clock, amounts):
        self.clock, self.amounts, self.calls = clock, list(amounts), 0

    async def fetch(self):
        self.calls += 1
        value = self.amounts.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, BalanceObservation):
            return value
        balance, total = value
        return BalanceObservation(Decimal(str(balance)), Decimal(str(total)) if total is not None else None,
                                  self.clock.now())


class BalanceContactTests(ContactScheduleFixture, unittest.IsolatedAsyncioTestCase):
    async def setup_balance(self, port, *, enabled=True, **changes):
        host, batch = await self.scheduled(balance_port=port)
        app = host.application
        self.settings(app, {"balance_awareness_enabled": enabled, "chat.enabled": False, **changes}).unwrap()
        return app, self.context(app, batch)

    async def test_opt_in_hides_amount_and_rechecks_source(self):
        port = BalancePort(self.clock, [("2.25", "100")])
        app, context = await self.setup_balance(port, enabled=False)
        self.advance(app, 60)
        app.contact_schedule.advance()
        self.assertEqual(port.calls, 0)
        self.settings(app, {"balance_awareness_enabled": True}).unwrap()
        app.contact_schedule.advance()
        await self.automatic_delivery(app)
        self.assertEqual(port.calls, 1)
        self.assertIn("balance_event", json.loads(self.contacts(app)[0]["record_json"])["automatic_origin"])
        material = next(item for item in self.contact_calls()[0].original.context.materials
                        if item.owner == SOURCE_OWNER)
        body = json.loads(material.payload)
        self.assertEqual(body["level"], "critical")
        self.assertNotIn("amount", body)
        self.assertNotIn("_receipt", body)
        self.assertNotIn("2.25", material.payload)
        source = material.source
        self.settings(app, {"balance_awareness_enabled": False}).unwrap()
        self.assertFalse(app.proactive.sources.validate_reference_for_audience(
            source, recipient=context.actor.subject, observed_at=self.clock.now()).is_success)

    async def test_cooldown_survives_restart_and_escalation_can_contact(self):
        port = BalancePort(self.clock, [("8", "100"), ("8", "100"), ("2", "100")])
        app, _ = await self.setup_balance(port, balance_check_interval_minutes=5,
            balance_message_cooldown_hours=24, balance_include_amount_in_message=True)
        self.advance(app, 60)
        await self.automatic_delivery(app)
        first = self.contact_calls()[0]
        body = json.loads(next(item for item in first.original.context.materials
                               if item.owner == SOURCE_OWNER).payload)
        self.assertEqual((body["level"], body["amount"], body["currency"]), ("low", "8.00", "元"))
        await app.close()
        restarted = (await self.start(self.host(runtime=self.open_runtime(), balance_port=port), 1, 1)).application
        restarted.contact_schedule.advance()
        self.assertEqual(port.calls, 1)
        self.clock.advance(timedelta(minutes=5))
        restarted.contact_schedule.advance()
        await self.until(lambda: port.calls == 2 and not restarted.contact_schedule.active_handles)
        self.assertEqual(len(self.contacts(restarted)), 1)
        self.assertTrue(restarted.proactive.sources.validate_reference_for_audience(
            next(item for item in first.original.context.materials if item.owner == SOURCE_OWNER).source,
            recipient=self.important.subject, observed_at=self.clock.now()).is_success)
        self.clock.advance(timedelta(minutes=5))
        restarted.contact_schedule.advance()
        await self.automatic_delivery(restarted, count=2)
        self.assertEqual(port.calls, 3)
        self.assertEqual(json.loads(self.contacts(restarted)[-1]["record_json"])["automatic_origin"]
                         ["balance_event"]["event_id"].startswith("balance-"), True)

    async def test_invalid_response_retries_without_persisting_or_contacting(self):
        port = BalancePort(self.clock, [ValueError("temporary"), ("2", None)])
        app, _ = await self.setup_balance(port)
        self.advance(app, 60)
        await self.until(lambda: port.calls == 1 and not app.contact_schedule.active_handles)
        self.assertIsNone(app.runtime.read_one("SELECT * FROM proactive_balance_polls", ()))
        self.clock.advance(timedelta(minutes=4))
        app.contact_schedule.advance()
        self.assertEqual(port.calls, 1)
        self.clock.advance(timedelta(minutes=1))
        app.contact_schedule.advance()
        await self.automatic_delivery(app)
        self.assertEqual(port.calls, 2)

    async def test_stale_observation_retries_and_config_change_discards_inflight_response(self):
        stale = BalanceObservation(Decimal("2"), None, self.clock.now() - timedelta(minutes=6))
        port = BalancePort(self.clock, [stale, ("2", None)])
        app, _ = await self.setup_balance(port)
        self.advance(app, 60)
        await self.until(lambda: port.calls == 1 and not app.contact_schedule.active_handles)
        self.assertIsNone(app.runtime.read_one("SELECT * FROM proactive_balance_polls", ()))
        app.contact_schedule.advance()
        self.assertEqual(port.calls, 1)
        self.clock.advance(timedelta(minutes=5))
        app.contact_schedule.advance()
        await self.automatic_delivery(app)
        self.assertEqual(port.calls, 2)

        pending = asyncio.Event()
        release = asyncio.Event()

        class DelayedPort:
            async def fetch(self):
                pending.set()
                await release.wait()
                return BalanceObservation(Decimal("2"), None, self.clock.now())

        delayed = DelayedPort()
        delayed.clock = self.clock
        await app.close()
        restarted = (await self.start(self.host(runtime=self.open_runtime(), balance_port=delayed), 1, 1)).application
        self.settings(restarted, {"balance_awareness_enabled": False}).unwrap()
        self.settings(restarted, {"balance_awareness_enabled": True}).unwrap()
        self.clock.advance(timedelta(hours=1))
        restarted.contact_schedule.advance()
        await asyncio.wait_for(pending.wait(), 3)
        self.settings(restarted, {"balance_awareness_enabled": False}).unwrap()
        release.set()
        await self.until(lambda: not restarted.contact_schedule.active_handles)
        self.assertEqual(len(self.contacts(restarted)), 1)


class BalanceAdapterTests(unittest.TestCase):
    def test_display_amount_uses_two_decimal_places(self):
        self.assertEqual(display_amount(Decimal("8")), "8.00")
        self.assertEqual(display_amount(Decimal("8.5")), "8.50")
        self.assertEqual(display_amount(Decimal("8.567")), "8.57")

    def test_nested_paths_divisor_and_total_used_fallback(self):
        at = datetime.now(timezone.utc)
        port = ServiceBalancePort(url="https://example.com/balance", total_path="data.0.total",
            used_path="data.0.used", balance_path="", divisor="100")
        observation = port.parse({"data": [{"total": 10000, "used": 9500}]}, at)
        self.assertEqual((observation.balance, observation.total), (Decimal("5"), Decimal("100")))
        with self.assertRaises(ValueError):
            port.parse({"data": [{"total": 10000, "used": True}]}, at)
        with self.assertRaises(ValueError):
            ServiceBalancePort(url="http://example.com/balance")
        with self.assertRaises(ValueError):
            ServiceBalancePort(url="https://user:secret@example.com/balance")

    def test_environment_configuration_and_percentage_threshold(self):
        with patch.dict("os.environ", {
            "COMPANION_V2_BALANCE_URL": "https://example.com/balance",
            "COMPANION_V2_BALANCE_TOTAL_JSON_PATH": "data.total",
            "COMPANION_V2_BALANCE_USED_JSON_PATH": "data.used",
            "COMPANION_V2_BALANCE_VALUE_DIVISOR": "100",
        }, clear=True):
            port = configured_balance_port()
        observation = port.parse({"data": {"total": 100000, "used": 95000}}, datetime.now(timezone.utc))
        self.assertEqual((observation.balance, observation.total), (Decimal("50"), Decimal("1000")))
        self.assertEqual(balance_level(observation, {"balance_critical_threshold": 3,
            "balance_low_threshold": 10, "balance_critical_percent_threshold": 5,
            "balance_low_percent_threshold": 15}), "critical")

    def test_newapi_preset_reads_user_quota_and_normalizes_the_configured_unit(self):
        with patch.dict("os.environ", {
            "COMPANION_V2_BALANCE_PROVIDER": "newapi",
            "COMPANION_V2_BALANCE_URL": "https://gateway.example.com/proxy/",
            "COMPANION_V2_BALANCE_API_KEY": "dashboard-access-token",
            "COMPANION_V2_BALANCE_CURRENCY_LABEL": "USD",
        }, clear=True):
            port = configured_balance_port()
        self.assertEqual(port.url, "https://gateway.example.com/proxy/api/user/self")
        self.assertEqual(port.headers["Authorization"], "Bearer dashboard-access-token")
        self.assertEqual((port.provider, port.provider_label, port.currency_label),
                         ("newapi", "NewAPI", "USD"))
        observation = port.parse({"success": True, "data": {"quota": 4250000, "used_quota": 250000}},
                                 datetime.now(timezone.utc))
        self.assertEqual(observation.balance, Decimal("8.5"))
        self.assertIsNone(observation.total)
        with self.assertRaises(ValueError):
            port.parse({"success": False, "message": "unauthorized"}, datetime.now(timezone.utc))

    def test_newapi_known_aliases_are_fallback_only_for_the_newapi_provider(self):
        from astrbot_host.service_balance import _newapi_compatible_urls

        self.assertEqual(_newapi_compatible_urls("https://api.syuan.org"), (
            "https://api.syuan.org/api/user/self", "https://ai.syuan.org/api/user/self"))
        self.assertEqual(_newapi_compatible_urls("https://ai.syuan.org/api/user/self"), (
            "https://ai.syuan.org/api/user/self", "https://api.syuan.org/api/user/self"))
        self.assertEqual(ServiceBalancePort(url="https://api.syuan.org/balance").request_urls,
                         ("https://api.syuan.org/balance",))

    def test_dashboard_newapi_settings_take_precedence_over_environment(self):
        with patch.dict("os.environ", {
            "COMPANION_V2_BALANCE_PROVIDER": "newapi",
            "COMPANION_V2_BALANCE_URL": "https://environment.example.com",
            "COMPANION_V2_BALANCE_API_KEY": "environment-token",
        }, clear=True):
            port = configured_balance_port({"service_balance": {
                "url": "https://dashboard.example.com/base",
                "api_key": "dashboard-token",
                "user_id": "1234",
                "value_divisor": "1000000",
            }})

        self.assertEqual(port.url, "https://dashboard.example.com/base/api/user/self")
        self.assertEqual(port.headers["Authorization"], "Bearer dashboard-token")
        self.assertEqual(port.headers["New-Api-User"], "1234")
        self.assertEqual(port.divisor, Decimal("1000000"))
        with self.assertRaises(ValueError):
            configured_balance_port({"service_balance": {"url": "https://dashboard.example.com"}})


class BalanceFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_newapi_retries_the_known_alias_after_a_failed_first_host(self):
        calls = []

        class Content:
            def __init__(self, body):
                self.body = body

            async def read(self, _limit):
                return self.body

        class Reply:
            def __init__(self, status, body):
                self.status, self.content_length = status, len(body)
                self.content = Content(body)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

        class Session:
            def __init__(self, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            def get(self, url, **_kwargs):
                calls.append(url)
                if url.startswith("https://api.syuan.org"):
                    return Reply(503, b"unavailable")
                return Reply(200, b'{"success":true,"data":{"quota":4250000}}')

        port = ServiceBalancePort(url="https://api.syuan.org/api/user/self", provider="newapi",
                                  balance_path="data.quota", divisor="500000")
        with patch("astrbot_host.service_balance.aiohttp.ClientSession", Session):
            observation = await port.fetch()
        self.assertEqual(calls, ["https://api.syuan.org/api/user/self", "https://ai.syuan.org/api/user/self"])
        self.assertEqual(observation.balance, Decimal("8.5"))


class BalanceStorageTests(unittest.TestCase):
    def test_v36_upgrade_preserves_existing_rows_and_rejects_partial_migration(self):
        with TemporaryDirectory(prefix="companion-v2-balance-") as temporary:
            root = Path(temporary) / "v2-data"
            runtime = StorageRuntime.open(data_root=root, installation_id="balance-test")
            with runtime.transaction() as connection:
                connection.execute("INSERT INTO runtime_metadata VALUES (?, ?)", ("balance-test-marker", "kept"))
            database = runtime.database_path
            runtime.close()
            with closing(sqlite3.connect(database)) as connection:
                remove_v37(connection)
                connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'", (SCHEMA_VERSION_V36,))
                connection.commit()
            upgraded = StorageRuntime.open(data_root=root, installation_id="balance-test")
            self.assertEqual(upgraded.read_one("SELECT value FROM runtime_metadata WHERE key = ?",
                                               ("schema_version",))[0], SCHEMA_VERSION)
            self.assertEqual(upgraded.read_one("SELECT value FROM runtime_metadata WHERE key = ?",
                                               ("balance-test-marker",))[0], "kept")
            upgraded.close()
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = 'schema_version'",
                                   (SCHEMA_VERSION_V36,))
                connection.commit()
            with self.assertRaises(StorageOpenError):
                StorageRuntime.open(data_root=root, installation_id="balance-test")


if __name__ == "__main__":
    unittest.main()

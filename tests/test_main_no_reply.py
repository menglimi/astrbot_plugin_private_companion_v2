"""The AstrBot entry records only the replies that were actually expected."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests import test_astrbot_staging_host as _astrbot_test_runtime
from tests.test_management_access import INSTALLATION, NOW
from companion_v2.foundation.outcome import Outcome
from companion_v2.storage.runtime import StorageRuntime


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "_companion_v2_no_reply_entry_test"
PACKAGE = ModuleType(PACKAGE_NAME)
PACKAGE.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = PACKAGE
SPEC = importlib.util.spec_from_file_location(PACKAGE_NAME + ".main", ROOT / "main.py")
ENTRY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ENTRY
SPEC.loader.exec_module(ENTRY)


def private_event():
    event = NS(platform_meta=NS(name="aiocqhttp"),
                message_obj=NS(type=NS(value="FriendMessage"), raw_message={"post_type": "message"}),
                stopped=False)
    event.stop_event = lambda: setattr(event, "stopped", True)
    return event


def group_event():
    event = NS(platform_meta=NS(name="aiocqhttp"),
                message_obj=NS(type=NS(value="GroupMessage"), raw_message={"post_type": "message"}),
                stopped=False)
    event.stop_event = lambda: setattr(event, "stopped", True)
    return event


class MainNoReplyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-entry-no-reply-")
        self.addCleanup(self.temporary.cleanup)
        self.runtime = StorageRuntime.open(data_root=Path(self.temporary.name),
                                           installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        self.target = NS(key="configured-role")
        self.staging = NS(
            runtime=self.runtime,
            now=lambda: NOW,
            claims=lambda _event: False,
            target_for_event=lambda _event: None,
            settings=NS(enabled=True),
            settings_error=None,
            _accepting=False,
            _terminated=False,
            session=NS(profile=NS(target=self.target)),
            session_topology=NS(reply_enabled=AsyncMock(return_value=True), observe=AsyncMock()),
            persona_mapping_for_event=AsyncMock(return_value=NS(role_id="registered-role")),
            group_reply_candidate=AsyncMock(),
            receive_claimed=AsyncMock(side_effect=RuntimeError("synthetic processing failure")),
            terminate=AsyncMock(),
        )
        self.plugin.staging = self.staging

    async def asyncTearDown(self):
        await self.plugin.terminate()

    async def test_unmatched_private_target_is_neither_logged_nor_recorded(self):
        # A private message this installation never configured is not a failure
        # of this plugin: it produced no expectation, so it produces no outcome.
        event = private_event()

        with patch.object(ENTRY, "refuse_stranger", new=AsyncMock(return_value=None)):
            await self.plugin.receive_companion_message(event)

        self.assertEqual(self.runtime.read_all("SELECT * FROM inbound_no_replies", ()), ())
        self.assertFalse(event.stopped)

    async def test_configured_private_target_not_accepting_is_recorded(self):
        self.staging.target_for_event = lambda _event: self.target
        event = private_event()

        with self.assertLogs("companion_v2.diagnostics.inbound", level="WARNING") as captured:
            await self.plugin.receive_companion_message(event)

        row = self.runtime.read_one("SELECT * FROM inbound_no_replies", ())
        self.assertEqual(row["reason_code"], "staging_not_accepting")
        self.assertEqual(row["channel"], "private")
        self.assertEqual(row["origin_key"], self.target.key)
        self.assertIn("stage=admission", captured.output[0])
        self.assertIn("expected=true reason=staging_not_accepting", captured.output[0])
        self.assertFalse(event.stopped)

    async def test_exception_after_v2_claims_private_message_is_recorded(self):
        self.staging.claims = lambda _event: True
        self.staging.target_for_event = lambda _event: self.target
        event = private_event()

        await self.plugin.receive_companion_message(event)

        row = self.runtime.read_one("SELECT * FROM inbound_no_replies", ())
        self.assertEqual(row["reason_code"], "inbound_processing_failed")
        self.assertEqual(row["origin_key"], self.target.key)
        self.assertFalse(event.stopped)
        self.assertTrue(event.call_llm)

    async def test_unregistered_persona_passes_through_without_stopping_or_logging(self):
        self.staging.claims = lambda _event: True
        self.staging.target_for_event = lambda _event: self.target
        self.staging.persona_mapping_for_event = AsyncMock(return_value=None)
        event = private_event()

        await self.plugin.receive_companion_message(event)

        self.assertFalse(event.stopped)
        self.staging.receive_claimed.assert_not_awaited()
        self.assertEqual(self.runtime.read_all("SELECT * FROM inbound_no_replies", ()), ())

    async def test_competing_astrbot_command_passes_through_a_claimed_route(self):
        from astrbot.core.star.filter.command import CommandFilter

        self.staging.claims = lambda _event: True
        self.staging.target_for_event = lambda _event: self.target
        event = group_event()
        command_handler = NS(
            handler_module_path="other_plugin.commands",
            handler_full_name="other_plugin.commands.handle",
            event_filters=[CommandFilter("other")],
        )
        event.get_extra = lambda key=None, default=None: (
            {"activated_handlers": [command_handler]}.get(key, default)
            if key is not None else {"activated_handlers": [command_handler]}
        )

        await self.plugin.receive_companion_message(event)

        self.assertFalse(event.stopped)
        self.staging.persona_mapping_for_event.assert_not_awaited()
        self.staging.receive_claimed.assert_not_awaited()

    async def test_unsupported_group_component_passes_through_to_astrbot(self):
        self.staging.claims = lambda _event: True
        self.staging.target_for_event = lambda _event: self.target
        self.staging.group_reply_candidate.return_value = NS(
            failure=NS(code="host_group_media_unsupported"))
        event = group_event()

        await self.plugin.receive_companion_message(event)

        self.assertFalse(event.stopped)
        self.staging.receive_claimed.assert_not_awaited()
        self.assertEqual(self.runtime.read_all("SELECT * FROM inbound_no_replies", ()), ())

    async def test_group_silent_choice_suppresses_only_astrbot_fallback(self):
        self.staging.claims = lambda _event: True
        self.staging.target_for_event = lambda _event: self.target
        self.staging.group_reply_candidate.return_value = NS(
            failure=None, unwrap=lambda: {"admitted": False})
        event = group_event()

        await self.plugin.receive_companion_message(event)

        self.assertFalse(event.stopped)
        self.assertTrue(event.call_llm)
        self.staging.receive_claimed.assert_not_awaited()


class StartupRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_plugin_retries_startup_until_onebot_account_is_ready(self):
        plugin = ENTRY.PrivateCompanionV2StagingPlugin.__new__(ENTRY.PrivateCompanionV2StagingPlugin)
        plugin._host_start_task = None
        plugin.staging = NS(
            settings=NS(enabled=True),
            _terminated=False,
            _accepting=False,
            session=None,
            startup_readiness=Mock(side_effect=(
                "host_platform_unavailable", "host_account_unavailable", None)),
            load_existing=AsyncMock(return_value=Outcome.success({"loaded": True})),
            start=AsyncMock(return_value=Outcome.success({"state": "running"})),
        )

        await plugin.initialize()
        task = plugin._host_start_task
        self.assertIsNotNone(task)
        await asyncio.wait_for(task, timeout=3)

        self.assertEqual(plugin.staging.startup_readiness.call_count, 3)
        plugin.staging.load_existing.assert_awaited_once()
        plugin.staging.start.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

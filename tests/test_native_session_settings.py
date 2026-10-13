import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from tests import test_astrbot_staging_host as _host_import_root
from astrbot_host import native
from astrbot_host.session_topology import SessionTopology


class NativeSessionSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_reads_share_one_lookup_and_dashboard_write_refreshes_cache(self):
        umo = "fixture:FriendMessage:995051631"
        native._session_settings_cache.pop(umo, None)
        native._session_settings_reads.pop(umo, None)
        native._session_settings_versions.pop(umo, None)
        entered, release = asyncio.Event(), asyncio.Event()

        async def read_settings(**_kwargs):
            entered.set()
            await release.wait()
            return {"session_enabled": True}

        lookup = AsyncMock(side_effect=read_settings)
        try:
            with patch.object(native.sp, "get_async", lookup):
                first = asyncio.create_task(native.load_session_settings(umo))
                await entered.wait()
                second = asyncio.create_task(native.load_session_settings(umo))
                await asyncio.sleep(0)
                self.assertEqual(lookup.await_count, 1)
                release.set()
                self.assertEqual(await asyncio.gather(first, second),
                                 [{"session_enabled": True}, {"session_enabled": True}])
                native.remember_session_settings(umo, {"session_enabled": False})
                self.assertEqual(await native.load_session_settings(umo), {"session_enabled": False})
                self.assertEqual(lookup.await_count, 1)
        finally:
            native._session_settings_cache.pop(umo, None)
            native._session_settings_reads.pop(umo, None)
            native._session_settings_versions.pop(umo, None)

    async def test_startup_warmup_loads_only_valid_window_settings(self):
        umo = "fixture:FriendMessage:995051632"
        row = NS(scope_id=umo, value={"val": {"session_enabled": False, "persona_id": "warm"}})
        native._session_settings_cache.pop(umo, None)
        native._session_settings_versions.pop(umo, None)
        try:
            with patch.object(native.sp, "range_get_async", AsyncMock(return_value=[
                    row, NS(scope_id="", value={"val": {}}), NS(scope_id="bad", value={"val": []})])):
                self.assertEqual(await native.warm_session_settings(), 1)
            self.assertEqual(await native.load_session_settings(umo),
                             {"session_enabled": False, "persona_id": "warm"})
        finally:
            native._session_settings_cache.pop(umo, None)
            native._session_settings_versions.pop(umo, None)

    async def test_expired_cache_is_served_while_refresh_runs(self):
        umo = "fixture:FriendMessage:995051633"
        entered, release = asyncio.Event(), asyncio.Event()

        async def read_settings(**_kwargs):
            entered.set()
            await release.wait()
            return {"session_enabled": False}

        native._session_settings_cache.pop(umo, None)
        native._session_settings_reads.pop(umo, None)
        native._session_settings_versions.pop(umo, None)
        try:
            with patch.object(native.sp, "get_async", AsyncMock(side_effect=read_settings)):
                native.remember_session_settings(umo, {"session_enabled": True})
                native._session_settings_cache[umo] = (0, {"session_enabled": True})
                self.assertEqual(await native.load_session_settings(umo), {"session_enabled": True})
                task = native._session_settings_reads[umo]
                await entered.wait()
                release.set()
                await task
                self.assertEqual(await native.load_session_settings(umo), {"session_enabled": False})
        finally:
            release.set()
            native._session_settings_cache.pop(umo, None)
            native._session_settings_reads.pop(umo, None)
            native._session_settings_versions.pop(umo, None)

    async def test_reply_switch_timeout_keeps_astrbot_core_path_available(self):
        umo = "fixture:FriendMessage:995051634"
        entered, release = asyncio.Event(), asyncio.Event()

        async def read_settings(**_kwargs):
            entered.set()
            await release.wait()
            return {"session_enabled": False, "llm_enabled": False}

        native._session_settings_cache.pop(umo, None)
        native._session_settings_reads.pop(umo, None)
        native._session_settings_versions.pop(umo, None)
        topology = SessionTopology(NS(data_root=Path(".")))
        event = NS(unified_msg_origin=umo)
        try:
            with patch.object(native, "SESSION_SETTINGS_LOOKUP_BUDGET_SECONDS", 0.01), \
                    patch.object(native.sp, "get_async", AsyncMock(side_effect=read_settings)), \
                    self.assertLogs("astrbot_host.session_topology", level="WARNING") as captured:
                self.assertTrue(await topology.reply_enabled(event))
            self.assertIn("继续 AstrBot 核心回复", "\n".join(captured.output))
            task = native._session_settings_reads[umo]
            await entered.wait()
            release.set()
            await task
            self.assertFalse(await topology.reply_enabled(event))
        finally:
            release.set()
            native._session_settings_cache.pop(umo, None)
            native._session_settings_reads.pop(umo, None)
            native._session_settings_versions.pop(umo, None)


if __name__ == "__main__":
    unittest.main()

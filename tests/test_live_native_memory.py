"""Live native writes, actual reply context and platform identity separation."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests import test_astrbot_staging_host as host_support
from astrbot_host.native_extensions.live.bilibili_live import LiveDanmakuEvent
from astrbot_host.native_extensions.live.runtime import LiveRuntime
from astrbot_host.native_extensions.live.state import LiveStateStore
from astrbot_host.native_extensions.together.activity_methods import TogetherActivityMethods


class LiveNativeMemoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="v2-live-native-memory-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.controller = NS(native_extensions=None, session=None, settings=None)
        self.context = NS(get_all_stars=lambda: ())
        self.config = {"auto_connect": False, "live_auto_register_min_events": 1,
                       "live_afterglow_enabled": False, "bili_live_log_events": False,
                       "twitch_live_log_events": False, "bilibili_ai_memory_integration_enabled": False}
        self.live = LiveRuntime(self.context, self.config,
                                self.root / "extensions" / "live", self.controller)
        self.addAsyncCleanup(self.live.terminate)

    def event(self, text, *, platform="bili", uid="42", username="同名观众"):
        return LiveDanmakuEvent("danmaku", username, text,
                               raw={"platform": platform, "user_id": uid, "login": "viewer"})

    async def test_bili_native_input_persists_and_actual_auxiliary_recalls_it(self):
        event = self.event("下次想看月亮的故事")
        await self.live._on_bili_live_event(event)
        await self.live._write_private_companion_live_event(event)
        context = await self.live._build_bili_live_auxiliary_context([event])
        self.assertIn("直播专用记忆上下文", context)
        self.assertIn(event.content, context)
        state = LiveStateStore(self.live).data["live_stream_companion"]
        self.assertEqual(state["viewer_activity"]["bili:42"]["total_events"], 1)
        self.assertEqual(state["memory_items"][0]["text"], event.content)
        self.assertEqual(state["memory_items"][0]["platform"], "bili")

    async def test_memory_switches_control_write_and_actual_reply_injection(self):
        event = self.event("记得下次聊银河")
        await self.live._on_bili_live_event(event)
        self.live.config["live_memory_context_enabled"] = False
        self.assertNotIn("直播专用记忆上下文",
                         await self.live._build_bili_live_auxiliary_context([event]))
        self.assertFalse(self.live._live_memory_status()["recall_enabled"])
        self.live.config["live_memory_context_enabled"] = True
        self.live.config["live_memory_enabled"] = False
        self.assertNotIn("直播专用记忆上下文",
                         await self.live._build_bili_live_auxiliary_context([event]))
        await self.live._on_bili_live_event(self.event("想听新的话题", uid="43"))
        self.assertEqual(len(self.live._v2_live_state_store()["memory_items"]), 1)

    async def test_same_nickname_and_same_number_never_merge_platform_accounts(self):
        profiles = self.live._live_state_store.data["profiles"]
        profiles["private-person"] = {"name": "同名观众", "aliases": [], "enabled": True,
            "important_memories": [{"content": "私人秘密", "source": "private_memory"}],
            "external_ids": ["qq:42"]}
        bili = self.event("想看B站游戏", uid="42")
        twitch = self.event("想听Twitch歌曲", platform="twitch", uid="42")
        stranger = self.event("想聊不同的话题", uid="43")
        self.assertIsNone(self.live._match_private_companion_member(
            self.live._live_state_store.owner, bili.username, bili))
        await self.live._on_bili_live_event(bili)
        await self.live._on_twitch_live_event(twitch)
        await self.live._on_bili_live_event(stranger)
        bili_state = self.live._v2_live_state_store()
        twitch_state = self.live._v2_live_state_store(platform="twitch")
        self.assertEqual(set(bili_state["viewer_activity"]), {"bili:42", "bili:43"})
        self.assertEqual(set(twitch_state["viewer_activity"]), {"twitch:42"})
        self.assertEqual(bili_state["viewer_activity"]["bili:42"]["total_events"], 1)
        recalled = self.live._build_live_stream_memory_context([twitch])
        self.assertIn(twitch.content, recalled)
        self.assertNotIn(bili.content, recalled)
        self.assertNotIn("私人秘密", recalled)
        self.assertEqual(len(profiles["private-person"]["important_memories"]), 1)

    async def test_twitch_persists_uses_reply_memory_and_writes_stop_summary(self):
        event = self.event("下次想听夜航", platform="twitch")
        self.live._twitch_session_started_at = time.time() - 120
        self.live._twitch_session_id = "twitch-session"
        await self.live._on_twitch_live_event(event)
        provider = NS(text_chat=AsyncMock(return_value=NS(completion_text="好呀，下次唱夜航")))
        self.context.get_using_provider = lambda *args: provider
        self.live._get_twitch_reply_session = AsyncMock(return_value="qq:FriendMessage:200")
        self.live._send_twitch_reply = AsyncMock(return_value=True)
        self.assertTrue(await self.live._reply_to_twitch_live_events([event]))
        prompt = provider.text_chat.call_args.kwargs["system_prompt"]
        self.assertIn("直播专用记忆上下文", prompt)
        self.assertIn(event.content, prompt)
        await self.live._stop_twitch_live(log=False)
        state = LiveStateStore(self.live).data["live_stream_companion"]["platforms"]["twitch"]
        self.assertEqual(state["memory_items"][0]["text"], event.content)
        self.assertEqual(state["summaries"][0]["platform"], "twitch")
        self.assertIn("Twitch", state["summaries"][0]["summary"])

    async def test_relationship_context_requires_account_link_and_obeys_switch(self):
        event = self.event("早呀")
        self.live._live_state_store.data["profiles"]["linked-viewer"] = {
            "name": "海风", "external_ids": ["bili:42"], "enabled": True,
            "important_memories": [{"content": "私聊秘密", "source": "private_memory"},
                                   {"content": "上次直播一起数星星", "source": "live_stream_companion"}]}
        self.live.config["live_relationship_style_include_memories"] = True
        context = await self.live._build_bili_live_auxiliary_context([event])
        self.assertIn("海风", context)
        self.assertIn("上次直播一起数星星", context)
        self.assertNotIn("私聊秘密", context)
        self.live.config["live_relationship_context_enabled"] = False
        self.assertNotIn("海风", await self.live._build_bili_live_auxiliary_context([event]))
        self.live.config["live_relationship_context_enabled"] = True
        same_name_unknown_account = self.event("早呀", uid="43", username="海风")
        self.assertEqual(self.live._build_native_live_relationship_context([same_name_unknown_account]), "")

    async def test_profile_names_refresh_after_attach_and_follow_current_role(self):
        route = {"installation_id": "install", "platform": "qq-main", "bot_id": "bot-a",
                 "account_id": "100", "role_id": "role-a", "subject_id": "person-a"}
        scope = NS(**{key: value for key, value in route.items() if key not in {"role_id", "subject_id"}},
                   kind=NS(value="private"), native_scope_id="200")
        context = NS(scope=scope, actor=NS(subject=NS(subject_id="person-a")),
                     role_binding=NS(role=NS(subject_id="role-a")))
        def document(name, **changes):
            return {"document_json": json.dumps({"route": {**route, **changes},
                "native_account_id": "200", "platform_nickname": name,
                "important_memories": [{"content": "不应投影的私人内容"}]})}
        storage = NS(read_all=Mock(return_value=[document("小环"),
            document("另一个角色", role_id="role-b", subject_id="person-b"),
            document("另一个机器人", bot_id="bot-b", subject_id="person-c")]))
        application = NS(runtime=storage, state="running")
        self.controller.native_extensions = NS(application=application)
        self.controller.session = NS(application=application, profile=NS(target=context))
        self.controller._multi_host = True
        await self.live.put_kv_data("bili_live_reply_session", "qq-main:FriendMessage:200")
        self.live._initialize_runtime = AsyncMock()
        with patch("astrbot_host.mobile_together.MobileTogetherBridge._target_context",
                   return_value=(self.controller.session, application, context)):
            await self.live.initialize()
            profiles = self.live._live_state_store.data["profiles"]
            self.assertEqual(set(profiles), {"v2:person-a"})
            self.assertNotIn("important_memories", profiles["v2:person-a"])
            self.assertEqual(self.live._bili_live_streamer_identity()["name"], "小环")
            context.role_binding = NS(role=NS(subject_id="role-b"))
            self.live._get_v2_live_state_owner()
            self.assertEqual(set(profiles), {"v2:person-b"})
            self.assertEqual(self.live._live_state_store.configured_target_ids(), [])

    def test_together_finds_screen_native_ffmpeg_directory(self):
        runtime = NS(data_dir=self.root / "extensions" / "together")
        executable = self.root / "extensions" / "screen" / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"synthetic executable")
        with patch("astrbot_host.native_extensions.together.activity_methods.shutil.which", return_value=None), \
             patch("astrbot_host.native_extensions.together.activity_methods.get_astrbot_data_path", return_value=str(self.root / "host")):
            self.assertEqual(TogetherActivityMethods._ffmpeg_path(runtime), executable)


if __name__ == "__main__":
    unittest.main()

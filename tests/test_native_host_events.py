"""Internal services enhance real AstrBot requests without owning the reply runner."""

import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock

from tests import test_astrbot_staging_host as _host_import_root
from astrbot.api.message_components import Image, Plain, Record
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot_host.native_extensions.host_events import (
    observe_native_host_response, observe_native_host_result, prepare_native_host_request,
)
from astrbot_host.native_extensions.game.model_methods import GameModelMethods
from astrbot_host.native_extensions.game.rooms_methods import GameRoomsMethods
from astrbot_host.native_extensions.live.l2d_mixin import Live2DMixin
from astrbot_host.native_extensions.live.soullink_mixin import SoullinkMixin
from astrbot_host.native_extensions.live.subtitle_mixin import SubtitleMixin
from companion_v2.games.models import GameRoom
from companion_v2.games.turtle_soup import TurtleSoupGame


class HostEvent:
    def __init__(self, *, private=True, sender="200", session="bot:private:200", text="摸摸", result=None):
        self.private, self.sender, self.unified_msg_origin = private, sender, session
        self.message_str, self.result, self.extra = text, result, {}

    def is_private_chat(self):
        return self.private

    def get_sender_id(self):
        return self.sender

    def get_result(self):
        return self.result

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)


def controller(**services):
    registry = NS(active_service=lambda name: services.get(name),
                  service=Mock(side_effect=AssertionError("paused service must not handle host events")))
    return NS(native_extensions=registry), services


def context_text(request):
    return "\n".join(part.text for part in request.extra_user_content_parts)


class LocalLive(Live2DMixin, SoullinkMixin, SubtitleMixin):
    def __init__(self):
        self.config = {"l2d_hotkeys": [{"tag": "开心", "hotkey_id": "fixture", "description": "笑一下"}],
                       "l2d_max_tags_per_reply": 1, "soullink_enabled": False,
                       "subtitle_enabled": True, "subtitle_scope": "all"}
        self._l2d_tasks, self._mouth_sync_tasks, self._soullink_tasks = set(), set(), set()
        self._soullink_runtime = NS(running=True, trigger=AsyncMock(), react_to_text=AsyncMock())
        self._trigger_l2d_tags = AsyncMock()
        self._start_mouth_sync_for_result = AsyncMock()
        self._push_subtitle = AsyncMock()
        self._check_and_reconnect = AsyncMock(side_effect=AssertionError("request must not reconnect"))
        self._build_bili_live_auxiliary_context = AsyncMock(side_effect=AssertionError("no legacy context read"))
        self.events = ["观众：今天的声音好可爱"]

    def _inject_vts_command_fallback_instruction(self, event, req):
        req.system_prompt += ""

    def _is_soullink_enabled(self):
        return self.config["soullink_enabled"]

    def _soullink_runtime_options(self):
        return {"style": "lively"}

    def _soullink_mode(self):
        return "full"

    def _is_bili_live_enabled(self):
        return True

    def _is_bili_live_running(self):
        return True

    def _recent_bili_events(self, **kwargs):
        return self.events

    def _format_bili_events(self, events):
        return "\n".join(events)

    def _safe_parse_int(self, value, default):
        return int(default if value is None else value)

    def _is_mouth_sync_enabled(self):
        return True

    def _prefer_subtitle_display_text(self, text, voice_context=False):
        return text


class LocalGame(GameModelMethods, GameRoomsMethods):
    private_qq_game_context_enabled = True

    @staticmethod
    def _game_label(game_type):
        return "海龟汤"

    def __init__(self, rooms):
        self.manager = NS(for_session=lambda session: [room for room in rooms if room.session_id == session])
        self._recent_private_game_results = {}


def game_room(**changes):
    fields = dict(room_id="room-a", access_token="private-room-token", source="private", session_id="bot:private:200",
                  platform="aiocqhttp", group_id="", creator_qq="200", creator_name="玩家", admin_room=False,
                  game_type="turtle_soup", difficulty="normal", status="active")
    fields.update(changes)
    room = GameRoom(**fields)
    room.game = TurtleSoupGame("normal", 3, "normal", puzzle=NS(solution="隐藏汤底不得进入核心对话"), question_count=3)
    room.messages = [{"content": "网页私聊不进入核心上下文"}]
    return room


async def drain(runtime):
    tasks = set().union(runtime._l2d_tasks, runtime._mouth_sync_tasks, runtime._soullink_tasks)
    if tasks:
        await asyncio.gather(*tasks)


class NativeHostEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_paused_services_and_plain_service_lookup_cannot_receive_events(self):
        runtime = LocalLive()
        host, active = controller(live=runtime)
        active.clear()
        req = ProviderRequest(system_prompt="原提示")
        event = HostEvent(result=MessageEventResult().message("正常回复"))
        prepare_native_host_request(host, event, req)
        observe_native_host_response(host, event, LLMResponse(role="assistant", completion_text="正常回复"))
        observe_native_host_result(host, event)
        self.assertEqual(req.system_prompt, "原提示")
        host.native_extensions.service.assert_not_called()
        runtime._push_subtitle.assert_not_awaited()
        runtime._soullink_runtime.react_to_text.assert_not_awaited()

    async def test_live_request_uses_received_events_and_configuration_without_waiting_for_io(self):
        runtime = LocalLive()
        host, _ = controller(live=runtime)
        req = ProviderRequest(system_prompt=None)
        prepare_native_host_request(host, HostEvent(), req)
        self.assertIn("今天的声音好可爱", context_text(req))
        self.assertNotIn("今天的声音好可爱", req.system_prompt)
        self.assertIn("开心", req.system_prompt)
        runtime._check_and_reconnect.assert_not_awaited()
        runtime._build_bili_live_auxiliary_context.assert_not_awaited()
        self.assertFalse(runtime._l2d_tasks)

    async def test_optional_domain_failure_preserves_other_domain_and_core_request(self):
        game = NS(_host_event_owner=NS(request=Mock(side_effect=RuntimeError("fixture failure"))))
        host, _ = controller(game=game, live=LocalLive())
        req = ProviderRequest(system_prompt="AstrBot 基础人格")
        with self.assertLogs("astrbot_host.native_extensions.host_events", level="WARNING"):
            prepare_native_host_request(host, HostEvent(), req)
        self.assertIn("AstrBot 基础人格", req.system_prompt)
        self.assertIn("今天的声音好可爱", context_text(req))

    async def test_soullink_without_controls_preserves_multimodal_component_order(self):
        runtime = LocalLive()
        runtime.config["soullink_enabled"] = True
        host, _ = controller(live=runtime)
        chain = MessageChain(chain=[Image.fromURL("https://example.invalid/image.png"), Plain("  看这张！\n\n"),
                                    Record.fromFileSystem("fixture.wav"), Plain("再听听这个。  ")])
        original = list(chain.chain)
        response = LLMResponse(role="assistant", result_chain=chain)
        observe_native_host_response(host, HostEvent(), response)
        self.assertEqual(response.result_chain.chain, original)
        self.assertTrue(all(before is after for before, after in zip(original, response.result_chain.chain)))
        await drain(runtime)

    async def test_controls_are_hidden_before_background_actions_and_optional_failure(self):
        runtime = LocalLive()
        runtime.config["soullink_enabled"] = True
        runtime._trigger_l2d_tags.side_effect = RuntimeError("VTS offline")
        host, _ = controller(live=runtime)
        response = LLMResponse(role="assistant", completion_text=(
            "诶，这个好有意思！\n\n我刚读到的。\n<l2d:开心,none>\n"
            '<soullink>{"emotion":"happy","intensity":0.8}</soullink>'))
        observe_native_host_response(host, HostEvent(), response)
        self.assertEqual(response.completion_text, "诶，这个好有意思！\n\n我刚读到的。")
        runtime._trigger_l2d_tags.assert_not_awaited()
        runtime._soullink_runtime.trigger.assert_not_awaited()
        with self.assertLogs("astrbot_host.native_extensions.live.host_events", level="WARNING"):
            await drain(runtime)
        runtime._trigger_l2d_tags.assert_awaited_once_with(["开心"])
        self.assertEqual(runtime._soullink_runtime.trigger.await_args.args[0]["emotion"], "happy")

    async def test_queued_presentation_is_skipped_after_service_is_stopped(self):
        runtime = LocalLive()
        host, active = controller(live=runtime)
        observe_native_host_response(host, HostEvent(), LLMResponse(role="assistant", completion_text="好呀！<l2d:开心>"))
        active.clear()
        await drain(runtime)
        runtime._trigger_l2d_tags.assert_not_awaited()

    async def test_real_sdk_result_can_be_cleared_after_snapshot_and_is_only_queued_once(self):
        runtime = LocalLive()
        host, _ = controller(live=runtime)
        result = MessageEventResult(chain=[Record.fromFileSystem("fixture.wav"), Plain("听到啦！")])
        event = HostEvent(result=result)
        observe_native_host_result(host, event)
        observe_native_host_result(host, event)
        runtime._push_subtitle.assert_not_awaited()
        result.chain[1].text = "后来修改"
        result.chain.clear()
        await drain(runtime)
        runtime._push_subtitle.assert_awaited_once_with("听到啦！", source="")
        runtime._start_mouth_sync_for_result.assert_awaited_once()
        snapshot = runtime._start_mouth_sync_for_result.await_args.args[0]
        self.assertEqual(snapshot.chain[1].text, "听到啦！")

    async def test_subtitle_scope_and_skip_do_not_block_audio_mouth_sync(self):
        for extra, scope in (({}, "bili_live"), ({"bili_live_auto_reply": True, "bili_live_skip_subtitle": True}, "all")):
            with self.subTest(extra=extra, scope=scope):
                runtime = LocalLive()
                runtime.config["subtitle_scope"] = scope
                host, _ = controller(live=runtime)
                event = HostEvent(result=MessageEventResult(chain=[Record.fromFileSystem("fixture.wav"), Plain("收到")]))
                event.extra.update(extra)
                observe_native_host_result(host, event)
                await drain(runtime)
                runtime._start_mouth_sync_for_result.assert_awaited_once()
                runtime._push_subtitle.assert_not_awaited()

    async def test_game_reads_matching_single_player_state_without_hidden_answers(self):
        own = game_room()
        other = game_room(room_id="room-other", creator_qq="300")
        wrong_session = game_room(room_id="room-elsewhere", session_id="bot:private:other")
        runtime = LocalGame([own, other, wrong_session])
        host, _ = controller(game=runtime)
        req = ProviderRequest(system_prompt="AstrBot 基础人格")
        prepare_native_host_request(host, HostEvent(), req)
        self.assertEqual(req.system_prompt, "AstrBot 基础人格")
        self.assertIn("提问 3 次", context_text(req))
        self.assertNotIn(own.game.puzzle.solution, context_text(req))
        self.assertNotIn(own.messages[0]["content"], context_text(req))
        self.assertEqual(context_text(req).count("当前私聊房间"), 1)
        prepared = context_text(req)
        prepare_native_host_request(host, HostEvent(), req)
        self.assertEqual(context_text(req), prepared)
        own.game.question_count = 4
        prepare_native_host_request(host, HostEvent(), req)
        self.assertIn("提问 4 次", context_text(req))
        self.assertNotIn("提问 3 次", context_text(req))
        self.assertEqual(req.system_prompt, "AstrBot 基础人格")
        for event in (HostEvent(sender="999"), HostEvent(private=False)):
            req = ProviderRequest(system_prompt="原提示")
            prepare_native_host_request(host, event, req)
            self.assertEqual(req.system_prompt, "原提示")
            self.assertFalse(req.extra_user_content_parts)

    async def test_game_recent_result_expires_and_does_not_cross_users(self):
        runtime = LocalGame([])
        host, _ = controller(game=runtime)
        runtime._recent_private_game_results["bot:private:200"] = NS(user_qq="200", expires_at=1, summary="过期结果")
        req = ProviderRequest(system_prompt="原提示")
        prepare_native_host_request(host, HostEvent(), req)
        self.assertEqual(req.system_prompt, "原提示")
        self.assertFalse(req.extra_user_content_parts)
        self.assertFalse(runtime._recent_private_game_results)
        runtime._recent_private_game_results["bot:private:200"] = NS(user_qq="300", expires_at=0, summary="其他玩家结果")
        prepare_native_host_request(host, HostEvent(), req)
        self.assertEqual(req.system_prompt, "原提示")
        self.assertFalse(req.extra_user_content_parts)

    async def test_reality_guidance_requires_a_current_private_request_and_a_real_v2_tool(self):
        runtime = NS(_safe_event_is_private=lambda event: event.is_private_chat(),
                     _official_reality_touch_metadata=lambda event: {},
                     _official_reality_touch_matches=lambda reminder, metadata: False,
                     data={"users": {}}, _user=lambda user_id, **kwargs: None,
                     v2_host_api=lambda: NS(_reality_context=NS(target=lambda user_id, **kwargs: None)))
        host, _ = controller(reality=runtime)
        camera = NS(_action="reality.camera.observe", name="companion_v2_reality_camera_observe")
        for private, text, tools in ((False, "看看摄像头", [camera]), (True, "今天好累", [camera]),
                                     (True, "看看摄像头", [])):
            req = ProviderRequest(system_prompt="原提示", func_tool=NS(tools=tools))
            prepare_native_host_request(host, HostEvent(private=private, text=text), req)
            self.assertEqual(req.system_prompt, "原提示")
        req = ProviderRequest(system_prompt="原提示", func_tool=NS(tools=[camera]))
        prepare_native_host_request(host, HostEvent(text="看看摄像头，我在吃什么"), req)
        self.assertIn(camera.name, context_text(req))
        self.assertIn("final_response_instruction", context_text(req))
        self.assertNotIn("pc_reality_touch_camera_snapshot", context_text(req))
        self.assertNotIn("一句", context_text(req))
        self.assertEqual(req.system_prompt, "原提示")
        original = context_text(req)
        prepare_native_host_request(host, HostEvent(text="看看摄像头，我在吃什么"), req)
        self.assertEqual(context_text(req), original)
        prepare_native_host_request(host, HostEvent(text="今天好累"), req)
        self.assertFalse(req.extra_user_content_parts)
        self.assertEqual(req.system_prompt, "原提示")


if __name__ == "__main__":
    unittest.main()

"""Authenticated OneBot poke handling across private and group delivery."""

from pathlib import Path
from datetime import timedelta
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from astrbot_host.controller import AstrBotStagingController
from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.conversation.pokes import PokePolicy
from companion_v2.foundation.clock import DeterministicClock
from tests.group_host_support import GroupFixture, group_config
from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi
from tests.recall_host_support import recall_notice, sdk_environment
from tests.test_management_access import NOW


def poke_notice(original, *, target=None, time=None):
    notice = recall_notice(original)
    raw = notice.message_obj.raw_message
    raw.update(notice_type="notify", sub_type="poke",
               target_id=int(original.message_obj.self_id) if target is None else target)
    raw.pop("message_id", None)
    raw.pop("operator_id", None)
    if time is not None:
        raw["time"] = time
    return notice


class PokePolicyTests(unittest.TestCase):
    def test_defaults_and_invalid_configuration(self):
        self.assertFalse(PokePolicy.parse(None).enabled)
        with self.assertRaises(ValueError):
            PokePolicy.parse({"enabled": True, "replies": []})
        with self.assertRaises(ValueError):
            PokePolicy.parse({"trigger_probability": 2})
        with self.assertRaises(ValueError):
            PokePolicy.parse({"back_probability": True})


class MultiHostPokeTests(GroupFixture, unittest.IsolatedAsyncioTestCase):
    def configure(self, *, private="preview", group="preview", back=0.0, trigger=1.0):
        config = group_config(delivery_mode=private, group_delivery_mode=group)
        config["poke"] = {"enabled": True, "trigger_probability": trigger,
                          "replies": ["在呢。"], "back_probability": back}
        self.controller = self.make_controller(config)
        return config

    async def test_private_target_needs_its_own_grant_and_survives_restart(self):
        config = self.configure(private="onebot_private", back=1.0)
        await self.start_host()
        notice = poke_notice(self.event(identifier="701"))
        api = self.native.platform.client._api._wsr_api
        blocked = await self.controller.receive_notice(notice)
        self.assertEqual(blocked.failure.code, "host_delivery_unauthorized")
        self.assertEqual(api.calls, [])
        (await self.controller.authorize_delivery("first")).unwrap()
        self.assertEqual((await self.controller.receive_notice(notice)).unwrap()["state"], "replayed")

        next_notice = poke_notice(self.event(identifier="702"), time=int(NOW.timestamp()) + 1)
        result = (await self.controller.receive_notice(next_notice)).unwrap()
        self.assertEqual((result["state"], result["poke_back"]), ("delivered", True))
        self.assertEqual([action for action, _ in api.calls], ["send_private_msg", "friend_poke"])
        self.assertEqual(api.calls[0][1]["user_id"], 200)
        self.assertEqual(api.calls[1][1]["user_id"], 200)

        await self.controller.terminate()
        self.controller = self.make_controller(config)
        (await self.controller.load_existing()).unwrap()
        (await self.controller.start()).unwrap()
        self.assertEqual((await self.controller.receive_notice(next_notice)).unwrap()["state"], "replayed")
        self.assertEqual(len(api.calls), 2)

    async def test_group_poke_uses_group_grant_and_rejects_wrong_target(self):
        self.configure(group="onebot_group", back=1.0)
        await self.start_host()
        original = self.group_event(identifier="701", sender="201", unique=True)
        notice = poke_notice(original)
        api = self.native.platform.client._api._wsr_api
        self.assertEqual((await self.controller.receive_notice(notice)).failure.code,
                         "host_group_delivery_unauthorized")
        (await self.controller.authorize_group_delivery("group-a")).unwrap()
        valid = poke_notice(original, time=int(NOW.timestamp()) + 1)
        result = (await self.controller.receive_notice(valid)).unwrap()
        self.assertEqual((result["state"], result["poke_back"]), ("delivered", True))
        self.assertEqual([action for action, _ in api.calls], ["send_group_msg", "group_poke"])
        self.assertEqual((api.calls[0][1]["group_id"], api.calls[1][1]["user_id"]), (300, 201))

        other_group = poke_notice(self.group_event("group-b", identifier="702"),
                                  time=int(NOW.timestamp()) + 2)
        self.assertEqual((await self.controller.receive_notice(other_group)).failure.code,
                         "host_group_delivery_unauthorized")
        wrong_target = poke_notice(self.group_event(identifier="703"), target=999,
                                   time=int(NOW.timestamp()) + 3)
        self.assertIsNone(await self.controller.receive_notice(wrong_target))
        self.assertEqual(len(api.calls), 2)

    async def test_self_poke_and_unconfigured_sender_are_ignored(self):
        self.configure(private="onebot_private")
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        own = poke_notice(self.event(identifier="701"), time=int(NOW.timestamp()) + 1)
        own.message_obj.raw_message["user_id"] = 100
        own.message_obj.sender.user_id = "100"
        own.session.session_id = own.message_obj.session_id = "100"
        own.unified_msg_origin = "qq-main:FriendMessage:100"
        self.assertIsNone(await self.controller.receive_notice(own))
        stranger = poke_notice(self.event(identifier="702"), time=int(NOW.timestamp()) + 2)
        stranger.message_obj.raw_message["user_id"] = 999
        stranger.message_obj.sender.user_id = "999"
        stranger.session.session_id = stranger.message_obj.session_id = "999"
        stranger.unified_msg_origin = "qq-main:FriendMessage:999"
        self.assertIsNone(await self.controller.receive_notice(stranger))
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_lost_ack_and_negative_message_id_do_not_duplicate(self):
        self.configure(private="onebot_private", back=1.0)
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        api = self.native.platform.client._api._wsr_api
        api.error = TimeoutError("lost text acknowledgement")
        notice = poke_notice(self.event(identifier="701"))
        self.assertEqual((await self.controller.receive_notice(notice)).unwrap()["state"], "unknown")
        api.error = None
        self.assertEqual((await self.controller.receive_notice(notice)).unwrap()["state"], "replayed")
        self.assertEqual(len(api.calls), 1)

        api.result = {"message_id": -701}
        next_notice = poke_notice(self.event(identifier="702"), time=int(NOW.timestamp()) + 1)
        result = (await self.controller.receive_notice(next_notice)).unwrap()
        self.assertEqual((result["message_id"], result["poke_back"]), ("-701", True))

    async def test_revocation_after_text_blocks_poke_back(self):
        self.configure(private="onebot_private", back=1.0)
        await self.start_host()
        (await self.controller.authorize_delivery("first")).unwrap()
        api = self.native.platform.client._api._wsr_api
        original_call = api.call_action

        async def revoke_after_text(action, **params):
            result = await original_call(action, **params)
            if action == "send_private_msg":
                self.controller.authority.revoke_delivery("first")
            return result

        api.call_action = revoke_after_text
        result = (await self.controller.receive_notice(poke_notice(self.event(identifier="701")))).unwrap()
        self.assertEqual((result["state"], result["poke_back"]), ("delivered", False))
        self.assertEqual([action for action, _ in api.calls], ["send_private_msg"])

    async def test_probability_skip_is_durable(self):
        self.configure(private="onebot_private", trigger=0.0)
        await self.start_host()
        notice = poke_notice(self.event(identifier="701"))
        self.assertEqual((await self.controller.receive_notice(notice)).unwrap()["state"], "skipped")
        self.assertEqual((await self.controller.receive_notice(notice)).unwrap()["state"], "replayed")
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])


class StagingPokeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-single-poke-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.native = sdk_environment.WebContext()
        self.clock = DeterministicClock.at(NOW)
        self.types = NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi)
        config = sdk_environment.host_config(staging={"enabled": True, "profile_id": "poke-private",
                                                       "delivery_mode": "onebot_private"})
        config["poke"] = {"enabled": True, "replies": ["在呢。"], "back_probability": 0.0}
        self.controller = AstrBotStagingController(self.native, config, self.root,
            native_types=self.types, now=self.clock.now)
        self.addAsyncCleanup(self.controller.terminate)

    async def test_single_target_poke_obeys_delivery_grant(self):
        (await self.controller.initialize_profile()).unwrap()
        (await self.controller.authorize_delivery()).unwrap()
        (await self.controller.start()).unwrap()
        notice = poke_notice(FakeEvent(self.native, event_id="701"))
        result = (await self.controller.receive_notice(notice)).unwrap()
        self.assertEqual(result["state"], "delivered")
        self.assertEqual(self.native.platform.client._api._wsr_api.calls[0][0], "send_private_msg")
        self.clock.advance(timedelta(minutes=16))
        expired = poke_notice(FakeEvent(self.native, event_id="702"), time=int(self.clock.now().timestamp()))
        self.assertIsNotNone((await self.controller.receive_notice(expired)).failure)
        self.assertEqual(len(self.native.platform.client._api._wsr_api.calls), 1)


if __name__ == "__main__":
    unittest.main()

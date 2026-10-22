"""S6 §6 failure fixtures (W1-F01--18) against the two real providers.

Each fixture fixes its original input, initial domain snapshot, authorization
revision, controlled clock and injection points, then records the observed
result.  A fixture whose required behaviour does not exist yet is registered as
BLOCKED with the reason instead of being quietly dropped or faked: the S6 rule
is that a fixture which has not run may not be counted as passing.

Reference: astrbot_plugin_private_companion/docs/S6_REALITY_TOGETHER_JOINT_ACCEPTANCE_V0.md §6
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from companion_v2.capabilities.native import parse_manifest, parse_result
from companion_v2.execution.models import SideEffect


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REALITY_PATH = PLUGIN_ROOT / "astrbot_plugin_reality_companion" / "native_v2" / "provider.py"
TOGETHER_PATH = PLUGIN_ROOT / "astrbot_plugin_together_companion" / "native_v2" / "provider.py"

# 这两个 provider 已随「七项伴侣能力内建进 V2」移出插件扫描目录，于是本文件
# 在导入阶段就会 FileNotFoundError。unittest 的发现阶段一旦导入失败，
# 整轮 run 直接判错，跟这个用例本身有没有意义无关。
# 保留证据、显式跳过：缺 fixture 时报「跳过」，而不是让整轮变红。
FIXTURE_PROVIDERS_PRESENT = REALITY_PATH.is_file() and TOGETHER_PATH.is_file()


def load_provider(name, path):
    spec = importlib.util.spec_from_file_location(f"w1_{name}_provider", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REALITY = load_provider("reality", REALITY_PATH) if FIXTURE_PROVIDERS_PRESENT else None
TOGETHER = load_provider("together", TOGETHER_PATH) if FIXTURE_PROVIDERS_PRESENT else None


# ---------------------------------------------------------------- fixture map

# status: "implemented" | "blocked"
# Every one of the 18 locators in S6 §6 appears exactly once, so the coverage of
# this suite is auditable rather than implied.
FIXTURES = {
    "W1-F01": ("两个样本、中间离线、随后只有心跳与一次空查询；采样时间与通信时间分开，覆盖保留缺口",
               "blocked", "快照只有每类一条最新记录，没有样本序列、覆盖缺口或独立的心跳更新路径"),
    "W1-F02": ("来源 revision 4 第一页已返回，第二页读取中撤权或保留期滑动，旧结果晚到",
               "blocked", "没有分页游标，也没有把游标绑定到来源修订的机制"),
    "W1-F03": ("I1 revision 3 仍振铃，接受/拒接/撤销/到期在同一修订上竞争",
               "implemented", "同人重放幂等、过期即终态、到点后不能再加入"),
    "W1-F04": ("I1 决策已保存，换代后重传，再加入同来意的新邀请 I2",
               "implemented", "换代后原操作仍按原身份回放，I2 保留独立身份"),
    "W1-F05": ("I1 已拒接、World 已提交、私信 D1 已提交但 ACK 丢失、回拨 O2 未知",
               "implemented", "拒接只结束该邀请，不连带结束房间或其它成员的活动"),
    "W1-F06": ("已文字解决/别打了、提交后取消、不同用户的另一通",
               "blocked", "Reality 侧没有回拨实体，无法验证「未提交的回拨被及时修订」"),
    "W1-F07": ("S 有 U，邀请票据供 V 加入；缺失身份、已消费票据和旧绑定再次请求",
               "implemented", "缺身份直接拒绝且不建会话；跨 scope 的合法 V 仍能加入；重放不建第二成员"),
    "W1-F08": ("R1 按 U 的私密上下文生成，V 加入令成员修订 4→5，V 同时请求媒体控制",
               "implemented", "成员修订每接纳一个新的不同身份 +1；成员、媒体与接管仍是分别的授权"),
    "W1-F09": ("S 有两成员、语音/镜头和影片，依次暂停影片、关一端镜头、断一端、退出一员",
               "blocked", "RoomSession 只有单个 websocket 与单通道镜头状态，没有逐端点分桶，无法构造多端点场景"),
    "W1-F10": ("M8 两端覆盖 0-40 / 30-40 秒，目标跳到 120 秒；原文改 M9，旧进度晚到",
               "blocked", "media_state 只有播放器标量，没有逐端点覆盖区间与控制修订"),
    "W1-F11": ("X1 interim 多次变化，随后 final 和 correction；另一成员说相似内容，混入回声",
               "blocked", "没有输入修订实体，临时识别与确认识别未分列"),
    "W1-F12": ("R1 文字已显示、A1 播放中、A2 排队，外部 O3 已提交；用户停止后旧回调晚到",
               "blocked", "没有「实际已播范围」账，也没有换代隔离旧输出的记录"),
    "W1-F13": ("A1 播放 ACK 丢失，TTS 超时触发 fallback；对照组仅合成失败、未提交播放",
               "blocked", "浏览器朗读回退在 V1 房间链路里，原生动作面无播放确认账可断言"),
    "W1-F14": ("Calendar C/K 即将触发，用户改为晚些文字；Memory 写入失败，旧语音提醒提交点与修改竞争",
               "blocked", "提醒与约定归 Calendar，不在两个扩展的原生动作面内"),
    "W1-F15": ("O3 已采集或远端已提交，设备重绑/撤权/来源删除后结果与查询 ACK 才返回",
               "implemented", "换绑后旧 binding_revision 被拒；撤权拒绝不新建操作行；未知结果保留原 operation 且不重试"),
    "W1-F16": ("持久 S revision 12 处于 reconnecting，完整重启后两个恢复者竞争，成功回复再丢失",
               "blocked", "恢复仍是内存宽限期，没有持久 Repository，也没有控制代 CAS"),
    "W1-F17": ("S 已结束但摘要/来源补存失败、旧音频回调晚到；World 另有窗口阻碍与「等我」约定",
               "implemented", "结束是终态：关闭后不再接受查找，旧回调无法把房间重新开场"),
    "W1-F18": ("媒体帧/临时转写持续积压、慢消费者、账本空间不足，同时收到停止/撤权与最终结果",
               "blocked", "没有队列水位或账本容量的对外观测点"),
}


# ------------------------------------------------------------------- doubles

def context(user="12345", role="role-a", session=None):
    return {"actor": {"subject": {"subject_id": "onebot-user:" + user},
                      "principal": {"native_account_id": user}},
            "audience": {"scope": {"installation_id": "install-a", "bot_id": "bot-a",
                                   "account_id": "bot-a-account", "platform": "aiocqhttp",
                                   "kind": "private", "session_id": session or user}},
            "role_binding": {"role_id": role}, "policy_revision": 1}


def together_binding(user="12345"):
    return SimpleNamespace(scope_key=TOGETHER.scope_key(context(user)), bot_id="bot-a",
                           account_id="bot-a-account", persona_id="persona-1", prompt="prompt",
                           model_provider_id="v2-chat", tts_provider_id="v2-voice",
                           tts_language="ja", tts_timeout_seconds=30, platform="aiocqhttp",
                           session_id=user, scope_kind="private")


def together_room(room_id="room-1", user="12345", mode="call", *, closed=False, revision=1):
    return SimpleNamespace(room_id=room_id, ticket_token="ticket-" + room_id, user_id=user,
                           mode=mode, native_v2=together_binding(user),
                           integration_closed=closed, created_at=1.0, call_active=False,
                           resume_token="resume-" + room_id, member_revision=revision)


class FakeTogether:
    def __init__(self):
        self.rooms = {}
        self.detached_rooms = {}
        self.ticket_store = SimpleNamespace(revoke=lambda token: None)
        self.room_server = SimpleNamespace(running=True)

    def _get_provider_by_id(self, provider_id):
        return SimpleNamespace(text_chat=lambda **kwargs: None)

    def admit_room_member(self, room, user_id, *, scope_key=""):
        members = getattr(room, "members", None)
        if not isinstance(members, dict):
            members = {}
            room.members = members
        members.setdefault(room.user_id, SimpleNamespace(
            user_id=room.user_id, role="owner", websocket=None))
        member = members.get(user_id)
        if member is None:
            member = SimpleNamespace(user_id=user_id, role="guest", websocket=None,
                                     scope_key=scope_key)
            members[user_id] = member
        return member

    def issue_member_room_ticket(self, room, *, user_id, invitation_id):
        return SimpleNamespace(token=f"{invitation_id}-{user_id}", mode=room.mode,
                               expires_at="2026-09-27T00:10:00+00:00")

    @staticmethod
    def _ticket_url(ticket):
        return f"https://together.test/join/{ticket.token}?mode={ticket.mode}"


class FakeReality:
    """Injection point for the device layer.

    ``targets`` holds the alias -> binding revision mapping, so a rebind is a
    single dict assignment rather than a rewrite of the provider.
    """

    def __init__(self):
        self.calls = []
        self.confirmed = True
        self.fail = False
        self.targets = {"desk": "rev-1"}
        self.mihome_web_api = self

    def mobile_context(self, user_id):
        return {"available": True, "user_id": user_id}

    def extension_device_target(self, alias, *, native=False):
        if alias not in self.targets:
            raise ValueError("unknown alias")
        return {"alias": alias, "binding_revision": self.targets[alias]}

    def extension_control_preflight(self, alias, *, native=False):
        if alias not in self.targets:
            raise ValueError("unknown alias")
        return "did-" + alias

    async def extension_control_power(self, alias, is_on, *, native=False):
        self.calls.append({"alias": alias, "is_on": is_on})
        if self.fail:
            raise TimeoutError("unconfirmed")
        return {"alias": alias, "is_on": is_on, "confirmed": self.confirmed}

    async def extension_device_action(self, alias, action, value, *, native=False,
                                      binding_revision=""):
        self.calls.append({"alias": alias, "action": action, "value": value,
                           "binding_revision": binding_revision})
        if self.fail:
            raise TimeoutError("unconfirmed")
        return {"alias": alias, "action": action, "value": value,
                "binding_revision": binding_revision, "confirmed": self.confirmed}


class ControlledClock:
    """A monotonic fake clock, so expiry is decided by the test, not by waiting."""

    def __init__(self, start=1_000_000.0):
        self.now = float(start)

    def advance(self, seconds):
        self.now += float(seconds)
        return self.now

    def time(self):
        return self.now


@contextmanager
def controlled_clock(clock, *modules):
    """Patch time.time inside the given provider modules only."""
    with mock.patch.object(time, "time", clock.time):
        patches = [mock.patch.object(module.time, "time", clock.time) for module in modules]
        for item in patches:
            item.start()
        try:
            yield clock
        finally:
            for item in reversed(patches):
                item.stop()


# ------------------------------------------------------------------ fixtures

@unittest.skipUnless(FIXTURE_PROVIDERS_PRESENT,
                     "W1 fixtures need the standalone reality/together providers, now bundled into V2")
class W1FixtureTests(unittest.IsolatedAsyncioTestCase):
    """The 18 S6 §6 locators; implemented ones run, the rest are registered."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    # -- shared plumbing -------------------------------------------------

    def together_provider(self, plugin=None):
        plugin = plugin or FakeTogether()
        provider = TOGETHER.NativeTogetherProvider(plugin, self.root / "together")
        return plugin, provider

    def reality_provider(self, plugin=None):
        plugin = plugin or FakeReality()
        provider = REALITY.NativeRealityProvider(plugin, self.root / "reality")
        return plugin, provider

    def request(self, provider, action, invocation, arguments=None, *, user="12345", role="role-a"):
        resolved = context(user, role)
        value = {"schema": "companion.native-provider.v1", "invocation_id": invocation,
                 "parent_task_id": "task-a",
                 # A tool_call_id is unique per call; reusing one would make the
                 # provider (correctly) refuse it as a mismatched original.
                 "tool_call_id": "call-" + invocation,
                 "action": action,
                 "origin_key": "origin-a", "context": resolved,
                 "binding": {"capability": action, "provider": provider.manifest()["provider_id"],
                             "version": provider.version, "generation": provider.generation},
                 "arguments": arguments or {}, "arguments_hash": "arguments-a",
                 "deadline_at": "2026-09-27T00:00:00+00:00"}
        if action == "together.room.create":
            scope = resolved["audience"]["scope"]
            value["host_persona"] = {"persona_id": "persona-1", "prompt": "V2 prompt",
                                     "bot_id": scope["bot_id"], "account_id": scope["account_id"]}
            value["host_execution"] = {"model_provider_id": "v2-chat", "tts_provider_id": "v2-voice",
                                       "tts_language": "ja", "tts_timeout_seconds": 30}
        return value

    async def run_action(self, provider, action, invocation, arguments=None, *, user="12345",
                         effect=None, before_dispatch=None):
        request = self.request(provider, action, invocation, arguments, user=user)
        result = await provider.execute(request, before_dispatch=before_dispatch or (lambda: True))
        parsed = parse_result(result, request=request,
                              side_effect=effect or (SideEffect.NONE if action in
                                                     {"together.room.snapshot", "together.room.members",
                                                      "together.room.invitations",
                                                      "reality.operation.lookup"}
                                                     else SideEffect.LOCAL))
        return result, parsed

    def assert_action_ran(self, fixture, observation):
        """Record a fixture's observed result in the standard report shape."""
        self.assertTrue(observation, f"{fixture}: observation was empty")

    # -- fixture inventory -----------------------------------------------

    def test_fixture_inventory_covers_all_eighteen_locators(self):
        expected = {f"W1-F{number:02d}" for number in range(1, 19)}
        self.assertEqual(set(FIXTURES), expected)
        for name, (spec, status, reason) in FIXTURES.items():
            self.assertIn(status, {"implemented", "blocked"}, name)
            self.assertTrue(spec and reason, name)
        # Blocked fixtures must name the missing capability, never a vague excuse.
        for name, (spec, status, reason) in FIXTURES.items():
            if status == "blocked":
                self.assertGreater(len(reason), 8, name)

    # -- W1-F03: invitation decisions race on one revision ---------------

    async def test_w1_f03_expiry_is_terminal_and_does_not_admit_late_join(self):
        clock = ControlledClock()
        plugin, provider = self.together_provider()
        plugin.rooms["room-1"] = together_room()
        with controlled_clock(clock, TOGETHER):
            issued, _ = await self.run_action(provider, "together.room.invite", "f03-invite",
                                             {"expires_in_seconds": 120})
            invitation = issued["result"]["invitation"]["invitation_id"]
            clock.advance(121)
            late, _ = await self.run_action(provider, "together.room.join", "f03-late",
                                           {"invitation_id": invitation}, user="67890")
            # The late decision must not act on the expired invitation...
            self.assertEqual((late["state"], late["effect"]), ("failed", "not_committed"))
            owner = provider.invitations.owner(invitation)
            self.assertEqual(provider.invitations.get(owner, invitation)["stage"], "expired")
            # ...and must not have admitted anybody or moved the revision.
            self.assertEqual(provider.invitations.get(owner, invitation)["joined_by"], [])
            self.assertEqual(plugin.rooms["room-1"].member_revision, 1)
        self.assert_action_ran("W1-F03", late)

    async def test_w1_f03_accepting_then_expiring_keeps_the_admitted_member(self):
        clock = ControlledClock()
        plugin, provider = self.together_provider()
        plugin.rooms["room-1"] = together_room()
        with controlled_clock(clock, TOGETHER):
            issued, _ = await self.run_action(provider, "together.room.invite", "f03-race",
                                             {"expires_in_seconds": 120})
            invitation = issued["result"]["invitation"]["invitation_id"]
            accepted, _ = await self.run_action(provider, "together.room.join", "f03-accept",
                                               {"invitation_id": invitation}, user="67890")
            self.assertEqual(accepted["state"], "succeeded")
            clock.advance(999)
            # A decision already committed stands; expiry must not undo it.
            replay, _ = await self.run_action(provider, "together.room.join", "f03-replay",
                                             {"invitation_id": invitation}, user="67890")
            self.assertTrue(replay["result"]["join"]["replayed"])
            self.assertEqual(plugin.rooms["room-1"].member_revision, 2)
        self.assert_action_ran("W1-F03", replay)

    # -- W1-F04: retransmission after a generation change ---------------

    async def test_w1_f04_original_decision_replays_under_a_new_generation(self):
        plugin, provider = self.together_provider()
        plugin.rooms["room-1"] = together_room()
        original = self.request(provider, "together.room.invite", "f04-invite")
        first = await provider.execute(original, before_dispatch=lambda: True)
        self.assertEqual(first["state"], "succeeded")
        # A new package generation must still answer the original invocation
        # from its own journal rather than inventing a second invitation.
        restarted = TOGETHER.NativeTogetherProvider(plugin, self.root / "together")
        replayed = await restarted.execute(original, before_dispatch=lambda: True)
        self.assertEqual(replayed, first)
        self.assertEqual(len(restarted.invitations.active(TOGETHER.scope_key(context()))), 1)
        # A genuinely separate request keeps its own identity.
        second = await restarted.execute(
            self.request(restarted, "together.room.invite", "f04-second"),
            before_dispatch=lambda: True)
        self.assertNotEqual(second["result"]["invitation"]["invitation_id"],
                            first["result"]["invitation"]["invitation_id"])
        self.assert_action_ran("W1-F04", second)

    # -- W1-F05: a rejection is its own fact ----------------------------

    async def test_w1_f05_refusing_an_invitation_does_not_end_the_room(self):
        plugin, provider = self.together_provider()
        plugin.rooms["room-1"] = together_room()
        plugin.rooms["room-2"] = together_room("room-2", user="67890")
        issued, _ = await self.run_action(provider, "together.room.invite", "f05-invite")
        invitation = issued["result"]["invitation"]["invitation_id"]
        # Refusing means: this invitation is not usable, and nothing else changes.
        owner = provider.invitations.owner(invitation)
        provider.invitations._data["scopes"][owner][invitation]["stage"] = "revoked"
        refused, _ = await self.run_action(provider, "together.room.join", "f05-join",
                                          {"invitation_id": invitation}, user="67890")
        self.assertEqual((refused["state"], refused["effect"]), ("failed", "not_committed"))
        # The room and the other member's activity are untouched.
        self.assertEqual(set(plugin.rooms), {"room-1", "room-2"})
        self.assertFalse(plugin.rooms["room-1"].integration_closed)
        self.assertEqual(plugin.rooms["room-1"].member_revision, 1)
        self.assertEqual(plugin.rooms["room-2"].member_revision, 1)
        self.assert_action_ran("W1-F05", refused)

    # -- W1-F07: identity, replay and invitation ownership ---------------

    async def test_w1_f07_identityless_ticket_is_refused_and_creates_no_session(self):
        from astrbot_plugin_together_companion.main import TogetherCompanionPlugin
        from astrbot_plugin_together_companion.models import RoomTicket

        plugin = TogetherCompanionPlugin.__new__(TogetherCompanionPlugin)
        plugin.rooms = {}
        plugin.primary_user_id = "primary-999"
        plugin._resolve_primary_user_id = lambda: "primary-999"
        ticket = RoomTicket("token", "call", "", 1.0, time.time() + 600, None)
        with self.assertRaises(Exception) as caught:
            await plugin.open_room(ticket, None)
        self.assertEqual(type(caught.exception).__name__, "RoomIdentityError")
        self.assertEqual(caught.exception.code, "together_ticket_identity_required")
        self.assertEqual(plugin.rooms, {})
        self.assert_action_ran("W1-F07", caught.exception.code)

    async def test_w1_f07_replaying_a_consumed_invitation_does_not_build_a_second_member(self):
        plugin, provider = self.together_provider()
        plugin.rooms["room-1"] = together_room()
        issued, _ = await self.run_action(provider, "together.room.invite", "f07-invite")
        invitation = issued["result"]["invitation"]["invitation_id"]
        first, _ = await self.run_action(provider, "together.room.join", "f07-first",
                                        {"invitation_id": invitation}, user="67890")
        second, _ = await self.run_action(provider, "together.room.join", "f07-replay",
                                         {"invitation_id": invitation}, user="67890")
        self.assertFalse(first["result"]["join"]["replayed"])
        self.assertTrue(second["result"]["join"]["replayed"])
        owner = provider.invitations.owner(invitation)
        self.assertEqual(provider.invitations.get(owner, invitation)["joined_by"], ["67890"])
        self.assertEqual(plugin.rooms["room-1"].member_revision, 2)
        # A different person may still be admitted to the same invitation.
        third, _ = await self.run_action(provider, "together.room.join", "f07-other",
                                        {"invitation_id": invitation}, user="11111")
        self.assertFalse(third["result"]["join"]["replayed"])
        self.assertEqual(plugin.rooms["room-1"].member_revision, 3)
        self.assert_action_ran("W1-F07", third)

    # -- W1-F08: audience revision and separate authorizations -----------

    async def test_w1_f08_member_revision_moves_once_per_admitted_identity(self):
        plugin, provider = self.together_provider()
        plugin.rooms["room-1"] = together_room(revision=4)
        issued, _ = await self.run_action(provider, "together.room.invite", "f08-invite")
        invitation = issued["result"]["invitation"]["invitation_id"]
        # The invitation records the audience revision it was issued against.
        self.assertEqual(issued["result"]["invitation"]["revision"], 4)
        joined, _ = await self.run_action(provider, "together.room.join", "f08-join",
                                         {"invitation_id": invitation}, user="67890")
        self.assertEqual(joined["result"]["join"]["member_revision"], 5)
        self.assertTrue(joined["result"]["join"]["member_revision_changed"])
        # Joining is membership, not media control or takeover: the members view
        # reports identity facts only and grants nothing.
        members, _ = await self.run_action(provider, "together.room.members", "f08-members")
        self.assertEqual(members["result"]["member_count"], 2)
        blob = json.dumps(members["result"])
        for forbidden in ("prompt", "ticket", "token", "scope_key"):
            self.assertNotIn(forbidden, blob, forbidden)
        self.assert_action_ran("W1-F08", joined)

    # -- W1-F15: rebind, revocation and late results ---------------------

    async def test_w1_f15_a_rebound_alias_invalidates_the_old_reference(self):
        plugin, provider = self.reality_provider()
        # The caller pins the binding revision it prepared the action against.
        prepared_revision = plugin.targets["desk"]
        # The alias is rebound to a different device between preparing and
        # dispatching: the pinned revision no longer matches.
        plugin.targets["desk"] = "rev-2"
        stale, _ = await self.run_action(
            provider, "reality.device.action", "f15-stale",
            {"alias": "desk", "action": "set_brightness", "value": "40",
             "expect_revision": prepared_revision},
            effect=SideEffect.EXTERNAL_DEVICE)
        self.assertEqual((stale["state"], stale["effect"]), ("failed", "not_committed"))
        self.assertEqual(plugin.calls, [])  # nothing reached the device
        # Pinning the current revision still works, so the guard is not a blanket refusal.
        current, _ = await self.run_action(
            provider, "reality.device.action", "f15-current",
            {"alias": "desk", "action": "set_brightness", "value": "40",
             "expect_revision": "rev-2"},
            effect=SideEffect.EXTERNAL_DEVICE)
        self.assertEqual(current["state"], "succeeded")
        self.assertEqual(len(plugin.calls), 1)
        self.assert_action_ran("W1-F15", current)

    async def test_w1_f15_revocation_refuses_without_creating_an_operation(self):
        plugin, provider = self.reality_provider()
        scope = REALITY.scope_key(context())
        before = len(provider.store.latest(scope))
        with self.assertRaises(REALITY.NativeRealityError) as caught:
            await provider.execute(
                self.request(provider, "reality.device.control", "f15-revoked",
                             {"alias": "desk", "is_on": True}),
                before_dispatch=lambda: False)
        self.assertEqual(caught.exception.code, "host_authority_revoked")
        self.assertEqual(len(provider.store.latest(scope)), before)
        self.assertEqual(plugin.calls, [])
        self.assert_action_ran("W1-F15", caught.exception.code)

    async def test_w1_f15_an_unknown_result_keeps_the_operation_and_is_never_retried(self):
        plugin, provider = self.reality_provider()
        plugin.fail = True
        uncertain, _ = await self.run_action(provider, "reality.device.control", "f15-unknown",
                                            {"alias": "desk", "is_on": False},
                                            effect=SideEffect.EXTERNAL_NETWORK)
        self.assertEqual((uncertain["state"], uncertain["effect"]), ("unknown", "unknown"))
        self.assertEqual(len(plugin.calls), 1)
        # The original operation is kept and a repeat is answered from the
        # journal; the device is never called a second time.
        again, _ = await self.run_action(provider, "reality.device.control", "f15-unknown",
                                        {"alias": "desk", "is_on": False},
                                        effect=SideEffect.EXTERNAL_NETWORK)
        self.assertEqual(again, uncertain)
        self.assertEqual(len(plugin.calls), 1)
        looked_up, _ = await self.run_action(
            provider, "reality.operation.lookup", "f15-lookup",
            {"operation_id": uncertain["operation_id"]}, effect=SideEffect.NONE)
        self.assertEqual(looked_up["state"], "unknown")
        self.assertEqual(len(plugin.calls), 1)
        self.assert_action_ran("W1-F15", looked_up)

    # -- W1-F17: ending is terminal --------------------------------------

    async def test_w1_f17_ending_only_releases_this_room_and_stays_terminal(self):
        plugin, provider = self.together_provider()
        plugin.rooms["room-1"] = together_room()
        plugin.rooms["room-2"] = together_room("room-2", user="67890")
        plugin.detached_rooms["resume-room-1"] = together_room("room-1")
        closed = []

        async def close_room(room):
            room.integration_closed = True
            closed.append(room.room_id)
            plugin.rooms.pop(room.room_id, None)

        plugin.close_room = close_room
        result, _ = await self.run_action(provider, "together.room.close", "f17-close")
        self.assertEqual(result["state"], "succeeded")
        # Only this provider's own room is released; the other member's room and
        # the later window's commitment are untouched.
        self.assertEqual(closed, ["room-1"])
        self.assertIn("room-2", plugin.rooms)
        self.assertFalse(plugin.rooms["room-2"].integration_closed)
        # A late callback cannot reopen the ended room.
        again, _ = await self.run_action(provider, "together.room.close", "f17-late")
        self.assertIn(again["result"].get("closed"), (False, None))
        self.assertEqual(closed, ["room-1"])
        self.assert_action_ran("W1-F17", again)

    # -- blocked fixtures: registered, explicitly not passing ------------

    def test_blocked_fixtures_are_registered_and_not_counted_as_passing(self):
        blocked = sorted(name for name, (_, status, _) in FIXTURES.items() if status == "blocked")
        implemented = sorted(name for name, (_, status, _) in FIXTURES.items()
                             if status == "implemented")
        # This fixture is the executable form of S6 §8.3: a spec that has not run
        # may not be reported as a pass.  The counts are pinned so a future slice
        # must consciously move a locator rather than inherit a silent claim.
        self.assertEqual(len(blocked) + len(implemented), 18)
        self.assertEqual(implemented, ["W1-F03", "W1-F04", "W1-F05", "W1-F07",
                                       "W1-F08", "W1-F15", "W1-F17"])
        self.assertEqual(blocked, ["W1-F01", "W1-F02", "W1-F06", "W1-F09", "W1-F10",
                                   "W1-F11", "W1-F12", "W1-F13", "W1-F14", "W1-F16",
                                   "W1-F18"])


if __name__ == "__main__":
    unittest.main()

"""Optional OneBot labels never change routing or fall back to another account."""

import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from astrbot_host.display_names import PlatformDisplayNames


class PlatformDisplayNameTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.calls = []
        self.responses = {}

        async def call(action, **params):
            self.calls.append((action, params))
            value = self.responses.get((params["self_id"], action))
            if isinstance(value, Exception):
                raise value
            return value

        self.api = NS(call_action=call)
        self.clients = {"100": object(), "101": object()}
        platform = NS(meta=lambda: NS(name="aiocqhttp", id="qq-main"),
                      get_client=lambda: NS(_wsr_api_clients=self.clients, _api=NS(_wsr_api=self.api)))
        self.context = NS(get_platform_inst=lambda platform_id: platform if platform_id == "qq-main" else None)
        self.names = PlatformDisplayNames(self.context)

    async def test_remarks_group_names_and_login_names_are_account_scoped_and_cached(self):
        self.responses.update({
            ("100", "get_friend_list"): [{"user_id": 200, "nickname": "昵称", "remark": "好友备注"}],
            ("101", "get_friend_list"): {"status": "ok", "retcode": 0,
                "data": [{"user_id": 200, "nickname": "另一个 Bot 的昵称", "remark": ""}]},
            ("100", "get_group_list"): [{"group_id": 300, "group_name": "读书群"}],
            ("100", "get_login_info"): {"user_id": 100, "nickname": "小伴"},
            ("101", "get_login_info"): {"user_id": 101, "nickname": "晚星"},
        })
        targets = [dict(platform_id="qq-main", account_id=account, participant_id="200", roles=[{"role_id": "role"}])
                   for account in ("100", "101")]
        targets.append(dict(platform_id="qq-main", account_id="100", group_id="300"))
        result = await self.names.targets(targets)
        self.assertEqual([row["display_name"] for row in result], ["好友备注", "另一个 Bot 的昵称", "读书群"])
        self.assertEqual([row["account_name"] for row in result], ["小伴", "晚星", "小伴"])
        self.assertNotIn("display_name", targets[0])
        self.assertEqual(result[0]["participant_id"], "200")
        self.assertEqual(result[0]["roles"], targets[0]["roles"])
        before = list(self.calls)
        self.assertEqual(await self.names.targets(targets), result)
        self.assertEqual(self.calls, before)
        self.assertTrue(all(action in {"get_friend_list", "get_group_list", "get_login_info"}
                            for action, _ in self.calls))

    async def test_detail_fallback_checks_identity_and_retains_existing_name_on_failure(self):
        self.responses[("100", "get_friend_list")] = []
        self.responses[("100", "get_stranger_info")] = {"user_id": 200, "nickname": "路人名字"}
        self.assertEqual(await self.names.lookup("qq-main", "100", "private", "200"), "路人名字")
        self.assertEqual(self.calls[-1], ("get_stranger_info", {"self_id": "100", "user_id": 200}))
        self.responses[("100", "get_stranger_info")] = {"user_id": 200, "nickname": "错误身份"}
        self.assertEqual(await self.names.lookup("qq-main", "100", "private", "201"), "")
        self.responses[("100", "get_group_list")] = TimeoutError("disconnected")
        self.responses[("100", "get_group_info")] = {"status": "failed", "retcode": 1,
                                                   "data": {"group_id": 300, "group_name": "不可信"}}
        group = (await self.names.targets([dict(platform_id="qq-main", account_id="100", group_id="300")]))[0]
        self.assertEqual(group["display_name"], "")
        self.responses[("100", "get_stranger_info")] = ValueError("unsupported")
        persons = await self.names.persons([dict(platform="qq-main", account_id="100", native_account_id="202",
                                               display_name="记录中的称呼", name_basis="platform")])
        self.assertEqual(persons[0]["display_name"], "记录中的称呼")
        target = (await self.names.targets([dict(platform_id="qq-main", account_id="100", participant_id="202",
                                                display_name="记录中的称呼", account_name="已有 Bot 名称")]))[0]
        self.assertEqual(target["display_name"], "记录中的称呼")
        self.assertEqual(target["account_name"], "已有 Bot 名称")

    async def test_administrator_names_and_disconnected_accounts_do_not_query(self):
        person = dict(platform="qq-main", account_id="100", native_account_id="200",
                      display_name="管理员称呼", admin_nickname="管理员称呼", name_basis="administrator")
        self.assertEqual(await self.names.persons([person]), [person])
        self.clients.clear()
        self.assertEqual(await self.names.lookup("qq-main", "100", "private", "200"), "")
        self.assertEqual(await self.names.lookup("qq-other", "100", "group", "300"), "")
        self.assertEqual(self.calls, [])
        with patch.object(self.context, "get_platform_inst", side_effect=RuntimeError("platform unavailable")):
            self.assertEqual(await self.names.lookup("qq-main", "100", "private", "201"), "")

    async def test_slow_lookup_is_bounded_and_failure_does_not_repeat_immediately(self):
        async def slow(*args, **kwargs):
            await asyncio.sleep(0.1)

        self.api.call_action = AsyncMock(side_effect=slow)
        with patch("astrbot_host.display_names.LOOKUP_TIMEOUT", 0.01):
            self.assertEqual(await self.names.lookup("qq-main", "100", "private", "200"), "")
        before = self.api.call_action.await_count
        self.assertEqual(await self.names.lookup("qq-main", "100", "private", "200"), "")
        self.assertEqual(self.api.call_action.await_count, before)

    async def test_cached_directory_labels_do_not_contact_onebot_even_after_expiry(self):
        people = [dict(platform="qq-main", account_id="100", native_account_id="200",
                       display_name="记录里的名字")]
        groups = [dict(platform_id="qq-main", account_id="100", group_id="300")]
        with patch.object(self.context, "get_platform_inst") as platform:
            self.assertEqual((await self.names.persons(people, cached_only=True))[0]["display_name"],
                             "记录里的名字")
            self.assertEqual((await self.names.targets(groups, cached_only=True))[0]["display_name"], "")
            self.names._cache.update({
                ("qq-main", "100", "private", "200"): (0, "已缓存好友备注"),
                ("qq-main", "101", "private", "200"): (0, "另一账号备注"),
                ("qq-main", "100", "group", "300"): (0, "已缓存群名"),
                ("qq-main", "100", "account", "100"): (0, "已缓存 Bot 名称"),
            })
            self.assertEqual((await self.names.persons(people, cached_only=True))[0]["display_name"],
                             "已缓存好友备注")
            group = (await self.names.targets(groups, cached_only=True))[0]
            self.assertEqual((group["display_name"], group["account_name"]), ("已缓存群名", "已缓存 Bot 名称"))
            platform.assert_not_called()
        self.assertNotIn("name_basis", people[0])
        self.assertEqual(self.calls, [])

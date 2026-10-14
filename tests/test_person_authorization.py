"""相识详情页的按人授权：读侧说真话，写侧只改本页拥有的那一份。

这一组测的是本次改动最容易出错的地方，每一条都对应一种"页面在撒谎"的形态：

1. **读侧给的是 grant 的真实状态**，不是一个布尔标志。撤销过、过期、尚未生效
   各自如实呈现，因为这些状态对操作员的意义完全不同（撤销过还能再打开）。
2. **本页拥有的能力可以关掉再打开**，靠的是本页自己的 ``acquaintance-grant:``
   世代，走操作账本。
3. **配置派生的授权被明确拒绝**，理由说得出来（改哪里），而且**原样不动**。
   这一条最重要：``staging_bootstrap`` 每次加载都会按配置重新签发这类授权，
   如果页面能撤销，下次加载就复原——页面显示「已撤销」而能力还活着，比没有
   按钮更坏；屏幕授权还会让准备流程直接失败。
4. **过期的 revision 不许覆盖**别人刚做完的改动。
5. **同一个操作键重放不会多签一份授权**。
6. 宿主路由的鉴权与请求形状：读不到身份、没加载运行实例、不是核心用户都不放行。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from astrbot_host.acquaintance_api import ADMIN_NAME_PATH, AUTHORIZATION_PATH, _authorization_participants
from astrbot_host.management_identity import dashboard_operator
from companion_v2.execution.models import TaskContext
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import AudienceRef
from companion_v2.identity_policy.grants import (
    DELIVERY_GRANT_ID,
    STAGING_CAPABILITY_GRANT_PREFIX,
    STAGING_SCREEN_GRANT_PREFIX,
)
from companion_v2.identity_policy.management import (
    GRANT_PREFIX,
    MANAGED_BY_CONFIGURATION,
    MANAGED_BY_PAGE,
    PersonAuthorizationManagement,
)
from companion_v2.identity_policy.models import AuthorizationTier, GrantState
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.identity_policy.interventions import (
    CALENDAR_INTERVENTION,
    INTERVENTION_CAPABILITIES,
    REST_WAKE_INTERVENTION,
    STATE_INTERVENTION,
    authorized_capabilities,
)
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.screen import SCREEN_READ
from companion_v2.execution.models import encode, stamp
from companion_v2.memory.person.access import card_id, person_owner_key
from companion_v2.memory.person.models import KIND as PERSON_CARD_KIND, empty_document as empty_person_card
from tests import test_astrbot_staging_host as support
from tests.test_management_access import ManagementFixture, NOW, SCOPE


AT = NOW + timedelta(seconds=5)


def participant(subject, scope):
    """运行实例给一个人留下的两样东西：**主体**（受信绑定里的身份）与**窗口**
    （宿主注册的那个已解析生效范围，带会话与窗口号）。

    页面入口只能从运行实例里读这两样，不能自己拼：拼出来的那份不是回复路径
    真正会查的生效范围。夹具照这个形状给。
    """
    return {"target": None, "subject_id": subject.subject_id, "subject": subject, "scope": scope}


class AuthorizationFixture(ManagementFixture):
    def setUp(self):
        super().setUp()
        self.policy.set_tier(self.important.subject, AuthorizationTier.STANDARD,
                             expected_revision=self.policy.revision, observed_at=NOW)
        # 夹具里已经绑定好的那个人就是「这个人」：subject 与 principal 都齐，
        # 只有窗口要照宿主的形状补全（夹具的 SCOPE 已经是完整窗口）。
        self.subject_id = self.important.subject.subject_id
        self.scope = replace(SCOPE, native_scope_id=self.subject_id)
        self.manager = PersonAuthorizationManagement(self.runtime,
            participants=(participant(self.important.subject, self.scope),))

    def capability(self, grant_id, capability, *, expires_at=None, scope=None):
        """一份真实的 grant 记录；id 决定它属于哪个世代。"""
        return self.identity.issue_grant(grant_id=grant_id, subject=self.important.subject,
            scope=scope or self.scope, capability=capability, tier=AuthorizationTier.STANDARD,
            valid_from=NOW, expires_at=expires_at, expected_revision=self.identity.revision)

    def status(self, *, at=AT, subject=None):
        return self.manager.status(self.core, subject or self.subject_id, observed_at=at).unwrap()

    def row(self, status, capability):
        return next(item for item in status["items"] if item["capability"] == capability)

    def state(self, capability):
        return self.row(self.status(), capability)["state"]

    def command(self, capability, enabled, *, key="operation-key", revision=None, subject=None):
        return self.manager.configure(self.core, {
            "operation_key": key, "subject_id": subject or self.subject_id, "capability": capability,
            "enabled": enabled,
            "expected_revision": self.identity.revision if revision is None else revision,
        }, observed_at=AT)


class AuthorizationReadTests(AuthorizationFixture):
    def test_a_person_without_grants_gets_an_honest_empty_state(self):
        status = self.status()
        # 一项授权都没有的人：如实说没有，而不是给每项能力画一行空白状态。
        self.assertEqual({item["capability"] for item in status["items"]},
                         {"conversation.reply", "proactive.contact", *INTERVENTION_CAPABILITIES})
        self.assertTrue(all(item["state"] == "off" for item in status["items"]))
        self.assertFalse(status["companion"])

    def test_only_core_has_default_intervention_access_and_delegation_is_exact(self):
        self.personas.register_route(ConversationRoute(self.scope, user=self.important.subject), observed_at=NOW)
        role = self.identity.resolve_role(self.scope, observed_at=NOW).unwrap()
        tasks = NS(runtime=self.runtime, identity=self.identity,
            check_context_access=lambda *_args, **_kwargs: Outcome.success(True))

        def context(actor):
            return TaskContext(actor, role, AudienceRef(self.scope, (actor.subject,)))

        standard = context(self.important)
        core = context(self.core)
        self.assertEqual(authorized_capabilities(tasks, standard, at=AT), frozenset())
        self.assertEqual(authorized_capabilities(tasks, core, at=AT), frozenset(INTERVENTION_CAPABILITIES))

        self.capability(GRANT_PREFIX + "state-intervention", STATE_INTERVENTION)
        other_scope = replace(self.scope, native_scope_id="another-private-window",
                              conversation_id="another-conversation", session_id="another-session")
        self.identity.issue_grant(grant_id=GRANT_PREFIX + "calendar-other-window",
            subject=self.important.subject, scope=other_scope, capability=CALENDAR_INTERVENTION,
            tier=AuthorizationTier.STANDARD, valid_from=NOW, expected_revision=self.identity.revision)
        self.assertEqual(authorized_capabilities(tasks, standard, at=AT), frozenset({STATE_INTERVENTION}))
        self.identity.revoke_grant(GRANT_PREFIX + "state-intervention", revoked_at=AT,
                                   expected_revision=self.identity.revision)
        self.assertEqual(authorized_capabilities(tasks, standard, at=AT), frozenset())

        self.policy.set_tier(self.important.subject, AuthorizationTier.CORE,
                             expected_revision=self.policy.revision, observed_at=NOW)
        core_rows = {item["capability"]: item for item in self.status()["items"]}
        self.assertEqual(core_rows[REST_WAKE_INTERVENTION]["effective_state"], "active")

    def test_status_exposes_administrator_permission_as_the_core_identity_projection(self):
        standard = self.status()
        self.assertEqual(standard["administrator"], {"enabled": False, "state": "off", "label": "未开启"})
        self.policy.set_tier(self.important.subject, AuthorizationTier.CORE,
                             expected_revision=self.policy.revision, observed_at=NOW)
        core = self.status()
        self.assertEqual(core["identity_tier"], "core")
        self.assertEqual(core["administrator"], {"enabled": True, "state": "active", "label": "核心管理员"})

    def test_every_row_carries_the_real_record_not_a_boolean(self):
        self.capability(STAGING_CAPABILITY_GRANT_PREFIX + "conversation.reply", "conversation.reply")
        self.capability(GRANT_PREFIX + "one", "proactive.contact", expires_at=AT + timedelta(seconds=1))
        self.capability(GRANT_PREFIX + "two", "screen.process")
        self.capability(GRANT_PREFIX + "three", "memory.read", expires_at=NOW + timedelta(seconds=1))
        self.identity.revoke_grant(GRANT_PREFIX + "two", revoked_at=AT, expected_revision=self.identity.revision)

        status = self.status()
        self.assertEqual({item["capability"] for item in status["items"]},
                         {"conversation.reply", "proactive.contact", "screen.process", "memory.read",
                          *INTERVENTION_CAPABILITIES})
        # 对话回复来自运行实例配置：真实状态是「已生效」，但本页不能改它。
        reply = self.row(status, "conversation.reply")
        self.assertEqual((reply["state"], reply["managed_by"], reply["revocable"]),
                         ("active", MANAGED_BY_PAGE, True))
        self.assertEqual(reply["grant_id"], STAGING_CAPABILITY_GRANT_PREFIX + "conversation.reply")
        # 本页签发的那一份：状态、生效范围、档位、到期与写所需 revision 都在。
        contact = self.row(status, "proactive.contact")
        self.assertEqual((contact["state"], contact["managed_by"], contact["revocable"]),
                         ("active", MANAGED_BY_PAGE, True))
        self.assertEqual(contact["tier"], "standard")
        self.assertEqual(contact["expires_at"], AT + timedelta(seconds=1))
        self.assertEqual(contact["scope"]["native_scope_id"], self.subject_id)
        self.assertEqual(contact["policy_revision"], self.identity.revision)
        # 撤销过与过期是两种不同的记录事实，不能合并成「关」。
        self.assertEqual(self.row(status, "screen.process")["state"], "revoked")
        self.assertEqual(self.row(status, "memory.read")["state"], "expired")

    def test_expiry_is_judged_at_the_observed_time(self):
        self.capability(DELIVERY_GRANT_ID, "message.delivery", expires_at=NOW + timedelta(seconds=10))
        self.assertEqual(self.state("message.delivery"), "active")
        later = self.status(at=NOW + timedelta(seconds=10))
        self.assertEqual(self.row(later, "message.delivery")["state"], "expired")
        self.assertFalse(later["companion"])

    def test_companion_uses_dialogue_permission_and_host_owns_delivery(self):
        self.capability(STAGING_CAPABILITY_GRANT_PREFIX + "conversation.reply", "conversation.reply")
        self.assertTrue(self.status()["companion"])
        self.capability(DELIVERY_GRANT_ID, "message.delivery", expires_at=AT + timedelta(seconds=60))
        self.assertTrue(self.status()["companion"])
        # 一条已经撤销的投递授权不算数：标记说的是"现在正在被陪伴"。
        self.identity.revoke_grant(DELIVERY_GRANT_ID, revoked_at=AT, expected_revision=self.identity.revision)
        self.assertTrue(self.status()["companion"])

    def test_rows_are_empty_when_nothing_is_bound_to_this_persons_window(self):
        # 另一个窗口上的授权不属于这个人现在的窗口：它不该出现在这一行里，
        # 否则页面会给一个写路径根本够不到的开关。
        self.capability(GRANT_PREFIX + "elsewhere", "proactive.contact",
                        scope=replace(self.scope, native_scope_id="someone-else"))
        self.assertTrue(all(item["state"] == "off" for item in self.status()["items"]))

    def test_an_unknown_person_is_refused_instead_of_addressed(self):
        self.assertEqual(self.manager.status(self.core, "not-in-the-directory", observed_at=AT).failure.code,
                         "acquaintance_subject_unknown")
        self.assertEqual(self.manager.status(self.core, "", observed_at=AT).failure.code,
                         "acquaintance_subject_required")

    def test_a_person_without_a_registered_window_is_refused_not_guessed(self):
        # 主体与窗口都只能来自运行实例：少一个就明说，不许自己拼一个出来——
        # 拼出来的那份不是回复路径真正会查的生效范围。
        no_window = PersonAuthorizationManagement(self.runtime, participants=(
            {"target": None, "subject_id": self.standard.subject.subject_id,
             "subject": self.standard.subject, "scope": None},))
        self.assertEqual(no_window.status(self.core, self.standard.subject.subject_id,
                                          observed_at=AT).failure.code,
                         "acquaintance_window_unknown")
        # 完全没有这个人的条目，等同于"不在目录里"。
        empty = PersonAuthorizationManagement(self.runtime, participants=())
        self.assertEqual(empty.status(self.core, self.subject_id, observed_at=AT).failure.code,
                         "acquaintance_subject_unknown")

    def test_reading_requires_the_same_gate_as_the_directory(self):
        policy = ObjectAccessPolicy(self.runtime)
        policy.set_tier(self.core.subject, AuthorizationTier.IMPORTANT,
                        expected_revision=policy.revision, observed_at=NOW)
        self.assertEqual(self.manager.status(self.core, self.subject_id, observed_at=AT).failure.code,
                         "core_access_required")
        self.assertEqual(self.command("proactive.contact", True, key="blocked").failure.code,
                         "core_access_required")
        self.assertEqual(self.runtime.read_all("SELECT * FROM identity_grants", ()), ())


class AuthorizationWriteTests(AuthorizationFixture):
    def test_a_page_managed_capability_can_be_turned_off_and_on_again(self):
        self.capability(GRANT_PREFIX + "seed", "proactive.contact")

        off = self.command("proactive.contact", False, key="off-1").unwrap()
        self.assertFalse(off["replayed"])
        self.assertEqual(self.state("proactive.contact"), "revoked")
        self.assertFalse(self.identity.authorize(self.important, scope=self.scope,
                                                 capability="proactive.contact", observed_at=AT).is_success)
        # 关掉之后这一行还在：那不是"从未授权"，而是"被撤销了"，还能再打开。
        row = self.row(self.status(), "proactive.contact")
        self.assertEqual((row["state"], row["revocable"]), ("revoked", True))

        on = self.command("proactive.contact", True, key="on-1").unwrap()
        self.assertFalse(on["replayed"])
        self.assertEqual(self.state("proactive.contact"), "active")
        self.assertTrue(self.identity.authorize(self.important, scope=self.scope,
                                                capability="proactive.contact", observed_at=AT).is_success)
        # 重开签发的是一份新的本页世代授权，旧的那一份仍留着当证据。
        grants = [grant for grant in self.identity.snapshot().grants
                  if grant.capability == "proactive.contact" and grant.grant_id.startswith(GRANT_PREFIX)]
        self.assertEqual({grant.state for grant in grants}, {GrantState.REVOKED, GrantState.ACTIVE})
        # 读侧说的是**现在**的状态：撤销过的那一份是历史，不是结论。
        self.assertEqual(self.row(self.status(), "proactive.contact")["state"], "active")

    def test_a_capability_the_page_never_granted_cannot_be_turned_off(self):
        result = self.command("memory.read", False, key="off-never")
        self.assertEqual(result.failure.code, "authorization_capability_not_managed")
        self.assertEqual(self.runtime.read_all("SELECT * FROM identity_grants", ()), ())

    def test_a_configuration_derived_capability_is_refused_and_left_untouched(self):
        derived = ((STAGING_CAPABILITY_GRANT_PREFIX + "text", "text"),
                   (DELIVERY_GRANT_ID, "message.delivery"),
                   (STAGING_SCREEN_GRANT_PREFIX + SCREEN_READ, SCREEN_READ))
        for grant_id, capability in derived:
            self.capability(grant_id, capability)
            for enabled in (False, True):
                refused = self.command(capability, enabled, key=f"{enabled}-{capability}")
                self.assertEqual(refused.failure.code, "authorization_capability_configured", capability)
            self.assertEqual(self.state(capability), "active", capability)
            # 原样不动：撤销会被下一次加载复原，还会让屏幕准备直接失败。
            record = next(grant for grant in self.identity.snapshot().grants if grant.grant_id == grant_id)
            self.assertEqual((record.state, record.revision), (GrantState.ACTIVE, 1), capability)
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())

    def test_a_stale_revision_fails_instead_of_clobbering(self):
        self.capability(GRANT_PREFIX + "seed", "proactive.contact")
        stale = self.identity.revision
        self.command("proactive.contact", False, key="winner", revision=stale).unwrap()
        refused = self.command("proactive.contact", True, key="loser", revision=stale)
        self.assertEqual(refused.failure.code, "authorization_revision_conflict")
        # 被拒绝的那一次没有落地：赢家的撤销仍然是最终状态。
        self.assertEqual(self.state("proactive.contact"), "revoked")

    def test_a_switch_on_a_capability_the_page_may_not_own_never_touches_any_grant(self):
        """一次被拒绝的开关不许留下任何痕迹。

        配置派生的授权是**已经生效**的那一份，所以两个方向都被拒绝；
        关键在于拒绝之后记录仍是原样（状态、版本、条数都不动），
        否则"拒绝了"与"改坏了"会同时为真。
        """
        self.capability(STAGING_CAPABILITY_GRANT_PREFIX + "text", "text")
        before = self.identity.revision
        for enabled in (False, True):
            refused = self.command("text", enabled, key=f"reissue-{enabled}")
            self.assertEqual(refused.failure.code, "authorization_capability_configured")
        # 记录本身没动：既没有被撤销，也没有多出本页的一份。
        written = next(grant for grant in self.identity.snapshot().grants
                       if grant.grant_id == STAGING_CAPABILITY_GRANT_PREFIX + "text")
        self.assertEqual((written.state, written.revision), (GrantState.ACTIVE, 1))
        self.assertEqual(len(self.identity.snapshot().grants), 1)
        # 拒绝发生在写入之前：连账本里都不该留下这次尝试。
        self.assertEqual(self.identity.revision, before)
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())

    def test_the_same_operation_key_twice_does_not_create_two_grants(self):
        first = self.command("proactive.contact", True, key="same-key").unwrap()
        self.assertFalse(first["replayed"])
        second = self.command("proactive.contact", True, key="same-key").unwrap()
        self.assertTrue(second["replayed"])
        self.assertEqual(second["operation_id"], first["operation_id"])
        self.assertEqual(len([grant for grant in self.identity.snapshot().grants
                              if grant.grant_id.startswith(GRANT_PREFIX)]), 1)
        # 同一个键换个参数不是重放，而是被拒绝的幂等冲突。
        self.assertEqual(self.command("proactive.contact", False, key="same-key").failure.code,
                         "idempotency_key_conflict")
        self.assertEqual(len([grant for grant in self.identity.snapshot().grants
                              if grant.grant_id.startswith(GRANT_PREFIX)]), 1)

    def test_a_replayed_operation_never_re_checks_the_old_revision(self):
        first = self.command("proactive.contact", True, key="replay-key").unwrap()
        # 别人随后改了同一份记录：重放原操作仍然返回原结果，不会因为 revision
        # 变了就报冲突——那会让一次已经成功的写入看起来失败。
        self.capability(GRANT_PREFIX + "other", "memory.read")
        replay = self.command("proactive.contact", True, key="replay-key", revision=1).unwrap()
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["operation_id"], first["operation_id"])

    def test_a_malformed_command_is_refused_before_anything_is_written(self):
        malformed = ({},
                     {"operation_key": "k"},
                     {"operation_key": "k", "subject_id": self.subject_id, "capability": "proactive.contact",
                      "enabled": "yes", "expected_revision": 1},
                     {"operation_key": "", "subject_id": self.subject_id, "capability": "proactive.contact",
                      "enabled": True, "expected_revision": 1},
                     {"operation_key": "k", "subject_id": self.subject_id, "capability": "proactive.contact",
                      "enabled": True, "expected_revision": 1, "extra": 1})
        for command in malformed:
            self.assertEqual(self.manager.configure(self.core, command, observed_at=AT).failure.code,
                             "authorization_command_invalid")
        self.assertEqual(self.runtime.read_all("SELECT * FROM identity_grants", ()), ())
        self.assertEqual(self.runtime.read_all("SELECT * FROM operations", ()), ())


class _Query:
    """请求查询串的最小实现：只要布尔、包含、keys/get/getlist 几个只读入口。

    真实的 starlette ``QueryParams('')`` 是**假值**（宿主路由靠这一点判断
    "这次请求不许带查询串"），所以这里也必须给出 ``__bool__``，否则夹具会把
    每一条 POST 都判成不合法——而生产里它们本来是合法的。
    """

    def __init__(self, text=""):
        self._values = {}
        for part in filter(None, text.split("&")):
            key, _, value = part.partition("=")
            self._values.setdefault(key, []).append(value)

    def __bool__(self):
        return bool(self._values)

    def __iter__(self):
        return iter(self._values)

    def __contains__(self, key):
        return key in self._values

    def keys(self):
        return list(self._values)

    def get(self, key, default=None):
        return self._values.get(key, [default])[0]

    def getlist(self, key):
        return list(self._values.get(key, ()))


def _body(payload):
    async def reader():
        return payload
    return reader


class AuthorizationRouteTests(unittest.IsolatedAsyncioTestCase):
    """宿主路由的形状与鉴权：这是页面唯一能碰到的入口。"""

    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-authorization-api-")
        self.addCleanup(self.temporary.cleanup)
        self.native = support.WebContext()
        types = support.NativeAdapterTypes("4.27.2", support.FakeEvent, support.FakeProvider,
                                           NS, NS, support.FakeReverseApi)
        self.controller = support.AstrBotStagingController(self.native, support.host_config(),
                                                           Path(self.temporary.name), native_types=types,
                                                           now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.controller.register_routes()

    def handler(self, method="GET", path=AUTHORIZATION_PATH):
        return next(handler for route, handler, methods, _ in self.native.registered_web_apis
                    if route == path and method in methods)

    async def send(self, *, method="GET", path=AUTHORIZATION_PATH, username="admin", query="", payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        with patch("astrbot_host.acquaintance_api.request",
                   NS(username=username, query=_Query(query), body=_body(body))):
            return await self.handler(method, path)()

    async def subject(self):
        """这个运行实例里那个人的受信 subject：目录与授权都按它寻址。"""
        entries = _authorization_participants(self.controller.runtime, self.controller.resolved_settings(), observed_at=support.NOW)
        self.assertEqual(len(entries), 1, entries)
        return entries[0]["subject_id"]

    async def test_both_routes_require_login_a_loaded_profile_and_core_tier(self):
        # 两个方法都注册在同一个地址上：读一个方法、写另一个方法。
        self.assertEqual({name for route, _, methods, _ in self.native.registered_web_apis
                          if route == AUTHORIZATION_PATH for name in methods}, {"GET", "POST"})
        self.assertEqual((await self.send(username="api_key:synthetic"))["data"]["code"],
                         "dashboard_identity_required")
        self.assertEqual((await self.send())["data"]["code"], "staging_not_initialized")
        (await self.controller.initialize_profile()).unwrap()
        # 查询串要么正好一个 subject_id，要么整条请求不合法。
        for query in ("subject_id=200&extra=1", "other=1", "subject_id=200&subject_id=201", ""):
            self.assertEqual((await self.send(query=query))["data"]["code"],
                             "acquaintance_request_invalid", query)
        policy = ObjectAccessPolicy(self.controller.runtime)
        operator = dashboard_operator(self.controller.runtime, "admin", at=support.NOW)
        policy.set_tier(operator.subject, AuthorizationTier.IMPORTANT,
                        expected_revision=policy.revision, observed_at=support.NOW)
        self.assertEqual((await self.send(query="subject_id=200"))["data"]["code"], "core_access_required")
        self.assertEqual((await self.send(method="POST", payload={}))["data"]["code"], "core_access_required")
        self.assertEqual(self.native.provider.client.state.calls, [])

    async def test_reading_one_person_reports_the_records_this_page_can_change(self):
        (await self.controller.initialize_profile()).unwrap()
        subject = await self.subject()
        response = await self.send(query=f"subject_id={subject}")
        self.assertEqual(response["status"], "ok", response)
        # 运行实例初始化给配置里的能力签了授权：它们如实出现，但本页改不了。
        items = response["data"]["items"]
        self.assertTrue(items)
        self.assertEqual({item["managed_by"] for item in items}, {MANAGED_BY_CONFIGURATION, MANAGED_BY_PAGE})
        self.assertEqual({item["revocable"] for item in items}, {False, True})
        self.assertIn("conversation.reply", {item["capability"] for item in items})
        # 授权清单不带记忆正文，也不带人格指纹。
        self.assertNotIn("representation", json.dumps(response))
        self.assertNotIn("instruction_hash", json.dumps(response))

    async def test_switching_then_reading_back_shows_the_new_state(self):
        (await self.controller.initialize_profile()).unwrap()
        subject = await self.subject()
        capability = "memory.subscribe"
        before = await self.send(query=f"subject_id={subject}")
        self.assertNotIn(capability, {item["capability"] for item in before["data"]["items"]})
        revision = before["data"]["items"][0]["policy_revision"]
        written = await self.send(method="POST", payload={"operation_key": "route-on", "subject_id": subject,
            "capability": capability, "enabled": True, "expected_revision": revision})
        self.assertEqual(written["status"], "ok", written)
        row = next(item for item in written["data"]["status"]["items"] if item["capability"] == capability)
        self.assertEqual((row["state"], row["managed_by"], row["revocable"]), ("active", MANAGED_BY_PAGE, True))
        after = await self.send(query=f"subject_id={subject}")
        self.assertEqual(next(item for item in after["data"]["items"]
                              if item["capability"] == capability)["state"], "active")
        # 关掉它：写侧真的改的是记录，读侧如实回报。
        off = await self.send(method="POST", payload={"operation_key": "route-off", "subject_id": subject,
            "capability": capability, "enabled": False, "expected_revision": row["policy_revision"]})
        self.assertEqual(off["status"], "ok", off)
        self.assertEqual(next(item for item in off["data"]["status"]["items"]
                              if item["capability"] == capability)["state"], "revoked")

    async def test_single_account_dialogue_can_be_reenabled_before_reopening(self):
        (await self.controller.initialize_profile()).unwrap()
        subject = await self.subject()
        for enabled in (False, True):
            status = (await self.send(query=f"subject_id={subject}"))["data"]
            result = await self.send(method="POST", payload={"subject_id": subject,
                "operation_key": "single-dialogue-" + str(enabled), "capability": "conversation.reply",
                "enabled": enabled, "expected_revision": status["policy_revision"]})
            self.assertEqual(result["status"], "ok", result)
        await self.controller.terminate()
        self.controller = support.AstrBotStagingController(self.native, support.host_config(),
            Path(self.temporary.name), native_types=self.controller.native_types, now=lambda: support.NOW)
        self.addAsyncCleanup(self.controller.terminate)
        self.controller.register_routes()
        (await self.controller.load_existing()).unwrap()
        status = (await self.send(query=f"subject_id={subject}"))["data"]
        self.assertEqual(next(item for item in status["items"] if item["capability"] == "conversation.reply")["state"], "active")

    async def test_a_malformed_body_or_a_configured_capability_is_refused_with_its_own_code(self):
        (await self.controller.initialize_profile()).unwrap()
        subject = await self.subject()
        for payload in ({"operation_key": "k"},
                        {"operation_key": "k", "subject_id": subject, "capability": "memory.subscribe",
                         "enabled": True}):
            self.assertEqual((await self.send(method="POST", payload=payload))["data"]["code"],
                             "authorization_command_invalid")
        with patch("astrbot_host.acquaintance_api.request",
                   NS(username="admin", query=_Query(), body=_body(b"not json"))):
            self.assertEqual((await self.handler("POST")())["data"]["code"], "authorization_command_invalid")
        reading = await self.send(query=f"subject_id={subject}")
        revision = reading["data"]["items"][0]["policy_revision"]
        refused = await self.send(method="POST", payload={"operation_key": "route-configured", "subject_id": subject,
            "capability": "text", "enabled": False, "expected_revision": revision})
        self.assertEqual(refused["data"]["code"], "authorization_capability_configured")
        again = await self.send(query=f"subject_id={subject}")
        self.assertEqual(next(item for item in again["data"]["items"]
                              if item["capability"] == "text")["state"], "active")

    async def test_administrator_name_route_is_scoped_revisioned_and_idempotent(self):
        self.assertEqual({name for route, _, methods, _ in self.native.registered_web_apis
                          if route == ADMIN_NAME_PATH for name in methods}, {"POST"})
        (await self.controller.initialize_profile()).unwrap()
        subject = await self.subject()
        settings = self.controller.resolved_settings()
        route = {"platform": settings.platform_id, "bot_id": settings.bot_id,
                 "account_id": settings.account_id, "role_id": settings.role_id}
        native_account_id = settings.participant_id
        owner = person_owner_key(self.controller.runtime.installation_id, route["platform"],
            route["bot_id"], route["account_id"], subject, route["role_id"])
        document = empty_person_card()
        document.update(route={**route, "subject_id": subject}, native_account_id=native_account_id,
                        platform_nickname="平台昵称")
        with self.controller.runtime.transaction() as connection:
            connection.execute("""INSERT INTO memory_views(
                view_id, owner_key, kind, revision, state, document_json, source_json, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)""",
                (card_id(owner), owner, PERSON_CARD_KIND, 1, encode(document), encode({"owner": "memory.person"}),
                 stamp(support.NOW)))

        command = {"operation_key": "admin-name-1", "subject_id": subject,
            "platform": route["platform"], "bot_id": route["bot_id"], "account_id": route["account_id"],
            "role_id": route["role_id"], "native_account_id": native_account_id,
            "admin_nickname": "管理员称呼", "expected_revision": 1}
        first = await self.send(method="POST", path=ADMIN_NAME_PATH, payload=command)
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual((first["data"]["admin_nickname"], first["data"]["revision"]), ("管理员称呼", 2))
        replay = await self.send(method="POST", path=ADMIN_NAME_PATH, payload=command)
        self.assertTrue(replay["data"]["replayed"])
        self.assertEqual(self.controller.runtime.read_one("SELECT revision FROM memory_views WHERE view_id = ?",
            (card_id(owner),))["revision"], 2)

        stale = {**command, "operation_key": "admin-name-stale", "admin_nickname": "旧稱呼"}
        self.assertEqual((await self.send(method="POST", path=ADMIN_NAME_PATH, payload=stale))["data"]["code"],
                         "person_nickname_revision_conflict")
        forged = {**command, "operation_key": "admin-name-forged", "bot_id": "other-bot",
                  "expected_revision": 2}
        self.assertEqual((await self.send(method="POST", path=ADMIN_NAME_PATH, payload=forged))["data"]["code"],
                         "acquaintance_person_unknown")

        cleared = {**command, "operation_key": "admin-name-clear", "admin_nickname": "", "expected_revision": 2}
        response = await self.send(method="POST", path=ADMIN_NAME_PATH, payload=cleared)
        self.assertEqual(response["status"], "ok", response)
        self.assertEqual((response["data"]["display_name"], response["data"]["name_basis"]),
                         ("平台昵称", "platform"))
        invalid = await self.send(method="POST", path=ADMIN_NAME_PATH, query="unexpected=1", payload=cleared)
        self.assertEqual(invalid["data"]["code"], "acquaintance_request_invalid")


if __name__ == "__main__":
    unittest.main()

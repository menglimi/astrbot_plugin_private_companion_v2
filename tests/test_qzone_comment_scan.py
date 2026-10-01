"""后台扫描的节奏：什么时候扫、这一轮回哪几条、失败怎么退避。

三件事最容易在后台循环里写错，所以每条都有对应用例：
① **先问路再受理**——间隔没到就不该把评论写进幂等表（否则它永远回不了了）；
② **预算之外完全不碰**——``max_actions_per_tick`` 之外的新评论下一轮仍然是新的；
③ **失败退避、成功清零**，且同一条评论的回复键从不改变（结果未知也不换键重放）。
"""

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from companion_v2.execution.models import TaskError
from companion_v2.qzone.comment_scan import (BACKOFF_BASE, BACKOFF_CAP, DEFERRED, DUPLICATE, FAILED,
                                             NOT_DUE, READY, UNKNOWN, CommentScanner,
                                             reply_operation_key)
from companion_v2.qzone.inbox import CommentInbox
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
INSTALLATION_ID = "installation-qzone-scan"
OWNER = "qzone-role:test"


class FakeState:
    def __init__(self):
        self.last_action_at = {}
        self.publish_day = ""
        self.publish_count = 0


class FakeService:
    """只实现扫描器真正用到的那三个入口：配置、状态、扫自己的动态。"""

    def __init__(self, *, settings=None, items=(), state=None):
        self.settings = {"enabled": True, "comment_enabled": True, "comment_recent_posts": 5,
                         "action_min_interval_minutes": 30, "max_actions_per_tick": 1,
                         **(settings or {})}
        self.state_value = state or FakeState()
        self.items = list(items)
        self.calls = []

    def configuration(self, context, at):
        return self.settings

    def state(self, context):
        return self.state_value

    async def scan(self, context, *, scope, limit, detail):
        self.calls.append({"scope": scope, "limit": limit, "detail": detail})
        return {"scope": scope, "count": len(self.items), "items": self.items}


def comment(*, uin="7", name="小明", text="今天天气不错", at="1759000000"):
    return {"author_uin": uin, "author": name, "text": text, "at": at}


def item(*, post_ref="ref-1", post_id="tid-1", comments=(), author="角色"):
    return {"post_ref": post_ref, "post_id": post_id, "author": author, "comments": list(comments)}


class ScannerTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._temporary = TemporaryDirectory(prefix="companion-v2-qzone-scan-")
        self.root = Path(self._temporary.name) / "v2-data"
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION_ID)
        self.inbox = CommentInbox(self.runtime, now=lambda: NOW)

    def tearDown(self):
        self.runtime.close()
        self._temporary.cleanup()

    def scanner(self, service, *, now=NOW):
        return CommentScanner(service=service, inbox=self.inbox, runtime=self.runtime,
                              platform="qq-main", login="100", now=lambda: now)

    async def scan(self, service, *, now=NOW, owner=OWNER):
        return await self.scanner(service, now=now).scan(owner=owner, context=object(), at=now)


class GateTests(ScannerTestCase):
    async def test_a_disabled_switch_never_touches_the_inbox(self):
        service = FakeService(settings={"enabled": False}, items=[item(comments=[comment()])])
        plan = await self.scan(service)
        self.assertFalse(plan.due)
        self.assertEqual(plan.reason, "空间能力已关闭")
        self.assertEqual(service.calls, [], "总闸关着就不该去刷空间")

        service = FakeService(settings={"comment_enabled": False}, items=[item(comments=[comment()])])
        plan = await self.scan(service)
        self.assertEqual(plan.reason, "回复未开启")
        # 关键：这两次都没把评论写进幂等表——否则这条评论以后永远回不了了。
        self.assertFalse(self.inbox.seen(_event()))

    async def test_a_spacing_block_defers_without_accepting_the_comment(self):
        state = FakeState()
        state.last_action_at = {"comment": NOW.isoformat()}
        service = FakeService(items=[item(comments=[comment()])], state=state)
        plan = await self.scan(service)
        self.assertFalse(plan.due)
        self.assertIn("分钟", plan.reason)
        self.assertEqual(plan.candidates, ())
        self.assertEqual(service.calls, [], "间隔没到就不该刷空间")

        # 间隔过去之后，同一条评论仍然是新的，可以正常回。
        later = NOW + timedelta(minutes=31)
        plan = await self.scan(service, now=later)
        self.assertTrue(plan.has_work)


class CandidateTests(ScannerTestCase):
    async def test_a_new_comment_becomes_a_candidate_with_a_stable_key(self):
        service = FakeService(items=[item(comments=[comment()])])
        plan = await self.scan(service)
        self.assertTrue(plan.due and plan.has_work)
        self.assertEqual(service.calls, [{"scope": "own", "limit": 5, "detail": True}])
        candidate = plan.candidates[0]
        self.assertEqual(candidate.post_ref, "ref-1")
        self.assertEqual(candidate.text, "今天天气不错")
        self.assertEqual(candidate.operation_key, reply_operation_key(candidate.event))

    async def test_the_budget_defers_the_rest_without_accepting_them(self):
        service = FakeService(items=[item(comments=[comment(uin="7", name="小明"),
                                                    comment(uin="8", name="小张", text="我也想问")])])
        plan = await self.scan(service)
        self.assertEqual(len(plan.candidates), 1, "每轮预算默认 1 条")
        self.assertEqual(plan.candidates[0].event.author, "uin:7")
        self.assertEqual([reason for reason, _ in plan.skipped], [DEFERRED])

        # 下一轮：被缓的那条仍然是新的（幂等表里没有它），于是这轮轮到它。
        second = await self.scan(service, now=NOW + timedelta(minutes=31))
        self.assertEqual(len(second.candidates), 1)
        self.assertEqual(second.candidates[0].event.author, "uin:8")
        self.assertEqual(second.candidates[0].author, "小张")

    async def test_own_comments_and_repeats_are_not_candidates(self):
        service = FakeService(items=[item(comments=[comment(uin="100")])])
        plan = await self.scan(service)
        self.assertEqual(plan.candidates, (), "自己不回自己")
        self.assertEqual(plan.skipped[0][0], "self")

        service = FakeService(items=[item(comments=[comment()])])
        first = await self.scan(service)
        self.assertTrue(first.has_work)
        self.scanner(service).note_replied(owner=OWNER, candidate=first.candidates[0],
                                           reply_text="是啊，风也正好", at=NOW)
        again = await self.scan(service, now=NOW + timedelta(minutes=31))
        self.assertEqual(again.candidates, ())
        self.assertEqual(again.skipped[0][0], DUPLICATE, "回过的评论不该再回一次")


class CursorTests(ScannerTestCase):
    async def test_the_interval_holds_until_it_is_due(self):
        service = FakeService(items=[item(comments=[comment()])])
        scanner = self.scanner(service)
        plan = await scanner.scan(owner=OWNER, context=object(), at=NOW)
        scanner.note_success(owner=OWNER, at=NOW, interval_minutes=30)

        soon = await self.scan(service, now=NOW + timedelta(minutes=5))
        self.assertFalse(soon.due)
        self.assertEqual(soon.reason, NOT_DUE)
        due = await self.scan(service, now=NOW + timedelta(minutes=31))
        self.assertTrue(due.due)

    async def test_failures_back_off_exponentially_and_cap(self):
        service = FakeService()
        scanner = self.scanner(service)
        delays = []
        for step in range(8):
            cursor = scanner.note_failure(owner=OWNER, at=NOW)
            delays.append(cursor.next_scan_at - NOW)
        self.assertEqual(delays[0], BACKOFF_BASE)
        self.assertEqual(delays[1], BACKOFF_BASE * 2)
        self.assertEqual(delays[2], BACKOFF_BASE * 4)
        self.assertEqual(delays[-1], BACKOFF_CAP, "退避要封顶，不能无限增长")
        self.assertEqual(scanner.cursor(owner=OWNER).consecutive_failures, 8)

        # 成功即清零，间隔回到常规值。
        cursor = scanner.note_success(owner=OWNER, at=NOW, interval_minutes=30)
        self.assertEqual(cursor.consecutive_failures, 0)
        self.assertEqual(cursor.next_scan_at, NOW + timedelta(minutes=30))

    async def test_the_cursor_is_per_owner_and_survives_a_restart(self):
        service = FakeService(items=[item(comments=[comment()])])
        scanner = self.scanner(service)
        first = await scanner.scan(owner=OWNER, context=object(), at=NOW)
        scanner.note_replied(owner=OWNER, candidate=first.candidates[0], reply_text="是啊", at=NOW,
                             interval_minutes=30)
        scanner.note_success(owner="qzone-role:other", at=NOW, interval_minutes=30)

        self.runtime.close()
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION_ID)
        restarted = self.scanner(service)
        self.assertEqual(restarted.cursor(owner=OWNER).consecutive_failures, 0)
        self.assertEqual(restarted.cursor(owner=OWNER).next_scan_at, NOW + timedelta(minutes=30))
        self.assertIsNone(restarted.cursor(owner="qzone-role:unknown").next_scan_at)

    async def test_an_unknown_result_keeps_the_same_reply_key(self):
        service = FakeService(items=[item(comments=[comment()])])
        first = await self.scan(service)
        candidate = first.candidates[0]
        # 结果未知：不推进这条评论的账，也不换键——换键就等于再发一条。
        self.scanner(service).note_failure(owner=OWNER, at=NOW, reason="unknown")
        second = await self.scan(service, now=NOW + timedelta(minutes=31))
        self.assertEqual(second.candidates, ())
        self.assertEqual(second.skipped[0][0], DUPLICATE)
        self.assertEqual(reply_operation_key(second.skipped and candidate.event), candidate.operation_key)


class ReplyTests(ScannerTestCase):
    """发送与记账的顺序：**先发后记**，发不出去就不许动账本。"""

    def make_service(self, *, error=None):
        service = FakeService(items=[item(comments=[comment()])])
        service.sent = []

        async def send_reply(context, *, post_ref, text, operation_key):
            service.sent.append({"post_ref": post_ref, "text": text, "operation_key": operation_key})
            if error is not None:
                raise error
            return {"post_ref": post_ref, "state": "accepted"}

        service.comment = send_reply
        return service

    async def test_a_successful_reply_records_the_ledger_and_advances_the_cursor(self):
        service = self.make_service()
        scanner = self.scanner(service)
        plan = await scanner.scan(owner=OWNER, context=object(), at=NOW)
        candidate = plan.candidates[0]

        await scanner.reply(owner=OWNER, context=object(), candidate=candidate, text="是啊，风也正好", at=NOW)

        self.assertEqual(service.sent[0]["operation_key"], candidate.operation_key)
        self.assertEqual(self.inbox.state(platform="qq-main", login="100").sent[0].text_norm,
                         "是啊风也正好")
        self.assertEqual(scanner.cursor(owner=OWNER).consecutive_failures, 0)

        # 再扫一轮：这条已经回过了，不再候选。
        again = await self.scan(service, now=NOW + timedelta(minutes=31))
        self.assertEqual(again.candidates, ())
        self.assertEqual(again.skipped[0][0], DUPLICATE)

    async def test_an_unknown_delivery_does_not_record_a_reply(self):
        error = TaskError("qzone_delivery_unknown", "投递结果未知")
        service = self.make_service(error=error)
        scanner = self.scanner(service)
        plan = await scanner.scan(owner=OWNER, context=object(), at=NOW)
        candidate = plan.candidates[0]

        with self.assertRaises(TaskError):
            await scanner.reply(owner=OWNER, context=object(), candidate=candidate, text="是啊", at=NOW)

        # 账本没动（不假装发成功了），游标退避，评论仍是已受理。
        self.assertEqual(self.inbox.state(platform="qq-main", login="100").sent, ())
        self.assertEqual(scanner.cursor(owner=OWNER).consecutive_failures, 1)
        self.assertEqual(scanner.cursor(owner=OWNER).last_reason, UNKNOWN)
        later = await self.scan(service, now=NOW + timedelta(minutes=6))
        self.assertEqual(later.candidates, (), "结果未知之后不再重试这条")
        self.assertEqual(service.sent[0]["operation_key"], candidate.operation_key)

    async def test_a_plain_failure_leaves_the_comment_answerable_later(self):
        service = self.make_service(error=TaskError("qzone_action_blocked", "距离上次同类动作不到 30 分钟"))
        scanner = self.scanner(service)
        plan = await scanner.scan(owner=OWNER, context=object(), at=NOW)
        candidate = plan.candidates[0]

        with self.assertRaises(TaskError):
            await scanner.reply(owner=OWNER, context=object(), candidate=candidate, text="是啊", at=NOW)

        self.assertEqual(scanner.cursor(owner=OWNER).last_reason, FAILED)
        self.assertEqual(self.inbox.state(platform="qq-main", login="100").sent, ())


def _event():
    from companion_v2.qzone.comments import comment_event
    return comment_event(platform="qq-main", login="100", post_tid="ref-1", uin="7", content="今天天气不错")


if __name__ == "__main__":
    unittest.main()

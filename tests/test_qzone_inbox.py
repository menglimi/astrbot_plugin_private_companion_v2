"""评论收件箱接到 V2 存储上的行为：真库、真幂等表、真文档。

这里问的是三件在扫描里最容易出错的事：
① 同一条评论被投递两次会不会回两次；② 评论被编辑过会不会被当成新评论；
③ 账本重启后还在不在。全部都走真实的 ``StorageRuntime`` 与 ``memory_views``。
"""

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from companion_v2.qzone.inbox import COOLDOWN, DUPLICATE, READY, SELF, CommentInbox, view_id
from companion_v2.storage.repositories import InboxRepository
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
INSTALLATION_ID = "installation-qzone-inbox"


class InboxTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._temporary = TemporaryDirectory(prefix="companion-v2-qzone-inbox-")
        self.root = Path(self._temporary.name) / "v2-data"
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION_ID)
        self.inbox = CommentInbox(self.runtime, now=lambda: NOW)

    def tearDown(self):
        self.runtime.close()
        self._temporary.cleanup()

    def decide(self, **changes):
        payload = {"platform": "qq-main", "login": "100", "post_tid": "tid-1", "comment_id": "c-1",
                   "uin": "7", "name": "小明", "content": "今天天气不错", "at": NOW}
        payload.update(changes)
        return self.inbox.decide(**payload)


class IntakeTests(InboxTestCase):
    async def test_a_new_comment_is_ready_and_a_replay_is_not(self):
        first = self.decide()
        self.assertTrue(first.should_reply)
        self.assertEqual(first.reason, READY)
        # 同一条评论再投一次：幂等表挡住，不再进入判定。
        self.assertEqual(self.decide().reason, DUPLICATE)
        # 换一种标点写法的同一条评论，仍然是同一条。
        self.assertEqual(self.decide(content="今天天气不错！").reason, DUPLICATE)

    async def test_an_edited_comment_is_a_conflict_not_a_new_comment(self):
        self.decide()
        edited = self.decide(content="说错了，是问晚饭")
        self.assertFalse(edited.accept)
        self.assertEqual(edited.reason, "inbox_event_conflict")

    async def test_two_people_using_the_same_comment_id_do_not_collide(self):
        self.assertTrue(self.decide().should_reply)
        other = self.decide(uin="8", name="小张", content="我也想说")
        self.assertTrue(other.should_reply, "别人的评论不能被当成同一条")
        self.assertEqual(other.event.author, "uin:8")

    async def test_the_same_comment_on_another_post_or_account_is_its_own_event(self):
        self.decide()
        self.assertTrue(self.decide(post_tid="tid-2").should_reply)
        self.assertTrue(self.decide(login="101").should_reply)

    async def test_an_id_less_comment_still_deduplicates_by_content(self):
        first = self.decide(comment_id="")
        self.assertTrue(first.should_reply)
        self.assertEqual(self.decide(comment_id="", content="今天天气不错！").reason, DUPLICATE)


class DecisionTests(InboxTestCase):
    async def test_own_comments_are_skipped(self):
        self.assertEqual(self.decide(uin="9", own_uin="9").reason, SELF)
        self.assertEqual(self.decide(uin="", name="角色本人", post_author_name="角色本人").reason, SELF)

    async def test_an_own_comment_shows_up_in_its_own_ledger(self):
        """自己发出去的那句话再被当成评论报回来时，账本认得出来（V1 的第三个条件）。"""
        self.inbox.record_sent(platform="qq-main", login="100", post_tid="tid-1", author="self",
                               comment_text="有人问天气", sent_text="今天天气不错", at=NOW)
        reported = self.decide(comment_id="c-777", uin="9", name="路人", content="今天天气不错！")
        self.assertEqual(reported.reason, SELF, "自己发的话不该被当成别人的评论来回")

    async def test_a_replied_person_is_throttled_even_under_a_new_id(self):
        first = self.decide()
        self.inbox.record_sent(platform="qq-main", login="100", post_tid="tid-1", author=first.event.author,
                               comment_text="今天天气不错", sent_text="是啊，风也正好", at=NOW)
        # 平台换了个 id 再报同一个人在同一帖下的另一句话：冷却仍然管用（V1 的节流层）。
        again = self.decide(comment_id="c-999", legacy="c-999", content="那明天呢")
        self.assertEqual(again.reason, COOLDOWN)
        # 而"同一条评论原样再报一次"是被幂等表永久挡住的，不吃冷却的时间窗。
        self.assertEqual(self.decide().reason, DUPLICATE)

    async def test_the_author_cooldown_holds_per_person_and_per_post(self):
        first = self.decide()
        self.inbox.record_sent(platform="qq-main", login="100", post_tid="tid-1", author=first.event.author,
                               comment_text="今天天气不错", sent_text="是啊", at=NOW)
        second = self.decide(comment_id="c-2", content="那明天呢")
        self.assertEqual(second.reason, COOLDOWN)
        # 换个人、换帖子都不吃这份冷却。
        self.assertTrue(self.decide(comment_id="c-3", uin="8", name="小张", content="我也想问").should_reply)
        self.assertTrue(self.decide(comment_id="c-4", post_tid="tid-2", content="另一个帖子").should_reply)
        # 冷却过后又能回。
        later = CommentInbox(self.runtime, now=lambda: NOW + timedelta(hours=6, minutes=1))
        after = later.decide(platform="qq-main", login="100", post_tid="tid-1", comment_id="c-5",
                             uin="7", name="小明", content="过了半天了",
                             at=NOW + timedelta(hours=6, minutes=1))
        self.assertTrue(after.should_reply)


class StorageTests(InboxTestCase):
    async def test_the_ledger_survives_a_restart(self):
        first = self.decide()
        self.inbox.record_sent(platform="qq-main", login="100", post_tid="tid-1", author=first.event.author,
                               comment_text="今天天气不错", sent_text="是啊，风也正好", at=NOW)
        self.runtime.close()
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION_ID)
        restarted = CommentInbox(self.runtime, now=lambda: NOW)

        replayed = restarted.decide(platform="qq-main", login="100", post_tid="tid-1", comment_id="c-2",
                                    uin="7", name="小明", content="那明天呢",
                                    at=NOW + timedelta(minutes=1))
        self.assertEqual(replayed.reason, COOLDOWN, "重启后账本必须还在")
        again = restarted.decide(platform="qq-main", login="100", post_tid="tid-1", comment_id="c-1",
                                 uin="7", name="小明", content="今天天气不错", at=NOW)
        self.assertEqual(again.reason, DUPLICATE, "重启后幂等表也必须还在")

    async def test_each_account_keeps_its_own_ledger(self):
        first = self.decide()
        self.inbox.record_sent(platform="qq-main", login="100", post_tid="tid-1", author=first.event.author,
                               comment_text="今天天气不错", sent_text="是啊", at=NOW)
        self.assertEqual(self.inbox.state(platform="qq-main", login="101").sent, ())
        self.assertEqual(len(self.inbox.state(platform="qq-main", login="100").sent), 1)
        self.assertNotEqual(view_id("qq-main", "100"), view_id("qq-main", "101"))

    async def test_the_document_stays_bounded(self):
        for index in range(200):
            decision = self.decide(comment_id=f"c-{index}", uin=str(index), content=f"评论 {index}")
            self.inbox.record_sent(platform="qq-main", login="100", post_tid="tid-1",
                                   author=decision.event.author, comment_text=f"评论 {index}",
                                   sent_text=f"回复 {index}", at=NOW + timedelta(seconds=index))
        state = self.inbox.state(platform="qq-main", login="100", at=NOW + timedelta(seconds=200))
        self.assertEqual(len(state.sent), 160)
        self.assertEqual(len(state.replies), 160)

    async def test_the_inbox_table_is_the_same_primitive_the_host_uses(self):
        event = self.decide().event
        receipt = InboxRepository(self.runtime).accept(
            consumer=event.consumer, event_id=event.event_id, payload_hash=event.payload_hash,
            observed_at=NOW)
        self.assertTrue(receipt.value.replayed, "收件箱用的就是宿主那一张幂等表")


if __name__ == "__main__":
    unittest.main()

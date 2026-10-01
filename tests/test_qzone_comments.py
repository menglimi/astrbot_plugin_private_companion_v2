"""空间评论的识别与幂等规则：把 V1 的行为锁成断言。

这些用例刻意**不碰存储、不连网**：它们问的是"这一条到底是不是同一条、要不要回"，
也就是收件箱最容易出错的那一层。存储侧只约定一件事——``comment_event`` 的三元组
直接交给 ``InboxRepository.accept``。
"""

import unittest
from datetime import datetime, timedelta, timezone

from companion_v2.qzone.comments import (
    AUTHOR_COOLDOWN, CommentRecord, author_key, author_post_key, author_post_recently_replied,
    comment_event, fingerprint, fuzzy_score, identifiers, is_self, leaks_internal, legacy_id,
    matches_recent_sent, normalized_text, note_sent, single_line, trim_records)


NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class NormalizationTests(unittest.TestCase):
    def test_markup_entities_case_and_punctuation_all_disappear(self):
        # 同一条评论在不同接口里的写法：带标签、带实体、大小写、全半角标点。
        left = normalized_text("<b>今天</b>天气不错！&amp; 你呢？")
        right = normalized_text("今天天气不错&你呢")
        self.assertEqual(left, right)

    def test_normalized_text_is_bounded_and_idempotent(self):
        long_text = "啊" * 400
        once = normalized_text(long_text)
        self.assertEqual(len(once), 160)
        self.assertEqual(normalized_text(once), once)

    def test_single_line_never_raises_on_dirty_input(self):
        self.assertEqual(single_line(None, 10), "")
        self.assertEqual(single_line("  多   空  白  ", 20), "多 空 白")
        self.assertEqual(len(single_line("x" * 50, 8)), 8)


class IdentityTests(unittest.TestCase):
    def test_author_key_prefers_the_stable_number_then_the_name(self):
        self.assertEqual(author_key(uin="12345"), "uin:12345")
        self.assertEqual(author_key(uin="", name=" 小明 "), "name:小明")
        self.assertEqual(author_key(), "unknown")

    def test_author_post_key_scopes_throttling_to_one_post(self):
        self.assertEqual(author_post_key("tid-1", "uin:1"), "tid-1|uin:1")
        self.assertEqual(author_post_key("", "uin:1"), "post|uin:1")

    def test_fingerprint_is_stable_and_content_sensitive(self):
        first = fingerprint("tid-1", uin="7", content="你好！")
        self.assertEqual(first, fingerprint("tid-1", uin="7", content="你好"))
        self.assertNotEqual(first, fingerprint("tid-2", uin="7", content="你好"))
        self.assertNotEqual(first, fingerprint("tid-1", uin="8", content="你好"))
        self.assertTrue(first.startswith("tid-1:fp:"))

    def test_identifiers_prefer_the_platform_id_and_keep_bounded_fallbacks(self):
        identity = identifiers(post_tid="tid-1", comment_id="c-9", uin="7", content="在吗",
                               legacy="old-9")
        self.assertEqual(identity.comment_id, "c-9")
        self.assertEqual(identity.stable, "c-9")
        self.assertEqual(identity.fallbacks, ("c-9", "old-9"))
        self.assertTrue(identity.comment_key.startswith("tid-1:fp:"))

    def test_identifiers_fall_back_to_the_fingerprint_without_an_id(self):
        identity = identifiers(post_tid="tid-1", uin="7", content="在吗")
        self.assertEqual(identity.comment_id, "")
        self.assertEqual(identity.stable, identity.comment_key)
        self.assertEqual(identity.fallbacks, (legacy_id("tid-1", uin="7", content="在吗"),))


class RecordTests(unittest.TestCase):
    def record(self, *, key, post_tid="tid-1", text_norm="你好", at=None, author="uin:1"):
        return CommentRecord(key, post_tid, author, text_norm, text_norm, at or NOW)

    def test_expired_and_duplicate_records_are_dropped(self):
        kept = trim_records([
            self.record(key="a", at=NOW - timedelta(days=8)),          # 过期
            self.record(key="b", at=NOW - timedelta(days=1)),          # 保留
            self.record(key="b", at=NOW),                              # 重复键
        ], now=NOW)
        self.assertEqual([item.key for item in kept], ["b"])

    def test_documents_round_trip_through_the_stored_shape(self):
        stored = [self.record(key="a", at=NOW).as_document()]
        restored = trim_records(stored, now=NOW)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].key, "a")
        self.assertEqual(restored[0].at, NOW)

    def test_records_without_a_usable_key_are_ignored(self):
        self.assertEqual(trim_records([{"post_tid": "", "ts": NOW.timestamp()}], now=NOW), ())
        self.assertEqual(trim_records([{"post_tid": "tid-1", "text_norm": "你好",
                                        "ts": NOW.timestamp()}], now=NOW)[0].key, "tid-1|你好")


class DedupAndThrottleTests(unittest.TestCase):
    def test_the_same_comment_from_another_interface_is_recognized_as_sent(self):
        sent, _ = note_sent((), (), now=NOW, post_tid="tid-1", author="uin:1",
                            comment_text="在吗", sent_text="在的，刚看到！")
        self.assertTrue(matches_recent_sent(sent, now=NOW, post_tid="tid-1", content="在的, 刚看到"))
        self.assertFalse(matches_recent_sent(sent, now=NOW, post_tid="tid-2", content="在的，刚看到"))
        self.assertFalse(matches_recent_sent(sent, now=NOW, post_tid="tid-1", content="别的话"))

    def test_a_sent_record_expires_after_a_week(self):
        sent, _ = note_sent((), (), now=NOW, post_tid="tid-1", author="uin:1",
                            comment_text="在吗", sent_text="在的")
        later = NOW + timedelta(days=7, seconds=1)
        self.assertFalse(matches_recent_sent(sent, now=later, post_tid="tid-1", content="在的"))

    def test_self_comments_are_never_answered(self):
        self.assertTrue(is_self(own_uin="9", comment_uin="9"))
        self.assertTrue(is_self(commenter_name="小林", author_name="小林"))
        self.assertTrue(is_self(already_sent=True))
        self.assertFalse(is_self(own_uin="9", comment_uin="8", commenter_name="小张", author_name="小林"))

    def test_author_reply_cooldown_holds_then_releases(self):
        _, replies = note_sent((), (), now=NOW, post_tid="tid-1", author="uin:1",
                               comment_text="在吗", sent_text="在的")
        self.assertTrue(author_post_recently_replied(replies, now=NOW, post_tid="tid-1", author="uin:1"))
        within = NOW + AUTHOR_COOLDOWN - timedelta(minutes=1)
        self.assertTrue(author_post_recently_replied(replies, now=within, post_tid="tid-1", author="uin:1"))
        after = NOW + AUTHOR_COOLDOWN + timedelta(minutes=1)
        self.assertFalse(author_post_recently_replied(replies, now=after, post_tid="tid-1", author="uin:1"))
        # 换一个人、或换一个帖子，都不吃这份冷却。
        self.assertFalse(author_post_recently_replied(replies, now=NOW, post_tid="tid-1", author="uin:2"))
        self.assertFalse(author_post_recently_replied(replies, now=NOW, post_tid="tid-2", author="uin:1"))

    def test_note_sent_keeps_both_ledgers_bounded(self):
        sent, replies = (), ()
        for index in range(200):
            sent, replies = note_sent(sent, replies, now=NOW + timedelta(seconds=index), post_tid="tid-1",
                                      author=f"uin:{index}", comment_text=f"评论{index}",
                                      sent_text=f"回复{index}")
        self.assertEqual(len(sent), 160)
        self.assertEqual(len(replies), 160)
        self.assertEqual(sent[-1].text_norm, normalized_text("回复199"))


class GuardTests(unittest.TestCase):
    def test_internal_words_and_blank_replies_are_refused(self):
        self.assertTrue(leaks_internal(""))
        self.assertTrue(leaks_internal("   "))
        self.assertTrue(leaks_internal("我老大说了算"))
        self.assertTrue(leaks_internal("这是插件的事"))
        self.assertFalse(leaks_internal("今天天气不错，去走走吧"))

    def test_the_pattern_list_can_be_injected(self):
        self.assertTrue(leaks_internal("某个敏感词", patterns=("敏感词",)))
        self.assertFalse(leaks_internal("老大", patterns=("敏感词",)))

    def test_fuzzy_score_admits_what_it_is(self):
        self.assertEqual(fuzzy_score("今天天气不错", "今天天气不错"), 1.0)
        self.assertGreater(fuzzy_score("今天天气不错啊", "今天天气不错"), 0.9)
        self.assertLess(fuzzy_score("今天天气不错啊", "今天天气不错"), 1.0)
        # 模糊就是模糊：改了几个字之后分数明显掉下来，判定方不能拿它当"同一条"。
        loose = fuzzy_score("午饭吃了拉面", "午饭吃的是拉面")
        self.assertGreater(loose, 0.1)
        self.assertLess(loose, 0.5)
        self.assertEqual(fuzzy_score("", "午饭"), 0.0)
        self.assertEqual(fuzzy_score("午饭", ""), 0.0)


class InboxEventTests(unittest.TestCase):
    def test_the_same_comment_folds_to_the_same_idempotency_key(self):
        first = comment_event(platform="qq-main", login="100", post_tid="tid-1", comment_id="c-1",
                              uin="7", content="在吗")
        second = comment_event(platform="qq-main", login="100", post_tid="tid-1", comment_id="c-1",
                               uin="7", content="在吗？")
        self.assertEqual(first.consumer, "qzone.comment")
        self.assertEqual(first.event_id, second.event_id, "同一条评论必须折成同一个幂等键")
        self.assertEqual(first.payload_hash, second.payload_hash, "标点差异不算改过正文")

    def test_edited_text_keeps_the_key_but_changes_the_payload(self):
        before = comment_event(platform="qq-main", login="100", post_tid="tid-1", comment_id="c-1",
                               uin="7", content="在吗")
        after = comment_event(platform="qq-main", login="100", post_tid="tid-1", comment_id="c-1",
                              uin="7", content="说错了，我是问晚饭")
        self.assertEqual(before.event_id, after.event_id)
        self.assertNotEqual(before.payload_hash, after.payload_hash)

    def test_different_people_and_posts_never_collide(self):
        base = comment_event(platform="qq-main", login="100", post_tid="tid-1", comment_id="c-1",
                             uin="7", content="在吗")
        self.assertNotEqual(base.event_id, comment_event(platform="qq-main", login="100", post_tid="tid-1",
                                                         comment_id="c-1", uin="8", content="在吗").event_id)
        self.assertNotEqual(base.event_id, comment_event(platform="qq-main", login="100", post_tid="tid-2",
                                                         comment_id="c-1", uin="7", content="在吗").event_id)
        self.assertNotEqual(base.event_id, comment_event(platform="qq-second", login="100", post_tid="tid-1",
                                                         comment_id="c-1", uin="7", content="在吗").event_id)

    def test_an_id_less_comment_still_gets_a_stable_key(self):
        first = comment_event(platform="qq-main", login="100", post_tid="tid-1", uin="7", content="在吗")
        second = comment_event(platform="qq-main", login="100", post_tid="tid-1", uin="7", content="在吗！")
        self.assertEqual(first.event_id, second.event_id)

    def test_keys_are_bounded_opaque_tokens(self):
        event = comment_event(platform="qq-main", login="100", post_tid="t" * 200,
                              comment_id="c" * 200, uin="7", content="在吗")
        for value in (event.event_id, event.payload_hash):
            self.assertEqual(len(value), 32)
            self.assertTrue(value.isalnum())
        self.assertEqual(event.post_tid, "t" * 80)
        self.assertEqual(event.author, "uin:7")


if __name__ == "__main__":
    unittest.main()

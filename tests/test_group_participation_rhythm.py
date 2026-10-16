"""Group self-initiated speech: interjection budget, feedback learning, repeats.

V1 bounded group interjection with a minimum interval and a per-group daily
count, let member reactions change how eager the role was later, and joined a
same-content repeat burst until it decided to stop. V2 adds no send path for any
of that: the rules produce bounded prompt references and an owner-scoped ledger,
and everything the role says still leaves through the ordinary authorized group
delivery chain. These tests cover the rules, the ledger bounds and the fact that
reading them never sends anything.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.conversation.group_interjection import (ACKNOWLEDGED_STEP, IGNORED_STEP, INTERJECTION,
                                                          REPEAT_FOLLOW, REPEAT_INTERRUPT, WEIGHT_MAX,
                                                          WEIGHT_MIN, WEIGHT_START)
from companion_v2.conversation.group_observation import (PREFIX, TOPIC_KIND, fold_mood, fold_topic_threads,
                                                          joke_guard, moment_candidates, moment_portrait,
                                                          topic_signature, topic_signatures_similar)
from companion_v2.conversation.group_timing import RepeatPolicy, clean_group_text, repeat_burst, repeat_signature
from companion_v2.conversation.participation import (CONFIG_GROUP, CONFIG_LIMITS, GroupParticipation,
                                                     GroupParticipationConfigurationOwner,
                                                     configuration_fields)
from companion_v2.foundation.refs import ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.memory.group.access import owner_key
from companion_v2.storage.runtime import StorageRuntime


INSTALLATION = "group-rhythm-installation"
ROLE = SubjectRef(INSTALLATION, SubjectKind.BOT, "persona-a")
SCOPE = ScopeRef(INSTALLATION, "onebot", ScopeKind.GROUP, "group-a", "bot-a", "login-a",
                 "conversation-a", "session-a")
PRIVATE = ScopeRef(INSTALLATION, "onebot", ScopeKind.PRIVATE, "native-a", "bot-a", "login-a",
                   "conversation-a", "session-a")
TURN = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
NOW = TURN + timedelta(minutes=5)
NAMED = {"group_wakeup_bot_name": "小星"}
WATCHED = ("conversation_batches", "conversation_parts", "conversation_sent_history",
           "conversation_delivery_receipts", "execution_tasks", "conversation_tool_calls")


def group_context(scope=SCOPE, speaker="200"):
    return NS(scope=scope, role_binding=NS(role=ROLE), actor=NS(principal=NS(native_account_id=speaker)),
              key="group-origin-" + scope.native_scope_id)


def material(purpose, payload):
    return NS(purpose=purpose, payload=payload, source=None)


def prompt_request(texts, recent=(), at=TURN):
    """One material per admitted history item, exactly as the group context seals it."""
    materials = [material("current_source", texts[0])]
    materials.extend(material("merged_input:%d" % index, text) for index, text in enumerate(texts[1:], 2))
    materials.extend(material("group_conversation_history", json.dumps(item, ensure_ascii=False))
                     for item in recent)
    return NS(event=NS(received_at=at), context=NS(materials=tuple(materials)))


def member(text, speaker, at):
    return {"type": "group_member_message", "speaker_id": speaker, "received_at": at.isoformat(), "text": text}


def burst_history(text, *, count, first_at=TURN - timedelta(seconds=60), step=10):
    """``count`` member messages repeating one text, oldest first."""
    return tuple(member(text, "20%d" % index, first_at + timedelta(seconds=step * index))
                 for index in range(count))


def burst_at(at, text="哈哈", count=3, step=10):
    """A same-content burst that ends just before ``at``, inside its window."""
    return burst_history(text, count=count, first_at=at - timedelta(seconds=60), step=step)


class GroupRhythmFixture(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-group-rhythm-")
        self.addCleanup(temporary.cleanup)
        self.runtime = StorageRuntime.open(data_root=Path(temporary.name) / "data", installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.context = group_context()
        self.participation = GroupParticipation(NS(runtime=self.runtime, timezone_name="Asia/Shanghai",
                                                   tasks=NS(now=lambda: NOW)))

    # -- helpers ------------------------------------------------------

    def target(self):
        return ConfigTarget(INSTALLATION, ConfigLayer.WINDOW, ROLE, SCOPE)

    def configure(self, **changes):
        """Write explicit window values through the registered owner."""
        owner = GroupParticipationConfigurationOwner(self.runtime)
        fields = configuration_fields()
        owner.write(self.target(), fields,
                    changes={CONFIG_GROUP + "." + key: value for key, value in changes.items()},
                    reset=(), expected_revision=owner.read(self.target(), fields).revision, observed_at=NOW)

    def turn(self, texts, recent=(), at=TURN, settings=None, batch="batch-1"):
        """One group turn's references, frozen for this batch like ``augment`` does."""
        frozen = self.participation._build_turn(self.context, prompt_request(texts, recent, at), settings or {})
        self.participation._frozen_turns[batch] = frozen
        return frozen

    def confirm(self, batch_id, *, text="群里的确认发言", at=NOW):
        """One confirmed group delivery, written through the real receipt tables."""
        part_id, receipt = "part-" + batch_id, "receipt-part-" + batch_id
        with self.runtime.transaction() as connection:
            connection.execute("""INSERT OR IGNORE INTO conversation_batches
                (batch_id, origin_key, context_json, role_instruction, state, revision, created_at,
                 contributions_json) VALUES (?, ?, '{}', '', 'ready', 1, ?, '{}')""",
                (batch_id, self.context.key, at.isoformat()))
            connection.execute("""INSERT INTO conversation_parts
                (part_id, batch_id, sequence, text, payload_hash, state, receipt_ref, delivered_at)
                VALUES (?, ?, 1, ?, ?, 'delivered', ?, ?)""",
                (part_id, batch_id, text, "hash-" + part_id, receipt, at.isoformat()))
            connection.execute("""INSERT INTO conversation_delivery_receipts
                (part_id, receipt_ref, receipt_json, observed_at) VALUES (?, ?, '{}', ?)""",
                (part_id, receipt, at.isoformat()))
            connection.execute("""INSERT INTO conversation_sent_history
                (part_id, batch_id, origin_key, delivered_at, receipt_ref) VALUES (?, ?, ?, ?, ?)""",
                (part_id, batch_id, self.context.key, at.isoformat(), receipt))
        return part_id

    def owner(self):
        return owner_key(self.context)

    def speech(self):
        return self.participation.speech.load(self.owner())

    def prime(self, **values):
        """Write one explicit ledger state, as a previous confirmed act would have."""
        with self.runtime.transaction() as connection:
            self.participation.speech.persist(connection, self.owner(), {**self.speech(), **values})

    def rows(self, table):
        return self.runtime.read_one("SELECT COUNT(*) FROM " + table, ())[0]

    def metadata(self):
        return {row["key"]: json.loads(row["value"]) for row in self.runtime.read_all(
            "SELECT key, value FROM runtime_metadata WHERE key LIKE ?", (PREFIX + "%",))}


class RepeatFollowTests(GroupRhythmFixture):
    def test_signature_and_burst_stay_inside_their_declared_bounds(self):
        for text in ("[图片]", "[图片 1]", "【语音】", "[合并转发 2]", "", "   ", "x" * 31):
            self.assertEqual(repeat_signature(text), "", text)
        self.assertEqual(clean_group_text("哈哈 [图片 1]"), "哈哈")
        self.assertEqual(repeat_signature("哈哈 [图片 1]"), "哈哈")
        self.assertEqual(repeat_signature("[提及机器人] 哈哈！"), "哈哈")
        self.assertEqual(repeat_signature("  哈哈  哈  "), "哈哈 哈")
        items = burst_history("哈哈", count=3)
        burst = repeat_burst("哈哈", items, at=TURN, window_seconds=120)
        self.assertEqual((burst["count"], burst["distinct"]), (3, 3))
        # Outside the declared window the same messages no longer accumulate.
        self.assertIsNone(repeat_burst("哈哈", items, at=TURN + timedelta(seconds=200), window_seconds=120))
        # The role's own copy is its act, never part of the members' burst.
        bot = (*items, {"kind": "bot", "speaker_id": "", "received_at": TURN.isoformat(), "text": "哈哈"})
        self.assertEqual(repeat_burst("哈哈", bot, at=TURN, window_seconds=120)["count"], 3)
        four = repeat_burst("哈哈", burst_history("哈哈", count=4), at=TURN, window_seconds=120)
        self.assertEqual((four["count"], four["distinct"]), (4, 4))

    def test_media_placeholders_do_not_enter_group_expression_or_moments(self):
        placeholders = burst_history("[图片 1]", count=4)
        self.assertEqual(moment_candidates(placeholders, TURN), ())
        self.assertEqual(fold_mood(None, placeholders, TURN)["message_count"], 0)
        self.assertEqual(joke_guard(placeholders, TURN)["objections"], 0)
        self.assertEqual(moment_portrait(placeholders, "200"), {})
        self.configure(enable_group_interjection=True)
        turn = self.turn(["[图片 1]"])
        self.assertIsNone(turn["act"])

    def test_nightly_cleanup_removes_legacy_placeholder_moments_and_repeat_signatures(self):
        owner = self.owner()
        with self.runtime.transaction() as connection:
            self.participation.records.write(connection, owner, "moments", {"moments": [
                {"hash": "old-image", "text": "[图片 1]", "at": TURN.isoformat(), "score": 2,
                 "reasons": ["burst"], "created_at": TURN.isoformat(), "expires_at": NOW.isoformat()},
                {"hash": "old-mixed", "text": "哈哈 [图片 1]", "at": TURN.isoformat(), "score": 2,
                 "reasons": ["spark"], "created_at": TURN.isoformat(), "expires_at": NOW.isoformat()}],
                "updated_at": NOW.isoformat()})
            self.participation.records.write(connection, owner, "mood", {"mood_scores": {
                "tease": 10, "banter": 0, "serious": 0, "tension": 0, "confession": 0, "dead_silence": 2},
                "top_mood": "tease", "social_tension": 3.8, "updated_at": NOW.isoformat(),
                "message_count": 1, "processed_keys": []})
            self.participation.records.write(connection, owner, "speech", {"repeat": {
                "signature": "[图片 1]", "acts": 2, "last_act_at": NOW.isoformat()},
                "pending": {"kind": REPEAT_FOLLOW, "signature": "[图片 1]", "batch_id": "old", "at": NOW.isoformat()}})
        self.assertEqual(self.participation.advance_reflection(), 3)
        self.assertEqual(self.participation.advance_reflection(), 0)
        moments = self.participation.records.read(owner, "moments")["moments"]
        self.assertEqual([item["text"] for item in moments], ["哈哈"])
        mood = self.participation.records.read(owner, "mood")
        self.assertEqual(mood["mood_scores"]["dead_silence"], 0)
        self.assertEqual(mood["top_mood"], "tease")
        self.assertEqual(mood["message_count"], 0)
        speech = self.participation.records.read(owner, "speech")
        self.assertEqual(speech["repeat"]["signature"], "")
        self.assertEqual(speech["repeat"]["acts"], 0)
        self.assertIsNone(speech["pending"])

    def test_the_reference_appears_only_for_a_real_burst(self):
        turn = self.turn(["哈哈"], recent=burst_history("哈哈", count=3))
        self.assertIn("群聊复读参考", turn["hints"])
        self.assertIn("参与跟读时只原样发送这一句", turn["hints"])
        self.assertEqual(turn["act"], REPEAT_FOLLOW)
        self.assertEqual(turn["act_signature"], "哈哈")
        for texts, recent in ((["哈哈"], burst_history("哈哈", count=1)),
                              (["[图片]"], burst_history("[图片]", count=4)),
                              (["这一句话明显超过三十个字符所以不可能成为复读的签名"], ())):
            with self.subTest(texts=texts):
                quiet = self.turn(texts, recent=recent)
                self.assertNotIn("群聊复读参考", quiet["hints"])
                self.assertIsNone(quiet["act"])
        self.configure(enable_group_repeat_follow=False)
        self.assertNotIn("群聊复读参考", self.turn(["哈哈"], recent=burst_history("哈哈", count=3))["hints"])
        # One member sending four copies counts in the counting mode only.
        self.configure(enable_group_repeat_follow=True, group_repeat_count_distinct_users_only=True)
        self.assertNotIn("群聊复读参考", self.turn(["哈哈"], recent=burst_history("哈哈", count=3, step=2))["hints"])
        self.configure(group_repeat_count_distinct_users_only=False)
        self.assertIn("群聊复读参考", self.turn(["哈哈"], recent=burst_history("哈哈", count=3, step=2))["hints"])

    def test_joining_once_escalates_to_stopping_the_repeat(self):
        first = self.turn(["哈哈"], recent=burst_at(TURN), batch="batch-join")
        self.assertEqual(first["act"], REPEAT_FOLLOW)
        self.participation._record(self.context, "batch-join", replied=True)
        self.assertEqual(self.speech()["pending"]["kind"], REPEAT_FOLLOW)
        self.assertEqual(self.speech()["used_today"], 0)  # a decision is not yet a fact
        self.confirm("batch-join", text="哈哈")
        # The next repeat arrives while the joined burst is still running.
        second_at = NOW + timedelta(seconds=60)
        second = self.turn(["哈哈"], recent=burst_at(second_at), at=second_at, batch="batch-stop")
        self.assertIn("参与打断时只发送管理员配置的打断语", second["hints"])
        self.assertIn("禁止复读", second["hints"])
        self.assertEqual(second["act"], REPEAT_INTERRUPT)
        self.participation._record(self.context, "batch-stop", replied=False)
        ledger = self.speech()
        self.assertEqual((ledger["used_today"], ledger["repeat"]["acts"]), (1, 1))

    def test_cooldown_daily_budget_and_tendencies_bound_the_next_burst(self):
        self.prime(day="2026-09-27", used_today=1, last_act_at=(NOW - timedelta(minutes=1)).isoformat(),
                   repeat={"signature": "别的", "acts": 1, "last_act_at": (NOW - timedelta(minutes=1)).isoformat()})
        early = NOW + timedelta(minutes=2)
        in_cooldown = self.turn(["哈哈"], recent=burst_at(early), at=early)
        self.assertNotIn("群聊复读参考", in_cooldown["hints"])
        self.assertIsNone(in_cooldown["act"])
        # Past the interval the rule runs again, and the configured tendencies decide the action.
        self.configure(group_interject_min_interval_minutes=0, group_repeat_follow_probability=0.05,
                       group_repeat_interrupt_probability=0.4)
        late = NOW + timedelta(minutes=200)
        preferred = self.turn(["哈哈"], recent=burst_at(late), at=late)
        self.assertIn("参与打断时只发送管理员配置的打断语", preferred["hints"])
        self.assertEqual(preferred["act"], REPEAT_INTERRUPT)
        # The shared V1 daily budget closes rememberable bursts as well.
        self.configure(group_interject_max_daily=1)
        self.assertNotIn("群聊复读参考", self.turn(["哈哈"], recent=burst_at(late), at=late)["hints"])

    def test_registered_bounds_and_the_reader_refuse_unsupported_values(self):
        fields = {field.field_id: field for field in configuration_fields()}
        declared = {field.field_id.removeprefix(CONFIG_GROUP + "."): (field.minimum, field.maximum)
                    for field in fields.values()}
        for name, bounds in CONFIG_LIMITS.items():
            self.assertEqual(declared[name], bounds)
        for name, bad in (("group_repeat_trigger_threshold", 2), ("group_repeat_window_seconds", 5),
                          ("group_interject_max_daily", 21), ("group_repeat_follow_probability", 1.5),
                          ("group_interject_feedback_window_seconds", 30)):
            with self.subTest(name=name), self.assertRaises(Exception):
                fields[CONFIG_GROUP + "." + name].validate(bad)
        with self.assertRaises(Exception):
            self.configure(group_repeat_interrupt_text="x" * 81)
        # A value written outside the owner is still refused by its consumer.
        self.configure(group_repeat_interrupt_text="正常打断语")
        with self.runtime.transaction() as connection:
            connection.execute("UPDATE configuration_values SET value_json = ? WHERE target_key = ? AND field_id = ?",
                (json.dumps("x" * 81), self.target().key, CONFIG_GROUP + ".group_repeat_interrupt_text"))
        with self.assertRaises(Exception):
            self.turn(["在吗"])


class InterjectionTests(GroupRhythmFixture):
    def test_the_switch_interval_daily_cap_and_feedback_follow_the_ledger(self):
        quiet = self.turn(["今天天气不错"])
        self.assertNotIn("群聊主动插话参考", quiet["hints"])
        self.assertIsNone(quiet["act"])
        self.configure(enable_group_interjection=True)
        first = self.turn(["今天天气不错"], batch="batch-interject")
        self.assertIn("额度剩余 2/2", first["hints"])
        self.assertIn("尚无可参考的自主发言", first["hints"])
        self.assertIn("最小间隔参考 180 分钟", first["hints"])
        self.assertEqual(first["act"], INTERJECTION)
        self.participation._record(self.context, "batch-interject", replied=True)
        self.confirm("batch-interject", text="我说一句")
        # A confirmed act spends one allowance and starts the interval.
        later = self.turn(["今天天气不错"], at=NOW + timedelta(minutes=200), batch="batch-later")
        self.assertIn("额度剩余 1/2", later["hints"])
        self.assertIn("约 200 分钟", later["hints"])
        too_soon = self.turn(["今天天气不错"], at=NOW + timedelta(minutes=179))
        self.assertIn("群聊主动插话参考", too_soon["hints"])
        self.assertIn("太近", too_soon["hints"])
        self.configure(group_interject_max_daily=0)
        self.assertIn("额度为 0", self.turn(["今天天气不错"], batch="batch-later")["hints"])
        self.participation._record(self.context, "batch-later", replied=False)
        self.assertEqual(self.speech()["used_today"], 1)

    def test_an_addressed_turn_is_not_self_initiated_speech(self):
        self.configure(enable_group_interjection=True)
        for texts, settings in ((["[提及机器人] 你在吗"], None), (["小星帮我看下"], NAMED),
                                (["有人在吗"], {"group_wakeup_direct_words": '["有人在吗"]'})):
            with self.subTest(texts=texts):
                addressed = self.turn(texts, settings=settings, batch="batch-addressed")
                self.assertIn("群聊主动插话参考", addressed["hints"])
                self.assertIsNone(addressed["act"])
        self.participation._record(self.context, "batch-addressed", replied=True)
        self.assertIsNone(self.speech()["pending"])
        self.assertIsNone(self.speech()["awaiting"])

    def test_feedback_learning_moves_the_weight_both_ways(self):
        self.configure(enable_group_interjection=True)
        self.turn(["今天天气不错"], batch="batch-feedback")
        self.participation._record(self.context, "batch-feedback", replied=True)
        self.confirm("batch-feedback", text="我说一句")
        self.turn(["今天天气不错"], at=NOW + timedelta(minutes=1), batch="batch-settle")
        self.participation._record(self.context, "batch-settle", replied=False)
        answered = self.turn(["今天天气不错"], at=NOW + timedelta(minutes=2), settings=NAMED,
                             batch="batch-ignored",
                             recent=(member("小星在吗", "201", NOW + timedelta(seconds=30)),))
        self.assertIn("被接话/被无视学习权重为 0.85", answered["hints"])
        self.participation._record(self.context, "batch-ignored", replied=True)
        self.assertEqual(self.speech()["weight"], WEIGHT_START + ACKNOWLEDGED_STEP)
        self.confirm("batch-ignored", text="我再说一句")
        self.turn(["今天天气不错"], at=NOW + timedelta(minutes=3), batch="batch-settle-2")
        self.participation._record(self.context, "batch-settle-2", replied=False)
        # Nobody answers inside the window: the tendency drops instead of staying put.
        dropped = self.turn(["今天天气不错"], at=NOW + timedelta(minutes=30), batch="batch-dropped")
        self.assertIn("被接话/被无视学习权重为 0.65", dropped["hints"])
        self.participation._record(self.context, "batch-dropped", replied=False)
        self.assertAlmostEqual(self.speech()["weight"], WEIGHT_START + ACKNOWLEDGED_STEP - IGNORED_STEP, places=6)
        self.assertLess(self.speech()["weight"], WEIGHT_START)
        # The weight stays inside its declared floor, and the switch really gates the learning.
        self.prime(weight=WEIGHT_MIN, awaiting={"kind": INTERJECTION, "at": NOW.isoformat()})
        self.turn(["今天天气不错"], at=NOW + timedelta(minutes=60), settings=NAMED, batch="batch-floor",
                  recent=(member("小星在吗", "202", NOW + timedelta(seconds=10)),))
        self.participation._record(self.context, "batch-floor", replied=False)
        self.assertAlmostEqual(self.speech()["weight"], WEIGHT_MIN + ACKNOWLEDGED_STEP, places=6)
        self.assertLessEqual(self.speech()["weight"], WEIGHT_MAX)
        self.configure(enable_group_interjection_feedback=False)
        self.assertNotIn("学习权重", self.turn(["今天天气不错"], batch="batch-floor")["hints"])

    def test_unconfirmed_and_stale_decisions_are_never_counted(self):
        self.configure(enable_group_interjection=True)
        self.turn(["今天天气不错"], batch="batch-unconfirmed")
        self.participation._record(self.context, "batch-unconfirmed", replied=True)
        # Inside the window an outcome that is still unknown stays unresolved...
        self.turn(["今天天气不错"], at=NOW + timedelta(seconds=60), batch="batch-unknown")
        self.participation._record(self.context, "batch-unknown", replied=False)
        self.assertEqual(self.speech()["pending"]["batch_id"], "batch-unconfirmed")
        self.assertEqual(self.speech()["used_today"], 0)
        # ...and a decision that never reached the group is dropped, not counted.
        self.turn(["今天天气不错"], at=NOW + timedelta(minutes=40), batch="batch-stale")
        self.participation._record(self.context, "batch-stale", replied=False)
        self.assertIsNone(self.speech()["pending"])
        self.assertEqual(self.speech()["used_today"], 0)
        self.assertEqual(self.speech()["weight"], WEIGHT_START)

    def test_reading_sends_nothing_and_recording_is_idempotent(self):
        self.configure(enable_group_interjection=True)
        before = {table: self.rows(table) for table in WATCHED}
        first = self.turn(["哈哈"], recent=burst_history("哈哈", count=3), batch="batch-record")
        self.assertEqual({table: self.rows(table) for table in WATCHED}, before)
        self.assertEqual(first["hints"], self.turn(["哈哈"], recent=burst_history("哈哈", count=3))["hints"])
        self.participation._record(self.context, "batch-record", replied=True)
        self.assertEqual(self.speech()["pending"]["kind"], REPEAT_FOLLOW)
        self.assertTrue(all(key.startswith(PREFIX) for key in self.metadata()))
        self.participation._record(self.context, "batch-record", replied=True)
        self.assertEqual({table: self.rows(table) for table in WATCHED}, before)
        self.assertEqual(self.speech()["recorded_batch"], "batch-record")
        self.assertTrue(all(key.startswith(PREFIX) for key in self.metadata()))
        self.participation._record(group_context(PRIVATE), "batch-private", replied=True)
        self.assertEqual(self.participation.catalog_for(group_context(PRIVATE)), ())
        self.assertNotIn("batch-private", json.dumps(self.metadata()))


class TopicThreadTests(GroupRhythmFixture):
    def test_signatures_ignore_media_and_merge_related_chinese_topic_lines(self):
        self.assertEqual(topic_signature("[图片 1]"), "")
        self.assertEqual(topic_signature("嗯？"), "")
        self.assertTrue(topic_signatures_similar(
            topic_signature("今天想聊下烤肉配什么酱"), topic_signature("烤肉配的蘸料我喜欢花生酱")))
        self.assertFalse(topic_signatures_similar(
            topic_signature("烤肉配什么酱"), topic_signature("周末准备去看电影")))
        self.assertFalse(topic_signatures_similar(
            topic_signature("我今天想看电影"), topic_signature("我今天想买衣服")))

    def test_threads_expire_dedupe_and_derive_participants_without_storing_ids(self):
        first_at = TURN - timedelta(minutes=2)
        second_at = TURN - timedelta(minutes=1)
        bot_at = TURN - timedelta(seconds=30)
        items = (
            {"kind": "member", "speaker_id": "member-a", "received_at": first_at.isoformat(),
             "text": "今天想聊下烤肉配什么酱"},
            {"kind": "member", "speaker_id": "member-b", "received_at": second_at.isoformat(),
             "text": "烤肉配的蘸料我喜欢花生酱"},
            {"kind": "bot", "speaker_id": "", "received_at": bot_at.isoformat(), "text": "花生酱也不错"},
        )
        record, facts = fold_topic_threads(None, items, TURN)

        self.assertEqual(len(record["threads"]), 1)
        self.assertEqual(record["threads"][0]["message_count"], 2)
        self.assertEqual(facts[0]["participant_count"], 2)
        self.assertTrue(facts[0]["bot_joined"])
        self.assertNotIn("member-a", json.dumps(record))
        self.assertNotIn("member-b", json.dumps(record))

        repeated, _ = fold_topic_threads(record, items, TURN + timedelta(seconds=1))
        self.assertEqual(repeated["threads"][0]["message_count"], 2)
        expired, expired_facts = fold_topic_threads(repeated, (), TURN + timedelta(minutes=91))
        self.assertEqual(expired["threads"], [])
        self.assertEqual(expired_facts, ())

    def test_topic_lines_are_window_scoped_prompt_material_and_can_be_disabled(self):
        prior = member("今天想聊下烤肉配什么酱", "201", TURN - timedelta(minutes=1))
        turn = self.turn(["烤肉配的蘸料我喜欢花生酱"], recent=(prior,))
        self.assertIn("本群近 90 分钟的话题线索", turn["hints"])
        self.assertIn("烤肉", turn["hints"])
        self.assertEqual(turn["observation"][TOPIC_KIND]["threads"][0]["message_count"], 2)

        self.configure(enable_group_topic_threads=False)
        disabled = self.turn(["烤肉配的蘸料我喜欢花生酱"], recent=(prior,), batch="batch-topic-off")
        self.assertNotIn("本群近 90 分钟的话题线索", disabled["hints"])
        self.assertNotIn(TOPIC_KIND, disabled["observation"])


if __name__ == "__main__":
    unittest.main()

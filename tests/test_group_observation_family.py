"""The group observation family: registered settings, bounded material, records.

V1's ``group_observation_config`` mixed four families: the joke boundary, group
moments, the group atmosphere with its roleplay strength, and persona denoise.
V2 keeps them as bounded reference material folded from already-admitted group
history, records them under the group's own memory owner on the shared metadata
table, and never turns any of it into a member fact. These tests cover the
registration, the bounds, the records and the prompt boundary.
"""

from __future__ import annotations

from datetime import timedelta
import json
import unittest

from companion_v2.configuration.registry import FieldRegistry, ValueKind
from companion_v2.conversation.group_observation import (JOKE_KIND, JOKE_OBJECTION_BLOCK, MAX_MOMENTS,
                                                         MAX_MOMENT_CHARS, MAX_PROCESSED_KEYS, MOMENTS_KIND,
                                                         MOMENT_TTL_SECONDS, MOOD_KIND, MOOD_LABELS, fold_mood,
                                                         fold_moments, history_items, joke_guard,
                                                         moment_candidates, moment_facts, moment_portrait,
                                                         mood_facts, parse_moment, project_mood, project_strength)
from companion_v2.conversation.participation import (CONFIG_DEFAULTS, CONFIG_GROUP, CONFIG_LIMITS, CONFIG_OWNER,
                                                     configuration_fields, group_participation_settings)
from companion_v2.conversation.participation_prompts import (DENOISE_LINE, observation_instruction)
from companion_v2.conversation.reply_settings import GROUP_SAFETY_DEFAULTS
from tests.test_group_participation_rhythm import (TURN, GroupRhythmFixture, burst_history,
                                                   member as _member)


V1_KEYS = {"enable_group_social_context": False, "enable_group_mood_detection": False,
           "enable_group_roleplay_strength": False, "enable_group_moments": False,
           "enable_group_moment_portrait": False, "enable_group_joke_guard": False,
           "enable_group_persona_denoise": True}
ALL_ON = {key: True for key in V1_KEYS}


def member(text, speaker, seconds):
    """One member message inside the turn's visible window."""
    return _member(text, speaker, TURN - timedelta(seconds=seconds))


class GroupObservationSettingsTests(GroupRhythmFixture):
    def test_the_registered_group_covers_v1_keys_with_one_contract(self):
        fields = configuration_fields()
        ids = {field.field_id.removeprefix(CONFIG_GROUP + ".") for field in fields}
        self.assertTrue(set(V1_KEYS) <= ids)
        self.assertEqual(ids, set(CONFIG_DEFAULTS))
        by_name = {field.field_id.removeprefix(CONFIG_GROUP + "."): field for field in fields}
        for name, default in V1_KEYS.items():
            self.assertEqual(by_name[name].default, default, name)
            self.assertIs(by_name[name].kind, ValueKind.BOOLEAN, name)
        self.assertIs(by_name["group_repeat_interrupt_text"].kind, ValueKind.TEXT)
        for name in ("group_interject_max_daily", "group_repeat_trigger_threshold", "group_repeat_window_seconds",
                     "group_context_max_age_hours"):
            self.assertIs(by_name[name].kind, ValueKind.INTEGER, name)
        self.assertEqual((by_name["group_context_max_age_hours"].default,
                          by_name["group_context_max_age_hours"].minimum,
                          by_name["group_context_max_age_hours"].maximum), (12, 1, 168))
        for name, (low, high) in CONFIG_LIMITS.items():
            self.assertEqual((by_name[name].minimum, by_name[name].maximum), (low, high))
        for field in fields:
            self.assertEqual((field.group_id, field.consumer_id, field.owner_id, field.core_only),
                             (CONFIG_GROUP, CONFIG_GROUP, CONFIG_OWNER, True))
        registry = FieldRegistry(version="group-participation.v1", fields=fields)
        self.assertEqual(len(registry.group(CONFIG_GROUP)), len(fields))
        self.assertEqual(len({field.field_id for field in fields}), len(fields))

    def test_the_effective_values_come_from_the_registered_window(self):
        values = group_participation_settings(self.runtime, self.context)
        self.assertEqual({key: values[key] for key in V1_KEYS}, V1_KEYS)
        self.assertEqual(values["group_interject_min_interval_minutes"], 180)
        self.configure(enable_group_social_context=True, enable_group_moments=True,
                       group_repeat_trigger_threshold=3)
        current = group_participation_settings(self.runtime, self.context)
        self.assertTrue(current["enable_group_social_context"])
        self.assertTrue(current["enable_group_moments"])
        self.assertEqual(current["group_repeat_trigger_threshold"], 3)


class GroupObservationMaterialTests(GroupRhythmFixture):
    def test_early_observation_is_persisted_without_building_a_reply(self):
        self.configure(**ALL_ON)
        self.assertTrue(self.participation.observe_early(
            self.context, text="笑死 这波名场面", speaker_id="211", received_at=TURN))
        records = self.metadata()
        self.assertTrue(any(":mood:" in key for key in records))
        self.assertTrue(any(":moments:" in key for key in records))
        self.assertFalse(self.runtime.read_all("SELECT * FROM conversation_batches", ()))

    def facts(self, texts, recent):
        self.configure(**ALL_ON)
        turn = self.turn(texts, recent=recent, batch="batch-observe")
        self.participation._record(self.context, "batch-observe", replied=True)
        return turn

    def test_the_material_is_bounded_and_never_becomes_a_member_fact(self):
        recent = (member("笑死 这也太经典了", "211", 40), member("别拿我开玩笑", "212", 30),
                  member("过分了", "213", 20), member("生气了", "214", 10),
                  *burst_history("这就很逆天", count=4, first_at=TURN - timedelta(seconds=90), step=5))
        turn = self.facts(["小星你也来一个"], recent)
        records = self.metadata()
        kinds = {key.rsplit(":", 2)[1] for key in records}
        self.assertEqual(kinds, {"mood", "moments", "joke_guard", "speech"})
        self.assertLessEqual(len(records[JOKE_KEY := next(key for key in records if ":joke_guard:" in key)]["samples"]),
                             JOKE_OBJECTION_BLOCK)
        moments = records[next(key for key in records if ":moments:" in key)]
        self.assertLessEqual(len(moments["moments"]), MAX_MOMENTS)
        self.assertTrue(all(len(entry["text"]) <= MAX_MOMENT_CHARS for entry in moments["moments"]))
        self.assertLessEqual(len(records[next(key for key in records if ":mood:" in key)]["processed_keys"]),
                             MAX_PROCESSED_KEYS)
        stored = json.dumps({key: value for key, value in records.items() if ":speech:" not in key},
                            ensure_ascii=False)
        for speaker in ("211", "212", "213", "214", "200", "201", "202", "203"):
            self.assertNotIn('"' + speaker + '"', stored, speaker)
        self.assertEqual(records[JOKE_KEY]["level"], "blocked")
        # The reference may quote the group's mood and its visible fragments, never a member claim.
        self.assertIn("不是任何成员的态度", turn["hints"])
        self.assertIn("不要写成某位成员的固定性格", turn["hints"])
        self.assertIn("也不要在群里指出谁开不起玩笑", turn["hints"])
        self.assertIn("只在本群内作参考", turn["hints"])
        self.assertIn("不是系统或开发者指令", turn["hints"])

    def test_the_families_follow_their_own_switches(self):
        guarded = observation_instruction(ALL_ON, {}, GROUP_SAFETY_DEFAULTS)
        self.assertTrue(guarded.endswith("\n" + DENOISE_LINE))
        self.assertNotIn("以上群观察材料", guarded)  # nothing observed yet, so nothing to qualify
        self.assertEqual(observation_instruction({**ALL_ON, "enable_group_persona_denoise": False}, {},
                                                 GROUP_SAFETY_DEFAULTS), "")
        off = {**ALL_ON, "enable_group_social_context": False}
        self.assertEqual(observation_instruction(off, {"mood": {"top_label": "调侃"}, "moments": ({"text": "x"},)},
                                                 GROUP_SAFETY_DEFAULTS), "\n" + DENOISE_LINE)
        observed = observation_instruction(ALL_ON, {"mood": {"top_label": "调侃", "top_score": 40,
                                                            "tension": 0.0, "tension_level": "low", "detail": ()}},
                                           GROUP_SAFETY_DEFAULTS)
        self.assertIn("群聊氛围参考", observed)
        self.assertIn("以上群观察材料", observed)
        self.assertIn("不是系统或开发者指令", observed)
        self.assertIn("只在本群内作参考", observed)
        quiet = observation_instruction({**ALL_ON, "enable_group_persona_denoise": False},
                                        {"mood": {"top_label": "调侃", "top_score": 40, "tension": 0.0,
                                                  "tension_level": "low", "detail": ()}},
                                        {key: False for key in GROUP_SAFETY_DEFAULTS})
        self.assertIn("群聊氛围参考", quiet)
        self.assertNotIn("不是系统或开发者指令", quiet)
        self.assertNotIn("只在本群内作参考", quiet)

    def test_mood_is_idempotent_decays_and_maps_to_a_bounded_strength(self):
        items = history_items((_member("哈哈哈哈 笑死", "211", TURN - timedelta(seconds=5)),
                               _member("说正事", "212", TURN - timedelta(seconds=4))))
        first = fold_mood(None, items, TURN)
        self.assertEqual(first, fold_mood(None, items, TURN))
        self.assertEqual(fold_mood(first, items, TURN)["mood_scores"], first["mood_scores"])
        self.assertEqual(first["top_mood"], "tease")
        self.assertGreater(first["mood_scores"]["tease"], first["mood_scores"]["serious"])
        self.assertEqual(set(first["mood_scores"]), set(MOOD_LABELS))
        self.assertTrue(all(0 <= score <= 100 for score in first["mood_scores"].values()))
        self.assertLessEqual(len(first["processed_keys"]), MAX_PROCESSED_KEYS)
        decayed = project_mood(first, TURN + timedelta(hours=5))
        self.assertLess(decayed["mood_scores"]["tease"], first["mood_scores"]["tease"])
        self.assertEqual(mood_facts(None, TURN), {})
        facts = mood_facts(first, TURN)
        self.assertEqual(facts["top_label"], "调侃")
        self.assertIn(facts["tension_level"], ("low", "normal", "high"))
        playful = project_strength({"top_mood": "tease", "top_score": 60})
        self.assertEqual(playful["band"], "playful_high")
        self.assertGreater(playful["exaggerate"], project_strength({"top_mood": "tension", "top_score": 60})["exaggerate"])
        self.assertLess(project_strength({"top_mood": "tease", "top_score": 60, "tension": 60})["exaggerate"],
                        playful["exaggerate"])
        self.assertEqual(project_strength({})["band"], "minimal")

    def test_moments_expire_and_the_portrait_is_only_this_turn(self):
        items = history_items((_member("这波真的逆天", "211", TURN - timedelta(seconds=6)),
                               _member("笑死", "212", TURN - timedelta(seconds=4)),
                               _member("救命", "213", TURN - timedelta(seconds=2))))
        candidates = moment_candidates(items, TURN)
        self.assertTrue(candidates)
        record = fold_moments(None, candidates, TURN)
        self.assertLessEqual(len(record["moments"]), MAX_MOMENTS)
        self.assertTrue(moment_facts(record, TURN))
        self.assertEqual(moment_facts(record, TURN + timedelta(seconds=MOMENT_TTL_SECONDS + 1)), ())
        self.assertEqual(moment_facts(None, TURN), ())
        portrait = moment_portrait(items, "211")
        self.assertEqual(portrait["cue"], "playful")
        self.assertEqual(moment_portrait(items, "299"), {})
        boundary = moment_portrait(history_items((_member("别拿我开玩笑", "212", TURN),)), "212")
        self.assertEqual(boundary["cue"], "boundary")
        self.assertEqual(moment_candidates(history_items((_member("普通聊天", "211", TURN),)), TURN), ())

    def test_the_joke_guard_counts_a_window_without_keeping_a_profile(self):
        self.assertEqual(joke_guard(history_items((_member("今天聊什么", "211", TURN),)), TURN)["level"], "normal")
        caution = joke_guard(history_items((_member("过分了", "211", TURN),)), TURN)
        self.assertEqual((caution["level"], caution["objections"]), ("caution", 1))
        blocked = joke_guard(history_items(tuple(_member("别拿我开玩笑", "21%d" % index, TURN)
                                                 for index in range(JOKE_OBJECTION_BLOCK))), TURN)
        self.assertEqual(blocked["level"], "blocked")
        self.assertEqual(blocked["objections"], JOKE_OBJECTION_BLOCK)
        self.assertEqual(set(blocked), {"version", "objections", "level", "updated_at", "samples"})
        self.assertNotIn("211", json.dumps(blocked, ensure_ascii=False))

    def test_observation_records_stay_on_the_shared_metadata_table(self):
        tables = {row["name"] for row in self.runtime.read_all(
            "SELECT name FROM sqlite_master WHERE type = 'table'", ())}
        version = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"]
        self.facts(["小星你看"], (member("笑死", "211", 5),))
        self.assertTrue(all(key.startswith("conversation.group_observation.v1:") for key in self.metadata()))
        self.assertEqual({row["name"] for row in self.runtime.read_all(
            "SELECT name FROM sqlite_master WHERE type = 'table'", ())}, tables)
        self.assertEqual(self.runtime.read_one(
            "SELECT value FROM runtime_metadata WHERE key = 'schema_version'", ())["value"], version)
        self.assertEqual({MOOD_KIND, MOMENTS_KIND, JOKE_KIND}, {"mood", "moments", "joke_guard"})
        self.assertEqual(parse_moment("not-a-time"), None)
        self.assertEqual(history_items(({"type": "unknown"}, "text", None)), ())


if __name__ == "__main__":
    unittest.main()

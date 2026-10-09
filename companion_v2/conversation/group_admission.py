"""Model-free candidates before a group message opens a reply batch."""

from collections import deque
import json
import re

from companion_v2.execution.models import TaskError, stamp
from .group_observation import parse_moment
from .group_timing import clean_group_text, repeat_burst, repeat_signature
from .reply_settings import group_wakeup_settings
from .reset import batch_current, boundary


QUESTION = re.compile(r"[?？]|怎么|怎样|如何|为什么|为啥|咋办|怎么办|有没有|谁懂|谁知道|"
                      r"救命|求助|求教|请教|帮帮|帮忙|能不能|可以吗|是否|\b(?:how|why|help)\b", re.I)
FOLLOW_UP_SECONDS = 120
MAX_GROUPS = 128
MAX_OBSERVATIONS = 128
PREFIX = "conversation.group_admission.v1:"
REASONS = {"mention": "明确 @ 机器人", "native_wakeup": "命中宿主唤醒词",
           "quoted_reply": "引用机器人已确认发送的群消息", "active_follow_up": "当前成员补充正在处理的任务",
           "native_quote": "宿主识别到引用机器人消息", "mention_all": "宿主配置允许 @ 全体唤醒",
           "reply_follow_up": "当前成员接续机器人刚发出的回复", "direct_word": "命中配置的直接唤醒词或名称",
           "image_interest": "已开启图片唤醒", "question": "命中群聊问题或求助策略",
           "context_word": "命中配置的群聊相关词", "interest": "命中配置的兴趣词",
           "repeat": "本群复读达到配置阈值", "interjection": "命中已开启的自主插话线索",
           "cold_group": "命中配置的冷群接话策略", "role_choice": "原人格自主判断参与"}


class GroupReplyAdmission:
    def __init__(self, messages):
        self.messages, self.runtime = messages, messages.runtime
        self.observations = {}

    def _key(self, context):
        scope = context.scope
        return (scope.installation_id, scope.platform, scope.bot_id, scope.account_id, scope.native_scope_id,
                scope.session_id, context.role_binding.role, getattr(context.role_binding, "revision", 0))

    def reset_window(self, window):
        route = (window.installation_id, window.platform, window.bot_id, window.account_id,
                 window.native_scope_id, window.session_id)
        for key in tuple(self.observations):
            if key[:6] == route:
                del self.observations[key]

    def observe(self, context, *, text, speaker_id, received_at):
        reset = boundary(self.runtime, context.scope)
        if reset is not None and stamp(received_at) <= reset["reset_at"]:
            return
        key = self._key(context)
        if key not in self.observations:
            if len(self.observations) >= MAX_GROUPS:
                self.observations.pop(next(iter(self.observations)))
            self.observations[key] = deque(maxlen=MAX_OBSERVATIONS)
        item = {"kind": "member", "speaker_id": speaker_id,
                "received_at": stamp(received_at), "text": clean_group_text(text)}
        if item not in self.observations[key]:
            self.observations[key].append(item)

    def candidate(self, context, *, text, instruction, at, settings, participation,
                  mentioned=False, native_wakeup=False, mentions_others=False, reply_ids=(),
                  mentions_all=False, quoted_bot=False, has_image=False, persona_name=""):
        self.messages.group_context.authorize(context, self.messages.tasks.now())
        wakeup = group_wakeup_settings(settings)
        if mentioned:
            return "mention"
        if self._quoted_reply(context, reply_ids, instruction, at):
            return "quoted_reply"
        if quoted_bot:
            return "native_quote"
        if native_wakeup:
            return "mention_all" if mentions_all else "native_wakeup"
        compact = clean_group_text(text)
        direct = list(wakeup["group_wakeup_direct_words"])
        if wakeup["group_wakeup_bot_name_enabled"]:
            direct.append(wakeup["group_wakeup_bot_name"] or persona_name)
        if context.actor.principal.native_account_id in wakeup["group_wakeup_primary_member_ids"]:
            direct.extend(wakeup["group_wakeup_owner_direct_words"])
        if (wakeup["group_wakeup_enabled"]
                and any(word and word.casefold() in compact.casefold() for word in direct)):
            return "direct_word"
        if mentions_others:
            return ""
        continuation = self._continuation(context, instruction, at)
        if continuation:
            return continuation
        if not wakeup["group_wakeup_enabled"]:
            return ""
        if (wakeup["group_wakeup_image_enabled"] and wakeup["group_wakeup_image_weight"] > 0
                and has_image):
            return "image_interest"
        if not compact or not any(char.isalnum() for char in compact):
            return ""
        # These are candidates, not compulsory replies or semantic scores. The
        # existing participation prompt still judges intent, thresholds and timing.
        if wakeup["group_wakeup_question_enabled"] and QUESTION.search(compact):
            return "question"
        if any(word.casefold() in compact.casefold() for word in wakeup["group_wakeup_context_words"]):
            return "context_word"
        if (wakeup["group_wakeup_interest_probability"] > 0
                and any(word.casefold() in compact.casefold() for word in wakeup["group_wakeup_interest_keywords"])):
            return "interest"
        items = list(self.observations.get(self._key(context), ()))
        current = {"kind": "member", "speaker_id": context.actor.principal.native_account_id,
                   "received_at": stamp(at), "text": compact}
        if current not in items:
            items.append(current)
        if participation["enable_group_repeat_follow"]:
            burst = repeat_burst(repeat_signature(compact), items, at=at,
                                 window_seconds=participation["group_repeat_window_seconds"])
            count = (burst["distinct"] if participation["group_repeat_count_distinct_users_only"]
                     else burst["count"]) if burst else 0
            if (count >= participation["group_repeat_trigger_threshold"]
                    and max(participation["group_repeat_follow_probability"],
                            participation["group_repeat_interrupt_probability"]) > 0):
                return "repeat"
        if participation["enable_group_interjection"]:
            from .group_interjection import openings
            signals = openings(compact)
            if "refusal" not in signals and any(signal in signals for signal in ("open_question", "joke_reaction")):
                return "interjection"
        if wakeup["group_wakeup_cold_group_enabled"]:
            previous = [parse_moment(item["received_at"]) for item in items if item != current]
            previous = [when for when in previous if when is not None and when < at]
            if previous and (at - max(previous)).total_seconds() >= wakeup["group_wakeup_cold_group_idle_minutes"] * 60:
                return "cold_group"
        return ""

    def record(self, context, batch_id, *, reason, mentioned):
        key = PREFIX + batch_id
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT value FROM runtime_metadata WHERE key = ?", (key,)).fetchone()
            saved = json.loads(row["value"]) if row else {"context_key": context.key, "reasons": [], "mentioned": False}
            if saved["context_key"] != context.key:
                raise TaskError("group_admission_changed", "reply admission belongs to another group turn")
            saved["mentioned"] = saved["mentioned"] or mentioned
            if reason in REASONS and reason not in saved["reasons"]:
                saved["reasons"].append(reason)
            connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, json.dumps(saved, ensure_ascii=False, sort_keys=True)))

    def recorded(self, context, batch_id):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (PREFIX + batch_id,))
        saved = json.loads(row["value"]) if row else None
        return saved if saved is not None and saved.get("context_key") == context.key else None

    def mark_logged(self, context, batch_id, stage):
        with self.runtime.transaction() as connection:
            saved = self.recorded(context, batch_id)
            if saved is None:
                return True
            stages = saved.setdefault("logged_stages", [])
            if stage in stages:
                return False
            stages.append(stage)
            connection.execute("UPDATE runtime_metadata SET value = ? WHERE key = ?",
                               (json.dumps(saved, ensure_ascii=False, sort_keys=True), PREFIX + batch_id))
            return True

    def _continuation(self, context, instruction, at):
        row = self.runtime.read_one("""SELECT b.*, f.state AS flow_state, f.deadline_at
            FROM conversation_flows f JOIN conversation_batches b ON b.batch_id = f.batch_id
            WHERE f.route_key = ? ORDER BY f.sequence DESC LIMIT 1""", (context.scope.key,))
        if (row is None or row["origin_key"] != context.key or row["role_instruction"] != instruction
                or row["state"] in ("cancelled", "invalidated")
                or not batch_current(self.runtime, row["batch_id"], context.scope)):
            return ""
        if row["flow_state"] in ("collecting", "generating", "delivering"):
            deadline = parse_moment(row["deadline_at"])
            return "active_follow_up" if deadline is not None and at < deadline else ""
        if row["flow_state"] != "complete":
            return ""
        receipt = self.runtime.read_one("""SELECT MAX(p.delivered_at) AS delivered_at
            FROM conversation_parts p JOIN conversation_sent_history h
                ON h.part_id = p.part_id AND h.batch_id = p.batch_id AND h.receipt_ref = p.receipt_ref
            JOIN conversation_delivery_receipts r ON r.part_id = p.part_id AND r.receipt_ref = p.receipt_ref
            WHERE p.batch_id = ? AND p.state = 'delivered' AND h.origin_key = ?""",
            (row["batch_id"], context.key))
        when = parse_moment(receipt["delivered_at"]) if receipt is not None else None
        if when is None or not 0 <= (at - when).total_seconds() <= FOLLOW_UP_SECONDS:
            return ""
        speaker = context.actor.principal.native_account_id
        if any(item["speaker_id"] != speaker and when < (parse_moment(item["received_at"]) or when) <= at
               for item in self.observations.get(self._key(context), ())):
            return ""
        return "reply_follow_up"

    def _quoted_reply(self, context, identifiers, instruction, at):
        if not identifiers:
            return False
        rows = self.runtime.read_all("""SELECT p.batch_id, p.delivered_at FROM conversation_parts p
            JOIN conversation_sent_history h
                ON h.part_id = p.part_id AND h.batch_id = p.batch_id AND h.receipt_ref = p.receipt_ref
            JOIN conversation_delivery_receipts r ON r.part_id = p.part_id AND r.receipt_ref = p.receipt_ref
            WHERE p.state = 'delivered' AND p.platform_ref IN ("""
            + ",".join("?" for _ in identifiers) + ") LIMIT 128", tuple(identifiers))
        for row in rows:
            when = parse_moment(row["delivered_at"])
            if when is None or when > at:
                continue
            try:
                self.messages.group_context.original(row["batch_id"], context, instruction, self.messages.tasks.now())
            except TaskError:
                continue
            return True
        return False

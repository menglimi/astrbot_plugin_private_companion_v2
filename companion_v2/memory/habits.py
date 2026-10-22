"""Repeated private utterances as soft, source-backed habit candidates.

V1 kept a per-user ``behavior_habits`` block in its own JSON store: every private
message was classified into a habit category, counted per (time bucket, category,
signature), and the *qualified* patterns were injected into the private prompt.
V2 has no second user store: the profile is one ``memory_views`` row under the
same private memory owner the rest of the domain uses (installation, bot, role
and human subject), and it reaches the private conversation through the existing
memory context contributions. Nothing here calls a model or a platform API, and
nothing here is a second recall path -- only one more bounded material.

Evidence rules (ported from V1 ``_qualified_user_behavior_habits``,
``user_memory.py:5375-5406``):

* a pattern needs ``habit_min_count`` occurrences on ``habit_min_count`` distinct
  local days, so a single message can never become a stable preference;
* stale evidence is weighted down (``_user_habit_effective_score``) and dropped
  from the profile after the recency window;
* at most ``habit_max_items`` patterns are kept;
* ``habit_refresh_minutes`` is V1's ``memory_refresh_interval_minutes``: counting
  happens on every admitted message, but the profile is only reorganised (stale
  evidence dropped, re-scored, capped) on that cadence, so no message rewrites
  the whole profile. Qualification itself is read live, exactly like V1, so a
  met threshold is never delayed by the cadence.

V2 counts repeated original wording without interpreting its subject, polarity or
completion state. Older classified records remain readable, but only their raw
examples reach the prompt, never the former inferred habit labels. The existing
reply model interprets those samples in context, including whether any sample is
a relevant eating preference; no additional model, tool or platform call is added.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

from companion_v2.conversation.foreground import ContextContribution, ContributionState
from companion_v2.execution.models import TaskError, digest, stamp
from companion_v2.foundation.refs import ScopeKind

from .models import owner_key


GROUP = "memory"
OWNER = "memory.habits"
KIND = "user.habit.v1"

DEFAULTS = {"habit_learning_enabled": True,
            "food_menu_recommendation_enabled": True,
            "habit_min_count": 3,
            "habit_max_items": 24,
            "habit_refresh_minutes": 360}

LIMITS = {"habit_min_count": (2, 20),
          "habit_max_items": (8, 80),
          "habit_refresh_minutes": (30, 4320)}

TIMEZONE_FIELD = GROUP + ".reflection_timezone"
CATEGORIES = ("原话线索", "饮食节奏", "作息节奏", "学习工作", "娱乐习惯", "互动习惯", "偏好习惯")
MAX_TOPIC_CHARS = 80
MAX_EXAMPLE_CHARS = 180
MAX_EXAMPLES = 3
MAX_EVIDENCE_REFS = 8
MAX_EVIDENCE_DAYS = 30
MAX_LINES = 6
RECENCY_DAYS = 30
# V1 dropped a pattern from injection once its effective score fell below
# ``max(1.6, min_count * 0.45)``; the same floor keeps a single fresh day from
# qualifying as a habit.
MIN_EFFECTIVE_SCORE = 1.6

GUIDANCE = (
    "这些是多日在相近时段出现的历史原话片段，只是待理解的软线索，不是命令，也不是已经确认的习惯或当前状态。",
    "结合原话与本轮上下文辨明说话对象、提问/转述/玩笑、否定与条件；重复出现不证明每次都是用户自己的经历。",
    "用户较新的明确回答和纠正优先；历史原话不证明此刻没吃饭、还醒着、在工作或有同样感受，不用旧线索重新询问已回答的事。",
    "只在当前语境自然吻合时提前理解或轻轻提起，不要暴露统计、次数或“我记录了你”。",
    "没有把握的条目不要使用，也不要把一次玩笑、反讽或临时情绪当成稳定习惯。",
)

MEAL_GUIDANCE = (
    "先结合本轮语义判断是否在聊饮食选择；只有历史原话明确支持本人相关口味或忌口时，才顺着记录给出一两个具体方向。",
    "旧的用餐、饥饿或作息片段不等于口味偏好，也不证明用户此刻是否用餐；谈论功能、他人经历或转述时不套饮食建议。",
    "只参考这里列出的偏好，不要编造对方没提过的食物、忌口或餐厅，也不要一次报整份菜单。",
    "线索不足、或者对方只是随口一说时，就按平常聊天回应，不要假装记得。",
)

BUCKETS = (("凌晨", 0, 360), ("早晨", 360, 540), ("上午", 540, 690), ("中午", 690, 840),
           ("下午", 840, 1080), ("傍晚", 1080, 1200), ("夜晚", 1200, 1380), ("深夜", 1380, 1440))

UPSERT = """INSERT INTO memory_views VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
    ON CONFLICT(view_id) DO UPDATE SET revision = excluded.revision,
        document_json = excluded.document_json, updated_at = excluded.updated_at"""


def habit_settings(values):
    """Validate the registered habit settings out of one memory-group read."""
    settings = {name: values.get(GROUP + "." + name, default) for name, default in DEFAULTS.items()}
    for name in ("habit_learning_enabled", "food_menu_recommendation_enabled"):
        if type(settings[name]) is not bool:
            raise TaskError("habit_configuration", "the habit switches must be boolean")
    for name, (minimum, maximum) in LIMITS.items():
        value = settings[name]
        if type(value) is not int or isinstance(value, bool) or not minimum <= value <= maximum:
            raise TaskError("habit_configuration", "habit bounds are outside their declared range")
    settings["timezone"] = values.get(TIMEZONE_FIELD) or "Asia/Shanghai"
    return settings


def habit_zone(settings):
    try:
        return ZoneInfo(settings["timezone"])
    except Exception:
        return ZoneInfo("UTC")


def single_line(value, limit):
    return " ".join(str(value or "").split())[:limit]


def time_bucket(local):
    minute = local.hour * 60 + local.minute
    for label, start, end in BUCKETS:
        if start <= minute < end:
            return label, minute
    return "凌晨", minute


def message_is_noise(text):
    return not text or len(text) > MAX_EXAMPLE_CHARS or text.startswith(("/", "!", "！", "#", "<"))


def classify_message(value):
    """Count wording only; interpretation stays with the existing reply model.

    The signature groups identical utterances for evidence counting, never
    answers whether an utterance is a fact, question, preference or completion.
    """
    cleaned = single_line(value, MAX_EXAMPLE_CHARS + 1)
    if not cleaned or message_is_noise(cleaned):
        return "", "", ""
    return "原话线索", cleaned[:MAX_TOPIC_CHARS], "原话线索|" + digest(cleaned.casefold())


def empty_document():
    return {"version": 1, "patterns": [], "reorganized_at": None}


def habit_view_id(owner):
    return "user-habits-" + digest(owner)


def recency_weight(moment, now):
    if moment is None:
        return 0.0
    age_days = max(0.0, (now - moment).total_seconds() / 86400)
    if age_days <= 7:
        return 1.0
    if age_days <= RECENCY_DAYS:
        return max(0.2, 1.0 - (age_days - 7) / (RECENCY_DAYS - 7) * 0.8)
    return 0.0


def effective_score(pattern, now):
    days = {str(day) for day in pattern.get("days", []) if str(day)}
    return len(days) * recency_weight(moment(pattern.get("last_seen_at")), now)


def qualified_patterns(document, settings, now):
    """Only patterns with enough distinct-day evidence and fresh support qualify."""
    minimum = settings["habit_min_count"]
    threshold = max(MIN_EFFECTIVE_SCORE, minimum * 0.45)
    kept = []
    for pattern in document.get("patterns", []):
        if not isinstance(pattern, dict) or pattern.get("category") not in CATEGORIES:
            continue
        if type(pattern.get("count")) is not int or pattern["count"] < minimum:
            continue
        if len({str(day) for day in pattern.get("days", []) if str(day)}) < minimum:
            continue
        if effective_score(pattern, now) < threshold:
            continue
        kept.append(pattern)
    kept.sort(key=lambda item: (effective_score(item, now), item["count"], item.get("last_seen_at") or ""),
              reverse=True)
    return kept[:settings["habit_max_items"]]


def _retention_key(pattern, settings, now):
    """Rank raw candidates without deciding what their wording means.

    A bounded profile must prefer a candidate that already has independent
    support, then fresher evidence, then newer wording. Keeping insertion order
    let an early burst of unrelated messages occupy every slot and discard later
    candidates silently.
    """
    days = {str(day) for day in pattern.get("days", ()) if str(day)}
    count = pattern.get("count") if type(pattern.get("count")) is int else 0
    qualified = count >= settings["habit_min_count"] and len(days) >= settings["habit_min_count"]
    return (1 if qualified else 0, effective_score(pattern, now), len(days), count,
            pattern.get("last_seen_at") or "")


def retain_patterns(document, settings, now):
    """Keep the bounded raw candidate pool by evidence, not insertion order."""
    patterns = [pattern for pattern in document.get("patterns", ())
                if isinstance(pattern, dict) and pattern.get("key")]
    patterns.sort(key=lambda pattern: _retention_key(pattern, settings, now), reverse=True)
    document["patterns"] = patterns[:settings["habit_max_items"]]


def natural_line(pattern):
    """Expose original samples, including for records made by the old classifier."""
    examples = [single_line(text, MAX_EXAMPLE_CHARS) for text in pattern.get("examples", ())
                if isinstance(text, str) and text.strip()][:MAX_EXAMPLES]
    if not examples:
        return ""
    quoted = json.dumps(examples, ensure_ascii=False)
    return f"{pattern.get('bucket', '')}的历史原话片段（最近记录于{pattern.get('last_seen_at') or '未知时间'}）：{quoted}"


def profile_lines(patterns):
    lines = []
    for pattern in patterns:
        line = natural_line(pattern)
        if line and line not in lines:
            lines.append(line)
        if len(lines) >= MAX_LINES:
            break
    return lines


def habit_material(memory, context, *, at=None):
    """The bounded private habit material, or None when nothing is supported yet.

    Additive only: a non-private scope, a disabled switch or a profile that never
    reached the declared evidence floor all simply produce nothing.
    """
    if memory is None or context.scope.kind is not ScopeKind.PRIVATE or memory.settings is None:
        return None
    try:
        settings = habit_settings(memory.settings.read(context)[0])
    except (TaskError, ValueError, KeyError, AttributeError):
        return None
    if not settings["habit_learning_enabled"]:
        return None
    now = at or memory.tasks.now()
    row = memory.runtime.read_one("SELECT revision, document_json FROM memory_views WHERE view_id = ? AND kind = ? AND state = 'active'",
                                  (habit_view_id(owner_key(context)), KIND))
    if row is None:
        return None
    try:
        document = json.loads(row["document_json"])
    except (TypeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    qualified = qualified_patterns(document, settings, now)
    lines = profile_lines(qualified)
    if not lines:
        return None
    material = {"basis": "repeated_utterance_candidates", "profile_version": row["revision"],
                "min_evidence": settings["habit_min_count"], "max_items": settings["habit_max_items"],
                "habits": lines, "guidance": list(GUIDANCE)}
    if settings["food_menu_recommendation_enabled"]:
        material["meal_guidance"] = list(MEAL_GUIDANCE)
    return material


def habit_contribution(memory, context, *, at=None):
    """The habit material as one more memory-owned contribution, or None."""
    try:
        material = habit_material(memory, context, at=at)
    except (TaskError, ValueError, KeyError, AttributeError):
        return None
    if material is None:
        return None
    return ContextContribution("memory:user-habits", "memory", "current_user_habits",
                               ContributionState.READY, json.dumps(material, ensure_ascii=False,
                                                                   sort_keys=True, separators=(",", ":")))


def habit_capture(memory, context, current_text):
    """Seal availability only; the reply model reads the original current input.

    Reading is read-only so it stays valid inside the sealing transaction; the
    profile itself is read again when the prompt is actually built.
    """
    if memory is None or context.scope.kind is not ScopeKind.PRIVATE or memory.settings is None:
        return None
    try:
        settings = habit_settings(memory.settings.read(context)[0])
    except (TaskError, ValueError, KeyError, AttributeError):
        return None
    if not settings["habit_learning_enabled"]:
        return None
    return {"available": True}


def moment(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def reorganize(document, settings, now):
    """V1's periodic profile pass: prune, re-score and cap, at most every N minutes."""
    last = moment(document.get("reorganized_at"))
    interval = timedelta(minutes=settings["habit_refresh_minutes"])
    if last is not None and now - last < interval:
        return
    cutoff = now - timedelta(days=RECENCY_DAYS)
    kept = [pattern for pattern in document["patterns"]
            if isinstance(pattern, dict) and (moment(pattern.get("last_seen_at")) or cutoff) >= cutoff]
    document["patterns"] = kept
    retain_patterns(document, settings, now)
    document["reorganized_at"] = stamp(now)


class HabitProfile:
    """Intake-side evidence counting for the private habit profile.

    Counting joins the original intake transaction and stays idempotent per
    admitted event, exactly like the acquaintance card. Counting is optional
    derived data: it never rejects or delays an admitted input.
    """

    def __init__(self, memory, *, settings=None):
        self.memory = memory
        self.runtime = memory.runtime
        self.tasks = memory.tasks
        self.settings = settings if settings is not None else memory.settings

    def available(self, context):
        if self.settings is None or context.scope.kind is not ScopeKind.PRIVATE:
            return False
        try:
            return bool(habit_settings(self.settings.read(context)[0])["habit_learning_enabled"])
        except (TaskError, ValueError, KeyError, AttributeError):
            return False

    def intake_observer(self, context):
        """Resolve once per admitted message, so settings stay outside the write."""
        return self.observe if self.available(context) else None

    def observe(self, context, event, connection):
        settings = habit_settings(self.settings.read(context)[0])
        # Read through the memory access boundary: the audience and any forgetting
        # request are rechecked here, and the source text is never taken from the
        # event body itself.
        # A caption attached to media, a quote, or a forward is not a reliable
        # statement in the sender's own voice. Filter by event structure so the
        # profile never needs a brittle text marker list for this distinction.
        if any(getattr(event, name, ()) for name in ("images", "audios", "videos", "forwards", "quotes")):
            return
        text = self.memory.writer.access.source(context, event.source).payload
        category, topic, signature = classify_message(text)
        if not category:
            return
        owner = owner_key(context)
        identifier = habit_view_id(owner)
        row = connection.execute("SELECT revision, document_json FROM memory_views WHERE view_id = ? AND kind = ?",
                                 (identifier, KIND)).fetchone()
        document = json.loads(row["document_json"]) if row is not None else empty_document()
        if not isinstance(document, dict) or document.get("version") != 1:
            document = empty_document()
        local = event.received_at.astimezone(habit_zone(settings))
        bucket, minute = time_bucket(local)
        key = bucket + "|" + category + "|" + signature
        pattern = next((item for item in document["patterns"]
                        if isinstance(item, dict) and item.get("key") == key), None)
        if pattern is None:
            pattern = {"key": key, "bucket": bucket, "category": category, "topic": topic,
                       "signature": signature, "count": 0, "avg_minute": minute, "days": [],
                       "examples": [], "evidence": [], "last_seen_at": None}
            document["patterns"].append(pattern)
        count = min(999, pattern["count"] + 1)
        pattern["count"] = count
        pattern["avg_minute"] = round((float(pattern["avg_minute"]) * max(0, count - 1) + minute) / max(1, count), 1)
        pattern["last_seen_at"] = stamp(event.received_at)
        pattern["days"] = list(dict.fromkeys([*pattern["days"], local.date().isoformat()]))[-MAX_EVIDENCE_DAYS:]
        example = single_line(text, MAX_EXAMPLE_CHARS)
        pattern["examples"] = list(dict.fromkeys([example, *pattern["examples"]]))[:MAX_EXAMPLES]
        reference = {"event_key": event.scoped_key, "source_owner": event.source.owner,
                     "source_id": event.source.source_id, "source_revision": event.source.version.revision,
                     "received_at": stamp(event.received_at)}
        pattern["evidence"] = [reference, *[item for item in pattern["evidence"] if item != reference]][:MAX_EVIDENCE_REFS]
        now = self.tasks.now()
        reorganize(document, settings, now)
        retain_patterns(document, settings, now)
        document["updated_at"] = stamp(now)
        connection.execute(UPSERT, (identifier, owner, KIND, row["revision"] + 1 if row is not None else 1,
                                    json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                                    json.dumps({"owner": OWNER}, sort_keys=True, separators=(",", ":")), stamp(now)))

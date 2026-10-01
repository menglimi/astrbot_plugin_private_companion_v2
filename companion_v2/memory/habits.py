"""Evidence-backed private habits and the recorded meal preferences they support.

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

The "what to eat" ability is deliberately expressed as prompt material only: when
the current turn asks about eating and the recorded preferences have enough
evidence, the persona may lean on them; no tool, provider or platform call is
added, and an unsupported guess is explicitly forbidden.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
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
CATEGORIES = ("饮食节奏", "作息节奏", "学习工作", "娱乐习惯", "互动习惯", "偏好习惯")
MAX_TOPIC_CHARS = 80
MAX_EXAMPLE_CHARS = 90
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
    "这是从对方自己说过的话里累计出来的软线索，不是命令，也不是对方的自我认定。",
    "只在当前语境自然吻合时提前理解或轻轻提起，不要暴露统计、次数或“我记录了你”。",
    "没有把握的条目不要使用，也不要把一次玩笑、反讽或临时情绪当成稳定习惯。",
)

MEAL_GUIDANCE = (
    "对方本轮在问吃什么：如果上面的口味/节奏线索证据足够，可以顺着这些记录给出一两个具体方向。",
    "只参考这里列出的偏好，不要编造对方没提过的食物、忌口或餐厅，也不要一次报整份菜单。",
    "线索不足、或者对方只是随口一说时，就按平常聊天回应，不要假装记得。",
)

FOOD_FEATURE_MARKERS = ("功能", "开关", "配置", "页面", "注入", "触发", "保存", "管理", "模块", "面板", "不好用", "误判")
FOOD_TOKENS = ("吃", "喝", "饭", "菜", "辣", "甜", "咸", "咖啡", "茶", "奶茶", "外卖", "夜宵", "宵夜", "水果",
               "牛奶", "酒", "零食", "甜品", "忌口", "香菜")
FOOD_QUERY_MARKERS = ("吃什么", "吃啥", "点什么", "点啥", "外卖", "夜宵", "宵夜", "午饭", "午餐", "晚饭", "晚餐",
                      "早餐", "早饭", "饿了", "好饿", "嘴馋", "推荐", "想喝", "喝什么")
INTERACTION_PATTERNS = ("^(?:早|早安|早上好|午安|中午好|晚上好|晚安)(?:呀|啊|哦|喔|啦|～|~|！|!)?$",
                        "^(?:摸摸|抱抱|贴贴|亲亲){1,4}(?:呀|啊|哦|啦|～|~|！|!)?$",
                        "^(?:你)?(?:在干嘛|在做什么|做什么呢|在吗)(?:呀|啊|呢|？|\\?)?$")
SELF_STATE = {"饮食": r"(?:我.{0,10}(?:吃|饿|饱)|(?:还没吃|没吃|刚吃|吃完|饿了|好饿|饱了|去吃饭|准备吃))",
              "作息": r"(?:我.{0,10}(?:睡|醒|困|起床|熬夜)|(?:睡觉啦|准备睡|去睡了|刚睡醒|醒了|起床了|困了|睡不着|还没睡))",
              "学习工作": r"(?:我.{0,12}(?:学习|上班|下班|工作|上课|下课|写作业|考试|摸鱼)|(?:去上班|下班了|上课了|下课了|写作业|准备考试))",
              "娱乐": r"(?:我.{0,12}(?:玩|看|刷|追)|(?:在玩|去玩|在看|刚看|最近看|正在刷|准备看).{0,20})"}
NOISE_MARKERS = ("我转发了一段聊天记录", "你看看里面在说什么", "合并转发", "聊天记录", "<timer", "<tts")
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
    lowered = text.lower()
    if not text or len(text) > 180 or text.startswith(("/", "!", "！", "#")):
        return True
    if any(token in lowered for token in NOISE_MARKERS):
        return True
    return bool(re.search(r"^(?:(?:私聊|群聊)?(?:告诉|转告|提醒|叫|转发给)).{1,40}", text)
                or re.search(r"(?:帮我|能去|可以去).{0,12}(?:告诉|叫|转告|提醒).{1,40}", text))


def has_self_state(text, kind):
    if not text or re.search(r"(?:你|他|她|它|别人|群里).{0,8}", text[:20]):
        return False
    return bool(re.search(SELF_STATE.get(kind, r"$^"), text))


def classify_message(value):
    """Deterministic habit classification: (category, topic, signature) or blanks.

    Ported from V1 ``_classify_user_habit_message``. Only the user's own state is
    read; V1's ``固定检索`` category described questions about the Bot's own life
    and is already served by the existing recall/state materials, so it is not
    migrated here.
    """
    cleaned = single_line(value, 220)
    if not cleaned or message_is_noise(cleaned):
        return "", "", ""
    compact = re.sub(r"\s+", "", cleaned)
    category = topic = ""
    if any(re.fullmatch(pattern, compact) for pattern in INTERACTION_PATTERNS):
        category, topic = "互动习惯", "日常问候" if "早" in compact or "晚" in compact else "亲昵互动"
    elif any(token in cleaned for token in ("喜欢", "讨厌", "想要", "以后", "每天", "经常", "总是", "习惯")):
        category, topic = "偏好习惯", cleaned
    elif has_self_state(cleaned, "饮食"):
        category = "饮食节奏"
        if any(token in cleaned for token in ("还没", "没吃", "没来得及", "没饭", "没到饭点")):
            topic = "还没吃/饭点偏晚"
        elif any(token in cleaned for token in ("吃了", "刚吃", "吃完", "饱")):
            topic = "已经吃过饭"
        else:
            topic = "吃饭相关"
    elif has_self_state(cleaned, "作息"):
        category = "作息节奏"
        if any(token in cleaned for token in ("还没睡", "睡不着", "熬夜")):
            topic = "夜里还没睡"
        elif any(token in cleaned for token in ("起床", "刚醒", "醒了")):
            topic = "起床/刚醒"
        else:
            topic = "睡眠相关"
    elif has_self_state(cleaned, "学习工作"):
        category, topic = "学习工作", "学习/工作节奏"
    elif has_self_state(cleaned, "娱乐"):
        category, topic = "娱乐习惯", "娱乐/刷内容"
    if not category or not topic:
        return "", "", ""
    signature = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_]+", "", topic.casefold())[:80]
    return category, single_line(topic, MAX_TOPIC_CHARS), category + "|" + signature


def meal_query(value):
    """Whether this turn asks the companion what to eat or drink."""
    text = single_line(value, 220)
    if not text or any(marker in text for marker in FOOD_FEATURE_MARKERS):
        return False
    return any(marker in text for marker in FOOD_QUERY_MARKERS)


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


def natural_line(pattern):
    """One soft clue per pattern; V1 ``_natural_user_habit_line`` phrasing."""
    bucket, category, topic = pattern.get("bucket", ""), pattern.get("category", ""), pattern.get("topic", "")
    if not topic:
        return ""
    if category == "饮食节奏":
        if "还没吃" in topic or "饭点偏晚" in topic:
            return f"{bucket}时对方常会提到还没吃饭，聊到吃的可以轻轻接住，不用像提醒。"
        if "已经吃过" in topic:
            return f"{bucket}时对方常已经吃过饭，别每次都追问吃没吃。"
        return f"{bucket}时对方容易聊到吃饭，相关时顺手接住就好。"
    if category == "作息节奏":
        if "夜里还没睡" in topic:
            return f"{bucket}时对方常还醒着，聊到睡觉时少一点催促，多一点顺着接。"
        if "起床" in topic or "刚醒" in topic:
            return f"{bucket}时对方常刚醒，语气可以放轻一点。"
        return f"{bucket}时对方容易聊到睡眠，别把作息说教化。"
    if category == "学习工作":
        return f"{bucket}时对方常在学习或工作相关状态里，回复可以更直接、少绕。"
    if category == "娱乐习惯":
        return f"{bucket}时对方常在看东西或玩内容，相关时可以自然接梗。"
    if category == "互动习惯":
        return f"{bucket}时对方常用这类固定开场，先直接接住，不用每次都当新话题。"
    return f"{bucket}时对方常提到类似“{topic}”的偏好或习惯，相关时记得顺着一点。"


def profile_lines(patterns):
    lines = []
    for pattern in patterns:
        line = natural_line(pattern)
        if line and line not in lines:
            lines.append(line)
        if len(lines) >= MAX_LINES:
            break
    return lines


def meal_lines(patterns):
    """Recorded eating preferences, already restricted to sufficiently supported ones.

    V1 learned a dish menu from explicit meal replies; V2 keeps that out of scope
    (no new store, no menu) and leans only on the recorded eating rhythm plus the
    taste preferences the user actually stated.
    """
    lines = []
    for pattern in patterns:
        topic = single_line(pattern.get("topic"), MAX_TOPIC_CHARS)
        if not topic:
            continue
        if pattern.get("category") == "饮食节奏" or any(token in topic for token in FOOD_TOKENS):
            if topic not in lines:
                lines.append(topic)
        if len(lines) >= MAX_LINES:
            break
    return lines


def habit_material(memory, context, *, meal_query=False, at=None):
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
    material = {"basis": "recorded_user_statements_only", "profile_version": row["revision"],
                "min_evidence": settings["habit_min_count"], "max_items": settings["habit_max_items"],
                "habits": lines, "guidance": list(GUIDANCE)}
    if settings["food_menu_recommendation_enabled"] and meal_query:
        recorded = meal_lines(qualified)
        if recorded:
            material["meal_question"] = True
            material["recorded_eating_preferences"] = recorded
            material["meal_guidance"] = list(MEAL_GUIDANCE)
    return material


def habit_contribution(memory, context, *, meal_query=False, at=None):
    """The habit material as one more memory-owned contribution, or None."""
    try:
        material = habit_material(memory, context, meal_query=meal_query, at=at)
    except (TaskError, ValueError, KeyError, AttributeError):
        return None
    if material is None:
        return None
    return ContextContribution("memory:user-habits", "memory", "current_user_habits",
                               ContributionState.READY, json.dumps(material, ensure_ascii=False,
                                                                   sort_keys=True, separators=(",", ":")))


def habit_capture(memory, context, current_text):
    """Sealed per batch: whether this turn's own input asks about eating.

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
    return {"meal_query": meal_query(current_text)}


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
    kept.sort(key=lambda item: (len({str(day) for day in item.get("days", []) if str(day)}),
                                item.get("count") or 0, item.get("last_seen_at") or ""), reverse=True)
    document["patterns"] = kept[:settings["habit_max_items"]]
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
        document["patterns"] = document["patterns"][:settings["habit_max_items"]]
        document["updated_at"] = stamp(now)
        connection.execute(UPSERT, (identifier, owner, KIND, row["revision"] + 1 if row is not None else 1,
                                    json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                                    json.dumps({"owner": OWNER}, sort_keys=True, separators=(",", ":")), stamp(now)))

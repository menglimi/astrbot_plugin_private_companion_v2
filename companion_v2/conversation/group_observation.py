"""Bounded group observation material: mood, moments, joke boundary, denoise.

V1 kept a per-group observation subsystem (``group_observation.py``,
``group_mood.py``, ``group_moments.py``, ``joke_boundary.py``,
``roleplay_strength.py``). V2 keeps the deterministic, cheap half of it and
records it as reference material for the group prompt:

* everything is folded from already-admitted, receipt-validated group material,
  so a message that is not in the authorized window cannot contribute;
* records belong to the group's own memory owner and live on the shared
  ``runtime_metadata`` table, so this slice adds no table and no schema version;
* a record never stores a member identifier, never claims anything about a
  member, and never produces an action against a member. V1's per-member joke
  sensitivity profile is deliberately not migrated: the guard is re-derived for
  the current visible window instead, and the moment record keeps the text
  without attribution.

The module owns no model call, no clock, no send path and no read privilege of
its own; prompt wording lives in ``participation_prompts``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re

from companion_v2.execution.models import digest


PREFIX = "conversation.group_observation.v1"
VERSION = "conversation.group_observation.v1"
MOOD_KIND = "mood"
MOMENTS_KIND = "moments"
JOKE_KIND = "joke_guard"

# Material budgets, in the same spirit as the group context window: bounded
# enough that one turn cannot grow the prompt or the record without limit.
MAX_PROCESSED_KEYS = 128
MAX_MOMENTS = 8
MAX_MOMENT_CHARS = 120
MAX_MOMENT_PROMPT_ITEMS = 3
MAX_DETAIL_MOODS = 2
MOMENT_TTL_SECONDS = 7 * 24 * 3600
MOMENT_BURST_SECONDS = 30
MOMENT_BURST_SPEAKERS = 3
MOOD_PROMPT_MIN_SCORE = 6.0
# V1 added 28 sensitivity points per serious objection and blocked at 60, so a
# member needed roughly three objections. Without a per-member profile the same
# ratio is applied to the visible window's own objection count.
JOKE_OBJECTION_BLOCK = 3
JOKE_OBJECTION_CAUTION = 1

MOOD_VERSION = "group_mood.v2"
MOOD_LABELS = ("tease", "banter", "serious", "tension", "confession", "dead_silence")
MOOD_LABELS_ZH = {"tease": "调侃", "banter": "互怼", "serious": "严肃",
                  "tension": "火药味", "confession": "告白", "dead_silence": "冷场"}
MOOD_SIGNALS = (
    (r"哈哈+|呵呵+|嘿嘿+|笑死|没绷住|绷不住|好笑|好乐|乐了|2333+|www+|xswl+", "tease", 1.6),
    (r"滑稽|阴阳|玩梗|整活|搞事|皮一下|开玩笑的|我开个玩笑", "tease", 1.4),
    (r"你不行|菜鸡|就这|拉胯|太菜|你这不行", "banter", 1.8),
    (r"？？？+", "banter", 0.6),
    (r"说正事|认真讲|说真的|认真的|严肃点|不是玩笑|不开玩笑|别闹了|谈正事", "serious", 2.4),
    (r"你什么意思|你再说一遍|别太过分|太过分了|有病吧|闭嘴|别吵|吵什么|急了", "tension", 2.6),
    (r"想打架|单挑|开喷|人身攻击|侮辱", "tension", 2.8),
    (r"我喜欢你|喜欢你|表白|在一起吧|好喜欢|心动|暗恋", "confession", 2.6),
    (r"想要你|想你了|舍不得|抱抱你|贴贴", "confession", 1.4),
)
MOOD_HALF_LIVES = {"tease": 1500.0, "banter": 1800.0, "serious": 900.0,
                   "tension": 7200.0, "confession": 2400.0, "dead_silence": 3600.0}
TENSION_WEIGHTS = {"tension": 1.0, "banter": 0.45, "tease": 0.18,
                   "confession": 0.12, "serious": 0.1, "dead_silence": 0.0}
SPARK_PATTERNS = (r"修罗场", r"血流成河", r"没绷住", r"笑死", r"经典", r"名场面", r"这波",
                  r"绷不住了", r"这谁顶得住", r"救命", r"好活", r"逆天", r"公开处刑", r"社死")
OBJECTION_PATTERNS = (r"别拿我开玩笑", r"不要开我玩笑", r"别开这种玩笑", r"这不是玩笑",
                      r"我不是在开玩笑", r"一点都不好笑", r"不好笑", r"过分了",
                      r"玩笑适可而止", r"别再这样了", r"我真的生气了", r"生气了", r"别闹了")
# V1's mood-to-exaggeration base, without the private expression band: a group
# turn has no private relationship band, so V1's neutral band modifier applies.
STRENGTH_BASE = {"tease": 72.0, "banter": 66.0, "confession": 38.0,
                 "serious": 14.0, "tension": 10.0, "dead_silence": 8.0}
STRENGTH_TENSION_DAMPEN = 0.5 * 0.3
STRENGTH_BANDS = ((60.0, "playful_high", "偏玩闹"), (35.0, "playful_moderate", "略玩闹"),
                  (12.0, "reserved", "克制"), (0.0, "minimal", "最低"))


def parse_moment(value):
    """Parse one stored ISO moment as aware UTC time; anything else is absent."""
    try:
        parsed = datetime.fromisoformat(value) if type(value) is str else None
    except ValueError:
        return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _low(value, default=0.0):
    if type(value) is bool or type(value) not in (int, float):
        return default
    return float(value)


def item_key(item):
    """A stable key so the same admitted message is folded only once."""
    return digest([str(item.get("speaker_id") or ""), str(item.get("received_at") or ""),
                   " ".join(str(item.get("text") or "").split())])


def history_items(recent):
    """Normalize the admitted group history into bounded observation items.

    Only the two receipt-backed shapes are read: ``group_member_message`` keeps
    its member attribution for counting, ``confirmed_group_reply`` is the role's
    own confirmed wording. Nothing else in the material contributes.
    """
    items = []
    for entry in recent:
        if type(entry) is not dict:
            continue
        kind = entry.get("type")
        if kind == "group_member_message":
            items.append({"kind": "member", "speaker_id": str(entry.get("speaker_id") or ""),
                          "received_at": entry.get("received_at"), "text": str(entry.get("text") or "")})
        elif kind == "confirmed_group_reply":
            items.append({"kind": "bot", "speaker_id": "", "received_at": entry.get("delivered_at"),
                          "text": str(entry.get("text") or "")})
    return tuple(items)


class GroupPresenceStore:
    """Bounded, owner-scoped group records on the shared runtime metadata table.

    One key per group owner and record kind. A document is written by the caller
    through ``write`` inside the caller's transaction, exactly like the other
    ``runtime_metadata`` ledgers, so no new table and no migration are needed.
    """

    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def key(owner, kind):
        return PREFIX + ":" + kind + ":" + digest([VERSION, owner])

    def read(self, owner, kind):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?",
                                    (self.key(owner, kind),))
        if row is None:
            return None
        try:
            value = json.loads(row["value"])
        except ValueError:
            return None
        return value if type(value) is dict and value.get("version") == VERSION else None

    def write(self, connection, owner, kind, document):
        """Persist one bounded document; the caller owns the transaction."""
        connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (self.key(owner, kind), json.dumps({"version": VERSION, **document},
                                               ensure_ascii=False, sort_keys=True, separators=(",", ":"))))


# -- mood -----------------------------------------------------------------

def fold_mood(existing, items, at):
    """Fold the visible window into the stored group mood, V1's decay included."""
    prior = project_mood(existing, at)
    scores = {label: _low((prior.get("mood_scores") or {}).get(label)) for label in MOOD_LABELS}
    processed = [str(key) for key in (prior.get("processed_keys") or ())][-MAX_PROCESSED_KEYS:]
    seen, count = set(processed), 0
    burst = {label: 0.0 for label in MOOD_LABELS}
    for item in items:
        if item.get("kind") != "member":
            continue  # the group's atmosphere is read from members, never from the role's own wording
        text = " ".join(str(item.get("text") or "").split())
        if not text:
            continue
        key = item_key({**item, "text": text})
        if key in seen:
            continue
        seen.add(key)
        processed.append(key)
        count += 1
        lowered = text.lower()
        for pattern, mood, weight in MOOD_SIGNALS:
            matches = len(re.findall(pattern, lowered))
            if matches:
                burst[mood] = min(100.0, burst[mood] + weight * min(3, matches))
    for label in MOOD_LABELS:
        if label == "dead_silence":
            continue
        scores[label] = round(min(100.0, scores[label] + burst[label]), 2)
    if count:
        scores["dead_silence"] = round(max(0.0, scores["dead_silence"] - 6.0), 2)
    tension = 0.0
    for label in MOOD_LABELS:
        if label != "dead_silence":
            tension += min(100.0, scores[label]) * TENSION_WEIGHTS.get(label, 0.0)
    return {"version": VERSION, "mood_scores": scores, "top_mood": _top_mood(scores),
            "social_tension": round(min(100.0, tension), 2),
            "updated_at": at.isoformat(), "message_count": int(prior.get("message_count") or 0) + count,
            "processed_keys": processed[-MAX_PROCESSED_KEYS:]}


def project_mood(existing, at):
    """Project a stored mood record to now, half-life decay included."""
    if type(existing) is not dict or existing.get("version") != VERSION:
        return {}
    updated = parse_moment(existing.get("updated_at"))
    elapsed = max(0.0, (at - updated).total_seconds()) if updated is not None else 0.0
    stored = existing.get("mood_scores") if type(existing.get("mood_scores")) is dict else {}
    scores = {label: round(_decay(max(0.0, _low(stored.get(label))), MOOD_HALF_LIVES[label], elapsed), 2)
              for label in MOOD_LABELS}
    tension = round(_decay(min(100.0, max(0.0, _low(existing.get("social_tension")))), 2400.0, elapsed), 2)
    return {"mood_scores": scores, "top_mood": _top_mood(scores), "social_tension": tension,
            "updated_at": updated, "message_count": max(0, int(_low(existing.get("message_count")))),
            "processed_keys": [str(key) for key in (existing.get("processed_keys") or ())][-MAX_PROCESSED_KEYS:]}


def mood_facts(existing, at):
    """Only what the prompt may quote: top mood, runner-ups and tension band."""
    mood = project_mood(existing, at)
    if not mood:
        return {}
    scores = mood["mood_scores"]
    top = mood["top_mood"]
    ranked = [label for label in sorted(MOOD_LABELS, key=lambda name: scores[name], reverse=True)
              if scores[label] >= MOOD_PROMPT_MIN_SCORE and label != top]
    tension = mood["social_tension"]
    return {"top_mood": top, "top_label": MOOD_LABELS_ZH[top], "top_score": round(scores[top], 2),
            "detail": tuple({"label": MOOD_LABELS_ZH[label], "score": round(scores[label], 2)}
                            for label in ranked[:MAX_DETAIL_MOODS]),
            "tension": tension, "tension_level": "high" if tension >= 55 else "low" if tension <= 12 else "normal"}


def _decay(score, half_life, elapsed):
    return 0.0 if score <= 0 or half_life <= 0 else max(0.0, score * (0.5 ** (max(0.0, elapsed) / half_life)))


def _top_mood(scores):
    ranked = sorted(MOOD_LABELS, key=lambda label: _low(scores.get(label)), reverse=True)
    return ranked[0] if _low(scores.get(ranked[0])) > 0 else "dead_silence"


def joke_guard(items, at):
    """Window-level joke boundary signals; deliberately not a member profile.

    V1 accumulated per-member sensitivity with a two-week calm decay. V2 keeps
    the same objection vocabulary but only for the currently visible window and
    without any member key, so the result can lower the joke energy of this turn
    and can never become a stored claim about a person.
    """
    objections = []
    for item in items:
        if item.get("kind") != "member":
            continue
        text = " ".join(str(item.get("text") or "").split())
        if text and any(re.search(pattern, text) for pattern in OBJECTION_PATTERNS):
            objections.append(text[:MAX_MOMENT_CHARS])
    count = len(objections)
    level = ("blocked" if count >= JOKE_OBJECTION_BLOCK else
             "caution" if count >= JOKE_OBJECTION_CAUTION else "normal")
    return {"version": VERSION, "objections": count, "level": level, "updated_at": at.isoformat(),
            "samples": objections[-JOKE_OBJECTION_BLOCK:]}


# -- moments --------------------------------------------------------------

def moment_candidates(items, at, *, window_seconds=MOMENT_BURST_SECONDS):
    """Deterministic 名场面 candidates: spark wording, or a tight multi-speaker burst.

    V1 also treated a quoted reply as a signal. The bounded V2 history carries no
    member-level reply attribution, so that signal is not invented here.
    """
    texts = [item for item in items if item.get("kind") == "member" and str(item.get("text") or "").strip()
             and (parse_moment(item.get("received_at")) or at) <= at]
    candidates = []
    for index, item in enumerate(texts):
        text = str(item["text"])
        lowered = text.lower()
        score, reasons = 0.0, []
        if any(re.search(pattern, lowered) for pattern in SPARK_PATTERNS):
            score, reasons = score + 2.0, reasons + ["spark"]
        start = parse_moment(item.get("received_at"))
        speakers = {str(item.get("speaker_id") or "")}
        for other in texts[index + 1:]:
            when = parse_moment(other.get("received_at"))
            if start is None or when is None or (when - start).total_seconds() > window_seconds:
                break
            speakers.add(str(other.get("speaker_id") or ""))
        if len(speakers - {""}) >= MOMENT_BURST_SPEAKERS:
            score, reasons = score + 1.0, reasons + ["burst"]
        if score >= 1.0:
            candidates.append({"text": " ".join(text.split())[:MAX_MOMENT_CHARS], "score": round(score, 2),
                               "reasons": reasons, "at": item.get("received_at")})
    candidates.sort(key=lambda entry: entry["score"], reverse=True)
    return tuple(candidates[:MAX_MOMENTS])


def fold_moments(existing, candidates, at):
    """Merge candidates into the bounded moment record, deduplicated and expiring."""
    stored = {}
    if type(existing) is dict and existing.get("version") == VERSION:
        for entry in existing.get("moments") or ():
            if type(entry) is not dict or not str(entry.get("text") or ""):
                continue
            expires = parse_moment(entry.get("expires_at"))
            if expires is not None and expires < at:
                continue
            stored[str(entry.get("hash") or digest(entry["text"]))] = dict(entry)
    for candidate in candidates:
        text = str(candidate.get("text") or "")
        if not text:
            continue
        key = digest(text)
        previous = stored.get(key)
        stored[key] = {"hash": key, "text": text, "at": candidate.get("at") or at.isoformat(),
                       "score": max(_low(candidate.get("score")), _low((previous or {}).get("score"))),
                       "reasons": list(candidate.get("reasons") or ()),
                       "created_at": (previous or {}).get("created_at") or at.isoformat(),
                       "expires_at": (previous or {}).get("expires_at") or (at + timedelta(seconds=MOMENT_TTL_SECONDS)).isoformat()}
    moments = sorted(stored.values(), key=lambda entry: str(entry.get("at") or ""), reverse=True)[:MAX_MOMENTS]
    return {"version": VERSION, "moments": moments, "updated_at": at.isoformat()}


def moment_facts(existing, at, *, limit=MAX_MOMENT_PROMPT_ITEMS):
    """The unexpired moments the prompt may mention, newest first, text only."""
    if type(existing) is not dict or existing.get("version") != VERSION:
        return ()
    active = []
    for entry in existing.get("moments") or ():
        if type(entry) is not dict or not str(entry.get("text") or ""):
            continue
        expires = parse_moment(entry.get("expires_at"))
        if expires is not None and expires < at:
            continue
        active.append({"text": str(entry["text"])[:MAX_MOMENT_CHARS], "at": str(entry.get("at") or "")})
    active.sort(key=lambda entry: entry["at"], reverse=True)
    return tuple(active[:limit])


def moment_portrait(items, current_speaker):
    """Current speaker's own visible cues for this turn only; never stored.

    V1 derived a provisional portrait from stored moments. V2 keeps it inside
    the turn: the cues come from this speaker's own authorized messages in the
    visible window, they are handed to the prompt as unverified reference, and
    nothing about them is written anywhere.
    """
    text = " ".join(str(item.get("text") or "") for item in items
                    if item.get("kind") == "member" and str(item.get("speaker_id") or "") == str(current_speaker or ""))
    if not text:
        return {}
    if any(re.search(pattern, text) for pattern in OBJECTION_PATTERNS):
        return {"cue": "boundary", "text": text[:MAX_MOMENT_CHARS]}
    sparks = [pattern for pattern in SPARK_PATTERNS if re.search(pattern, text)]
    if sparks:
        return {"cue": "playful", "sparks": tuple(sparks[:3]), "text": text[:MAX_MOMENT_CHARS]}
    return {}


def project_strength(mood_facts_value):
    """V1's exaggeration projection: playful moods lean in, tense ones step back."""
    facts = mood_facts_value or {}
    top = str(facts.get("top_mood") or "dead_silence")
    if top not in MOOD_LABELS:
        top = "dead_silence"
    dominant = _low(facts.get("top_score"))
    weight = min(1.0, dominant / (60.0 if top == "dead_silence" else 50.0))
    exaggerate = STRENGTH_BASE.get(top, 8.0) * weight + 8.0 * (1.0 - weight)
    exaggerate = max(0.0, exaggerate - _low(facts.get("tension")) * STRENGTH_TENSION_DAMPEN)
    band = next((name for limit, name, _ in STRENGTH_BANDS if exaggerate >= limit), "minimal")
    return {"exaggerate": round(exaggerate, 2), "band": band, "top_mood": top,
            "label": next(label for _, name, label in STRENGTH_BANDS if name == band)}


def observe(store, *, owner, settings, items, at, current_speaker=""):
    """Compute this turn's bounded observation facts and the records to fold.

    Nothing is written here: the caller folds ``records`` at the moment the turn
    actually decides something, so an unfinished turn leaves no observation.
    """
    facts, records = {}, {}
    if settings["enable_group_social_context"]:
        if settings["enable_group_mood_detection"]:
            record = fold_mood(store.read(owner, MOOD_KIND), items, at)
            records[MOOD_KIND] = record
            facts["mood"] = mood_facts(record, at)
        if settings["enable_group_roleplay_strength"]:
            facts["strength"] = project_strength(facts.get("mood"))
        if settings["enable_group_moments"]:
            record = fold_moments(store.read(owner, MOMENTS_KIND), moment_candidates(items, at), at)
            records[MOMENTS_KIND] = record
            facts["moments"] = moment_facts(record, at)
        if settings["enable_group_moment_portrait"]:
            facts["portrait"] = moment_portrait(items, current_speaker)
        if settings["enable_group_joke_guard"]:
            record = joke_guard(items, at)
            records[JOKE_KIND] = record
            facts["joke_guard"] = record
    return {"facts": facts, "records": records}

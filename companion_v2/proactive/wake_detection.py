"""User wake-up observation: typed evidence fusion, never keyword inference.

The companion must not claim to know that the user woke up from the tone of a
message, and must not guess it from silence.  This module only fuses *typed*
observations that another owner already produced:

* an explicit private input (the user is demonstrably awake at that instant);
* an explicit answer to the scheduled wake-up session;
* a mobile device activity/telemetry state transition reported by the Reality
  gateway (walking/running/cycling vs sleeping/resting);
* a fresh foreground-app usage summary or a device reconnect (screen in use);
* a reported step count that moved past the previous reading.

Absence of evidence is never treated as sleep, silence never as "still asleep",
and no natural-language text is inspected.  The output is a bounded observation
plus a contact decision that reuses the existing proactive opportunity ledger.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from zoneinfo import ZoneInfo


STATE_UNKNOWN = "unknown"
STATE_ASLEEP_LIKELY = "asleep_likely"
STATE_STIRRING = "stirring"
STATE_AWAKE_LIKELY = "awake_likely"
STATE_CONFIRMED = "confirmed"
AWAKE_STATES = frozenset({STATE_AWAKE_LIKELY, STATE_CONFIRMED})

POSITIVE = "positive"
NEGATIVE = "negative"
EXPLICIT_KINDS = frozenset({"alarm_acknowledged", "explicit_input"})

# These are closed identifiers of the mobile gateway API, not free text.
TELEMETRY_AWAKE_STATES = frozenset({"walking", "running", "cycling"})
TELEMETRY_SLEEP_STATES = frozenset({"sleeping"})
TELEMETRY_RESTING_STATES = frozenset({"resting"})


@dataclass(frozen=True)
class SignalRule:
    """Polarity, freshness bound, default confidence and prompt-safe label."""

    polarity: str
    max_age_seconds: int
    confidence: int
    label: str


SIGNALS = MappingProxyType({
    "alarm_acknowledged": SignalRule(POSITIVE, 12 * 3600, 100, "用户本人明确回应了这次叫醒"),
    "explicit_input": SignalRule(POSITIVE, 3 * 3600, 92, "用户在一段安静之后主动发来私聊"),
    "motion_activity": SignalRule(POSITIVE, 20 * 60, 70, "用户侧设备从休息状态转为步行、跑步或骑行等活动"),
    "screen_resumed": SignalRule(POSITIVE, 20 * 60, 58, "用户侧设备重新出现前台应用使用摘要"),
    "device_reconnected": SignalRule(POSITIVE, 20 * 60, 40, "用户侧设备在离线后重新上报状态"),
    "steps_increased": SignalRule(POSITIVE, 30 * 60, 52, "用户侧设备的步数在上一观测之后增加"),
    "sleep_reported": SignalRule(NEGATIVE, 14 * 3600, 88, "用户侧设备报告的最近活动状态是睡眠"),
    "resting_reported": SignalRule(NEGATIVE, 45 * 60, 45, "用户侧设备报告的最近活动状态是静止休息"),
})


def _as_utc(value, *, field="time"):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _bounded(value):
    return max(0, min(100, int(value)))


@dataclass(frozen=True)
class WakeEvidence:
    """One typed observation about the user's state at a known instant."""

    kind: str
    observed_at: datetime
    source: str = ""
    confidence: int | None = None
    detail: str = ""

    def __post_init__(self):
        rule = SIGNALS.get(self.kind)
        if rule is None:
            raise ValueError("wake evidence must use a registered signal kind")
        object.__setattr__(self, "observed_at", _as_utc(self.observed_at, field="wake evidence time"))
        confidence = rule.confidence if self.confidence is None else self.confidence
        if type(confidence) is not int or not 0 <= confidence <= 100:
            raise ValueError("wake evidence confidence must be an integer in 0..100")
        object.__setattr__(self, "confidence", confidence)
        if type(self.source) is not str or len(self.source) > 80:
            raise ValueError("wake evidence source must be a short identifier")
        if type(self.detail) is not str or len(self.detail) > 160:
            raise ValueError("wake evidence detail must stay bounded")

    def document(self):
        return {"kind": self.kind, "observed_at": self.observed_at.isoformat(),
                "source": self.source, "confidence": self.confidence,
                "detail": self.detail, "polarity": SIGNALS[self.kind].polarity}


def evidence(kind, observed_at, *, source="", confidence=None, detail=""):
    return WakeEvidence(kind, observed_at, source=source, confidence=confidence, detail=detail)

@dataclass(frozen=True)
class WakeObservation:
    """The fused state; ``woke_at`` is the start of the current wake episode."""

    state: str
    confidence: int
    woke_at: datetime | None
    episode_key: str
    evidence: tuple
    negative_at: datetime | None
    reason: str
    zone: str

    def document(self):
        return {"state": self.state, "confidence": self.confidence,
                "woke_at": self.woke_at.isoformat() if self.woke_at else None,
                "episode_key": self.episode_key, "reason": self.reason,
                "negative_at": self.negative_at.isoformat() if self.negative_at else None,
                "zone": self.zone,
                "evidence": [item.document() for item in self.evidence]}


def _decayed(item, rule, at):
    age = max(0.0, (at - item.observed_at).total_seconds())
    life = max(1, rule.max_age_seconds)
    return max(1, round(item.confidence * max(0.35, 1.0 - 0.55 * age / life)))


def observe(items, *, at, zone="Asia/Shanghai", episode_minutes=90):
    """Fuse bounded evidence into one wake state.

    Only fresh evidence inside each signal's own age bound is considered.  The
    most recent negative signal ends the previous episode; positives must be
    strictly newer than it to describe the current wake episode.
    """
    at = _as_utc(at, field="wake observation time")
    try:
        tz = ZoneInfo(str(zone or "Asia/Shanghai"))
    except Exception as error:
        raise ValueError("wake observation requires a valid timezone") from error
    fresh = []
    for item in items or ():
        if not isinstance(item, WakeEvidence):
            raise ValueError("wake observation accepts WakeEvidence only")
        rule = SIGNALS[item.kind]
        if item.observed_at > at + timedelta(seconds=5):
            continue
        if at - item.observed_at > timedelta(seconds=rule.max_age_seconds):
            continue
        fresh.append(item)
    fresh.sort(key=lambda item: (item.observed_at, item.kind))
    if not fresh:
        return WakeObservation(STATE_UNKNOWN, 0, None, "", (), None, "no_fresh_evidence", tz.key)

    negatives = [item for item in fresh if SIGNALS[item.kind].polarity == NEGATIVE]
    positives = [item for item in fresh if SIGNALS[item.kind].polarity == POSITIVE]
    latest_negative = negatives[-1] if negatives else None
    negative_at = latest_negative.observed_at if latest_negative is not None else None
    current = [item for item in positives
               if negative_at is None or item.observed_at > negative_at]
    if not current:
        confidence = max((item.confidence for item in negatives), default=0)
        return WakeObservation(STATE_ASLEEP_LIKELY, _bounded(confidence), None, "",
                               tuple(fresh), negative_at, "negative_evidence_is_newer", tz.key)

    scored = [(item, _decayed(item, SIGNALS[item.kind], at)) for item in current]
    base = max(value for _, value in scored)
    sources = {item.source or item.kind for item, _ in scored}
    kinds = {item.kind for item, _ in scored}
    bonus = min(20, 6 * (len(sources) - 1))
    explicit_recent = any(
        item.kind in EXPLICIT_KINDS and at - item.observed_at <= timedelta(minutes=30)
        for item, _ in scored)
    score = 100 if explicit_recent else min(100, base + bonus)
    if explicit_recent:
        state = STATE_CONFIRMED
    elif score >= 65:
        state = STATE_AWAKE_LIKELY
    elif score >= 40:
        state = STATE_STIRRING
    else:
        state = STATE_UNKNOWN

    explicit = [item.observed_at for item, _ in scored if item.kind in EXPLICIT_KINDS]
    woke_at = min(explicit) if explicit else min(item.observed_at for item, _ in scored)
    woke_at = min(woke_at, at)
    local = woke_at.astimezone(tz)
    width = max(1, int(episode_minutes))
    bucket = (local.hour * 60 + local.minute) // width
    episode_key = f"wake:{local.date().isoformat()}:{bucket}:{tz.key}"
    if explicit_recent:
        reason = "explicit_awake_signal"
    elif len(sources) > 1:
        reason = "independent_signals"
    elif len(kinds) > 1:
        reason = "corroborating_signals"
    else:
        reason = "single_signal"
    return WakeObservation(state, _bounded(score), woke_at, episode_key,
                           tuple(fresh), negative_at, reason, tz.key)

@dataclass(frozen=True)
class WakeContactDecision:
    allowed: bool
    reason: str
    observation: WakeObservation

    def document(self):
        return {"allowed": self.allowed, "reason": self.reason,
                "observation": self.observation.document()}


def contact_decision(observation, *, at, minimum_confidence=65, window_minutes=90,
                     already_contacted=False, quiet_hours=False, purpose_allowed=True,
                     morning_start=5, morning_end=12):
    """Decide whether this wake episode may open one proactive contact now.

    Every refusal is a stable reason code so the scheduler can record it on the
    existing diagnostic ledger instead of inventing a second state store.
    """
    if not isinstance(observation, WakeObservation):
        raise ValueError("wake contact requires a WakeObservation")
    at = _as_utc(at, field="wake contact time")
    if not purpose_allowed:
        return WakeContactDecision(False, "purpose_disabled", observation)
    if observation.state not in AWAKE_STATES:
        return WakeContactDecision(False, "not_awake_likely", observation)
    if observation.confidence < int(minimum_confidence):
        return WakeContactDecision(False, "confidence_below_threshold", observation)
    if observation.woke_at is None:
        return WakeContactDecision(False, "no_wake_time", observation)
    if at < observation.woke_at:
        return WakeContactDecision(False, "woke_in_future", observation)
    if at - observation.woke_at > timedelta(minutes=max(1, int(window_minutes))):
        return WakeContactDecision(False, "wake_window_elapsed", observation)
    if already_contacted:
        return WakeContactDecision(False, "wake_contact_already_sent", observation)
    if quiet_hours:
        return WakeContactDecision(False, "quiet_hours", observation)
    try:
        local = at.astimezone(ZoneInfo(observation.zone))
    except Exception:
        return WakeContactDecision(False, "timezone_unavailable", observation)
    if not int(morning_start) <= local.hour < int(morning_end):
        return WakeContactDecision(False, "outside_wake_window", observation)
    return WakeContactDecision(True, "wake_contact_candidate", observation)

def intent_summary(observation, *, limit=5):
    """A prompt-safe thought summary: timing evidence, never a sighting claim."""
    if not isinstance(observation, WakeObservation) or observation.state not in AWAKE_STATES:
        return ""
    labels = []
    for item in observation.evidence[-max(1, int(limit)):]:
        label = SIGNALS[item.kind].label
        if label not in labels:
            labels.append(label)
    observed = "；".join(labels) or "用户侧近期活动状态发生变化"
    return (
        f"这是一次由用户醒来线索触发的可选问候机会，当前判断为{observation.state}"
        f"（参考置信度 {observation.confidence}/100）。可用的线索只有：{observed}。"
        "这些线索只说明用户侧输入或设备状态在近期从休息转为活动，不证明你亲眼看见、听见或确认了对方已经起床。"
        "不要说出「我看到你醒了」「我一直在看着你」，也不要复述设备、传感器、数值、字段名或观察过程。"
        "把这次机会只用于选择开口时机和语气：像自然地碰上这个早晨那样，先带来一句自己的话、一个轻话题或一点真实近况；"
        "不追问睡了多久、不评价作息、不要求报平安，也不把起床变成打卡。"
        "如果此刻没有自然的话、线索仍不够确定，或对方可能并不想被打扰，就选择 skip。"
    )

def _snapshot_time(item, at):
    for key in ("captured_at", "sample_at", "last_report_at"):
        value = item.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
    age = item.get("age_seconds")
    if isinstance(age, (int, float)) and age >= 0:
        return at - timedelta(seconds=float(age))
    return at


def evidence_from_mobile_snapshot(snapshot, *, at, previous_steps=None):
    """Map the Reality gateway's typed mobile projection into wake evidence.

    Only closed enum identifiers and timestamps are read.  Raw labels, titles
    and any free text are deliberately ignored, so no app name or message word
    ever influences the judgement.
    """
    at = _as_utc(at, field="mobile snapshot time")
    out = []
    if not isinstance(snapshot, Mapping):
        return ()
    device = snapshot.get("device")
    if isinstance(device, Mapping) and device.get("available") and device.get("online"):
        out.append(evidence("device_reconnected", _snapshot_time(device, at), source="mobile.device"))
    activity = snapshot.get("activity")
    if isinstance(activity, Mapping) and activity.get("available") and not activity.get("stale"):
        out.append(evidence("screen_resumed", _snapshot_time(activity, at), source="mobile.activity"))
    telemetry = snapshot.get("telemetry")
    if isinstance(telemetry, Mapping) and telemetry.get("available"):
        reading = telemetry.get("activity")
        reading = reading if isinstance(reading, Mapping) else {}
        state = str(reading.get("state") or "").strip().lower()
        observed_at = _snapshot_time(reading or telemetry, at)
        if state in TELEMETRY_AWAKE_STATES:
            out.append(evidence("motion_activity", observed_at, source="mobile.telemetry"))
        elif state in TELEMETRY_SLEEP_STATES:
            out.append(evidence("sleep_reported", observed_at, source="mobile.telemetry"))
        elif state in TELEMETRY_RESTING_STATES:
            out.append(evidence("resting_reported", observed_at, source="mobile.telemetry"))
        for measurement in telemetry.get("measurements") or ():
            if not isinstance(measurement, Mapping):
                continue
            if str(measurement.get("type") or "").strip().lower() != "steps":
                continue
            value = measurement.get("value")
            if not isinstance(value, (int, float)):
                continue
            if previous_steps is not None and value <= previous_steps:
                continue
            if previous_steps is None and value <= 0:
                continue
            out.append(evidence("steps_increased", _snapshot_time(measurement, at),
                                source="mobile.telemetry", detail="steps_moved"))
            break
    return tuple(out)


def evidence_from_wakeup_session(alarm, *, at):
    """Map the existing wake-up session receipt into wake evidence."""
    at = _as_utc(at, field="wakeup session time")
    session = alarm.get("contact_session") if isinstance(alarm, Mapping) else None
    if not isinstance(session, Mapping):
        return ()
    status = str(session.get("status") or "").strip().lower()
    stamp = session.get("feedback_at") or session.get("completed_at")
    observed_at = (datetime.fromtimestamp(float(stamp), tz=timezone.utc)
                   if isinstance(stamp, (int, float)) and stamp > 0 else at)
    if status == "acknowledged":
        return (evidence("alarm_acknowledged", observed_at, source="wakeup.session"),)
    if status == "snoozed":
        return (evidence("sleep_reported", observed_at, source="wakeup.session", confidence=80),)
    return ()


def evidence_from_private_input(*, received_at, previous_input_at=None,
                                minimum_gap_minutes=45):
    """A private input proves the user is awake; it is a wake transition only
    when it follows a quiet gap.  An ongoing exchange stays with the normal
    reply path and is not re-labelled as a wake episode.
    """
    at = _as_utc(received_at, field="private input time")
    if previous_input_at is None:
        return (evidence("explicit_input", at, source="conversation.input", confidence=80),)
    previous = _as_utc(previous_input_at, field="previous input time")
    if (at - previous).total_seconds() < max(0, int(minimum_gap_minutes)) * 60:
        return ()
    return (evidence("explicit_input", at, source="conversation.input"),)
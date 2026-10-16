"""Main-chain habit learning, authenticated targets and receipt-backed feedback."""

from datetime import timedelta
import json

from companion_v2.execution.models import TaskError, digest, encode, stamp
from companion_v2.model_gateway.models import ToolSpec
from ..group_observation import parse_moment
from . import prompts
from .store import BehaviorStore, MAX_HABITS, owner_key


LEARN = "group.behavior.learn"
PLAN = "group.behavior.plan"
FEEDBACK = "group.behavior.feedback"
ANNOTATIONS = frozenset({LEARN, FEEDBACK})


def _spec(action, description, properties, required):
    return ToolSpec(action, description, encode({"type": "object", "properties": properties,
                    "required": required, "additionalProperties": False}))


def _text(limit):
    return {"type": "string", "minLength": 1, "maxLength": limit}


EVIDENCE = {"type": "array", "items": _text(80), "minItems": 1, "maxItems": 8, "uniqueItems": True}
CATALOG = (
    _spec(LEARN, "从本群已认证成员发言学习或修订本角色的互动习惯；只记笔记，不发送，可随后旁听。", {
        "habit_id": _text(80), "label": _text(48), "situation": _text(240), "action": _text(240),
        "boundaries": _text(240), "cues": {"type": "array", "items": _text(40), "maxItems": 6, "uniqueItems": True},
        "evidence_handles": EVIDENCE, "member_handle": _text(80)},
        ["label", "situation", "action", "boundaries", "cues", "evidence_handles"]),
    _spec(PLAN, "为本轮真实回复选择一个已学互动习惯和本群已认证对象；只准备真实 @，不直接发送。", {
        "habit_id": _text(80), "target_handle": _text(80), "reason": _text(240)},
        ["habit_id", "target_handle", "reason"]),
    _spec(FEEDBACK, "依据互动对象在实际发送调用返回后的真实回应评估一次互动；没有回应不算喜欢。", {
        "attempt_id": _text(80), "assessment": {"type": "string", "enum": ["welcomed", "unwelcome", "unclear"]},
        "evidence_handles": EVIDENCE, "reason": _text(240)},
        ["attempt_id", "assessment", "evidence_handles", "reason"]),
)


class GroupBehavior:
    def __init__(self, messages):
        self.messages, self.runtime = messages, messages.runtime
        self.store = BehaviorStore(self.runtime)
        self._frames = {}

    def settings(self, context):
        from ..participation import group_participation_settings
        return group_participation_settings(self.runtime, context)

    def catalog_for(self, context):
        self.messages.group_context.authorize(context, self.messages.tasks.now())
        settings = self.settings(context)
        enabled = {LEARN: settings["enable_group_behavior_learning"],
                   PLAN: settings["enable_group_behavior_imitation"],
                   FEEDBACK: settings["enable_group_behavior_feedback"]}
        return tuple(spec for spec in CATALOG if enabled[spec.action])

    def authorize(self, context, switch):
        self.messages.group_context.authorize(context, self.messages.tasks.now())
        if not self.settings(context)[switch]:
            raise TaskError("group_behavior_disabled", "this behavior feature is disabled")

    def observe(self, context, *, text, speaker_id, received_at, event_id):
        if (not event_id or not text or speaker_id != context.actor.principal.native_account_id
                or speaker_id == context.scope.account_id):
            return
        settings = self.settings(context)
        if not any(settings[name] for name in ("enable_group_behavior_learning", "enable_group_behavior_imitation",
                                               "enable_group_behavior_feedback")):
            return
        event_key = digest([owner_key(context), str(event_id)])
        with self.runtime.transaction() as connection:
            observations = self.store.observations(context)
            if any(item["key"] == event_key for item in observations):
                return
            observations.append({"key": event_key, "speaker_id": speaker_id,
                "received_at": stamp(received_at), "text": " ".join(text.split())[:600]})
            observations = [item for item in observations
                if (parse_moment(item["received_at"]) or received_at) >= received_at - timedelta(hours=48)]
            self.store.write_observations(connection, context, observations)

    def frame(self, context, native_input):
        """Freeze evidence once per admitted turn, shared by prompt and native tools."""
        key = digest([context.key, native_input.event_id])
        if key in self._frames:
            return self._frames[key]
        self.observe(context, text=native_input.text, speaker_id=native_input.principal.native_account_id,
                     received_at=native_input.at, event_id=native_input.event_id)
        document = self.store.read(context)
        at = native_input.at
        observations = [item for item in self.store.observations(context)
                        if at - timedelta(hours=48) <= parse_moment(item["received_at"]) <= at][-16:]
        members = {"member-" + digest([key, item["speaker_id"]])[:20]: item["speaker_id"] for item in observations}
        handles = {account: handle for handle, account in members.items()}
        evidence = {"behavior-evidence-" + digest([key, item["key"]])[:20]: item for item in observations}
        frame = {"key": key, "members": members, "evidence": evidence,
                 "habits": [dict(item) for item in document["habits"][-12:]],
                 "attempts": [dict(item) for item in document["attempts"][-6:]], "handles": handles}
        if len(self._frames) >= 128:
            self._frames.pop(next(iter(self._frames)))
        self._frames[key] = frame
        return frame

    def instruction(self, context, native_input):
        settings = self.settings(context)
        if not any(settings[name] for name in ("enable_group_behavior_learning", "enable_group_behavior_imitation",
                                               "enable_group_behavior_feedback")):
            return ""
        frame = self.frame(context, native_input)
        payload = {
            "learning_enabled": settings["enable_group_behavior_learning"],
            "imitation_enabled": settings["enable_group_behavior_imitation"],
            "feedback_enabled": settings["enable_group_behavior_feedback"],
            "members": [{"handle": handle, "speaker_id": account} for handle, account in frame["members"].items()],
            "human_evidence": [{"handle": handle, "speaker_handle": frame["handles"][item["speaker_id"]],
                                "text": item["text"][:320], "received_at": item["received_at"]}
                               for handle, item in frame["evidence"].items()],
            "habits": [{key: item[key] for key in ("habit_id", "label", "situation", "action", "boundaries",
                       "member_id", "updated_at", "enabled", "member_feedback")} for item in frame["habits"]],
            "recent_attempts": frame["attempts"],
        }
        guidance = settings["group_behavior_guidance"]
        return prompts.INSTRUCTION + ("\n管理员互动偏好：" + guidance if guidance else "") + "\n" + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"))

    def _evidence(self, frame, arguments):
        handles = arguments.get("evidence_handles", ())
        if not handles or any(handle not in frame["evidence"] for handle in handles):
            raise TaskError("group_behavior_evidence_invalid", "use human evidence offered to this exact turn")
        return [frame["evidence"][handle] for handle in handles]

    def learn(self, context, frame, arguments, *, at):
        self.authorize(context, "enable_group_behavior_learning")
        if any(not arguments[name].strip() for name in ("label", "situation", "action", "boundaries")):
            raise TaskError("invalid_tool_arguments", "habit descriptions must not be blank")
        evidence = self._evidence(frame, arguments)
        member = frame["members"].get(arguments.get("member_handle"), "")
        if arguments.get("member_handle") and (not member or member not in {item["speaker_id"] for item in evidence}):
            raise TaskError("group_behavior_member_invalid", "a personal habit needs that member's own evidence")
        with self.runtime.transaction() as connection:
            document = self.store.read(context)
            identifier = arguments.get("habit_id")
            previous = next((item for item in document["habits"] if item["habit_id"] == identifier), None)
            if identifier and previous is None:
                raise TaskError("group_behavior_habit_missing", "the habit does not belong to this role and group")
            if previous is not None and not arguments.get("member_handle"):
                member = previous["member_id"]
            if previous is None:
                previous = next((item for item in document["habits"] if item["label"].casefold() == arguments["label"].strip().casefold()
                                 and item["member_id"] == member), None)
            if previous is None and len(document["habits"]) >= MAX_HABITS:
                raise TaskError("group_behavior_storage_full", "review existing habits before adding more")
            identifier = previous["habit_id"] if previous else "habit-" + digest([owner_key(context), frame["key"], arguments["label"]])[:24]
            item = {"habit_id": identifier, "member_id": member, "updated_at": stamp(at),
                    "enabled": previous.get("enabled", True) if previous else True,
                    "member_feedback": previous.get("member_feedback", {}) if previous else {},
                    **{name: arguments[name].strip() for name in ("label", "situation", "action", "boundaries")},
                    "cues": [value.strip() for value in arguments["cues"] if value.strip()],
                    "evidence": list({row["key"]: row for row in [*(previous or {}).get("evidence", ()), *evidence]}.values())[-12:]}
            document["habits"] = [row for row in document["habits"] if row["habit_id"] != identifier] + [item]
            self.store.write(connection, context, document)
        return {"habit_id": identifier, "saved": True, "sent": False}

    def plan(self, context, frame, arguments, *, turn_id, call_id, at):
        self.authorize(context, "enable_group_behavior_imitation")
        account = frame["members"].get(arguments["target_handle"])
        if not account or account == context.scope.account_id:
            raise TaskError("group_behavior_target_invalid", "choose one authenticated member of this group")
        with self.runtime.transaction() as connection:
            document = self.store.read(context)
            habit = next((item for item in document["habits"] if item["habit_id"] == arguments["habit_id"]), None)
            if habit is None or not habit["enabled"]:
                raise TaskError("group_behavior_habit_missing", "choose an enabled habit of this role and group")
            if habit["member_id"] and habit["member_id"] != account:
                raise TaskError("group_behavior_target_invalid", "this individual habit belongs to another member")
            previous = next((item for item in document["attempts"] if item["turn_id"] == turn_id), None)
            if previous:
                if previous["habit_id"] != habit["habit_id"] or previous["target_id"] != account:
                    raise TaskError("group_behavior_plan_fixed", "the target for this reply has already been selected")
                return dict(previous)
            attempt = {"attempt_id": "interaction-" + digest([turn_id, call_id])[:24], "turn_id": turn_id,
                       "habit_id": habit["habit_id"], "label": habit["label"], "target_id": account,
                       "reason": arguments["reason"].strip(), "planned_at": stamp(at), "state": "planned",
                       "feedback": []}
            document["attempts"].append(attempt)
            self.store.write(connection, context, document)
            return dict(attempt)

    def delivery(self, context, attempt_id, *, stage, text, at):
        with self.runtime.transaction() as connection:
            document = self.store.read(context)
            attempt = next((item for item in document["attempts"] if item["attempt_id"] == attempt_id), None)
            if attempt is None:
                return
            if stage == "returned":
                attempt["returned_at"] = stamp(at)
                attempt["text"] = text[:400]
                attempt["platform_confirmed"] = False
            if attempt["state"] not in ("unknown", "returned") or stage == "unknown":
                attempt["state"] = stage
            self.store.write(connection, context, document)

    def validate_plan(self, context, plan):
        self.authorize(context, "enable_group_behavior_imitation")
        document = self.store.read(context)
        habit = next((item for item in document["habits"] if item["habit_id"] == plan["habit_id"]), None)
        attempt = next((item for item in document["attempts"] if item["attempt_id"] == plan["attempt_id"]), None)
        if (habit is None or not habit["enabled"] or attempt is None
                or attempt["target_id"] != plan["target_id"]
                or (habit["member_id"] and habit["member_id"] != plan["target_id"])):
            raise TaskError("group_behavior_habit_missing", "the selected interaction is no longer available")

    def feedback(self, context, frame, arguments, *, at):
        self.authorize(context, "enable_group_behavior_feedback")
        evidence = self._evidence(frame, arguments)
        with self.runtime.transaction() as connection:
            document = self.store.read(context)
            attempt = next((item for item in document["attempts"] if item["attempt_id"] == arguments["attempt_id"]), None)
            returned = parse_moment(attempt.get("returned_at")) if attempt else None
            if (returned is None or attempt["state"] != "returned"
                    or any(item["speaker_id"] != attempt["target_id"] or parse_moment(item["received_at"]) <= returned for item in evidence)):
                raise TaskError("group_behavior_feedback_invalid", "feedback needs the target's own response after a returned send")
            feedback = {"assessment": arguments["assessment"], "reason": arguments["reason"].strip(),
                        "at": stamp(at), "evidence": [item["key"] for item in evidence]}
            if not any(item["evidence"] == feedback["evidence"] for item in attempt["feedback"]):
                attempt["feedback"] = [*attempt["feedback"], feedback][-6:]
                habit = next((item for item in document["habits"] if item["habit_id"] == attempt["habit_id"]), None)
                if habit is not None:
                    members = habit.setdefault("member_feedback", {})
                    members[attempt["target_id"]] = [*members.get(attempt["target_id"], ()), feedback][-4:]
                    if len(members) > 32:
                        oldest = min(members, key=lambda key: members[key][-1]["at"])
                        del members[oldest]
                self.store.write(connection, context, document)
            return {"attempt_id": attempt["attempt_id"], "saved": True, "sent": False}

    def candidate(self, context, *, text):
        """Learned cues only admit a model decision; they never execute an action."""
        return any(item["enabled"] and any(cue.casefold() in text.casefold() for cue in item["cues"])
                   for item in self.store.read(context)["habits"])

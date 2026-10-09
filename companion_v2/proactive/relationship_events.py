"""Evidence-led contact candidates from explicit statements in a private turn."""

import re
from datetime import timedelta

from companion_v2.execution.models import TaskError, digest, require, stamp
from companion_v2.foundation.refs import ScopeKind

from .contact_models import ContactIntent
from .models import EvidenceSnapshot, Opportunity, Thought, ThoughtKind


PURPOSE_CUES = {
    "affection": re.compile(r"想你|喜欢你|爱你|在乎你|抱抱|miss you|love you|care about you", re.I),
    "care": re.compile(r"累了|疲惫|难过|伤心|焦虑|压力大|撑不住|tired|exhausted|sad|anxious", re.I),
    "play": re.compile(r"开个玩笑|讲个笑话|玩游戏|一起玩|好玩的|joke|play a game|let's play", re.I),
    "repair": re.compile(r"你刚才|你之前|刚刚那句|你说错|让我不舒服|别这样|stop doing|that hurt", re.I),
    "invitation": re.compile(r"一起.{0,12}(看|玩|去|做|吃|听)|我们.{0,12}(一起|下次)|let's (watch|play|go|try)", re.I),
}


class RelationshipContactEvents:
    """Surface only explicit, recent private language; the model still decides to skip."""

    def __init__(self, contacts, messages):
        self.contacts, self.messages = contacts, messages
        self.runtime = contacts.runtime

    def _text(self, context, event, at):
        if context.scope.kind is not ScopeKind.PRIVATE:
            return ""
        if any(getattr(event, name, ()) for name in ("images", "audios", "videos", "forwards", "quotes")):
            return ""
        source = self.messages._read_source(event.source, context, event.capability, at)
        if source.content_hash != event.input_hash or digest(source.payload) != source.content_hash:
            raise TaskError("contact_input_changed", "relationship candidate requires its original private text")
        return source.payload[:8192]

    def select(self, context, preferences, event, at, *, purpose=None):
        text = self._text(context, event, at)
        if not text:
            return None
        for candidate_purpose, cue in PURPOSE_CUES.items():
            if purpose is not None and purpose != candidate_purpose:
                continue
            if preferences.reason(candidate_purpose):
                continue
            match = cue.search(text)
            if match is None:
                continue
            opportunity = Opportunity("relationship-" + digest([context.key, event.scoped_key, candidate_purpose]),
                context.scope, event.received_at, event.received_at + timedelta(
                    seconds=preferences.values["event_max_age_seconds"]))
            task_id = self.contacts.task_id(context, opportunity)
            if self.runtime.read_one("SELECT 1 FROM execution_tasks WHERE task_id = ?", (task_id,)) or self.runtime.read_one(
                    "SELECT 1 FROM proactive_contacts WHERE task_id = ?", (task_id,)):
                continue
            marker = {"purpose": candidate_purpose, "event_key": event.scoped_key, "event_hash": digest(text),
                      "expires_at": stamp(opportunity.expires_at)}
            thought = Thought("relationship-thought-" + digest(marker), opportunity, ThoughtKind.CONVERSATION,
                f"对方最近明确提到一段与{candidate_purpose}有关的话。只围绕原话判断是否适合自然回应；不要把提示分类当成事实，也可以跳过。",
                EvidenceSnapshot(context.scope, at, (event.source,)), 1.0)
            return opportunity, (ContactIntent(candidate_purpose, thought),), marker
        return None

    def validate(self, context, event, marker, at):
        if type(marker) is not dict or set(marker) != {"purpose", "event_key", "event_hash", "expires_at"}:
            raise TaskError("contact_relationship_invalid", "relationship candidate marker is invalid")
        if (marker["purpose"] not in PURPOSE_CUES or marker["event_key"] != event.scoped_key
                or not marker["expires_at"]):
            raise TaskError("contact_relationship_changed", "relationship candidate no longer matches its turn")
        text = self._text(context, event, at)
        match = PURPOSE_CUES[marker["purpose"]].search(text)
        if digest(text) != marker["event_hash"] or match is None or event.received_at > at:
            raise TaskError("contact_relationship_changed", "explicit relationship evidence changed")
        preferences = require(self.contacts.preferences.read(context, observed_at=at))
        preferences.require_contact(marker["purpose"])
        expires = event.received_at + timedelta(
            seconds=preferences.values["event_max_age_seconds"])
        if marker["expires_at"] != stamp(expires) or at >= expires:
            raise TaskError("contact_relationship_expired", "relationship evidence is no longer current")

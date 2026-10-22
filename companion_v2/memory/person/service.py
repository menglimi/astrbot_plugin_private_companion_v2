"""Acquaintance cards on the shared memory store: counting, names and bounded views.

The card is a memory_views row under the person owner. Counting joins the
original intake transaction and stays idempotent per event, because replays
return before the input row is inserted again. Names are recorded by the host
from the authenticated OneBot event; nothing here reads V1 data or trusts
content-provided identity.
"""

import json

from companion_v2.conversation.foreground import ContextContribution, ContributionState
from companion_v2.execution.models import TaskError, encode, require, stamp
from companion_v2.foundation.refs import ScopeKind
from companion_v2.memory.models import text
from .access import OWNER, card_id, owner_for_subject, owner_key, resolve_subject
from .models import KIND, MAX_GROUP_CARDS, aggregate, bind_route, clean_name, count_input, display_name, empty_document


UPSERT = """INSERT INTO memory_views VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
    ON CONFLICT(view_id) DO UPDATE SET revision = excluded.revision,
        document_json = excluded.document_json, updated_at = excluded.updated_at"""


class PersonAcquaintance:
    def __init__(self, runtime, tasks):
        self.runtime, self.tasks = runtime, tasks
        self.settings = None  # Attached by the composition root; absence keeps the feature off.

    def available(self, context):
        if self.settings is None:
            return False
        try:
            return bool(self.settings.read(context).get("person.acquaintance_enabled"))
        except Exception:
            return False

    def check(self, context, *, at=None):
        at = at or self.tasks.now()
        require(self.tasks.check_context_access(context, action="conversation.reply", observed_at=at))
        require(self.tasks.identity.authorize(context.actor, scope=context.scope, capability="text", observed_at=at))

    # -- intake -------------------------------------------------------------

    def intake_observer(self, context):
        """Resolve once per admitted message whether counting participates, so the
        configuration read stays outside the intake transaction."""
        if not self.available(context):
            return None
        return self.observe if self.settings.read(context).get(
            "person.learning.acquaintance_learning_enabled", True) else None

    def observe(self, context, event, connection):
        """Count one admitted input. Optional derived data never rejects intake."""
        owner = owner_key(context)
        identifier = card_id(owner)
        row = connection.execute("SELECT revision, document_json FROM memory_views WHERE view_id = ? AND kind = ?",
                                 (identifier, KIND)).fetchone()
        document = json.loads(row["document_json"]) if row is not None else empty_document()
        bind_route(document, context)
        count_input(document, context.scope, stamp(event.received_at), event.received_at.date().isoformat())
        connection.execute(UPSERT, (identifier, owner, KIND, row["revision"] + 1 if row is not None else 1,
                                    encode(document), encode({"owner": OWNER}), stamp(self.tasks.now())))

    # -- platform names -----------------------------------------------------

    def record_platform_names(self, context, *, group_id=None, nickname=None, card=None):
        """Store host-captured platform display names, bumping the card only when
        a value actually changes so routine messages do not churn revisions."""
        if self.settings is None:
            return
        nickname, card = clean_name(nickname), clean_name(card)
        if nickname is None and card is None:
            return
        owner = owner_key(context)
        with self.runtime.transaction() as connection:
            identifier = card_id(owner)
            row = connection.execute("SELECT revision, document_json FROM memory_views WHERE view_id = ? AND kind = ?",
                                     (identifier, KIND)).fetchone()
            document = json.loads(row["document_json"]) if row is not None else empty_document()
            bind_route(document, context)
            changed = False
            if nickname and nickname != document["platform_nickname"]:
                document["platform_nickname"] = nickname
                document["nickname_updated_at"] = stamp(self.tasks.now())
                changed = True
            if group_id is not None and card:
                cards = document["group_cards"]
                current = cards.get(group_id)
                if current is None or current["card"] != card:
                    if current is None and len(cards) >= MAX_GROUP_CARDS:
                        cards.pop(min(cards, key=lambda key: cards[key]["updated_at"]))
                    cards[group_id] = {"card": card, "updated_at": stamp(self.tasks.now())}
                    changed = True
            if not changed:
                return
            connection.execute(UPSERT, (identifier, owner, KIND, row["revision"] + 1 if row is not None else 1,
                                        encode(document), encode({"owner": OWNER}), stamp(self.tasks.now())))

    # -- reads ---------------------------------------------------------------

    def row(self, owner):
        return self.runtime.read_one("SELECT * FROM memory_views WHERE view_id = ? AND owner_key = ? AND kind = ?",
                                     (card_id(owner), owner, KIND))

    def projection(self, context, document, *, budget, with_contexts=False):
        name, basis = display_name(document, context.scope)
        summary = aggregate(document)
        payload = {"display_name": name, "name_basis": basis, "msg_count": summary["msg_count"],
                   "active_days": summary["active_days"], "first_seen": summary["first_seen"],
                   "last_seen": summary["last_seen"]}
        if with_contexts:
            payload["contexts"] = {key: {"msg_count": entry["msg_count"], "active_days": entry["active_days"],
                                         "last_seen": entry["last_seen"]}
                                   for key, entry in sorted(document["contexts"].items())}
        while len(encode(payload).encode("utf-8")) > budget and payload:
            for key in ("contexts", "first_seen", "last_seen", "display_name", "name_basis"):
                if key in payload:
                    del payload[key]
                    break
            else:
                break
        return payload

    def capture(self, context, at):
        material = self.card_contribution(context, at)
        return {"version": 1, "context_key": context.key,
                "payload": material.payload if material is not None else None}

    @staticmethod
    def validate_snapshot(snapshot, context):
        if (type(snapshot) is not dict or set(snapshot) != {"version", "context_key", "payload"}
                or snapshot["version"] != 1 or snapshot["context_key"] != context.key
                or snapshot["payload"] is not None and (type(snapshot["payload"]) is not str
                    or len(snapshot["payload"].encode("utf-8")) > 4096)):
            raise TaskError("acquaintance_snapshot_invalid", "card must retain its original conversation")

    def card_contribution(self, context, at, *, snapshot=None):
        """The current speaker's bounded card, or None when the feature has
        nothing to say. A failed optional check only drops the card."""
        if not self.available(context):
            return None
        try:
            self.check(context, at=at)
        except TaskError:
            return None
        if snapshot is not None:
            self.validate_snapshot(snapshot, context)
            if snapshot["payload"] is None:
                return None
            # Intake may advance counters while a tool is running. This card
            # describes what the sealed turn saw; access is still checked above.
            return ContextContribution("person-speaker-card", OWNER, "current_person_card",
                                       ContributionState.READY, snapshot["payload"])
        row = self.row(owner_key(context))
        if row is None or row["state"] != "active":
            return None
        payload = self.projection(context, json.loads(row["document_json"]),
                                  budget=self.settings.read(context)["person.acquaintance_card_chars"])
        return ContextContribution("person-speaker-card", OWNER, "current_person_card",
                                   ContributionState.READY, encode(payload))

    def private_contact(self, context, at):
        """True when this group speaker also has a private context with the role.

        This is a boolean identity link only.  Private text, private timing and
        the relationship memory itself stay outside the group audience.
        """
        if context.scope.kind is not ScopeKind.GROUP or not self.available(context):
            return False
        try:
            self.check(context, at=at)
        except TaskError:
            return False
        row = self.row(owner_key(context))
        if row is None or row["state"] != "active":
            return False
        document = json.loads(row["document_json"])
        return bool(document.get("contexts", {}).get("private"))

    # -- model tool ----------------------------------------------------------

    def recall(self, context, speaker_id=None):
        """Project one member's card for the current conversation. The default
        subject is the current speaker; a number must resolve through the
        trusted binding table."""
        self.check(context)
        if not self.available(context):
            return {"state": "disabled"}
        if speaker_id is None:
            subject_id = context.actor.subject.subject_id
            native = context.actor.principal.native_account_id
        else:
            speaker = text(speaker_id, "speaker_id", 32)
            if not speaker.isdigit():
                raise TaskError("acquaintance_member_unknown", "speaker references use native account numbers")
            subject_id = resolve_subject(self.runtime, context, speaker)
            native = speaker
        row = self.row(owner_for_subject(context, subject_id))
        if row is None or row["state"] != "active":
            return {"speaker_id": native, "state": "unacquainted"}
        budget = self.settings.read(context)["person.acquaintance_card_chars"] if self.settings is not None else 1024
        payload = self.projection(context, json.loads(row["document_json"]), budget=budget, with_contexts=True)
        return {"speaker_id": native, "state": "known", **payload}

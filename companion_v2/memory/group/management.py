"""Core governance of a collective archive, without impersonating its members."""

from dataclasses import asdict, dataclass
import json

from companion_v2.execution.models import TaskError, digest, encode, require, stamp
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.memory import codec
from companion_v2.memory.models import integer, text
from companion_v2.sources.privacy import redact_text
from companion_v2.storage.models import OperationState
from .access import group_owner_key
from .service import KIND, OWNER as MEMORY_OWNER


OWNER = "management.memory.group"


@dataclass(frozen=True)
class GroupMemoryTarget:
    installation_id: str
    platform_id: str
    bot_id: str
    account_id: str
    group_id: str
    session_id: str
    role_id: str

    def __post_init__(self):
        for key, value in asdict(self).items():
            text(value, key, 512)

    @property
    def key(self):
        role = SubjectRef(self.installation_id, SubjectKind.BOT, self.role_id)
        return group_owner_key(self.installation_id, self.platform_id, self.bot_id, self.account_id,
                               self.group_id, self.session_id, role)

    @property
    def authorization_scope(self):
        # This is an administrator's archive address, not a fabricated member conversation.
        return ScopeRef(self.installation_id, "companion", ScopeKind.SYSTEM, "group-memory:" + self.key)


class GroupMemoryManagement:
    def __init__(self, memory, operator):
        self.memory, self.operator = memory, operator
        self.runtime, self.tasks = memory.runtime, memory.tasks
        self.access = ObjectAccessPolicy(self.runtime)

    def _check(self, target):
        if type(target) is not GroupMemoryTarget:
            raise TaskError("group_memory_target_required", "management needs a fixed collective archive address")
        require(self.access.feature_access(self.operator, scope=target.authorization_scope,
            action="memory.manage", observed_at=self.tasks.now()))

    def _row(self, target, identifier, revision=None):
        text(identifier, "memory_id", 512)
        row = self.runtime.read_one("SELECT * FROM memory_views WHERE owner_key = ? AND kind = ? AND view_id = ?",
                                    (target.key, KIND, identifier))
        if row is None:
            raise TaskError("group_memory_unavailable", "memory is unavailable to this group archive")
        if revision is not None:
            integer(revision, "revision")
            if row["revision"] != revision:
                raise TaskError("group_memory_revision_conflict", "refresh the current group statement revision")
        return row

    def _token(self, target, row):
        return digest([target, self.operator, self.access.revision, self.access.identity.revision,
                       row["view_id"], row["revision"], row["state"], row["document_json"], row["source_json"]])

    def _item(self, target, row):
        item = {"memory_id": row["view_id"], "revision": row["revision"], "state": row["state"],
                "statement": None, "updated_at": row["updated_at"], "view_token": self._token(target, row)}
        try:
            visible, _ = self.memory._read_row(row)
            item.update(visible)
        except TaskError as error:
            item["unavailable_reason"] = error.code
        return item

    @outcome
    def list(self, target, *, after_id="", limit=20, state="active"):
        text(after_id, "after_id", 512, empty=True)
        integer(limit, "limit", 1, 50)
        if state not in ("active", "retracted"):
            raise ValueError("select active or retracted group statements")
        with self.runtime.read_snapshot():
            self._check(target)
            # Use the existing owner/kind/state/view_id index. Invalid sources
            # remain metadata-only entries; filtering cannot hide an unbounded scan.
            rows = self.runtime.read_all("""SELECT * FROM memory_views WHERE owner_key = ? AND kind = ?
                AND state = ? AND view_id > ? ORDER BY view_id LIMIT ?""",
                (target.key, KIND, state, after_id, limit + 1))
            return {"items": [self._item(target, row) for row in rows[:limit]],
                    "next_cursor": rows[limit - 1]["view_id"] if len(rows) > limit else None,
                    "operator_id": self.operator.subject.subject_id, "target": asdict(target),
                    "supported_visibility": ["group"], "physical_erasure": "not_supported"}

    @outcome
    def detail(self, target, *, memory_id, revision, start=0, chars=2048):
        integer(start, "start", 0, 65536)
        integer(chars, "chars", 1, 4096)
        with self.runtime.read_snapshot():
            self._check(target)
            row = self._row(target, memory_id, revision)
            item = self._item(target, row)
            if item.get("unavailable_reason"):
                return {"item": item, "evidence": None}
            record, original, event = self.memory.access._input_for_owner(
                target.key, json.loads(row["document_json"])["evidence"])
            if start > len(record.payload):
                raise ValueError("source offset is outside the original group input")
            end = min(len(record.payload), start + chars)
            return {"item": item, "evidence": {"text": record.payload[start:end], "start": start, "end": end,
                "total_chars": len(record.payload), "has_more": end < len(record.payload),
                "speaker_id": original.actor.principal.native_account_id, "said_at": stamp(event.received_at),
                "attribution": "member_statement", "view": "original_group_input"}}

    @outcome
    def safety_hits(self, target, *, after_id="", limit=20, member_id="", review_state=""):
        """Read bounded safety evidence for this group after current authorization."""
        text(after_id, "after_id", 512, empty=True)
        integer(limit, "limit", 1, 50)
        text(member_id, "member_id", 512, empty=True)
        text(review_state, "review_state", 32, empty=True)
        if review_state and review_state not in ("pending", "reviewed", "dismissed"):
            raise ValueError("select pending, reviewed, dismissed, or leave review_state empty")
        with self.runtime.read_snapshot():
            self._check(target)
            clauses = ["owner_key = ?", "hit_id > ?"]
            parameters = [target.key, after_id]
            if member_id:
                clauses.append("member_id = ?")
                parameters.append(member_id)
            if review_state:
                clauses.append("review_state = ?")
                parameters.append(review_state)
            parameters.append(limit + 1)
            rows = self.runtime.read_all(
                "SELECT * FROM group_member_safety_hits WHERE " + " AND ".join(clauses)
                + " ORDER BY hit_id LIMIT ?", tuple(parameters))
            items = []
            for row in rows[:limit]:
                try:
                    evidence = json.loads(row["evidence_json"])
                except (TypeError, ValueError):
                    evidence = {"unavailable": "invalid_evidence"}
                try:
                    review = json.loads(row["review_json"]) if row["review_json"] else None
                except (TypeError, ValueError):
                    review = {"unavailable": "invalid_review"}
                items.append({"hit_id": row["hit_id"], "member_id": row["member_id"],
                    "message_id": row["message_id"], "rule_id": row["rule_id"],
                    "direction": row["direction"], "severity": row["severity"],
                    "evidence": evidence, "occurred_at": row["occurred_at"],
                    "review_state": row["review_state"], "review": review,
                    "permissions_changed": False})
            return {"items": items,
                    "next_cursor": rows[limit - 1]["hit_id"] if len(rows) > limit else None,
                    "operator_id": self.operator.subject.subject_id, "target": asdict(target),
                    "evidence_only": True, "permissions_changed": False}

    @outcome
    def review_safety_hit(self, target, *, hit_id, review_state, operation_key, note=""):
        """Record an administrator review without changing member permissions."""
        text(hit_id, "hit_id", 512)
        text(review_state, "review_state", 32)
        text(operation_key, "operation_key", 512)
        note = redact_text(text(note, "note", 2048, empty=True))
        if review_state not in ("pending", "reviewed", "dismissed"):
            raise ValueError("select pending, reviewed, or dismissed")
        with self.runtime.transaction() as connection:
            self._check(target)
            row = connection.execute(
                "SELECT * FROM group_member_safety_hits WHERE owner_key = ? AND hit_id = ?",
                (target.key, hit_id)).fetchone()
            if row is None:
                raise TaskError("group_safety_hit_unavailable", "this safety hit is unavailable to the group archive")
            previous = json.loads(row["review_json"]) if row["review_json"] else None
            if previous and previous.get("operation_key") == operation_key:
                if previous.get("review_state") != review_state or previous.get("note", "") != note:
                    raise TaskError("group_safety_review_conflict", "this operation key has different arguments")
                return {"hit_id": hit_id, "review_state": row["review_state"],
                        "review": previous, "replayed": True, "permissions_changed": False}
            # An operation key is the caller's idempotency identity for the
            # whole group archive. Reusing it for another hit would make a
            # replay ambiguous, so reject it even when that other hit is not
            # the one currently being reviewed.
            for candidate in connection.execute(
                    "SELECT hit_id, review_json FROM group_member_safety_hits "
                    "WHERE owner_key = ? AND review_json IS NOT NULL AND hit_id != ?",
                    (target.key, hit_id)).fetchall():
                try:
                    candidate_review = json.loads(candidate["review_json"])
                except (TypeError, ValueError):
                    continue
                if candidate_review.get("operation_key") == operation_key:
                    raise TaskError("group_safety_review_conflict", "this operation key belongs to another safety hit")
            now = self.tasks.now()
            review = {"operation_key": operation_key, "review_state": review_state,
                      "note": note, "operator_id": self.operator.subject.subject_id,
                      "reviewed_at": stamp(now)}
            connection.execute(
                "UPDATE group_member_safety_hits SET review_state = ?, review_json = ? WHERE owner_key = ? AND hit_id = ?",
                (review_state, encode(review), target.key, hit_id))
            return {"hit_id": hit_id, "review_state": review_state, "review": review,
                    "replayed": False, "permissions_changed": False}

    def _receipt(self, target, identifier):
        return self.runtime.read_one("""SELECT * FROM memory_operations WHERE operation_id = ?
            AND owner_key = ? AND caller_id = ? AND namespace = ?""",
            (identifier, target.key, self.operator.subject.subject_id, OWNER))

    @outcome
    def operation(self, target, *, operation_id):
        text(operation_id, "operation_id", 512)
        with self.runtime.read_snapshot():
            self._check(target)
            row = self._receipt(target, operation_id)
            if row is None:
                raise TaskError("group_memory_operation_unavailable", "this operator has no such archive receipt")
            return json.loads(row["result_json"])

    @outcome
    def retract(self, target, *, memory_id, expected_revision, view_token, operation_key, reason=""):
        text(memory_id, "memory_id", 512)
        integer(expected_revision, "expected_revision")
        text(view_token, "view_token", 512)
        text(operation_key, "operation_key", 512)
        reason = redact_text(text(reason, "reason", 512, empty=True))
        with self.runtime.transaction() as connection:
            self._check(target)
            identifier = "group-memory-admin-" + digest([target.key, self.operator.subject, operation_key])
            parameters = dict(action="retract", memory_id=memory_id, expected_revision=expected_revision,
                              view_token=view_token, reason=reason)
            previous = self._receipt(target, identifier)
            if previous is not None:
                if previous["payload_hash"] != digest(parameters):
                    raise TaskError("group_memory_operation_conflict", "this operation key has different arguments")
                return json.loads(previous["result_json"])
            row = self._row(target, memory_id, expected_revision)
            if view_token != self._token(target, row):
                raise TaskError("group_memory_view_stale", "refresh the archive after identity or policy changes")
            if row["state"] != "active":
                raise TaskError("group_memory_inactive", "the statement was already retracted")
            now = self.tasks.now()
            if stamp(now) < row["updated_at"]:
                raise TaskError("group_memory_clock_regression", "archive time cannot move backwards")
            operation = OperationRef(identifier, OWNER, target.authorization_scope, VersionRef(identifier, 1), identifier)
            require(self.memory.operations.reserve(operation, parameter_hash=digest(parameters), observed_at=now))
            source = codec.source(json.loads(row["source_json"]))
            role = SubjectRef(target.installation_id, SubjectKind.BOT, target.role_id)
            scope = source.scope
            if (source.owner != MEMORY_OWNER or source.source_id != memory_id
                    or source.version != VersionRef(memory_id, expected_revision) or scope.kind is not ScopeKind.GROUP
                    or group_owner_key(scope.installation_id, scope.platform, scope.bot_id, scope.account_id,
                        scope.native_scope_id, scope.session_id, role) != target.key):
                raise TaskError("group_memory_changed", "the archive source no longer identifies this group statement")
            state = connection.execute("""SELECT governance_revision FROM sources
                WHERE source_id = ? AND lineage_id = ? AND source_revision = ?""",
                (source.source_id, source.version.lineage_id, source.version.revision)).fetchone()
            if state is not None:
                require(self.memory.sources.revoke(source, expected_governance_revision=state[0], observed_at=now))
            document = json.loads(row["document_json"])
            connection.execute("INSERT OR IGNORE INTO memory_guards VALUES (?, ?, ?, ?, 'retracted')",
                (target.key, memory_id, digest(document["evidence"]), memory_id))
            connection.execute("UPDATE memory_views SET revision = ?, state = 'retracted', updated_at = ? WHERE view_id = ?",
                (expected_revision + 1, stamp(now), memory_id))
            result = {"operation_id": identifier, "memory_id": memory_id, "revision": expected_revision + 1,
                      "state": "retracted", "operator_id": self.operator.subject.subject_id,
                      "attribution": "administrator_action", "reason": reason, "updated_at": stamp(now),
                      "forgetting": "logical", "physical_erasure": "not_performed", "delivery": "not_started"}
            connection.execute("INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, target.key, self.operator.subject.subject_id, OWNER, digest(parameters), encode(parameters),
                 encode({"target": target, "operator": self.operator}), "retracted", encode(result), stamp(now), stamp(now)))
            require(self.memory.operations.transition(identifier, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=now))
            return result

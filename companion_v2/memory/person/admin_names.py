"""Core-operator edits to a person's administrator-assigned display name."""

import json

from companion_v2.execution.models import TaskError, digest, encode, require, stamp
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import OperationRef, ScopeKind, ScopeRef, VersionRef
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from .management import MAX_DIRECTORY, _route_tuple
from .models import KIND, directory_display_name


OPERATION_OWNER = "memory.person.admin_name"
MAX_OPERATION_KEY = 128
MAX_NAME = 64


class PersonAcquaintanceNameManagement:
    def __init__(self, runtime):
        self.runtime = runtime
        self.access = ObjectAccessPolicy(runtime)
        self.operations = OperationRepository(runtime)

    @outcome
    def set_nickname(self, operator, *, routes, subject_id, platform, bot_id, account_id,
                     role_id, native_account_id, nickname, expected_revision,
                     operation_key, observed_at):
        values = (subject_id, platform, bot_id, account_id, role_id, native_account_id)
        if (any(type(value) is not str or not value or value != value.strip() or len(value) > 512
                for value in values)
                or type(nickname) is not str or len(nickname) > 256
                or type(expected_revision) is not int or expected_revision < 1
                or type(operation_key) is not str or not operation_key.strip()
                or len(operation_key) > MAX_OPERATION_KEY):
            raise TaskError("person_nickname_command_invalid", "provide a directory person, name, revision and operation key")

        nickname = " ".join(nickname.split()) or None
        if nickname is not None and len(nickname) > MAX_NAME:
            raise TaskError("person_nickname_invalid", "the administrator name must be at most 64 characters")

        route = {"platform": platform, "bot_id": bot_id, "account_id": account_id, "role_id": role_id}
        route_key = _route_tuple(route)
        if route_key not in {_route_tuple(item) for item in routes}:
            raise TaskError("acquaintance_person_unknown", "this person is outside the current Bot and role directory")

        observed = stamp(observed_at)
        self._authorize(operator, observed_at)
        route_scope_key = digest([self.runtime.installation_id, route_key, subject_id])
        identifier = "person-admin-name-" + digest([
            self.runtime.installation_id, route_scope_key, operator.subject.subject_id, operation_key])
        parameters = {"subject_id": subject_id, "platform": platform, "bot_id": bot_id,
                     "account_id": account_id, "role_id": role_id,
                     "native_account_id": native_account_id, "nickname": nickname,
                     "expected_revision": expected_revision}
        parameter_hash = digest([encode(operator.principal), encode(operator.subject),
                                 operator.binding_id, operator.binding_revision, parameters])
        operation = OperationRef(identifier, OPERATION_OWNER,
            ScopeRef(self.runtime.installation_id, "companion", ScopeKind.SYSTEM,
                     "person-admin-name:" + route_scope_key),
            VersionRef(identifier, 1), identifier)

        with self.runtime.transaction() as connection:
            self._authorize(operator, observed_at)
            previous = connection.execute("SELECT * FROM memory_operations WHERE operation_id = ?",
                                          (identifier,)).fetchone()
            if previous is not None:
                if (previous["namespace"] != "person.admin_nickname"
                        or previous["payload_hash"] != parameter_hash):
                    raise TaskError("person_nickname_operation_conflict", "this operation key was used with different arguments")
                if previous["state"] != OperationState.COMPLETED.value:
                    raise TaskError("person_nickname_operation_unresolved", "the previous name change is unresolved")
                result = json.loads(previous["result_json"])
                result["replayed"] = True
                return result

            row = self._card(connection, route, subject_id, native_account_id)
            if row is None:
                raise TaskError("acquaintance_person_unknown", "this person is not in the current V2 acquaintance directory")
            if row["revision"] != expected_revision:
                raise TaskError("person_nickname_revision_conflict", "the acquaintance card changed; refresh before saving")

            receipt = require(self.operations.reserve(operation, parameter_hash=parameter_hash,
                                                       observed_at=observed_at))
            if receipt.replayed:
                raise TaskError("person_nickname_operation_unresolved", "the previous name change has no completed domain receipt")

            document = json.loads(row["document_json"])
            changed = document.get("admin_nickname") != nickname
            revision = row["revision"]
            updated_at = row["updated_at"]
            if changed:
                document["admin_nickname"] = nickname
                document["admin_nickname_updated_at"] = observed
                revision += 1
                updated_at = observed
                updated = connection.execute(
                    """UPDATE memory_views SET revision = ?, document_json = ?, updated_at = ?
                       WHERE view_id = ? AND owner_key = ? AND kind = ? AND state = 'active' AND revision = ?""",
                    (revision, encode(document), updated_at, row["view_id"], row["owner_key"], KIND, expected_revision))
                if updated.rowcount != 1:
                    raise TaskError("person_nickname_revision_conflict", "the acquaintance card changed; refresh before saving")

            display_name, name_basis = directory_display_name(document)
            result = {"operation_id": identifier, "subject_id": subject_id,
                      "admin_nickname": document.get("admin_nickname"),
                      "admin_nickname_updated_at": document.get("admin_nickname_updated_at"),
                      "display_name": display_name, "name_basis": name_basis,
                      "revision": revision, "updated_at": updated_at,
                      "changed": changed, "replayed": False}
            connection.execute("INSERT INTO memory_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, row["owner_key"], operator.subject.subject_id, "person.admin_nickname",
                 parameter_hash, encode(parameters), encode({"operator": operator, "route": route}),
                 OperationState.COMPLETED.value, encode(result), observed, observed))
            require(self.operations.transition(identifier, expected_state=OperationState.ACCEPTED,
                next_state=OperationState.COMPLETED, observed_at=observed_at))
            return result

    def _authorize(self, operator, observed_at):
        require(self.access.feature_access(operator,
            scope=ScopeRef(self.runtime.installation_id, "companion", ScopeKind.SYSTEM, "page.management"),
            action="memory.manage", observed_at=observed_at))

    @staticmethod
    def _card(connection, route, subject_id, native_account_id):
        rows = connection.execute(
            """SELECT * FROM memory_views WHERE kind = ? AND state = 'active'
               ORDER BY updated_at DESC, view_id DESC LIMIT ?""", (KIND, MAX_DIRECTORY)).fetchall()
        for row in rows:
            try:
                document = json.loads(row["document_json"])
                pinned = document.get("route")
                if (type(pinned) is dict and _route_tuple(pinned) == _route_tuple(route)
                        and pinned.get("subject_id") == subject_id
                        and document.get("native_account_id") == native_account_id):
                    return row
            except (TypeError, ValueError):
                continue
        return None

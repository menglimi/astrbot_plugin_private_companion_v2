"""Bounded derived records, isolated by role and group rather than native session."""

import json

from companion_v2.execution.models import digest, encode
from companion_v2.foundation.refs import ScopeKind


VERSION = "conversation.group_behavior.v1"
MAX_OBSERVATIONS = 64
MAX_HABITS = 32
MAX_ATTEMPTS = 32


def owner_key(context):
    scope = context.scope
    if scope.kind is not ScopeKind.GROUP:
        raise ValueError("behavior learning requires a group")
    return digest([VERSION, scope.installation_id, scope.platform, scope.bot_id,
                   scope.account_id, scope.native_scope_id, context.role_binding.role.subject_id])


class BehaviorStore:
    def __init__(self, runtime):
        self.runtime = runtime

    def read(self, context):
        return self.read_owner(owner_key(context))

    def read_owner(self, owner):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?", (VERSION + ":" + owner,))
        if row is not None:
            value = json.loads(row["value"])
            if value.get("version") == VERSION:
                return value
        return {"version": VERSION, "habits": [], "attempts": []}

    def observations(self, context):
        row = self.runtime.read_one("SELECT value FROM runtime_metadata WHERE key = ?",
                                    (VERSION + ".observations:" + owner_key(context),))
        return json.loads(row["value"]) if row else []

    def write_observations(self, connection, context, observations):
        connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (VERSION + ".observations:" + owner_key(context), encode(observations[-MAX_OBSERVATIONS:])))

    def write(self, connection, context, document):
        scope = context.scope
        document["owner"] = {"installation_id": scope.installation_id, "platform": scope.platform,
            "bot_id": scope.bot_id, "account_id": scope.account_id, "group_id": scope.native_scope_id,
            "role_id": context.role_binding.role.subject_id}
        self.write_owner(connection, owner_key(context), document)

    def write_owner(self, connection, owner, document):
        document["attempts"] = document["attempts"][-MAX_ATTEMPTS:]
        # Capacity bounds storage, never the frequency of social interaction.
        connection.execute("""INSERT INTO runtime_metadata(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (VERSION + ":" + owner, encode(document)))

    def groups(self, context):
        rows = self.runtime.read_all("SELECT key, value FROM runtime_metadata WHERE key LIKE ?", (VERSION + ":%",))
        result = []
        for row in rows:
            document = json.loads(row["value"])
            owner = document.get("owner", {})
            if (owner.get("installation_id") == context.scope.installation_id
                    and owner.get("bot_id") == context.scope.bot_id
                    and owner.get("role_id") == context.role_binding.role.subject_id):
                result.append((row["key"].removeprefix(VERSION + ":"), document))
        return result

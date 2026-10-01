"""Transactional object notices for rebuildable memory recall, without bodies."""


RECALL_TABLES = frozenset({"memory_recall_changes"})


def conversation_owner(context):
    return "json_array(" + ", ".join(
        f"json_extract({context}, '$.{path}')" for path in (
            "role_binding.scope.installation_id", "role_binding.scope.bot_id", "role_binding.role.subject_id",
            "actor.subject.subject_id",
        )
    ) + ")"


def notices(table, kind, identifier, columns, *, conversation=False):
    statements = []
    for action, aliases in (("INSERT", ("NEW",)), ("UPDATE", ("OLD", "NEW")), ("DELETE", ("OLD",))):
        body = []
        for alias in aliases:
            owner = conversation_owner("b.context_json") if conversation else f"{alias}.owner_key"
            source = f" FROM conversation_batches b WHERE b.batch_id = {alias}.batch_id" if conversation else ""
            if action == "UPDATE" and alias == "OLD":
                changed_owner = "OLD.batch_id IS NOT NEW.batch_id" if conversation else "OLD.owner_key IS NOT NEW.owner_key"
                source += (" AND " if conversation else " WHERE ") + changed_owner
            body.append(f"""INSERT INTO memory_recall_changes(owner, kind, object_id, token)
                SELECT {owner}, '{kind}', {alias}.{identifier}, lower(hex(randomblob(16))){source};""")
        event = f"UPDATE OF {columns}" if action == "UPDATE" else action
        changed = " WHEN " + " OR ".join(f"OLD.{column} IS NOT NEW.{column}" for column in columns.split(", ")) if action == "UPDATE" else ""
        statements.append(f"CREATE TRIGGER recall_{kind}_{action.lower()} AFTER {event} ON {table}{changed} BEGIN "
                          + " ".join(body) + " END")
    return tuple(statements)


RECALL_STATEMENTS = (
    """CREATE TABLE memory_recall_changes (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        owner TEXT NOT NULL, kind TEXT NOT NULL, object_id TEXT NOT NULL, token TEXT NOT NULL
    )""",
    "CREATE INDEX memory_recall_feed_idx ON memory_recall_changes(owner, kind, sequence)",
    "CREATE INDEX memory_guard_evidence_idx ON memory_guards(owner_key, evidence_key, reason)",
    # Seed pointers once during the atomic schema upgrade. Query-time catch-up is
    # paged from this log; there is no full-text backfill or model call on startup.
    f"""INSERT INTO memory_recall_changes(owner, kind, object_id, token)
        SELECT {conversation_owner('b.context_json')}, 'human', i.event_key, lower(hex(randomblob(16)))
        FROM conversation_inputs i JOIN conversation_batches b ON b.batch_id = i.batch_id""",
    f"""INSERT INTO memory_recall_changes(owner, kind, object_id, token)
        SELECT {conversation_owner('b.context_json')}, 'reply', h.part_id, lower(hex(randomblob(16)))
        FROM conversation_sent_history h JOIN conversation_batches b ON b.batch_id = h.batch_id""",
    """INSERT INTO memory_recall_changes(owner, kind, object_id, token)
        SELECT owner_key, 'experience', view_id, lower(hex(randomblob(16))) FROM memory_views""",
    """INSERT INTO memory_recall_changes(owner, kind, object_id, token)
        SELECT owner_key, 'fact', atom_id, lower(hex(randomblob(16))) FROM memory_atoms""",
) + notices("conversation_inputs", "human", "event_key", "event_json, withdrawn, batch_id", conversation=True) \
    + notices("conversation_sent_history", "reply", "part_id", "batch_id, delivered_at, receipt_ref", conversation=True) \
    + notices("memory_views", "experience", "view_id", "owner_key, revision, state, document_json, source_json") \
    + notices("memory_atoms", "fact", "atom_id", "owner_key, namespace, revision, state, record_json, source_json")

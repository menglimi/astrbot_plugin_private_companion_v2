"""Calendar and role-state owners, their revisions, maintenance and platform receipts."""

RECORD_TABLES = ("calendar", "role_state")
STATE_TABLES = {"role_state_schedules", "platform_presence_operations"}
STATE_STATEMENTS = []
for owner in RECORD_TABLES:
    STATE_TABLES.update({owner + "_records", owner + "_history", owner + "_receipts"})
    STATE_STATEMENTS.extend((
        f"""CREATE TABLE {owner}_records (
            owner_key TEXT NOT NULL, record_id TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK(revision > 0),
            updated_at TEXT NOT NULL, record_json TEXT NOT NULL,
            PRIMARY KEY(owner_key, record_id))""",
        f"""CREATE TABLE {owner}_history (
            owner_key TEXT NOT NULL, record_id TEXT NOT NULL, revision INTEGER NOT NULL,
            operation_id TEXT NOT NULL REFERENCES operations(operation_id), record_json TEXT NOT NULL,
            PRIMARY KEY(owner_key, record_id, revision),
            FOREIGN KEY(owner_key, record_id) REFERENCES {owner}_records(owner_key, record_id))""",
        f"""CREATE TABLE {owner}_receipts (
            operation_id TEXT PRIMARY KEY NOT NULL REFERENCES operations(operation_id),
            owner_key TEXT NOT NULL, record_id TEXT NOT NULL, result_json TEXT NOT NULL)""",
    ))
STATE_STATEMENTS.extend((
    """CREATE TABLE role_state_schedules (
        context_key TEXT PRIMARY KEY NOT NULL, context_json TEXT NOT NULL,
        settings_json TEXT NOT NULL, next_at TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK(revision > 0),
        enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
        result_json TEXT)""",
    "CREATE INDEX role_state_due_idx ON role_state_schedules(enabled, next_at, context_key)",
    """CREATE TABLE platform_presence_operations (
        operation_id TEXT PRIMARY KEY NOT NULL,
        account_key TEXT NOT NULL, context_key TEXT NOT NULL,
        desired_hash TEXT NOT NULL, state TEXT NOT NULL,
        request_json TEXT NOT NULL, updated_at TEXT NOT NULL,
        result_json TEXT NOT NULL)""",
    "CREATE INDEX platform_presence_account_idx ON platform_presence_operations(account_key, updated_at, operation_id)",
))
STATE_STATEMENTS = tuple(STATE_STATEMENTS)

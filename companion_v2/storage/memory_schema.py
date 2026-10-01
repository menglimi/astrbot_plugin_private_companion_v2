"""Authoritative memory tables live in the unified V2 database.

Search terms and vectors belong to a separate rebuildable database. No indexes
in this module constitute another writable fact store.
"""

MEMORY_TABLES = frozenset({"memory_atoms", "memory_revisions", "memory_operations", "memory_changes",
    "memory_guards", "memory_views", "memory_reflections", "memory_sessions", "memory_handles",
    "source_dependencies", "memory_schedules"})

MEMORY_STATEMENTS = (
    """CREATE TABLE memory_schedules (
        schedule_id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, revision INTEGER NOT NULL,
        context_json TEXT NOT NULL, settings_json TEXT NOT NULL, enabled INTEGER NOT NULL,
        next_at TEXT NOT NULL, covered_until TEXT NOT NULL, pending_batch TEXT
    )""",
    "CREATE INDEX memory_schedule_due_idx ON memory_schedules(enabled, next_at, schedule_id)",
    """CREATE TABLE memory_atoms (
        atom_id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, namespace TEXT NOT NULL,
        subject TEXT NOT NULL, fact_key TEXT NOT NULL, single_value INTEGER NOT NULL,
        revision INTEGER NOT NULL, state TEXT NOT NULL, scope_json TEXT NOT NULL,
        record_json TEXT NOT NULL, source_json TEXT NOT NULL, updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX memory_owner_idx ON memory_atoms(owner_key, namespace, state, atom_id)",
    "CREATE UNIQUE INDEX memory_single_idx ON memory_atoms(owner_key, fact_key) WHERE single_value = 1 AND state = 'active'",
    """CREATE TABLE memory_revisions (
        atom_id TEXT NOT NULL REFERENCES memory_atoms(atom_id), revision INTEGER NOT NULL,
        state TEXT NOT NULL, record_json TEXT NOT NULL, source_json TEXT NOT NULL,
        PRIMARY KEY(atom_id, revision)
    )""",
    """CREATE TABLE memory_operations (
        operation_id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, caller_id TEXT NOT NULL,
        namespace TEXT NOT NULL, payload_hash TEXT NOT NULL, proposal_json TEXT,
        context_json TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX memory_pending_idx ON memory_operations(owner_key, state, operation_id)",
    """CREATE TABLE memory_changes (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, owner_key TEXT NOT NULL, namespace TEXT NOT NULL,
        atom_id TEXT NOT NULL, revision INTEGER NOT NULL, kind TEXT NOT NULL, occurred_at TEXT NOT NULL
    )""",
    "CREATE INDEX memory_changes_owner_idx ON memory_changes(owner_key, sequence)",
    """CREATE TABLE memory_guards (
        owner_key TEXT NOT NULL, fact_key TEXT NOT NULL, evidence_key TEXT NOT NULL,
        atom_id TEXT NOT NULL, reason TEXT NOT NULL,
        PRIMARY KEY(owner_key, fact_key, evidence_key)
    )""",
    """CREATE TABLE memory_views (
        view_id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, kind TEXT NOT NULL,
        revision INTEGER NOT NULL, state TEXT NOT NULL, document_json TEXT NOT NULL,
        source_json TEXT NOT NULL, updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX memory_views_owner_idx ON memory_views(owner_key, kind, state, view_id)",
    """CREATE TABLE memory_reflections (
        batch_id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, request_hash TEXT NOT NULL,
        context_json TEXT NOT NULL, manifest_json TEXT NOT NULL, state TEXT NOT NULL,
        result_json TEXT, receipts_json TEXT NOT NULL, task_id TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX memory_reflections_owner_idx ON memory_reflections(owner_key, state, batch_id)",
    """CREATE TABLE memory_sessions (
        session_id TEXT PRIMARY KEY, context_key TEXT NOT NULL, owner_key TEXT NOT NULL,
        expires_at TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0, chars INTEGER NOT NULL DEFAULT 0,
        state_json TEXT NOT NULL
    )""",
    """CREATE TABLE memory_handles (
        handle TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES memory_sessions(session_id),
        evidence_json TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    "CREATE INDEX memory_handles_session_idx ON memory_handles(session_id, handle)",
    """CREATE TABLE source_dependencies (
        dependent_id TEXT NOT NULL, dependent_lineage TEXT NOT NULL, dependent_revision INTEGER NOT NULL,
        input_id TEXT NOT NULL, input_lineage TEXT NOT NULL, input_revision INTEGER NOT NULL,
        PRIMARY KEY(dependent_id, dependent_lineage, dependent_revision, input_id, input_lineage, input_revision),
        FOREIGN KEY(dependent_id, dependent_lineage, dependent_revision)
            REFERENCES sources(source_id, lineage_id, source_revision),
        FOREIGN KEY(input_id, input_lineage, input_revision)
            REFERENCES sources(source_id, lineage_id, source_revision)
    )""",
    "CREATE INDEX source_dependants_idx ON source_dependencies(input_id, input_lineage, input_revision)",
)

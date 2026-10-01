"""Storage owned by reviewable role self-review guidance.

A self-review run produces model-authored, evidence-bound suggestions about the
role's own observable behaviour. They are candidates only: nothing here changes
prompts, configuration, memory or behaviour until an authenticated operator
accepts an item, and accepted guidance always carries a short expiry.
"""

SELF_REVIEW_STATEMENTS = (
    """CREATE TABLE role_self_review_runs (
        run_id TEXT PRIMARY KEY NOT NULL,
        owner_key TEXT NOT NULL,
        scope_key TEXT NOT NULL,
        window_json TEXT NOT NULL,
        material_hash TEXT NOT NULL,
        summary TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending', 'decided', 'expired')),
        created_at TEXT NOT NULL,
        decided_at TEXT,
        UNIQUE(owner_key, scope_key, run_id)
    )""",
    """CREATE TABLE role_self_review_items (
        item_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL REFERENCES role_self_review_runs(run_id),
        owner_key TEXT NOT NULL,
        scope_key TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('try_next_time', 'keep', 'ask_user', 'no_change')),
        observation TEXT NOT NULL,
        next_action TEXT NOT NULL,
        confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
        evidence_json TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending', 'accepted', 'rejected')),
        created_at TEXT NOT NULL,
        decided_at TEXT,
        decided_by TEXT,
        decision_key TEXT,
        ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
        UNIQUE(run_id, ordinal)
    )""",
    "CREATE INDEX role_self_review_item_queue_idx ON role_self_review_items(owner_key, scope_key, state, created_at, item_id)",
    "CREATE INDEX role_self_review_item_active_idx ON role_self_review_items(owner_key, scope_key, state, expires_at)",
)

SELF_REVIEW_TABLES = frozenset({"role_self_review_runs", "role_self_review_items"})

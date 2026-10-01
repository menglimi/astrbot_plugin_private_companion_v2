"""Storage owned by reviewable growth progress suggestions."""

PROGRESS_STATEMENTS = (
    """CREATE TABLE role_growth_progress_reviews (
        review_id TEXT PRIMARY KEY NOT NULL,
        owner_key TEXT NOT NULL,
        scope_key TEXT NOT NULL,
        receipt_operation_id TEXT NOT NULL,
        growth_id TEXT,
        base_revision INTEGER CHECK(base_revision > 0),
        source_json TEXT NOT NULL,
        progress_note TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending', 'accepted', 'rejected', 'skipped')),
        created_at TEXT NOT NULL,
        decided_at TEXT,
        decided_by TEXT,
        decision_key TEXT,
        applied_revision INTEGER CHECK(applied_revision > 0),
        UNIQUE(owner_key, scope_key, receipt_operation_id),
        FOREIGN KEY(owner_key, growth_id) REFERENCES role_growth_items(owner_key, growth_id)
    )""",
    "CREATE INDEX role_growth_progress_queue_idx ON role_growth_progress_reviews(owner_key, scope_key, state, created_at, review_id)",
)

PROGRESS_TABLES = frozenset({"role_growth_progress_reviews"})

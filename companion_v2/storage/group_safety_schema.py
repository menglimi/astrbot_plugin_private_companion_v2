"""Schema additions for deterministic group member safety evidence."""

GROUP_SAFETY_STATEMENTS = (
    """CREATE TABLE group_member_safety_hits (
        hit_id TEXT PRIMARY KEY NOT NULL,
        owner_key TEXT NOT NULL,
        member_id TEXT NOT NULL,
        message_id TEXT,
        rule_id TEXT NOT NULL,
        direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound')),
        severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 3),
        evidence_json TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        review_state TEXT NOT NULL CHECK(review_state IN ('pending', 'reviewed', 'dismissed')),
        review_json TEXT,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX group_member_safety_hits_time_idx ON group_member_safety_hits(owner_key, occurred_at, hit_id)",
    "CREATE INDEX group_member_safety_hits_member_idx ON group_member_safety_hits(owner_key, member_id, occurred_at)",
)
GROUP_SAFETY_TABLES = frozenset({"group_member_safety_hits"})

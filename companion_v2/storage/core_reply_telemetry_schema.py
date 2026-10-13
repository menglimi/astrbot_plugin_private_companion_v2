"""Optional body-free telemetry for replies executed by AstrBot itself."""


TABLE = "astrbot_core_reply_observations"
STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS astrbot_core_reply_observations (
        turn_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
        role_key TEXT NOT NULL, context_key TEXT NOT NULL, scope_kind TEXT NOT NULL,
        context_json TEXT NOT NULL, received_at TEXT NOT NULL,
        observed_at TEXT NOT NULL, record_json TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS astrbot_core_reply_role_idx ON astrbot_core_reply_observations(role_key, received_at, turn_id)",
)

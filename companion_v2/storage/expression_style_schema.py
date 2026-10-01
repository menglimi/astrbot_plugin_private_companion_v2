"""Storage owned by reviewable expression-style learning.

Style learning is about form only -- sentence rhythm, punctuation, diction,
formatting. It never infers identity, personality, mood, health, relationships
or stable preferences from samples. Observations stay candidates until an
authenticated operator adopts them, and adopted rules are reversible.
"""

EXPRESSION_STATEMENTS = (
    """CREATE TABLE expression_style_runs (
        run_id TEXT PRIMARY KEY NOT NULL,
        owner_key TEXT NOT NULL,
        scope_key TEXT NOT NULL,
        sample_json TEXT NOT NULL,
        material_hash TEXT NOT NULL,
        summary TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending', 'decided', 'expired')),
        created_at TEXT NOT NULL,
        decided_at TEXT,
        UNIQUE(owner_key, scope_key, run_id)
    )""",
    """CREATE TABLE expression_style_signals (
        signal_id TEXT PRIMARY KEY NOT NULL,
        run_id TEXT NOT NULL REFERENCES expression_style_runs(run_id),
        owner_key TEXT NOT NULL,
        scope_key TEXT NOT NULL,
        dimension TEXT NOT NULL CHECK(dimension IN
            ('sentence_rhythm', 'emoji', 'punctuation', 'directness', 'diction', 'formatting', 'other')),
        observation TEXT NOT NULL,
        proposal TEXT NOT NULL,
        confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
        evidence_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending', 'adopted', 'rejected', 'retired')),
        created_at TEXT NOT NULL,
        decided_at TEXT,
        decided_by TEXT,
        decision_key TEXT,
        ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
        UNIQUE(run_id, ordinal)
    )""",
    "CREATE INDEX expression_style_signal_queue_idx ON expression_style_signals(owner_key, scope_key, state, created_at, signal_id)",
    "CREATE INDEX expression_style_signal_adopted_idx ON expression_style_signals(owner_key, scope_key, state, dimension)",
)

EXPRESSION_TABLES = frozenset({"expression_style_runs", "expression_style_signals"})

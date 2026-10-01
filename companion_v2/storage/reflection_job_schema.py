"""Explicit, durable requests to continue one existing reflection batch."""

REFLECTION_JOB_TABLES = frozenset({"memory_reflection_jobs"})
REFLECTION_JOB_STATEMENTS = (
    """CREATE TABLE memory_reflection_jobs (
        job_id TEXT PRIMARY KEY NOT NULL,
        batch_id TEXT NOT NULL REFERENCES memory_reflections(batch_id),
        owner_key TEXT NOT NULL,
        context_json TEXT NOT NULL,
        operator_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('queued', 'complete', 'blocked')),
        next_at TEXT NOT NULL,
        result_code TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX memory_reflection_job_due_idx ON memory_reflection_jobs(state, next_at, job_id)",
    "CREATE INDEX memory_reflection_job_batch_idx ON memory_reflection_jobs(batch_id, created_at, job_id)",
)

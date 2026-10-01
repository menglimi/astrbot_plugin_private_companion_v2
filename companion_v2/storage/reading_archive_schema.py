"""Schema additions for the reading archive.

The archive is a pure provider contract: the body holds catalog entries, the source
reference that points at the provider-owned asset, and governance/reading state. It
never stores the work's text or images, so no asset format is frozen here and a later
provider can supply novels or manga through the same columns.
"""

READING_ARCHIVE_STATEMENTS = (
    """CREATE TABLE reading_archive_entries (
        owner_key TEXT NOT NULL,
        entry_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('novel', 'manga', 'other')),
        title TEXT NOT NULL,
        author TEXT NOT NULL DEFAULT '',
        origin TEXT NOT NULL CHECK(origin IN ('provider', 'manual')),
        source_json TEXT,
        provider_id TEXT,
        provider_version TEXT,
        asset_ref TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        state TEXT NOT NULL CHECK(state IN ('available', 'reading', 'finished', 'withdrawn')),
        revision INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, entry_id)
    )""",
    "CREATE INDEX reading_archive_entries_state_idx ON reading_archive_entries(owner_key, state, updated_at)",
    "CREATE INDEX reading_archive_entries_origin_idx ON reading_archive_entries(owner_key, origin, title)",
    """CREATE TABLE reading_archive_progress (
        owner_key TEXT NOT NULL,
        entry_id TEXT NOT NULL,
        position_json TEXT NOT NULL,
        percent INTEGER NOT NULL CHECK(percent BETWEEN 0 AND 100),
        note TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, entry_id),
        FOREIGN KEY(owner_key, entry_id) REFERENCES reading_archive_entries(owner_key, entry_id)
    )""",
    """CREATE TABLE reading_archive_reviews (
        owner_key TEXT NOT NULL,
        review_id TEXT NOT NULL,
        entry_id TEXT NOT NULL,
        body TEXT NOT NULL,
        rating INTEGER CHECK(rating IS NULL OR rating BETWEEN 1 AND 5),
        evidence_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(owner_key, review_id),
        FOREIGN KEY(owner_key, entry_id) REFERENCES reading_archive_entries(owner_key, entry_id)
    )""",
    "CREATE INDEX reading_archive_reviews_entry_idx ON reading_archive_reviews(owner_key, entry_id, created_at)",
    """CREATE TABLE reading_archive_consents (
        owner_key TEXT NOT NULL,
        entry_id TEXT NOT NULL,
        subject_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('granted', 'revoked')),
        revision INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, entry_id, subject_json)
    )""",
)
READING_ARCHIVE_TABLES = frozenset({
    "reading_archive_entries",
    "reading_archive_progress",
    "reading_archive_reviews",
    "reading_archive_consents",
})

# C2-3b: when the shelf last spoke. Stored rather than held in memory, because a
# throttle that resets on restart is exactly how a "rare" behaviour becomes chatty.
# It lands after the archive itself, so it carries its own version.
READING_ARCHIVE_TRIGGER_STATEMENTS = (
    """CREATE TABLE reading_archive_triggers (
        owner_key TEXT NOT NULL,
        action TEXT NOT NULL CHECK(action IN ('share', 'ask')),
        last_at TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(owner_key, action)
    )""",
)
READING_ARCHIVE_TRIGGER_TABLES = frozenset({"reading_archive_triggers"})

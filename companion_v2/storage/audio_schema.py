"""Voice originals and listening views, separate from image storage."""

AUDIO_TABLES = frozenset({"conversation_audio_payloads"})
AUDIO_STATEMENTS = (
    """CREATE TABLE conversation_audio_payloads (
        parent_id TEXT NOT NULL, parent_lineage TEXT NOT NULL, parent_revision INTEGER NOT NULL,
        position INTEGER NOT NULL CHECK(position >= 0),
        source_id TEXT NOT NULL, source_lineage TEXT NOT NULL, source_revision INTEGER NOT NULL,
        asset_id TEXT NOT NULL, asset_lineage TEXT NOT NULL, asset_revision INTEGER NOT NULL,
        wave_asset_id TEXT NOT NULL, wave_asset_lineage TEXT NOT NULL, wave_asset_revision INTEGER NOT NULL,
        descriptor_json TEXT NOT NULL, content BLOB NOT NULL, waveform BLOB NOT NULL,
        PRIMARY KEY(parent_id, parent_lineage, parent_revision, position),
        UNIQUE(source_id, source_lineage, source_revision),
        FOREIGN KEY(parent_id, parent_lineage, parent_revision)
            REFERENCES sources(source_id, lineage_id, source_revision),
        FOREIGN KEY(source_id, source_lineage, source_revision)
            REFERENCES sources(source_id, lineage_id, source_revision),
        FOREIGN KEY(asset_id, asset_lineage, asset_revision)
            REFERENCES assets(asset_id, lineage_id, asset_revision),
        FOREIGN KEY(wave_asset_id, wave_asset_lineage, wave_asset_revision)
            REFERENCES assets(asset_id, lineage_id, asset_revision)
    )""",
)

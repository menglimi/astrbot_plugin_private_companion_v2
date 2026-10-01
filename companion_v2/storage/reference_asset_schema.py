"""Registered reference material for one role.

Reference images and wardrobe items are *assets*, not configuration. V2's
configuration values are scalars only (``companion_v2/configuration/models.py``
``Scalar = bool | int | float | str``), so a V1-style list of pictures with an
inline file path has no representation here by design — storing a path in config
text would bypass asset ownership and visibility checks.

What a row holds is a *registration*: which stored asset the material refers to,
the SHA-256 the registrant asserted, and what the material may be used for. The
bytes stay with the owner that produced them; this table never carries them, so
no image format is frozen and a provider can supply material through the same
columns.

``role`` is the V1 use vocabulary, kept verbatim so a later planner can match a
material to a slot instead of guessing from "this picture was used".
"""

REFERENCE_ASSET_STATEMENTS = (
    """CREATE TABLE reference_assets (
        owner_key TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('reference_image', 'wardrobe_item')),
        role TEXT NOT NULL CHECK(role IN ('identity', 'outfit', 'pose', 'scene', 'style',
                                          'background', 'continuity', 'edit_source', 'edit_mask')),
        label TEXT NOT NULL DEFAULT '',
        content_hash TEXT NOT NULL CHECK(length(content_hash) = 64),
        size_bytes INTEGER NOT NULL CHECK(size_bytes > 0 AND size_bytes <= 20971520),
        mime_type TEXT NOT NULL,
        media_ref TEXT NOT NULL,
        source TEXT NOT NULL CHECK(source IN ('operator', 'provider')),
        state TEXT NOT NULL CHECK(state IN ('active', 'withdrawn')),
        revision INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, asset_id)
    )""",
    # A material may carry several roles, but each pairing is an explicit row, so
    # "used this picture" never silently implies every role it could serve.
    """CREATE TABLE reference_asset_roles (
        owner_key TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('identity', 'outfit', 'pose', 'scene', 'style',
                                          'background', 'continuity', 'edit_source', 'edit_mask')),
        created_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, asset_id, role),
        FOREIGN KEY(owner_key, asset_id) REFERENCES reference_assets(owner_key, asset_id)
    )""",
    "CREATE INDEX reference_assets_kind_idx ON reference_assets(owner_key, kind, state, updated_at)",
    "CREATE INDEX reference_assets_hash_idx ON reference_assets(owner_key, content_hash)",
    "CREATE INDEX reference_asset_roles_role_idx ON reference_asset_roles(owner_key, role, asset_id)",
    # Wardrobe entries are the same registration with item semantics: a name, an
    # optional description, free tags and where the item came from. Keeping them in
    # the reference family is what lets the two share one asset table (C2-1/C2-2).
    """CREATE TABLE wardrobe_items (
        owner_key TEXT NOT NULL,
        item_id TEXT NOT NULL,
        asset_id TEXT,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        tags_json TEXT NOT NULL DEFAULT '[]',
        source TEXT NOT NULL CHECK(source IN ('operator', 'provider')),
        state TEXT NOT NULL CHECK(state IN ('active', 'withdrawn')),
        revision INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, item_id),
        FOREIGN KEY(owner_key, asset_id) REFERENCES reference_assets(owner_key, asset_id)
    )""",
    "CREATE INDEX wardrobe_items_state_idx ON wardrobe_items(owner_key, state, updated_at)",
)
REFERENCE_ASSET_TABLES = frozenset({
    "reference_assets",
    "reference_asset_roles",
    "wardrobe_items",
})

# V1 capped the managed reference list at 24 entries; the limit is enforced when a
# registration is written, so an over-long list is refused rather than silently
# truncated at use time.
REFERENCE_LIMIT_SCALE = "per_role"


def reference_limit() -> int:
    """Registrations one role may hold. Declared here, enforced by the service."""
    return 24

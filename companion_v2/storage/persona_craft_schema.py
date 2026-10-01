"""Schema additions for the persona workshop: append-only draft versions.

为什么用触发器而不是「靠调用方自觉」：用户明确要求 备份 / 编辑记录 / 撤回，而
这三件事只有在历史**不可改写**时才成立。撤回如果实现成删除，就等于把「上一版
是什么」这件事交给运气。所以这里除了建表，还建两个 BEFORE UPDATE/DELETE 触发器，
让任何一条 UPDATE/DELETE（包括将来某个新代码路径、甚至操作者手敲的 SQL）都在
SQLite 层被拒绝，而不是只在 review 时被要求「不要这么写」。

``restored_from`` 的 CHECK 把「撤回」和「新草稿」区分开：撤回必须说明它撤回到
哪一版（审计要能顺着这条线走回去），普通保存则不许伪造这种来源。
"""

PERSONA_CRAFT_STATEMENTS = (
    """CREATE TABLE persona_draft_versions (
        owner_key TEXT NOT NULL,
        version_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK(sequence > 0),
        kind TEXT NOT NULL CHECK(kind IN ('draft', 'restore')),
        draft_text TEXT NOT NULL,
        original_text TEXT NOT NULL,
        persona_name TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL,
        restored_from TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY(owner_key, version_id),
        UNIQUE(owner_key, sequence),
        CHECK((kind = 'restore') = (restored_from IS NOT NULL))
    )""",
    # 列表按「最新在前」读，所以索引方向跟读取方向一致：撤回/预览都走这条。
    "CREATE INDEX persona_draft_versions_order_idx ON persona_draft_versions(owner_key, sequence DESC)",
    """CREATE TRIGGER persona_draft_versions_append_only_update
        BEFORE UPDATE ON persona_draft_versions
        BEGIN SELECT RAISE(ABORT, 'persona draft history is append-only'); END""",
    """CREATE TRIGGER persona_draft_versions_append_only_delete
        BEFORE DELETE ON persona_draft_versions
        BEGIN SELECT RAISE(ABORT, 'persona draft history is append-only'); END""",
)
PERSONA_CRAFT_TABLES = frozenset({"persona_draft_versions"})
# 迁移完整性靠这两个触发器证明：少了它们，历史就重新变得可改写。
PERSONA_CRAFT_TRIGGERS = ("persona_draft_versions_append_only_update",
                          "persona_draft_versions_append_only_delete")

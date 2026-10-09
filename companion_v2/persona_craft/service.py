"""The persona workshop: hand the operator a draft beside the host's own text.

这个服务的职责边界只有三条，写清楚是为了避免它日后「顺手」长成一个会写回宿主
的功能：

1. **只读宿主**。原文由宿主层取好之后作为 ``PersonaSnapshot`` 传进来；本服务
   不碰 AstrBot，也不持有任何写人格的能力。它甚至不存哈希——``instruction_hash``
   是安全相关值，不进页面也不进这里。
2. **只追加**。保存和撤回都是新增一版：撤回那一版正文等于旧版正文，但它是新
   记录，并且记下它撤回到哪一版。历史因此永远可回溯。
3. **原文随版本快照**。每版都存下「当时对着的原文」，所以过一阵回头看某一版，
   仍然知道改的是哪份底稿——用户最初的痛点正是「不知道在跟什么对照」。
"""

from __future__ import annotations

from datetime import datetime, timezone

from companion_v2.execution.models import TaskError
from companion_v2.persona_craft.models import (DRAFT_KIND, RESTORE_KIND, PersonaSnapshot,
                                               clean_expected_current, owner_key)
from companion_v2.persona_craft.repositories import PersonaDraftRepository


class PersonaWorkshop:
    """One role's persona draft ledger, composed with the host's current text."""

    def __init__(self, runtime, *, installation_id: str, role_id: str, now=None):
        if now is not None and not callable(now):
            # 传进来的必须是时钟本身。写成 datetime 的话错误会一直等到第一次写入
            # 才以 TypeError 出现，而那时已经离调用点很远了。
            raise ValueError("the workshop clock must be callable")
        self.runtime = runtime
        self.installation_id = installation_id
        self.role_id = role_id
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.versions = PersonaDraftRepository(runtime)

    def owner(self, persona_id: str) -> str:
        return owner_key(self.installation_id, self.role_id, persona_id)

    def state(self, snapshot: PersonaSnapshot, *, limit: int = 30) -> dict:
        """What the page renders: the host's text, plus the history beside it.

        ``owner`` stays out of the payload on purpose: it is a derived hash and the
        page has no use for it (nothing displayable may be a hash).
        """
        if not isinstance(snapshot, PersonaSnapshot):
            raise TaskError("persona_workshop_request_invalid", "the host persona must be read before the workshop")
        owner = self.owner(snapshot.persona_id)
        history = self.versions.history(owner, limit=limit)
        latest = history[0] if history else None
        return {
            "persona": snapshot,
            "current": latest,
            "versions": history,
            "count": self.versions.count(owner),
            # 只有一版历史时，页面要提示「还没存过草稿」，而不是显示一份空白编辑区。
            "has_history": latest is not None,
        }

    def save(self, snapshot: PersonaSnapshot, *, text, note, expected_current, original_text=None) -> dict:
        """Append the proposed persona as a new version."""
        source = snapshot.text if original_text is None else original_text
        if type(source) is not str or len(source) > 30000:
            raise TaskError("persona_draft_invalid", "the source snapshot must be text under 30000 characters")
        return self._append(snapshot, text=text, note=note, expected_current=expected_current,
                            kind=DRAFT_KIND, restored_from=None, original_text=source)

    def restore(self, snapshot: PersonaSnapshot, *, version_id, note, expected_current) -> dict:
        """Revive an older version by appending a copy of its text.

        撤回是「追加一版」而不是「删掉新版」：删掉的话，操作者就再也看不到自己
        刚撤掉的是什么，而用户要的正是那份编辑记录。
        """
        if not isinstance(snapshot, PersonaSnapshot):
            raise TaskError("persona_workshop_request_invalid", "the host persona must be read before the workshop")
        target = self.versions.version(self.owner(snapshot.persona_id), version_id)
        return self._append(snapshot, text=target.draft_text, note=note, expected_current=expected_current,
                            kind=RESTORE_KIND, restored_from=target.version_id, original_text=snapshot.text)

    def _append(self, snapshot: PersonaSnapshot, *, text, note, expected_current, kind, restored_from,
                original_text) -> dict:
        if not isinstance(snapshot, PersonaSnapshot):
            raise TaskError("persona_workshop_request_invalid", "the host persona must be read before the workshop")
        expected = clean_expected_current(expected_current)
        owner = self.owner(snapshot.persona_id)
        with self.runtime.transaction():
            latest = self.versions.latest(owner)
            current_id = "" if latest is None else latest.version_id
            if current_id != expected:
                # 两个操作者同时编辑时，后手不能悄悄把前手的草稿顶掉；页面重新读取
                # 后重做即可。历史只增不删，所以这里拒绝的只是「当前版」的归属。
                raise TaskError("persona_draft_conflict", "the draft moved on; read the newest version and retry")
            version = self.versions.append(
                owner, draft_text=text, note=note,
                # 原文可为用户粘贴的工作来源；显示名和归属仍来自宿主所选人格。
                original_text=original_text, persona_name=snapshot.name, at=self.now(),
                kind=kind, restored_from=restored_from)
        return {"version": version, "current": version}


__all__ = ["PersonaWorkshop"]

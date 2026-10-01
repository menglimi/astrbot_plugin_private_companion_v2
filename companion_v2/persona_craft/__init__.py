"""人格工坊：把宿主的人格原文和一份可编辑草稿并排放，历史只增不删。

V1 的「人格标准化问卷」让模型改写人格并存回宿主，用户填完之后只剩一坨生成文本，
既不好改也无从对照。V2 不重复这条路：本领域只保存草稿版本，**从不写宿主人格**。
"""

from .models import (DRAFT_KIND, DraftVersion, KINDS, MAX_DRAFT_CHARS, MAX_NOTE_CHARS, MAX_PAGE,
                     PersonaSnapshot, RESTORE_KIND, clean_draft, clean_note, owner_key, version_id)
from .repositories import PersonaDraftRepository
from .service import PersonaWorkshop

__all__ = [
    "DRAFT_KIND", "DraftVersion", "KINDS", "MAX_DRAFT_CHARS", "MAX_NOTE_CHARS", "MAX_PAGE",
    "PersonaDraftRepository", "PersonaSnapshot", "PersonaWorkshop", "RESTORE_KIND",
    "clean_draft", "clean_note", "owner_key", "version_id",
]

"""Persona workshop contracts: immutable draft versions of one host persona.

关于「为什么要有这个领域」：V1 的人格标准化问卷会用模型把用户的人格文本改写成
一份模板，然后**存回宿主**。用户的原话是「填完问卷之后再想改就不好改了」——
手里只剩一个生成出来的大块文本，既不知道该跟哪一版对照，也没有舒服的改法。

V2 因此把 AstrBot 的人格文本当成**宿主所有、只读**：本领域从不写回人格，
只保存「草稿版本」，最后一步由操作者自己把右侧文本复制回 AstrBot。这里定义的
就是那条草稿记录的形状。

两个字段的保真度不一样，必须写清楚，否则会被后人当成不一致而「顺手修好」：

* ``draft_text`` / ``original_text`` 是**逐字**的。原文可能是右边有空格、结尾有
  换行、示例段落里有 JSON——这些都是宿主实际返回的样子。任何 strip/规范化都会
  让「左侧就是宿主原文」这句话变成假话，而那正是本页存在的理由。
* ``note`` 是**标签**，不是文档。它只为「这一版我想干嘛」服务，所以允许去首尾
  空白；把它当正文逐字保存只会让列表里出现一堆看不见的差异。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from companion_v2.execution.models import TaskError, digest


# 与 native.py 对输入文本的上限一致：人格正文再长也不该超过一次对话输入的额度。
MAX_DRAFT_CHARS = 65536
# 备注是人写的短标签，不是第二份人格正文。
MAX_NOTE_CHARS = 200
# 一页最多读回的版本数。历史只增不删，所以读取必须分页有界。
MAX_PAGE = 100

DRAFT_KIND = "draft"
RESTORE_KIND = "restore"
KINDS = (DRAFT_KIND, RESTORE_KIND)


@dataclass(frozen=True)
class PersonaSnapshot:
    """宿主此刻的人格投影：显示名 + 原文，外加「到底有没有解析到」。

    ``resolved`` 单独存在，是因为「没有人格」不是错误：AstrBot 的会话可以没有
    选中人格，此时 ``text`` 就是空串。页面需要能区分「空的原文」和「读不到」，
    否则只能把两种情况都说成「读取失败」。
    """

    persona_id: str
    name: str
    text: str
    resolved: bool

    def __post_init__(self):
        for field in ("persona_id", "name", "text"):
            if type(getattr(self, field)) is not str:
                raise ValueError("persona snapshot fields must be text")
        if type(self.resolved) is not bool:
            raise ValueError("persona snapshot must state whether a persona resolved")


@dataclass(frozen=True)
class DraftVersion:
    """一版不可变的草稿：改后的文本 + 它当时对着的原文 + 备注和时间。"""

    version_id: str
    sequence: int
    kind: str
    draft_text: str
    original_text: str
    persona_name: str
    note: str
    restored_from: str | None
    created_at: datetime

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence <= 0:
            raise ValueError("draft version sequence must be a positive integer")
        if self.kind not in KINDS:
            raise ValueError("draft version kind must be declared")
        if (self.restored_from is None) != (self.kind == DRAFT_KIND):
            raise ValueError("only a restore names the version it restored")


def owner_key(installation_id: str, role_id: str, persona_id: str) -> str:
    """草稿的归属：安装 + 角色 + 宿主人格。

    刻意**不含会话窗口**。同一个角色换一个私聊窗口重绑之后仍然是同一个人格、
    同一份草稿；把窗口算进 owner 只会让「换了个对象，历史全没了」——那正是
    用户抱怨过的体验。宿主人格 ID 参与归属，因为不同人格本来就是不同的文本。
    """
    for value in (installation_id, role_id, persona_id):
        if type(value) is not str:
            raise ValueError("draft ownership fields must be text")
    if not installation_id.strip():
        raise ValueError("draft ownership requires an installation")
    return digest([installation_id, role_id, persona_id])


def version_id(sequence: int) -> str:
    """版本标识就是序号，**不是哈希**。

    页面要显示它、撤回要引用它，所以它必须可读；而「不向页面暴露任何哈希」是这一页
    的硬约束（``instruction_hash`` 是安全相关值，其余哈希也没有展示价值）。归属仍由
    ``owner_key`` 参与主键，因此不同角色/人格之间不会撞号。
    """
    if type(sequence) is not int or sequence <= 0:
        raise ValueError("draft version sequence must be a positive integer")
    return "persona-draft-v" + str(sequence).zfill(6)


def clean_note(note: object) -> str:
    """备注是标签：去掉首尾空白，但拒绝空标签。"""
    if type(note) is not str:
        raise TaskError("persona_note_invalid", "a version needs a short operator note")
    value = note.strip()
    if not value:
        raise TaskError("persona_note_invalid", "name this version so it can be recognised later")
    if len(value) > MAX_NOTE_CHARS:
        raise TaskError("persona_note_invalid", f"the note must stay within {MAX_NOTE_CHARS} characters")
    return value


def clean_draft(text: object) -> str:
    """正文**逐字**保存；只做「是不是文本」「有没有超长」这两项拒绝。

    允许空正文：操作者可能就是想从零重写一份。空正文是一个状态，不是错误。
    """
    if type(text) is not str:
        raise TaskError("persona_draft_invalid", "the proposed persona must be text")
    if len(text) > MAX_DRAFT_CHARS:
        raise TaskError("persona_draft_too_large", f"the proposed persona exceeds {MAX_DRAFT_CHARS} characters")
    return text


def clean_expected_current(value: object) -> str:
    """比较并交换用的「你以为当前是哪一版」。空串表示「我以为还没有历史」。"""
    if type(value) is not str or len(value) > 128:
        raise TaskError("persona_workshop_request_invalid", "provide the version you are editing from")
    return value


__all__ = ["DRAFT_KIND", "DraftVersion", "KINDS", "MAX_DRAFT_CHARS", "MAX_NOTE_CHARS", "MAX_PAGE",
           "PersonaSnapshot", "RESTORE_KIND", "clean_draft", "clean_expected_current", "clean_note",
           "owner_key", "version_id"]

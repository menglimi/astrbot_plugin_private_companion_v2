"""一句话的礼貌拒绝：没有对话权限时不进对话，按配置回一句。

职责边界（重要，别越界）：

* **这个模块只做决定，不发消息**。它回答"现在该不该说、说什么"，并把"什么时候说过了"
  记成一行书签；真正的发送在 ``astrbot_host/``——那里才有平台客户端，也才可能覆盖
  未绑定的陌生号（陌生号没有身份、没有 grant，走不了核心投递通道）。
* **不新增权限副本**：对话/主动权限始终只看 grant（``conversation.reply`` /
  ``proactive.contact``）。冷却书签是"上次什么时候说过"，不是权限。
* **不动 `text` / `message.delivery` 授权**：否则这句拒绝自己也发不出去。
* **不发就不发**：留空文案 = 保持安静；旧 ``delivery_mode=preview`` 只作为旧配置
  的兼容读取值，正式投递固定走真实 OneBot 私聊通道。
"""

from __future__ import annotations

import json
from datetime import datetime

from companion_v2.execution.models import TaskError, digest, encode, stamp
from companion_v2.foundation.refs import ScopeKind
from companion_v2.relationships.private_access import DIALOGUE_CAPABILITY, REVOCABLE_ABSENCE_CODES


OWNER = "relationship.private_notice"
KIND = "relationship.private_notice.v1"
VERSION = 1

UPSERT = """INSERT INTO memory_views VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
    ON CONFLICT(view_id) DO UPDATE SET revision = excluded.revision,
        document_json = excluded.document_json, updated_at = excluded.updated_at"""


def _moment(value):
    """Parse a stored stamp back into an aware datetime; unreadable stays unknown."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class PrivateRefusalNotice:
    """按人冷却地决定"该不该回一句、回什么"。"""

    def __init__(self, runtime, tasks, *, settings=None):
        self.runtime, self.tasks = runtime, tasks
        self.settings = settings

    # -- keys ---------------------------------------------------------------

    def owner_key(self, context, subject_id=None):
        scope = context.scope
        subject_id = subject_id or context.actor.subject.subject_id
        return digest([KIND, scope.installation_id, scope.platform, scope.bot_id, scope.account_id,
                       subject_id])

    def _document_id(self, owner):
        return "private-notice-" + digest(owner)

    # -- configuration ------------------------------------------------------

    def configured(self, context):
        if self.settings is None:
            from companion_v2.relationships.private_access import (DENIED_REPLY,
                                                                    NOTICE_COOLDOWN_SECONDS)
            return {"denied_reply": DENIED_REPLY, "notice_cooldown_seconds": NOTICE_COOLDOWN_SECONDS}
        return self.settings.defaults(context)

    # -- cooldown bookmark --------------------------------------------------

    def document(self, context, subject_id=None):
        row = self.runtime.read_one("SELECT document_json FROM memory_views WHERE view_id = ? AND kind = ?",
                                    (self._document_id(self.owner_key(context, subject_id)), KIND))
        if row is None:
            return None
        try:
            document = json.loads(row["document_json"])
        except (TypeError, ValueError):
            return None
        return document if isinstance(document, dict) else None

    def _write(self, context, subject_id, text, at, *, sent):
        owner = self.owner_key(context, subject_id)
        identifier = self._document_id(owner)
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT revision, document_json FROM memory_views WHERE view_id = ? AND kind = ?",
                                     (identifier, KIND)).fetchone()
            document = json.loads(row["document_json"]) if row is not None else {"version": VERSION}
            if not isinstance(document, dict):
                document = {"version": VERSION}
            document.update({"version": VERSION, "subject_id": subject_id, "text_sha": digest(text),
                             "updated_at": stamp(at)})
            if sent:
                document["last_notice_at"] = stamp(at)
            connection.execute(UPSERT, (identifier, owner, KIND, row["revision"] + 1 if row is not None else 1,
                                        encode(document), encode({"owner": OWNER}), stamp(at)))
        return document

    # -- decision -----------------------------------------------------------

    def due(self, context, at):
        """这一句现在该不该说；冷却期内返回 ``None``。"""
        values = self.configured(context)
        text = str(values.get("denied_reply") or "").strip()
        if not text:
            return None
        cooldown = int(values.get("notice_cooldown_seconds") or 0)
        if cooldown <= 0:
            return text
        document = self.document(context) or {}
        previous = _moment(document.get("last_notice_at"))
        if previous is None:
            return text
        return text if (at - previous).total_seconds() >= cooldown else None

    def mark_sent(self, context, subject_id, text, at):
        """宿主确实把这句话送出去了才记账，冷却从这一刻开始。"""
        return self._write(context, subject_id, text, at, sent=True)


class PrivateAccessGate:
    """按人的对话权限：没有权限就不进对话（宿主随后按配置回一句）。

    三个入口各有分工：

    * ``denied()`` —— **只判定**，不发送、不抛错；
    * ``refuse()`` —— 判定 + 抛 ``private_access_dialogue_denied``（宿主层用它，
      那里才是"要不要收下这条消息"的地方，也是唯一能发消息的地方）；
    * ``guard()`` —— 与 ``refuse()`` 同义，用于 ``accept`` 这类兜底点，语义上表明
      "到这里还没回过话，只是不许进对话"。
    """

    def __init__(self, tasks, notice):
        self.tasks, self.notice = tasks, notice

    def denied(self, context, *, at=None):
        if context.scope.kind is not ScopeKind.PRIVATE:
            return False  # 群聊有自己的口径（群成员风控与群授权），这里不动
        at = at or self.tasks.now()
        result = self.tasks.check_context_access(context, action=DIALOGUE_CAPABILITY, observed_at=at)
        if result.is_success:
            return False
        # 真故障（绑定变了、作用域不对…）照旧往上抛，不伪装成"没权限"。
        return result.failure.code in REVOCABLE_ABSENCE_CODES

    def refuse(self, context, *, at=None):
        if not self.denied(context, at=at):
            return None
        raise TaskError("private_access_dialogue_denied", "this private user has no dialogue permission")

    def guard(self, context, *, at=None):
        return self.refuse(context, at=at)

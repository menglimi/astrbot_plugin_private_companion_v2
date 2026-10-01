"""评论收件箱：把识别与幂等规则接到 V2 的存储原语上。

两件事，各自用**已有**的机制，都不新增表、不动 schema 版本：

* **幂等**——一条评论折成 ``(consumer, event_id, payload_hash)`` 交给 ``InboxRepository``：
  重复投递被它挡掉，正文被编辑判成 ``inbox_event_conflict``。
* **状态**——两份有界账本（最近已发、最近回复）存成一份 ``memory_views`` 文档，
  按**空间账号**（平台 + 登录号）分开：一个角色可能有好几个号在空间里活动，
  账本混在一起会让 A 号的回复影响 B 号的判断。

判定顺序与 V1 一致：**幂等 → 自我/已回过 → 作者冷却 → 就绪**。
这里只回答"要不要回"，不发送、不读记忆、不调模型；发送与账本提交由调用方
在 ``qzone/service.py`` 的预留链路里完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from companion_v2.execution.models import encode, normalize_utc
from companion_v2.storage.repositories import InboxRepository

from .comments import (REPLY_RETENTION, SENT_RETENTION, CommentEvent,
                       author_post_recently_replied, comment_event, is_self, matches_recent_sent,
                       note_sent, trim_records)


KIND = "qzone.comment_inbox.v1"
OWNER = "qzone.comment_inbox"
ACTIVE = "active"
UPSERT = """INSERT INTO memory_views VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(view_id) DO UPDATE SET revision = excluded.revision, state = excluded.state,
        document_json = excluded.document_json, source_json = excluded.source_json,
        updated_at = excluded.updated_at"""

READY = "ready"
DUPLICATE = "duplicate"
CONFLICT = "inbox_event_conflict"
SELF = "self"
COOLDOWN = "author_cooldown"


def view_id(platform, login):
    """一份账本对应一个空间账号；id 有界且不含账号明文。"""
    return "qzone-comment-inbox:" + comment_event(
        platform=platform, login=login, post_tid="", uin="0", content="").event_id


@dataclass(frozen=True)
class InboxState:
    sent: tuple = ()
    replies: tuple = ()

    def as_document(self, at):
        return {"version": 1, "updated_at": normalize_utc(at, field="comment clock").isoformat(),
                "sent": [record.as_document() for record in self.sent],
                "replies": [record.as_document() for record in self.replies]}

    @classmethod
    def from_document(cls, value, *, at):
        if not isinstance(value, dict):
            return cls()
        return cls(sent=trim_records(value.get("sent"), now=at, retention=SENT_RETENTION),
                   replies=trim_records(value.get("replies"), now=at, retention=REPLY_RETENTION))


@dataclass(frozen=True)
class CommentDecision:
    """一条评论的处理结论：要么可以回，要么带着**具体理由**被跳过。"""

    accept: bool
    reason: str
    event: CommentEvent

    @property
    def should_reply(self):
        return self.accept and self.reason == READY


class CommentInbox:
    """按空间账号维护评论的受理与账本；同一实例可跨账号复用。"""

    def __init__(self, runtime, *, now=None):
        self.runtime = runtime
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _at(self, at):
        return normalize_utc(at or self._now(), field="comment clock")

    # -- 账本 ---------------------------------------------------------------

    def state(self, *, platform, login, at=None):
        at = self._at(at)
        row = self.runtime.read_one("SELECT document_json FROM memory_views WHERE view_id = ? AND kind = ?",
                                    (view_id(platform, login), KIND))
        if row is None:
            return InboxState()
        import json
        try:
            document = json.loads(row["document_json"])
        except (TypeError, ValueError):
            return InboxState()
        return InboxState.from_document(document, at=at)

    def _write(self, *, platform, login, state, at):
        identifier = view_id(platform, login)
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT revision FROM memory_views WHERE view_id = ?",
                                     (identifier,)).fetchone()
            connection.execute(UPSERT, (
                identifier, identifier, KIND, (row["revision"] + 1) if row else 1, ACTIVE,
                encode(state.as_document(at)), encode({"owner": OWNER}),
                normalize_utc(at, field="comment clock").isoformat(timespec="microseconds")))

    def record_sent(self, *, platform, login, post_tid, author, comment_text, sent_text, at=None):
        """回完一条之后落账：同一账号的下一次扫描据此认出"已经回过"。"""
        at = self._at(at)
        state = self.state(platform=platform, login=login, at=at)
        sent, replies = note_sent(state.sent, state.replies, now=at, post_tid=post_tid, author=author,
                                  comment_text=comment_text, sent_text=sent_text)
        updated = InboxState(sent=sent, replies=replies)
        self._write(platform=platform, login=login, state=updated, at=at)
        return updated

    # -- 受理与判定 ---------------------------------------------------------

    def seen(self, event):
        """只读地问一句"这条评论以前受理过吗"，**不写任何东西**。

        后台扫描靠它把"已经处理过的评论"与"还没碰过的新评论"分开：预算之外的新评论
        这一轮完全不碰（``seen`` 返回假，下一轮它仍然是新的），而已经受理过的评论不该
        因为一次扫描预算不够就被反复判定。
        """
        row = self.runtime.read_one("SELECT 1 FROM inbox WHERE consumer = ? AND event_id = ? LIMIT 1",
                                    (event.consumer, event.event_id))
        return row is not None

    def decide(self, *, platform, login, post_tid, comment_id="", uin=None, name="", content="",
               created="", comment_key="", legacy="", raw=None, own_uin=None,
               post_author_name="", at=None):
        at = self._at(at)
        event = comment_event(platform=platform, login=login, post_tid=post_tid, comment_id=comment_id,
                              uin=uin, name=name, content=content, created=created,
                              comment_key=comment_key, legacy=legacy, raw=raw)
        receipt = InboxRepository(self.runtime).accept(
            consumer=event.consumer, event_id=event.event_id, payload_hash=event.payload_hash,
            observed_at=at)
        if receipt.failure is not None:
            # 目前只有一种失败：同一个幂等键用不同载荷出现过。其余失败照原样报出去，
            # 免得把"看不懂的原因"伪装成"内容冲突"。
            reason = CONFLICT if receipt.failure.code == CONFLICT else receipt.failure.code
            return CommentDecision(False, reason, event)
        if receipt.value.replayed:
            return CommentDecision(False, DUPLICATE, event)
        state = self.state(platform=platform, login=login, at=at)
        # V1 的 `matches_recent_sent` 比的是**评论正文**，它回答的是"这条评论是不是我
        # 自己发出去的"（`is_self` 的第三个条件），不是"我回过这条没有"。
        # "回过了没有"在 V2 由上面的幂等表永久保证，在 V1 则只有作者冷却这一层。
        already_sent = matches_recent_sent(state.sent, now=at, post_tid=event.post_tid, content=content)
        if is_self(own_uin=own_uin, comment_uin=uin, commenter_name=name,
                   author_name=post_author_name, already_sent=already_sent):
            return CommentDecision(False, SELF, event)
        if author_post_recently_replied(state.replies, now=at, post_tid=event.post_tid, author=event.author):
            return CommentDecision(False, COOLDOWN, event)
        return CommentDecision(True, READY, event)


__all__ = ["ACTIVE", "COOLDOWN", "CONFLICT", "CommentDecision", "CommentInbox", "DUPLICATE",
           "InboxState", "KIND", "OWNER", "READY", "SELF", "view_id"]

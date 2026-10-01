"""评论收件箱的后台扫描：把"扫到的动态与评论"变成"这一轮回哪一条"。

分工与前两块一致：``comments.py`` 只判定、``inbox.py`` 只管受理与账本、这里管**节奏**。
扫描本身**不发送**——它给出候选与一个**确定的 operation_key**，发送仍走
``qzone/service.py`` 的预留链路（那里才有"结果未知不换 key 重放"的纪律）。

三条纪律写在这里，因为它们最容易在后台循环里出错：

* **先问路再受理**：总闸、回复开关、动作间隔都在**受理之前**判断。受理一条评论就是
  给它留下永久痕迹（幂等表里那一行），所以"这轮不方便回"绝不能变成"这条以后都不回了"。
* **候选受预算限制**：``max_actions_per_tick`` 之外的新评论**这一轮完全不碰**，
  下一轮它们仍然是新的（幂等表里没有它们）。
* **失败要退避**：连续失败按 5 分钟起指数增长、封顶 6 小时；成功即清零。
  退避只影响"下次什么时候扫"，不影响已经受理的评论。

扫描节奏复用这个域既有的字段（``comment_enabled`` / ``comment_recent_posts`` /
``action_min_interval_minutes`` / ``max_actions_per_tick``），**不新增配置、不动 schema**；
游标存成 ``memory_views`` 文档，按"角色 × 空间账号"分档。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from companion_v2.execution.models import digest, encode, normalize_utc
from companion_v2.qzone.comments import CommentEvent, comment_event
from companion_v2.qzone.policy import action_reason
from companion_v2.qzone.references import COMMENT
from companion_v2.qzone.service import local_day


KIND = "qzone.comment_scan.v1"
OWNER = "qzone.comment_scan"
ACTIVE = "active"
UPSERT = """INSERT INTO memory_views VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(view_id) DO UPDATE SET revision = excluded.revision, state = excluded.state,
        document_json = excluded.document_json, source_json = excluded.source_json,
        updated_at = excluded.updated_at"""

BACKOFF_BASE = timedelta(minutes=5)
BACKOFF_CAP = timedelta(hours=6)
REPLY_PREFIX = "qzone.comment.reply:"

READY = "ready"
NOT_DUE = "not_due"
DEFERRED = "deferred"
DUPLICATE = "duplicate"
UNKNOWN = "unknown"
FAILED = "failed"


def reply_operation_key(event):
    """同一条评论的回复只有一个键：结果未知时也不许换一个键再发一次。"""
    return REPLY_PREFIX + event.event_id


def scan_view_id(owner):
    return "qzone-comment-scan:" + digest([KIND, owner])


def _day(at):
    return local_day(at)


@dataclass(frozen=True)
class ScanCursor:
    """下次什么时候扫、连续失败几次——只有这三件事需要持久化。"""

    last_scan_at: datetime | None = None
    consecutive_failures: int = 0
    next_scan_at: datetime | None = None
    last_reason: str = ""

    def as_document(self, at):
        return {"version": 1, "updated_at": normalize_utc(at, field="scan clock").isoformat(),
                "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else "",
                "consecutive_failures": int(self.consecutive_failures),
                "next_scan_at": self.next_scan_at.isoformat() if self.next_scan_at else "",
                "last_reason": self.last_reason[:80]}

    @classmethod
    def from_document(cls, value):
        if not isinstance(value, dict):
            return cls()

        def moment(name):
            try:
                return normalize_utc(datetime.fromisoformat(str(value.get(name) or "")), field="scan clock")
            except (TypeError, ValueError):
                return None

        try:
            failures = max(0, int(value.get("consecutive_failures") or 0))
        except (TypeError, ValueError):
            failures = 0
        return cls(last_scan_at=moment("last_scan_at"), consecutive_failures=failures,
                   next_scan_at=moment("next_scan_at"), last_reason=str(value.get("last_reason") or "")[:80])

    def backoff(self, *, at):
        """失败后的下次时间：5 分钟起翻倍，封顶 6 小时。"""
        delay = min(BACKOFF_BASE * (2 ** max(0, self.consecutive_failures - 1)), BACKOFF_CAP)
        return self.next_scan_at or (at + delay)


@dataclass(frozen=True)
class CommentCandidate:
    """一条值得回的评论；``operation_key`` 让重试不会变成第二条回复。"""

    post_ref: str
    post_id: str
    event: CommentEvent
    author: str
    text: str

    @property
    def operation_key(self):
        return reply_operation_key(self.event)


@dataclass(frozen=True)
class ScanPlan:
    due: bool
    reason: str
    candidates: tuple
    skipped: tuple
    cursor: ScanCursor

    @property
    def has_work(self):
        return bool(self.candidates)


def candidate_for(*, platform, login, post_ref, uin=None, name="", content="", created="",
                  post_id="", author=""):
    """按**同一条评论折叠出同一个候选**：宿主在回复时重新算一遍，不信任调用方给的键。"""
    event = comment_event(platform=platform, login=login, post_tid=post_ref, uin=uin, name=name,
                          content=content, created=created)
    return CommentCandidate(post_ref=post_ref, post_id=post_id or post_ref, event=event,
                            author=str(author or name or ""), text=str(content or ""))


class CommentScanner:
    """一个角色 × 一个空间账号的扫描器；判定交给 ``CommentInbox``，发送交给调用方。"""

    def __init__(self, *, service, inbox, runtime, platform, login, now=None):
        self.service = service
        self.inbox = inbox
        self.runtime = runtime
        self.platform = platform
        self.login = str(login)
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _at(self, at):
        return normalize_utc(at or self._now(), field="scan clock")

    # -- 游标 ---------------------------------------------------------------

    def cursor(self, *, owner, at=None):
        row = self.runtime.read_one("SELECT document_json FROM memory_views WHERE view_id = ? AND kind = ?",
                                    (scan_view_id(owner), KIND))
        if row is None:
            return ScanCursor()
        try:
            return ScanCursor.from_document(json.loads(row["document_json"]))
        except (TypeError, ValueError):
            return ScanCursor()

    def _write(self, *, owner, cursor, at):
        identifier = scan_view_id(owner)
        with self.runtime.transaction() as connection:
            row = connection.execute("SELECT revision FROM memory_views WHERE view_id = ?",
                                     (identifier,)).fetchone()
            connection.execute(UPSERT, (
                identifier, identifier, KIND, (row["revision"] + 1) if row else 1, ACTIVE,
                encode(cursor.as_document(at)), encode({"owner": OWNER}),
                normalize_utc(at, field="scan clock").isoformat(timespec="microseconds")))
        return cursor

    def note_success(self, *, owner, at=None, reason=READY, interval_minutes=30):
        at = self._at(at)
        gap = timedelta(minutes=max(1, int(interval_minutes or 30)))
        return self._write(owner=owner, at=at, cursor=ScanCursor(
            last_scan_at=at, consecutive_failures=0, next_scan_at=at + gap, last_reason=reason))

    def note_failure(self, *, owner, at=None, reason=FAILED):
        at = self._at(at)
        previous = self.cursor(owner=owner, at=at)
        grown = ScanCursor(last_scan_at=previous.last_scan_at,
                           consecutive_failures=previous.consecutive_failures + 1,
                           last_reason=str(reason)[:80])
        return self._write(owner=owner, at=at, cursor=ScanCursor(
            last_scan_at=grown.last_scan_at, consecutive_failures=grown.consecutive_failures,
            next_scan_at=grown.backoff(at=at), last_reason=grown.last_reason))

    def due(self, *, owner, at=None):
        at = self._at(at)
        cursor = self.cursor(owner=owner, at=at)
        if cursor.next_scan_at is not None and at < cursor.next_scan_at:
            return False, NOT_DUE
        return True, READY

    # -- 扫描 ---------------------------------------------------------------

    async def scan(self, *, owner, context, at=None):
        """一次扫描：先问路，再受理（受理数不超过本轮预算）。"""
        at = self._at(at)
        cursor = self.cursor(owner=owner, at=at)
        settings = self.service.configuration(context, at)
        if not settings.get("enabled"):
            return ScanPlan(False, "空间能力已关闭", (), (), cursor)
        if not settings.get("comment_enabled"):
            return ScanPlan(False, "回复未开启", (), (), cursor)
        blocked = action_reason(self.service.state(context), settings, kind=COMMENT, at=at, day=_day(at))
        if blocked:
            # 间隔没到 / 今天发得太多：**不受理**，下一轮这条评论仍然是新的。
            return ScanPlan(False, blocked, (), (), cursor)
        due, reason = self.due(owner=owner, at=at)
        if not due:
            return ScanPlan(False, reason, (), (), cursor)

        budget = max(1, int(settings.get("max_actions_per_tick") or 1))
        limit = max(1, int(settings.get("comment_recent_posts") or 5))
        report = await self.service.scan(context, scope="own", limit=limit, detail=True)
        candidates, skipped = [], []
        for item in report.get("items") or ():
            post_ref = str(item.get("post_ref") or "")
            if not post_ref:
                continue
            for comment in item.get("comments") or ():
                event = comment_event(platform=self.platform, login=self.login, post_tid=post_ref,
                                      uin=comment.get("author_uin"), name=comment.get("author"),
                                      content=comment.get("text"), created=comment.get("at"))
                if self.inbox.seen(event):
                    skipped.append((DUPLICATE, event.event_id))
                    continue
                if len(candidates) >= budget:
                    # 预算之外的新评论这一轮完全不碰。
                    skipped.append((DEFERRED, event.event_id))
                    continue
                decision = self.inbox.decide(platform=self.platform, login=self.login, post_tid=post_ref,
                                             uin=comment.get("author_uin"), name=comment.get("author"),
                                             content=comment.get("text"), created=comment.get("at"),
                                             own_uin=self.login, post_author_name=item.get("author"), at=at)
                if decision.should_reply:
                    candidates.append(CommentCandidate(
                        post_ref=post_ref, post_id=str(item.get("post_id") or post_ref),
                        event=decision.event, author=str(comment.get("author") or ""),
                        text=str(comment.get("text") or "")))
                else:
                    skipped.append((decision.reason, event.event_id))
        return ScanPlan(True, READY, tuple(candidates), tuple(skipped), cursor)

    def note_replied(self, *, owner, candidate, reply_text, at=None, interval_minutes=30):
        """回复真的发出去了：落账，然后推进游标。"""
        at = self._at(at)
        self.inbox.record_sent(platform=self.platform, login=self.login, post_tid=candidate.post_ref,
                               author=candidate.event.author, comment_text=candidate.text,
                               sent_text=reply_text, at=at)
        return self.note_success(owner=owner, at=at, reason=READY, interval_minutes=interval_minutes)

    async def reply(self, *, owner, context, candidate, text, at=None, interval_minutes=30):
        """发送一条回复并落账——**先发后记**，发送没成功就不许动账本。

        键取自候选（由评论身份决定），所以结果未知时重试会被 ``qzone/service`` 的
        预留链路按同键拒掉，不会变成第二条回复。失败分两种：**投递结果未知**退避后
        原样抛出（该评论保持已受理，不再回），其余失败同样不落账（下一轮还能再试）。
        """
        at = self._at(at)
        try:
            receipt = await self.service.comment(context, post_ref=candidate.post_ref, text=text,
                                                 operation_key=candidate.operation_key)
        except Exception as error:
            reason = UNKNOWN if _is_unknown(error) else FAILED
            self.note_failure(owner=owner, at=at, reason=reason)
            raise
        self.note_replied(owner=owner, candidate=candidate, reply_text=text, at=at,
                          interval_minutes=interval_minutes)
        return receipt


def _is_unknown(error):
    """投递结果未知：这个域用 ``operation_state``/``qzone_delivery_unknown`` 表达它。"""
    code = str(getattr(error, "code", "") or "")
    return "unknown" in code or code.endswith("delivery_unknown")


__all__ = ["ACTIVE", "BACKOFF_BASE", "BACKOFF_CAP", "CommentCandidate", "CommentScanner", "DEFERRED",
           "DUPLICATE", "FAILED", "KIND", "NOT_DUE", "OWNER", "READY", "REPLY_PREFIX", "ScanCursor",
           "ScanPlan", "UNKNOWN", "candidate_for", "reply_operation_key", "scan_view_id"]

"""空间评论的身份与幂等规则（自 V1 迁移）。

这一层只有**判定**，不碰存储、不发网络请求。V1 把它们散在 895 行的 mixin 里，
这里按"一条评论到底是不是同一条、要不要回、回过了没有"重新归位：

* **身份**：``uin`` 优先，退化到归一化名字，再退化 ``unknown``。绝不因为一条评论
  就给人建 V2 身份——那会让"这个人是谁"出现第二个答案。
* **归一化**：去标签、反转义、压缩空白、小写、去标点、有界。它同时是"同一条评论"
  与"已经回过"两个判断的基础，所以必须是幂等的纯函数。
* **幂等**：``comment_event`` 把一条评论折成 ``(consumer, event_id, payload_hash)``，
  直接喂给 ``InboxRepository.accept``——V2 已有的入站幂等原语，**不新增表**。
* **节流与护栏**：自己不回自己、同一作者同一帖有冷却、回复不得夹带内部信息。

保留窗口沿用 V1 的实测值：已发评论 7 天、作者回复 24 小时、上限各 160 条、作者冷却 6 小时。
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from companion_v2.execution.models import digest, normalize_utc


CONSUMER = "qzone.comment"

MAX_TEXT = 160
RECORD_LIMIT = 160
FALLBACK_LIMIT = 5
SENT_RETENTION = timedelta(days=7)
REPLY_RETENTION = timedelta(hours=24)
AUTHOR_COOLDOWN = timedelta(hours=6)

_HTML = re.compile(r"<[^>]+>")
_PUNCTUATION = re.compile(r"[，,。.!！?？~～…·、；;：:\"'“”‘’\[\]（）()\s]+")
_SPACE = re.compile(r"\s+")

# V1 的护栏词表，加上 V2 对主要用户的称呼（V1 用「主人」，V2 用「老大」）。
# 回复里出现这些词就说明它把私下的关系或内部机制端到了公开场合。
DEFAULT_LEAK_PATTERNS = (
    "私聊", "老大", "主人", "主要用户", "朋友用户", "次要用户",
    "插件", "模型", "系统提示", "token", "后台", "内部", "记忆注入",
)


def single_line(value, limit):
    """压成一行并有界；不抛错——判定的输入常常是脏的，脏输入不该炸掉整轮扫描。"""
    return _SPACE.sub(" ", str(value or "")).strip()[: max(1, int(limit))]


def normalized_text(value):
    """比较用的正文形态：内容相同、标点或空白不同视为同一条。"""
    cleaned = html.unescape(_HTML.sub("", str(value or "")))
    cleaned = _PUNCTUATION.sub("", _SPACE.sub("", cleaned).lower())
    return cleaned[:MAX_TEXT]


def author_key(*, uin=None, name=""):
    identifier = str(uin or "").strip()
    if identifier and identifier.isascii() and identifier.isdecimal():
        return f"uin:{identifier}"
    fallback = re.sub(r"\s+", "", single_line(name, 40).lower())
    return f"name:{fallback}" if fallback else "unknown"


def author_post_key(post_tid, author):
    """同一作者在同一帖上的键——节流按它记账，不按人跨帖。"""
    return f"{single_line(post_tid, 80) or 'post'}|{author}"


def fingerprint(post_tid, *, uin=None, name="", content=""):
    author = str(uin or "").strip() or re.sub(r"\s+", "", single_line(name, 40).lower()) or "unknown"
    material = f"{single_line(post_tid, 80) or 'post'}|{author}|{normalized_text(content)}"
    return f"{single_line(post_tid, 80) or 'post'}:fp:{digest(material)[:20]}"


def legacy_id(post_tid, *, uin=None, name="", content="", created=""):
    """老接口只给得出这种形态的 id；留在备用标识里，便于回退查询。"""
    author = str(uin or "").strip() or re.sub(r"\s+", "", single_line(name, 40).lower()) or "unknown"
    material = "|".join([single_line(post_tid, 80) or "post", author, normalized_text(content),
                         single_line(created, 40)])
    return f"{single_line(post_tid, 80) or 'post'}:sha1:{digest(material)[:20]}"


@dataclass(frozen=True)
class CommentIdentity:
    """一条评论的稳定身份：能拿到的 id、指纹键、以及有界的备用标识。"""

    comment_id: str
    comment_key: str
    fallbacks: tuple[str, ...]

    @property
    def stable(self):
        """幂等键优先用平台给的 id；平台没给就用指纹——两者都不会随时间变化。"""
        return self.comment_id or self.comment_key


def identifiers(*, post_tid, comment_id="", uin=None, name="", content="", created="",
                comment_key="", legacy="", raw=None):
    """产出 ``(comment_id, comment_key, 备用标识)``；``raw`` 存在时以它为准（V1 同序）。

    指纹只在"平台没给 id"或"要跨接口回退"时起作用，所以这里从不假装指纹等于 id。
    """
    fields = raw if isinstance(raw, Mapping) else {}
    uin = fields.get("uin", uin)
    name = fields.get("name", name)
    content = fields.get("content", content)
    created = fields.get("created", created)
    resolved_id = single_line(comment_id, 120)
    resolved_key = single_line(comment_key or fingerprint(post_tid, uin=uin, name=name, content=content), 120)
    legacy_value = single_line(legacy or legacy_id(post_tid, uin=uin, name=name, content=content,
                                                   created=created), 120)
    fallbacks = []
    for value in (resolved_id, legacy_value):
        if value and value not in fallbacks:
            fallbacks.append(value)
    return CommentIdentity(resolved_id, resolved_key, tuple(fallbacks[:FALLBACK_LIMIT]))


@dataclass(frozen=True)
class CommentRecord:
    """收件箱记账的一行，字段与 V1 的记录一一对应。"""

    key: str
    post_tid: str
    author_key: str
    text_norm: str
    text: str
    at: datetime

    def as_document(self):
        return {"key": self.key, "post_tid": self.post_tid, "author_key": self.author_key,
                "text_norm": self.text_norm, "text": self.text, "ts": self.at.timestamp()}

    @classmethod
    def from_document(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            return None
        key = single_line(value.get("key") or value.get("signature"), MAX_TEXT)
        post_tid = single_line(value.get("post_tid"), 80)
        text_norm = single_line(value.get("text_norm"), MAX_TEXT)
        if not key and post_tid and text_norm:
            key = f"{post_tid}|{text_norm}"
        if not key:
            return None
        try:
            at = datetime.fromtimestamp(float(value.get("ts") or 0), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
        return cls(key, post_tid, single_line(value.get("author_key"), 80), text_norm,
                   single_line(value.get("text"), 120), at)


def trim_records(values, *, now, retention=SENT_RETENTION, limit=RECORD_LIMIT):
    """按 key 去重、按窗口过期、按上限截尾——与 V1 的裁剪规则逐条对应。"""
    now = normalize_utc(now, field="comment clock")
    kept, seen = [], set()
    for item in values if isinstance(values, Iterable) and not isinstance(values, (str, bytes)) else ():
        record = CommentRecord.from_document(item)
        if record is None:
            continue
        if record.at and now - record.at > retention:
            continue
        if record.key in seen:
            continue
        seen.add(record.key)
        kept.append(record)
    return tuple(kept[-max(1, int(limit)):])


def matches_recent_sent(records, *, now, post_tid, content):
    """同帖内、正文归一化后与"最近已发"相同 ⇒ 这条已经回过了。"""
    target = normalized_text(content)
    if not target:
        return False
    tid = single_line(post_tid, 80) or "post"
    for record in trim_records(records, now=now, retention=SENT_RETENTION):
        if record.post_tid == tid and record.text_norm == target:
            return True
    return False


def is_self(*, own_uin=None, comment_uin=None, commenter_name="", author_name="", already_sent=False):
    """自己不回自己：账号相同，或评论者名字与帖主相同，或这条本来就是自己发的。"""
    own = str(own_uin or "").strip()
    if own and str(comment_uin or "").strip() == own:
        return True
    left = re.sub(r"\s+", "", single_line(commenter_name, 40).lower())
    right = re.sub(r"\s+", "", single_line(author_name, 40).lower())
    if left and right and left == right:
        return True
    return bool(already_sent)


def author_post_recently_replied(records, *, now, post_tid, author, cooldown=AUTHOR_COOLDOWN):
    now = normalize_utc(now, field="comment clock")
    key = author_post_key(post_tid, author)
    for record in trim_records(records, now=now, retention=REPLY_RETENTION):
        if record.key == key and now - record.at < cooldown:
            return True
    return False


def note_sent(sent, replies, *, now, post_tid, author, comment_text, sent_text):
    """回完一条之后的两笔记账；返回新的元组（不改调用方的容器，便于放进事务）。"""
    now = normalize_utc(now, field="comment clock")
    tid = single_line(post_tid, 80) or "post"
    text_norm = normalized_text(sent_text)
    updated_sent = list(trim_records(sent, now=now, retention=SENT_RETENTION))
    if text_norm:
        updated_sent.append(CommentRecord(f"{tid}|{text_norm}", tid, "self", text_norm,
                                          single_line(sent_text, 120), now))
    updated_replies = list(trim_records(replies, now=now, retention=REPLY_RETENTION))
    updated_replies.append(CommentRecord(author_post_key(tid, author), tid, author,
                                         normalized_text(comment_text),
                                         single_line(comment_text, 120), now))
    return (trim_records(updated_sent, now=now, retention=SENT_RETENTION),
            trim_records(updated_replies, now=now, retention=REPLY_RETENTION))


def fuzzy_score(comment_text, hint):
    """把一条评论与"记得的提示"对齐打分；模糊就明说是模糊，不假装精确。"""
    text = normalized_text(comment_text)
    query = normalized_text(hint)
    if not query or not text:
        return 0.0
    if query == text:
        return 1.0
    if query in text or text in query:
        return min(0.96, min(len(query), len(text)) / max(len(query), len(text)) + 0.18)
    def grams(value):
        return {value[index:index + 3] for index in range(max(0, len(value) - 2))}
    left, right = grams(query), grams(text)
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def leaks_internal(text, *, patterns=DEFAULT_LEAK_PATTERNS):
    """空回复与夹带内部信息的回复都算不合格（V1 的隐私护栏，词表可注入）。"""
    compact = str(text or "")
    if not compact.strip():
        return True
    return any(re.search(pattern, compact, flags=re.IGNORECASE) for pattern in patterns)


@dataclass(frozen=True)
class CommentEvent:
    """可直接交给 ``InboxRepository.accept`` 的三元组，外加判定用得到的身份。"""

    consumer: str
    event_id: str
    payload_hash: str
    identity: CommentIdentity
    post_tid: str
    author: str
    text_norm: str


def comment_event(*, platform, login, post_tid, comment_id="", uin=None, name="", content="",
                  created="", comment_key="", legacy="", raw=None):
    """把一条评论折成入站幂等三元组。

    ``event_id`` 只由**稳定身份**决定（平台的评论 id，退化到指纹），所以正文被改写时
    幂等键不变、``payload_hash`` 变——``InboxRepository`` 会把它判成冲突而不是新事件。
    这正是我们要的：平台上的评论被编辑过，不该被当成第二条评论再回一次。

    身份里**必须**带上作者：平台的评论 id 只保证在帖子内唯一，两个人在同一帖下各有一条
    "c-1" 是可能的，不带作者就会把别人的评论当成自己的那一条（V1 的指纹里同样带作者）。
    """
    identity = identifiers(post_tid=post_tid, comment_id=comment_id, uin=uin, name=name, content=content,
                           created=created, comment_key=comment_key, legacy=legacy, raw=raw)
    author = author_key(uin=uin, name=name)
    scope = ["qzone.comment", single_line(platform, 80), single_line(login, 80),
             single_line(post_tid, 80) or "post", author, identity.stable]
    return CommentEvent(CONSUMER, digest(scope)[:32], digest([author, normalized_text(content)])[:32],
                        identity, single_line(post_tid, 80) or "post", author, normalized_text(content))


__all__ = ["AUTHOR_COOLDOWN", "CONSUMER", "CommentEvent", "CommentIdentity", "CommentRecord",
           "DEFAULT_LEAK_PATTERNS", "FALLBACK_LIMIT", "MAX_TEXT", "RECORD_LIMIT", "REPLY_RETENTION",
           "SENT_RETENTION", "author_key", "author_post_key", "author_post_recently_replied",
           "comment_event", "fingerprint", "fuzzy_score", "identifiers", "is_self", "leaks_internal",
           "legacy_id", "matches_recent_sent", "normalized_text", "note_sent", "single_line",
           "trim_records"]

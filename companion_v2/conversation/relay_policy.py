"""跨窗口递话的授权判定（纯逻辑，不碰发送）。

口径来自产品要求：

* **核心管理员**可以让 bot 帮忙私聊递话——只允许发到管理员选定的私聊目标，
  且需要一次确认（避免模型自作主张把内容发出去）；
* **其他用户**可以让 bot 给核心管理员递话——目标只能是核心管理员本人，
  不给他们发到任意窗口的能力；
* 群聊、未开启、空文本、超长文本一律拒绝。

这里只回答“这次递话该不该放行、要不要确认”，真正的发送由宿主层完成并写审计。
把判定独立出来，是为了让授权边界可以脱离网络与数据库被穷举测试。
"""

from dataclasses import dataclass

DENIED_DISABLED = "relay_disabled"
DENIED_TEXT_EMPTY = "relay_text_empty"
DENIED_TEXT_TOO_LONG = "relay_text_too_long"
DENIED_GROUP = "relay_group_not_allowed"
DENIED_TARGET = "relay_target_not_allowed"
DENIED_SELF = "relay_target_is_current_window"

ALLOWED = "relay_allowed"

MAX_TEXT_CHARS = 500


@dataclass(frozen=True)
class RelayRequest:
    """一次递话请求：发到哪、发什么。"""

    destination_kind: str          # "private" | "group"
    destination_id: str
    text: str
    source_id: str = ""            # 发起窗口，用于“不要发给自己”


@dataclass(frozen=True)
class RelayDecision:
    allowed: bool
    code: str
    reason: str = ""
    needs_confirm: bool = False    # True 表示必须由核心管理员确认后才发送
    audience: str = ""             # "owner" | "admin_target"，便于审计区分来源


def decide(request: RelayRequest, *, actor_is_core: bool, core_target_id: str,
           allowed_targets=(), enabled: bool = True, require_confirm: bool = True,
           max_chars: int = MAX_TEXT_CHARS) -> RelayDecision:
    """判定这次递话是否允许，以及要不要确认。

    ``allowed_targets`` 是核心管理员配置的私聊白名单；``core_target_id`` 是
    核心管理员本人的私聊目标，用来承载“其他用户递给管理员”的那条路径。
    """
    if not enabled:
        return RelayDecision(False, DENIED_DISABLED, "当前窗口没有开启跨窗口递话")
    text = request.text if isinstance(request.text, str) else ""
    if not text.strip():
        return RelayDecision(False, DENIED_TEXT_EMPTY, "递话内容为空")
    if len(text) > max(1, int(max_chars)):
        return RelayDecision(False, DENIED_TEXT_TOO_LONG, f"递话内容超过 {max_chars} 字上限")
    if request.destination_kind != "private":
        return RelayDecision(False, DENIED_GROUP, "递话只支持私聊目标")
    destination = request.destination_id if isinstance(request.destination_id, str) else ""
    if not destination:
        return RelayDecision(False, DENIED_TARGET, "递话目标为空")
    if request.source_id and destination == request.source_id:
        return RelayDecision(False, DENIED_SELF, "目标就是当前窗口，无需递话")

    if actor_is_core:
        if destination not in set(allowed_targets or ()):
            return RelayDecision(False, DENIED_TARGET,
                                 "核心管理员只能发到已加入白名单的私聊目标")
        return RelayDecision(True, ALLOWED, needs_confirm=bool(require_confirm),
                             audience="admin_target")

    if not core_target_id:
        return RelayDecision(False, DENIED_TARGET, "尚未配置核心管理员的私聊目标")
    if destination != core_target_id:
        return RelayDecision(False, DENIED_TARGET,
                             "其他用户只能给核心管理员递话")
    # 递话给管理员本身不需要再确认弹窗：内容由发起者自己写，管理员收到即可。
    return RelayDecision(True, ALLOWED, needs_confirm=False, audience="owner")


__all__ = [
    "RelayRequest", "RelayDecision", "decide",
    "ALLOWED", "DENIED_DISABLED", "DENIED_TEXT_EMPTY", "DENIED_TEXT_TOO_LONG",
    "DENIED_GROUP", "DENIED_TARGET", "DENIED_SELF", "MAX_TEXT_CHARS",
]

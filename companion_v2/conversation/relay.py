"""跨窗口递话的执行计划：把配置、发起者身份与判定拼成一条待发送记录。

拆分理由：`relay_policy` 只回答"能不能发"，这里负责"发什么、记什么"，
真正的网络发送留在宿主层（`astrbot_host/`）。这样授权与审计可以先被测试钉住，
发送实现晚一步接上也不会改变已经承诺的行为。

产品口径（2026-10-19）：

* 核心管理员可以让 bot 帮忙私聊递话——只发白名单目标，默认需确认；
* 其他用户只能让 bot 给核心管理员递话——目标固定为管理员本人，无需确认；
* 群聊、未开启、空文本、超长、发给自己一律拒绝。
"""

from dataclasses import dataclass, field

from .relay_policy import RelayDecision, RelayRequest, decide

DEFAULT_MAX_CHARS = 500


@dataclass(frozen=True)
class RelayPlan:
    """一条可以直接交给宿主发送的递话计划。"""

    decision: RelayDecision
    destination_id: str = ""
    text: str = ""
    audit: dict = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    @property
    def needs_confirm(self) -> bool:
        return self.decision.needs_confirm


def _text_setting(value, default):
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def plan_relay(request: RelayRequest, settings, *, actor_is_core: bool,
               actor_id: str = "", source_label: str = "") -> RelayPlan:
    """给定窗口设置与发起者身份，产出递话计划（含审计字段）。

    ``settings`` 来自配置组 ``conversation.relay``；缺省即“未开启”，
    所以没有配置过的窗口不会意外获得跨窗口发送能力。
    """
    settings = settings if isinstance(settings, dict) else {}
    allowed = settings.get("allowed_targets")
    if isinstance(allowed, str):
        allowed = tuple(item.strip() for item in allowed.replace("[", "").replace("]", "")
                        .replace('"', "").split(",") if item.strip())
    decision = decide(
        request,
        actor_is_core=bool(actor_is_core),
        core_target_id=str(settings.get("core_target_id") or ""),
        allowed_targets=tuple(allowed or ()),
        enabled=settings.get("enabled") is True,
        require_confirm=settings.get("require_confirm") is not False,
        max_chars=_text_setting(settings.get("max_text_chars"), DEFAULT_MAX_CHARS),
    )
    audit = {
        "kind": "conversation.relay",
        "actor": actor_id,
        "actor_is_core": bool(actor_is_core),
        "source": source_label or request.source_id,
        "destination": request.destination_id,
        "audience": decision.audience,
        "code": decision.code,
        "chars": len(request.text or ""),
        "needs_confirm": decision.needs_confirm,
    }
    if not decision.allowed:
        return RelayPlan(decision, audit=audit)
    return RelayPlan(decision, request.destination_id, (request.text or "").strip(), audit)


__all__ = ["RelayPlan", "plan_relay", "DEFAULT_MAX_CHARS"]

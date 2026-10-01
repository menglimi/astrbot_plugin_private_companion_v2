"""「这份能力现在由谁对外表达」的通用记录。

## 为什么需要它

V2 与「我会牢牢记住你」（下称牢插件）在同一个进程里同时存在，两边都会向模型
注入记忆、也都会给模型一套记忆工具。这不是功能多，而是**同一件事被实现了两遍**：
模型会拿到两份互相矛盾的记忆叙事，并且会把新记忆分别写进两个库。真正需要的是
一个明确的归属判定——一段时期内只有一边对外表达，另一边退到后面继续记录。

## 为什么放在 capabilities 而不是 memory

因为要解决的问题不是「事实怎么存」，而是「哪一方对外承担这项能力」。同一个判定
以后可能出现在其它能力上（例如画像、时间线），所以它是一份能力级合同：域核心
（memory/conversation）只读它，宿主适配层负责**探测**别家插件的声明并写出结论。
``companion_v2`` 不许反向导入 ``astrbot_host``，所以真实探测被隔离在
:mod:`companion_v2.adapters.astrbot.memory_owner` 里的一个函数中。

## 四条纪律

1. **只读别人的声明**。不猜文件、不读别家数据库、不调用会改状态的接口；只调用
   它自己公开的取句柄函数，并读它自己报的生命周期。
2. **失败一律倒向「自己来」**。探测抛异常、声明缺失、句柄为 ``None``、句柄说
   自己已经停了——全部算 V2 自己承担。宁可两边都注入（可观察、可修），也不能
   两边都沉默：那正是本模块要防的那个故障。
3. **不落任何持久标志**。每次询问都重新判定，没有 latch、没有缓存，所以句柄消失
   的**下一个请求**就回到 V2 自己的记忆，不会把安装卡在错误状态里。
4. **结论要能给人看**。判定结果带着 ``owner`` / ``provider`` / ``reason``，页面
   据此写出「记忆现在由谁提供、为什么」，而不是让用户去猜为什么模型不再记得。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


# 把结论摊平成两个字段：谁在对外表达，为什么。
RENDER_EXTERNAL = "external"
"""别家插件正在对外提供这项能力（V2 让位）。"""

RENDER_SELF = "self"
"""V2 自己对外提供这项能力（别家不在、没启用、或者句柄坏了）。"""

RENDER_OWNERS = (RENDER_EXTERNAL, RENDER_SELF)

REASON_EXTERNAL_ACTIVE = "external_owner_active"
"""声明的句柄可用且自报在服务。"""

REASON_MODULE_ABSENT = "owner_module_absent"
"""没有加载任何提供方模块：V2 自己来。"""

REASON_DECLARATION_ABSENT = "owner_declaration_absent"
"""模块在，但找不到它公开的取句柄函数：V2 自己来。"""

REASON_HANDLE_DISABLED = "owner_handle_disabled"
"""取句柄函数返回 ``None``：声明说这个桥没启用。"""

REASON_HANDLE_UNREADABLE = "owner_handle_unreadable"
"""取句柄函数抛异常，或句柄自报已经停了：声明当下不可用。"""

REASONS = (
    REASON_EXTERNAL_ACTIVE,
    REASON_MODULE_ABSENT,
    REASON_DECLARATION_ABSENT,
    REASON_HANDLE_DISABLED,
    REASON_HANDLE_UNREADABLE,
)


@dataclass(frozen=True)
class MemoryOwnership:
    """一次判定结论，也是页面能照着说话的原文。"""

    owner: str
    reason: str
    module: str = ""
    provider: str = ""
    display_name: str = ""

    def __post_init__(self):
        if self.owner not in RENDER_OWNERS:
            raise ValueError("memory ownership must be external or self")
        if self.reason not in REASONS:
            raise ValueError("memory ownership requires a known reason code")

    @property
    def delegated(self) -> bool:
        return self.owner == RENDER_EXTERNAL

    def document(self) -> dict:
        """给页面和日志用的纯 JSON 文档；字段名就是页面读的那些。"""

        return asdict(self)


class MemoryProvider(Protocol):
    """宿主提供的窄端口：现在谁在对外提供记忆，为什么。

    只读、同步、无参数。判定必须能**失败**：实现抛异常时调用方按「V2 自己来」
    处理，绝不把异常继续抛给对话主链。
    """

    def state(self) -> MemoryOwnership:
        """Return the current owner of the model-facing memory capability."""


class SelfMemoryOwner:
    """没有别的提供方时的默认结论：V2 自己提供记忆。"""

    def __init__(self, reason: str = REASON_MODULE_ABSENT):
        if reason not in REASONS:
            raise ValueError("a local memory owner needs a known reason code")
        self.reason = reason

    def state(self) -> MemoryOwnership:
        return MemoryOwnership(owner=RENDER_SELF, reason=self.reason)


DEFAULT_MEMORY_OWNER = SelfMemoryOwner()


def delegated_memory(provider) -> bool:
    """这项能力现在是否由别家提供。

    探测不可用、结论类型不对、字段值不在允许集合里——统统按「V2 自己来」。
    这是本模块最重要的一条：判定的失败方向只能倒向「有人负责」，不能倒向
    「两边都不注入而没人说明」。
    """

    if provider is None:
        return False
    try:
        state = provider.state()
    except Exception:
        return False
    return isinstance(state, MemoryOwnership) and state.delegated


def failure_reason(provider) -> str:
    """判定不可用时该报告的原因码，供页面解释为什么又轮到 V2。"""

    if provider is None:
        return REASON_MODULE_ABSENT
    try:
        state = provider.state()
    except Exception:
        return REASON_HANDLE_UNREADABLE
    if isinstance(state, MemoryOwnership):
        return state.reason
    return REASON_HANDLE_UNREADABLE


__all__ = [
    "DEFAULT_MEMORY_OWNER",
    "MemoryOwnership",
    "MemoryProvider",
    "REASON_DECLARATION_ABSENT",
    "REASON_EXTERNAL_ACTIVE",
    "REASON_HANDLE_DISABLED",
    "REASON_HANDLE_UNREADABLE",
    "REASON_MODULE_ABSENT",
    "REASONS",
    "RENDER_EXTERNAL",
    "RENDER_OWNERS",
    "RENDER_SELF",
    "SelfMemoryOwner",
    "delegated_memory",
    "failure_reason",
]

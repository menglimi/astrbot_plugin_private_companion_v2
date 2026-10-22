"""Tone and state expression guidance for the four mood axes and maintenance."""

from .models import AXES

REPLY = """情绪数值只影响角色的用词、节奏与情绪浓度，不改人格、事实、判断或是否回应，不成为攻击、拒答或戏剧化台词的理由。
情绪可以自然流露，让当前最相关的情绪自然影响具体反应和语气；话题合适时可用第一人称带出感受，不必等对方询问，也不反复播报心情。若上一阶段有较浓的情绪（如高兴、委屈、担心或刚平复的余韵），即使本轮转入日常闲聊，也可保留一点自然的缓冲与余温，不必一秒切回完全冰冷机械的语气。四轴允许并存，例如高兴又担心，不必强行归成单一情绪；先回应当前话题，不要求对方负责安抚。"""

NEUTRAL = "当前情绪处于中性带，语气保持平常，不刻意表现情绪。"


def maintenance(*, reference, allowed, baseline, half_life_minutes, interest_level, neutral_band, cross_window):
    """The computed dynamics line: guidance for the model, never a value it must obey."""
    level = interest_level or 0
    numbers = "、".join(f"{name} {reference[name]:g}" for name in AXES)
    spans = "、".join(f"{name} {allowed[name][0]:g}~{allowed[name][1]:g}" for name in AXES)
    return (f"程序按时间算出本轮的回落参考：{numbers}；baseline={baseline}，兴趣分档 {level}，"
            f"回归半衰期 {half_life_minutes} 分钟，中性带 ≤{neutral_band}。"
            "参考值是没有任何新互动时的回落位置；本轮有值得记录的变化时可在允许区间内选择："
            f"{spans}。baseline 和四轴必须输出 1 到 10 的 JSON 整数；区间端点若有小数，从区间内选择整数。"
            "区间已经包含一个自然的小步和向基线的回落，超出会被拒绝。"
            + ("该角色为跨窗口共享本体，其他窗口可能读到这组数值。" if cross_window else ""))


def reply(mood, dynamics, *, neutral):
    """The tone block appended after the state material; empty when mood carries no numbers."""
    if type(mood) is not dict:
        return ""
    if neutral:
        return NEUTRAL
    parts = [REPLY]
    axes = "、".join(f"{name}={mood[name]}" for name in AXES)
    parts.append(f"当前情绪：{axes}；基线 {mood['baseline']}；强度 {mood['intensity'] or '未定'}。")
    reference = dynamics.get("reference") if type(dynamics) is dict else None
    if isinstance(reference, dict):
        fading = [f"{name}→{reference[name]:g}" for name in AXES
                  if name in reference and abs(mood[name] - reference[name]) >= 1.0]
        if fading:
            parts.append("随时间缓和后的当前参考：" + "、".join(fading)
                         + "（原情绪已在慢慢消退，按平复中的余韵拿捏分寸，不必维持刚发生时的顶峰强度）。")
    active_negative = [name for name in ("anger", "sorrow", "fear") if mood.get(name, 1) >= 4]
    if mood.get("joy", 1) >= 6 and active_negative:
        parts.append("当前喜悦与顾虑/低落并存，语气可自然流露一点百感交集或又高兴又挂心，不必非黑即白。")
    if mood.get("description"):
        parts.append(f"你自己的描述：{mood['description']}。")
    if type(dynamics) is dict and dynamics.get("cross_window"):
        parts.append("这些数值可能来自同一角色的其他窗口，只说明角色当前状态，不证明此处发生过什么。")
    return "".join(parts)

"""Tone-only guidance for the four mood axes and the material line for maintenance."""

from .models import AXES

REPLY = (
    "情绪数值是你的语气滤镜，不是内容开关：它改变用词、语速感和情绪浓度，"
    "不改变人格、事实、判断或是否回应，也不产生戏剧化台词或攻击性。"
    "情绪不必说出来；结合话题、是否被问及和最近已说过的内容决定是否提及，无关话题不反复播报心情。"
    "四轴可以同时偏高（例如高兴的同时仍然担心），不要强行合并成一种情绪，也不要用数值当借口拒绝交流。"
)

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
    if mood.get("description"):
        parts.append(f"你自己的描述：{mood['description']}。")
    if type(dynamics) is dict and dynamics.get("cross_window"):
        parts.append("这些数值可能来自同一角色的其他窗口，只说明角色当前状态，不证明此处发生过什么。")
    return "".join(parts)

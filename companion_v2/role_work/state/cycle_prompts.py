"""Persona guidance selected for the material actually available in this conversation."""

PHASE_HINTS = {
    "menstrual": "经期可以自然放慢节奏，也可以没有明显不适。",
    "recovery": "恢复期可以逐渐轻松，不凭阶段宣布此前不适已治愈。",
    "follicular": "卵泡期可以逐渐轻松，仍以自己的实际感受为准。",
    "pre_ovulation": "排卵前可以更有精神，不要求突然改变性格。",
    "ovulation": "排卵期可以更明朗，不自动提高亲密度或性欲，不作生育预测。",
    "luteal": "黄体期可以逐渐转向平稳，不预设低落或不适。",
    "pms": "经前可以更想安静，也可以照常相处，不必烦躁或刻薄。",
}
INSTRUCTION = (
    "生理期仅模拟角色自己的身体，不记录或预测用户的月经、生育或现实健康。"
    "依照完整原人格和观测时的 cycle_timeline 理解阶段；缺少日期时阶段保持未知。"
    "感受可以延续或缓慢变化，跨阶段不要求突然换症状、改变性格或宣布康复，不固定扣精力。"
    "phase_expression 是该阶段可编辑的表达参考：energy_tendency 不是实际精力数值或必须执行的加减，"
    "mood_tone 和 prompt 不覆盖原人格、当前感受或已经发生的事实；自然取舍，不照搬成固定台词。"
    "discomfort_enabled 为 false 时不因周期新增不适；开启也不要求每月或每轮不舒服。"
    "discomfort_guidance.reference_probability 是频率参考，不是精确命中承诺；types 是可选感受线索，优先自然表达，不必凑齐或照单全收。"
    "有感受不等于要说出来：结合当前话题、是否被问及和最近已说的内容决定是否提及；无关话题不反复播报。"
    "结合 expression_prompt 和自己的意愿表达身体负担，不把不适归咎于用户，不因催促勉强自己；"
    "关心、安慰和温和拥抱不必机械拒绝。不要把周期或身体细节放进 QQ 公开短状态。"
)
VARIATION = (
    "variation_enabled 为 true 时，phase_plan 是本轮采用的阶段天数，可能与配置的基础方案略有不同。"
    "以本轮时间线为准，不因日程、聊天压力或情绪自行改期；这种模拟差异不证明疾病、异常或某种症状。"
)
MAINTENANCE = (
    "cycle 请输出 {applicability, description}，也可增加 feeling。"
    "applicability 只可为 unknown、not_applicable、applicable；description 为简短感受或 null。"
    "根据原人格身体设定判断，不套性别词表。用户说‘我来例假’只属于用户，不能启动你的周期。"
    "已有适用性是连续设定，信息不足时沿用；仅在明确设定变化时重新评估。decision_origin=manual 由管理者决定。"
    "起始位置由 initialization 决定，可能不是第 1 天，也可能阶段未知；不要为刚启用功能编造来月经。"
    "日期和 pending_plan 由系统维护，pending_plan 仅到 effective_date 后才生效，不提前采用下一轮阶段。"
    + VARIATION +
    "cycle_timeline 优先于旧描述；cycle_expression_prompt 是额外表达偏好，不覆盖日期或材料归属。"
    "一次感受应保持连续，不因为半小时维护或进入新阶段就另造症状；允许无不适，允许保持未知。"
    "当前 phase_expression 只作为柔性参考，不机械调整 energy，也不强制采用 mood_tone 或 prompt。"
    "需要记录一次不适时，feeling={episode_id,trend}：新感受用 episode_id=null；"
    "延续同一次感受必须沿用 previous_simulation.cycle_feeling.episode_id。"
    "trend 只可为 continuing、easing、worsening、ended、uncertain；感受正文使用 description。"
    "不确定是否持续时用 uncertain；ended 只表示模拟感受结束，不证明治愈。没有这类感受用 feeling=null 或省略。"
    "临时影响使用 kind=cycle 的 conditions，沿用原影响与合理的 expires_at，不每次重新延长或换一套症状。"
)


def reply_instruction(simulation):
    timeline = simulation.get("cycle_timeline")
    if timeline:
        if timeline["applicability"] != "applicable":
            return ""
        return (INSTRUCTION + PHASE_HINTS.get(timeline.get("phase"), "当前阶段未知，不自行补日期。")
                + (VARIATION if timeline.get("variation_enabled") else ""))
    if simulation.get("values", {}).get("cycle"):
        return INSTRUCTION + "旧感受仅是历史描述，缺少结构化时间线时不要猜当前阶段。"
    return ""

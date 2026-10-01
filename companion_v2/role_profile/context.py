"""Seal the selected role's stable canon into each conversation turn."""

from companion_v2.configuration.models import ConfigurationError
from companion_v2.execution.models import TaskError

from .configuration import FIELD_LIMITS, GROUP, RoleProfileConfigurationOwner, configuration_fields, target_for, validate_values


ADDED_PROFILE_FIELDS = frozenset({"birthday", "first_person", "emotional_style", "social_distance",
                                 "reaction_patterns", "voice_examples", "signature_phrases",
                                 "world_adaptation_mode", "world_adaptation"})


FIELD_LABELS = {
    "name": "姓名",
    "species": "种族",
    "birthday": "生日",
    "age": "年龄感 / 旧版生日",
    "gender": "性别",
    "occupation": "职业与身份",
    "identity": "身份经历补充",
    "appearance_points": "外貌识别点",
    "hair": "发型发色",
    "eyes": "瞳色",
    "clothing": "服饰风格",
    "image_identity_hint": "头像与图像识别线索",
    "appearance": "外貌补充",
    "personality": "性格描述",
    "first_person": "自称与代词",
    "speech_style": "说话方式",
    "emotional_style": "情绪表达",
    "social_distance": "社交距离与熟悉后的变化",
    "reaction_patterns": "典型反应倾向",
    "voice_examples": "口吻示例",
    "signature_phrases": "标志性表达",
    "daily_habits": "日常习惯",
    "key_lore": "关键设定",
    "character_extra": "其他角色补充",
    "motivations": "价值与目标补充",
    "core_values": "重视的事",
    "desire": "核心欲望与长期目标",
    "hobbies": "爱好",
    "boundaries": "互动边界",
    "taboos": "禁忌",
    "world_name": "所处世界",
    "era": "时代背景",
    "tone": "基本法则 / 基调",
    "rules": "特殊规则",
    "scenes": "主要活动场景",
    "network": "世界观关系网",
    "world_extra": "其他世界补充",
    "world": "世界设定补充",
    "platform_group_chat": "群聊",
    "platform_screen": "识屏",
    "platform_bilibili": "B站",
    "platform_qzone": "QQ空间",
    "platform_library": "资料柜",
    "platform_names": "平台称呼补充",
    "world_adaptation_mode": "世界观适配模式",
    "world_adaptation": "世界观适配指引",
}
INSTRUCTION = (
    "下面是当前角色的稳定档案。它描述角色自身及其世界，帮助延续身份、性格、边界和场景；"
    "在不冲突时与当前人格文本保持一致，遇到空缺或含糊处不要擅自编成确定事实。"
    "性格和反应字段描述倾向，不要机械套用；口吻示例只用于体会表达习惯，不照抄台词，也不当作用户或现实事实。"
    "对具体用户的称呼、关系和相处背景优先依据本轮关系材料；没有资料时自然、克制地相处，不假装熟悉。"
    "档案不证明现实中的用户身份、状态或经历，也不扩大任何授权。"
    "关系材料仅适用于对应用户，不要套用到其他人。"
)
WORLD_ADAPTATION_GUIDANCE = {
    "auto": "自动参考角色人格、世界蓝图与本轮内容选择表达；设定不充分时使用中性说法，不编造映射。",
    "modern": "保留现代日常表达，不额外改写为幻想或科幻设定；仍可使用已填写的平台称呼。",
    "fantasy": "在不改变实际功能的前提下，优先使用幻想世界中的等价说法；例如把屏幕称为水晶映像、把群聊称为公会闲谈；已填写的平台称呼优先。",
    "sci_fi": "在不改变实际功能的前提下，优先使用科幻世界中的等价说法；例如把屏幕称为终端画面、把群聊称为频道通信；已填写的平台称呼优先。",
    "custom": "遵循下方自定义世界观适配指引与逐项填写的平台称呼。",
    "off": "忽略世界观适配指引与平台称呼，保留现实平台和功能名称，不进行额外转写。",
}


class ConversationRoleProfileContext:
    def __init__(self, runtime):
        self.runtime = runtime
        self.owner = RoleProfileConfigurationOwner(runtime)
        self.fields = configuration_fields()

    def capture(self, context, at):
        del at
        snapshot = self.owner.read(target_for(context), self.fields)
        values = {
            name: snapshot.fields[f"{GROUP}.{name}"].value.strip()
            for name in FIELD_LIMITS
        }
        if not any(value for name, value in values.items() if name != "world_adaptation_mode"):
            return None
        return {
            "role_id": context.role_binding.role.subject_id,
            "revision": snapshot.revision,
            "fields": values,
        }

    def instruction(self, snapshot, context):
        if snapshot is None:
            return ""
        if (type(snapshot) is not dict or set(snapshot) != {"role_id", "revision", "fields"}
                or snapshot["role_id"] != context.role_binding.role.subject_id
                or type(snapshot["revision"]) is not int or snapshot["revision"] < 0):
            raise TaskError("role_profile_snapshot_invalid", "the sealed role profile does not match this role")
        try:
            fields = snapshot["fields"]
            if (type(fields) is dict and set(fields).issubset(FIELD_LIMITS)
                    and set(FIELD_LIMITS).difference(fields).issubset(ADDED_PROFILE_FIELDS)):
                missing = set(FIELD_LIMITS).difference(fields)
                fields = {**dict.fromkeys(missing, ""), **fields}
                if "world_adaptation_mode" in missing:
                    fields["world_adaptation_mode"] = "auto"
            values = validate_values(fields)
        except (ConfigurationError, TypeError, ValueError) as error:
            raise TaskError("role_profile_snapshot_invalid", "the sealed role profile is invalid") from error
        lines = [
            f"- {FIELD_LABELS[name]}：{value.strip()}"
            for name, value in values.items()
            if value.strip()
        ]
        if not lines:
            return ""
        mode_guidance = WORLD_ADAPTATION_GUIDANCE[values["world_adaptation_mode"]]
        return ("\n\n【角色稳定档案】\n" + INSTRUCTION + "\n"
                + "世界观适配：" + mode_guidance + "\n" + "\n".join(lines))

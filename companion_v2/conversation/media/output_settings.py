"""Role image triggers and prompt preferences used by the native image path."""

import json
import re

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.configuration.registry import FieldDefinition, ValueKind
from companion_v2.execution.models import TaskError

GROUP = OWNER = "conversation.image_output"
LAYERS = (ConfigLayer.INSTALLATION, ConfigLayer.ROLE)
CHOICES = {
    "trigger_mode": {"tool", "rules", "off"},
    "prompt_format": {"traditional", "natural", "nai"},
    "style": {"realistic", "anime", "custom"},
    "negative_mode": {"safe_default", "merge", "replace"},
}
DEFAULT_SCENE_PRESETS = (
    {"id": "home-night", "name": "睡前居家", "prompt": "cozy bedroom, warm bedside light, relaxed home clothing"},
    {"id": "campus-day", "name": "校园日常", "prompt": "natural campus daytime, candid everyday atmosphere"},
    {"id": "formal-event", "name": "正式场合", "prompt": "formal event setting, composed posture, refined clothing"},
)
SCENE_MARKER = re.compile(r"\[场景预设[:：]([^\]\r\n]{1,40})\]")
DEFAULTS = {
    "allow_user_requests": True, "trigger_mode": "tool", "rule_max_daily": 3,
    "proactive_probability": 0.35, "proactive_max_daily": 1,
    "prompt_format": "traditional", "style": "realistic", "style_prompt": "",
    "negative_mode": "safe_default", "negative_prompt": "",
    "text2img_fixed_prompt": "clean composition, environmental storytelling",
    "selfie_fixed_prompt": "stable facial features, natural selfie framing",
    "edit_fixed_prompt": "preserve unedited pixels, no unrelated redesign",
    "text2img_negative_prompt": "lowres, text, watermark",
    "selfie_negative_prompt": "inconsistent facial features",
    "edit_negative_prompt": "unrequested redesign, identity change",
    "scene_presets_json": json.dumps(DEFAULT_SCENE_PRESETS, ensure_ascii=False, separators=(",", ":")),
}


def configuration_fields():
    return tuple(FieldDefinition(GROUP + "." + key, GROUP, GROUP,
        ValueKind.BOOLEAN if type(value) is bool else ValueKind.INTEGER if type(value) is int
        else ValueKind.PROBABILITY if type(value) is float else ValueKind.TEXT, value,
        layers=LAYERS, owner_id=OWNER,
        **({"minimum": 0, "maximum": 1} if type(value) is float else
           {"minimum": -1, "maximum": 100} if type(value) is int else {}))
        for key, value in DEFAULTS.items())


class ImageOutputConfigurationOwner(SparseConfigurationOwner):
    owner_id = OWNER

    def write(self, target, fields, **kwargs):
        current = self.read(target, fields)
        values = {key.rsplit(".", 1)[-1]: item.value for key, item in current.fields.items()}
        values.update({key.rsplit(".", 1)[-1]: value for key, value in kwargs["changes"].items()})
        for key, choices in CHOICES.items():
            if values.get(key) not in choices:
                raise TaskError("image_output_configuration_invalid", "invalid image preference")
        if any(type(value) is str and len(value) > 4000 for value in values.values()):
            raise TaskError("image_output_configuration_invalid", "image prompt exceeds 4000 characters")
        parse_scene_presets(values.get("scene_presets_json", DEFAULTS["scene_presets_json"]))
        return super().write(target, fields, **kwargs)


def effective_settings(runtime, context):
    target = ConfigTarget(context.scope.installation_id, ConfigLayer.ROLE,
                          context.role_binding.role, bot_id=context.scope.bot_id)
    snapshot = ImageOutputConfigurationOwner(runtime).read(target, configuration_fields())
    values = {key.rsplit(".", 1)[-1]: item.value for key, item in snapshot.fields.items()}
    return {**DEFAULTS, **values}


def parse_scene_presets(value):
    if type(value) is not str or len(value) > 4000:
        raise TaskError("image_output_configuration_invalid", "scene presets must be bounded JSON text")
    try:
        presets = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise TaskError("image_output_configuration_invalid", "scene presets must be a JSON list") from error
    if type(presets) is not list or len(presets) > 12:
        raise TaskError("image_output_configuration_invalid", "scene presets allow at most 12 entries")
    ids, names = set(), set()
    for item in presets:
        if type(item) is not dict or set(item) != {"id", "name", "prompt"}:
            raise TaskError("image_output_configuration_invalid", "each scene preset needs an id, name and prompt")
        identifier, name, prompt = item["id"], item["name"], item["prompt"]
        if (type(identifier) is not str or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,31}", identifier)
                or type(name) is not str or not name.strip() or name != name.strip() or len(name) > 24
                or type(prompt) is not str or not prompt.strip() or prompt != prompt.strip() or len(prompt) > 800
                or identifier in ids or name in names):
            raise TaskError("image_output_configuration_invalid", "scene preset names and ids must be unique and bounded")
        ids.add(identifier)
        names.add(name)
    return tuple(presets)


def prompt_instruction(values):
    if not values["allow_user_requests"] or values["trigger_mode"] == "off":
        return "当前角色已关闭用户请求生图和改图；按本轮话题自然回应，图片请求可简短说明暂不能执行。"
    formats = {"traditional": "使用简洁的英文画面标签，以逗号分隔",
               "natural": "使用连贯的自然语言描述构图、人物与场景",
               "nai": "使用 NAI 标签格式，可用花括号表达强调，避免聊天句式"}
    trigger = (
        "用户用自然语言要新图片、画图、自拍、头像或改图时，使用本轮开放的图片工具完成，无需特定指令。"
        "“来张自拍看看”“想看你现在的穿搭”已经表达了看图需求；承接尚未完成的同一请求时，"
        "结合最近对话理解“看看”“当然”“继续”“再来一张”，不要求对方重复整句。"
        "需求清楚时可自然接话并执行；确实缺少影响画面的关键信息时再问一句。"
        "玩笑、讨论摄影或泛泛问近况仍按普通聊天理解，已完成的请求不因后续应声重复生图。"
        "角色本人出镜时，按当前人设与已知对话展开外观、穿搭、动作和场景；"
        "近期明确换装或换景优先，缺少的细节可自然创作，不把生成画面说成现实观测。"
        "自拍画面在 prompt 中写明 selfie，以便应用角色的自拍提示词。"
        "图片请求以实际图片工具结果接续，不用反复确认、只说稍等或改邀其他活动代替。"
    )
    presets = parse_scene_presets(values.get("scene_presets_json", DEFAULTS["scene_presets_json"]))
    scene = ("可用场景预设：" + "、".join(item["name"] + "（ID:" + item["id"] + "）" for item in presets)
             + "。场景与用户要求吻合时，可在图片工具 prompt 中标记 [场景预设:名称]；"
               "宿主会替换为对应画面提示词，不要把标记写入解释或回复。" if presets else "")
    return "图片调用偏好：" + trigger + "\n图片 prompt 应" + formats[values["prompt_format"]] + "。" + scene


def apply_prompts(arguments, action, values):
    result = dict(arguments)
    original = result.get("prompt", "")
    presets = parse_scene_presets(values.get("scene_presets_json", DEFAULTS["scene_presets_json"]))
    selected_names = []
    for match in SCENE_MARKER.finditer(original):
        name = match.group(1).strip()
        if name not in selected_names:
            selected_names.append(name)
    original = SCENE_MARKER.sub("", original).strip()
    scene_prompts = [item["prompt"] for name in selected_names for item in presets if item["name"] == name]
    kind = "edit" if action != "image.generate" else (
        "selfie" if re.search(r"自拍|selfie|self.portrait", original, re.I) else "text2img")
    style = {"realistic": "photorealistic", "anime": "anime illustration", "custom": ""}[values["style"]]
    blocks = [values[kind + "_fixed_prompt"], style, values["style_prompt"], *scene_prompts, original]
    delimiter = "\n" if values["prompt_format"] == "natural" else ", "
    result["prompt"] = delimiter.join(block.strip() for block in blocks if block.strip())
    defaults = values[kind + "_negative_prompt"]
    negative = defaults if values["negative_mode"] == "safe_default" else (
        delimiter.join(block for block in (defaults, values["negative_prompt"]) if block)
        if values["negative_mode"] == "merge" else values["negative_prompt"])
    # User exclusions remain attached even when replacing the system negative text.
    result["negative_prompt"] = delimiter.join(block for block in (negative, result.get("negative_prompt", "")) if block)
    return result

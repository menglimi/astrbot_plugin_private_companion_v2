"""Natural-language image requests in AstrBot's existing core tool loop."""

from collections.abc import Mapping
import json
import logging
from zoneinfo import ZoneInfo

from companion_v2.conversation.media.generated import IMAGE_ACTIONS
from companion_v2.conversation.media.output_settings import effective_settings, prompt_instruction
from companion_v2.references.prompts import IMAGE_REFERENCE_INSTRUCTION

from .native_extensions.request_context import set_system_instruction


logger = logging.getLogger(__name__)
_PURPOSES = {
    "image.generate": "按画面描述生成新图，包括无参考图的角色自拍、头像、穿搭照与普通场景",
    "image.edit": "依据本轮附图、已保存产物或角色参考素材改图，也可用人设参考图拍新的自拍",
    "image.mask_edit": "使用明确底图和蒙版做局部编辑",
}
_DELIVERY = (
    "生成工具返回的图片由 AstrBot 缓存供查看，生成成功与已经发给对方是两个步骤。"
    "图片符合请求时，把工具结果实际提供的缓存原路径交给 send_message_to_user，"
    "使用 messages=[{\"type\":\"image\",\"path\":\"工具返回的原路径\"}] 投递当前会话，session 留空。"
    "需要随图说话可在同一 messages 中加入 plain.text；投递成功后自然收住，避免重复发送同一张图或重复随图正文。"
    "根据工具结果说明实际进展：没有成功结果时不声称已生成或送达，unknown 时保留原操作，不换编号重做。"
    "短文字可以表达角色语气，但发起图片请求后的核心动作仍是完成图片生成与投递。"
)


def core_image_tool_contract(action, description, parameters):
    """Annotate only the request-local schema; leave the provider catalog intact."""
    if action not in _PURPOSES:
        return description, parameters
    description = _PURPOSES[action] + "；返回图片原件与操作回执，生成成功本身不代表已发送。"
    properties = parameters.get("properties", {})
    prompt = properties.get("prompt")
    if isinstance(prompt, dict):
        prompt["description"] = (
            "本次画面或修改要求，按图片调用偏好的格式书写；角色出镜时展开当前外观、穿搭与场景，自拍写明 selfie。"
        )
    return description, parameters


def core_image_tools(session, offered):
    """Keep role-disabled image tools out of this request's private ToolSet."""
    if not any(item.spec.action in IMAGE_ACTIONS for item in offered):
        return offered, None
    try:
        values = effective_settings(session.application.runtime, session.context)
    except Exception as error:
        logger.warning("[CompanionV2] 核心生图偏好暂不可用 error_type=%s", type(error).__name__)
        return tuple(item for item in offered if item.spec.action not in IMAGE_ACTIONS), None
    if not values["allow_user_requests"] or values["trigger_mode"] == "off":
        return tuple(item for item in offered if item.spec.action not in IMAGE_ACTIONS), None
    return offered, values


def _reference_date(session):
    prepared = session.prepared
    original = prepared.get("native_input") if isinstance(prepared, Mapping) else None
    at = getattr(original, "at", None) or session.application.tasks.now()
    timezone_name = getattr(session.application.messages, "timezone_name", "Asia/Shanghai")
    snapshot = prepared.get("perception_context") if isinstance(prepared, Mapping) else None
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except ValueError:
            snapshot = None
    clock = snapshot.get("current_local_time") if isinstance(snapshot, Mapping) else None
    if isinstance(clock, Mapping):
        timezone_name = clock.get("timezone") or timezone_name
    return at.astimezone(ZoneInfo(timezone_name)).date().isoformat()


def inject_core_image_prompt(session, request, offered, values):
    """Keep configuration in system and role reference data in the turn suffix."""
    session.state.pop("_image_reference_material", None)
    actions = tuple(item.spec.action for item in offered if item.spec.action in IMAGE_ACTIONS)
    if not actions or values is None:
        set_system_instruction(request, "image_output")
        return
    from .core_reply_tools import native_tool_name

    descriptions = "\n".join(native_tool_name(action) + "：" + _PURPOSES[action] for action in actions)
    instruction = prompt_instruction(values) + "\n本轮图片工具：\n" + descriptions + "\n" + _DELIVERY
    if "image.edit" in actions:
        instruction += (
            "\n本轮参考素材位于 companion_v2_context.image_reference_material。"
            "角色自拍有可用身份锚点时，可通过改图工具的 reference_ids 与 reference_roles=[\"identity\"] 保持人物一致；"
            "仅采用已存素材时用 reference_indices=[]，避免带入本轮无关附图。"
            "没有可用身份图时，依照已知角色外观使用生成工具；只有改图工具可用且没有任何参考图时，"
            "简短说明需要图片参考，不猜素材 ID。\n" + IMAGE_REFERENCE_INSTRUCTION
        )
        owner = getattr(session.application.messages, "reference_materials", None)
        if owner is not None:
            try:
                material = owner.prompt_material(session.context, local_date=_reference_date(session))
                if isinstance(material, dict) and (material.get("references") or material.get("wardrobe")):
                    session.state["_image_reference_material"] = material
            except Exception as error:
                logger.warning("[CompanionV2] 核心生图参考资料暂不可用 error_type=%s", type(error).__name__)
    set_system_instruction(request, "image_output", instruction)

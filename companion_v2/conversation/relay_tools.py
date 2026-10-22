"""First-party model tool declarations for controlled cross-window relaying."""

from companion_v2.capabilities.models import CapabilityPackageDescriptor
from companion_v2.conversation.external_tools import ExtensionToolDescriptor
from companion_v2.execution.models import ProviderBinding, SideEffect, encode
from companion_v2.model_gateway.models import ToolSpec


EXTENSION = "conversation.relay"
PACKAGE_ID = "companion_v2.conversation.relay"
PUBLISHER_ID = "astrbot_plugin_private_companion"
PACKAGE_VERSION = "1.0.0"
ARTIFACT_HASH = "included-conversation-relay-1.0.0"
PROVIDER = "companion.relay"
GENERATION = "included-1"
DATASET_OWNER = "conversation.relay.audit"

PROPOSE_ACTION = "relay_message"
SEND_ACTION = "relay_send"
RELAY_ACTIONS = frozenset((PROPOSE_ACTION, SEND_ACTION))


def package_descriptor():
    return CapabilityPackageDescriptor(
        extension_id=EXTENSION,
        package_id=PACKAGE_ID,
        publisher_id=PUBLISHER_ID,
        package_version=PACKAGE_VERSION,
        artifact_hash=ARTIFACT_HASH,
        capabilities=(PROPOSE_ACTION, SEND_ACTION),
        dataset_owners=(DATASET_OWNER,),
    )


def _descriptor(action, description, properties, required, side_effect):
    schema = encode({"type": "object", "additionalProperties": False,
                     "properties": properties, "required": list(required)})
    return ExtensionToolDescriptor(
        ToolSpec(action, description, schema),
        package_descriptor(),
        ProviderBinding(PROPOSE_ACTION if action == PROPOSE_ACTION else SEND_ACTION,
                        PROVIDER, PACKAGE_VERSION, GENERATION),
        DATASET_OWNER,
        side_effect=side_effect,
        timeout_seconds=20,
    )


def tool_descriptors():
    return (
        _descriptor(
            PROPOSE_ACTION,
            "准备一条跨窗口私聊递话，不会发送。只在用户明确要求代为转达时调用，并沿用用户给出的目标和原文。"
            "返回 awaiting_confirmation 时，把目标、正文和确认编号告诉用户，等待用户明确回复‘确认发送’后再调用发送工具；"
            "返回 ready 时可以在当前轮继续调用发送工具。",
            {"destination_id": {"type": "string", "description": "收件人的私聊账号 ID。"},
             "text": {"type": "string", "description": "用户要求转达的原文，不要自行改写。"}},
            ("destination_id", "text"), SideEffect.NONE,
        ),
        _descriptor(
            SEND_ACTION,
            "发送 relay_message 返回的那一条待发送私聊。必须沿用同一确认编号、目标和原文。"
            "需要确认时，confirmed 只能在当前用户消息明确回复‘确认发送’后设为 true；参数本身不构成确认。"
            "如果上次结果未知，不要再次调用或换编号重发。",
            {"operation_id": {"type": "string", "description": "relay_message 返回的确认编号。"},
             "destination_id": {"type": "string", "description": "与待发送操作完全一致的私聊账号 ID。"},
             "text": {"type": "string", "description": "与待发送操作完全一致的原文。"},
             "confirmed": {"type": "boolean", "description": "仅在当前用户消息明确确认后为 true；否则为 false。"}},
            ("operation_id", "destination_id", "text", "confirmed"), SideEffect.MESSAGE_DELIVERY,
        ),
    )


__all__ = ["ARTIFACT_HASH", "DATASET_OWNER", "EXTENSION", "GENERATION", "PACKAGE_ID", "PACKAGE_VERSION",
           "PROPOSE_ACTION", "PROVIDER", "PUBLISHER_ID", "RELAY_ACTIONS", "SEND_ACTION",
           "package_descriptor", "tool_descriptors"]

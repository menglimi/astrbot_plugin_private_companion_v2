"""Keep QQ voice and optional reaction attachments in supported messages."""

from astrbot.core.message.components import BaseMessageComponent, ComponentType, Image, Record
from astrbot.core.message.message_event_result import MessageChain


class _OneBotEmojiImage(BaseMessageComponent):
    type: ComponentType = ComponentType.Image
    file: str

    def toDict(self):
        return {"type": "image", "data": {"file": self.file, "sub_type": 1}}


def _derive(message, chain):
    derive = getattr(message, "derive", None)
    return derive(chain) if callable(derive) else MessageChain(chain=chain)


def native_reply_messages(event, message):
    chain = getattr(message, "chain", None)
    if not isinstance(chain, (list, tuple)):
        return (message,)
    getter = getattr(event, "get_platform_name", None)
    qq = callable(getter) and getter() == "aiocqhttp"
    groups, current = [], []
    for part in chain:
        reaction = getattr(part, "_companion_v2_reaction_attachment", None)
        separate = (qq and isinstance(part, Record)) or (
            isinstance(reaction, dict) and reaction.get("delivery_mode") != "same_message")
        if separate:
            if current:
                groups.append(_derive(message, current))
                current = []
            groups.append(_derive(message, [part]))
        else:
            current.append(part)
    if current:
        groups.append(_derive(message, current))
    return tuple(groups)


async def native_wire_message(event, message):
    """The SDK's Image conversion drops sub_type; keep it for owned QQ stickers."""
    getter = getattr(event, "get_platform_name", None)
    if not callable(getter) or getter() != "aiocqhttp":
        return message
    chain = getattr(message, "chain", None)
    if not isinstance(chain, (list, tuple)):
        return message
    output = []
    changed = False
    for part in chain:
        reaction = getattr(part, "_companion_v2_reaction_attachment", None)
        if isinstance(part, Image) and isinstance(reaction, dict) and reaction.get("image_format") == "qq_emoji":
            output.append(_OneBotEmojiImage(file="base64://" + await part.convert_to_base64()))
            changed = True
        else:
            output.append(part)
    return _derive(message, output) if changed else message

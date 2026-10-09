"""Synthetic reply-image selections from host-offered evidence only."""

import json

from tests.native_adapter_support import completion, final_text


def offered_images(payload):
    content = payload["messages"][2]["content"]
    result = []
    if isinstance(content, list):
        for part in content[1:]:
            if part["type"] == "text":
                handle = json.loads(part["text"]).get("sendable_image")
                if handle and handle not in result:
                    result.append(handle)
    return result


def image_reply(payload, *, text="把这张原图附在这里。", handles=None):
    value = json.loads(final_text(text))
    if text == "":
        value["action"] = "image"
        value["claims"] = []
    value["images"] = offered_images(payload) if handles is None else handles
    return completion(json.dumps(value, ensure_ascii=False))


async def attach_originals(payload, _):
    return image_reply(payload)

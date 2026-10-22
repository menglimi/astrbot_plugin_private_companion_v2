"""Decode an ordered reply header and its JSON string without exposing wire text."""

import json
import re

from companion_v2.conversation.foreground import ModelDraft
from companion_v2.execution.models import encode
from .model_wire import decode_text_response, strict_json


_STRING_UNIT = re.compile(r'[^"\\\x00-\x1f]+|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})')
STREAM_REPLY_INSTRUCTION = (
    "本轮采用边生成边发送：JSON 字段顺序必须是 action、claims、可选 images、最后 text。先确定完整动作和事实引用，再生成正文；claims 的 statement 仍须逐字出现在 text 中，text 必须是最后一个字段。正文一旦输出不能修改或重写；需调用工具时只输出工具调用，不同时写正文。正常使用本轮分段词、自然停顿或已启用的分段标记；不在正文里解释发送机制。"
)


class OrderedReplyStream:
    def __init__(self, wire):
        self.wire = wire
        self.raw = ""
        self.position = 0
        self.header = {}
        self.text_start = None
        self.string_end = None
        self.draft_header = None
        self.disabled = False
        self.opened = False

    def feed(self, fragment):
        self.raw += fragment
        if len(self.raw) > 131072:
            raise ValueError("stream reply exceeds the wire limit")
        if self.disabled:
            return None
        if self.text_start is None:
            if not self._header():
                return None
        end = self.position
        while end < len(self.raw):
            if self.raw[end] == '"':
                self.string_end = end + 1
                break
            unit = _STRING_UNIT.match(self.raw, end)
            if unit is None:
                # Escapes, including a surrogate pair, may span SDK chunks.
                if self.raw[end] != "\\":
                    raise ValueError("invalid reply string")
                break
            end = unit.end()
        self.position = end
        if self.string_end is not None:
            remainder = self.raw[self.string_end:].strip()
            if remainder and remainder != "}":
                raise ValueError("stream text must be the final field")
        text = json.loads(self.raw[self.text_start:end] + '"')
        if len(text) > 65536:
            raise ValueError("stream text exceeds the reply limit")
        # json.loads can return an unpaired high surrogate while the next half
        # is still in flight. Never hand that temporary value to a sender.
        if text and 0xD800 <= ord(text[-1]) <= 0xDBFF:
            text = text[:-1]
        if any(0xD800 <= ord(char) <= 0xDFFF for char in text):
            raise ValueError("reply contains an unpaired surrogate")
        if not text.strip() or self.draft_header is None:
            return None
        return ModelDraft(text, self.draft_header.claims, self.draft_header.action)

    def _header(self):
        raw = self.raw
        position = self.position
        if not self.opened:
            position = len(raw) - len(raw.lstrip())
            if position == len(raw):
                return False
            if raw[position] != "{":
                raise ValueError("stream reply requires a JSON object")
            self.opened = True
            self.position = position + 1
        while True:
            position = self.position
            while position < len(raw) and raw[position].isspace():
                position += 1
            try:
                key, end = json.JSONDecoder().raw_decode(raw, position)
            except json.JSONDecodeError:
                return False
            if not isinstance(key, str) or key not in ("action", "claims", "images", "text") or key in self.header:
                raise ValueError("invalid or duplicate stream reply field")
            while end < len(raw) and raw[end].isspace():
                end += 1
            if end == len(raw):
                return False
            if raw[end] != ":":
                raise ValueError("invalid stream reply field")
            end += 1
            while end < len(raw) and raw[end].isspace():
                end += 1
            if end == len(raw):
                return False
            if key == "text":
                if not {"action", "claims"} <= self.header.keys():
                    # Existing providers that ignore the ordering instruction
                    # keep the ordinary complete-response path.
                    self.disabled = True
                    return False
                if raw[end] != '"':
                    raise ValueError("stream text must be a JSON string")
                claims = self.header["claims"]
                probe = "\n".join(c.get("statement", "") for c in claims if isinstance(c, dict)) if isinstance(claims, list) else ""
                header_text = probe if self.header["action"] in ("text", "voice_only") else ""
                self.draft_header, _ = decode_text_response(encode({**self.header, "text": header_text}), self.wire)
                if self.header["action"] != "text" or self.header.get("images"):
                    self.disabled = True
                    return False
                self.text_start = end
                self.position = end + 1
                return True
            try:
                _, value_end = json.JSONDecoder().raw_decode(raw, end)
            except json.JSONDecodeError:
                return False
            boundary = value_end
            while boundary < len(raw) and raw[boundary].isspace():
                boundary += 1
            if boundary == len(raw):
                return False
            if raw[boundary] != ",":
                raise ValueError("stream reply header must precede text")
            self.header[key] = strict_json(raw[end:value_end])
            self.position = boundary + 1

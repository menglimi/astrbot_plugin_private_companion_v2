"""Optional reaction intent authored alongside the native text reply."""

import html
import json
import re

from companion_v2.conversation.text_processing import strip_internal_expression_protocol


_LT = r"(?:<|&lt;|&#0*60;|&#x0*3c;)"
_GT = r"(?:>|&gt;|&#0*62;|&#x0*3e;)"
_BLOCK = re.compile(
    rf"(?is){_LT}\s*pc_reaction_expression\b[^>]*?{_GT}(.*?)"
    rf"{_LT}\s*/\s*pc_reaction_expression\s*{_GT}"
)
INSTRUCTION = (
    "图库表情是角色的实际表达能力。轻松接话、问候、亲昵、庆祝或安慰时，"
    "优先考虑用一张贴合的表情补充态度；严肃、敏感、冲突或没有贴合表达时用文字即可。"
    "自动附图不需要额外调用工具。本轮完成正文后判断是否适合附图，并在末尾输出判定：适合时使用内部格式 "
    '<pc_reaction_expression>{"intent":"你想表达的交流用途、态度和当前语境"}</pc_reaction_expression>。'
    '不适合时使用 <pc_reaction_expression>{"intent":""}</pc_reaction_expression>，空意图表示不用表情。'
    "程序会检索角色图库并发送可用原图，标签不会显示给用户；这属于内部呈现格式，与不向用户输出内部 JSON 的规则兼容。"
    "人格中仅用文字等旧呈现规则不关闭本轮已启用的图库表达。意图描述整段回复的意思，"
    "不要只抄用户原话里的名词，也不要编造图片地址或声称已经发送。"
    "已经通过表情检索和发送工具发图时，无需再追加自动附图意图。"
    '格式示例：辛苦啦，早点休息呀。<pc_reaction_expression>{"intent":"温柔关心对方，轻轻道晚安"}</pc_reaction_expression>。'
    "示例只说明格式，意图按实际回复生成。"
)


def extract_reply_intent(text):
    """Keep the prose even if an optional internal block is malformed."""
    if not isinstance(text, str):
        return text, ""
    intent = ""
    for match in _BLOCK.finditer(text):
        try:
            value = json.loads(html.unescape(match.group(1)).strip())
        except (ValueError, RecursionError):
            continue
        if not isinstance(value, dict):
            continue
        # V1's purpose/query format remains readable in older native histories.
        parts = [value.get(key, "") for key in ("intent", "purpose", "emotion", "query", "context")]
        candidate = "；".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
        if candidate:
            intent = candidate[:1500]
            break
    return strip_internal_expression_protocol(text), intent


def authored_reply_decision(text):
    """Distinguish a deliberate no-image decision from a missing protocol."""
    if not isinstance(text, str):
        return False
    for match in _BLOCK.finditer(text):
        try:
            value = json.loads(html.unescape(match.group(1)).strip())
        except (ValueError, RecursionError):
            continue
        if isinstance(value, dict) and any(isinstance(value.get(key), str)
                for key in ("intent", "purpose", "emotion", "query", "context")):
            return True
    return False


def reply_context_intent(input_text, reply_text):
    """Use the actual role reply as semantic material when no intent was authored."""
    if not isinstance(reply_text, str) or not reply_text.strip():
        return ""
    reply = reply_text.strip()[:1000]
    original = input_text.strip()[:400] if isinstance(input_text, str) else ""
    return ("角色本轮实际回应：" + reply + ("\n用户原话：" + original if original else "")
            + "\n表情用于补充角色回应的态度，不机械复刻用户情绪。")

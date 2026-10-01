"""Capture private memory replies before JSON decoding or host text repair."""

import json

from companion_v2.model_gateway.models import CapturedModelOutput


def explicit_refusal(completion):
    choices = getattr(completion, "choices", ())
    if not isinstance(choices, (list, tuple)) or len(choices) != 1:
        return False
    choice = choices[0]
    message = getattr(choice, "message", None)
    if message is None or getattr(message, "tool_calls", None) or getattr(message, "function_call", None):
        return False
    return bool(getattr(message, "refusal", None)) or getattr(choice, "finish_reason", None) == "content_filter"


def response_format(request):
    if request.response_format == "text":
        return None
    if request.response_format == "json_object":
        return {"type": "json_object"}
    return {"type": "json_schema", "json_schema": {
        "name": "content_authoring" if request.output_format == "content_authoring" else "memory_reflection", "strict": True,
        "schema": json.loads(request.response_schema_json),
    }}


def capture(completion):
    choices = getattr(completion, "choices", ())
    if not isinstance(choices, (list, tuple)) or len(choices) != 1:
        return CapturedModelOutput("", "invalid")
    choice = choices[0]
    message = getattr(choice, "message", None)
    body = getattr(message, "content", None)
    reason = getattr(choice, "finish_reason", None)
    if not isinstance(body, str):
        body = ""
    if len(body) > 65536:
        return CapturedModelOutput(body[:65536], "oversized")
    if explicit_refusal(completion):
        return CapturedModelOutput(body, "refusal")
    if getattr(message, "tool_calls", None) or getattr(message, "function_call", None):
        return CapturedModelOutput(body, "invalid")
    if reason not in ("stop", "length"):
        reason = "invalid"
    return CapturedModelOutput(body, reason)

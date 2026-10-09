"""Snapshot raw completion metadata before the native parser can modify it."""

from companion_v2.model_gateway.response_diagnostics import (
    FINISH_REASONS, ResponseDiagnostics, ResponseTextSummary,
)


def observe_completion(completion):
    raw_completion = getattr(completion, "raw_completion", None)
    choices = getattr(completion, "choices", ()) or getattr(raw_completion, "choices", ())
    choice = choices[0] if isinstance(choices, (list, tuple)) and choices else None
    reason = getattr(choice, "finish_reason", None)
    reason = "missing" if reason is None else reason if type(reason) is str and reason in FINISH_REASONS else "unknown"
    message = getattr(choice, "message", None)
    text = getattr(completion, "completion_text", None)
    if text is None:
        text = getattr(message, "content", None)
    return ResponseDiagnostics(completion_present=completion is not None,
        finish_reason=reason, parse_state="raw_observed" if completion is not None else "not_received",
        raw=ResponseTextSummary.from_text(text))

"""One text and speech plan shared by generation and offline previews."""

from dataclasses import dataclass

from .foreground import ClaimKind
from .voice_reply import separate_spoken, speech_candidates, speech_decisions


def observed_statements(draft):
    return tuple(claim.statement for claim in draft.claims if claim.kind is ClaimKind.OBSERVED)


@dataclass(frozen=True)
class PreparedReply:
    visible: str
    source_parts: tuple[str, ...]
    parts: tuple[str, ...]
    spans: tuple
    kept_indices: tuple[int, ...]

    def speech(self, policy):
        candidates = None
        if policy.generation_mode == "model_tag" or policy.trigger_mode == "adaptive":
            originals = speech_candidates(self.visible, self.source_parts, self.spans, policy)
            candidates = tuple(originals[index] for index in self.kept_indices)
        return speech_decisions(self.visible, self.parts, self.spans, policy, candidates=candidates)


def prepare_reply(text, segmentation, presentation, voice=None, *, statements=(), split=None):
    text, leaked = presentation.framework_guard(text)
    if leaked:
        return PreparedReply(text, (text,), (text,), (), (0,))
    replaced = presentation.replace_text(text, statements=statements)
    visible, spans = separate_spoken(replaced, voice) if voice else (replaced, ())
    parts = segmentation.parts(visible)
    if split is not None and not segmentation.enabled:
        original = "".join(parts)
        parts = split(original)
        if (type(parts) is not tuple or not 1 <= len(parts) <= 64
                or any(type(part) is not str or not part.strip() for part in parts)
                or "".join(parts) != original):
            raise ValueError("custom segmentation must preserve the complete reply")
    # Authored speech stays literal after its wrapper is removed for display.
    cleaned = presentation.clean_parts(parts, statements=(*statements, *(speech for _, speech in spans)))
    indices = tuple(index for index, part in enumerate(cleaned) if part.strip())
    if not indices:
        raise ValueError("presentation removed all visible reply text")
    return PreparedReply(visible, parts, tuple(cleaned[index] for index in indices), spans, indices)

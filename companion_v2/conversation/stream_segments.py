"""Append-only text boundaries for native group streams, without host imports."""

from dataclasses import replace
import json

from .segment_control import LLM_SEGMENT_MARKER, controlled_parts


class TextSegmentStream:
    def __init__(self, policy):
        self.policy, self.source, self.consumed, self.published = policy, "", 0, 0

    def feed(self, text):
        self.source += text
        ready = []
        while (end := self._boundary(self.source[self.consumed:])) is not None:
            body = self.source[self.consumed:self.consumed + end]
            parts, _ = controlled_parts(body)
            body = "".join(parts)
            self.consumed += end
            if body.strip():
                ready.append(body)
                self.published += 1
        return tuple(ready)

    def finish(self):
        body = self.source[self.consumed:]
        if not body.strip():
            return ()
        parts, _ = controlled_parts(body)
        if not parts:
            return ()
        # Long replies retain all text even beyond the policy's bounded rule
        # input. Already published stream parts can never be retracted.
        if len(body) > 65536:
            return ("".join(parts),)
        policy = replace(self.policy, max_segments=max(1, self.policy.max_segments - self.published))
        if len(self.source) > policy.threshold:
            policy = replace(policy, threshold=1)
        return policy.parts(body)

    def _boundary(self, text):
        policy = self.policy
        if (not policy.enabled or policy.streaming_mode != "incremental"
                or self.published >= policy.max_segments - 1):
            return None
        candidates = []
        if policy.llm_controlled:
            parts, explicit = controlled_parts(text)
            if explicit and len(parts) > 1:
                marker = text.find(LLM_SEGMENT_MARKER, len(parts[0].rstrip()))
                if marker >= 0:
                    candidates.append((marker + len(LLM_SEGMENT_MARKER), True))
        if len(self.source) <= policy.threshold:
            candidates.extend((end, False) for end in policy.rule_boundaries(text)
                              if sum(not char.isspace() for char in text[:end]) >= policy.min_segment_chars)
        for end, explicit in sorted(set(candidates)):
            if end >= len(text) or not text[end:].strip():
                continue
            if not explicit and sum(not char.isspace() for char in text[end:]) < policy.min_segment_chars:
                continue
            if policy.rule_mode == "words":
                words = json.loads(policy.split_words)
                if any(text[start:] and len(text[start:]) < len(word) and word.startswith(text[start:])
                       for word in words for start in range(max(0, end - len(word)), end)):
                    continue
                if text[end - 1] in ".…~～" and text[end] == text[end - 1]:
                    continue
            return end
        return None

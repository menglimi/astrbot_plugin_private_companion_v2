"""Small deterministic policy for native poke notifications."""

from dataclasses import dataclass
from math import isfinite

from companion_v2.execution.models import digest


DEFAULT_REPLIES = ("在呢，怎么啦？", "收到你的戳戳啦。", "我在这里。")


@dataclass(frozen=True)
class PokePolicy:
    enabled: bool = False
    trigger_probability: float = 1.0
    replies: tuple[str, ...] = DEFAULT_REPLIES
    back_probability: float = 0.0

    @classmethod
    def parse(cls, value):
        if value is None:
            value = {}
        if type(value) is not dict or set(value) - {"enabled", "trigger_probability", "replies", "back_probability"}:
            raise ValueError("poke settings contain unknown fields")
        enabled = value.get("enabled", False)
        replies = value.get("replies", list(DEFAULT_REPLIES))
        if type(enabled) is not bool or type(replies) is not list or not 1 <= len(replies) <= 20:
            raise ValueError("poke switch or replies are invalid")
        if any(type(item) is not str or not item.strip() or len(item) > 120 for item in replies):
            raise ValueError("poke replies must be short nonempty strings")

        def probability(name, default):
            number = value.get(name, default)
            if type(number) not in (int, float) or not isfinite(number) or not 0 <= number <= 1:
                raise ValueError("poke probability must be between zero and one")
            return float(number)

        return cls(enabled, probability("trigger_probability", 1.0), tuple(item.strip() for item in replies),
                   probability("back_probability", 0.0))

    @staticmethod
    def _fraction(event_key, purpose):
        return int(digest([event_key, purpose])[:13], 16) / 0x10000000000000

    def reply_for(self, event_key):
        if not self.enabled or self._fraction(event_key, "trigger") >= self.trigger_probability:
            return None
        index = int(digest([event_key, "reply"])[:13], 16) % len(self.replies)
        return self.replies[index]

    def poke_back(self, event_key):
        return self._fraction(event_key, "back") < self.back_probability

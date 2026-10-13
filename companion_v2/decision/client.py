"""Decision-model port and errors; transport belongs to the host adapter."""

from typing import Protocol

from .contract import LayaDecision


class LayaClientError(RuntimeError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


class LayaDecisionClient(Protocol):
    async def decide(self, facts: dict, *, enabled_fields=None) -> LayaDecision: ...

    async def probe(self, *, enabled_fields=None) -> LayaDecision: ...

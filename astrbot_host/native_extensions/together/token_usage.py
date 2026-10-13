"""Compatibility import for Together's service-owned token ledger."""

from ..usage import TokenUsageTracker as NativeTokenUsageTracker


class TokenUsageTracker(NativeTokenUsageTracker):
    def __init__(self, path):
        super().__init__(path, source="together", display_name="一起房间",
            note="展示实时通话、画面理解和观影整理的模型消耗，不计入 V2 角色预算。")

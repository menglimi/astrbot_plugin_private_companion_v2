"""High-level Laya configuration and decision operations."""

from __future__ import annotations

from .client import LayaClientError, LayaDecisionClient
from .store import LayaSettingsStore


class LayaDecisionService:
    def __init__(self, store: LayaSettingsStore):
        self.store = store

    def status(self) -> dict:
        return self.store.read()

    def save(self, revision, changes) -> dict:
        return self.store.update(revision, changes)

    def _client(self, values: dict) -> LayaDecisionClient:
        if values["mode"] == "remote" and not values["endpoint"].strip():
            raise LayaClientError("laya_endpoint_missing", "远程模式需要填写 Laya SystemOne 服务地址")
        return LayaDecisionClient(mode=values["mode"], endpoint=values["endpoint"],
                                  api_key=values["api_key"],
                                  timeout_seconds=values["timeout_seconds"])

    async def test(self) -> dict:
        values = self.store.raw()
        client = self._client(values)
        result = await client.probe()
        return {"status": "ok", "mode": values["mode"], "default_model": "multilingual",
                "decision": result.document()}

    async def decide(self, facts: dict) -> dict:
        values = self.store.raw()
        if not values["enabled"]:
            return {"status": "skipped", "reason": "laya_disabled"}
        client = self._client(values)
        try:
            result = await client.decide(facts)
        except LayaClientError as error:
            if error.code == "laya_rule_skip":
                return {"status": "skipped", "reason": error.reason}
            raise
        return {"status": "ok", "decision": result.document()}

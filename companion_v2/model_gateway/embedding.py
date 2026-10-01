"""Typed, bounded embedding and rerank calls, shared by semantic consumers."""

import asyncio
from collections import OrderedDict
import math

from companion_v2.execution.models import TaskError, digest


def unit(payload):
    if isinstance(payload, dict):
        payload = payload.get("embedding", payload.get("vector", payload.get("data")))
    if not isinstance(payload, (list, tuple)) or not 1 <= len(payload) <= 4096:
        raise ValueError("invalid embedding dimensions")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in payload):
        raise ValueError("embedding must contain finite numbers")
    norm = math.hypot(*payload)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("embedding has no finite direction")
    return tuple(x / norm for x in payload)


class EmbeddingGateway:
    def __init__(self, port, *, timeout=8, concurrency=2):
        self.port, self.timeout = port, timeout
        self.slots = asyncio.Semaphore(concurrency)
        self.cache = OrderedDict()
        self.metrics = {"calls": 0, "texts": 0, "cache_hits": 0, "failures": 0, "last_error": None}

    async def embed(self, owner, texts, provider_id=""):
        if not texts or len(texts) > 64 or any(type(t) is not str or not t.strip() or len(t) > 8000 for t in texts):
            raise ValueError("bounded nonempty embedding text required")
        binding = self.port.binding(provider_id, "embedding")
        keys = [(owner, binding, digest(t)) for t in texts]
        missing = list(dict.fromkeys(k for k in keys if k not in self.cache))
        self.metrics["cache_hits"] += len(keys) - len(missing)
        if missing:
            documents = [texts[keys.index(k)] for k in missing]
            try:
                async with self.slots:
                    self.metrics["calls"] += 1
                    self.metrics["texts"] += len(documents)
                    values = await asyncio.wait_for(self.port.embed(provider_id, documents), self.timeout)
                if self.port.binding(provider_id, "embedding") != binding:
                    raise TaskError("embedding_provider_changed", "embedding model changed during the request")
                if len(values) != len(documents):
                    raise ValueError("embedding batch length mismatch")
                vectors = [unit(v) for v in values]
                if len({len(v) for v in vectors}) != 1:
                    raise ValueError("inconsistent embedding dimensions")
                for key, vector in zip(missing, vectors):
                    self.cache[key] = vector
                self.metrics["last_error"] = None
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.metrics["failures"] += 1
                self.metrics["last_error"] = getattr(error, "code", type(error).__name__)
                raise
        result = tuple(self.cache[k] for k in keys)
        while len(self.cache) > 1024:
            self.cache.popitem(last=False)
        return binding, result

    async def rerank(self, provider_id, query, documents):
        if not provider_id or len(documents) < 2:
            return None
        async with self.slots:
            scores = await asyncio.wait_for(self.port.rerank(provider_id, query, documents), self.timeout)
        if len(scores) != len(documents) or any(type(s) not in (int, float) or not math.isfinite(s) for s in scores):
            raise ValueError("invalid rerank scores")
        return scores

    def clear(self):
        self.cache.clear()

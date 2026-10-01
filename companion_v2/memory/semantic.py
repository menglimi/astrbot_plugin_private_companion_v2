"""Generate real query vectors and incrementally fill authorized memory documents."""

from contextlib import closing
import json

from companion_v2.execution.models import TaskError
from .models import owner_key


class MemorySemanticRecall:
    def __init__(self, memory, gateway, settings):
        self.memory, self.gateway, self.settings = memory, gateway, settings
        self.continuations = {}

    async def prepare(self, context, arguments):
        cfg = self.settings()
        if not cfg["enabled"] or not cfg["memory_enabled"]:
            return {}
        query = self.memory.query
        query.access.check(context)
        owner = owner_key(context)
        text = arguments.get("query_intent", "")
        if not isinstance(text, str) or not text.strip():
            return {}
        cursor = arguments.get("cursor")
        if cursor:
            return self.continuations.get((context.key, cursor), {})
        namespace, kind = arguments.get("namespace", "personal"), arguments.get("kind", "facts")
        try:
            model, vectors = await self.gateway.embed(owner, [text], cfg["embedding_provider"])
            query.access.check(context)
            snapshot = query.recall_index.advance(context, namespace, kind)
            with closing(query.index._open()) as db:
                rows = db.execute("""SELECT d.* FROM recall_documents d LEFT JOIN recall_vectors v
                    ON v.owner=d.owner AND v.id=d.id AND v.model=? AND v.hash=d.hash
                    WHERE d.owner=? AND v.id IS NULL ORDER BY d.id LIMIT ?""",
                    (model, snapshot["partition"], cfg["batch_size"])).fetchall()
            eligible = []
            for row in rows:
                try:
                    query.objects.read(context, row)
                    eligible.append(row)
                except TaskError:
                    continue
            if eligible:
                binding, embedded = await self.gateway.embed(owner,
                    [json.loads(r["document_json"])["text"][:8000] for r in eligible], cfg["embedding_provider"])
                query.access.check(context)
                if binding == model:
                    for row, vector in zip(eligible, embedded):
                        try:
                            query.objects.read(context, row)
                            query.index.put_vector(row["owner"], row["id"], model=model, values=vector, expected_hash=row["hash"])
                        except (TaskError, ValueError):
                            continue
            return {"vector": vectors[0], "model": model}
        except Exception:
            query.access.check(context)
            return {}

    async def backfill(self, context, kind, namespace="personal"):
        cfg, query = self.settings(), self.memory.query
        if not cfg["enabled"] or not cfg["memory_enabled"]:
            return
        model = self.gateway.port.binding(cfg["embedding_provider"], "embedding")
        after = ""
        while True:
            query.access.check(context)
            snapshot = query.recall_index.advance(context, namespace, kind)
            with closing(query.index._open()) as db:
                rows = db.execute("""SELECT d.* FROM recall_documents d LEFT JOIN recall_vectors v
                    ON v.owner=d.owner AND v.id=d.id AND v.model=? AND v.hash=d.hash
                    WHERE d.owner=? AND d.id>? AND v.id IS NULL ORDER BY d.id LIMIT ?""",
                    (model, snapshot["partition"], after, cfg["batch_size"])).fetchall()
            eligible = []
            for row in rows:
                try:
                    query.objects.read(context, row)
                    eligible.append(row)
                except TaskError:
                    continue
            if eligible:
                binding, vectors = await self.gateway.embed(owner_key(context),
                    [json.loads(r["document_json"])["text"][:8000] for r in eligible], cfg["embedding_provider"])
                query.access.check(context)
                if binding != model:
                    raise TaskError("embedding_provider_changed", "memory model changed while indexing")
                for row, vector in zip(eligible, vectors):
                    try:
                        query.objects.read(context, row)
                        query.index.put_vector(row["owner"], row["id"], model=model, values=vector, expected_hash=row["hash"])
                    except (TaskError, ValueError):
                        continue
            if rows:
                after = rows[-1]["id"]
            elif snapshot["ready"]:
                break
            else:
                after = ""
            import asyncio
            await asyncio.sleep(0)

    def remember_cursor(self, context, result, prepared):
        cursor = result.get("next_cursor")
        if cursor:
            self.continuations[(context.key, cursor)] = prepared
            if len(self.continuations) > 512:
                self.continuations.pop(next(iter(self.continuations)))

    async def rerank(self, context, intent, payload):
        """Reorder only this authorized page; pagination and evidence stay intact."""
        items = payload.get("items", [])
        cfg = self.settings()
        if not cfg["enabled"] or not cfg["memory_enabled"] or not cfg["rerank_provider"] or len(items) < 2:
            return payload
        self.memory.query.access.check(context)
        try:
            texts = [json.dumps(item, ensure_ascii=False)[:8000] for item in items]
            scores = await self.gateway.rerank(cfg["rerank_provider"], intent, texts)
            self.memory.query.access.check(context)
            return {**payload, "items": [item for _, item in sorted(zip(scores, items), key=lambda v: v[0], reverse=True)],
                    "rerank_state": "ranked_current_page"}
        except Exception:
            self.memory.query.access.check(context)
            return {**payload, "rerank_state": "unavailable_kept_retrieval_order"}

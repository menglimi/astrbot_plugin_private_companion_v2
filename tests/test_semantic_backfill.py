import asyncio
import json
import threading
import unittest
from types import SimpleNamespace

from companion_v2.execution.models import TaskError
from companion_v2.memory.semantic import MemorySemanticRecall
from companion_v2.memory.sent_sources import ConfirmedReplySources, OWNER


class FakeAccess:
    def __init__(self):
        self.revoked = False

    def check(self, context):
        if self.revoked:
            raise TaskError("memory_access_revoked", "memory access was revoked")


class FakeDatabase:
    def __init__(self, rows, indexed):
        self.rows, self.indexed = rows, indexed

    def execute(self, statement, parameters):
        after, limit = parameters[-2:]
        rows = [row for row in self.rows if row["id"] > after and row["id"] not in self.indexed]
        return SimpleNamespace(fetchall=lambda: rows[:limit])

    def close(self):
        pass


class FakeIndex:
    def __init__(self, rows):
        self.rows = rows
        self.vectors = {}

    def _open(self):
        return FakeDatabase(self.rows, self.vectors)

    def put_vector(self, owner, identifier, *, model, values, expected_hash):
        self.vectors[identifier] = (owner, model, values, expected_hash)


class FakeObjects:
    def __init__(self, access):
        self.access = access
        self.started = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.read_threads = []

    def read(self, context, row):
        self.read_threads.append(threading.get_ident())
        self.started.set()
        if self.block:
            self.release.wait(2)
        self.access.check(context)


class FakeGateway:
    def __init__(self, access):
        self.access = access
        self.port = self
        self.result_binding = "embedding-model-1"
        self.fail = False

    def binding(self, provider, kind):
        return "embedding-model-1"

    async def embed(self, owner, texts, provider):
        if self.fail:
            raise RuntimeError("embedding failed")
        return self.result_binding, [[1.0, 0.0] for _ in texts]


class SemanticBackfillTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = SimpleNamespace(
            scope=SimpleNamespace(installation_id="install", bot_id="bot"),
            role_binding=SimpleNamespace(role=SimpleNamespace(subject_id="role")),
            actor=SimpleNamespace(subject=SimpleNamespace(subject_id="person")),
        )
        self.access = FakeAccess()
        self.rows = [{"id": "doc-1", "owner": "partition", "hash": "hash-1",
                      "document_json": json.dumps({"text": "original message"})}]
        self.index = FakeIndex(self.rows)
        self.objects = FakeObjects(self.access)
        self.query = SimpleNamespace(
            access=self.access,
            index=self.index,
            objects=self.objects,
            recall_index=SimpleNamespace(advance=lambda *args: {"partition": "partition", "ready": True}),
        )
        self.memory = SimpleNamespace(query=self.query)
        self.gateway = FakeGateway(self.access)
        self.recall = MemorySemanticRecall(self.memory, self.gateway, lambda: {
            "enabled": True, "memory_enabled": True, "embedding_provider": "provider",
            "batch_size": 8,
        })

    async def test_blocked_source_read_does_not_block_event_loop_and_backfill_completes(self):
        self.objects.block = True
        release_timer = threading.Timer(0.15, self.objects.release.set)
        release_timer.start()
        beats = 0

        async def heartbeat():
            nonlocal beats
            while not self.objects.release.is_set():
                beats += 1
                await asyncio.sleep(0.005)

        beat_task = asyncio.create_task(heartbeat())
        try:
            await asyncio.wait_for(self.recall.backfill(self.context, "sources"), timeout=2)
        finally:
            self.objects.release.set()
            release_timer.cancel()
            beat_task.cancel()
            await asyncio.gather(beat_task, return_exceptions=True)
        self.assertGreater(beats, 5)
        self.assertEqual(set(self.index.vectors), {"doc-1"})
        self.assertTrue(all(thread_id != threading.get_ident() for thread_id in self.objects.read_threads))

    async def test_embedding_failure_does_not_write_vectors(self):
        self.gateway.fail = True
        with self.assertRaisesRegex(RuntimeError, "embedding failed"):
            await self.recall.backfill(self.context, "sources")
        self.assertEqual(self.index.vectors, {})

    async def test_revocation_after_embedding_prevents_vector_write(self):
        async def revoke_during_embed(owner, texts, provider):
            self.access.revoked = True
            return "embedding-model-1", [[1.0, 0.0] for _ in texts]

        self.gateway.embed = revoke_during_embed
        with self.assertRaises(TaskError) as error:
            await self.recall.backfill(self.context, "sources")
        self.assertEqual(error.exception.code, "memory_access_revoked")
        self.assertEqual(self.index.vectors, {})

    async def test_provider_binding_change_prevents_vector_write(self):
        self.gateway.result_binding = "embedding-model-2"
        with self.assertRaises(TaskError) as error:
            await self.recall.backfill(self.context, "sources")
        self.assertEqual(error.exception.code, "embedding_provider_changed")
        self.assertEqual(self.index.vectors, {})


class ConfirmedReplyReadConcurrencyTests(unittest.TestCase):
    def test_parallel_reads_of_the_same_reply_keep_separate_cycle_stacks(self):
        sources = object.__new__(ConfirmedReplySources)
        sources._reading = threading.local()
        barrier = threading.Barrier(2)
        sources._read = lambda *args, **kwargs: (barrier.wait(timeout=2), "read")[1]
        context = object()
        reference = SimpleNamespace(owner=OWNER, version=SimpleNamespace(revision=1), source_id="sent:same")
        results, errors = [], []

        def read():
            try:
                results.append(sources._resolve(context, reference, publish=False))
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=read) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(results, ["read", "read"])


if __name__ == "__main__":
    unittest.main()

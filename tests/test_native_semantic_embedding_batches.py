"""Provider batch limits must not leave the real reaction index empty."""

from types import SimpleNamespace as NS
import unittest

from astrbot_host.semantic_models import NativeSemanticModels


class BatchError(Exception):
    def __init__(self, status, message):
        self.status_code = status
        self.body = {"message": message}


class BatchProvider:
    def __init__(self, *, limit=10, failing=None):
        self.provider_config = {"id": "embedding-provider", "model": "model-a"}
        self.limit, self.failing, self.calls = limit, failing, []

    async def get_embeddings(self, texts):
        self.calls.append(list(texts))
        if self.failing:
            raise self.failing
        if len(texts) > self.limit:
            raise BatchError(400, f"batch size is invalid, it should not be larger than {self.limit}: input.contents")
        return {"data": [{"index": index, "embedding": [float(text), 1.0]}
                         for index, text in reversed(list(enumerate(texts)))]}


class NativeEmbeddingBatchTests(unittest.IsolatedAsyncioTestCase):
    def port(self, provider):
        return NativeSemanticModels(NS(get_provider_by_id=lambda _: provider))

    async def test_explicit_provider_limit_splits_and_retains_original_text_order(self):
        provider = BatchProvider()
        port = self.port(provider)
        result = await port.embed("embedding-provider", [str(index) for index in range(24)])
        self.assertEqual([len(call) for call in provider.calls], [24, 10, 10, 4])
        self.assertEqual([value["index"] for value in result], list(range(24)))
        self.assertEqual([value["embedding"][0] for value in result], [float(index) for index in range(24)])
        provider.calls.clear()
        await port.embed("embedding-provider", [str(index) for index in range(24)])
        self.assertEqual([len(call) for call in provider.calls], [10, 10, 4])
        provider.provider_config["model"] = "model-b"
        provider.calls.clear()
        await port.embed("embedding-provider", [str(index) for index in range(12)])
        self.assertEqual([len(call) for call in provider.calls], [12, 10, 2])

    async def test_authentication_quota_and_unrelated_parameter_errors_are_not_retried(self):
        for error in (BatchError(401, "invalid key"), BatchError(429, "rate limit exceeded"),
                      BatchError(400, "invalid input text"), BatchError(400, "batch limit is 10 but the input encoding is invalid")):
            provider = BatchProvider(failing=error)
            with self.assertRaises(BatchError):
                await self.port(provider).embed("embedding-provider", ["1", "2"])
            self.assertEqual(len(provider.calls), 1)

    async def test_single_item_errors_and_incomplete_results_do_not_return_partial_vectors(self):
        provider = BatchProvider(failing=BatchError(400, "batch size too large"))
        with self.assertRaises(BatchError):
            await self.port(provider).embed("embedding-provider", ["1"])
        class Incomplete(BatchProvider):
            async def get_embeddings(self, texts):
                return [[1.0, 0.0]]
        with self.assertRaises(ValueError):
            await self.port(Incomplete()).embed("embedding-provider", ["1", "2"])

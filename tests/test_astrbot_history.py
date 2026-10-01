"""History transport rejection must precede media preparation and extra reads."""

from functools import partial
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from companion_v2.adapters.astrbot.forwards import NativeForwardLocator, read_private_forwards
from companion_v2.adapters.astrbot.quotes import NativeQuoteLocator, read_private_quote
from companion_v2.execution.models import TaskError
from tests.forward_support import outer_raw
from tests.native_adapter_support import FakeReverseApi
from tests.test_conversation_quotes import quote_raw


class HistoryResponseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clients = {"100": object(), "101": object()}
        self.api = FakeReverseApi(clients)
        client = NS(_api=NS(_wsr_api=self.api), _wsr_api_clients=clients)
        self.images = AsyncMock(side_effect=AssertionError("invalid history may not fetch images"))
        options = dict(client=client, scope=NS(account_id="100", native_scope_id="200"),
                       reverse_api_type=FakeReverseApi, image_loader=self.images)
        self.readers = (
            ("quote", quote_raw(), partial(read_private_quote, NativeQuoteLocator(0, "345"), **options)),
            ("forward", outer_raw(), partial(read_private_forwards, (NativeForwardLocator(0, "forward-resource"),),
                                            message_id="678", **options)),
        )

    async def rejected(self, reader, response, code):
        self.api.result = response
        self.api.calls.clear()
        with self.assertRaises(TaskError) as failure:
            await reader()
        self.assertEqual(failure.exception.code, code)
        self.images.assert_not_awaited()
        self.assertEqual(len(self.api.calls), 1)
        action, params = self.api.calls[0]
        self.assertEqual(action, "get_friend_msg_history")
        self.assertEqual((params["self_id"], params["user_id"], params["count"]), ("100", "200", 1))

    async def test_failed_pending_and_malformed_status_never_return_successful_looking_data(self):
        for kind, raw, reader in self.readers:
            for flags in ({"status": "failed"}, {"status": "async"}, {"status": None},
                          {"retcode": 1}, {"retcode": "1"}, {"retcode": False},
                          {"retcode": 0.0}, {"retcode": None}):
                with self.subTest(kind=kind, flags=flags):
                    await self.rejected(reader, {"data": {"messages": [raw]}, **flags}, f"host_{kind}_unavailable")
        for kind, raw, reader in self.readers:
            await self.rejected(reader, {"status": "ok", "data": {"status": "failed", "messages": [raw]}},
                                f"host_{kind}_unavailable")

    async def test_ambiguous_and_recursive_wrappers_do_not_choose_a_payload(self):
        for kind, raw, reader in self.readers:
            responses = (
                {"messages": [raw], "data": {"messages": [raw]}},
                {"messages": [raw], "data": None},
                {"data": {"messages": [raw], "data": [raw]}},
                {"data": {"data": {"messages": [raw]}}},
                {"messages": None, "data": [raw]},
            )
            for index, response in enumerate(responses):
                with self.subTest(kind=kind, shape=index):
                    await self.rejected(reader, response, f"host_{kind}_unavailable")

    async def test_wrappers_preserve_single_message_requirement(self):
        for kind, raw, reader in self.readers:
            for messages in ([], [None], [raw, raw], {"0": raw}):
                await self.rejected(reader, {"data": {"messages": messages}}, f"host_{kind}_unavailable")

    async def test_wrapped_history_cannot_change_the_pinned_account(self):
        for kind, raw, reader in self.readers:
            changed = {**raw, "self_id": 101}
            for response in ([changed], {"data": [changed]}, {"data": {"messages": [changed]}}):
                await self.rejected(reader, response, f"host_{kind}_scope_mismatch")

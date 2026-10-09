"""Use the SDK's actual query object, including duplicate parameter handling."""

from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests import test_astrbot_staging_host as sdk_environment
from astrbot.api.web import PluginMultiDict
from astrbot_host.acquaintance_api import AcquaintanceWebAPI
from astrbot_host.multi_api import MultiHostWebAPI
from companion_v2.foundation.outcome import Outcome
from companion_v2.execution.models import TaskError


class MultiQueryTests(unittest.IsolatedAsyncioTestCase):
    def test_acquaintance_route_query_reads_plugin_multidict_without_integer_iteration(self):
        route = PluginMultiDict([("platform", "qq"), ("bot_id", "bot-a"),
                                 ("account_id", "100"), ("role_id", "role-a")])
        self.assertEqual(AcquaintanceWebAPI._route_query(route), {
            "platform": "qq", "bot_id": "bot-a", "account_id": "100", "role_id": "role-a",
        })
        self.assertIsNone(AcquaintanceWebAPI._route_query(PluginMultiDict([])))
        with self.assertRaises(TaskError) as error:
            AcquaintanceWebAPI._route_query(PluginMultiDict([("platform", "qq")]))
        self.assertEqual(error.exception.code, "acquaintance_route_required")

    async def test_control_accepts_sdk_keys_and_rejects_ambiguous_parameters(self):
        controller = NS(probe=AsyncMock(return_value=Outcome.success({})),
                        authorize_delivery=AsyncMock(return_value=Outcome.success({})))
        api = MultiHostWebAPI(controller)
        request = NS(username="demo-admin", query=PluginMultiDict([]))
        with patch("astrbot_host.multi_api.request", request):
            self.assertEqual((await api.control("probe")())["status"], "ok")
            controller.probe.assert_awaited_once_with()
            request.query = PluginMultiDict([("target_id", "first")])
            self.assertEqual((await api.control("authorize_delivery", target=True)())["status"], "ok")
            controller.authorize_delivery.assert_awaited_once_with(target_id="first")
            controller.authorize_delivery.reset_mock()
            controller.probe.reset_mock()
            for pairs in ([], [("target_id", "first"), ("target_id", "second")],
                          [("target_id", "first"), ("unexpected", "value")]):
                request.query = PluginMultiDict(pairs)
                result = await api.control("authorize_delivery", target=True)()
                self.assertEqual(result["data"]["code"], "host_request_invalid")
            request.query = PluginMultiDict([("target_id", "first")])
            self.assertEqual((await api.control("probe")())["data"]["code"], "host_request_invalid")
            controller.authorize_delivery.assert_not_awaited()
            controller.probe.assert_not_awaited()

    async def test_preview_and_batches_accept_sdk_queries_without_integer_indexing(self):
        controller = NS(preview=Mock(return_value=Outcome.success({})), batches=Mock(return_value=Outcome.success({})))
        api = MultiHostWebAPI(controller)
        request = NS(username="demo-admin", query=None)
        with patch("astrbot_host.multi_api.request", request):
            for handler, method, pairs, arguments in (
                (api.api_preview, controller.preview, [("target_id", "first"), ("batch_id", "original")], ("first", "original")),
                (api.api_batches, controller.batches, [("target_id", "first")], ("first",)),
            ):
                request.query = PluginMultiDict(pairs)
                self.assertEqual((await handler())["status"], "ok")
                method.assert_called_once_with(*arguments)
                method.reset_mock()
                for invalid in ([], pairs + [("unexpected", "value")], *(pairs + [pair] for pair in pairs)):
                    request.query = PluginMultiDict(invalid)
                    self.assertEqual((await handler())["data"]["code"], "host_request_invalid")
                method.assert_not_called()

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from astrbot_host.relay_tools import RelayToolPort
from companion_v2.conversation.external_tools import ExternalToolInvocation
from companion_v2.execution.models import TaskError, encode
from companion_v2.foundation.refs import AudienceRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, ResolvedIdentity, RoleBinding
from companion_v2.storage.repositories import OperationRepository
from companion_v2.storage.runtime import StorageRuntime
from companion_v2.conversation.relay_tools import SEND_ACTION, tool_descriptors


NOW = datetime(2026, 10, 19, 4, 0, tzinfo=timezone.utc)
SETTINGS = {"enabled": True, "require_confirm": True, "max_text_chars": 500,
            "core_target_id": "1001", "allowed_targets": ["2002"]}


class FakeReverseApi:
    def __init__(self, response=None):
        self.response = response if response is not None else {"message_id": 789}
        self.calls = []

    async def call_action(self, action, **kwargs):
        self.calls.append((action, kwargs))
        return self.response


class RelayToolPortTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = TemporaryDirectory(prefix="companion-v2-relay-")
        self.addCleanup(self.temporary.cleanup)
        self.runtime = StorageRuntime.open(data_root=Path(self.temporary.name) / "v2-data",
                                           installation_id="installation-a")
        self.addCleanup(self.runtime.close)
        scope = ScopeRef("installation-a", "onebot", ScopeKind.PRIVATE, "1001",
                         "bot-a", "account-a", "conversation-1001", "session-1001")
        subject = SubjectRef("installation-a", SubjectKind.HUMAN, "owner")
        role = SubjectRef("installation-a", SubjectKind.BOT, "companion")
        principal = AuthenticatedHostPrincipal("installation-a", "astrbot", "onebot", "1001",
                                               "bot-a", "account-a")
        actor = ResolvedIdentity(principal, subject, "binding-a", 1, 1)
        self.context = SimpleNamespace(
            scope=scope,
            actor=actor,
            role_binding=RoleBinding(scope, role, 1),
            audience=AudienceRef(scope, (subject,)),
            key="relay-test-context",
        )
        self.api = FakeReverseApi()
        client = SimpleNamespace(_api=SimpleNamespace(_wsr_api=self.api),
                                 _wsr_api_clients={"account-a": self.api})
        bridge = SimpleNamespace(target_for_scope=lambda _scope: None,
                                 client=lambda _scope: client)
        self.port = RelayToolPort(bridge, native_types=SimpleNamespace(reverse_api=FakeReverseApi))
        self.port.attach(SimpleNamespace(
            state="running", runtime=self.runtime,
            relay_settings=SimpleNamespace(read=lambda _context, _at: dict(SETTINGS)),
            now=lambda: NOW,
        ))
        self.current_input = {"event_id": "proposal-event", "observed_at": NOW.isoformat()}
        self.current_text = "帮我转告：今晚不去了"
        self.port._input = lambda _invocation: (self.current_input, self.current_text)
        self.text = "今晚不去了"
        self.operation_id = None

    def invocation(self, action, arguments, identifier):
        descriptor = next(item for item in tool_descriptors() if item.tool.action == action)
        return ExternalToolInvocation(identifier, "core-reply:relay-test", "call-" + identifier,
                                      self.context, descriptor, encode(arguments), NOW + timedelta(minutes=2))

    def propose(self):
        invocation = self.invocation("relay_message", {"destination_id": "2002", "text": self.text}, "proposal-1")
        result = self.port._propose(invocation, json.loads(invocation.arguments_json))
        self.operation_id = json.loads(result.source.payload)["operation_id"]
        self.assertEqual(json.loads(result.source.payload)["state"], "awaiting_confirmation")
        self.assertEqual(self.api.calls, [])

    async def send(self):
        arguments = {"operation_id": self.operation_id, "destination_id": "2002",
                     "text": self.text, "confirmed": True}
        invocation = self.invocation(SEND_ACTION, arguments, "send-1")
        return await self.port._send(invocation, arguments)

    async def test_confirmation_must_be_a_later_message_and_delivery_receipt_is_audited(self):
        self.propose()
        same_turn = await self.send()
        self.assertEqual(same_turn.error_code, "relay_confirmation_required")
        self.assertEqual(self.api.calls, [])

        self.current_input = {"event_id": "confirmation-event",
                              "observed_at": (NOW + timedelta(seconds=1)).isoformat()}
        self.current_text = "确认发送"
        sent = await self.send()
        self.assertEqual(sent.state, "succeeded")
        self.assertEqual(self.api.calls[0][1]["user_id"], 2002)
        self.assertEqual(self.api.calls[0][1]["self_id"], "account-a")
        outbox = OperationRepository(self.runtime).outbox(
            self.operation_id, "private:2002").unwrap()
        self.assertEqual((outbox.state, outbox.receipt_ref),
                         ("accepted", "onebot-message:789"))

        replay = await self.send()
        self.assertEqual(replay.receipt_ref, "onebot-message:789")
        self.assertEqual(len(self.api.calls), 1)

    async def test_missing_platform_receipt_stays_unknown_and_is_never_replayed(self):
        self.propose()
        self.current_input = {"event_id": "confirmation-event",
                              "observed_at": (NOW + timedelta(seconds=1)).isoformat()}
        self.current_text = "确认发送"
        self.api.response = {"status": "ok"}

        result = await self.send()
        self.assertEqual(result.state, "unknown")
        outbox = OperationRepository(self.runtime).outbox(
            self.operation_id, "private:2002").unwrap()
        self.assertEqual((outbox.state, outbox.receipt_ref), ("unknown", None))

        with self.assertRaises(TaskError) as raised:
            await self.send()
        self.assertEqual(raised.exception.code, "relay_result_unknown")
        self.assertEqual(len(self.api.calls), 1)


if __name__ == "__main__":
    unittest.main()

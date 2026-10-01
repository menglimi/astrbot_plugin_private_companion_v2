from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace
import unittest

from astrbot_host.mobile_together import MobileTogetherBridge
from companion_v2.execution.models import TaskError
from companion_v2.sources.models import GovernanceState


class MobileTogetherBridgeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.allowed = {"together.room.create", "together.room.invite", "together.room.join"}
        self.context = SimpleNamespace(
            scope=SimpleNamespace(kind=SimpleNamespace(value="private"), native_scope_id="12345"),
            actor=SimpleNamespace(principal=SimpleNamespace(native_account_id="12345")),
            role_binding=SimpleNamespace(role=SimpleNamespace(subject_id="role-a")),
            key="context-a",
        )

        class Admission:
            def admit(inner, descriptor, context, at):
                if descriptor.tool.action not in self.allowed:
                    raise TaskError("capability_denied", "denied")

        self.application = SimpleNamespace(state="running", external=Admission())
        self.declarations = []
        for action in ("together.room.create", "together.room.invite", "together.room.join"):
            properties = {"mode": {"type": "string", "enum": ["call", "watch"]}} if action.endswith("create") else {}
            descriptor = SimpleNamespace(tool=SimpleNamespace(
                action=action,
                parameters_json=json.dumps({"type": "object", "properties": properties}),
            ), timeout_seconds=5)
            self.declarations.append(SimpleNamespace(host_tool_id="native:" + action, descriptor=descriptor))

        class Registry:
            application = self.application

            def declarations(inner):
                return tuple(self.declarations)

            def current_declaration(inner, host_tool_id):
                return next((item for item in self.declarations if item.host_tool_id == host_tool_id), None)

            async def invoke(inner, host_tool_id, invocation):
                self.invocations.append(invocation)
                if (getattr(inner, "reject_argument_conflict", False)
                        and len(self.invocations) > 1
                        and self.invocations[0].arguments_hash != invocation.arguments_hash):
                    error = RuntimeError("native_original_invocation_mismatch")
                    error.code = "native_original_invocation_mismatch"
                    raise error
                payload = json.dumps({"native": {"result": {"room": {
                    "url": "https://room.example/join/ticket", "mode": "call",
                    "expires_at": 123, "ticket_token": "must-not-leak",
                }}}})
                source = SimpleNamespace(state=GovernanceState.ACTIVE, payload=payload)
                return SimpleNamespace(state="succeeded", effect="committed", operation_id="op-1",
                    receipt_ref="receipt-1", source=source)

        self.invocations = []
        self.registry = Registry()
        self.session = SimpleNamespace(profile=SimpleNamespace(target=self.context), application=self.application)
        self.apis = {
            "astrbot_plugin_reality_companion": SimpleNamespace(
                companion_v2_mobile_session_user=lambda token: {
                    "schema": "companion.mobile-session.v1",
                    "user_id": ({"valid-session-token-123456": "12345",
                                 "other-session-token-123456": "99999"}.get(token, "")),
                }),
            "astrbot_plugin_together_companion": SimpleNamespace(companion_v2_status=lambda: {
                "schema": "companion.provider-status.v1",
                "plugin_id": "astrbot_plugin_together_companion",
                "enabled": True,
                "runtime_ready": False,
            }),
        }
        host_context = SimpleNamespace(get_registered_star=lambda plugin_id:
            SimpleNamespace(star_cls=SimpleNamespace(extension_api=self.apis[plugin_id]))
            if plugin_id in self.apis else None)
        self.controller = SimpleNamespace(
            context=host_context,
            session=self.session,
            native_extensions=self.registry,
            _multi_host=False,
            _terminated=False,
            now=lambda: datetime.now(timezone.utc),
        )
        self.bridge = MobileTogetherBridge(self.controller)

    def test_status_uses_per_action_v2_authorization_and_room_modes(self):
        self.allowed.remove("together.room.invite")
        result = self.bridge.status("valid-session-token-123456")
        self.assertTrue(result["matched"])
        self.assertTrue(result["ready"])
        self.assertFalse(result["capabilities"]["invite"])
        self.assertEqual(result["modes"], ["call", "watch"])

    async def test_mobile_invocation_is_stable_for_retries_and_projects_ticket_secret(self):
        first = await self.bridge.invoke("valid-session-token-123456", request_id="request-1",
                                         operation="create", arguments={"mode": "call"})
        second = await self.bridge.invoke("valid-session-token-123456", request_id="request-1",
                                          operation="create", arguments={"mode": "call"})
        self.assertEqual(self.invocations[0].invocation_id, self.invocations[1].invocation_id)
        projected = self.bridge.mobile_result("create", first)
        self.assertEqual(projected["result"]["room"]["url"], "https://room.example/join/ticket")
        self.assertNotIn("ticket_token", json.dumps(projected))
        self.assertEqual(second["state"], "succeeded")

    async def test_operation_requires_stable_request_id_and_current_consent(self):
        with self.assertRaisesRegex(TaskError, "stable request_id"):
            await self.bridge.invoke("valid-session-token-123456", request_id="", operation="create",
                                     arguments={"mode": "call"})
        self.allowed.remove("together.room.create")
        with self.assertRaisesRegex(TaskError, "not authorized"):
            await self.bridge.invoke("valid-session-token-123456", request_id="request-2", operation="create",
                                     arguments={"mode": "call"})

    async def test_reusing_request_id_with_different_arguments_is_a_known_conflict(self):
        self.registry.reject_argument_conflict = True
        await self.bridge.invoke("valid-session-token-123456", request_id="request-conflict",
                                 operation="create", arguments={"mode": "call"})
        with self.assertRaisesRegex(TaskError, "different room arguments") as raised:
            await self.bridge.invoke("valid-session-token-123456", request_id="request-conflict",
                                     operation="create", arguments={"mode": "watch"})
        self.assertEqual(raised.exception.code, "mobile_together_request_conflict")
        self.assertEqual(len(self.invocations), 2)

    def test_unmatched_user_is_not_retargeted_to_the_active_v2_profile(self):
        result = self.bridge.status("other-session-token-123456")
        self.assertFalse(result["matched"])

    def test_duplicate_multi_targets_are_refused(self):
        self.controller._multi_host = True
        self.controller.settings = SimpleNamespace(targets=(
            SimpleNamespace(participant_id="12345"), SimpleNamespace(participant_id="12345")))
        self.controller.authority = object()
        with self.assertRaisesRegex(TaskError, "more than one"):
            self.bridge._target_context("12345")


if __name__ == "__main__":
    unittest.main()

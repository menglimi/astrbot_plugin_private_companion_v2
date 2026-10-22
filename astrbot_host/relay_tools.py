"""Supervised first-party tool port for audited cross-window private relaying."""

from __future__ import annotations

from datetime import datetime
import json
import re
from types import SimpleNamespace

from companion_v2.adapters.astrbot.tools import AstrBotToolDeclaration
from companion_v2.conversation.native_tool_sources import input_row
from companion_v2.conversation.relay import plan_relay
from companion_v2.conversation.relay_policy import RelayRequest
from companion_v2.conversation.relay_tools import (DATASET_OWNER, PROPOSE_ACTION, SEND_ACTION,
                                                   tool_descriptors)
from companion_v2.conversation.external_tools import ExternalToolInvocation, ExternalToolResponse
from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.refs import OperationRef, SourceRef, VersionRef
from companion_v2.sources.models import SourceRecord
from companion_v2.storage.models import OperationState
from companion_v2.storage.repositories import OperationRepository

from .private_notice import prepare_private_notice_transport
from .relay_dispatch import relay_private


OWNER = "conversation.relay"
_DESTINATION = re.compile(r"[0-9]{1,20}\Z")
_CONFIRMATIONS = frozenset(("确认", "确认发送", "确认递话", "发吧", "就按这段发"))


class RelayToolPort:
    """Keep configuration policy, operation audit and the authenticated OneBot route together."""

    def __init__(self, bridge, *, native_types, enabled=True):
        if bridge is None or not callable(getattr(bridge, "client", None)):
            raise ValueError("relay tools need the original authenticated account bridge")
        if native_types is None or not isinstance(getattr(native_types, "reverse_api", None), type):
            raise ValueError("relay tools need the installed reverse-WebSocket API type")
        self.bridge, self.native_types = bridge, native_types
        self.application = None
        self._declarations = (tuple(AstrBotToolDeclaration("relay:" + item.tool.action, item)
                                    for item in tool_descriptors()) if enabled else ())

    def declarations(self):
        return self._declarations

    def current_declaration(self, host_tool_id):
        if self.application is None:
            return None
        return next((item for item in self._declarations if item.host_tool_id == host_tool_id), None)

    def provider_admission(self, host_tool_id):
        declaration = next((item for item in self._declarations if item.host_tool_id == host_tool_id), None)
        if declaration is None:
            return None

        def admit(context, at):
            application = self.application
            if application is None or application.state != "running":
                raise TaskError("relay_host_unavailable", "跨窗口递话当前不可用")
            return application.tasks.authorize_context(context, action="conversation.reply", observed_at=at)

        return admit

    def attach(self, application):
        if self.application is not None and self.application is not application:
            raise ValueError("relay tool port can attach only once")
        if getattr(application, "relay_settings", None) is None:
            raise ValueError("relay settings must be assembled before the relay tool port")
        self.application = application
        return self

    async def invoke(self, host_tool_id, invocation: ExternalToolInvocation) -> ExternalToolResponse:
        declaration = next((item for item in self._declarations if item.host_tool_id == host_tool_id), None)
        if declaration is None or declaration.descriptor != invocation.descriptor:
            raise TaskError("relay_provider_changed", "递话工具声明已变化")
        arguments = json.loads(invocation.arguments_json)
        action = declaration.descriptor.tool.action
        if action == PROPOSE_ACTION:
            return self._propose(invocation, arguments)
        if action == SEND_ACTION:
            return await self._send(invocation, arguments)
        raise TaskError("relay_action_unknown", "未知递话动作")

    def _app(self):
        if self.application is None or self.application.state != "running":
            raise TaskError("relay_host_unavailable", "跨窗口递话当前不可用")
        return self.application

    def _source(self, invocation, result):
        application = self._app()
        at = application.now()
        payload = encode(result)
        reference = SourceRef("relay:" + invocation.invocation_id, DATASET_OWNER, invocation.context.scope,
            VersionRef(invocation.invocation_id, 1), at,
        )
        return SourceRecord(reference, invocation.context.audience, digest(payload), payload)

    def _response(self, invocation, result, *, state="succeeded", effect="none", operation_id=None,
                  receipt_ref=None, error_code=None):
        return ExternalToolResponse(invocation.invocation_id, invocation.context.key,
            invocation.arguments_hash, invocation.descriptor.binding, state, effect=effect,
            source=self._source(invocation, result) if state == "succeeded" else None,
            operation_id=operation_id, receipt_ref=receipt_ref, error_code=error_code)

    def _input(self, invocation):
        application = self._app()
        row = input_row(application.messages, invocation.context, invocation.parent_task_id)
        from companion_v2.conversation.messages import source_from_document
        reference = source_from_document(json.loads(row["source_json"]))
        record = application.messages._read_source(reference, invocation.context, "text", application.now())
        return row, record.payload

    def _settings(self, invocation):
        application = self._app()
        return application.relay_settings.read(invocation.context, application.now())

    def _plan(self, invocation, destination_id, text):
        if type(destination_id) is not str or _DESTINATION.fullmatch(destination_id) is None:
            raise TaskError("relay_target_invalid", "私聊目标必须是有效的数字账号 ID")
        settings = self._settings(invocation)
        actor_id = invocation.context.actor.principal.native_account_id
        actor_is_core = actor_id == settings.get("core_target_id", "")
        request = RelayRequest("private", destination_id, text, actor_id)
        plan = plan_relay(request, settings, actor_is_core=actor_is_core,
                          actor_id=invocation.context.actor.subject.subject_id,
                          source_label=invocation.context.scope.native_scope_id)
        return settings, request, plan

    @staticmethod
    def _operation_id(invocation, event_id, destination_id, text):
        token = digest(["conversation.relay.v1", invocation.context.key, event_id,
                        invocation.context.actor.subject, destination_id, digest(text)])
        return "relay-" + token

    @staticmethod
    def _parameter_hash(invocation, plan):
        context = invocation.context
        actor = context.actor
        return digest({
            "source_context": context.key,
            "source_scope": context.scope,
            "actor": [actor.principal, actor.subject, actor.binding_id, actor.binding_revision],
            "role": context.role_binding,
            "audience": plan.decision.audience,
            "needs_confirm": plan.needs_confirm,
            "destination": plan.destination_id,
            "text_hash": digest(plan.text),
        })

    @staticmethod
    def _part_id(destination_id):
        return "private:" + destination_id

    def _reserve(self, invocation, plan, operation_id):
        application = self._app()
        at = application.now()
        operation = OperationRef(operation_id, OWNER, invocation.context.scope,
                                 VersionRef(operation_id, 1), operation_id)
        outbox_hash = digest({"destination": plan.destination_id, "text": plan.text,
                              "scope": invocation.context.scope, "audience": plan.decision.audience})
        receipt = require(OperationRepository(application.runtime).reserve(
            operation,
            parameter_hash=self._parameter_hash(invocation, plan),
            observed_at=at,
            outbox_part_id=self._part_id(plan.destination_id),
            outbox_payload_hash=outbox_hash,
        ))
        return receipt, operation, outbox_hash

    def _propose(self, invocation, arguments):
        destination_id, text = arguments.get("destination_id"), arguments.get("text")
        if type(text) is not str:
            raise TaskError("relay_text_invalid", "递话正文必须是文本")
        settings, request, plan = self._plan(invocation, destination_id, text)
        if not plan.allowed:
            return self._response(invocation, {"state": "denied", "code": plan.decision.code,
                                               "reason": plan.decision.reason, "audit": plan.audit})
        row, _ = self._input(invocation)
        operation_id = self._operation_id(invocation, row["event_id"], plan.destination_id, plan.text)
        receipt, operation, _ = self._reserve(invocation, plan, operation_id)
        if receipt.state is OperationState.UNKNOWN:
            return self._response(invocation, {"state": "unknown", "operation_id": operation_id,
                                               "instruction": "结果未知，禁止自动重发"})
        if receipt.state is OperationState.COMPLETED:
            outbox = require(OperationRepository(self.application.runtime).outbox(
                operation_id, self._part_id(plan.destination_id)))
            state = ("already_sent" if outbox.state == "accepted" and outbox.receipt_ref
                     else "expired" if outbox.state == "cancelled" else "unresolved")
            return self._response(invocation, {"state": state, "operation_id": operation_id,
                                               "receipt_ref": outbox.receipt_ref if state == "already_sent" else None})
        if receipt.state is not OperationState.ACCEPTED:
            raise TaskError("relay_operation_unresolved", "递话操作状态无法确认")
        outbox = require(OperationRepository(self.application.runtime).outbox(
            operation_id, self._part_id(plan.destination_id)))
        if outbox.state != "pending":
            if outbox.state == "unknown":
                return self._response(invocation, {"state": "unknown", "operation_id": operation_id,
                                                   "instruction": "结果未知，禁止自动重发"})
            raise TaskError("relay_operation_unresolved", "递话 outbox 状态与操作不一致")
        awaiting = plan.needs_confirm
        return self._response(invocation, {
            "state": "awaiting_confirmation" if awaiting else "ready",
            "operation_id": operation_id,
            "destination_id": plan.destination_id,
            "text": plan.text,
            "requires_confirmation": awaiting,
            "confirmation_phrase": "确认发送" if awaiting else "",
            "audit": plan.audit,
        })

    @staticmethod
    def _confirmation_matches(text):
        normalized = text.strip().rstrip("。！？!?；;").strip()
        return normalized in _CONFIRMATIONS

    def _load_pending(self, invocation, operation_id, plan):
        application = self._app()
        if type(operation_id) is not str or not operation_id.startswith("relay-"):
            raise TaskError("relay_confirmation_invalid", "确认编号无效")
        operations = OperationRepository(application.runtime)
        receipt = require(operations.get(operation_id))
        operation = receipt.operation
        if (operation.owner != OWNER or operation.scope != invocation.context.scope
                or operation.idempotency_key != operation_id):
            raise TaskError("relay_confirmation_scope", "确认编号不属于当前窗口")
        verified, _, _ = self._reserve(invocation, plan, operation_id)
        return operations, verified

    def _route(self, context):
        bridge = self.bridge
        if callable(getattr(bridge, "target_for_scope", None)):
            bridge.target_for_scope(context.scope)
        elif callable(getattr(bridge, "account", None)):
            bridge.account(context.scope)
        else:
            raise TaskError("relay_account_unavailable", "当前窗口没有可验证的 OneBot 账号")
        client = bridge.client(context.scope)
        route = SimpleNamespace(
            platform_id=context.scope.platform,
            bot_id=context.scope.bot_id,
            login=context.scope.account_id,
            sender=context.actor.principal.native_account_id,
            peer=context.scope.native_scope_id,
            session_id=context.scope.native_scope_id,
            client=client,
        )
        controller = SimpleNamespace(native_types=self.native_types)
        transport = prepare_private_notice_transport(controller, route)
        return controller, route, transport

    async def _send(self, invocation, arguments):
        operation_id = arguments.get("operation_id")
        destination_id, text = arguments.get("destination_id"), arguments.get("text")
        confirmed = arguments.get("confirmed") is True
        if type(text) is not str:
            raise TaskError("relay_text_invalid", "递话正文必须是文本")
        settings, request, plan = self._plan(invocation, destination_id, text)
        if not plan.allowed:
            return self._response(invocation, {"state": "denied", "code": plan.decision.code,
                                               "reason": plan.decision.reason, "audit": plan.audit},
                                  state="failed", effect="not_committed",
                                  receipt_ref="relay-denied:" + digest([operation_id, plan.decision.code]),
                                  error_code=plan.decision.code)
        if plan.needs_confirm:
            row, input_text = self._input(invocation)
            if not confirmed or not self._confirmation_matches(input_text):
                return self._response(invocation, {"state": "awaiting_confirmation",
                    "operation_id": operation_id, "confirmation_phrase": "确认发送"},
                    state="failed", effect="not_committed",
                    receipt_ref="relay-confirmation-required:" + digest(operation_id or ""),
                    error_code="relay_confirmation_required")
        else:
            row = None
        operations, receipt = self._load_pending(invocation, operation_id, plan)
        if plan.needs_confirm and row is not None and (
                datetime.fromisoformat(row["observed_at"]) <= receipt.created_at):
            return self._confirmation_refused(invocation, operation_id)
        if receipt.state is OperationState.COMPLETED:
            outbox = require(operations.outbox(operation_id, self._part_id(plan.destination_id)))
            if outbox.state == "accepted" and outbox.receipt_ref:
                return self._response(invocation, {"state": "already_sent", "operation_id": operation_id,
                                                   "receipt_ref": outbox.receipt_ref, "audit": plan.audit}, state="succeeded",
                                      effect="committed", operation_id=operation_id,
                                      receipt_ref=outbox.receipt_ref)
            raise TaskError("relay_operation_unresolved", "递话操作已结束但没有成功发送回执")
        if receipt.state is not OperationState.ACCEPTED:
            raise TaskError("relay_result_unknown", "上次发送结果未知；不会再次发送")
        outbox = require(operations.outbox(operation_id, self._part_id(plan.destination_id)))
        if outbox.state != "pending":
            raise TaskError("relay_result_unknown", "递话 outbox 已不在待发送状态；不会再次发送")
        controller, route, transport = self._route(invocation.context)
        if invocation.before_dispatch is not None:
            invocation.before_dispatch()
        at = self._app().now()
        require(operations.transition_outbox(operation_id, self._part_id(plan.destination_id),
            expected_operation_state=OperationState.ACCEPTED, next_operation_state=OperationState.UNKNOWN,
            expected_outbox_state="pending", next_outbox_state="unknown", observed_at=at))
        try:
            result = await relay_private(controller, None, request=request, settings=settings,
                actor_is_core=invocation.context.actor.principal.native_account_id == settings.get("core_target_id", ""),
                actor_id=invocation.context.actor.subject.subject_id,
                confirmed=confirmed or not plan.needs_confirm, base_route=route, transport=transport)
        except Exception:
            return self._response(invocation, {"state": "unknown", "operation_id": operation_id,
                                               "instruction": "结果未知，禁止自动重发"},
                                  state="unknown", effect="unknown", operation_id=operation_id,
                                  error_code="relay_delivery_unknown")
        message_id = result.get("receipt", {}).get("message_id") if isinstance(result, dict) else None
        receipt_ref = _onebot_receipt_ref(message_id)
        if not isinstance(result, dict) or result.get("state") != "sent" or receipt_ref is None:
            return self._response(invocation, {"state": "unknown", "operation_id": operation_id,
                                               "instruction": "没有获得 OneBot 成功回执，禁止自动重发"},
                                  state="unknown", effect="unknown", operation_id=operation_id,
                                  error_code="relay_delivery_unknown")
        require(operations.transition_outbox(operation_id, self._part_id(plan.destination_id),
            expected_operation_state=OperationState.UNKNOWN, next_operation_state=OperationState.COMPLETED,
            expected_outbox_state="unknown", next_outbox_state="accepted", observed_at=self._app().now(),
            receipt_ref=receipt_ref))
        return self._response(invocation, {"state": "sent", "operation_id": operation_id,
            "destination_id": plan.destination_id, "receipt_ref": receipt_ref, "audit": plan.audit},
            state="succeeded", effect="committed", operation_id=operation_id, receipt_ref=receipt_ref)

    def _confirmation_refused(self, invocation, operation_id):
        return self._response(invocation, {"state": "awaiting_confirmation",
            "operation_id": operation_id, "confirmation_phrase": "确认发送"},
            state="failed", effect="not_committed",
            receipt_ref="relay-confirmation-required:" + digest(operation_id or ""),
            error_code="relay_confirmation_required")


def _onebot_receipt_ref(message_id):
    if isinstance(message_id, bool) or type(message_id) not in (str, int):
        return None
    identifier = str(message_id).strip()
    if not identifier or len(identifier) > 496:
        return None
    return "onebot-message:" + identifier


__all__ = ["OWNER", "RelayToolPort"]

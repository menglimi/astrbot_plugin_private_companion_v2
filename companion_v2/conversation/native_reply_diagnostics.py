"""Window-scoped reply diagnostics from observed AstrBot requests and sends."""

import json

from companion_v2.execution.models import digest
from companion_v2.model_gateway.core_observations import available


def recent(runtime, scope, role, *, limit):
    if not available(runtime):
        return []
    rows = runtime.read_all("""SELECT record_json FROM astrbot_core_reply_observations
        WHERE role_key = ? AND scope_kind = ?
        AND json_extract(context_json, '$.role_binding.scope.native_scope_id') = ?
        AND json_extract(context_json, '$.role_binding.scope.session_id') = ?
        AND json_extract(context_json, '$.role_binding.scope.conversation_id') = ?
        ORDER BY received_at DESC, turn_id DESC LIMIT ?""",
        (digest([scope.installation_id, scope.platform, scope.bot_id, scope.account_id, role]),
         scope.kind.value, scope.native_scope_id, scope.session_id, scope.conversation_id, limit))
    result = []
    for row in rows:
        record = json.loads(row["record_json"])
        delivery = record.get("delivery", {})
        returned = delivery.get("returned", 0)
        state = record.get("generation_state", "awaiting_request")
        requests = record.get("requests", [])
        result.append({"batch_id": record["turn_id"], "created_at": record["received_at"],
            "execution_path": "astrbot_core", "state": "complete" if state == "completed" and returned else
                "closed" if state == "suppressed" else "generating" if state == "running" else state,
            "reason": state, "turn_type": "astrbot.core.reply", "current_inputs": 1, "parts": [],
            "calls": [{"position": item["position"], "state": item["state"],
                "actual_tokens": (item.get("usage") or {}).get("tokens"), "latency_ms": item.get("latency_ms"),
                "failure_code": item.get("failure_code"), "response_diagnostics": None} for item in requests],
            "response_type": "native_reply" if returned else "no_reply",
            "injected_materials": record.get("materials", []), "group_history_items": None,
            "offered_tools": record.get("offered_tools", []), "filtered_tools": [],
            "rounds": [{"round_no": index, "state": item["state"], "tool_actions": []}
                       for index, item in enumerate(requests)],
            "tool_calls": record.get("tools", []), "send_returns": returned,
            "delivery_state": delivery.get("state", "not_started"), "platform_confirmed": False})
    return result

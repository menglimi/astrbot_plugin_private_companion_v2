"""Read a source actually offered by the current AstrBot input observation."""

from companion_v2.conversation.native_tool_sources import native_offers
from companion_v2.execution.models import TaskError, digest

from .core_reply_tool_execution import executor_for


async def execute_core_source_read(session, call_id, arguments):
    if type(arguments.get("handle")) is not str:
        raise TaskError("invalid_tool_arguments", "source read requires one original handle")
    await session.wait_source()
    app, context = session.application, session.context

    def read():
        offered = native_offers(app.messages, context, session.turn_id)
        original = offered.get(arguments["handle"])
        if original is None:
            raise TaskError("tool_source_unavailable", "no original source was offered for this native turn")
        reference, capability, _ = original
        return app.messages._read_source(reference, context, capability, app.tasks.now())

    record = read()
    result = executor_for(app).local(session, call_id, "source.read", arguments, lambda _: {
        "state": "succeeded", "effect": "none", "payload": record.payload,
        "content_hash": record.content_hash, "payload_hash": digest(record.payload),
    })
    current = read()
    if result.get("state") == "succeeded" and (
            result["content_hash"] != current.content_hash or result["payload_hash"] != digest(current.payload)):
        raise TaskError("tool_result_changed", "the original offered source changed")
    return result

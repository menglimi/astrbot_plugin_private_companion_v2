"""Keep existing local diagnostics available through the native tool runner."""

from companion_v2.diagnostics.models import DiagnosticContext, DiagnosticQuery
from companion_v2.diagnostics.service import report_document
from companion_v2.execution.models import TaskError, require

from .core_reply_tool_execution import executor_for


async def execute_core_diagnostic(session, call_id, action, arguments):
    if action == "diagnostics.inspect":
        document = arguments.get("query")
        if type(document) is not dict:
            raise TaskError("invalid_tool_arguments", "inspection requires a diagnostic query")
        try:
            query = DiagnosticQuery.restore({"mode": "self_check", "target": None,
                "operation_scope": None, "window": None, **document})
        except (KeyError, TypeError, ValueError) as error:
            raise TaskError("invalid_tool_arguments", "the diagnostic query is invalid") from error
    elif action == "diagnostics.explain" and type(arguments.get("topic")) is str:
        query = None
    else:
        raise TaskError("invalid_tool_arguments", "the diagnostic action requires its declared arguments")
    await session.wait_source()
    app, context = session.application, session.context
    diagnostics = app.tools.diagnostics
    original = DiagnosticContext(context.actor, context.role_binding, context.audience)
    topic = arguments.get("topic")

    def command(_):
        if action == "diagnostics.inspect":
            report = require(diagnostics.inspect(original, query))
        elif action == "diagnostics.explain":
            report = require(diagnostics.explain(original, topic))
        else:
            raise TaskError("core_tool_unavailable", "the diagnostic action is unavailable")
        return {"state": "succeeded", "effect": "none", "report": report_document(report)}

    result = executor_for(app).local(session, call_id, action, arguments, command)
    if result.get("state") == "succeeded":
        require(diagnostics.validate_snapshot(original, result["report"], query=query, topic=topic))
    return result

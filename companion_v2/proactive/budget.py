"""Window-local rolling contact allowances, separate from actual model usage."""

from datetime import timedelta

from companion_v2.execution.models import TaskError, stamp


DIAGNOSTIC_TASK_PREFIX = "contact-diagnostic-task-"
_COUNTED_TASK_STATES = "'created', 'admitted', 'running', 'retry_scheduled', 'cancelling', 'succeeded', 'uncertain'"


class ContactBudget:
    def __init__(self, runtime):
        self.runtime = runtime

    @staticmethod
    def _relationship_predicate(alias):
        prefix = alias + ".record_json"
        return " AND ".join((
            f"json_extract({prefix}, '$.spec.context.role_binding.scope.installation_id') = ?",
            f"json_extract({prefix}, '$.spec.context.role_binding.scope.bot_id') = ?",
            f"json_extract({prefix}, '$.spec.context.role_binding.role.subject_id') = ?",
            f"json_extract({prefix}, '$.spec.context.actor.subject.installation_id') = ?",
            f"json_extract({prefix}, '$.spec.context.actor.subject.subject_id') = ?",
        ))

    @staticmethod
    def _relationship_values(context):
        return (context.scope.installation_id, context.scope.bot_id, context.role_binding.role.subject_id,
                context.actor.subject.installation_id, context.actor.subject.subject_id)

    @staticmethod
    def _attempt_count_predicate(alias):
        return f"{alias}.state IN ({_COUNTED_TASK_STATES})"

    def attempts(self, context, preferences, at, *, exclude_task_id=""):
        cutoff = stamp(at - timedelta(hours=24))
        count = self.runtime.read_one("""SELECT COUNT(*) FROM execution_tasks t
            WHERE t.origin_key = ? AND t.kind = 'proactive.compose' AND t.created_at > ? AND t.task_id != ?
            AND t.task_id NOT LIKE ? AND """ + self._attempt_count_predicate("t"),
            (context.key, cutoff, exclude_task_id, DIAGNOSTIC_TASK_PREFIX + "%"))[0]
        if count >= preferences.values["max_attempts_24h"]:
            raise TaskError("contact_attempt_budget", "contact decision allowance is exhausted")
        relation_count = self.runtime.read_one("""SELECT COUNT(*) FROM execution_tasks t
            WHERE t.kind = 'proactive.compose' AND t.created_at > ? AND t.task_id != ?
            AND t.task_id NOT LIKE ? AND """ + self._attempt_count_predicate("t") + " AND "
            + self._relationship_predicate("t"),
            (cutoff, exclude_task_id, DIAGNOSTIC_TASK_PREFIX + "%", *self._relationship_values(context)))[0]
        if relation_count >= preferences.values["max_relationship_attempts_24h"]:
            raise TaskError("contact_relationship_attempt_budget", "relationship contact decision allowance is exhausted")

    def attempt_usage(self, context, preferences, at):
        """Return the same rolling-window counts used by admission checks."""
        cutoff = stamp(at - timedelta(hours=24))
        session_count = self.runtime.read_one("""SELECT COUNT(*) FROM execution_tasks t
            WHERE t.origin_key = ? AND t.kind = 'proactive.compose' AND t.created_at > ?
            AND t.task_id NOT LIKE ? AND """ + self._attempt_count_predicate("t"),
            (context.key, cutoff, DIAGNOSTIC_TASK_PREFIX + "%"))[0]
        relationship_count = self.runtime.read_one("""SELECT COUNT(*) FROM execution_tasks t
            WHERE t.kind = 'proactive.compose' AND t.created_at > ? AND t.task_id NOT LIKE ? AND """
            + self._attempt_count_predicate("t") + " AND " + self._relationship_predicate("t"),
            (cutoff, DIAGNOSTIC_TASK_PREFIX + "%", *self._relationship_values(context)))[0]
        return {
            "session": {"used": session_count, "limit": preferences.values["max_attempts_24h"], "window_hours": 24},
            "relationship": {"used": relationship_count,
                "limit": preferences.values["max_relationship_attempts_24h"], "window_hours": 24},
        }

    def contacts(self, context, preferences, at, *, exclude_contact_id=""):
        # Pending drafts reserve a place. An unresolved wire effect continues to
        # reserve it until a trusted receipt resolves what actually happened.
        count = self.runtime.read_one("""SELECT COUNT(DISTINCT c.contact_id) FROM proactive_contacts c
            JOIN background_deliveries d ON json_extract(d.request_json, '$.source_ref') = c.contact_id
            WHERE c.origin_key = ? AND d.owner = 'proactive.contact' AND c.contact_id != ?
            AND COALESCE(json_extract(c.record_json, '$.administrator_test'), 0) = 0
            AND (d.state IN ('pending', 'dispatched', 'accepted', 'unknown')
                OR (d.state = 'delivered' AND d.delivered_at > ?))""",
            (context.key, exclude_contact_id, stamp(at - timedelta(hours=24))))[0]
        if count >= preferences.values["max_contacts_24h"]:
            raise TaskError("contact_delivery_budget", "contact delivery allowance is exhausted")
        relation_count = self.runtime.read_one("""SELECT COUNT(DISTINCT c.contact_id) FROM proactive_contacts c
            JOIN background_deliveries d ON json_extract(d.request_json, '$.source_ref') = c.contact_id
            JOIN execution_tasks t ON t.task_id = c.task_id
            WHERE d.owner = 'proactive.contact' AND c.contact_id != ?
            AND COALESCE(json_extract(c.record_json, '$.administrator_test'), 0) = 0
            AND (d.state IN ('pending', 'dispatched', 'accepted', 'unknown')
                OR (d.state = 'delivered' AND d.delivered_at > ?)) AND """
            + self._relationship_predicate("t"),
            (exclude_contact_id, stamp(at - timedelta(hours=24)), *self._relationship_values(context)))[0]
        if relation_count >= preferences.values["max_relationship_contacts_24h"]:
            raise TaskError("contact_relationship_delivery_budget", "relationship contact delivery allowance is exhausted")

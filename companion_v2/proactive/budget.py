"""Window-local rolling contact allowances, separate from actual model usage."""

from datetime import timedelta

from companion_v2.execution.models import TaskError, stamp


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

    def attempts(self, context, preferences, at, *, exclude_task_id=""):
        cutoff = stamp(at - timedelta(hours=24))
        count = self.runtime.read_one("""SELECT COUNT(*) FROM execution_tasks
            WHERE origin_key = ? AND kind = 'proactive.compose' AND created_at > ? AND task_id != ?""",
            (context.key, cutoff, exclude_task_id))[0]
        if count >= preferences.values["max_attempts_24h"]:
            raise TaskError("contact_attempt_budget", "contact decision allowance is exhausted")
        relation_count = self.runtime.read_one("""SELECT COUNT(*) FROM execution_tasks t
            WHERE t.kind = 'proactive.compose' AND t.created_at > ? AND t.task_id != ? AND """
            + self._relationship_predicate("t"),
            (cutoff, exclude_task_id, *self._relationship_values(context)))[0]
        if relation_count >= preferences.values["max_relationship_attempts_24h"]:
            raise TaskError("contact_relationship_attempt_budget", "relationship contact decision allowance is exhausted")

    def contacts(self, context, preferences, at, *, exclude_contact_id=""):
        # Pending drafts reserve a place. An unresolved wire effect continues to
        # reserve it until a trusted receipt resolves what actually happened.
        count = self.runtime.read_one("""SELECT COUNT(*) FROM proactive_contacts c
            JOIN background_deliveries d ON json_extract(d.request_json, '$.source_ref') = c.contact_id
            WHERE c.origin_key = ? AND d.owner = 'proactive.contact' AND c.contact_id != ?
            AND (d.state IN ('pending', 'dispatched', 'accepted', 'unknown')
                OR (d.state = 'delivered' AND d.delivered_at > ?))""",
            (context.key, exclude_contact_id, stamp(at - timedelta(hours=24))))[0]
        if count >= preferences.values["max_contacts_24h"]:
            raise TaskError("contact_delivery_budget", "contact delivery allowance is exhausted")
        relation_count = self.runtime.read_one("""SELECT COUNT(*) FROM proactive_contacts c
            JOIN background_deliveries d ON json_extract(d.request_json, '$.source_ref') = c.contact_id
            JOIN execution_tasks t ON t.task_id = c.task_id
            WHERE d.owner = 'proactive.contact' AND c.contact_id != ?
            AND (d.state IN ('pending', 'dispatched', 'accepted', 'unknown')
                OR (d.state = 'delivered' AND d.delivered_at > ?)) AND """
            + self._relationship_predicate("t"),
            (exclude_contact_id, stamp(at - timedelta(hours=24)), *self._relationship_values(context)))[0]
        if relation_count >= preferences.values["max_relationship_contacts_24h"]:
            raise TaskError("contact_relationship_delivery_budget", "relationship contact delivery allowance is exhausted")

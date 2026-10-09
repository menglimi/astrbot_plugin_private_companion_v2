"""Core Dashboard management over explicit, source-governed growth records."""

from __future__ import annotations

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import ReferenceValidationError, RoleOwnerRef, ScopeKind, SourceRef, SubjectKind
from companion_v2.identity_policy.models import ResolvedIdentity
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.personas import PersonaDirectory
from companion_v2.sources.repositories import SourceRepository

from .models import GrowthKind, GrowthState, RoleGrowthRecord


class RoleGrowthManagement:
    """Expose only the selected role/private participant after Dashboard auth."""

    TRANSITIONS = {"pause": GrowthState.PAUSED, "complete": GrowthState.ACHIEVED,
                   "retire": GrowthState.RETIRED, "withdraw": GrowthState.RETIRED}
    ALLOWED_STATES = {
        "confirm": (GrowthState.PROPOSED,), "resume": (GrowthState.PAUSED,),
        "pause": (GrowthState.ACTIVE,), "complete": (GrowthState.ACTIVE, GrowthState.PAUSED),
        "withdraw": (GrowthState.PROPOSED,),
        "retire": (GrowthState.PROPOSED, GrowthState.ACTIVE, GrowthState.PAUSED),
        "revise": (GrowthState.PROPOSED, GrowthState.ACTIVE, GrowthState.PAUSED),
    }

    def __init__(self, ledger):
        self.ledger = ledger
        self.runtime = ledger.runtime
        self.policy = ObjectAccessPolicy(self.runtime)
        self.sources = SourceRepository(self.runtime)
        self.identities = self.policy.identity
        self.personas = PersonaDirectory(self.runtime)

    def _authorize(self, operator: ResolvedIdentity, context: TaskContext, at):
        if (context.scope.kind is not ScopeKind.PRIVATE
                or context.audience.recipients != (context.actor.subject,)
                or context.actor.subject.kind is not SubjectKind.HUMAN
                or operator.subject.kind is not SubjectKind.HUMAN):
            raise TaskError("growth_management_scope", "select one resolved private participant")
        current = require(self.identities.resolve_authenticated(context.actor.principal, observed_at=at))
        if (current.subject != context.actor.subject or current.binding_id != context.actor.binding_id
                or current.binding_revision != context.actor.binding_revision):
            raise TaskError("growth_target_changed", "the selected participant changed")
        if (current.principal.platform, current.principal.bot_id, current.principal.account_id) != (
                context.scope.platform, context.scope.bot_id, context.scope.account_id):
            raise TaskError("growth_target_changed", "the participant belongs to a different Bot account route")
        route = require(self.personas.resolve(context.scope, observed_at=at))
        if route.route.user != current.subject or route.binding != context.role_binding:
            raise TaskError("growth_target_changed", "the selected private role changed")
        access = require(self.policy.scope_access(operator, scope=context.scope,
            action="role.growth.manage", owner=current.subject, core_only=True, observed_at=at))
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id), access.policy_revision

    @staticmethod
    def _token(operator, context, identifier, revision, policy_revision):
        return digest(["role-growth-management.v1", operator.subject, operator.binding_id,
            operator.binding_revision, context.key, identifier, revision, policy_revision])

    def _record(self, identifier, owner, context):
        if (type(identifier) is not str or not identifier.strip() or identifier != identifier.strip()
                or len(identifier) > 512):
            raise TaskError("growth_management_invalid", "select an original growth record")
        try:
            record = self.ledger.record(identifier, owner=owner)
        except KeyError:
            raise TaskError("growth_record_unavailable", "growth record is unavailable in this role") from None
        if record.scope != context.scope:
            raise TaskError("growth_record_unavailable", "growth record is unavailable in this private scope")
        return record

    def _unavailable(self, record, context, at):
        for source in record.sources:
            if source.scope != context.scope:
                return "source_scope_mismatch"
            checked = self.sources.validate_reference_for_audience(
                source, recipient=context.actor.subject, observed_at=at)
            if not checked.is_success:
                return checked.failure.code
        return None

    def _project(self, record, operator, context, policy_revision, at):
        unavailable = self._unavailable(record, context, at)
        actions = []
        if record.state is GrowthState.PROPOSED:
            if unavailable is None:
                actions.extend(("confirm", "revise"))
            actions.extend(("withdraw", "retire"))
        elif record.state is GrowthState.ACTIVE:
            if unavailable is None:
                actions.extend(("revise", "pause"))
                if record.kind is GrowthKind.GOAL:
                    actions.append("complete")
            actions.append("retire")
        elif record.state is GrowthState.PAUSED:
            if unavailable is None:
                actions.extend(("resume", "revise"))
                if record.kind is GrowthKind.GOAL:
                    actions.append("complete")
            actions.append("retire")
        return {"growth_id": record.growth_id, "revision": record.revision,
            "kind": record.kind.value, "state": record.state.value,
            "title": record.title if unavailable is None else None,
            "description": record.description if unavailable is None else None,
            "progress_note": record.progress_note if unavailable is None else None,
            "source_count": len(record.sources), "unavailable_reason": unavailable,
            "proposed_by": record.proposed_by.subject_id,
            "confirmed_by": record.confirmed_by.subject_id if record.confirmed_by else None,
            "changed_by": record.changed_by.subject_id if record.changed_by else None,
            "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat(),
            "actions": actions,
            "view_token": self._token(operator, context, record.growth_id, record.revision, policy_revision)}

    @outcome
    def list(self, *, operator, context, state=None, kind=None, limit=20, after_id=None):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise TaskError("growth_query_invalid", "page size must be between 1 and 50")
        if after_id is not None and (type(after_id) is not str or not after_id.strip()
                or after_id != after_id.strip() or len(after_id) > 512):
            raise TaskError("growth_query_invalid", "use an original growth ID as the cursor")
        try:
            selected_state = GrowthState(state) if state is not None else None
            selected_kind = GrowthKind(kind) if kind is not None else None
        except (TypeError, ValueError):
            raise TaskError("growth_query_invalid", "unknown growth state or kind") from None
        at = self.ledger.now()
        with self.runtime.read_snapshot():
            owner, policy_revision = self._authorize(operator, context, at)
            records = self.ledger.for_role(owner, scope=context.scope, state=selected_state,
                kind=selected_kind, limit=limit + 1, after_id=after_id)
            page = records[:limit]
            return {"context_key": context.key, "role_id": owner.persona_id,
                "subject_id": context.actor.subject.subject_id, "operator_id": operator.subject.subject_id,
                "create_token": self._token(operator, context, "new-growth", 0, policy_revision),
                "items": [self._project(record, operator, context, policy_revision, at) for record in page],
                "next_cursor": page[-1].growth_id if len(records) > limit else None}

    @outcome
    def evidence(self, *, operator, context, growth_id):
        """Read only the current, audience-authorized source text for one record."""
        at = self.ledger.now()
        with self.runtime.read_snapshot():
            owner, _ = self._authorize(operator, context, at)
            record = self._record(growth_id, owner, context)
            unavailable = self._unavailable(record, context, at)
            if unavailable:
                raise TaskError(unavailable, "one or more original sources are no longer readable")
            resolved = require(self.identities.resolve_authenticated(
                context.actor.principal, observed_at=at))
            items = []
            for reference in record.sources:
                source = require(self.sources.read(reference, resolved=resolved,
                    capability="role.growth.read", observed_at=at, authorizer=self.identities))
                items.append({"text": source.payload[:2000], "issued_at": reference.issued_at.isoformat()})
            return {"growth_id": record.growth_id, "revision": record.revision,
                "items": items, "read_at": at.isoformat()}

    def _validate_sources(self, sources, context, at):
        if (type(sources) is not tuple or not 1 <= len(sources) <= 8
                or any(not isinstance(source, SourceRef) for source in sources)
                or len(set(sources)) != len(sources)):
            raise TaskError("growth_sources_invalid", "provide one to eight unique source references")
        for source in sources:
            if source.scope != context.scope:
                raise TaskError("source_scope_mismatch", "growth evidence must use the selected private scope")
            require(self.sources.validate_reference_for_audience(
                source, recipient=context.actor.subject, observed_at=at))

    @outcome
    def create(self, *, operator, context, operation_key, view_token, kind, title, description="",
               progress_note="", sources):
        self._validate_operation_key(operation_key)
        try:
            selected_kind = GrowthKind(kind)
        except (TypeError, ValueError):
            raise TaskError("growth_command_invalid", "choose skill or goal") from None
        for name, value, maximum in (("title", title, 512), ("description", description, 8192),
                                     ("progress_note", progress_note, 8192)):
            if type(value) is not str or len(value) > maximum or (name == "title" and not value.strip()):
                raise TaskError("growth_command_invalid", "provide bounded proposal text")
        at = self.ledger.now()
        with self.runtime.transaction():
            owner, policy_revision = self._authorize(operator, context, at)
            if view_token != self._token(operator, context, "new-growth", 0, policy_revision):
                raise TaskError("growth_view_stale", "refresh the selected role before proposing growth")
            self._validate_sources(sources, context, at)
            growth_id = "dashboard-growth-" + digest([operator.subject, context.key, operation_key])
            operation_id = "growth-create:" + digest([operator.subject, context.key, operation_key])
            replayed = self.ledger.operations.get(operation_id).is_success
            try:
                record = RoleGrowthRecord(growth_id, owner, context.scope, selected_kind, title,
                    description, progress_note, sources, at, at, proposed_by=operator.subject)
                saved = self.ledger.propose(record, operation_id=operation_id)
            except ReferenceValidationError:
                raise TaskError("growth_command_conflict", "growth proposal could not be saved") from None
            current = self._record(growth_id, owner, context)
            return {"operation_id": operation_id, "applied_revision": saved.revision, "replayed": replayed,
                "item": self._project(current, operator, context, policy_revision, at)}

    @staticmethod
    def _validate_operation_key(operation_key):
        if (type(operation_key) is not str or not 1 <= len(operation_key) <= 128
                or operation_key != operation_key.strip()):
            raise TaskError("growth_command_invalid", "an original operation key is required")

    @outcome
    def command(self, *, operator, context, growth_id, action, expected_revision,
                view_token, operation_key, title=None, description=None, progress_note=None, sources=None):
        if type(action) is not str or action not in self.ALLOWED_STATES:
            raise TaskError("growth_command_invalid", "unknown growth action")
        if type(expected_revision) is not int or expected_revision < 1:
            raise TaskError("growth_command_invalid", "the original revision is required")
        self._validate_operation_key(operation_key)
        if action == "revise":
            for name, value in (("title", title), ("description", description), ("progress_note", progress_note)):
                maximum = 512 if name == "title" else 8192
                if type(value) is not str or len(value) > maximum or (name == "title" and not value.strip()):
                    raise TaskError("growth_command_invalid", "provide bounded revised growth text")
        elif any(value is not None for value in (title, description, progress_note, sources)):
            raise TaskError("growth_command_invalid", "text and sources are accepted only for revision")
        at = self.ledger.now()
        operation_id = "growth-management:" + digest([operator.subject, context.key, operation_key])
        with self.runtime.transaction():
            owner, policy_revision = self._authorize(operator, context, at)
            token = self._token(operator, context, growth_id, expected_revision, policy_revision)
            if type(view_token) is not str or view_token != token:
                raise TaskError("growth_view_stale", "refresh the growth record before applying this change")
            self._record(growth_id, owner, context)
            try:
                original = self.ledger.revision(growth_id, expected_revision, owner=owner)
            except KeyError:
                raise TaskError("growth_revision_conflict", "the selected growth revision is unavailable") from None
            if (original.scope != context.scope or original.state not in self.ALLOWED_STATES[action]
                    or action == "complete" and original.kind is GrowthKind.SKILL):
                raise TaskError("growth_command_conflict", "this action does not apply to the selected record")
            unavailable = self._unavailable(original, context, at)
            if action not in ("retire", "withdraw") and action != "revise" and unavailable:
                raise TaskError(unavailable, "growth evidence is no longer available")
            if action == "revise":
                selected_sources = original.sources if sources is None else sources
                self._validate_sources(selected_sources, context, at)
            try:
                if action == "revise":
                    updated = self.ledger.revise(growth_id, owner=owner, scope=context.scope,
                        expected_revision=expected_revision, operation_id=operation_id, title=title,
                        description=description, progress_note=progress_note, sources=selected_sources,
                        actor=operator.subject, observed_at=at)
                elif action in ("confirm", "resume"):
                    updated = self.ledger.confirm(growth_id, owner=owner, scope=context.scope,
                        expected_revision=expected_revision, operation_id=operation_id,
                        actor=operator.subject, observed_at=at)
                else:
                    target = GrowthState.RETIRED if action in ("retire", "withdraw") else self.TRANSITIONS[action]
                    updated = self.ledger.transition(growth_id, owner=owner, scope=context.scope,
                        expected_revision=expected_revision, operation_id=operation_id, state=target,
                        actor=operator.subject, observed_at=at)
            except ReferenceValidationError:
                raise TaskError("growth_command_conflict", "the record changed or this action no longer applies") from None
            current = self._record(growth_id, owner, context)
            return {"operation_id": operation_id, "applied_revision": updated.revision,
                "item": self._project(current, operator, context, policy_revision, at)}

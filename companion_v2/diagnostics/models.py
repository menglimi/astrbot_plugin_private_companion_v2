"""Read-only diagnostic contracts. Evidence references contain no source bodies."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum

from companion_v2.configuration.models import ConfigLayer, ConfigTarget, fingerprint
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import AudienceRef, ScopeRef, SubjectKind, SubjectRef, normalize_utc
from companion_v2.identity_policy.models import ResolvedIdentity, RoleBinding, _opaque


class DiagnosticError(ValueError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code


def require(result: Outcome):
    if result.failure:
        raise DiagnosticError(result.failure.code, result.failure.reason)
    return result.unwrap()


class DiagnosticMode(str, Enum):
    EXPLAIN = "explain"
    SELF_CHECK = "self_check"
    INCIDENT = "incident"
    REPAIR_PROPOSAL = "repair_proposal"


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class DiagnosticContext:
    """Constructed by a trusted host with its original role and actual audience."""

    actor: ResolvedIdentity
    role_binding: RoleBinding
    audience: AudienceRef

    def __post_init__(self):
        if self.role_binding.scope != self.audience.scope or not self.audience.scope.is_resolved:
            raise ValueError("diagnostics requires the original complete conversation route")

    @property
    def scope(self) -> ScopeRef:
        return self.audience.scope

    @property
    def key(self) -> str:
        # Global policy revisions are checked live, never made part of caller identity.
        return fingerprint({"principal": asdict(self.actor.principal), "subject": asdict(self.actor.subject),
                            "binding": [self.actor.binding_id, self.actor.binding_revision],
                            "role": asdict(self.role_binding), "audience": asdict(self.audience)})


@dataclass(frozen=True)
class IncidentWindow:
    start: datetime
    end: datetime

    def __post_init__(self):
        for name in ("start", "end"):
            object.__setattr__(self, name, normalize_utc(getattr(self, name), field=name))
        if not timedelta(0) < self.end - self.start <= timedelta(days=1):
            raise ValueError("incident window must be positive and at most 24 hours")


def restore_target(value: dict) -> ConfigTarget:
    role = SubjectRef(value["installation_id"], SubjectKind.BOT, value["role_id"]) if value["role_id"] else None
    scope = ScopeRef.restore(value["scope"]) if value["scope"] else None
    subject = SubjectRef(value["installation_id"], SubjectKind.HUMAN, value["subject_id"]) if value.get("subject_id") else None
    return ConfigTarget(value["installation_id"], ConfigLayer(value["layer"]), role, scope, value.get("bot_id"), subject)


@dataclass(frozen=True)
class DiagnosticQuery:
    mode: DiagnosticMode = DiagnosticMode.SELF_CHECK
    target: ConfigTarget | None = None
    group_id: str | None = None
    extension_id: str | None = None
    capability_id: str | None = None
    operation_id: str | None = None
    operation_scope: ScopeRef | None = None
    window: IncidentWindow | None = None
    storage: bool = False
    execution: bool = False
    execution_task_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.mode, DiagnosticMode) or self.mode not in (DiagnosticMode.SELF_CHECK, DiagnosticMode.INCIDENT):
            raise ValueError("explanation and proposals use their separate service entry points")
        if (self.target is None) != (self.group_id is None):
            raise ValueError("configuration checks require one explicit target and group")
        if self.target and self.target.scope and not self.target.scope.is_resolved:
            raise ValueError("diagnostic configuration scope must be resolved")
        if self.capability_id and not self.extension_id:
            raise ValueError("consent check requires its extension")
        for value in (self.group_id, self.extension_id, self.capability_id, self.operation_id, self.execution_task_id):
            if value is not None:
                _opaque(value, field="diagnostic identifier")
        if self.execution_task_id is not None and not self.execution:
            raise ValueError("task evidence requires the execution check")
        incident = self.mode is DiagnosticMode.INCIDENT
        if incident != all((self.operation_id, self.operation_scope, self.window)):
            raise ValueError("incident requires an exact operation, scope and bounded time window")
        if not incident and any((self.operation_id, self.operation_scope, self.window)):
            raise ValueError("operation history is only available in incident mode")
        if any(type(flag) is not bool for flag in (self.storage, self.execution)):
            raise ValueError("diagnostic selectors must be booleans")
        if not any((self.target, self.extension_id, self.operation_id, self.storage, self.execution)):
            raise ValueError("choose at least one local check")

    def document(self) -> dict:
        return {"mode": self.mode.value, "target": self.target.document() if self.target else None,
                "group_id": self.group_id, "extension_id": self.extension_id, "capability_id": self.capability_id,
                "operation_id": self.operation_id,
                "operation_scope": self.operation_scope.document() if self.operation_scope else None,
                "window": {"start": self.window.start.isoformat(), "end": self.window.end.isoformat()} if self.window else None,
                "storage": self.storage, "execution": self.execution, "execution_task_id": self.execution_task_id}

    @classmethod
    def restore(cls, value: dict) -> DiagnosticQuery:
        return cls(**{**value, "mode": DiagnosticMode(value["mode"]),
                      "target": restore_target(value["target"]) if value["target"] else None,
                      "operation_scope": ScopeRef.restore(value["operation_scope"]) if value["operation_scope"] else None,
                      "window": IncidentWindow(**{k: datetime.fromisoformat(v) for k, v in value["window"].items()})
                      if value["window"] else None})


@dataclass(frozen=True)
class DiagnosticCheck:
    check_id: str
    name: str
    version: str
    level: str
    scope_contract: str
    permission: str
    cost: str = "bounded_local_read"
    timeout_ms: int = 500
    freshness_seconds: int = 60
    side_effects: str = "none"


@dataclass(frozen=True)
class DiagnosticEvidence:
    reference: str
    scope: ScopeRef
    revision_token: str


@dataclass(frozen=True)
class CheckResult:
    check: DiagnosticCheck
    status: CheckStatus
    code: str
    started_at: datetime
    finished_at: datetime
    elapsed_ms: float
    details_json: str
    evidence: tuple[DiagnosticEvidence, ...]


@dataclass(frozen=True)
class Finding:
    conclusion: str
    supporting_evidence: tuple[str, ...]
    opposing_evidence: tuple[str, ...]
    evidence_level: str
    reason: str


@dataclass(frozen=True)
class DiagnosticReport:
    report_id: str
    mode: DiagnosticMode
    origin_key: str
    query: DiagnosticQuery | None
    results: tuple[CheckResult, ...]
    findings: tuple[Finding, ...]
    explanation: str
    uncertainties: tuple[str, ...]
    next_steps: tuple[str, ...]
    created_at: datetime
    expires_at: datetime
    basis_token: str


@dataclass(frozen=True)
class RepairProposal:
    proposal_id: str
    revision: int
    state: str
    review_token: str
    review_json: str
    receipt_json: str | None = None
    replayed: bool = False

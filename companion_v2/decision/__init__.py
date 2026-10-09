"""Optional Laya decision-model integration.

The plugin ships typed-question adapters only. Laya's Python package is
installed in the AstrBot runtime, and checkpoints are fetched by Laya itself.
"""

from .contract import (
    DECISION_FIELDS,
    LayaDecision,
    DecisionContractError,
    deterministic_skip_reason,
    parse_decision,
)
from .service import LayaDecisionService
from .store import LayaSettingsStore

__all__ = [
    "DECISION_FIELDS",
    "DecisionContractError",
    "LayaDecision",
    "LayaDecisionService",
    "LayaSettingsStore",
    "deterministic_skip_reason",
    "parse_decision",
]

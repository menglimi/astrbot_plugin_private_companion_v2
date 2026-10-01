"""Side-effect-free G3 conversation slice using a deterministic local renderer."""

from .kernel import IsolatedConversationKernel
from .foreground import (
    ClaimKind,
    ContextContribution,
    ContributionState,
    DeterministicLocalModel,
    EvidencePromptCompiler,
    ForegroundContextAssembler,
    ForegroundConversationPipeline,
    ForegroundLeaseRegistry,
    GroundedDraftReviewer,
)
from .models import (
    ConversationReceipt,
    DeterministicFakeRenderer,
    ExternalEffectCounters,
    InboundConversationEvent,
)

__all__ = [
    "ConversationReceipt",
    "ClaimKind",
    "ContextContribution",
    "ContributionState",
    "DeterministicFakeRenderer",
    "DeterministicLocalModel",
    "EvidencePromptCompiler",
    "ExternalEffectCounters",
    "ForegroundContextAssembler",
    "ForegroundConversationPipeline",
    "ForegroundLeaseRegistry",
    "GroundedDraftReviewer",
    "InboundConversationEvent",
    "IsolatedConversationKernel",
]

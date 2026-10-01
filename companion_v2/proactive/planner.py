"""Select at most one feasible thought per opportunity; no sender exists in this layer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hashlib

from companion_v2.foundation.outcome import Outcome

from .models import DeliveryPlan, Opportunity, Thought, ThoughtSelection


Eligibility = Callable[[Thought], bool]


class ProactivePlanner:
    def select(
        self,
        opportunity: Opportunity,
        thoughts: tuple[Thought, ...],
        *,
        observed_at: datetime,
        selection_seed: str,
        eligible: Eligibility | None = None,
    ) -> Outcome[ThoughtSelection]:
        if opportunity.is_expired_at(observed_at):
            return Outcome.failed("opportunity_expired", "opportunity is no longer eligible")
        if not selection_seed or selection_seed != selection_seed.strip():
            return Outcome.failed("selection_seed_required", "selection requires a stable seed")
        condition = eligible or (lambda thought: True)
        feasible = tuple(
            thought
            for thought in thoughts
            if thought.opportunity == opportunity and condition(thought)
        )
        if not feasible:
            return Outcome.failed("no_feasible_thought", "no thought can become a delivery plan")
        if len(feasible) == 1:
            return Outcome.success(
                ThoughtSelection(
                    opportunity=opportunity,
                    selected=feasible[0],
                    feasible_count=1,
                    weight_used=False,
                )
            )
        selected = _weighted_select(feasible, selection_seed=selection_seed, opportunity=opportunity)
        return Outcome.success(
            ThoughtSelection(
                opportunity=opportunity,
                selected=selected,
                feasible_count=len(feasible),
                weight_used=True,
            )
        )

    def plan(self, selection: ThoughtSelection, *, created_at: datetime) -> DeliveryPlan:
        token = "\x1f".join(
            (
                selection.opportunity.opportunity_id,
                selection.selected.thought_id,
                str(selection.selected.share_candidate.material.material_id)
                if selection.selected.share_candidate is not None
                else "conversation",
            )
        ).encode("utf-8")
        return DeliveryPlan(
            plan_id=f"delivery-plan-{hashlib.sha256(token).hexdigest()[:24]}",
            selection=selection,
            created_at=created_at,
        )


def _weighted_select(
    thoughts: tuple[Thought, ...],
    *,
    selection_seed: str,
    opportunity: Opportunity,
) -> Thought:
    token = f"{selection_seed}\x1f{opportunity.opportunity_id}".encode("utf-8")
    unit = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") / 2**64
    largest = max(item.weight for item in thoughts)
    weights = tuple(item.weight / largest for item in thoughts)
    threshold = unit * sum(weights)
    total = 0.0
    for thought, weight in zip(thoughts, weights):
        total += weight
        if threshold < total:
            return thought
    return thoughts[-1]

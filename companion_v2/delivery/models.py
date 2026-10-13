"""Shared text delivery envelopes and trusted sender receipts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import inspect
from typing import Awaitable, Callable

from companion_v2.execution.models import ProviderBinding, TaskContext
from companion_v2.foundation.refs import normalize_utc
from companion_v2.identity_policy.models import _opaque

from .plan import OutboundPlan, PokePlan, VoicePlan


@dataclass(frozen=True)
class DeliveryEnvelope:
    part_id: str
    operation_id: str
    context: TaskContext
    sequence: int
    text: str
    payload_hash: str
    sender: ProviderBinding
    before_dispatch: Callable[[], object] | None = field(default=None, compare=False, repr=False)
    # Sealed content additions (quoted message, mentions, faces, component
    # order). They are derived from the same immutable batch the reply was
    # sealed from, so dispatching re-derives exactly the reviewed additions.
    plan: OutboundPlan | None = field(default=None, compare=False, kw_only=True)
    # Best-effort presentation side effects. They are authenticated by their
    # owner's sealed record and never invalidate the sealed text.
    voice: VoicePlan | None = field(default=None, compare=False, kw_only=True)
    poke: PokePlan | None = field(default=None, compare=False, kw_only=True)
    voice_required: bool = field(default=False, compare=False, kw_only=True)

    def __post_init__(self):
        for name, kind in (("plan", OutboundPlan), ("voice", VoicePlan), ("poke", PokePlan)):
            value = getattr(self, name)
            if value is not None and not isinstance(value, kind):
                raise ValueError(f"delivery envelope {name} must be a validated plan")
        if type(self.voice_required) is not bool:
            raise ValueError("delivery envelope voice requirement must be explicit")


@dataclass(frozen=True)
class DeliveryReceipt:
    part_id: str
    operation_id: str
    origin_key: str
    payload_hash: str
    sender: ProviderBinding
    status: str
    receipt_ref: str
    platform_ref: str | None = None
    delivered_at: datetime | None = None
    failure_code: str | None = None

    def __post_init__(self):
        for name in ("part_id", "operation_id", "origin_key", "payload_hash", "receipt_ref"):
            _opaque(getattr(self, name), field=name)
        if not isinstance(self.sender, ProviderBinding) or self.status not in ("accepted", "delivered", "not_sent", "unknown"):
            raise ValueError("receipt requires a known sender and explicit outcome")
        if self.platform_ref is not None:
            _opaque(self.platform_ref, field="platform_ref")
        if self.failure_code is not None:
            _opaque(self.failure_code, field="failure_code")
            if self.status != "not_sent":
                raise ValueError("a known rejection code requires a confirmed not-sent result")
        if self.status == "delivered":
            if self.platform_ref is None or self.delivered_at is None:
                raise ValueError("delivery confirmation needs an original platform reference and time")
            object.__setattr__(self, "delivered_at", normalize_utc(self.delivered_at, field="delivered_at"))
        elif self.delivered_at is not None:
            raise ValueError("only confirmed delivery has a delivery time")


@dataclass(frozen=True)
class LocalSender:
    binding: ProviderBinding
    send: Callable[[DeliveryEnvelope], Awaitable[DeliveryReceipt]]
    supports_images: bool = False
    supports_poke: bool = False

    def __post_init__(self):
        if (not isinstance(self.binding, ProviderBinding) or not inspect.iscoroutinefunction(self.send)
                or type(self.supports_images) is not bool or type(self.supports_poke) is not bool):
            raise ValueError("local senders require a complete binding and cooperative async function")

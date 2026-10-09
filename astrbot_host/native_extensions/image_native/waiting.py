"""Bounded reads of a confirmed backend task; no submission or implicit retry."""
from __future__ import annotations

import asyncio
from datetime import datetime

from .owner import checked
from .types import NativeImageError


def deadline_timestamp(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("deadline needs timezone")
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError) as exc:
        raise NativeImageError("invalid_native_deadline") from exc


async def wait_for_output(owner, operation, *, authorize, deadline: float, budget_seconds: float,
                          interval_seconds: float, now, monotonic, sleep):
    until = monotonic() + budget_seconds
    while operation["state"] == "pending":
        remaining = min(until - monotonic(), deadline - now())
        if remaining <= 0:
            break
        await checked(authorize)
        try:
            current = await asyncio.wait_for(owner.recover(operation["scope"], operation["id"], authorize=authorize), timeout=remaining)
        except TimeoutError:
            # Keep the original locator and operation. The cancelled read does
            # not imply a new generation or a definitive backend failure.
            break
        operation = current
        if operation["state"] != "pending":
            break
        remaining = min(until - monotonic(), deadline - now())
        if remaining <= 0:
            break
        await sleep(min(interval_seconds, remaining))
    return operation

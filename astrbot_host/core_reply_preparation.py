"""Measure this plugin's request preparation without changing native dispatch."""

from contextlib import contextmanager
from datetime import datetime, timezone
import time

from companion_v2.execution.models import stamp
from .core_reply import CORE_REPLY_CONTEXT_EXTRA


def _moment(clock):
    try:
        value = clock() if clock else None
        return value if isinstance(value, datetime) else datetime.now(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


@contextmanager
def measure_core_preparation(event, name, *, now=None):
    """Keep only stage names and measured time; never persist inline."""
    state = event.get_extra(CORE_REPLY_CONTEXT_EXTRA)
    if not isinstance(state, dict):
        yield
        return
    started_at, started = stamp(_moment(now)), time.monotonic()
    status = "returned"
    try:
        yield
    except BaseException:
        status = "failed"
        raise
    finally:
        try:
            step = {"name": name, "state": status, "started_at": started_at,
                    "finished_at": stamp(_moment(now)),
                    "elapsed_ms": round(max(0, time.monotonic() - started) * 1000)}
            state.setdefault("_preparation_steps", []).append(step)
            observer = state.get("_preparation_observer")
            if callable(observer):
                observer(step)
        except Exception:
            pass  # A diagnostic failure cannot change authorization or a reply.

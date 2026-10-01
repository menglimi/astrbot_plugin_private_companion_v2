"""Governance for derived sources, shared by all source consumers."""

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import get_ident

from companion_v2.execution.models import TaskError
from companion_v2.storage.codec import decode_timestamp


_CURRENT = ContextVar("source_validation_traversal", default=None)


def _task():
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


def _guards(runtime):
    return tuple((owner, guard, guard.closed, guard.check)
                 for owner, guard in getattr(runtime, "_source_owner_guards", {}).items())


@dataclass
class _Traversal:
    runtime: object
    at: object
    thread: int
    task: object
    guards: tuple
    checked: set = field(default_factory=set)
    visiting: set = field(default_factory=set)
    active: bool = True


def key(reference):
    return (reference.source_id, reference.version.lineage_id, reference.version.revision)


def validate(runtime, reference, at):
    """Reuse only completed checks in this synchronous runtime/time call stack."""
    state = _CURRENT.get()
    thread, task, guards = get_ident(), _task(), _guards(runtime)
    if (state is not None and state.active and state.runtime is runtime and state.at == at
            and state.thread == thread and state.task is task):
        if state.guards != guards:
            state.checked.clear()
            state.guards = guards
        _walk(state, key(reference))
        return
    state = _Traversal(runtime, at, thread, task, guards)
    token = _CURRENT.set(state)
    try:
        _walk(state, key(reference))
    finally:
        # A copied context may outlive this call or enter another task/thread.
        state.active = False
        state.checked.clear()
        state.visiting.clear()
        _CURRENT.reset(token)


def _walk(state, reference_key):
    runtime, at = state.runtime, state.at
    pending, entered = [(reference_key, False)], set()
    try:
        while pending:
            current, exiting = pending.pop()
            # Even a repeated read must observe current source revocation/expiry.
            row = runtime.read_one("""SELECT * FROM sources
                WHERE source_id = ? AND lineage_id = ? AND source_revision = ?""", current)
            if row is None or row["state"] != "active":
                raise TaskError("source_dependency_unavailable", "an original source dependency is unavailable")
            if at < decode_timestamp(row["issued_at"]) or (row["expires_at"] and at >= decode_timestamp(row["expires_at"])):
                raise TaskError("source_dependency_expired", "an original source dependency is outside its validity")
            if exiting:
                from .governance import validate as validate_owner
                from .repositories import _source_from_row
                # Postorder keeps owner reads of declared inputs out of recursion.
                validate_owner(runtime, _source_from_row(row), at)
                state.checked.add(current)
                state.visiting.remove(current)
                entered.remove(current)
            elif current in state.visiting:
                raise TaskError("source_dependency_cycle", "a derived source cannot support itself")
            elif current not in state.checked:
                state.visiting.add(current)
                entered.add(current)
                pending.append((current, True))
                pending.extend((tuple(r), False) for r in runtime.read_all("""SELECT input_id, input_lineage, input_revision
                    FROM source_dependencies WHERE dependent_id = ? AND dependent_lineage = ? AND dependent_revision = ?""", current))
    finally:
        # An owner can catch a rejected nested read. Its unfinished nodes must not
        # become cached successes or remain marked as a recursive visit.
        state.visiting.difference_update(entered)


def link(runtime, dependent, inputs, at):
    """Trusted source-owner API, called in the publication transaction."""
    target = key(dependent)
    with runtime.transaction() as connection:
        for reference in inputs:
            validate(runtime, reference, at)
            pending, seen = [key(reference)], set()
            while pending:
                current = pending.pop()
                if current == target:
                    raise TaskError("source_dependency_cycle", "a derived source cannot support itself")
                if current in seen:
                    continue
                seen.add(current)
                pending.extend(tuple(r) for r in runtime.read_all("""SELECT input_id, input_lineage, input_revision
                    FROM source_dependencies WHERE dependent_id = ? AND dependent_lineage = ? AND dependent_revision = ?""", current))
            connection.execute("INSERT OR IGNORE INTO source_dependencies VALUES (?, ?, ?, ?, ?, ?)", (*target, *key(reference)))


def revoke_dependants(runtime, reference, at):
    """Revocation is durable; publishing a new source cannot reactivate descendants."""
    pending, seen = [key(reference)], set()
    with runtime.transaction() as connection:
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            children = runtime.read_all("""SELECT dependent_id, dependent_lineage, dependent_revision
                FROM source_dependencies WHERE input_id = ? AND input_lineage = ? AND input_revision = ?""", current)
            for child in children:
                values = tuple(child)
                connection.execute("""UPDATE sources SET state = 'revoked', governance_revision = governance_revision + 1,
                    updated_at = ? WHERE source_id = ? AND lineage_id = ? AND source_revision = ? AND state = 'active'""",
                    (at.isoformat(), *values))
                pending.append(values)

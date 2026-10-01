"""Exact-scope delivery grant lineage for the single-target staging profile."""

from __future__ import annotations

from companion_v2.execution.models import TaskError, require
from companion_v2.identity_policy.models import AuthorizationTier, GrantState

from .staging_config import DELIVERY_CAPABILITY, DELIVERY_GRANT_ID


def delivery_grant_id(number: int) -> str:
    return DELIVERY_GRANT_ID if number == 1 else f"{DELIVERY_GRANT_ID}:{number}"


def delivery_grants(identity, *, subject, scope):
    """Reject foreign grants and retain every revoked predecessor as evidence."""
    named = {}
    for grant in identity.snapshot().grants:
        relevant = (grant.grant_id == DELIVERY_GRANT_ID
                    or grant.grant_id.startswith(DELIVERY_GRANT_ID + ":"))
        exact = (grant.subject == subject and grant.scope == scope
                 and grant.capability == DELIVERY_CAPABILITY)
        if not relevant and not exact:
            continue
        if not relevant:
            raise TaskError("staging_delivery_grant_changed", "unexpected staging delivery grant")
        suffix = grant.grant_id[len(DELIVERY_GRANT_ID):]
        if suffix == "":
            number = 1
        elif (suffix.startswith(":") and suffix[1:].isascii()
              and suffix[1:].isdecimal() and suffix[1:] == str(int(suffix[1:]))
              and int(suffix[1:]) >= 2):
            number = int(suffix[1:])
        else:
            raise TaskError("staging_delivery_grant_changed", "unexpected staging delivery grant")
        if (not exact or grant.tier is not AuthorizationTier.STANDARD
                or grant.expires_at is None):
            raise TaskError("staging_delivery_grant_changed", "staging delivery grant target or terms changed")
        named[number] = grant
    if set(named) != set(range(1, len(named) + 1)):
        raise TaskError("staging_delivery_grant_changed", "staging delivery grant history is incomplete")
    ordered = tuple(named[number] for number in range(1, len(named) + 1))
    for grant in ordered[:-1]:
        if grant.state is not GrantState.REVOKED or grant.revision != 2:
            raise TaskError("staging_delivery_grant_changed", "previous staging delivery grant remains active")
    if ordered:
        current = ordered[-1]
        if ((current.state is GrantState.ACTIVE and current.revision != 1)
                or (current.state is GrantState.REVOKED and current.revision != 2)):
            raise TaskError("staging_delivery_grant_changed", "current staging delivery grant changed")
    return ordered


def require_delivery_access(identity, *, actor, scope, observed_at):
    grants = delivery_grants(identity, subject=actor.subject, scope=scope)
    access = require(identity.authorize(actor, scope=scope,
        capability=DELIVERY_CAPABILITY, observed_at=observed_at))
    if not grants or access.grant_id != grants[-1].grant_id or access.grant_revision != 1:
        raise TaskError("staging_delivery_grant_changed", "current staging delivery grant changed")
    return access

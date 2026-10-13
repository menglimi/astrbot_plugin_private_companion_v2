"""Check whether a confirmed mobile room still has a usable host ticket."""

from __future__ import annotations

import json

from companion_v2.execution.models import digest, encode
from companion_v2.together.provider import scope_key


def room_request_available(service, context, request_id):
    """Return False only when a committed room's original ticket is gone.

    The caller already checked the current phone, context and create consent.
    Missing or unconfirmed native history never permits a replacement request.
    """
    provider = getattr(service, '_native_provider', None)
    tickets = getattr(service, 'ticket_store', None)
    if provider is None or tickets is None or getattr(provider, '_closed', False):
        return None
    scope = scope_key(json.loads(encode(context)))
    invocation_id = 'mobile-' + digest(['mobile-together.v1', 'together.room.create', request_id, context.key])
    operation = next((item for item in provider.store.latest(scope, 'together.room.create')
                      if item.get('invocation_id') == invocation_id), None)
    if operation is None or operation.get('state') != 'succeeded' or operation.get('effect') != 'committed':
        return None
    room = (operation.get('result') or {}).get('room') or {}
    token = room.get('ticket_token')
    if type(token) is not str or not token:
        return None
    ticket = tickets.get(token)
    return bool(ticket is not None and ticket.user_id == context.actor.principal.native_account_id
                and getattr(ticket.native_v2, 'scope_key', None) == scope)

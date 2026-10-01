"""A reset changes the conversation, never the private relationship's route."""

from companion_v2.foundation.refs import ScopeKind


ROUTE_FIELDS = ("installation_id", "platform", "kind", "native_scope_id", "bot_id", "account_id")


def same_private_route(original, current):
    return (original.is_resolved and current.is_resolved
            and original.kind is ScopeKind.PRIVATE and current.kind is ScopeKind.PRIVATE
            and all(getattr(original, field) == getattr(current, field) for field in ROUTE_FIELDS))

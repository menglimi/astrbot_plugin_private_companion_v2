"""Read group forwards from the exact group message on its pinned OneBot account."""

import asyncio

from companion_v2.conversation.forwards.models import ForwardIntakePolicy
from companion_v2.conversation.quotes.models import message_number
from companion_v2.execution.models import TaskError
from companion_v2.foundation.refs import ScopeKind

from .forwards import NativeForwardLocator, capture_forward_cards, freeze_forward_cards
from .history import extract_history_messages
from .native import account_number


async def read_group_forwards(locators, *, message_id, sender_id, client, scope, reverse_api_type,
                              image_loader, audio_loader=None, video_loader=None, retained=(),
                              intake=ForwardIntakePolicy()):
    """Capture expanded nodes without resolving their displayed accounts as identities."""
    try:
        if scope.kind is not ScopeKind.GROUP:
            raise TaskError("host_forward_scope_mismatch", "group forward history needs its original group route")
        if (not isinstance(locators, tuple) or not 0 < len(locators) <= intake.max_forwards
                or any(type(item) is not NativeForwardLocator for item in locators)
                or tuple(item.position for item in locators) != tuple(sorted({item.position for item in locators}))):
            raise TaskError("host_forward_limit", "group input needs bounded ordered native forward locators")
        peer = account_number(scope.native_scope_id)
        sender = account_number(sender_id)
        if sender == scope.account_id:
            raise TaskError("host_forward_scope_mismatch", "the bot cannot forward a group message as its own input")
        sequence = message_number(message_id, error_code="host_forward_invalid")
        api, clients = client._api._wsr_api, client._wsr_api_clients
        connection = clients.get(scope.account_id)

        def current():
            if (type(api) is not reverse_api_type or api._api_clients is not clients or not connection
                    or client._api._wsr_api is not api or client._wsr_api_clients is not clients
                    or clients.get(scope.account_id) is not connection):
                raise TaskError("host_forward_account_changed", "original group forward account connection changed")

        current()
        raw = await api.call_action("get_group_msg_history", self_id=scope.account_id,
            group_id=peer, message_seq=sequence, count=1, reverse_order=False, parse_mult_msg=True)
        current()
        records = extract_history_messages(raw)
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            raise TaskError("host_forward_unavailable", "history did not return the exact outer group message")
        outer = records[0]
        native_sender = outer.get("sender")
        if (outer.get("message_type") != "group" or outer.get("anonymous") is not None
                or outer.get("sub_type") == "anonymous" or not isinstance(native_sender, dict)
                or account_number(outer.get("self_id")) != scope.account_id
                or account_number(outer.get("group_id")) != peer
                or message_number(outer.get("message_id"), error_code="host_forward_scope_mismatch") != sequence
                or account_number(native_sender.get("user_id")) != sender
                or (outer.get("user_id") is not None and account_number(outer["user_id"]) != sender)):
            raise TaskError("host_forward_scope_mismatch", "forward history belongs to another group, sender or message")
        parts = outer.get("message")
        if not isinstance(parts, list) or not parts:
            raise TaskError("host_forward_unsupported", "outer group message requires a native component array")
        if len(parts) > 128:
            raise TaskError("host_forward_limit", "outer group message exceeds its component budget")
        positions, cards = [], []
        for position, part in enumerate(parts):
            if not isinstance(part, dict) or not isinstance(part.get("data"), dict):
                raise TaskError("host_forward_unsupported", "outer group component requires a native data object")
            if part.get("type") == "forward":
                positions.append(position)
                cards.append(part["data"])
        if tuple(positions) != tuple(item.position for item in locators):
            raise TaskError("host_forward_scope_mismatch", "history changed the ordered group forward positions")
        plans = freeze_forward_cards(locators, cards, audio_enabled=audio_loader is not None,
                                     video_enabled=video_loader is not None, intake=intake)
        return await capture_forward_cards(plans, image_loader=image_loader, audio_loader=audio_loader,
                                           video_loader=video_loader, current=current, retained=retained)
    except TaskError:
        raise
    except asyncio.TimeoutError:
        raise TaskError("host_forward_timeout", "group forward preparation did not complete in time") from None
    except Exception:
        raise TaskError("host_forward_unavailable", "group forward nodes could not be captured") from None

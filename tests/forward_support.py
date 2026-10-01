"""Synthetic OneBot forward snapshots; no remote messages or user data."""

from copy import deepcopy
import base64
from functools import partial
from types import SimpleNamespace as NS

from astrbot_host.media import load_native_image
from companion_v2.adapters.astrbot.forwards import read_private_forwards
from tests.native_adapter_support import FakeEvent, FakeReverseApi
from tests.test_conversation_images import FakeImage, image_bytes
from tests.test_conversation_quotes import QuoteFixture, quote_raw


class FakeForward:
    type = "Forward"

    def __init__(self, identifier="forward-resource"):
        self.id = identifier
        self.content = "untrusted SDK inline content"


def node_raw(text="记录中的一句话", *, sender="300", name="记录中的昵称", images=(), at=1700000000,
             nested=None, audios=(), videos=()):
    parts = [{"type": "text", "data": {"text": text}}] if text else []
    parts.extend({"type": "image", "data": {"file": FakeImage(body).file, "url": "https://invalid.example/unused"}}
                 for body in images)
    for kind, bodies in (("record", audios), ("video", videos)):
        parts.extend({"type": kind, "data": {"file": "base64://" + base64.b64encode(body).decode("ascii")}}
                     for body in bodies)
    if nested is not None:
        parts.append({"type": "forward", "data": {"id": "nested-resource", "content": nested}})
    return {"message_id": 345, "message_type": "group", "group_id": 900,
            "sender": {"user_id": sender, "nickname": name}, "time": at, "message": parts}


def forward_raw():
    return {"messages": [node_raw(images=(image_bytes(),)), node_raw("第二位说话者", sender="400")]}


def outer_raw(message_id="678", *, cards=None, content=None):
    cards = cards or [{"type": "forward", "data": {"id": "forward-resource", "content": content or forward_raw()["messages"]}}]
    return {"self_id": 100, "user_id": 200, "message_type": "private", "sub_type": "friend",
            "message_id": int(message_id), "sender": {"user_id": 200}, "message": cards}


def quoted_forward_raw(*, sender="100", nodes=None, cards=1, direct=False):
    raw = quote_raw(sender=sender, count=int(direct), text="")
    raw["message"].extend({"type": "forward", "data": {"id": "forward-resource",
        "content": deepcopy(nodes if nodes is not None else forward_raw()["messages"])}} for _ in range(cards))
    return raw


class ForwardFixture(QuoteFixture):
    def setUp(self):
        super().setUp()
        self.forward_raw = forward_raw()
        self.forward_resources = ["forward-resource"]
        self.forward_message_ids = set()
        self.bridge.forward_type = FakeForward
        self.bridge.forward_loader = partial(read_private_forwards, reverse_api_type=FakeReverseApi, image_loader=load_native_image)
        previous = self.api.call_action
        async def dispatch(action, **params):
            if action == "get_friend_msg_history" and params.get("message_seq") in self.forward_message_ids:
                self.api.calls.append((action, params))
                cards = [{"type": "forward", "data": {"id": resource, "content": deepcopy(self.forward_raw["messages"])}}
                         for resource in self.forward_resources]
                return {"messages": [outer_raw(params["message_seq"], cards=cards)]}
            return await previous(action, **params)
        self.api.call_action = dispatch

    def forward_event(self, identifier="678", *, resource="forward-resource", with_text=True):
        self.forward_message_ids.add(identifier)
        self.forward_resources = [resource]
        event = FakeEvent(self.native, event_id=identifier)
        event.message_obj.message = ([NS(type="Plain", text="看看这份聊天记录")] if with_text else []) + [FakeForward(resource)]
        return event

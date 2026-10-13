"""Synthetic configured groups with both shared and per-member native sessions."""

from types import SimpleNamespace as NS

from tests.multi_host_support import MultiFixture, MultiNativeContext, multi_config
from tests.native_adapter_support import FakeEvent


def group_config(**changes):
    return multi_config(group_targets=[
        dict(target_id="group-a", platform_id="qq-main", account_id="100", bot_id="bot-a", group_id="300"),
        dict(target_id="group-b", platform_id="qq-main", account_id="100", bot_id="bot-a", group_id="301"),
        dict(target_id="group-c", platform_id="qq-second", account_id="101", bot_id="bot-b", group_id="300"),
    ], **changes)


class GroupContext(MultiNativeContext):
    async def current(self, umo):
        return self.conversations.get(umo, self.conversations[umo.split(":", 1)[0]])

    async def resolve(self, **kwargs):
        self.role_lookups += 1
        if self.before_resolve:
            await self.before_resolve(self.role_lookups)
        umo = kwargs["umo"]
        selected = self.selections.get(umo, self.selections[umo.split(":", 1)[0]])
        return selected, self.persona_records.get(selected), None, False


class Query(dict):
    def getlist(self, key):
        return [self[key]] if key in self else []


class GroupFixture(MultiFixture):
    def setUp(self):
        super().setUp()
        self.native = GroupContext()
        self.window_personas.update({
            "qq-main:GroupMessage:300": "original",
            "qq-main:GroupMessage:301": "original",
            "qq-second:GroupMessage:300": "original",
        })
        self.controller = self.make_controller(group_config())

    def group_event(self, target="group-a", identifier="group-message", sender="200", *, unique=False, text="大家好"):
        target = self.controller.settings.target(target)
        event = FakeEvent(NS(platform=self.native.platforms[target.platform_id]), event_id=identifier,
                          sender=sender, login=target.account_id, text=text)
        kind = NS(value="GroupMessage")
        event.message_obj.type = event.session.message_type = kind
        event.message_obj.group_id = target.group_id
        event.message_obj.session_id = target.group_id
        event.session.session_id = sender + "_" + target.group_id if unique else target.group_id
        event.unified_msg_origin = f"{target.platform_id}:GroupMessage:{event.session.session_id}"
        self.window_personas.setdefault(event.unified_msg_origin, "original")
        event.message_obj.raw_message = dict(post_type="message", message_type="group", self_id=int(target.account_id),
            user_id=int(sender), sender={"user_id": int(sender)}, group_id=int(target.group_id), message_id=identifier)
        event.created_at = self.clock.now().timestamp()
        return event

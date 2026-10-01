"""Group original-image selection and local ACK fixtures, with no remote traffic."""

from copy import deepcopy

from tests.group_media_support import group_raw
from tests.group_quote_media_support import GroupQuoteMediaFixture
from tests.image_delivery_support import attach_originals


class GroupImageDeliveryFixture(GroupQuoteMediaFixture):
    def setUp(self):
        super().setUp()
        self.native.provider.client.state.behavior = attach_originals

    def sends(self, platform="qq-main"):
        api = self.native.platforms[platform].client._api._wsr_api
        return [params for action, params in api.calls if action == "send_group_msg"]

    def parts(self, batch):
        return self.app.runtime.read_all("SELECT * FROM conversation_parts WHERE batch_id = ? ORDER BY sequence", (batch,))

    def sent_original(self, batch):
        part = self.parts(batch)[-1]
        identifier = part["platform_ref"].split(":")[-1]
        raw = group_raw(message_id=identifier, sender="100", count=0)
        raw["message"] = deepcopy(self.sends()[-1]["message"])
        self.records[identifier] = raw
        return identifier

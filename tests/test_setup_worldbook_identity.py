from types import SimpleNamespace
import unittest

from astrbot_plugin_private_companion.page_api import PrivateCompanionPageApi


class WorldbookIdentityTests(unittest.TestCase):
    def _api(self):
        api = object.__new__(PrivateCompanionPageApi)
        api.plugin = SimpleNamespace(
            data={},
            _platform_profile=lambda **kwargs: {"kind": "weixin_oc"},
        )
        return api

    def test_wechat_openid_is_preserved_as_an_opaque_node_id(self):
        api = self._api()
        user_id = "o9cq8043T0voJ1joNT3BwokaErZI@im.wechat"
        self.assertEqual(api._normalize_worldbook_member_id(user_id), user_id)
        self.assertTrue(api._worldbook_setup_member_id_valid(
            user_id, target_ids=[user_id], target_platform="weixin_oc"))

    def test_unrelated_opaque_text_is_still_rejected(self):
        api = self._api()
        self.assertFalse(api._worldbook_setup_member_id_valid(
            "not-a-real-id", target_ids=[], target_platform="weixin_oc"))


if __name__ == "__main__":
    unittest.main()

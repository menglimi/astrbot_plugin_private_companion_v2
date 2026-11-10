from types import SimpleNamespace
import unittest

from astrbot_plugin_private_companion.platform_compat import PlatformCompatibilityMixin


class _Platform:
    def meta(self):
        return SimpleNamespace(name="weixin_personal_sqco", id="weixin_oc")


class _Manager:
    def get_insts(self):
        return [_Platform()]


class _Plugin(PlatformCompatibilityMixin):
    target_platform = "weixin_oc"

    def __init__(self):
        self.context = SimpleNamespace(platform_manager=_Manager())


class PreferredPlatformNameTests(unittest.TestCase):
    def test_umo_name_uses_the_adapter_name_not_only_the_instance_id(self):
        self.assertEqual(_Plugin()._preferred_platform_name(), "weixin_personal_sqco")

    def test_unknown_request_stays_unchanged(self):
        plugin = _Plugin()
        plugin.target_platform = "aiocqhttp"
        self.assertEqual(plugin._preferred_platform_name(), "aiocqhttp")


if __name__ == "__main__":
    unittest.main()

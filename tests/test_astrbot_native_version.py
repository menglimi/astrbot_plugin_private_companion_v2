import unittest

from companion_v2.adapters.astrbot.native import check_version


class AstrBotNativeVersionTests(unittest.TestCase):
    def test_accepts_only_verified_host_contracts(self):
        for version in ("4.27.2", "4.28.2"):
            with self.subTest(version=version):
                check_version(version)

        for version in ("4.28.3", "4.29.0", None, []):
            with self.subTest(version=version):
                with self.assertRaisesRegex(ValueError, "verified contract"):
                    check_version(version)


if __name__ == "__main__":
    unittest.main()

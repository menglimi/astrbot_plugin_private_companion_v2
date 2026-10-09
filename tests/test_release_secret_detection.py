import json
import tempfile
import unittest
from pathlib import Path

from tools.build_v2_release import CORE_DIRS, ROOT, allowed, checked_payload, sources


class ReleaseSecretDetectionTests(unittest.TestCase):
    def test_core_release_sources_include_astrbot_changelog(self):
        self.assertIn(ROOT / "CHANGELOG.md", sources(ROOT, CORE_DIRS))

    def test_excludes_local_news_feed_capture_from_release_sources(self):
        root = Path("source-root")
        fixture = root / "fixtures" / "proactive" / "news_feed_juya_20261004.xml"
        self.assertFalse(allowed(fixture, root))

    def test_excludes_development_previews_backups_and_archived_tools(self):
        root = Path("source-root")
        excluded = (
            "pages/陪伴小屋/shell-preview.html",
            "pages/陪伴小屋/shell-preview-mock.html",
            "fixtures/reply_efficiency_preview.json",
            "pages/陪伴小屋/semantic-page.css.backup",
            "tests/group-test.out",
            "tools/_archive/old_check.py",
        )
        for relative in excluded:
            with self.subTest(path=relative):
                self.assertFalse(allowed(root / relative, root))

    def test_release_inventory_omits_local_shell_preview_and_backup(self):
        names = {path.relative_to(ROOT).as_posix() for path in sources(ROOT, CORE_DIRS)}
        self.assertNotIn("pages/陪伴小屋/shell-preview.html", names)
        self.assertNotIn("pages/陪伴小屋/shell-preview-mock.html", names)
        self.assertNotIn("fixtures/reply_efficiency_preview.json", names)
        self.assertNotIn("pages/陪伴小屋/semantic-page.css.backup", names)

    def test_page_build_manifest_omits_local_shell_preview(self):
        manifest = json.loads((ROOT / "pages" / "陪伴小屋" / "page-build.json").read_text(encoding="utf-8"))
        self.assertNotIn("shell-preview.html", manifest["files"])
        self.assertNotIn("semantic-page.css.backup", manifest["files"])

    def scan(self, payload):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.md"
            source.write_bytes(payload)
            return checked_payload(source, root)

    def test_flags_credential_prefixes_at_text_boundaries(self):
        for prefix in (b"ghp_", b"github_pat_", b"abk_", b"sk-proj-"):
            with self.subTest(prefix=prefix):
                with self.assertRaisesRegex(ValueError, "credential-like content rejected"):
                    self.scan(b"key=" + prefix + b"x" * 48)

    def test_does_not_treat_risk_article_slug_as_a_secret(self):
        payload = b"https://apnews.com/article/risk-" + b"supply-chain-" + b"a" * 40
        self.assertEqual(self.scan(payload), payload + b"\n")


if __name__ == "__main__":
    unittest.main()

"""Exercise the complete legacy-data acceptance flow using isolated synthetic sources."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from tests.legacy_data_acceptance_process import run


def _group(members, edges):
    return {
        "members": {account: {"name": f"合成成员{account}", "count": 5 + index}
                    for index, account in enumerate(members)},
        "relationship_edges": {
            f"{left}|{right}": {"a": left, "b": right, "count": index + 1, "tone": "banter"}
            for index, (left, right) in enumerate(edges)},
    }


def _profile(label, groups, *, diary_date, dream_date):
    worldbook_entries = [{"id": f"{label}-base", "name": f"{label}设定",
        "content": f"合成普通资料 {label}", "__template_key": "role"},
        {"id": f"{label}-member", "name": f"{label}私聊成员",
         "content": f"合成私聊成员资料 {label}", "__template_key": "user",
         "scope": ["900"]}]
    worldbook_group_profiles = {}
    worldbook_member_profiles = {}
    for group_id, record in groups.items():
        worldbook_entries.append({"id": f"{label}-group-{group_id}",
            "name": f"{label}群 {group_id}", "content": f"合成群资料 {label}/{group_id}",
            "__template_key": "group", "scope": [f"default:groupmessage:{group_id}"]})
        worldbook_group_profiles[group_id] = {"name": f"{label}群补充 {group_id}",
            "content": f"合成群补充资料 {label}/{group_id}"}
        account_id = next(iter(record["members"]))
        worldbook_member_profiles[account_id] = {"user_id": account_id,
            "name": f"{label}群成员 {account_id}", "content": f"合成群成员线索 {label}/{account_id}",
            "projection_kind": "group_observation",
            "group_observation_scope_ids": [f"default:groupmessage:{group_id}"]}

    return {
        "groups": groups,
        "worldbook_entries": worldbook_entries,
        "worldbook_group_profiles": worldbook_group_profiles,
        "worldbook_member_profiles": worldbook_member_profiles,
        "bot_diaries": [{"date": diary_date, "body": f"合成日记 {label}",
            "summary": f"合成摘要 {label}", "dream_fragments": [f"合成梦境片段 {label}"]}],
        "daily_dream": {"date": dream_date, "content": f"合成梦境 {label}",
            "afterglow": f"合成余韵 {label}"},
    }


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
                     encoding="utf-8", newline="\n")


def _png(color):
    output = io.BytesIO()
    Image.new("RGB", (2, 2), color).save(output, format="PNG")
    return output.getvalue()


def _source_hashes(root: Path, config_path: Path):
    paths = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]
    paths.append(config_path)
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths))}


class LegacyDataAcceptanceProcessTests(unittest.IsolatedAsyncioTestCase):
    def _write_source(self, root, config_path, *, target_label, account_offset, image_color):
        root.mkdir(parents=True)
        _write_json(config_path, {})
        primary_groups = {
            "789": _group([str(account_offset + 200), str(account_offset + 201)],
                          [(str(account_offset + 200), str(account_offset + 201))]),
            "790": _group([str(account_offset + 202), str(account_offset + 203),
                           str(account_offset + 204)],
                          [(str(account_offset + 202), str(account_offset + 203)),
                           (str(account_offset + 203), str(account_offset + 204))]),
        }
        secondary_groups = {
            "789": _group([str(account_offset + 301), str(account_offset + 302),
                           str(account_offset + 303)],
                          [(str(account_offset + 301), str(account_offset + 302)),
                           (str(account_offset + 302), str(account_offset + 303))]),
            "791": _group([str(account_offset + 304), str(account_offset + 305)],
                          [(str(account_offset + 304), str(account_offset + 305))]),
        }
        for index, (filename, label, groups) in enumerate((
                ("companions.json", f"{target_label}-主角色", primary_groups),
                ("persona_profiles/companion-b.json", f"{target_label}-次人格", secondary_groups))):
            profile = _profile(label, groups, diary_date="2025-04-01", dream_date="2025-04-02")
            photo = f"photo_reference_images/{index}-identity.png"
            outfit = f"photo_reference_images/{index}-outfit.png"
            for path, kind in ((photo, "identity"), (outfit, "outfit")):
                color = tuple(hashlib.sha256((label + kind).encode("utf-8")).digest()[:3])
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(_png(color))
            profile["persona_settings"] = {
                "photo_reference_catalog": [{"id": "identity", "source": photo,
                    "reference_roles": ["identity", "style"]}],
                "wardrobe_items": [{"id": "outfit", "name": label + "围巾",
                    "description": label + "合成穿搭", "tags": ["winter", "test"],
                    "path": outfit}]}
            _write_json(root / filename, profile)

        image_directory = root / "reaction_expression_library" / "images"
        image_directory.mkdir(parents=True)
        image = _png(image_color)
        image_sha = hashlib.sha256(image).hexdigest()
        (image_directory / "response.png").write_bytes(image)
        _write_json(root / "reaction_expression_library" / "catalog.json", {
            "version": 2,
            "items": [{"filename": "response.png", "stored_name": "response.png",
                       "sha256": image_sha, "name": f"{target_label}合成回应", "tags": ["test"]}],
        })
        (root / "archive-only").mkdir()
        (root / "archive-only" / "nested.txt").write_text(
            f"synthetic source immutability sentinel {target_label}\n",
            encoding="utf-8", newline="\n")

    async def test_multi_persona_multi_group_import_retries_reload_and_preserves_source(self):
        with TemporaryDirectory(prefix="companion-v2-legacy-acceptance-synthetic-") as temporary:
            base = Path(temporary)
            target_sources = {}
            source_hashes = {}
            for target_id, account_offset, image_color in (
                    ("first", 1000, "green"), ("second", 2000, "blue")):
                root = base / f"v1-{target_id}" / "astrbot_plugin_private_companion"
                config_path = base / f"v1-{target_id}" / "astrbot_plugin_private_companion_config.json"
                self._write_source(root, config_path, target_label=target_id,
                    account_offset=account_offset, image_color=image_color)
                target_sources[target_id] = (root, config_path)
                source_hashes.update(_source_hashes(root, config_path))

            first_root, first_config = target_sources["first"]
            result = await run(first_root, first_config, target_sources=target_sources)
            after = {}
            for root, config_path in target_sources.values():
                after.update(_source_hashes(root, config_path))

            migration = result["migration"]
            self.assertEqual(migration["source_personas"], 2)
            self.assertEqual(migration["target_persona_mappings"], 4)
            self.assertEqual(migration["targets"], ["first", "second"])
            self.assertEqual(migration["private_duplicate_retries"], 4)
            self.assertEqual(migration["reaction_assets_expected"], 4)
            self.assertEqual(migration["reaction_assets_created"], 4)
            self.assertEqual(migration["reaction_assets_remaining"], 0)
            self.assertEqual(migration["journals_expected"], 8)
            self.assertEqual(migration["journals_created"], 8)
            self.assertEqual(migration["journals_remaining"], 0)
            self.assertEqual(migration["reference_images_created"], 8)
            self.assertEqual(migration["wardrobe_items_created"], 4)
            self.assertEqual(migration["persisted_after_restart"]["reference_payloads"], 8)
            self.assertEqual(migration["persisted_after_restart"]["wardrobe_items"], 4)
            self.assertEqual(migration["persisted_after_restart"]["personas_verified"], 4)
            self.assertEqual(migration["persisted_after_restart"]["targets_verified"], 2)
            self.assertEqual(set(migration["archives_verified_by_target"]), {"first", "second"})
            self.assertTrue(all(item["complete"]
                                for item in migration["archives_verified_by_target"].values()))

            def group_counts(groups):
                return {(item["target_id"], item["persona_key"], item["source_group_key"]):
                        (item["members"], item["edges"]) for item in groups}

            def key(value):
                return hashlib.sha256(value.encode("utf-8")).hexdigest()

            expected_groups = {
                (target_id, persona_key, key(group_id)[:10]): counts
                for target_id in ("first", "second")
                for persona_key, pairs in (
                    (key("primary")[:8], (("789", (2, 1)), ("790", (3, 2)))),
                    (key("companion-b")[:8], (("789", (3, 2)), ("791", (2, 1)))),
                )
                for group_id, counts in pairs
            }
            self.assertEqual(group_counts(migration["groups"]), expected_groups)
            self.assertTrue(all(item["duplicate_retry"]
                                and item["group_worldbook_duplicate_retry"]
                                for item in migration["groups"]))
            self.assertEqual(group_counts(migration["persisted_after_restart"]["groups"]),
                             expected_groups)
            self.assertIsNotNone(migration["archive_verified_after_restart"])
            self.assertTrue(migration["archive_verified_after_restart"]["complete"])
            self.assertTrue(migration["v1_unchanged"])
            self.assertEqual(source_hashes, after)
            self.assertEqual(migration["model_calls"], 0)
            self.assertEqual(migration["platform_sends"], 0)


if __name__ == "__main__":
    unittest.main()

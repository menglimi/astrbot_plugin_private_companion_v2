"""人格工坊的领域合同：只追加、撤回也是新增、原文逐字保存。

这一组测试盯的是四条**用户明确要求**的性质，而不是实现细节：

* 历史只增不删（SQLite 层就拒绝 UPDATE/DELETE，不只是「代码里没写」）；
* 撤回 = 追加一版正文相同的记录，旧版仍在；
* 每版都带「当时对着的原文」，所以回头看仍然知道改的是哪份底稿；
* 正文与原文逐字保存（结尾空白、制表符、示例段落都不能被「顺手修好」）。

背景：V1 的人格标准化问卷用模型改写人格并**存回宿主**，用户填完之后只剩一坨生成
文本，既不好改也无从对照。V2 只保存草稿，从不写宿主人格。
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from companion_v2.execution.models import TaskError
from companion_v2.persona_craft import (MAX_NOTE_CHARS, PersonaSnapshot, PersonaWorkshop,
                                        clean_note, owner_key, version_id)
from companion_v2.storage.runtime import StorageRuntime


INSTALLATION = "installation-a"
ROLE = "persona-a"
ORIGINAL = "你是原来的角色。  \n\n示例：\t先问一句再回答。\n\n"
NOTE = "第一版：压短示例语气"


def snapshot(text=ORIGINAL, *, name="original", persona_id="original", resolved=True):
    return PersonaSnapshot(persona_id, name, text, resolved)


class PersonaCraftFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="companion-persona-craft-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(self.runtime.close)
        self.clock = [datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)]
        self.workshop = PersonaWorkshop(self.runtime, installation_id=INSTALLATION, role_id=ROLE,
                                        now=lambda: self.clock[0])

    def tick(self, seconds=60):
        self.clock[0] = self.clock[0] + timedelta(seconds=seconds)
        return self.clock[0]

    def save(self, text, *, note=NOTE, expected=""):
        return self.workshop.save(snapshot(), text=text, note=note, expected_current=expected)

    def rows(self, owner=None):
        owner = owner or owner_key(INSTALLATION, ROLE, "original")
        return tuple(self.runtime.read_all(
            "SELECT * FROM persona_draft_versions WHERE owner_key = ? ORDER BY sequence", (owner,)))


class AppendOnlyTests(PersonaCraftFixture):
    def test_every_save_appends_and_keeps_the_earlier_versions(self):
        first = self.save("第一版草稿")["version"]
        self.tick()
        second = self.save("第二版草稿", expected=first.version_id)["version"]
        self.assertEqual([row["sequence"] for row in self.rows()], [1, 2])
        self.assertEqual([row["draft_text"] for row in self.rows()], ["第一版草稿", "第二版草稿"])
        self.assertNotEqual(first.version_id, second.version_id)
        # 旧版仍可按 ID 取回，内容一字未改。
        history = self.workshop.state(snapshot())
        self.assertEqual([item.draft_text for item in history["versions"]], ["第二版草稿", "第一版草稿"])
        self.assertTrue(history["has_history"])
        self.assertEqual(history["count"], 2)

    def test_a_stale_expected_current_is_refused_without_writing(self):
        first = self.save("第一版草稿")["version"]
        with self.assertRaises(TaskError) as caught:
            self.save("并行的另一版", expected="")
        self.assertEqual(caught.exception.code, "persona_draft_conflict")
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["draft_text"], "第一版草稿")
        # 带着正确的当前版就能继续追加。
        self.save("第二版草稿", expected=first.version_id)
        self.assertEqual(len(self.rows()), 2)

    def test_the_database_itself_refuses_to_rewrite_history(self):
        """触发器是这条性质的实现，所以要直接证明它拦得住 SQL。"""
        self.save("第一版草稿")
        with closing(sqlite3.connect(self.root / StorageRuntime.DATABASE_FILENAME)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE persona_draft_versions SET draft_text = 'tampered'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM persona_draft_versions")
            connection.rollback()
        self.assertEqual([row["draft_text"] for row in self.rows()], ["第一版草稿"])

    def test_no_module_in_the_new_domain_issues_update_or_delete(self):
        """除了触发器，代码里也不该出现对这张表的 UPDATE/DELETE。"""
        root = Path(__file__).resolve().parents[1] / "companion_v2" / "persona_craft"
        source = "\n".join(path.read_text(encoding="utf-8").upper() for path in root.glob("*.py"))
        self.assertNotIn("UPDATE PERSONA_DRAFT_VERSIONS", source)
        self.assertNotIn("DELETE FROM PERSONA_DRAFT_VERSIONS", source)

    def test_the_note_is_refused_rather_than_truncated(self):
        with self.assertRaises(TaskError) as caught:
            clean_note("   ")
        self.assertEqual(caught.exception.code, "persona_note_invalid")
        with self.assertRaises(TaskError):
            clean_note("x" * (MAX_NOTE_CHARS + 1))
        with self.assertRaises(TaskError):
            clean_note(None)
        self.assertEqual(clean_note("  改短示例  "), "改短示例")


class RestoreTests(PersonaCraftFixture):
    def test_restore_appends_a_copy_instead_of_deleting_the_newer_version(self):
        first = self.save("第一版草稿")["version"]
        self.tick()
        second = self.save("第二版草稿", expected=first.version_id)["version"]
        self.tick()
        restored = self.workshop.restore(snapshot(), version_id=first.version_id,
                                         note="撤回第一版", expected_current=second.version_id)["version"]
        self.assertEqual(restored.draft_text, first.draft_text)
        self.assertEqual(restored.kind, "restore")
        self.assertEqual(restored.restored_from, first.version_id)
        self.assertEqual(restored.sequence, 3)
        # 三行都在：撤回没有删掉「被撤掉的那一版」。
        rows = self.rows()
        self.assertEqual([row["version_id"] for row in rows],
                         [first.version_id, second.version_id, restored.version_id])
        self.assertEqual(rows[1]["draft_text"], "第二版草稿")
        self.assertEqual(self.workshop.state(snapshot())["current"].version_id, restored.version_id)

    def test_restore_of_an_unknown_version_is_refused(self):
        self.save("第一版草稿")
        with self.assertRaises(TaskError) as caught:
            self.workshop.restore(snapshot(), version_id="persona-draft-v999999", note="撤回",
                                  expected_current="persona-draft-v000001")
        self.assertEqual(caught.exception.code, "persona_version_unavailable")
        self.assertEqual(len(self.rows()), 1)

    def test_a_restore_always_names_its_source(self):
        first = self.save("第一版草稿")["version"]
        self.tick()
        restored = self.workshop.restore(snapshot(), version_id=first.version_id, note="撤回",
                                         expected_current=first.version_id)["version"]
        self.assertEqual(restored.kind, "restore")
        self.assertIsNotNone(restored.restored_from)
        # 普通保存不许伪造来源：只有撤回能带 restored_from。
        with self.assertRaises(ValueError):
            from companion_v2.persona_craft.models import DraftVersion
            DraftVersion("x", 1, "draft", "t", "o", "n", "note", "persona-draft-v000001",
                         self.clock[0])


class OriginalSnapshotTests(PersonaCraftFixture):
    def test_every_version_carries_the_original_it_was_drafted_against(self):
        self.save("第一版草稿")
        # 操作者随后在 AstrBot 里改了人格；下一版必须记住新底稿，而旧版仍记着旧的。
        self.tick()
        moved = snapshot("你是**新**的角色。\n", name="renamed")
        self.workshop.save(moved, text="对着新原文的草稿", note="跟上新原文",
                           expected_current=version_id(1))
        rows = self.rows()
        self.assertEqual(rows[0]["original_text"], ORIGINAL)
        self.assertEqual(rows[0]["persona_name"], "original")
        self.assertEqual(rows[1]["original_text"], "你是**新**的角色。\n")
        self.assertEqual(rows[1]["persona_name"], "renamed")

    def test_the_text_and_the_original_are_stored_byte_for_byte(self):
        tricky = "行尾有两个空格  \n制表符\t在中间\n\n结尾两行都是空行\n\n"
        self.save(tricky)
        stored = self.rows()[0]
        self.assertEqual(stored["draft_text"], tricky)
        self.assertEqual(stored["original_text"], ORIGINAL)
        self.assertTrue(stored["original_text"].endswith("\n\n"))
        self.assertNotEqual(stored["original_text"], ORIGINAL.strip())
        # 读回来也必须一致（仓储层不能顺手 strip）。
        self.assertEqual(self.workshop.state(snapshot())["versions"][0].draft_text, tricky)

    def test_an_empty_original_is_a_state_not_a_failure(self):
        empty = snapshot("", name="", persona_id="", resolved=False)
        self.assertEqual(self.workshop.state(empty)["count"], 0)
        saved = self.workshop.save(empty, text="从零写一份", note="宿主没有人格", expected_current="")
        self.assertEqual(saved["version"].original_text, "")
        self.assertFalse(saved["version"].original_text)

    def test_ownership_survives_a_rebound_conversation(self):
        """草稿属于「角色 + 宿主人格」，换窗口重绑不该丢历史。"""
        self.save("第一版草稿")
        other_conversation = PersonaWorkshop(self.runtime, installation_id=INSTALLATION, role_id=ROLE,
                                             now=lambda: self.clock[0])
        self.assertEqual(other_conversation.state(snapshot())["count"], 1)
        # 换角色或换人格则是另一份历史。
        other_role = PersonaWorkshop(self.runtime, installation_id=INSTALLATION, role_id="persona-b",
                                     now=lambda: self.clock[0])
        self.assertEqual(other_role.state(snapshot())["count"], 0)
        other_persona = PersonaWorkshop(self.runtime, installation_id=INSTALLATION, role_id=ROLE,
                                        now=lambda: self.clock[0])
        self.assertEqual(other_persona.state(snapshot(persona_id="another"))["count"], 0)

    def test_versions_are_listed_newest_first_with_the_page_limit(self):
        current = ""
        for index in range(5):
            self.tick()
            current = self.save(f"第 {index} 版", expected=current)["version"].version_id
        history = self.workshop.state(snapshot(), limit=3)["versions"]
        self.assertEqual([item.sequence for item in history], [5, 4, 3])
        self.assertEqual(self.workshop.state(snapshot())["count"], 5)


class PayloadTests(PersonaCraftFixture):
    def test_the_page_payload_never_carries_a_hash(self):
        """instruction_hash 是安全相关值；其余哈希也没有展示价值。"""
        self.save("第一版草稿")
        payload = json.dumps(PersonaWorkshop(self.runtime, installation_id=INSTALLATION, role_id=ROLE,
                                             now=lambda: self.clock[0]).state(snapshot()),
                             default=str, ensure_ascii=False)
        self.assertNotIn("instruction_hash", payload)
        self.assertNotIn("owner_key", payload)
        import re
        self.assertIsNone(re.search(r"\b[0-9a-f]{64}\b", payload), payload)

    def test_the_workshop_refuses_a_missing_snapshot(self):
        for value in (None, "text", {"text": "x"}):
            with self.assertRaises(TaskError) as caught:
                self.workshop.state(value)
            self.assertEqual(caught.exception.code, "persona_workshop_request_invalid")

    def test_owner_keys_separate_roles_and_personas(self):
        self.assertNotEqual(owner_key(INSTALLATION, ROLE, "a"), owner_key(INSTALLATION, ROLE, "b"))
        self.assertNotEqual(owner_key(INSTALLATION, ROLE, "a"), owner_key(INSTALLATION, "other", "a"))
        self.assertEqual(owner_key(INSTALLATION, ROLE, "a"), owner_key(INSTALLATION, ROLE, "a"))
        with self.assertRaises(ValueError):
            owner_key("", ROLE, "a")


if __name__ == "__main__":
    unittest.main()

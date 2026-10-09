from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from astrbot_host.knowledge_sources import AstrBotKnowledgeSources


class FakeHelper:
    def __init__(self, docs):
        self.docs = docs
        self.init_error = None

    async def count_documents(self):
        return len(self.docs)

    async def list_documents(self, *, offset, limit):
        return self.docs[offset:offset + limit]


class FakeManager:
    def __init__(self, database, kb, helper):
        self.kb_db = NS(db_path=str(database))
        self.kb = kb
        self.helper = helper

    async def list_kbs(self):
        return [self.kb]

    async def get_kb(self, kb_id):
        return self.helper if kb_id == self.kb.kb_id else None


class AstrBotKnowledgeSourcesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-official-kb-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        kb_root = self.root / "knowledge_base"
        kb_root.mkdir(parents=True)
        database = kb_root / "kb.db"
        connection = sqlite3.connect(database)
        connection.executescript(
            "CREATE TABLE knowledge_bases (kb_id TEXT, kb_name TEXT);"
            "CREATE TABLE kb_documents (kb_id TEXT, doc_id TEXT, doc_name TEXT);"
        )
        connection.executemany("INSERT INTO knowledge_bases VALUES (?, ?)", [("kb-1", "星河设定")])
        connection.executemany("INSERT INTO kb_documents VALUES (?, ?, ?)", [
            ("kb-1", "doc-1", "角色资料.md"), ("kb-1", "doc-2", "城市资料.md")])
        connection.commit()
        connection.close()

        doc_root = kb_root / "kb-1"
        doc_root.mkdir()
        chunks = [
            ("米拉喜欢雨天", {"kb_id": "kb-1", "kb_doc_id": "doc-1", "chunk_index": 0}),
            ("她会沿着河边散步", {"kb_id": "kb-1", "kb_doc_id": "doc-1", "chunk_index": 1}),
            ("旧城有一座钟楼", {"kb_id": "kb-1", "kb_doc_id": "doc-2", "chunk_index": 0}),
        ]
        connection = sqlite3.connect(doc_root / "doc.db")
        connection.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, text TEXT, metadata TEXT)")
        connection.executemany("INSERT INTO documents (text, metadata) VALUES (?, ?)",
                               [(text, json.dumps(meta, ensure_ascii=False)) for text, meta in chunks])
        connection.commit()
        connection.close()

        self.docs = [NS(doc_id="doc-1", doc_name="角色资料.md", file_type="md", chunk_count=2),
                     NS(doc_id="doc-2", doc_name="城市资料.md", file_type="md", chunk_count=1)]
        kb = NS(kb_id="kb-1", kb_name="星河设定", description="角色与城市背景", emoji="📚",
                doc_count=2, chunk_count=3)
        manager = FakeManager(database, kb, FakeHelper(self.docs))
        self.sources = AstrBotKnowledgeSources(NS(kb_manager=manager))

    async def test_lists_official_kbs_and_documents_with_v1_ids(self):
        sources = await self.sources.list_sources()

        self.assertEqual(sources[0]["id"], "kb:kb-1")
        self.assertEqual(sources[0]["name"], "星河设定")
        self.assertEqual([item["id"] for item in sources[0]["documents"]],
                         ["doc:kb-1:doc-1", "doc:kb-1:doc-2"])

    async def test_candidates_respect_document_selection_and_character_budget(self):
        candidates = self.sources.candidates(
            ["doc:kb-1:doc-2"], source_limit=4, entry_limit=8, entry_char_limit=100,
            char_budget=100)

        self.assertEqual([item.document_id for item in candidates], ["doc-2"])
        self.assertEqual(candidates[0].document_name, "城市资料.md")
        self.assertEqual(candidates[0].text, "旧城有一座钟楼")

        bounded = self.sources.candidates(
            ["kb:kb-1"], source_limit=4, entry_limit=1, entry_char_limit=5, char_budget=3)
        self.assertEqual(len(bounded), 1)
        self.assertEqual(bounded[0].text, "米拉喜")

    async def test_documents_remain_selectable_when_the_embedding_provider_failed(self):
        self.sources.manager.helper.init_error = "embedding provider unavailable"
        self.sources.manager.helper.list_documents = AsyncMock(side_effect=RuntimeError("helper unavailable"))
        database = self.sources.manager.kb_db
        database.count_documents_by_kb = AsyncMock(return_value=2)
        database.list_documents_by_kb = AsyncMock(return_value=self.docs)

        sources = await self.sources.list_sources()

        self.assertEqual([item["doc_id"] for item in sources[0]["documents"]], ["doc-1", "doc-2"])
        self.sources.manager.helper.list_documents.assert_not_awaited()

    async def test_documents_use_host_metadata_when_the_helper_is_missing(self):
        self.sources.manager.helper = None
        database = self.sources.manager.kb_db
        database.count_documents_by_kb = AsyncMock(return_value=2)
        database.list_documents_by_kb = AsyncMock(return_value=self.docs)

        sources = await self.sources.list_sources()

        self.assertEqual([item["doc_id"] for item in sources[0]["documents"]], ["doc-1", "doc-2"])
        database.list_documents_by_kb.assert_awaited_once_with("kb-1", offset=0, limit=2)

    async def test_a_removed_chunk_database_does_not_hide_other_sources(self):
        connection = sqlite3.connect(self.root / "knowledge_base" / "kb.db")
        connection.execute("INSERT INTO knowledge_bases VALUES (?, ?)", ("kb-2", "已移除的资料"))
        connection.commit()
        connection.close()

        candidates = self.sources.candidates(["kb:kb-2", "kb:kb-1"])

        self.assertEqual(len(candidates), 3)
        self.assertTrue(all(item.knowledge_base_id == "kb-1" for item in candidates))

    async def test_damaged_metadata_does_not_hide_valid_chunks(self):
        connection = sqlite3.connect(self.root / "knowledge_base" / "kb-1" / "doc.db")
        connection.execute("UPDATE documents SET metadata = ? WHERE id = 1", ("{",))
        connection.commit()
        connection.close()

        candidates = self.sources.candidates(["kb:kb-1"])
        selected_document = self.sources.candidates(["doc:kb-1:doc-1"])

        self.assertEqual([item.text for item in candidates], ["她会沿着河边散步", "旧城有一座钟楼"])
        self.assertEqual([item.text for item in selected_document], ["她会沿着河边散步"])


if __name__ == "__main__":
    unittest.main()

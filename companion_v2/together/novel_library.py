# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import html
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Iterator
import uuid
import zipfile
from xml.etree import ElementTree


_CHAPTER_RE = re.compile(
    r"^(?:\s{0,4})(第[零〇一二两三四五六七八九十百千万0-9]+[章节卷回部篇集]|"
    r"chapter\s+[0-9ivxlcdm]+|序章|楔子|引子|前言|后记|尾声|番外(?:篇)?)"
    r"(?:[\s:：._-].*)?$",
    re.IGNORECASE,
)
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$")
_WORD_RE = re.compile(r"[\u3400-\u9fff]{2,12}|[A-Za-z][A-Za-z0-9_-]{1,30}")


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "p", "div", "section", "article", "aside", "header", "footer", "li",
        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "br", "hr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "svg", "math"}:
            self._ignored += 1
        elif lowered in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "svg", "math"} and self._ignored:
            self._ignored -= 1
        elif lowered in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.parts.append(data)

    def text(self) -> str:
        return _normalize_text("".join(self.parts))


def _normalize_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode_text(data: bytes) -> str:
    if not data:
        return ""
    candidates = ("utf-8-sig", "utf-16", "gb18030", "big5")
    for encoding in candidates:
        try:
            text = data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if text and text.count("\ufffd") == 0:
            return _normalize_text(text)
    raise ValueError("无法可靠识别文本编码，请将文件转换为 UTF-8 后重新导入")


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(str(value or ""))
    parser.close()
    return parser.text()


def _paragraphs(value: str, *, max_chars: int = 1800) -> list[str]:
    raw_items = [item.strip() for item in re.split(r"\n+", _normalize_text(value)) if item.strip()]
    result: list[str] = []
    for item in raw_items:
        remaining = item
        while len(remaining) > max_chars:
            boundary = max(
                remaining.rfind("。", 0, max_chars),
                remaining.rfind("！", 0, max_chars),
                remaining.rfind("？", 0, max_chars),
                remaining.rfind(". ", 0, max_chars),
            )
            if boundary < max_chars // 2:
                boundary = max_chars
            else:
                boundary += 1
            result.append(remaining[:boundary].strip())
            remaining = remaining[boundary:].strip()
        if remaining:
            result.append(remaining)
    return result


def _split_plain_text(text: str, *, markdown: bool = False) -> list[tuple[str, str]]:
    lines = _normalize_text(text).splitlines()
    starts: list[tuple[int, str]] = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        match = _MARKDOWN_HEADING_RE.match(line) if markdown else None
        if match:
            starts.append((index, match.group(1).strip()[:160]))
        elif _CHAPTER_RE.match(line):
            starts.append((index, line[:160]))
    if not starts:
        return [("正文", "\n".join(lines).strip())]
    chapters: list[tuple[str, str]] = []
    if starts[0][0] > 0:
        preface = "\n".join(lines[: starts[0][0]]).strip()
        if preface:
            chapters.append(("序言", preface))
    for position, (start, title) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        content = "\n".join(lines[start + 1 : end]).strip()
        chapters.append((title or f"第 {position + 1} 章", content))
    return [(title, content) for title, content in chapters if content or title]


class NovelLibrary:
    """UTF-8 novel storage with chapter-level progress and spoiler-safe FTS retrieval."""

    def __init__(self, data_dir: Path, *, max_upload_mb: int = 40) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.books_dir = self.data_dir / "books"
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.data_dir / "novel_library.sqlite3"
        self.max_upload_bytes = max(1, min(int(max_upload_mb or 40), 200)) * 1024 * 1024
        self._lock = threading.RLock()
        self._chapter_list_cache: OrderedDict[str, tuple[tuple[int, str, int], ...]] = OrderedDict()
        self._chapter_cache: OrderedDict[tuple[str, int], dict[str, Any]] = OrderedDict()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=20.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL,
                    source_path TEXT NOT NULL DEFAULT '',
                    sha256 TEXT NOT NULL UNIQUE,
                    chapter_count INTEGER NOT NULL DEFAULT 0,
                    paragraph_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                    chapter_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    word_count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(book_id, chapter_index)
                );
                CREATE TABLE IF NOT EXISTS paragraphs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                    chapter_index INTEGER NOT NULL,
                    paragraph_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    UNIQUE(book_id, chapter_index, paragraph_index)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS paragraph_fts USING fts5(
                    content,
                    book_id UNINDEXED,
                    chapter_index UNINDEXED,
                    paragraph_index UNINDEXED,
                    tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS reading_progress (
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                    chapter_index INTEGER NOT NULL DEFAULT 0,
                    paragraph_index INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, book_id)
                );
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                    chapter_index INTEGER NOT NULL,
                    paragraph_index INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                """
            )

    def import_bytes(self, filename: str, data: bytes) -> dict[str, Any]:
        safe_name = Path(str(filename or "novel.txt")).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in {".txt", ".md", ".markdown", ".epub"}:
            raise ValueError("目前仅支持 TXT、Markdown 和 EPUB 小说")
        if not data:
            raise ValueError("上传的小说文件为空")
        if len(data) > self.max_upload_bytes:
            raise ValueError(f"小说文件不能超过 {self.max_upload_bytes // 1024 // 1024} MB")
        digest = hashlib.sha256(data).hexdigest()
        existing = self.get_book_by_hash(digest)
        if existing:
            return {**existing, "duplicate": True}
        if suffix == ".epub":
            title, author, chapters = self._parse_epub(data, fallback_title=Path(safe_name).stem)
        else:
            text = _decode_text(data)
            title, author = Path(safe_name).stem[:160] or "未命名小说", ""
            chapters = _split_plain_text(text, markdown=suffix in {".md", ".markdown"})
        chapters = [(str(title_ or "").strip()[:160], _normalize_text(content)) for title_, content in chapters]
        chapters = [(title_, content) for title_, content in chapters if content]
        if not chapters:
            raise ValueError("没有从文件中识别到可阅读的正文")
        if len(chapters) > 10000:
            raise ValueError("章节数量异常，已停止导入")
        book_id = uuid.uuid4().hex
        source_dir = self.books_dir / book_id
        source_dir.mkdir(parents=True, exist_ok=False)
        source_path = source_dir / f"source{suffix}"
        source_path.write_bytes(data)
        now = time.time()
        paragraph_count = 0
        try:
            with self._lock, self._connection() as connection:
                connection.execute(
                    "INSERT INTO books(id,title,author,source_type,source_path,sha256,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (book_id, title[:160], author[:120], suffix.lstrip("."), str(source_path), digest, now, now),
                )
                for chapter_index, (chapter_title, content) in enumerate(chapters):
                    connection.execute(
                        "INSERT INTO chapters(book_id,chapter_index,title,content,word_count) VALUES(?,?,?,?,?)",
                        (book_id, chapter_index, chapter_title or f"第 {chapter_index + 1} 章", content, len(content)),
                    )
                    paragraph_rows = [
                        (book_id, chapter_index, paragraph_index, paragraph)
                        for paragraph_index, paragraph in enumerate(_paragraphs(content))
                    ]
                    connection.executemany(
                        "INSERT INTO paragraphs(book_id,chapter_index,paragraph_index,content) VALUES(?,?,?,?)",
                        paragraph_rows,
                    )
                    connection.executemany(
                        "INSERT INTO paragraph_fts(content,book_id,chapter_index,paragraph_index) VALUES(?,?,?,?)",
                        ((paragraph, row_book_id, row_chapter, paragraph_index)
                         for row_book_id, row_chapter, paragraph_index, paragraph in paragraph_rows),
                    )
                    paragraph_count += len(paragraph_rows)
                connection.execute(
                    "UPDATE books SET chapter_count=?,paragraph_count=?,updated_at=? WHERE id=?",
                    (len(chapters), paragraph_count, time.time(), book_id),
                )
        except Exception:
            try:
                source_path.unlink(missing_ok=True)
                source_dir.rmdir()
            except OSError:
                pass
            raise
        return {**self.get_book(book_id), "duplicate": False}

    def _parse_epub(self, data: bytes, *, fallback_title: str) -> tuple[str, str, list[tuple[str, str]]]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ValueError("EPUB 文件损坏或不是有效的 EPUB") from exc
        with archive:
            members = archive.infolist()
            if len(members) > 20000 or sum(item.file_size for item in members) > self.max_upload_bytes * 20:
                raise ValueError("EPUB 解压后的内容异常大，已停止导入")
            for item in members:
                path = Path(item.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("EPUB 包含不安全的文件路径")
            try:
                container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
                rootfile = next(
                    element.attrib.get("full-path", "")
                    for element in container.iter()
                    if element.tag.rsplit("}", 1)[-1] == "rootfile"
                )
                package_data = archive.read(rootfile)
            except (KeyError, StopIteration, ElementTree.ParseError) as exc:
                raise ValueError("EPUB 缺少有效的书籍目录") from exc
            package = ElementTree.fromstring(package_data)
            title = fallback_title
            author = ""
            manifest: dict[str, str] = {}
            spine: list[str] = []
            for element in package.iter():
                tag = element.tag.rsplit("}", 1)[-1]
                if tag == "title" and (element.text or "").strip() and title == fallback_title:
                    title = (element.text or "").strip()
                elif tag == "creator" and (element.text or "").strip() and not author:
                    author = (element.text or "").strip()
                elif tag == "item":
                    identifier = element.attrib.get("id", "")
                    href = element.attrib.get("href", "")
                    media_type = element.attrib.get("media-type", "")
                    if identifier and href and media_type in {"application/xhtml+xml", "text/html"}:
                        manifest[identifier] = href
                elif tag == "itemref" and element.attrib.get("idref"):
                    spine.append(element.attrib["idref"])
            base = Path(rootfile).parent
            chapters: list[tuple[str, str]] = []
            for identifier in spine:
                href = manifest.get(identifier)
                if not href:
                    continue
                member = (base / href.split("#", 1)[0]).as_posix()
                try:
                    document = _decode_text(archive.read(member))
                except (KeyError, ValueError):
                    continue
                chapter_text = _html_to_text(document)
                if not chapter_text:
                    continue
                heading = ""
                try:
                    root = ElementTree.fromstring(document)
                    for element in root.iter():
                        if element.tag.rsplit("}", 1)[-1] in {"h1", "h2", "h3", "title"}:
                            heading = "".join(element.itertext()).strip()
                            if heading:
                                break
                except ElementTree.ParseError:
                    pass
                chapters.append((heading[:160] or f"第 {len(chapters) + 1} 章", chapter_text))
            if not chapters:
                raise ValueError("EPUB 中没有识别到可阅读的章节")
            return title[:160] or fallback_title, author[:120], chapters

    def list_books(self, *, user_id: str = "") -> list[dict[str, Any]]:
        query = """
            SELECT b.*, p.chapter_index AS progress_chapter,
                   p.paragraph_index AS progress_paragraph, p.updated_at AS progress_updated_at
            FROM books b LEFT JOIN reading_progress p
              ON p.book_id=b.id AND p.user_id=?
            ORDER BY COALESCE(p.updated_at, b.created_at) DESC
        """
        with self._lock, self._connection() as connection:
            rows = connection.execute(query, (str(user_id or ""),)).fetchall()
        return [self._book_payload(row) for row in rows]

    def get_book_by_hash(self, digest: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM books WHERE sha256=?", (digest,)).fetchone()
        return self._book_payload(row) if row else None

    def get_book(self, book_id: str, *, user_id: str = "") -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """SELECT b.*, p.chapter_index AS progress_chapter,
                          p.paragraph_index AS progress_paragraph, p.updated_at AS progress_updated_at
                   FROM books b LEFT JOIN reading_progress p ON p.book_id=b.id AND p.user_id=?
                   WHERE b.id=?""",
                (str(user_id or ""), str(book_id or "")),
            ).fetchone()
        return self._book_payload(row) if row else None

    @staticmethod
    def _book_payload(row: sqlite3.Row) -> dict[str, Any]:
        keys = set(row.keys())
        return {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "author": str(row["author"] or ""),
            "source_type": str(row["source_type"]),
            "chapter_count": int(row["chapter_count"] or 0),
            "paragraph_count": int(row["paragraph_count"] or 0),
            "created_at": float(row["created_at"] or 0.0),
            "progress": {
                "chapter_index": int(row["progress_chapter"] or 0) if "progress_chapter" in keys else 0,
                "paragraph_index": int(row["progress_paragraph"] or 0) if "progress_paragraph" in keys else 0,
                "updated_at": float(row["progress_updated_at"] or 0.0) if "progress_updated_at" in keys else 0.0,
            },
        }

    def chapters(self, book_id: str) -> list[dict[str, Any]]:
        cache_key = str(book_id or "")
        with self._lock:
            cached = self._chapter_list_cache.get(cache_key)
            if cached is not None:
                self._chapter_list_cache.move_to_end(cache_key)
                return [
                    {"chapter_index": item[0], "title": item[1], "word_count": item[2]}
                    for item in cached
                ]
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT chapter_index,title,word_count FROM chapters WHERE book_id=? ORDER BY chapter_index",
                (cache_key,),
            ).fetchall()
            cached = tuple(
                (int(row["chapter_index"]), str(row["title"]), int(row["word_count"] or 0))
                for row in rows
            )
            self._chapter_list_cache[cache_key] = cached
            self._chapter_list_cache.move_to_end(cache_key)
            while len(self._chapter_list_cache) > 32:
                self._chapter_list_cache.popitem(last=False)
        return [
            {"chapter_index": item[0], "title": item[1], "word_count": item[2]}
            for item in cached
        ]

    def chapter(self, book_id: str, chapter_index: int) -> dict[str, Any] | None:
        cache_key = (str(book_id or ""), max(0, int(chapter_index or 0)))
        with self._lock:
            cached = self._chapter_cache.get(cache_key)
            if cached is not None:
                self._chapter_cache.move_to_end(cache_key)
                return cached
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT chapter_index,title,word_count FROM chapters WHERE book_id=? AND chapter_index=?",
                cache_key,
            ).fetchone()
            if row is None:
                return None
            paragraphs = connection.execute(
                "SELECT paragraph_index,content FROM paragraphs WHERE book_id=? AND chapter_index=? ORDER BY paragraph_index",
                (str(book_id or ""), int(row["chapter_index"])),
            ).fetchall()
        payload = dict(row)
        payload["paragraphs"] = [dict(item) for item in paragraphs]
        with self._lock:
            self._chapter_cache[cache_key] = payload
            self._chapter_cache.move_to_end(cache_key)
            while len(self._chapter_cache) > 12:
                self._chapter_cache.popitem(last=False)
        return payload

    def save_progress(self, user_id: str, book_id: str, chapter_index: int, paragraph_index: int) -> dict[str, Any]:
        user = str(user_id or "").strip()[:120]
        if not user:
            raise ValueError("当前房间没有可用的用户身份")
        resolved_book_id = str(book_id or "")
        resolved_chapter = max(0, int(chapter_index or 0))
        now = time.time()
        with self._lock, self._connection() as connection:
            row = connection.execute(
                """SELECT MAX(p.paragraph_index) AS max_paragraph
                   FROM chapters c LEFT JOIN paragraphs p
                     ON p.book_id=c.book_id AND p.chapter_index=c.chapter_index
                   WHERE c.book_id=? AND c.chapter_index=?
                   GROUP BY c.book_id,c.chapter_index""",
                (resolved_book_id, resolved_chapter),
            ).fetchone()
            if row is None:
                raise ValueError("章节不存在")
            max_paragraph = max(0, int(row["max_paragraph"] or 0))
            paragraph = max(0, min(int(paragraph_index or 0), max_paragraph))
            connection.execute(
                """INSERT INTO reading_progress(user_id,book_id,chapter_index,paragraph_index,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(user_id,book_id) DO UPDATE SET
                   chapter_index=excluded.chapter_index,
                   paragraph_index=excluded.paragraph_index,
                   updated_at=excluded.updated_at""",
                (user, resolved_book_id, resolved_chapter, paragraph, now),
            )
        return {"chapter_index": resolved_chapter, "paragraph_index": paragraph, "updated_at": now}

    def progress(self, user_id: str, book_id: str) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT chapter_index,paragraph_index,updated_at FROM reading_progress WHERE user_id=? AND book_id=?",
                (str(user_id or ""), str(book_id or "")),
            ).fetchone()
        return dict(row) if row else {"chapter_index": 0, "paragraph_index": 0, "updated_at": 0.0}

    def reading_context(
        self,
        *,
        user_id: str,
        book_id: str,
        chapter_index: int,
        paragraph_index: int,
        query: str,
        top_k: int = 8,
    ) -> dict[str, Any]:
        book = self.get_book(book_id, user_id=user_id)
        chapter = self.chapter(book_id, chapter_index)
        if not book or not chapter:
            return {}
        max_chapter = max(0, int(chapter_index or 0))
        max_paragraph = max(0, int(paragraph_index or 0))
        current_paragraphs = chapter.get("paragraphs") or []
        window_start = max(0, max_paragraph - 5)
        window_end = min(len(current_paragraphs), max_paragraph + 3)
        nearby = current_paragraphs[window_start:window_end]
        hits = self.search(
            book_id,
            query,
            max_chapter=max_chapter,
            max_paragraph=max_paragraph,
            top_k=top_k,
        )
        previous = []
        if max_chapter > 0:
            with self._lock, self._connection() as connection:
                rows = connection.execute(
                    """SELECT chapter_index,title,content FROM chapters
                       WHERE book_id=? AND chapter_index BETWEEN ? AND ? ORDER BY chapter_index""",
                    (book_id, max(0, max_chapter - 2), max_chapter - 1),
                ).fetchall()
            for row in rows:
                pieces = _paragraphs(str(row["content"]), max_chars=900)
                digest = "\n".join((pieces[:2] + pieces[-1:]))[:1800]
                previous.append({"chapter_index": int(row["chapter_index"]), "title": row["title"], "digest": digest})
        return {
            "book": book,
            "chapter": {"chapter_index": chapter["chapter_index"], "title": chapter["title"]},
            "position": {"chapter_index": max_chapter, "paragraph_index": max_paragraph},
            "nearby": nearby,
            "previous_chapters": previous,
            "hits": hits,
        }

    def search(
        self,
        book_id: str,
        query: str,
        *,
        max_chapter: int,
        max_paragraph: int,
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        terms = []
        seen: set[str] = set()
        stop_terms = {"这个", "那个", "之前", "什么", "是谁", "哪里", "怎么", "发生", "刚才", "这里"}
        for raw_term in _WORD_RE.findall(str(query or "")):
            candidates = [raw_term]
            if re.fullmatch(r"[\u3400-\u9fff]+", raw_term) and len(raw_term) > 2:
                candidates.extend(
                    raw_term[index : index + size]
                    for size in (2, 3, 4)
                    for index in range(0, len(raw_term) - size + 1)
                )
            for term in candidates:
                normalized = term.casefold()
                if normalized in seen or normalized in stop_terms:
                    continue
                seen.add(normalized)
                terms.append(term)
                if len(terms) >= 10:
                    break
            if len(terms) >= 10:
                break
        rows: list[sqlite3.Row] = []
        with self._lock, self._connection() as connection:
            if terms:
                expression = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:10])
                try:
                    rows = connection.execute(
                        """SELECT f.chapter_index,f.paragraph_index,f.content,c.title,bm25(paragraph_fts) AS score
                           FROM paragraph_fts f JOIN chapters c
                             ON c.book_id=f.book_id AND c.chapter_index=CAST(f.chapter_index AS INTEGER)
                           WHERE paragraph_fts MATCH ? AND f.book_id=?
                             AND (CAST(f.chapter_index AS INTEGER) < ? OR
                                  (CAST(f.chapter_index AS INTEGER)=? AND CAST(f.paragraph_index AS INTEGER)<=?))
                           ORDER BY score LIMIT ?""",
                        (expression, str(book_id), int(max_chapter), int(max_chapter), int(max_paragraph), max(1, min(int(top_k), 20))),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows and terms:
                clauses = " OR ".join("p.content LIKE ?" for _item in terms[:10])
                rows = connection.execute(
                    f"""SELECT p.chapter_index,p.paragraph_index,p.content,c.title,0 AS score
                        FROM paragraphs p JOIN chapters c
                          ON c.book_id=p.book_id AND c.chapter_index=p.chapter_index
                        WHERE p.book_id=? AND (p.chapter_index < ? OR
                          (p.chapter_index=? AND p.paragraph_index<=?))
                          AND ({clauses})
                        ORDER BY p.chapter_index DESC,p.paragraph_index DESC LIMIT ?""",
                    (
                        str(book_id), int(max_chapter), int(max_chapter), int(max_paragraph),
                        *(f"%{term}%" for term in terms[:10]),
                        max(1, min(int(top_k), 20)),
                    ),
                ).fetchall()
            if not rows:
                rows = connection.execute(
                    """SELECT p.chapter_index,p.paragraph_index,p.content,c.title,0 AS score
                       FROM paragraphs p JOIN chapters c
                         ON c.book_id=p.book_id AND c.chapter_index=p.chapter_index
                       WHERE p.book_id=? AND (p.chapter_index < ? OR
                         (p.chapter_index=? AND p.paragraph_index<=?))
                       ORDER BY p.chapter_index DESC,p.paragraph_index DESC LIMIT ?""",
                    (str(book_id), int(max_chapter), int(max_chapter), int(max_paragraph), max(3, min(int(top_k), 20))),
                ).fetchall()
        return [
            {
                "chapter_index": int(row["chapter_index"]),
                "chapter_title": str(row["title"]),
                "paragraph_index": int(row["paragraph_index"]),
                "content": str(row["content"])[:1800],
            }
            for row in rows
        ]

    @staticmethod
    def format_context(context: dict[str, Any]) -> str:
        if not context:
            return ""
        book = context.get("book") or {}
        chapter = context.get("chapter") or {}
        position = context.get("position") or {}
        lines = [
            f"书名：{book.get('title') or '未命名小说'}",
            f"当前已读边界：第 {int(position.get('chapter_index', 0)) + 1} 章《{chapter.get('title') or ''}》第 {int(position.get('paragraph_index', 0)) + 1} 段。",
            "以下资料均已按当前已读边界过滤；不得声称知道或暗示边界之后的剧情。",
        ]
        previous = context.get("previous_chapters") or []
        if previous:
            lines.append("最近已读章节提要（抽取自原文，可能不完整）：")
            for item in previous:
                lines.append(f"- 第 {int(item.get('chapter_index', 0)) + 1} 章《{item.get('title') or ''}》：{item.get('digest') or ''}")
        nearby = context.get("nearby") or []
        if nearby:
            lines.append("当前位置附近原文：")
            for item in nearby:
                lines.append(f"- 第 {int(item.get('paragraph_index', 0)) + 1} 段：{item.get('content') or ''}")
        hits = context.get("hits") or []
        if hits:
            lines.append("与问题相关的已读原文证据：")
            for item in hits:
                lines.append(
                    f"- 第 {int(item.get('chapter_index', 0)) + 1} 章《{item.get('chapter_title') or ''}》"
                    f"第 {int(item.get('paragraph_index', 0)) + 1} 段：{item.get('content') or ''}"
                )
        return "\n".join(lines)[:18000]

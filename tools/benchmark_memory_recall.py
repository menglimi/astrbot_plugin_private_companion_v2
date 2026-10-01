"""Reproducible local memory/cache timing; no host, provider or user data."""

import argparse
import asyncio
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from statistics import median
from time import perf_counter
from threading import Timer
import unittest
from unittest.mock import patch
from uuid import uuid4

from companion_v2.memory.models import AtomRef
from companion_v2.memory.query import MemoryQuery
from companion_v2.memory.writer import MemoryWriter
from tests.memory_support import MemoryFixture


class BenchmarkFixture(MemoryFixture, unittest.TestCase):
    pass


async def measure(facts, seed_from=None):
    fixture = BenchmarkFixture()
    fixture.setUp()
    try:
        start = perf_counter()
        if seed_from is None:
            base = replace(fixture.proposed(), single_value=False, object="cobalt", representation="cobalt")
            with fixture.runtime.transaction():
                for number in range(facts - 1):
                    fixture.remember(replace(base, predicate="item-" + str(number)), key="item-" + str(number))
                target = fixture.remember(replace(base, predicate="destination", object="voyagerneedle", representation="voyagerneedle"), key="target")
        else:
            # Reuse this tool's synthetic owner store, never its search cache.
            # Only a temporary copy is queried; the supplied snapshot is read-only.
            fixture.runtime.close()
            with closing(sqlite3.connect(seed_from.resolve().as_uri() + "?mode=ro", uri=True)) as source, \
                    closing(sqlite3.connect(fixture.root / "companion-v2.sqlite3")) as target_db:
                source.backup(target_db)
            fixture.runtime = fixture.open_runtime()
            fixture.tasks, fixture.messages, fixture.delivery = fixture.components(fixture.runtime)
            fixture.memory = MemoryWriter(fixture.tasks)
            fixture.recall = MemoryQuery(fixture.memory)
            count = fixture.runtime.read_one("SELECT COUNT(*) n FROM memory_atoms", ())["n"]
            if count != facts:
                raise ValueError("seed fixture has a different fact count")
            row = fixture.runtime.read_one("SELECT atom_id, revision FROM memory_atoms WHERE json_extract(record_json, '$.proposal.object') = 'voyagerneedle'", ())
            if row is None:
                raise ValueError("seed fixture is missing this benchmark's target")
            target = AtomRef(row["atom_id"], row["revision"])
        setup_ms = (perf_counter() - start) * 1000
        print(json.dumps({"stage": "seeded", "facts": facts, "setup_ms": round(setup_ms, 3)}), flush=True)
        # Drive the internal cold projection in finite batches, outside any LLM
        # query budget. Each real query below still uses the normal owner checks.
        pages, startup_lag = [], []
        while True:
            beat = asyncio.create_task(asyncio.sleep(0))
            await asyncio.sleep(0)
            start = perf_counter()
            with fixture.runtime.read_snapshot():
                snapshot = fixture.recall.fact_index.advance(fixture.context, "personal")
            pages.append((perf_counter() - start) * 1000)
            await beat
            startup_lag.append((perf_counter() - start) * 1000)
            if snapshot["ready"]:
                break
        warm, reads, owner_rows = [], [], []
        session_id = "memory-benchmark-" + uuid4().hex
        fixture.recall.begin(fixture.context, session_id)
        def recall():
            return fixture.recall.query(fixture.context, session_id, query_intent="voyagerneedle")
        for _ in range(5):
            start = perf_counter()
            with patch.object(fixture.memory, "read", wraps=fixture.memory.read) as read, \
                    patch.object(fixture.runtime, "read_all", wraps=fixture.runtime.read_all) as bulk:
                result = recall().unwrap()
            warm.append((perf_counter() - start) * 1000)
            reads.append(read.call_count)
            owner_rows.append(sum("memory_atoms" in call.args[0] or "memory_changes" in call.args[0] for call in bulk.call_args_list))
            assert [item["atom_id"] for item in result["items"]] == [target.atom_id]
        reopens = []
        for _ in range(3):
            start = perf_counter()
            MemoryQuery(fixture.memory)
            reopens.append((perf_counter() - start) * 1000)
        # A real second SQLite connection owns the write slot for 350 ms.
        # The timer releases it even when synchronous lookup blocks the loop.
        with closing(sqlite3.connect(fixture.recall.index.path, check_same_thread=False)) as other:
            other.execute("BEGIN IMMEDIATE")
            timer = Timer(0.35, other.rollback)
            timer.start()
            try:
                start = perf_counter()
                result = recall()
                lock_ms = (perf_counter() - start) * 1000
            finally:
                timer.join(timeout=2)
                if timer.is_alive():
                    raise RuntimeError("lock fixture did not stop")
        return {"facts": facts, "fixture": "copied_synthetic_writer_fixture" if seed_from else "public_writer_single_transaction",
            "setup_ms": round(setup_ms, 3),
            "cold_pages": len(pages), "cold_total_ms": round(sum(pages), 3), "cold_max_page_ms": round(max(pages), 3),
            "cold_median_page_ms": round(median(pages), 3), "event_loop_max_delay_ms": round(max(startup_lag), 3),
            "warm_median_ms": round(median(warm), 3), "warm_max_ms": round(max(warm), 3),
            "warm_authoritative_reads": reads, "warm_owner_bulk_queries": owner_rows,
            "reopen_median_ms": round(median(reopens), 3), "warm_cache_lock_ms": round(lock_ms, 3),
            "lock_query_success": result.is_success}
    finally:
        fixture.doCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=int, default=10000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-from", type=Path, help="read-only snapshot generated from this tool's synthetic fixture")
    args = parser.parse_args()
    if not 1 <= args.facts <= 50000:
        parser.error("facts must be between 1 and 50000")
    result = asyncio.run(measure(args.facts, args.seed_from))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

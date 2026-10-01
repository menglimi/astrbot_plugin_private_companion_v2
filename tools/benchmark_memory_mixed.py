"""Synthetic source/experience/mixed recall; no host, model or external delivery."""

import argparse
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import statistics
import time
import unittest
from unittest.mock import patch

from companion_v2.memory.query import MemoryQuery
from companion_v2.memory.search import SearchIndex
from tests.memory_support import MemoryFixture


class Fixture(MemoryFixture, unittest.TestCase):
    def supervisor(self, runtime=None, registrations=None, limits=None):
        return super().supervisor(runtime, registrations, replace(limits or self.limits, retained_tasks=10000))


def benchmark(count, baseline_path=None):
    fixture = Fixture()
    fixture.setUp()
    try:
        evidence = fixture.evidence("shared-proof")
        created = time.perf_counter()
        batch = None
        for number in range(count):
            word = "voyager" if number == 0 else "background"
            batch = fixture.accept(fixture.event(f"{word}-{number}"), batch_id=batch if number % 32 else None)
            fixture.recall.experiences.save(fixture.context, view_id=f"view-{number:06}", expected_revision=0,
                title=word, statements=({"text": word, "evidence": (evidence,), "atoms": ()},)).unwrap()
        result = {"source_count": count + 1, "experience_count": count,
                  "seed_seconds": time.perf_counter() - created, "queries": {}}
        classes = {"optimized": MemoryQuery}
        if baseline_path:
            spec = importlib.util.spec_from_file_location("companion_v2.memory.benchmark_baseline_query", baseline_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            classes["baseline"] = module.MemoryQuery
        for label, query_type in classes.items():
            result["queries"][label] = {}
            for kind in ("sources", "experiences", "all"):
                query = query_type(fixture.memory)
                directory = fixture.runtime.data_root / (label + "-" + kind)
                directory.mkdir()
                query.index = SearchIndex(directory)
                if label == "optimized":
                    query.recall_index.index = query.index
                durations, pages, current = [], 0, None
                # Drive the same finite cache batches as the query path. Cold
                # build measurements do not borrow or enlarge a turn budget.
                if label == "optimized":
                    while not current or not current["ready"]:
                        with fixture.runtime.transaction():
                            start = time.perf_counter()
                            current = query.recall_index.advance(fixture.context, "personal", kind)
                            durations.append((time.perf_counter() - start) * 1000)
                            pages += 1
                samples, reads, bulk_rows = [], [], []
                original_read_all = fixture.runtime.read_all
                for sample in range(4):
                    session = f"{label}:{kind}:{sample}"
                    query.begin(fixture.context, session)
                    fetched = []
                    def tracked(sql, parameters):
                        rows = original_read_all(sql, parameters)
                        if any(name in sql for name in ("conversation_inputs", "memory_views", "memory_atoms", "memory_recall_changes")):
                            fetched.append(len(rows))
                        return rows
                    with patch.object(fixture.runtime, "read_all", side_effect=tracked), \
                            patch.object(query.access, "source", wraps=query.access.source) as source_reads, \
                            patch.object(query.experiences, "read", wraps=query.experiences.read) as view_reads:
                        start = time.perf_counter()
                        value = query.query(fixture.context, session, query_intent="voyager", kind=kind).unwrap()
                        samples.append((time.perf_counter() - start) * 1000)
                    if value["next_cursor"] or len(value["items"]) != (2 if kind == "all" else 1):
                        raise AssertionError("old target missing or unexpected unfinished search")
                    reads.append({"source": source_reads.call_count, "experience": view_reads.call_count})
                    bulk_rows.append(sum(fetched))
                result["queries"][label][kind] = {
                    "cold_batches": pages, "cold_ms": sum(durations) if durations else samples[0],
                    "max_batch_ms": max(durations) if durations else samples[0],
                    "hot_median_ms": statistics.median(samples[1:]),
                    "hot_samples_ms": samples[1:], "hot_owner_reads": reads[1:], "hot_bulk_rows": bulk_rows[1:],
                }
        return result
    finally:
        fixture.doCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objects", type=int, default=1000)
    parser.add_argument("--baseline-query", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if not 1 <= arguments.objects <= 10000:
        parser.error("objects must be in 1..10000")
    result = benchmark(arguments.objects, arguments.baseline_query)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

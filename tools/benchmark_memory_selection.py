"""Synthetic reflection selection with accumulated complete/held history; no I/O providers."""

import argparse
from contextlib import closing
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import statistics
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from companion_v2.execution.models import digest, encode, stamp
from companion_v2.memory.models import owner_key
from companion_v2.memory.reflection import MemoryReflection
from tests.test_memory_selection import SelectionFixture


class Fixture(SelectionFixture, unittest.TestCase):
    def supervisor(self, runtime=None, registrations=None, limits=None):
        return super().supervisor(runtime, registrations, replace(limits or self.limits, retained_tasks=10000))


def load_baseline(directory):
    modules = {}
    for name in ("reflection_recovery", "reflection"):
        spec = importlib.util.spec_from_file_location("companion_v2.memory.selection_baseline_" + name, directory / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    modules["reflection"].recovery = modules["reflection_recovery"]
    return modules["reflection"].MemoryReflection


def seed(fixture, sources, facts, history):
    fixture.seed(sources - 1)
    base = fixture.proposed()
    for number in range(facts):
        fixture.remember(replace(base, predicate="记录" + str(number), representation="private input source"), "fact-" + str(number))
    first = fixture.prepare("seed", maximum_sources=1)
    fixture.finish(first["batch_id"])
    template = fixture.manifest(first["batch_id"])
    with closing(fixture.recall.index._open()) as cache:
        rows = cache.execute("SELECT * FROM recall_documents ORDER BY json_extract(metadata_json, '$.source_id') LIMIT ?", (history,)).fetchall()
    with fixture.runtime.transaction() as db:
        db.execute("DELETE FROM memory_reflections WHERE batch_id = ?", (first["batch_id"],))
        for number, row in enumerate(rows):
            original = fixture.recall.objects.read(fixture.context, row)["evidence"]
            manifest = {**template, "evidence": [json.loads(encode(original))], "facts": [], "pending": []}
            identifier = "history-" + str(number)
            db.execute("INSERT INTO memory_reflections VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?)",
                (identifier, owner_key(fixture.context), digest(identifier), encode(fixture.context), encode(manifest),
                 "complete" if number < history * 3 // 4 else "prepared", encode({"items": {}, "sequence": template["memory_sequence"]}),
                 stamp(fixture.clock.now()), stamp(fixture.clock.now())))


def measure(fixture, reflection, label, sample, *, cold):
    durations, steps, source_reads, fact_reads, projections, scans = [], [], [], [], [], []
    row = None
    for step in range(10000):
        statements = []
        def trace(sql):
            if "select manifest_json from memory_reflections" in sql.lower():
                statements.append(sql)
        with fixture.runtime.transaction() as db, \
                patch.object(fixture.recall.access, "source", wraps=fixture.recall.access.source) as reads, \
                patch.object(fixture.memory, "read", wraps=fixture.memory.read) as facts, \
                patch.object(fixture.recall.objects, "project", wraps=fixture.recall.objects.project) as projected:
            db.set_trace_callback(trace)
            try:
                start = time.perf_counter()
                if row is None:
                    result = reflection.prepare(fixture.context, request_id=f"{label}:{sample}", maximum_sources=4, **fixture.window).unwrap()
                    row = reflection._row(fixture.context, result["batch_id"])
                else:
                    row = reflection.selection.advance(fixture.context, row)
                elapsed = (time.perf_counter() - start) * 1000
            finally:
                db.set_trace_callback(None)
        durations.append(elapsed)
        source_reads.append(reads.call_count)
        fact_reads.append(facts.call_count)
        projections.append(projected.call_count)
        scans.append(len(statements))
        steps.append(row["state"])
        if row["state"] != "selecting":
            break
    else:
        raise AssertionError("preparation did not converge")
    manifest = json.loads(row["manifest_json"])
    if row["state"] != "prepared" or len(manifest["evidence"]) != 4:
        raise AssertionError("expected four usable sources")
    with fixture.runtime.transaction() as db:
        db.execute("DELETE FROM memory_reflections WHERE batch_id = ?", (row["batch_id"],))
    return {"steps": len(steps), "states": steps, "total_ms": sum(durations), "max_step_ms": max(durations),
            "source_owner_reads": source_reads, "fact_owner_reads": fact_reads, "projected_objects": projections,
            "history_full_scan_statements": scans, "selected": len(manifest["evidence"]), "remaining": manifest["remaining_sources"],
            "deferred": manifest["deferred_sources"], "cold": cold}


def benchmark(sources, facts, history, baseline):
    fixture = Fixture()
    fixture.setUp()
    try:
        started = time.perf_counter()
        seed(fixture, sources, facts, history)
        result = {"sources": sources, "facts": facts, "history": history,
                  "complete_history": history * 3 // 4, "held_history": history - history * 3 // 4,
                  "seed_seconds": time.perf_counter() - started, "implementations": {}}
        classes = {"optimized": MemoryReflection}
        if baseline:
            classes["baseline"] = load_baseline(baseline)
        for label, reflection_type in classes.items():
            fixture.recall.index.clear()
            reflection = reflection_type(fixture.runtime)
            tasks = fixture.supervisor(registrations=fixture.registrations + reflection.registrations)
            reflection.attach(fixture.component, SimpleNamespace(runtime=fixture.runtime, tasks=tasks))
            cold = measure(fixture, reflection, label, 0, cold=True)
            samples = [measure(fixture, reflection, label, sample, cold=False) for sample in range(1, 4)]
            result["implementations"][label] = {"cold": cold, "hot_median_ms": statistics.median(v["total_ms"] for v in samples),
                                               "hot_samples": samples}
        return result
    finally:
        fixture.doCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=int, default=1000)
    parser.add_argument("--facts", type=int, default=128)
    parser.add_argument("--history", type=int, default=800)
    parser.add_argument("--baseline-memory", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    if not 5 <= options.sources <= 10000 or not 0 <= options.history <= options.sources - 4 or not 0 <= options.facts <= 10000:
        parser.error("sources must be 5..10000, history 0..sources-4, facts 0..10000")
    result = benchmark(options.sources, options.facts, options.history, options.baseline_memory)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Run the affected memory/host tests and validate real returned protocol objects.

Run with AstrBot's Python and its backend/app on PYTHONPATH. --contracts points
only to the reviewed design schema directory, never a V1 user data directory.
jsonschema/referencing are verification dependencies, not plugin dependencies.
"""

import argparse
from collections import Counter
from contextlib import ExitStack
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


TEST_MODULES = (
    "test_memory_subscriptions", "test_memory_stream_edges", "test_memory_pending_wire", "test_memory_stream_host",
    "test_memory_proposal_wire", "test_memory_commands_host", "test_memory_wire", "test_memory_provider_host",
    "test_provider_registry", "test_memory_writer", "test_memory_query", "test_memory_boundaries",
    "test_memory_incremental", "test_memory_reflection", "test_memory_recovery", "test_memory_recovery_queue",
    "test_memory_conversation", "test_memory_management", "test_host_application", "test_host_recovery",
    "test_storage_runtime", "test_astrbot_staging_host", "test_astrbot_staging_bootstrap", "test_astrbot_native", "test_isolation",
)


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def validators(directory):
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    from companion_v2.memory.stream_store import CONTRACT_FINGERPRINT

    schemas, hashes = {}, {}
    for path in sorted(directory.glob("*.schema.json")):
        content = path.read_bytes().replace(b"\r\n", b"\n")
        schema = json.loads(content.decode("utf-8"))
        Draft202012Validator.check_schema(schema)
        schemas[path.name.removesuffix(".schema.json")] = schema
        hashes[schema["$id"]] = hashlib.sha256(content).hexdigest()
    lines = "".join(key + "\t" + hashes[key] + "\n" for key in sorted(hashes))
    fingerprint = hashlib.sha256(lines.encode("utf-8")).hexdigest()
    if len(schemas) != 13 or fingerprint != CONTRACT_FINGERPRINT:
        raise ValueError("review contract schema set or fingerprint changed")
    registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas.values())
    return {name: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
            for name, schema in schemas.items()}


def instrument(stack, schemas, counts):
    from companion_v2.memory.proposal_wire import MemoryProposalWireV1
    from companion_v2.memory.wire import MemoryQueryWireV1
    from companion_v2.memory.wire_operations import MemoryOperationWireV1
    from companion_v2.memory.subscriptions import MemorySubscriptions, SubscriptionControl
    from companion_v2.memory.stream_consumer import MemoryReferenceConsumer

    def bind(cls, name, schema, select=lambda value: value):
        original = getattr(cls, name)
        @wraps(original)
        def checked(*args, **kwargs):
            result = original(*args, **kwargs)
            value = select(result)
            if value is not None:
                schemas[schema].validate(value)
                counts[schema] += 1
            return result
        stack.enter_context(patch.object(cls, name, checked))

    for cls, method in ((MemoryProposalWireV1, "handle"), (MemoryProposalWireV1, "resolve_pending"),
                        (MemoryOperationWireV1, "handle"), (MemoryQueryWireV1, "handle")):
        bind(cls, method, "memory-result")
    bind(SubscriptionControl, "handle", "memory-subscription-result")
    bind(MemorySubscriptions, "poll", "memory-change-batch", lambda result: result.unwrap()["batch"] if result.is_success else None)
    for method in ("stage_page", "apply_batch", "activate"):
        bind(MemoryReferenceConsumer, method, "memory-checkpoint", lambda result: result.unwrap() if result.is_success else None)
    bind(MemoryReferenceConsumer, "recovery_checkpoint", "memory-checkpoint",
         lambda result: result.unwrap()["checkpoint"] if result.is_success else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", required=True, type=Path, help="review contract schemas directory")
    parser.add_argument("--tests", nargs="+", default=TEST_MODULES, help="test module basenames; default is the affected branch suite")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix="companion-v2-memory-acceptance-") as root, ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"ASTRBOT_ROOT": root}))
        schemas, counts = validators(args.contracts), Counter()
        instrument(stack, schemas, counts)
        loaded = unittest.defaultTestLoader.loadTestsFromNames(["tests." + name for name in args.tests])
        unique = {case.id(): case for case in cases(loaded)}
        result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(unique.values()))
        print(json.dumps(dict(unique_tests=len(unique), tests_run=result.testsRun, skipped=len(result.skipped),
                              schema_instances=dict(sorted(counts.items())), passed=result.wasSuccessful()), ensure_ascii=False))
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

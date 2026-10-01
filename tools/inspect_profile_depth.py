"""Measure how deep one V2 profile's runtime state actually goes (read-only)."""

import sqlite3
import sys
from pathlib import Path


_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_DATA = _PLUGIN_ROOT.parents[1] / "plugin_data" / _PLUGIN_ROOT.name

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    _PLUGIN_DATA / "profiles" / "qq-v2-stream-20260926" / "runtime" / "companion-v2.sqlite3"
)


def main():
    connection = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("TABLES", len(tables))
    populated = []
    for name in tables:
        try:
            count = connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        except sqlite3.Error:
            continue
        if count:
            populated.append((name, count))
    print("POPULATED_TABLES", len(populated), "of", len(tables))
    for name, count in sorted(populated, key=lambda item: -item[1])[:20]:
        print("  ", name, count)
    print("MODEL_CALLS", [tuple(row) for row in connection.execute(
        "SELECT state, COUNT(*) FROM model_calls GROUP BY state")])
    print("TASKS_BY_KIND", [tuple(row) for row in connection.execute(
        "SELECT kind, state, COUNT(*) FROM execution_tasks GROUP BY kind, state")])
    print("BATCH_STATES", [tuple(row) for row in connection.execute(
        "SELECT state, COUNT(*) FROM conversation_batches GROUP BY state")])
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

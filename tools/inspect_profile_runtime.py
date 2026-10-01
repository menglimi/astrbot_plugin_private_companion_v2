"""Read-only snapshot of one V2 profile's runtime state (no writes, no host)."""

import json
import sqlite3
import sys
from pathlib import Path


_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_DATA = _PLUGIN_ROOT.parents[1] / "plugin_data" / _PLUGIN_ROOT.name

PROFILE = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    _PLUGIN_DATA / "profiles" / "qq-v2-stream-20260926"
)


def main():
    config = json.loads((PROFILE / "staging-config.json").read_text(encoding="utf-8"))
    print("PROFILE", PROFILE.name)
    print("CONFIG_KEYS", sorted(config))
    print("SCOPE", json.dumps(config.get("scope"), ensure_ascii=False))
    print("PERSONA", json.dumps(config.get("persona"), ensure_ascii=False))
    print("DELIVERY_MODE", config.get("delivery_mode"))
    print("HOST", json.dumps(config.get("host"), ensure_ascii=False))
    print("MODEL", json.dumps(config.get("model"), ensure_ascii=False))
    database = PROFILE / "runtime" / "companion-v2.sqlite3"
    if not database.exists():
        print("NO_DATABASE")
        return 0
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    def scalar(sql, *args):
        row = connection.execute(sql, args).fetchone()
        return None if row is None else row[0]

    version = scalar("SELECT value FROM runtime_metadata WHERE key = ?", "schema_version")
    print("SCHEMA_VERSION", version)
    print("BATCHES", scalar("SELECT COUNT(*) FROM conversation_batches"))
    print("LAST_BATCH_AT", scalar("SELECT MAX(created_at) FROM conversation_batches"))
    print("INPUTS", scalar("SELECT COUNT(*) FROM conversation_inputs"))
    print("PARTS", scalar("SELECT COUNT(*) FROM conversation_parts"))
    print("DELIVERED_PARTS", scalar("SELECT COUNT(*) FROM conversation_parts WHERE state = 'delivered'"))
    print("LAST_DELIVERED_AT", scalar("SELECT MAX(delivered_at) FROM conversation_sent_history"))
    print("TASKS", scalar("SELECT COUNT(*) FROM execution_tasks"))
    for row in connection.execute("SELECT state, COUNT(*) AS total FROM execution_tasks GROUP BY state ORDER BY total DESC"):
        print("TASK_STATE", row["state"], row["total"])
    print("FLOWS", scalar("SELECT COUNT(*) FROM conversation_flows"))
    for row in connection.execute("SELECT state, COUNT(*) AS total FROM conversation_flows GROUP BY state ORDER BY total DESC"):
        print("FLOW_STATE", row["state"], row["total"])
    print("MEMORY_ATOMS", scalar("SELECT COUNT(*) FROM memory_atoms"))
    print("MEMORY_LAST", scalar("SELECT MAX(created_at) FROM memory_atoms"))
    print("REFLECTIONS", scalar("SELECT COUNT(*) FROM memory_reflections"))
    print("REFLECTION_LAST", scalar("SELECT MAX(created_at) FROM memory_reflections"))
    print("PROACTIVE_CONTACTS", scalar("SELECT COUNT(*) FROM proactive_contacts"))
    print("PROACTIVE_LAST", scalar("SELECT MAX(created_at) FROM proactive_contacts"))
    print("MODEL_CALLS", scalar("SELECT COUNT(*) FROM model_calls"))
    print("MODEL_LAST", scalar("SELECT MAX(created_at) FROM model_calls"))
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

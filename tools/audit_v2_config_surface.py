"""Which configuration groups a dashboard route can actually read and write.

A group is only operator-editable from the cottage when some host API exposes it
through the configuration service. Everything else is visible only through the
AstrBot plugin form. This prints that mapping next to each registered group.

Usage: python tools/audit_v2_config_surface.py
"""

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "astrbot_host"
# group_id -> the management/service class that owns its read-write contract.
CONSUMERS = {
    "conversation.presentation": "ReplyManagement",
    "conversation.perception": "PerceptionManagement",
    "proactive.contact": "ContactManagement",
    "role.state": "StateManagement",
    "role.life": "RoleLifeManagement",
    "role.growth": "RoleGrowthManagement",
    "memory": "MemoryManagement",
    "person": "AcquaintanceManagement",
    "expression.learning": "ReplyManagement (expression_*)",
    "model.budget": "BudgetLedger",
}
ROUTES = {
    "conversation.presentation": "/reply",
    "conversation.perception": "/perception + /perception-native",
    "proactive.contact": "/state/command (contact.configure) + /perception-native (news)",
    "role.state": "/state/command (configure) + /perception-native (environment)",
    "role.life": "/life/command",
    "role.growth": "/growth/command",
    "memory": "/memory/settings/command",
    "person": "/acquaintance (read only)",
    "expression.learning": "/reply/expression/configure",
    "model.budget": "—",
}


def registered_groups():
    """Read the group ids from the modules that declare them rather than guessing."""
    groups = set()
    for path in ROOT.joinpath("companion_v2").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r'^GROUP\s*=\s*"([^"]+)"', text, re.MULTILINE):
            groups.add((match.group(1), path.relative_to(ROOT).as_posix()))
    return groups


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    groups = registered_groups()
    by_id = {}
    for group, path in groups:
        by_id.setdefault(group, []).append(path)
    for group in sorted(by_id):
        route = ROUTES.get(group, "—（宿主表单以外没有写入合同）")
        consumer = CONSUMERS.get(group, "—")
        print(f"{group}\t{consumer}\t{route}\t{','.join(sorted(by_id[group]))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

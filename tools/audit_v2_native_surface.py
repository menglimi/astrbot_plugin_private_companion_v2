"""Dump every registered configuration group and task kind the V2 app assembles.

Read-only introspection for the gap audit: it builds the same FieldRegistry the
host builds and prints one line per group with its field count and layer set, so
a documentation table can be checked against the real registry instead of prose.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from companion_v2.conversation.media.quota import configuration_fields as quota_fields
from companion_v2.conversation.media.review import configuration_fields as review_fields
from companion_v2.conversation.perception_settings import configuration_fields as perception_fields
from companion_v2.conversation.reply_settings import configuration_fields as reply_fields
from companion_v2.conversation.segmentation import SegmentationPolicy
from companion_v2.expression.configuration import configuration_fields as expression_fields
from companion_v2.expression.reaction_configuration import configuration_fields as reaction_fields
from companion_v2.conversation.busy_gate import configuration_fields as busy_gate_fields
from companion_v2.model_gateway.budget import configuration_fields as budget_fields
from companion_v2.memory.configuration import extend_registry
from companion_v2.memory.models import MemoryPolicy
from companion_v2.memory.person.configuration import configuration_fields as person_fields
from companion_v2.model_gateway.models import Lane, ModelTaskProfile
from companion_v2.model_gateway.routing import configuration_fields as model_fields
from companion_v2.proactive.configuration import configuration_fields as contact_fields, with_contact_fields
from companion_v2.role_work.growth.configuration import configuration_fields as growth_fields
from companion_v2.role_work.life.configuration import configuration_fields as life_fields
from companion_v2.role_work.state.configuration import configuration_fields as state_fields
from companion_v2.configuration.registry import FieldRegistry


def build():
    # One representative task profile is enough: every profile contributes the
    # same four field shapes, and the audit only counts groups.
    profiles = (ModelTaskProfile("conversation.reply", Lane.FOREGROUND, "default", "audit"),)
    registry = FieldRegistry(version="audit.v1", fields=model_fields(profiles))
    registry = extend_registry(registry, MemoryPolicy())
    extra = tuple(field for field in (
        *life_fields(), *growth_fields(), *state_fields(),
        *reply_fields(SegmentationPolicy(), False, 0.0),
        *perception_fields(), *person_fields(), *quota_fields(), *review_fields(),
        *expression_fields(), *reaction_fields(), *busy_gate_fields(), *budget_fields(),
    ) if field.field_id not in registry.fields)
    registry = FieldRegistry(version="audit.v1", fields=tuple(registry.fields.values()) + extra)
    return with_contact_fields(registry)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    registry = build()
    print(f"TOTAL_GROUPS\t{len(registry.groups)}")
    print(f"TOTAL_FIELDS\t{len(registry.fields)}")
    for group in sorted(registry.groups):
        fields = registry.groups[group]
        layers = len(fields[0].layers)
        print(f"GROUP\t{group}\t{len(fields)}\tlayers={layers}\towner={fields[0].owner_id}")
    if "--fields" in sys.argv:
        for group in sorted(registry.groups):
            names = [field.field_id.removeprefix(group + ".") for field in registry.groups[group]]
            print(f"FIELDS\t{group}\t{','.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

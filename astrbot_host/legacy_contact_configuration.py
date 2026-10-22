"""Add verified private contact overrides to the reviewed upgrade plan."""

from dataclasses import replace

from companion_v2.foundation.refs import ScopeKind
from companion_v2.legacy.migration import ConfigIntent
from companion_v2.legacy.proactive_configuration import (
    PRIVATE_RELATIONSHIP, PRIVATE_WINDOW, private_contact_configuration,
)


def append_private_contact_plan(controller, session, migration, plan, configuration_scope):
    if configuration_scope not in ("all", "plugin", "proactive"):
        return plan
    context = session.profile.target
    if context.scope.kind is not ScopeKind.PRIVATE:
        return plan
    settings = getattr(controller, "settings", None)
    mappings = getattr(settings, "personas", ())
    matching = [item.persona_id for item in mappings
                if item.bot_id == context.scope.bot_id
                and item.role_id == context.role_binding.role.subject_id]
    persona_id = matching[0] if len(set(matching)) == 1 else ""
    private = private_contact_configuration(migration.v1_root, migration._configuration() or {},
        persona_id=persona_id, platform_id=context.scope.platform,
        account_id=context.scope.account_id, participant_id=context.actor.principal.native_account_id)
    intents = list(plan.intents)
    for kind, names in ((PRIVATE_RELATIONSHIP, set(private.changes) - {"max_contacts_24h"}),
                        (PRIVATE_WINDOW, {"max_contacts_24h"} & set(private.changes))):
        if not names:
            continue
        intents.append(ConfigIntent(scope="proactive.contact", group_id="proactive.contact",
            changes={name: private.changes[name] for name in sorted(names)},
            source_id="private.core_profiles.users", target_kind=kind,
            confidence={name: "high" for name in names},
            sources={name: private.sources[name] for name in names}))
    return replace(plan, intents=tuple(intents), differences=plan.differences + private.differences)

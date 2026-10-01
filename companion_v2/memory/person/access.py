"""Stable per-person ownership and trusted platform-account resolution.

The card owner keeps the installation, the bot/account route and the role, so
every companion holds its own acquaintance with the same human subject. The
human subject itself is installation-scoped, which is what makes one person the
same person across groups and private chat.
"""

import json

from companion_v2.execution.models import TaskError, digest
from companion_v2.foundation.refs import SubjectKind


OWNER = "memory.person"


def person_owner_key(installation_id, platform, bot_id, account_id, subject_id, role_id):
    return digest(["memory.person.v1", installation_id, platform, bot_id,
                   account_id, subject_id, role_id])


def owner_key(context):
    scope = context.scope
    return person_owner_key(scope.installation_id, scope.platform, scope.bot_id, scope.account_id,
                            context.actor.subject.subject_id, context.role_binding.role.subject_id)


def owner_for_subject(context, subject_id):
    scope = context.scope
    return person_owner_key(scope.installation_id, scope.platform, scope.bot_id, scope.account_id,
                            subject_id, context.role_binding.role.subject_id)


def card_id(owner):
    return "person-card-" + digest(owner)


def resolve_subject(runtime, context, speaker_id):
    """Resolve a native account to its installation human subject through the
    trusted binding table. Bindings exist only for accounts the host has
    authenticated, so an unknown number can never fabricate a card owner."""
    rows = runtime.read_all(
        """SELECT payload_json FROM identity_bindings
           WHERE installation_id = ? AND host_id = ? AND platform = ? AND native_account_id = ?
             AND bot_id = ? AND account_id = ? ORDER BY revision DESC""",
        (context.scope.installation_id, context.actor.principal.host_id, context.scope.platform,
         speaker_id, context.scope.bot_id, context.scope.account_id))
    for row in rows:
        subject = json.loads(row["payload_json"]).get("subject") or {}
        if (subject.get("kind") == SubjectKind.HUMAN.value
                and subject.get("installation_id") == context.scope.installation_id):
            return subject["subject_id"]
    raise TaskError("acquaintance_member_unknown",
                    "this account has no authenticated binding in this installation")

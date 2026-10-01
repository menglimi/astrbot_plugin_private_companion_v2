"""An explicit collective audience, distinct from the current human speaker."""

import hashlib
import json
from companion_v2.foundation.refs import AudienceRef, ScopeKind, SubjectKind, SubjectRef


def group_audience(scope, speaker):
    if (scope.kind is not ScopeKind.GROUP or not scope.is_resolved
            or speaker.kind is not SubjectKind.HUMAN or speaker.installation_id != scope.installation_id):
        raise ValueError("a group audience requires a resolved group and its human speaker")
    identity = json.dumps([scope.platform, scope.account_id, scope.bot_id, scope.native_scope_id],
                          ensure_ascii=True, separators=(",", ":"))
    group = SubjectRef(scope.installation_id, SubjectKind.GROUP,
                       "conversation-group:" + hashlib.sha256(identity.encode("utf-8")).hexdigest())
    # This collective recipient does not claim an exhaustive or static member list.
    return AudienceRef(scope, (speaker, group))

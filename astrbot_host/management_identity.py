"""Map a host-authenticated Dashboard administrator to a separate V2 human identity."""

from companion_v2.execution.models import TaskError, digest, require
from companion_v2.foundation.refs import SubjectKind, SubjectRef
from companion_v2.identity_policy.models import AuthenticatedHostPrincipal, AuthorizationTier
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.repository import PersistentIdentityDirectory


def dashboard_operator(runtime, username, *, at):
    # username must come from astrbot.api.web.request, never a query/body/header claim.
    if (type(username) is not str or not username.strip() or username != username.strip()
            or len(username) > 128 or username.startswith("api_key:")):
        raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard as an administrator")
    identifier = "dashboard:" + digest([runtime.installation_id, username])
    principal = AuthenticatedHostPrincipal(runtime.installation_id, "astrbot-dashboard",
                                            "dashboard", username)
    identities = PersistentIdentityDirectory(runtime)
    with runtime.transaction():
        resolved = identities.resolve_authenticated(principal, observed_at=at)
        if resolved.failure is not None and resolved.failure.code == "unbound_identity":
            subject = SubjectRef(runtime.installation_id, SubjectKind.HUMAN, identifier)
            identities.bind(binding_id=identifier, principal=principal, subject=subject,
                valid_from=at, expected_revision=identities.revision)
            policy = ObjectAccessPolicy(runtime)
            policy.set_tier(subject, AuthorizationTier.CORE, expected_revision=policy.revision, observed_at=at)
            resolved = identities.resolve_authenticated(principal, observed_at=at)
        # A known revoked binding or downgraded tier is never silently restored.
        return require(resolved)

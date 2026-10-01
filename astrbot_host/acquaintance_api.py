"""Dashboard directory for acquaintance cards and their per-capability authorization.

The directory spans every configured target of the loaded profile. It is
navigation data for the relations-and-permissions page: it grants no delivery
authorization, exposes no private memory body and never mutates cards.

The authorization routes beside it are the operator's one place to see and change
what *one private participant* is allowed to do. What they may change is decided
by ``PersonAuthorizationManagement`` from the grant id itself: a grant the loaded
profile document re-issues on every load is reported with its real state and is
refused here, naming where it is changed instead. Refusing is not a limitation we
can lift by trying harder -- revoking such a grant is undone by the next
bootstrap, so a page that offered the button would be lying.
"""

from __future__ import annotations

import json

from astrbot.api.web import request

from companion_v2.execution.models import TaskError, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import ScopeKind, ScopeRef
from companion_v2.identity_policy.management import (
    PAGE_MANAGED_CAPABILITIES,
    PersonAuthorizationManagement,
)
from companion_v2.identity_policy.object_access import ObjectAccessPolicy
from companion_v2.identity_policy.personas import ConversationRoute
from companion_v2.memory.person.admin_names import PersonAcquaintanceNameManagement
from companion_v2.memory.person.management import PersonAcquaintanceDirectory

from .management_identity import dashboard_operator


PREFIX = "/astrbot_plugin_private_companion_v2/acquaintance"
AUTHORIZATION_PATH = PREFIX + "/authorization"
ADMIN_NAME_PATH = PREFIX + "/admin-name"
MAX_AUTHORIZATION_BODY = 8192


def _configured_windows(settings):
    """The private targets this profile manages, keyed by their routing tuple.

    A group target carries a ``group_id`` and is deliberately absent: this page
    manages what one person may do, and a group is not a person.
    """
    if not hasattr(settings, "all_targets"):
        return [{"key": (settings.platform_id, settings.account_id, settings.participant_id)}]
    return [{"key": (target.platform_id, target.account_id, target.participant_id)}
            for target in settings.all_targets if not getattr(target, "group_id", None)]


def _authorization_participants(runtime, settings):
    """One entry per configured private person: their subject and their window.

    Both come from the registered conversation route rather than from settings.
    The settings name a participant as a bare platform account ("200"); the whole
    installation addresses them as a subject ("onebot-user:200"), and a grant's
    scope carries the conversation and session the host opened. Deriving either
    one here would be a second, silently divergent naming of the same person --
    the grant written against it would not be the one the reply path checks.
    """
    wanted = {entry["key"] for entry in _configured_windows(settings)}
    participants = []
    for row in runtime.read_all("SELECT record_json FROM conversation_routes", ()):
        route = ConversationRoute.restore(json.loads(row["record_json"]))
        if route.scene_kind is not ScopeKind.PRIVATE or route.user is None or not route.scope.is_resolved:
            continue
        scope = route.scope
        if (scope.platform, scope.account_id, scope.native_scope_id) not in wanted:
            continue
        participants.append({"target": None, "subject_id": route.user.subject_id,
                             "subject": route.user, "scope": scope})
    return participants


def _directory_routes(settings):
    routes, groups = [], []
    if hasattr(settings, "all_targets"):
        for target in settings.all_targets:
            roles = [persona.role_id for persona in settings.personas if persona.bot_id == target.bot_id]
            routes.extend({"platform": target.platform_id, "bot_id": target.bot_id,
                           "account_id": target.account_id, "role_id": role_id} for role_id in roles)
            if getattr(target, "group_id", None):
                groups.append({"group_id": target.group_id, "bot_id": target.bot_id,
                               "account_id": target.account_id, "member_count": 0, "msg_count": 0})
    else:
        routes.append({"platform": settings.platform_id, "bot_id": settings.bot_id,
                       "account_id": settings.account_id, "role_id": settings.role_id})
    return routes, groups


class AcquaintanceWebAPI:
    def __init__(self, controller):
        self.controller = controller

    def routes(self):
        return [(PREFIX, self.directory, ["GET"], "Read the Companion V2 acquaintance directory"),
                (AUTHORIZATION_PATH, self.authorization, ["GET"],
                 "Read one person's capability authorization"),
                (AUTHORIZATION_PATH, self.authorize, ["POST"],
                 "Switch one page-managed capability for one person"),
                (ADMIN_NAME_PATH, self.set_admin_name, ["POST"],
                 "Set a directory person's administrator-assigned display name")]

    async def _operator(self):
        """The signed-in-operator, loaded-profile gate both routes must pass.

        Identity comes first on purpose: who is asking is knowable before what
        they asked for, and an unauthenticated caller must not get a different
        answer by varying the request shape.
        """
        controller = self.controller
        username = request.username
        if type(username) is not str or not username.strip() or username.startswith("api_key:"):
            raise TaskError("dashboard_identity_required", "sign in to the AstrBot Dashboard")
        if controller._terminated:
            raise TaskError("staging_host_terminated", "the plugin has stopped")
        if controller.runtime is None or controller.settings is None:
            raise TaskError("staging_not_initialized", "load the V2 profile before reading the directory")
        operator = dashboard_operator(controller.runtime, username, at=controller.now())
        require(ObjectAccessPolicy(controller.runtime).feature_access(operator,
            scope=ScopeRef(controller.runtime.installation_id, "companion", ScopeKind.SYSTEM,
                           "page.management"),
            action="memory.manage", observed_at=controller.now()))
        return username, operator

    def _management(self):
        controller = self.controller
        return PersonAuthorizationManagement(controller.runtime,
            participants=_authorization_participants(controller.runtime, controller.settings))

    @staticmethod
    def _query(allowed, required=()):
        query = request.query
        if (set(query.keys()) - set(allowed) or set(required) - set(query.keys())
                or any(len(query.getlist(key)) != 1 for key in query.keys())):
            raise TaskError("acquaintance_request_invalid", "the directory does not accept these query fields")
        return {key: query.get(key) for key in allowed if key in query}

    async def directory(self):
        from .web_api import outcome_response
        controller = self.controller
        try:
            if request.query:
                raise TaskError("acquaintance_request_invalid", "the directory does not accept query overrides")
            async with controller._control_lock:
                username, _ = await self._operator()
                routes, groups = _directory_routes(controller.settings)
                result = PersonAcquaintanceDirectory(controller.runtime).directory(routes)
                members = {}
                for person in result["persons"]:
                    for group_id, entry in person["groups"].items():
                        members.setdefault(group_id, []).append(person)
                for group in groups:
                    for person in members.get(group["group_id"], ()):
                        group["member_count"] += 1
                        group["msg_count"] += person["groups"][group["group_id"]]["msg_count"]
                return outcome_response(Outcome.success({
                    "installation_id": controller.runtime.installation_id,
                    "profile_id": getattr(controller, "target_id", None) or controller.settings.profile_id,
                    "operator_name": username, "persons": result["persons"],
                    "groups": groups, "counts": result["counts"],
                    # The page must not keep its own copy of which capabilities this
                    # page owns: a second list would drift and start offering a
                    # control for a capability that cannot be changed here.
                    "page_managed_capabilities": list(PAGE_MANAGED_CAPABILITIES)}))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))

    async def authorization(self):
        """Read the real state of every capability one person holds."""
        from .web_api import outcome_response
        controller = self.controller
        try:
            async with controller._control_lock:
                _, operator = await self._operator()
                query = self._query(("subject_id",), required=("subject_id",))
                manager = self._management()
                return outcome_response(manager.status(operator, query["subject_id"],
                                                       observed_at=controller.now()))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))

    async def authorize(self):
        """Switch one page-managed capability, as one ledgered operation."""
        from .web_api import outcome_response
        controller = self.controller
        try:
            raw = await request.body()
            if len(raw) > MAX_AUTHORIZATION_BODY or request.query:
                raise TaskError("acquaintance_request_invalid", "the authorization command requires one bounded JSON body")

            def unique(pairs):
                values = {}
                for key, value in pairs:
                    if key in values:
                        raise TaskError("acquaintance_request_invalid", "the authorization command repeats a field")
                    values[key] = value
                return values

            command = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
            if type(command) is not dict:
                raise TaskError("authorization_command_invalid", "an explicit authorization command is required")
            async with controller._control_lock:
                _, operator = await self._operator()
                manager = self._management()
                result = manager.configure(operator, command, observed_at=controller.now())
                if result.is_success and not result.unwrap()["replayed"]:
                    # Every later request re-reads the current rows, so no in-memory
                    # cache has to be invalidated here; the session only needs to know
                    # that authority moved so an already-assembled turn rechecks it.
                    session = (None if controller._terminated
                               else controller.session or controller.last_session)
                    if session is not None:
                        session.application.notify()
                return outcome_response(result)
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return outcome_response(Outcome.failed("authorization_command_invalid",
                                                   "the authorization command is not valid JSON"))

    async def set_admin_name(self):
        """Set or clear a person's preferred name within one authorized role route."""
        from .web_api import outcome_response
        controller = self.controller
        try:
            raw = await request.body()
            if len(raw) > MAX_AUTHORIZATION_BODY or request.query:
                raise TaskError("acquaintance_request_invalid", "the name command requires one bounded JSON body")

            def unique(pairs):
                values = {}
                for key, value in pairs:
                    if key in values:
                        raise TaskError("acquaintance_request_invalid", "the name command repeats a field")
                    values[key] = value
                return values

            command = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
            required = {"operation_key", "subject_id", "platform", "bot_id", "account_id", "role_id",
                        "native_account_id", "admin_nickname", "expected_revision"}
            if (type(command) is not dict or set(command) != required
                    or type(command.get("expected_revision")) is not int
                    or type(command.get("admin_nickname")) is not str):
                raise TaskError("person_nickname_command_invalid", "the name command does not match its contract")
            async with controller._control_lock:
                _, operator = await self._operator()
                routes, _ = _directory_routes(controller.settings)
                manager = PersonAcquaintanceNameManagement(controller.runtime)
                return outcome_response(manager.set_nickname(operator, routes=routes, observed_at=controller.now(),
                    subject_id=command["subject_id"], platform=command["platform"], bot_id=command["bot_id"],
                    account_id=command["account_id"], role_id=command["role_id"],
                    native_account_id=command["native_account_id"], nickname=command["admin_nickname"],
                    expected_revision=command["expected_revision"], operation_key=command["operation_key"]))
        except TaskError as error:
            return outcome_response(Outcome.failed(error.code, str(error)))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return outcome_response(Outcome.failed("person_nickname_command_invalid",
                                                   "the name command is not valid JSON"))

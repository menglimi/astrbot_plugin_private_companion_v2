"""Build V2's native Content extension with invocation-scoped host services.

Only the V2 consumer resolves identities and checks current public permissions.
These ports accept ordinary JSON/callables and never import the host's core.
"""

from __future__ import annotations

import asyncio
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .governance import ContentGovernance
from .models import AccessRequest, ContentError, JsonObject, WorkOwner, canonical, digest, source_union
from .provider import NativeContentProvider, ResolvedTarget
from .repository import ContentRepository
from .service import ContentService


def _checked(callback: Callable, *args) -> None:
    if not callable(callback):
        raise ContentError("host_service_required")
    result = callback(*args)
    if result is not None:
        if inspect.iscoroutine(result):
            result.close()
        raise ContentError("synchronous_host_service_required")


@dataclass
class _InvocationBinding:
    request_hash: str
    target: ResolvedTarget
    check_access: Callable[[dict], None]
    active: bool = True
    # Host-side writing bounds and the fixed version an extending draft must answer.
    # They are context, not authority: the host already validated both.
    authoring: dict | None = None
    continuation: dict | None = None


class InvocationAccess:
    def __init__(self) -> None:
        self.current: ContextVar[_InvocationBinding | None] = ContextVar("content_invocation", default=None)

    def binding(self, request: dict) -> _InvocationBinding:
        current = self.current.get()
        if current is None or not current.active:
            raise ContentError("content_host_context_required")
        if current.request_hash != digest(canonical(request)):
            raise ContentError("content_host_context_mismatch")
        return current

    def resolve(self, request: dict) -> ResolvedTarget:
        return self.binding(request).target

    def authoring(self, request: dict) -> dict | None:
        """The host's writing bounds for this invocation, when the host sent any."""
        return self.binding(request).authoring

    def continuation(self, request: dict) -> dict | None:
        """The fixed version an extending draft must answer, when this is one."""
        return self.binding(request).continuation

    def check(self, access: AccessRequest) -> None:
        binding = self.binding(access.origin.request.value())
        if (access.owner != binding.target.owner
                or access.contributor is not None and access.contributor != binding.target.contributor):
            raise ContentError("content_host_target_mismatch")
        _checked(binding.check_access, dict(
            action=access.action, owner=access.owner.value(), origin=access.origin.value(),
            work_id=access.work_id,
            stored_audience=access.stored_audience.value() if access.stored_audience else None,
            sources=[source.value() for source in access.sources],
            contributor=access.contributor.value() if access.contributor else None,
        ))


class HostedContentProvider(NativeContentProvider):
    def __init__(self, service: ContentService, *, access: InvocationAccess,
                 live: Callable[[], None], package_version: str) -> None:
        self.access = access
        self.host_live = live
        self.governance = ContentGovernance(service.repository.path)
        super().__init__(service, resolve=access.resolve, package_version=package_version)

    def _live(self) -> None:
        super()._live()
        _checked(self.host_live)

    @contextmanager
    def bind_content_context(self, request: dict, *, target: dict, check_access: Callable,
                             authoring: dict | None = None, continuation: dict | None = None):
        """Bind one authorized Content operation.

        ``authoring`` carries the host's writing bounds (switch, direction, character
        ceiling, candidate ceiling) and ``continuation`` the fixed version an extending
        draft must answer. Both are optional: a host that sends neither keeps the plain
        contract, and older V2 builds stay compatible.
        """
        value, _, _ = self._request(request)
        resolved = JsonObject.capture(target).value()
        if (set(resolved) != {"schema", "owner", "contributor", "sources"}
                or resolved["schema"] != "content.host-context.v1"
                or type(resolved["sources"]) is not list or not callable(check_access)):
            raise ContentError("invalid_content_host_context")
        try:
            owner = WorkOwner(**resolved["owner"])
            context = value["context"]
            role = context["role_binding"]["role"]
            scope = context["audience"]["scope"]
            if (context["actor"]["subject"]["installation_id"] != owner.installation_id
                    or role["installation_id"] != owner.installation_id or role["kind"] != "bot"
                    or role["subject_id"] != owner.role_id
                    or scope["installation_id"] != owner.installation_id or scope["bot_id"] != owner.bot_id
                    or context["role_binding"]["scope"] != scope):
                raise ContentError("content_host_target_mismatch")
            resolved_target = ResolvedTarget(owner, JsonObject.capture(resolved["contributor"]),
                                            source_union(tuple(JsonObject.capture(source) for source in resolved["sources"])))
        except (KeyError, TypeError) as exc:
            raise ContentError("invalid_content_host_context") from exc
        binding = _InvocationBinding(digest(canonical(value)), resolved_target, check_access,
                                     authoring=authoring, continuation=continuation)
        token = self.access.current.set(binding)
        try:
            yield self
        finally:
            binding.active = False
            self.access.current.reset(token)

    def _control_guard(self, before_dispatch):
        def guard():
            self._live()
            _checked(before_dispatch)
        return guard

    def content_state(self, request: dict, *, before_dispatch) -> dict:
        return self.governance.state(request, self._control_guard(before_dispatch))

    def content_events(self, request: dict, *, before_dispatch) -> dict:
        return self.governance.events(request, self._control_guard(before_dispatch))


def build_provider(data_root: Path, *, version: str, live: Callable[[], None]) -> HostedContentProvider:
    _checked(live)
    repository = ContentRepository(data_root)
    try:
        access = InvocationAccess()
        provider = HostedContentProvider(ContentService(repository, access),
                                         access=access, live=live, package_version=version)
        _checked(live)
        return provider
    except BaseException:
        repository.close()
        raise


async def open_provider(data_root: Path, *, version: str, live: Callable[[], None]) -> HostedContentProvider:
    """Settle construction even if unload races with the SQLite open worker."""
    worker = asyncio.create_task(asyncio.to_thread(build_provider, data_root, version=version, live=live))
    try:
        provider = await asyncio.shield(worker)
    except asyncio.CancelledError:
        settlement = asyncio.gather(worker, return_exceptions=True)
        while True:
            try:
                result = (await asyncio.shield(settlement))[0]
                break
            except asyncio.CancelledError:
                continue
        if isinstance(result, HostedContentProvider):
            await result.close()
        raise
    try:
        _checked(live)
    except BaseException:
        await provider.close()
        raise
    return provider

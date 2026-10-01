"""V2 native execution through pinned AstrBot ports, JSON and verified bytes."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timezone
import inspect
import json
from types import MappingProxyType
from typing import Callable, Mapping

from companion_v2.adapters.astrbot.tools import AstrBotToolPort, map_tools
from companion_v2.capabilities.native import invocation_request, json_document, parse_result
from companion_v2.capabilities.native_reads import READ_ACTIONS, NativeReadConsumer
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.external_tools import ExternalToolResponse
from companion_v2.execution.models import TaskError, digest, encode, require
from companion_v2.foundation.outcome import Outcome
from companion_v2.foundation.refs import SourceRef, VersionRef
from companion_v2.sources.models import GovernanceState, SourceRecord

from .discovery import discover
from .images import IMAGE_ACTIONS, ImageReferenceLease, image_result_handler
from .image_settings import read_image_settings
from .content import ACTIONS as CONTENT_ACTIONS, ContentConsumer
from .screens import ACTION as SCREEN_ACTION, ScreenAdopter
from .reality_camera import ACTION as REALITY_CAMERA_ACTION, RealityCameraConsumer, RealityCameraGuard


TOGETHER_CREATE_ACTION = "together.room.create"


def together_execution_binding(settings):
    voice = settings.voice_reply_policy
    return {"model_provider_id": settings.provider_id,
            "tts_provider_id": voice.provider_for_language(),
            "tts_language": voice.language,
            "tts_timeout_seconds": voice.timeout_seconds}


class NativeExtensionRegistry(AstrBotToolPort):
    """Discovery never mutates storage; execution borrows the original task fence."""

    def __init__(self, context, *, result_handlers: Mapping[str, Callable] | None = None, now=None,
                 together_execution=None, image_settings_path=None):
        self.context = context
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.together_execution = dict(together_execution or {})
        self._default_handlers = result_handlers is None
        if result_handlers is None:
            result_handlers = {action: lambda invocation, result: image_result_handler(
                invocation, result, observed_at=self.now()) for action in IMAGE_ACTIONS}
            # Read-only providers (Reality, Live) have no artifact to adopt, but their
            # results still carry domain obligations: no credential may reach a model,
            # and a live cursor must advance instead of replaying delivered events.
            reader = NativeReadConsumer(self)
            result_handlers.update({action: reader.adopt for action in READ_ACTIONS})
            camera_reader = RealityCameraConsumer(self)
            result_handlers[REALITY_CAMERA_ACTION] = camera_reader.adopt
        self.result_handlers = MappingProxyType(dict(result_handlers))
        self.application = self.runtime = self.role_guard = self.persona_guard = None
        self.content = None
        self.screen = None
        self.camera = None
        self._entries, self.issues = discover(context)
        self._blocked_extension_ids = frozenset()
        self.image_settings_path = image_settings_path
        self.image_enabled = read_image_settings(image_settings_path)
        self._enforcing_image_settings = False
        self._closed = False

    def declarations(self):
        return tuple(entry[0] for entry in self._entries.values()
                     if entry[0].descriptor.package.extension_id not in self._blocked_extension_ids) if not self._closed else ()

    def current_declaration(self, host_tool_id):
        entry = self._entries.get(host_tool_id)
        if (self._closed or entry is None
                or entry[0].descriptor.package.extension_id in self._blocked_extension_ids
                or not entry[1].current(self.context)):
            return None
        if (self._enforcing_image_settings and entry[0].descriptor.tool.action in IMAGE_ACTIONS
                and not self.image_enabled[entry[0].descriptor.tool.action]):
            return None
        return entry[0]

    def image_extension_api(self):
        "The current image extension's management API, or None when absent or stale."
        if self._closed:
            return None
        for declaration, lease in self._entries.values():
            if declaration.descriptor.tool.action in IMAGE_ACTIONS and lease.current(self.context):
                return lease.api
        return None

    def set_image_enabled(self, settings):
        if self._closed or set(settings) != IMAGE_ACTIONS or any(type(value) is not bool for value in settings.values()):
            raise ValueError("image settings require both native actions")
        self.image_enabled = dict(settings)

    def attach(self, application):
        runtime = getattr(application, "runtime", None)
        if runtime is None or self._closed or (self.application is not None and self.application is not application):
            raise ValueError("native registry must attach to one V2 application")
        self.application, self.runtime = application, runtime
        if self.screen is None and any(entry[0].descriptor.tool.action == SCREEN_ACTION for entry in self._entries.values()):
            self.screen = ScreenAdopter(self, application)
        if self.camera is None and any(entry[0].descriptor.tool.action == REALITY_CAMERA_ACTION
                                       for entry in self._entries.values()):
            self.camera = RealityCameraGuard(self, application)
        if self.content is None and any(entry[0].descriptor.tool.action in CONTENT_ACTIONS for entry in self._entries.values()):
            self.content = ContentConsumer(self, application)
        return self

    def bind_role_guard(self, guard, persona_guard=None):
        if (self._closed or not inspect.iscoroutinefunction(guard)
                or (persona_guard is not None and not inspect.iscoroutinefunction(persona_guard))):
            raise ValueError("native role attestation requires a cooperative host bridge")
        self.role_guard = guard
        self.persona_guard = persona_guard

    def register_catalog(self, *, observed_at):
        """Trusted management operation; declaration registration grants no use rights."""
        if self.runtime is None or self._closed:
            return Outcome.failed("native_registry_unattached", "attach the current registry to a V2 runtime first")
        try:
            repository = CapabilityRepository(self.runtime)
            blocked = {}
            with self.runtime.transaction():
                packages = {}
                for declaration in self.declarations():
                    package = declaration.descriptor.package
                    if package.extension_id in blocked:
                        continue
                    if self.current_declaration(declaration.host_tool_id) != declaration:
                        raise TaskError("native_provider_changed", "native declaration is no longer current")
                    registered = repository.register_descriptor(package, registered_at=observed_at)
                    if registered.failure is not None and registered.failure.code == "capability_descriptor_conflict":
                        # An optional provider cannot replace an immutable descriptor
                        # under the same version, or take the whole core offline.
                        # Retain its records and refuse every tool from this extension.
                        blocked[package.extension_id] = self._entries[declaration.host_tool_id][1].manifest.plugin_id
                        continue
                    packages[package.extension_id] = require(registered)
                if self.content is not None and "content" not in blocked and "content" not in self._blocked_extension_ids:
                    self.content.sources.synchronize()
            self._blocked_extension_ids = self._blocked_extension_ids | frozenset(blocked)
            self.issues = tuple(dict.fromkeys((*self.issues,
                *((plugin_id, "capability_descriptor_conflict") for plugin_id in blocked.values()))))
            self._enforcing_image_settings = True
            return Outcome.success(tuple(packages.values()))
        except TaskError as error:
            return Outcome.failed(error.code, str(error))
        except Exception:
            return Outcome.failed("native_catalog_registration_failed", "native catalog registration failed")

    def _guard(self, host_tool_id, invocation):
        if self.current_declaration(host_tool_id) is None:
            raise TaskError("native_provider_changed", "the pinned native provider is no longer loaded")
        if self.now() >= invocation.deadline_at:
            raise TaskError("native_deadline_expired", "the original native request has expired")
        if self.application is not None:
            self.application.require_running()
            if self.application.external is None or self.application.external.providers.get(
                    invocation.descriptor.tool.action) is None:
                raise TaskError("native_executor_unavailable", "this application did not assemble the native executor")
            self.application.external._admit(invocation.descriptor, invocation.context, self.now())
        if not callable(invocation.before_dispatch) or inspect.iscoroutinefunction(invocation.before_dispatch):
            raise TaskError("native_guard_missing", "native execution requires the original synchronous task fence")
        result = invocation.before_dispatch()
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise TaskError("native_guard_invalid", "native execution cannot defer authorization")

    async def _role(self, host_tool_id, invocation):
        self._guard(host_tool_id, invocation)
        if self.role_guard is not None:
            await self.role_guard(invocation.context.scope, invocation.context.role_binding)
            self._guard(host_tool_id, invocation)

    async def invoke(self, host_tool_id, invocation):
        entry = self._entries.get(host_tool_id)
        if entry is None or entry[0].descriptor != invocation.descriptor:
            raise TaskError("native_provider_changed", "the original native declaration is unavailable")
        port = entry[1].port
        await self._role(host_tool_id, invocation)
        action = invocation.descriptor.tool.action
        reference_lease = None
        if action == "image.mask_edit" or (action == "image.edit"
                and "artifact_id" not in json.loads(invocation.arguments_json)):
            reference_lease = ImageReferenceLease(self, invocation)
        screen_check = self.screen.preflight(invocation) if self.screen is not None and invocation.descriptor.tool.action == SCREEN_ACTION else None
        camera_check = (self.camera.preflight(invocation)
                        if self.camera is not None and invocation.descriptor.tool.action == REALITY_CAMERA_ACTION
                        else None)
        request = invocation_request(invocation)
        if invocation.descriptor.tool.action == TOGETHER_CREATE_ACTION:
            if self.persona_guard is None:
                raise TaskError("native_persona_guard_missing", "room creation requires a verified host persona")
            request["host_persona"] = await self.persona_guard(
                invocation.context.scope, invocation.context.role_binding)
            request["host_execution"] = dict(self.together_execution)
            self._guard(host_tool_id, invocation)
        if self.content is not None and invocation.descriptor.tool.action in CONTENT_ACTIONS:
            self.content.sources.synchronize()
        # Providers receive a copy; mutation cannot alter receipt validation.
        # The synchronous closure expires with this single awaited provider call.
        async def call(method, document, *, image_references=None):
            if not inspect.iscoroutinefunction(method):
                raise TaskError("native_port_invalid", "native I/O must be cooperative asynchronous code")
            active, guarded = True, False

            def before_dispatch():
                nonlocal guarded
                if not active:
                    raise TaskError("native_guard_expired", "the original native dispatch boundary has closed")
                self._guard(host_tool_id, invocation)
                if screen_check is not None:
                    self.screen.recheck(invocation, *screen_check)
                if camera_check is not None:
                    self.camera.recheck(invocation, camera_check)
                if image_references is not None:
                    image_references.recheck()
                guarded = True

            self._guard(host_tool_id, invocation)
            try:
                binding = (self.content.bind(invocation, document, before_dispatch)
                    if self.content is not None and invocation.descriptor.tool.action in CONTENT_ACTIONS else nullcontext())
                with binding:
                    kwargs = {"before_dispatch": before_dispatch}
                    if image_references is not None:
                        parameters = inspect.signature(method).parameters
                        if {"host_references", "fetch_reference"}.issubset(parameters):
                            async def fetch_reference(handle, content_hash, *, role):
                                before_dispatch()
                                return image_references.fetch(handle, content_hash, role=role)
                            kwargs.update(host_references=image_references.offers, fetch_reference=fetch_reference)
                        elif invocation.descriptor.tool.action == "image.mask_edit":
                            raise TaskError("native_reference_reader_unavailable", "the image provider does not accept host image references")
                    result = await method(json_document(document), **kwargs)
                return result, guarded
            finally:
                active = False

        raw, guarded = await call(port.execute, request, image_references=reference_lease)
        # A receipt already returned by the provider is a fact about the original
        # operation. Later loss of access revokes materials, not that fact.
        native = parse_result(raw, request=request, side_effect=invocation.descriptor.side_effect)
        if native.state != "succeeded":
            return self._source_response(invocation, native)
        try:
            if not guarded:
                raise TaskError("native_guard_unused", "the native provider omitted its dispatch check")
            await self._role(host_tool_id, invocation)
            if reference_lease is not None:
                reference_lease.recheck()
            artifacts = []
            for metadata in native.artifacts:
                artifact_request = {**request, "operation_id": metadata.operation_id,
                                    "artifact_id": metadata.artifact_id, "content_hash": metadata.content_hash}
                content, guarded = await call(getattr(port, "read_artifact", None), artifact_request)
                if not guarded:
                    raise TaskError("native_guard_unused", "the native provider omitted its dispatch check")
                await self._role(host_tool_id, invocation)
                try:
                    artifacts.append(metadata.with_content(content))
                except ValueError as error:
                    raise TaskError("native_artifact_changed", "native bytes differ from the immutable artifact receipt") from error
            adopted = replace(native, artifacts=tuple(artifacts))
            self._guard(host_tool_id, invocation)
            handler = self.result_handlers.get(invocation.descriptor.tool.action)
            if self._default_handlers and action in IMAGE_ACTIONS:
                handler = lambda original, received: image_result_handler(
                    original, received, observed_at=self.now(),
                    input_references=() if reference_lease is None else reference_lease.used_references)
            if self._default_handlers and self.content is not None and invocation.descriptor.tool.action in CONTENT_ACTIONS:
                handler = self.content.adopt
            if self._default_handlers and screen_check is not None:
                handler = lambda original, received: self.screen.adopt(original, received, *screen_check)
            # Keep Screen publication and the final host fence in one commit.
            # A failed fence must not leave a governed capture behind.
            adoption = self.runtime.transaction() if screen_check is not None else nullcontext()
            with adoption:
                if handler is None:
                    if artifacts:
                        raise TaskError("native_artifact_unadopted", "native artifacts require an explicit domain adopter")
                    result = self._source_response(invocation, adopted)
                else:
                    result = handler(invocation, adopted)
                    if inspect.isawaitable(result):
                        if inspect.iscoroutine(result):
                            result.close()
                        raise TaskError("native_handler_invalid", "native adoption must be synchronous")
                self._validate_response(invocation, adopted, result)
                self._guard(host_tool_id, invocation)
                if camera_check is not None:
                    self.camera.recheck(invocation, camera_check)
            return result
        except (Exception, asyncio.CancelledError) as error:
            code = (error.code if isinstance(error, TaskError) else "native_adoption_cancelled"
                    if isinstance(error, asyncio.CancelledError) else "native_adoption_unavailable")
            return self._source_response(invocation, native, unavailable_code=code)

    @staticmethod
    def _validate_response(invocation, native, result):
        if not isinstance(result, ExternalToolResponse) or (
                result.invocation_id, result.origin_key, result.arguments_hash, result.binding,
                result.state, result.effect, result.operation_id, result.receipt_ref) != (
                invocation.invocation_id, invocation.context.key, invocation.arguments_hash, invocation.descriptor.binding,
                native.state, native.effect, native.operation_id, native.receipt_ref):
            raise TaskError("native_handler_invalid", "adoption must preserve the original native receipt")
        if native.state == "succeeded":
            source = result.source
            if (source.reference.scope != invocation.context.scope or source.audience != invocation.context.audience
                    or source.reference.owner != invocation.descriptor.source_owner
                    or source.content_hash != digest(source.payload)
                    or json.loads(source.payload).get("native") != native.metadata(invocation.descriptor.binding)):
                raise TaskError("native_handler_invalid", "adoption must preserve native metadata and exact audience")

    def _source_response(self, invocation, native, *, unavailable_code=None):
        source = None
        if native.state == "succeeded":
            metadata = {"native": native.metadata(invocation.descriptor.binding)}
            if unavailable_code:
                metadata["adoption"] = {"state": "unavailable", "code": unavailable_code}
            payload = encode(metadata)
            reference = SourceRef("native:" + invocation.invocation_id, invocation.descriptor.source_owner,
                invocation.context.scope, VersionRef(invocation.invocation_id, 1), self.now())
            source = SourceRecord(reference, invocation.context.audience, digest(payload), payload,
                                  GovernanceState.REVOKED if unavailable_code else GovernanceState.ACTIVE)
        return ExternalToolResponse(invocation.invocation_id, invocation.context.key, invocation.arguments_hash,
            invocation.descriptor.binding, native.state, native.effect, source=source,
            operation_id=native.operation_id, receipt_ref=native.receipt_ref)

    def executor(self, runtime):
        return map_tools(runtime, self) if self.declarations() else None

    def close(self):
        if self.content is not None:
            self.content.close()
        self._closed = True
        self.application = self.runtime = self.role_guard = self.persona_guard = self.screen = None


__all__ = ["NativeExtensionRegistry"]

"""Native owner: generation ends at a receipt; adoption and delivery stay outside."""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Callable

from .package import package_hash
from .store import ImageStore
from .types import (ArtifactContent, BackendResult, ImageInvocation, NativeImageError, ReferenceImage,
                    ReferenceOffer, fingerprint, require_text)


async def checked(guard: Callable):
    result = guard()
    if inspect.isawaitable(result):
        result = await result
    if result is False:
        raise NativeImageError("image_authority_revoked")


class NativeImageOwner:
    def __init__(self, directory: Path, backend, *, generation: str | None = None, identity_key: str | None = None):
        if generation is not None:
            require_text(generation, "provider_generation")
        identity_key = identity_key or fingerprint({"package": package_hash(), "backend": getattr(backend, "revision", type(backend).__module__ + "." + type(backend).__qualname__)})
        self.store = ImageStore(directory, generation, identity_key=identity_key)
        self.generation = self.store.generation
        self.backend = backend
        self._closed = False
        self._tasks: set[asyncio.Task] = set()
        self._refreshing: set[str] = set()

    def _live(self):
        if self._closed:
            raise NativeImageError("image_provider_stopped")

    async def execute(self, invocation: ImageInvocation, *, references: tuple[ReferenceImage, ...] = (),
                      reference_offers: tuple[ReferenceOffer, ...] = (), resolve_references: Callable | None = None,
                      before_dispatch: Callable) -> dict:
        self._live()
        references, reference_offers = tuple(references), tuple(reference_offers)
        request = invocation.document(references, reference_offers)
        operation, fresh = self.store.begin(request)
        if not fresh:
            return operation
        task = asyncio.current_task()
        self._tasks.add(task)

        async def dispatch():
            self._live()
            await checked(before_dispatch)
            self._live()
            self.store.state(invocation.scope_key, operation["id"], "dispatching")

        async def read_guard():
            self._live()
            await checked(before_dispatch)
            self._live()
            self.store.get(invocation.scope_key, operation["id"])

        dispatch.read = read_guard

        try:
            if reference_offers:
                if not callable(resolve_references):
                    raise NativeImageError("native_reference_reader_unavailable")
                await checked(before_dispatch)
                resolved = resolve_references(reference_offers)
                if inspect.isawaitable(resolved):
                    resolved = await resolved
                if (not isinstance(resolved, tuple) or len(resolved) != len(reference_offers)
                        or any(not isinstance(item, ReferenceImage) for item in resolved)):
                    raise NativeImageError("native_reference_reader_invalid")
                expected = tuple(offer.metadata() for offer in reference_offers)
                actual = tuple(item.metadata() for item in resolved)
                if any(any(item.get(key) != offer.get(key) for key in ("reference_id", "source_key", "sha256", "role"))
                       for item, offer in zip(actual, expected)):
                    raise NativeImageError("reference_binding_mismatch")
                references = resolved
            # The backend calls dispatch immediately before every remote mutation.
            result = await self.backend.execute(invocation, tuple(references), dispatch)
            self._live()
            current = self.store.get(invocation.scope_key, operation["id"])
            if current["state"] != "dispatching":
                raise NativeImageError("backend_missing_dispatch_fence")
            return self._accept(current, result)
        except asyncio.CancelledError:
            self._interrupted(invocation.scope_key, operation["id"], "execution_interrupted")
            raise
        except Exception as exc:
            # A transport exception after dispatch can mean the server accepted it.
            return self._interrupted(invocation.scope_key, operation["id"],
                                     exc.code if isinstance(exc, NativeImageError) else "backend_result_unconfirmed")
        finally:
            self._tasks.discard(task)

    def _interrupted(self, scope: str, operation_id: str, error: str) -> dict:
        operation = self.store.get(scope, operation_id)
        if operation["state"] not in {"prepared", "dispatching", "pending"}:
            return operation
        state = "failed" if operation["state"] == "prepared" else "unknown"
        return self.store.state(scope, operation_id, state, error=error)

    def _accept(self, operation: dict, result: BackendResult) -> dict:
        if not isinstance(result, BackendResult):
            raise NativeImageError("backend_result_invalid")
        if result.images:
            return self.store.complete(operation["scope"], operation["id"], tuple(result.images), dict(result.receipt))
        if result.locator:
            return self.store.state(operation["scope"], operation["id"], "pending", locator=dict(result.locator), receipt=dict(result.receipt))
        raise NativeImageError("backend_result_unconfirmed")

    async def recover(self, scope: str, operation_id: str, *, authorize: Callable) -> dict:
        """Poll an existing locator; neither unknown nor restart can submit again."""
        self._live()
        await checked(authorize)
        self._live()
        operation = self.store.get(scope, operation_id)
        if operation["state"] != "pending" or operation_id in self._refreshing:
            return operation
        self._refreshing.add(operation_id)
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            async def read_guard():
                self._live()
                await checked(authorize)
                self._live()
                self.store.get(scope, operation_id)

            result = await self.backend.recover(dict(operation["locator"]), read_guard)
            # Each remote read was authorized before I/O. Once the backend
            # returns a confirmed result, record its effect under the original
            # operation; revocation still prevents further reads and adoption.
            self._live()
            current = self.store.get(scope, operation_id)
            return self._accept(current, result)
        except asyncio.CancelledError:
            # A cancelled GET does not lose the confirmed backend task locator.
            raise
        except Exception:
            return self.store.get(scope, operation_id)
        finally:
            self._refreshing.discard(operation_id)
            self._tasks.discard(task)

    async def read_artifact(self, scope: str, artifact_id: str, *, origin_key: str, provider_generation: str, authorize: Callable) -> ArtifactContent:
        self._live()
        await checked(authorize)
        metadata, raw = self.store.artifact(scope, artifact_id)
        if metadata["origin_key"] != origin_key or metadata["provider_generation"] != provider_generation:
            raise NativeImageError("image_artifact_origin_mismatch")
        await checked(authorize)
        self._live()
        return ArtifactContent(metadata=metadata, data=raw)

    async def close(self):
        self._closed = True
        tasks = tuple(task for task in self._tasks if task is not asyncio.current_task())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        closer = getattr(self.backend, "close", None)
        if callable(closer):
            result = closer()
            if inspect.isawaitable(result):
                await result

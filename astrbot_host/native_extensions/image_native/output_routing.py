"""Native image routing through V2-only API queues and local backend connections."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from .backends import NativeTransportBackend
from .owner import checked
from .types import BackendResult, NativeImageError, fingerprint


class Rejected(NativeImageError):
    """A definitive rejection allows trying the next configured endpoint."""


class OnlineImageBackend:
    def __init__(self, config):
        self.config = config

    @property
    def operations(self):
        config = self.config
        base = config.get("base_url", "").rstrip("/")
        parsed = urlsplit(base)
        if (config.get("enabled") is not True or not config.get("model")
                or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.fragment):
            return ()
        platform = config.get("platform", "auto")
        if platform == "auto":
            platform = "minimax" if "minimax" in parsed.hostname.lower() else "openai"
        return ("generate",) if platform == "minimax" else ("generate", "edit") if platform == "openai" else ()

    async def execute(self, invocation, references, before_dispatch):
        config = self.config
        base = config.get("base_url", "").rstrip("/")
        if not base or not config.get("model"):
            raise NativeImageError("native_endpoint_unconfigured")
        platform = config["platform"]
        if platform == "auto":
            platform = "minimax" if "minimax" in urlsplit(base).hostname.lower() else "openai"
        if invocation.operation == "mask_edit" or (platform == "minimax" and invocation.operation != "generate"):
            raise NativeImageError("unsupported_image_operation")
        suffix = "/image_generation" if platform == "minimax" else (
            "/images/edits" if invocation.operation == "edit" else "/images/generations")
        url = base if base.endswith(suffix) else base + suffix
        size = f"{config['width']}x{config['height']}"
        body = {"model": config["model"], "prompt": invocation.prompt,
                "n": 1, "size": size, "response_format": "b64_json"}
        if platform == "minimax":
            body = {"model": config["model"], "prompt": invocation.prompt,
                    "n": 1, "aspect_ratio": f"{config['width']}:{config['height']}", "response_format": "base64"}
        if invocation.operation == "edit":
            if len(references) != 1:
                raise NativeImageError("native_edit_reference_unsupported")
            form = aiohttp.FormData()
            for key,value in body.items():
                if key != "response_format":
                    form.add_field(key, str(value))
            form.add_field("image", references[0].data, filename="reference.png", content_type="image/png")
            kwargs = {"data":form}
        else:
            kwargs = {"json":body}
        headers = ({"Authorization": "Bearer " + config["api_key"]}
                   if config.get("api_key") else {})
        timeout = aiohttp.ClientTimeout(total=config.get("timeout_seconds", 180))
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            await checked(before_dispatch)
            async with session.post(url, headers=headers, allow_redirects=False, **kwargs) as response:
                if response.status in {400, 401, 403, 404, 405, 413, 422}:
                    raise Rejected("backend_rejected")
                if response.status >= 300:
                    raise NativeImageError("backend_result_unconfirmed")
                raw = await self._read(response)
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise NativeImageError("backend_result_unconfirmed") from exc
            entries = payload.get("data", [])
            if isinstance(entries, dict):
                entries = [{"b64_json":item} for item in entries.get("image_base64", [])] or [
                    {"url":item} for item in entries.get("image_urls", [])]
            if not isinstance(entries, list) or not entries:
                raise NativeImageError("backend_result_unconfirmed")
            entry = entries[0]
            if entry.get("b64_json"):
                try:
                    image = base64.b64decode(entry["b64_json"], validate=True)
                except ValueError as exc:
                    raise NativeImageError("backend_result_unconfirmed") from exc
            elif entry.get("url"):
                remote = urlsplit(entry["url"])
                if remote.scheme not in {"http", "https"} or not remote.hostname or remote.username or remote.password:
                    raise NativeImageError("backend_image_url_invalid")
                await checked(getattr(before_dispatch, "read", before_dispatch))
                async with session.get(entry["url"], allow_redirects=False) as response:
                    if response.status != 200:
                        raise NativeImageError("backend_result_unconfirmed")
                    image = await self._read(response)
            else:
                raise NativeImageError("backend_result_unconfirmed")
            return BackendResult((image,), receipt={"backend":"online_api", "endpoint_id":config["id"],
                                                   "model":config["model"], "response_received":True})

    @staticmethod
    async def _read(response):
        raw = bytearray()
        async for chunk in response.content.iter_chunked(65536):
            raw.extend(chunk)
            if len(raw) > 32 * 1024 * 1024:
                raise NativeImageError("backend_response_too_large")
        return bytes(raw)


class OutputRoutingBackend:
    def __init__(self, settings, directory):
        self.config = json.loads(json.dumps(settings))
        self.backend = settings["backend"]
        self.directory = Path(directory)
        self.revision = fingerprint(settings)
        self._closed = False

    @property
    def operations(self):
        if self.config.get("enabled") is not True:
            return ()
        available = {operation for operation in ("generate", "edit", "mask_edit")
                     for backend in self._routes(operation)
                     if operation in getattr(backend, "operations", ())}
        return tuple(operation for operation in ("generate", "edit", "mask_edit") if operation in available)

    def _routes(self, operation=None):
        route_operation = "generate" if operation == "generate" else "edit"
        operation_routes = self.config.get("operation_routes")
        if operation is not None and isinstance(operation_routes, dict):
            endpoints = {item.get("id"): item for item in self.config.get("endpoints", [])
                         if isinstance(item, dict) and isinstance(item.get("id"), str)}
            routes = operation_routes.get(route_operation, ())
            if not isinstance(routes, (list, tuple)):
                return
            for route in routes:
                if not isinstance(route, str):
                    continue
                if route.startswith("online:"):
                    endpoint = endpoints.get(route[7:])
                    if endpoint and endpoint.get("enabled"):
                        yield OnlineImageBackend(endpoint)
                    continue
                if route in {"comfyui", "sd_webui"}:
                    try:
                        yield NativeTransportBackend(route, self.config.get(route, {}), self.directory / route)
                    except NativeImageError:
                        continue
            return

        selected = self.backend
        if selected in {"auto", "online_api"}:
            for endpoint in self.config.get("endpoints", []):
                if endpoint.get("enabled"):
                    yield OnlineImageBackend(endpoint)
        for name in ("comfyui", "sd_webui"):
            if selected in {"auto", name}:
                try:
                    yield NativeTransportBackend(name, self.config.get(name, {}), self.directory / name)
                except NativeImageError:
                    continue

    async def execute(self, invocation, references, before_dispatch):
        if self._closed or not self.config["enabled"]:
            raise NativeImageError("image_provider_stopped")
        prompt = invocation.envelope.get("image_prompt", {})
        if prompt:
            invocation = replace(invocation, prompt=prompt["positive"], negative_prompt=prompt["negative"])
        for backend in self._routes(invocation.operation):
            if invocation.operation not in backend.operations:
                continue
            dispatched = False

            async def dispatch():
                nonlocal dispatched
                await checked(before_dispatch)
                dispatched = True

            dispatch.read = getattr(before_dispatch, "read", before_dispatch)
            try:
                return await backend.execute(invocation, references, dispatch)
            except Rejected:
                continue
            except Exception:
                if dispatched:
                    raise
        raise NativeImageError("native_backend_unconfigured")

    async def recover(self, locator, authorize):
        name = locator.get("backend")
        if name not in {"comfyui", "sd_webui"}:
            raise NativeImageError("native_backend_changed")
        backend = NativeTransportBackend(name, self.config.get(name, {}), self.directory / name)
        return await backend.recover(locator, authorize)

    async def close(self):
        self._closed = True

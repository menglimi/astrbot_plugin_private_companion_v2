"""Execute compiled native plans without prompt rewriting or backend fallback."""
from __future__ import annotations

import base64
import json
from typing import Callable

import aiohttp

from .comfyui_service import ComfyUIService
from .comfyui_workflows import fill_workflow, validate_mapping
from .image_operations import inspect_image
from .image_preparation_task import PreparationError


class NativeRejected(PreparationError):
    """A definitive pre-execution rejection, distinct from an uncertain POST."""


class NativeClient:
    def __init__(self, backend: str, config: dict, directory):
        self.backend, self.config = backend, config
        self.comfy = ComfyUIService(config, directory) if backend == "comfyui" else None
        self.session = None

    async def close(self):
        if self.comfy is not None:
            await self.comfy.close()
        if self.session is not None:
            await self.session.close()

    async def _http(self):
        if self.comfy is not None:
            return await self.comfy._http()
        if self.session is None:
            headers = {"Authorization": "Bearer " + self.config["api_key"]} if self.config.get("api_key") else {}
            self.session = aiohttp.ClientSession(headers=headers, trust_env=False,
                                                  timeout=aiohttp.ClientTimeout(total=30))
        return self.session

    async def request(self, method: str, path: str, *, limit: int = 8 * 1024 * 1024, **kwargs):
        session = await self._http()
        async with session.request(method, self.config["base_url"] + path, allow_redirects=False, **kwargs) as response:
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw) > limit:
                    raise PreparationError("backend_response_too_large")
            if response.status in {400, 401, 403, 404, 405, 413, 422}:
                raise NativeRejected("backend_rejected")
            if response.status >= 300:
                raise PreparationError("backend_response_error")
            try:
                return json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise PreparationError("backend_response_invalid") from exc

    async def health(self) -> dict:
        if self.backend == "comfyui":
            value = await self.request("GET", "/system_stats")
            return {"backend": self.backend, "available": True,
                    "version": str(value.get("system", {}).get("comfyui_version", ""))[:80]}
        samplers = await self.request("GET", "/sdapi/v1/samplers")
        return {"backend": self.backend, "available": isinstance(samplers, list),
                "samplers": [str(v["name"])[:100] for v in samplers if isinstance(v, dict) and "name" in v]}

    async def prepare_comfy(self, plan: dict, prompt: dict, references: dict[str, bytes],
                            check: Callable[[], None], record_upload: Callable[[str], None]) -> dict:
        definitions = await self.request("GET", "/object_info")
        check()
        if not isinstance(definitions, dict) or any(node["class_type"] not in definitions for node in plan["workflow"].values()):
            raise PreparationError("workflow_nodes_missing")
        validate_mapping(plan["workflow"], plan["mapping"], definitions)
        fields = plan["mapping"]["fields"]
        values = {"positive_prompt": prompt["positive"], **plan["parameters"]}
        if "negative_prompt" in fields:
            values["negative_prompt"] = prompt["negative"]
        for binding in plan["reference_bindings"]:
            check()
            raw = references[binding["input_id"]]
            field = fields[binding["slot"]]
            if plan["workflow"][field["node_id"]]["class_type"] in {"ETN_LoadImageBase64", "ETN_LoadMaskBase64"}:
                values[binding["slot"]] = base64.b64encode(raw).decode("ascii")
            else:
                mime = inspect_image(raw)["media_type"]
                form = aiohttp.FormData()
                form.add_field("image", raw, filename="reference." + mime.split("/")[1], content_type=mime)
                form.add_field("overwrite", "false")
                form.add_field("type", "input")
                uploaded = await self.request("POST", "/upload/image", data=form)
                if not isinstance(uploaded, dict) or not isinstance(uploaded.get("name"), str):
                    raise PreparationError("reference_upload_unconfirmed")
                values[binding["slot"]] = "/".join(v for v in (str(uploaded.get("subfolder", "")), uploaded["name"]) if v)
                record_upload(binding["input_id"])
            check()
        return fill_workflow(plan["workflow"], plan["mapping"], values)

    async def submit_comfy(self, workflow: dict, output_node: str) -> str:
        result = await self.request("POST", "/prompt", json={"client_id": self.comfy.client_id, "prompt": workflow})
        task_id = result.get("prompt_id") if isinstance(result, dict) else None
        if not isinstance(task_id, str) or not 1 <= len(task_id) <= 256:
            raise PreparationError("submission_unconfirmed")
        self.comfy._tasks[task_id] = output_node
        return task_id

    async def poll_comfy(self, task_id: str, output_node: str) -> dict:
        self.comfy._tasks[task_id] = output_node
        return await self.comfy.get_result(task_id)

    async def download_comfy(self, url: str) -> bytes:
        if not url.startswith(self.config["base_url"] + "/view?"):
            raise PreparationError("output_unavailable")
        session = await self._http()
        async with session.get(url, allow_redirects=False) as response:
            if response.status != 200:
                raise PreparationError("output_unavailable")
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw) > 50 * 1024 * 1024:
                    raise PreparationError("output_size_limit")
            return bytes(raw)

    async def cancel_comfy(self, task_id: str, output_node: str) -> dict:
        self.comfy._tasks[task_id] = output_node
        return await self.comfy.cancel(task_id)

    async def generate_sd(self, plan: dict, prompt: dict, references: dict[str, bytes]) -> tuple[list[bytes], dict]:
        payload = {**plan["parameters"], "prompt": prompt["positive"], "negative_prompt": prompt["negative"],
                   "n_iter": 1, "save_images": False, "send_images": True}
        if plan["operation"] in {"edit", "mask_edit"}:
            source = next(binding["input_id"] for binding in plan["reference_bindings"]
                          if binding.get("role", "edit_source") == "edit_source")
            payload["init_images"] = [base64.b64encode(references[source]).decode("ascii")]
            if plan.get("edit_region"):
                region = plan["edit_region"]
                payload.update(mask=base64.b64encode(references[region['mask_input_id']]).decode('ascii'),
                               inpainting_mask_invert=0, mask_blur=0, inpaint_full_res=False)
        else:
            payload.pop("denoising_strength", None)
        value = await self.request("POST", "/sdapi/v1/" + ("img2img" if plan["operation"] in {"edit", "mask_edit"} else "txt2img"),
                                   json=payload, limit=96 * 1024 * 1024,
                                   timeout=aiohttp.ClientTimeout(total=int(self.config.get("timeout_seconds", 300))))
        if not isinstance(value, dict) or not isinstance(value.get("images"), list):
            raise PreparationError("backend_response_invalid")
        info = value.get("info", {})
        try:
            info = json.loads(info) if isinstance(info, str) else info
        except ValueError:
            info = {}
        start = info.get("index_of_first_image", 0) if isinstance(info, dict) else 0
        if type(start) is not int or not 0 <= start < len(value["images"]):
            raise PreparationError("backend_response_invalid")
        images = value["images"][start:]
        if not 1 <= len(images) <= payload["batch_size"]:
            raise PreparationError("backend_response_invalid")
        try:
            decoded = [base64.b64decode(raw.split(",", 1)[-1] if raw.startswith("data:") else raw, validate=True)
                       for raw in images]
        except (ValueError, TypeError, AttributeError) as exc:
            raise PreparationError("backend_response_invalid") from exc
        return decoded, {"backend": "sd_webui", "response_received": True,
                         "output_count": len(decoded), "seeds": info.get("all_seeds", []) if isinstance(info, dict) else []}

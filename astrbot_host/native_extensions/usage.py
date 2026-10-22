"""Service-owned model receipts for V2's native capability runtimes."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any


class TokenUsageTracker:
    def __init__(self, path: Path, *, source="native", display_name="内部能力",
                 note="模型用量只依据实际回执，缺失字段保持未知。") -> None:
        self.path = Path(path)
        self.source, self.display_name = source, display_name
        self.note = note
        self._usage_lock = threading.Lock()
        self._save_lock = threading.Lock()
        self._last_save_at = 0.0
        self._usage = self._load()

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _raw_value(value: Any, key: str) -> Any:
        current = value
        for part in key.split("."):
            if isinstance(current, Mapping):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
            if current is None:
                return None
        return current

    @classmethod
    def _usage_value(cls, usage: Any, *keys: str) -> int | None:
        for key in keys:
            parsed = cls._raw_value(usage, key)
            if type(parsed) is int and parsed >= 0:
                return parsed
        return None

    @classmethod
    def _extract(cls, response: Any, prompt: str, completion: str) -> dict[str, Any]:
        candidates = [
            cls._raw_value(response, "raw_completion.usage"),
            cls._raw_value(response, "raw_completion.usage_metadata"),
            cls._raw_value(response, "raw_response.usage"),
            cls._raw_value(response, "raw_response.token_usage"),
            cls._raw_value(response, "raw_usage"),
            cls._raw_value(response, "token_usage"),
            cls._raw_value(response, "usage"),
        ]
        prompt_tokens = completion_tokens = total_tokens = cached_tokens = cache_write_tokens = None
        for usage in candidates:
            if usage is None:
                continue
            sdk_other = cls._usage_value(usage, "input_other")
            sdk_cached = cls._usage_value(usage, "input_cached")
            sdk = sdk_other is not None
            if sdk and not any((sdk_other or 0, sdk_cached or 0, cls._usage_value(usage, "output") or 0)):
                # AstrBot creates an all-zero TokenUsage even with no provider receipt.
                continue
            inputs = cls._usage_value(usage, "prompt_tokens", "input_tokens", "prompt_token_count", "prompt", "input")
            outputs = cls._usage_value(usage, "completion_tokens", "output_tokens", "completion", "output")
            total = cls._usage_value(usage, "total_tokens", "total_token_count", "total")
            cached = cls._usage_value(usage, "cache_read_tokens", "cache_read_input_tokens",
                "prompt_cache_hit_tokens", "cached_tokens", "cached_input_tokens", "cached_content_token_count",
                "prompt_tokens_details.cached_tokens", "input_tokens_details.cached_tokens", "input_token_details.cache_read")
            creation = cls._usage_value(usage, "cache_write_tokens", "cache_creation_input_tokens",
                "cache_creation_tokens", "prompt_cache_creation_tokens")
            if sdk:
                inputs = sdk_other + (sdk_cached or 0)
                if cached is None and sdk_cached and sdk_cached > 0:
                    cached = sdk_cached
            elif cls._raw_value(usage, "prompt_tokens") is None and cls._raw_value(usage, "input_tokens") is not None:
                if cls._raw_value(usage, "cache_read_input_tokens") is not None or cls._raw_value(usage, "cache_creation_input_tokens") is not None:
                    inputs = inputs + (cached or 0) + (creation or 0) if inputs is not None else None
            if outputs is None:
                outputs = cls._usage_value(usage, "candidates_token_count")
                if outputs is not None:
                    outputs += cls._usage_value(usage, "thoughts_token_count") or 0
            if total is None and inputs is not None and outputs is not None:
                total = inputs + outputs
            if prompt_tokens is None:
                prompt_tokens = inputs
            if completion_tokens is None:
                completion_tokens = outputs
            if total_tokens is None:
                total_tokens = total
            if cached_tokens is None:
                cached_tokens = cached
            if cache_write_tokens is None:
                cache_write_tokens = creation
        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens
        reported_tokens = total_tokens
        if prompt_tokens is not None and (cached_tokens is not None and cached_tokens > prompt_tokens
                or cache_write_tokens is not None and (cached_tokens or 0) + cache_write_tokens > prompt_tokens):
            cached_tokens = cache_write_tokens = None
        hit_reported = cached_tokens is not None and prompt_tokens is not None
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "cache_read_tokens": cached_tokens,
            "cache_write_tokens": cache_write_tokens,
            "estimated": False,
            "reported_tokens": reported_tokens,
            "estimated_tokens": 0,
            "usage_available": reported_tokens is not None,
            "usage_availability": "reported" if reported_tokens is not None else "unavailable",
            "cache_hit_reported": hit_reported,
            "cache_input_tokens": prompt_tokens if hit_reported else None,
            "cache_reported_calls": int(hit_reported),
            "cache_telemetry_calls": int(cached_tokens is not None or cache_write_tokens is not None),
        }

    def record(
        self,
        *,
        provider_id: str,
        task: str,
        prompt: str,
        completion: str,
        elapsed_ms: int,
        success: bool,
        error: str = "",
        response: Any = None,
        persist: bool = True,
    ) -> None:
        with self._usage_lock:
            self._append_record(provider_id=provider_id, task=task, prompt=prompt, completion=completion,
                elapsed_ms=elapsed_ms, success=success, error=error, response=response)
        if persist:
            self.save()

    def _append_record(self, *, provider_id: str, task: str, prompt: str, completion: str,
                       elapsed_ms: int, success: bool, error: str, response: Any) -> None:
        usage = self._extract(response, prompt, completion)
        now = datetime.now()
        now_ts = time.time()
        day = now.strftime("%Y-%m-%d")
        hour = now.strftime("%Y-%m-%d %H:00")
        store = self._usage if isinstance(self._usage, dict) else {}
        self._usage = store
        provider_key = str(provider_id or "(default)")[:160]
        task_key = str(task or self.source + "_other")[:80]

        def mapping(name: str) -> dict[str, Any]:
            value = store.setdefault(name, {})
            if not isinstance(value, dict):
                value = {}
                store[name] = value
            return value

        def nested(parent: dict[str, Any], key: str) -> dict[str, Any]:
            value = parent.setdefault(key, {})
            if not isinstance(value, dict):
                value = {}
                parent[key] = value
            return value

        def bump(bucket: dict[str, Any]) -> None:
            bucket["calls"] = self._safe_int(bucket.get("calls")) + 1
            bucket["success"] = self._safe_int(bucket.get("success")) + (1 if success else 0)
            bucket["errors"] = self._safe_int(bucket.get("errors")) + (0 if success else 1)
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "cached_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "reported_tokens",
                "estimated_tokens",
                "cache_input_tokens",
                "cache_reported_calls",
                "cache_telemetry_calls",
            ):
                value = usage.get(key)
                if value is not None:
                    bucket[key] = self._safe_int(bucket.get(key)) + value
                else:
                    bucket.setdefault(key, None)
            bucket["usage_reported_calls"] = self._safe_int(bucket.get("usage_reported_calls")) + int(usage["usage_available"])
            bucket["unconfirmed_calls"] = self._safe_int(bucket.get("unconfirmed_calls")) + int(not usage["usage_available"])
            bucket["cache_hit_reported"] = self._safe_int(bucket.get("cache_reported_calls")) > 0
            bucket["elapsed_ms"] = self._safe_int(bucket.get("elapsed_ms")) + max(0, int(elapsed_ms or 0))
            bucket["last_ts"] = now_ts

        totals = mapping("totals")
        by_provider = mapping("by_provider")
        by_task = mapping("by_task")
        by_day = mapping("by_day")
        by_day_provider = mapping("by_day_provider")
        by_day_task = mapping("by_day_task")
        by_hour = mapping("by_hour")
        day_providers = nested(by_day_provider, day)
        day_tasks = nested(by_day_task, day)
        for bucket in (
            totals,
            by_provider.setdefault(provider_key, {}),
            by_task.setdefault(task_key, {}),
            by_day.setdefault(day, {}),
            day_providers.setdefault(provider_key, {}),
            day_tasks.setdefault(task_key, {}),
            by_hour.setdefault(hour, {}),
        ):
            if isinstance(bucket, dict):
                bump(bucket)

        recent = store.setdefault("recent", [])
        if not isinstance(recent, list):
            recent = []
            store["recent"] = recent
        recent.append(
            {
                "ts": now_ts,
                "time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "provider": provider_key,
                "task": task_key,
                "success": bool(success),
                **usage,
                "elapsed_ms": max(0, int(elapsed_ms or 0)),
                "prompt_chars": len(str(prompt or "")),
                "completion_chars": len(str(completion or "")),
                "error": " ".join(str(error or "").split())[:160],
            }
        )
        del recent[:-240]
        store["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")

    def summary(self) -> dict[str, Any]:
        with self._usage_lock:
            try:
                payload = json.loads(json.dumps(self._usage, ensure_ascii=False))
            except (TypeError, ValueError):
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.update(
            {
                "available": True,
                "display_name": self.display_name,
                "plugin_name": "astrbot_plugin_private_companion." + self.source,
                "counted_in_private_companion_budget": False,
                "note": self.note,
            }
        )
        return payload

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {}

            def history(value):
                if isinstance(value, dict):
                    if (value.get("estimated") is True or self._safe_int(value.get("estimated_tokens")) > 0) and "cache_telemetry_calls" not in value:
                        value["estimated_tokens"] = self._safe_int(value.get("estimated_tokens") or value.get("total_tokens"))
                        value["reported_tokens"] = max(0, self._safe_int(value.get("total_tokens")) - value["estimated_tokens"])
                        for key in ("cached_tokens", "cache_read_tokens", "cache_write_tokens", "cache_input_tokens"):
                            value[key] = None
                        value.update(cache_hit_reported=False, cache_reported_calls=0, cache_telemetry_calls=0)
                    for item in tuple(value.values()):
                        history(item)
                elif isinstance(value, list):
                    for item in value:
                        history(item)

            history(payload)
            return payload
        except (OSError, TypeError, ValueError):
            return {}

    def save(self, *, force: bool = False) -> None:
        with self._save_lock:
            now_ts = time.time()
            if not force and now_ts - self._last_save_at < 30:
                return
            self._last_save_at = now_ts
            with self._usage_lock:
                payload = json.dumps(self._usage, ensure_ascii=False, indent=2) + "\n"
            # Snapshot under the data lock, then write without blocking new receipts.
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(self.path.suffix + ".tmp")
                temporary.write_text(payload, encoding="utf-8", newline="\n")
                temporary.replace(self.path)
            except OSError:
                return


async def tracked_text_chat(owner, provider, *, task: str, timeout: float | None = None, **kwargs):
    """Keep one actual provider attempt and receipt on the service's own ledger."""
    started = time.perf_counter()
    response = None
    error_type = ""
    try:
        operation = provider.text_chat(**kwargs)
        response = await operation if timeout is None else await asyncio.wait_for(operation, timeout=timeout)
        return response
    except asyncio.CancelledError:
        error_type = "cancelled"
        raise
    except Exception as error:
        error_type = type(error).__name__
        raise
    finally:
        tracker = getattr(owner, "token_usage", None)
        if tracker is not None:
            try:
                try:
                    provider_id = str(getattr(provider.meta(), "id", "") or "")
                except Exception:
                    provider_id = str(getattr(provider, "provider_id", "") or "")
                completion = response if isinstance(response, str) else getattr(response, "completion_text", "")
                completion = completion if isinstance(completion, str) else ""
                tracker.record(provider_id=provider_id, task=task,
                    prompt=str(kwargs.get("system_prompt") or "") + "\n" + str(kwargs.get("prompt") or ""),
                    completion=completion, elapsed_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    success=not error_type and bool(completion.strip()),
                    error=error_type or ("" if completion.strip() else "empty_response"),
                    response=response, persist=False)
                pending = getattr(owner, "_model_usage_tasks", None)
                if pending is None:
                    pending = owner._model_usage_tasks = set()
                if not pending:
                    saving = asyncio.create_task(asyncio.to_thread(tracker.save), name="companion-v2:model-usage-save")
                    pending.add(saving)
                    saving.add_done_callback(pending.discard)
            except Exception as error:
                logging.getLogger(__name__).debug("Native model receipt unavailable error_type=%s", type(error).__name__)


async def flush_model_usage(owner):
    """Finish pending disk snapshots, then flush the service's final receipts."""
    pending = getattr(owner, "_model_usage_tasks", None)
    if pending:
        await asyncio.gather(*tuple(pending), return_exceptions=True)
    tracker = getattr(owner, "token_usage", None)
    if tracker is not None:
        await asyncio.to_thread(tracker.save, force=True)

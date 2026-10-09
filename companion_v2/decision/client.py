"""Adapters for the official Laya Python API and its SystemOne HTTP protocol."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import logging
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .contract import LayaDecision, DecisionContractError, deterministic_skip_reason, parse_decision
from .prompt import DECISION_QUESTIONS, build_state, facts_document


logger = logging.getLogger(__name__)
_LOCAL_ROUTER_LOCK = threading.Lock()
_LOCAL_ROUTERS: dict[str, tuple[object, threading.Lock]] = {}
MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_MODEL = "multilingual"


class LayaClientError(RuntimeError):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _endpoint(value: str) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LayaClientError("laya_endpoint_invalid", "Laya 服务地址必须是 HTTP(S) 地址")
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1/systemone"):
        path += "/systemone" if path.endswith("/v1") else "/v1/systemone"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def _local_router():
    with _LOCAL_ROUTER_LOCK:
        cached = _LOCAL_ROUTERS.get(DEFAULT_MODEL)
        if cached is not None:
            return cached
        try:
            from laya import Router
        except ImportError as error:
            raise LayaClientError(
                "laya_package_missing",
                "当前 AstrBot Python 环境未安装 Laya；请在模型页复制安装命令并重启 AstrBot",
            ) from error
        try:
            router = Router(default=DEFAULT_MODEL, max_loaded=1)
        except Exception as error:
            raise LayaClientError("laya_initialization_failed", f"Laya Router 初始化失败：{type(error).__name__}: {error}") from error
        cached = (router, threading.Lock())
        _LOCAL_ROUTERS[DEFAULT_MODEL] = cached
        return cached


def _local_predict(state: str, questions: dict):
    router, lock = _local_router()
    try:
        with lock:
            return router.predict(state, questions)
    except Exception as error:
        raise LayaClientError("laya_inference_failed", f"Laya 本地推理失败：{type(error).__name__}: {error}") from error


def _parse_document(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise LayaClientError("laya_response_invalid", "Laya 返回的不是有效 JSON") from error
    if type(value) is not dict:
        raise LayaClientError("laya_response_invalid", "Laya 返回的 JSON 不是对象")
    return value


def _decision_from_result(document: dict) -> LayaDecision:
    answers = document.get("answers")
    if type(answers) is not dict:
        raise LayaClientError("laya_response_invalid", "Laya 响应缺少 answers 对象")
    choices = {}
    for name in DECISION_QUESTIONS:
        answer = answers.get(name)
        choice = answer.get("choice") if type(answer) is dict else None
        if type(answer) is not dict or answer.get("type") != "choice" or type(choice) is not str:
            raise LayaClientError("laya_response_invalid", f"Laya 响应缺少 choice 分类：{name}")
        choices[name] = choice
    choices["reason_codes"] = []
    try:
        return parse_decision(choices)
    except DecisionContractError as error:
        raise LayaClientError("laya_contract_invalid", str(error)) from error


def _safe_error_text(raw: bytes, secret: str) -> str:
    try:
        text = raw.decode("utf-8", errors="replace")
        document = json.loads(text)
        if isinstance(document, dict):
            detail = document.get("detail") or document.get("error") or document
            text = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
    except (TypeError, ValueError):
        text = raw.decode("utf-8", errors="replace")
    if secret:
        text = text.replace(secret, "<hidden>")
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())[:1000]


class LayaDecisionClient:
    def __init__(self, *, mode: str = "local", endpoint: str = "", api_key: str = "",
                 timeout_seconds: int = 8):
        if mode not in {"local", "remote"}:
            raise LayaClientError("laya_mode_invalid", "Laya 接入方式必须是 local 或 remote")
        self.mode = mode
        self.endpoint = _endpoint(endpoint) if mode == "remote" else ""
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def decide(self, facts: dict) -> LayaDecision:
        skip = deterministic_skip_reason(facts)
        if skip is not None:
            raise LayaClientError("laya_rule_skip", skip)
        state = build_state(facts_document(facts))
        questions = deepcopy(DECISION_QUESTIONS)
        logger.debug("[CompanionV2][开发者追踪] Laya 输入 mode=%s state=%s questions=%s",
                     self.mode, state[:16000], json.dumps(questions, ensure_ascii=False, separators=(",", ":")))
        if self.mode == "local":
            raw_result = await asyncio.to_thread(_local_predict, state, questions)
        else:
            raw_result = await self._post(state, questions)
        if type(raw_result) is not dict:
            raise LayaClientError("laya_response_invalid", "Laya predict 返回的结果不是对象")
        logger.debug("[CompanionV2][开发者追踪] Laya 原始答案 mode=%s response=%s",
                     self.mode, repr(raw_result)[:20000])
        decision = _decision_from_result(raw_result)
        logger.debug("[CompanionV2][开发者追踪] Laya 合同转换 result=%s",
                     json.dumps(decision.document(), ensure_ascii=False, separators=(",", ":")))
        return decision

    async def probe(self) -> LayaDecision:
        return await self.decide({
            "message_kind": "text",
            "user_text": "我这边在测试连接，请按当前语义分类问题作答。",
            "scope_kind": "test",
            "connection_test": True,
        })

    async def _post(self, state: str, questions: dict) -> dict:
        body = json.dumps({"state": state, "questions": questions},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = Request(self.endpoint, data=body, headers=headers, method="POST")

        def send() -> dict:
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    content = response.read(MAX_RESPONSE_BYTES + 1)
            except HTTPError as error:
                detail = _safe_error_text(error.read(4096), self.api_key)
                raise LayaClientError("laya_http_error",
                    f"Laya HTTP {error.code}" + (f"：{detail}" if detail else "")) from error
            except (URLError, TimeoutError, OSError) as error:
                raise LayaClientError("laya_transport_failed",
                    f"Laya 连接失败：{type(error).__name__}: {error}") from error
            if len(content) > MAX_RESPONSE_BYTES:
                raise LayaClientError("laya_response_too_large", "Laya 响应超过 1 MiB")
            try:
                return _parse_document(content.decode("utf-8"))
            except UnicodeError as error:
                raise LayaClientError("laya_response_invalid", "Laya 响应不是 UTF-8") from error

        try:
            return await asyncio.to_thread(send)
        except LayaClientError:
            raise

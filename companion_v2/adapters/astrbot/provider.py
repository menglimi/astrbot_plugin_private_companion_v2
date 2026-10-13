"""One-attempt text transport for the verified AstrBot OpenAI-compatible class.

No host import or registration occurs here. This adapter bypasses text_chat's
outer ten-attempt loop and disables the SDK retry layer on a private client view.
The V2 gateway alone owns tool execution, fallback and durable accounting.
"""

from copy import copy, deepcopy
from dataclasses import dataclass, replace
from logging import getLogger
import re
from types import SimpleNamespace
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.model_gateway.cache_diagnostics import signature_for_payload
from companion_v2.model_gateway.failures import ModelFailure
from companion_v2.model_gateway.models import Amount, CapturedModelOutput, LocalProvider, ProviderResponse
from companion_v2.model_gateway.response_diagnostics import ResponseDiagnostics, ResponseTextSummary

from .model_wire import build_wire, decode_response
from .native import check_version, native_id
from .memory_output import capture, explicit_refusal, response_format
from .streaming import StreamTranscript
from .response_diagnostics import observe_completion
from .provider_transport import definitely_not_sent


RESERVED_EXTRA = frozenset({"model", "messages", "tools", "functions", "function_call", "tool_choice",
    "stream", "stream_options", "max_tokens", "max_completion_tokens", "max_output_tokens", "n",
    "response_format", "extra_body"})
logger = getLogger(__name__)
_MEDIA_KEYS = frozenset(("url", "image_url", "data", "data_base64", "video_data", "input_audio"))
_SECRET_KEYS = frozenset(("api_key", "access_token", "authorization", "password", "secret", "token"))


def _developer_content(value):
    """Keep text in DEBUG traces while replacing large binary media payloads."""
    if isinstance(value, (list, tuple)):
        return [_developer_content(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        key_name = key.casefold() if isinstance(key, str) else ""
        if key_name in _SECRET_KEYS or key_name.endswith(("_api_key", "_access_token", "_secret", "_password")):
            result[key] = "<secret omitted>"
        elif key in _MEDIA_KEYS and isinstance(item, str) and len(item) > 256:
            result[key] = f"<binary omitted chars={len(item)}>"
        else:
            result[key] = _developer_content(item)
    return result


def _developer_payload(payload):
    """Render the actual provider request without flooding logs with base64 media."""
    if not isinstance(payload, dict):
        return payload
    return _developer_content(payload)


def _developer_completion(completion):
    """Return the response body in a log-friendly shape before host parsing."""
    if completion is None:
        return None
    if isinstance(completion, (dict, list, tuple)):
        return _developer_content(completion)
    for method in ("model_dump", "to_dict"):
        convert = getattr(completion, method, None)
        if callable(convert):
            try:
                dumped = convert()
                if isinstance(dumped, (dict, list, tuple)):
                    return _developer_content(dumped)
            except Exception:
                pass

    def read(value, name, default=None):
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    # AstrBot's native transport returns LLMResponse rather than the raw
    # OpenAI ``choices`` object.  Keep its plain completion text and tool
    # fields explicit so the trace remains useful after host parsing.
    if hasattr(completion, "completion_text"):
        raw = getattr(completion, "raw_completion", None)
        raw_dump = None
        raw_choice = None
        raw_choices = read(raw, "choices", ())
        if isinstance(raw_choices, (list, tuple)) and raw_choices:
            raw_choice = raw_choices[0]
        raw_message = read(raw_choice, "message")
        if raw is not None:
            for method in ("model_dump", "to_dict"):
                convert = getattr(raw, method, None)
                if callable(convert):
                    try:
                        raw_dump = _developer_content(convert())
                        break
                    except Exception:
                        pass
            if raw_dump is None:
                raw_dump = _developer_completion(raw) if raw is not completion else None
        return {"role": getattr(completion, "role", None),
                "completion_text": _developer_content(getattr(completion, "completion_text", None)),
                "reasoning_content": _developer_content(getattr(completion, "reasoning_content", None)),
                "tools_call_name": _developer_content(getattr(completion, "tools_call_name", None)),
                "tools_call_ids": _developer_content(getattr(completion, "tools_call_ids", None)),
                "tools_call_args": _developer_content(getattr(completion, "tools_call_args", None)),
                "raw_content": _developer_content(read(raw_message, "content")),
                "raw_finish_reason": read(raw_choice, "finish_reason"),
                "raw_completion": raw_dump,
                "usage": repr(getattr(completion, "usage", None)),
                "raw_type": type(completion).__name__}

    choices = getattr(completion, "choices", ())
    choice = choices[0] if isinstance(choices, (list, tuple)) and choices else None
    message = read(choice, "message")
    return {"finish_reason": read(choice, "finish_reason"),
            "message": {"role": read(message, "role"),
                        "content": _developer_content(read(message, "content")),
                        "tool_calls": _developer_content(read(message, "tool_calls"))},
            "usage": _developer_content(read(completion, "usage")),
            "raw_type": type(completion).__name__}


class _DeveloperRequestTrace:
    """Observe SDK parameters after all native request transformations."""

    def __init__(self, client, provider_id, event_id):
        self.client, self.provider_id, self.event_id = client, provider_id, event_id

    async def create(self, **kwargs):
        logger.debug("[CompanionV2][开发者追踪] 最终模型请求 event_id=%s provider=%s payload=%s",
                     self.event_id, self.provider_id, _developer_payload(kwargs))
        return await self.client.chat.completions.create(**kwargs)

    def client_view(self):
        trace = self

        class ClientView:
            chat = SimpleNamespace(completions=SimpleNamespace(create=trace.create))

            def __getattr__(self, name):
                return getattr(trace.client, name)

        return ClientView()


def provider_fingerprint(native):
    """Read-only identity of the selected configuration, without returning secrets."""
    return digest([native.provider_config, native.get_model(),
                   sorted(getattr(native, "default_params", {}))])


@dataclass(frozen=True)
class UsageTariff:
    """Explicit rated cost in microUSD per million tokens; not a billing receipt."""
    input: int
    cached_input: int
    output: int

    def __post_init__(self):
        if any(type(v) is not int or not 0 <= v <= 10**12 for v in (self.input, self.cached_input, self.output)):
            raise ValueError("tariff requires nonnegative integer microUSD rates")

    def amount(self, other, cached, output, *, input_tokens=None, cached_input_tokens=None,
               cache_creation_tokens=None):
        cost = (other * self.input + cached * self.cached_input + output * self.output + 999999) // 1000000
        return Amount(other + cached + output, cost, input_tokens=input_tokens,
                      cached_input_tokens=cached_input_tokens, cache_creation_tokens=cache_creation_tokens,
                      output_tokens=output if input_tokens is not None else None)


class AstrBotTextProvider:
    def __init__(self, context, *, bridge, binding, provider_id, version, provider_type,
                 function_tool_type, tool_set_type, tariff: UsageTariff, maximum_output_tokens=4096,
                 maximum_input_estimate=131072, output_parameter="max_tokens", streaming=False):
        check_version(version)
        if output_parameter not in ("max_tokens", "max_completion_tokens"):
            raise ValueError("output token parameter must be selected explicitly")
        if type(maximum_input_estimate) is not int or not 1024 <= maximum_input_estimate <= 1000000:
            raise ValueError("input estimate ceiling is outside this adapter profile")
        self.context, self.bridge, self.binding, self.provider_id = context, bridge, binding, provider_id
        self.native = context.get_provider_by_id(provider_id)
        if type(self.native) is not provider_type:
            raise ValueError("provider needs the verified native provider class")
        self.provider_type = provider_type
        self.config = deepcopy(self.native.provider_config)
        self.config_hash = digest(self.config)
        self.model = self.native.get_model()
        self.client = self.native.client
        self.parameters = frozenset(self.native.default_params)
        self.function_tool_type, self.tool_set_type = function_tool_type, tool_set_type
        self.tariff, self.output_parameter = tariff, output_parameter
        if type(streaming) is not bool:
            raise ValueError("streaming must be an explicit boolean")
        if streaming and not callable(getattr(self.native, "_query_stream", None)):
            raise ValueError("the verified native provider has no streaming transport")
        self.streaming = streaming
        self.maximum_output_tokens, self.maximum_input_estimate = maximum_output_tokens, maximum_input_estimate
        extra = self.config.get("custom_extra_body", {})
        if not isinstance(extra, dict) or RESERVED_EXTRA & extra.keys():
            raise ValueError("custom provider parameters cannot override V2 routing, tools or output limits")
        # Validate the public limits without making a request.
        self.local_provider()

    def local_provider(self):
        modalities = self.config.get("modalities")
        capabilities = (tuple(capability for modality, capability in (
            ("text", "text"), ("tool_use", "tools"), ("image", "image"), ("audio", "audio"))
            if modality in modalities) if isinstance(modalities, list) and modalities
            else ("text", "tools", "image", "audio"))
        return LocalProvider(self.binding, capabilities, self.maximum_output_tokens,
                             self.reserve, self.generate, transport="astrbot_openai", default_streaming=self.streaming,
                             supports_model_override=True, model=self.model)

    def _current(self):
        if (self.context.get_provider_by_id(self.provider_id) is not self.native
                or self.native.client is not self.client or self.native.get_model() != self.model
                or digest(self.native.provider_config) != self.config_hash
                or frozenset(self.native.default_params) != self.parameters):
            raise TaskError("host_provider_changed", "original host provider/client/configuration was replaced")

    def _estimate(self, envelope, wire):
        estimated = wire.input_estimate()
        structured = response_format(envelope.original)
        if structured is not None:
            estimated += len(encode(structured).encode("utf-8"))
        if (estimated > self.maximum_input_estimate or type(envelope.max_output_tokens) is not int
                or not 1 <= envelope.max_output_tokens <= self.maximum_output_tokens):
            raise TaskError("host_model_limit", "request exceeds its declared input/output profile")
        return estimated

    def reserve(self, envelope):
        estimate = self._estimate(envelope, build_wire(envelope, model_name=envelope.model_override or self.model))
        # No assumed cache hit; reserve using the larger of the two input rates.
        rate = max(self.tariff.input, self.tariff.cached_input)
        return UsageTariff(rate, rate, self.tariff.output).amount(estimate, 0, envelope.max_output_tokens)

    def _usage(self, raw):
        try:
            def read(value, name):
                return value.get(name) if isinstance(value, dict) else getattr(value, name, None)

            usage = read(raw, "usage")
            prompt = read(usage, "prompt_tokens")
            completion = read(usage, "completion_tokens")
            total = read(usage, "total_tokens")
            if total is None and type(prompt) is int and type(completion) is int:
                total = prompt + completion
            values = (prompt, completion, total)
            if any(type(v) is not int or not 0 <= v <= 10**12 for v in values) or prompt + completion != total:
                return None
            details = read(usage, "prompt_tokens_details") or read(usage, "input_tokens_details")
            cached = read(details, "cached_tokens") if details else None
            if cached is None:
                cached = read(usage, "cache_read_input_tokens")
            if cached is None:
                cached = read(usage, "prompt_cache_hit_tokens")
            cache_creation = read(usage, "cache_creation_input_tokens")
            if cache_creation is None:
                cache_creation = read(usage, "cache_creation_tokens")
            if cache_creation is None and details:
                cache_creation = read(details, "cache_creation_tokens")
            if cache_creation is None:
                creation = read(usage, "cache_creation")
                if creation:
                    creation_values = [read(creation, name) for name in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")]
                    if all(value is None or type(value) is int for value in creation_values):
                        cache_creation = sum(value or 0 for value in creation_values)
            # Absent cache detail is rated conservatively at the input rate.
            cache_read = 0 if cached is None else cached
            if (type(cache_read) is not int or not 0 <= cache_read <= prompt
                    or cache_creation is not None and (type(cache_creation) is not int
                                                       or not 0 <= cache_creation <= prompt
                                                       or cache_read + cache_creation > prompt)):
                return None
            return self.tariff.amount(prompt - cache_read, cache_read, completion, input_tokens=prompt,
                                      cached_input_tokens=cache_read if cached is not None else None,
                                      cache_creation_tokens=cache_creation)
        except (AttributeError, TypeError, ValueError):
            return None

    def _receipt(self, raw, fallback):
        try:
            identifier = native_id(raw.id)
            if len(identifier) <= 256:
                return "astrbot-response:" + digest(self.binding)[:24] + ":" + identifier
        except (AttributeError, TypeError, ValueError):
            pass
        return fallback

    async def probe(self):
        """Send one fixed, context-free request through the pinned native transport."""
        self._current()
        native = copy(self.native)
        native.provider_config = deepcopy(self.config)
        native.client = self.client.with_options(max_retries=0)
        if native.client.max_retries != 0:
            raise ValueError("native probe retries could not be disabled")
        payload = {"model": self.model, "messages": [{"role": "user", "content": "Reply OK."}],
                   self.output_parameter: 8, "stream": False}
        result = await native._query(payload, None, request_max_retries=1)
        self._current()
        if result is None:
            raise ValueError("native probe returned no result")

    async def generate(self, envelope):
        receipt = "astrbot-model-" + uuid4().hex
        observed = []
        parse_failed = False
        verified_refusal = False
        transcript = None
        response = None
        diagnostics = ResponseDiagnostics()
        try:
            wire = build_wire(envelope, model_name=envelope.model_override or self.model)
            logger.debug("[CompanionV2][开发者追踪] 模型提示词组装 provider=%s output_format=%s messages=%s tools=%s",
                         self.provider_id, wire.output_format, _developer_content(wire.messages),
                         _developer_content(wire.tools))
            self._estimate(envelope, wire)
            await self.bridge.verify_role(envelope.original.event.scope, envelope.original.role_binding,
                                          envelope.original.role_instruction)
            self._current()
            native = copy(self.native)
            native.provider_config = deepcopy(self.config)
            native.client = self.client.with_options(max_retries=0)
            if native.client.max_retries != 0:
                raise ValueError("client retry layer could not be disabled")
            native.client = _DeveloperRequestTrace(native.client, self.provider_id,
                getattr(envelope.original.event, "event_id",
                        getattr(envelope.original.event, "request_id", "unknown"))).client_view()
            streaming = self.streaming if envelope.original.streaming is None else envelope.original.streaming
            if streaming and envelope.original.output_format == "conversation":
                if not callable(getattr(native, "_query_stream", None)):
                    raise ValueError("native streaming transport is unavailable")
                on_content = None
                if envelope.on_reply_prefix is not None and envelope.original.streaming_mode == "incremental":
                    from .reply_stream import OrderedReplyStream
                    reply_stream = OrderedReplyStream(wire)

                    async def on_content(fragment):
                        draft = reply_stream.feed(fragment)
                        if draft is not None and (envelope.reply_prefix_ready is None or envelope.reply_prefix_ready(draft)):
                            self._current()
                            await self.bridge.verify_role(envelope.original.event.scope, envelope.original.role_binding,
                                                          envelope.original.role_instruction)
                            await envelope.on_reply_prefix(draft)
                transcript = StreamTranscript(native.client, on_content)
            tools = self.tool_set_type(tools=[self.function_tool_type(**t, handler=None) for t in wire.tools]) if wire.tools else None

            async def parse(completion, offered):
                # Retain actual usage even if the host parser rejects an empty/filtered result.
                nonlocal parse_failed, verified_refusal, diagnostics
                observed.append(completion)
                logger.debug("[CompanionV2][开发者追踪] 原生解析输入 provider=%s response=%s",
                             self.provider_id, _developer_completion(completion))
                diagnostics = observe_completion(completion)
                if transcript is not None:
                    try:
                        transcript.verify(completion)
                    except Exception:
                        diagnostics = replace(diagnostics, parse_state="stream_rejected")
                        raise
                verified_refusal = explicit_refusal(completion) or bool(transcript and transcript.refusal)
                if wire.output_format == "memory_reflection":
                    # Memory owns parsing and a durable recovery queue. Keep the
                    # provider's original text and completion reason, even when
                    # a native text parser would reject an empty/refused reply.
                    return completion
                try:
                    parsed = await self.provider_type._parse_openai_completion(native, completion, offered)
                    diagnostics = replace(diagnostics, parse_state="native_parsed",
                        parsed=ResponseTextSummary.from_text(getattr(parsed, "completion_text", None)))
                    logger.debug("[CompanionV2][开发者追踪] 原生解析结果 provider=%s completion_text=%r diagnostics=%s",
                                 self.provider_id, getattr(parsed, "completion_text", None), diagnostics.to_record())
                    return parsed
                except Exception as error:
                    parse_failed = True
                    diagnostics = replace(diagnostics, parse_state="native_rejected")
                    logger.debug("[CompanionV2][开发者追踪] 原生解析失败 provider=%s error_type=%s",
                                 self.provider_id, type(error).__name__, exc_info=True)
                    raise
            native._parse_openai_completion = parse
            if envelope.original.images or envelope.original.audios or envelope.original.videos:
                # V2 has already materialized and validated exact data URLs. The
                # host's general image resolver may download, re-encode or log
                # unresolved locations; none of those are needed for these bytes.
                async def keep_original_images(contexts):
                    return deepcopy(contexts)
                native._materialize_context_image_parts = keep_original_images
            payload, _ = await native._prepare_chat_payload(prompt=None, contexts=deepcopy(wire.messages),
                                                          model=envelope.model_override or self.model)
            if envelope.original.images or envelope.original.audios or envelope.original.videos:
                def image_materials(messages):
                    return [message for message in messages if isinstance(message.get("content"), list)]
                if image_materials(payload["messages"]) != image_materials(wire.messages):
                    raise ValueError("native preparation changed original images or their coverage and attribution")
            payload[self.output_parameter] = envelope.max_output_tokens
            structured = response_format(envelope.original)
            if structured is not None:
                payload["response_format"] = structured
            logger.debug("[CompanionV2][开发者追踪] 实际模型请求 provider=%s model=%s payload=%s",
                         self.provider_id, payload.get("model", self.model), _developer_payload(payload))
            self._current()
            if envelope.before_dispatch is None:
                raise ValueError("native model dispatch requires the live owner's fence")
            envelope.before_dispatch()
            if envelope.record_cache_signature is not None:
                try:
                    envelope.record_cache_signature(signature_for_payload(
                        payload.get("model", envelope.model_override or self.model),
                        payload.get("messages", ()), wire.tools))
                except Exception:
                    logger.debug("cache signature collection failed", exc_info=True)
        except Exception as error:
            task_error_code = error.code if isinstance(error, TaskError) else None
            if (not isinstance(task_error_code, str)
                    or re.fullmatch(r"[a-z0-9_.-]{1,80}", task_error_code) is None):
                task_error_code = None
            status_code = getattr(error, "status_code", None)
            if type(status_code) is not int or not 100 <= status_code <= 599:
                status_code = None
            error_type = type(error).__name__
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", error_type) is None:
                error_type = None
            diagnostics = replace(diagnostics, failure=ModelFailure.PREPARATION,
                error_type=error_type, error_code=task_error_code, status_code=status_code)
            logger.warning("[CompanionV2] 模型请求准备失败 provider=%s failure=%s error_type=%s "
                           "task_error_code=%s status_code=%s",
                           self.provider_id, ModelFailure.PREPARATION.value,
                           error_type or "unavailable", task_error_code or "unavailable",
                           status_code if status_code is not None else "unavailable")
            return ProviderResponse("not_started", usage=Amount(0, 0), receipt_ref=receipt,
                                    failure=ModelFailure.PREPARATION,
                                    diagnostics=diagnostics)
        failure = ModelFailure.TRANSPORT
        try:
            response = (await transcript.query(native, payload, tools) if transcript is not None
                        else await native._query(payload, tools, request_max_retries=1))
            logger.debug("[CompanionV2][开发者追踪] 模型原始回复 provider=%s response=%s",
                         self.provider_id, _developer_completion(response))
            raw = transcript.usage_receipt if transcript is not None and transcript.usage_receipt else (observed[-1] if observed else None)
            usage = self._usage(raw)
            receipt = self._receipt(raw, receipt)
            failure = ModelFailure.PROVIDER_RECHECK
            self._current()
            failure = ModelFailure.ROLE_RECHECK
            await self.bridge.verify_role(envelope.original.event.scope, envelope.original.role_binding,
                                          envelope.original.role_instruction)
            failure = ModelFailure.WIRE_DECODE
            if wire.output_format == "memory_reflection":
                logger.debug("[CompanionV2][开发者追踪] 模型正文处理 provider=%s stage=captured body=%s",
                             self.provider_id, _developer_completion(observed[-1]))
                return ProviderResponse("generated", captured_output=capture(observed[-1]), usage=usage, receipt_ref=receipt,
                                        diagnostics=replace(diagnostics, parse_state="captured"))
            if verified_refusal:
                logger.debug("[CompanionV2][开发者追踪] 模型正文处理 provider=%s stage=refusal",
                             self.provider_id)
                return ProviderResponse("generated", captured_output=CapturedModelOutput("", "refusal"),
                                        usage=usage, receipt_ref=receipt, diagnostics=replace(diagnostics, parse_state="refusal"))
            draft, calls = decode_response(response, wire)
            logger.debug("[CompanionV2][开发者追踪] 模型正文处理 provider=%s stage=decoded body=%r claims=%r tool_calls=%r",
                         self.provider_id, draft.text if draft is not None else None,
                         draft.claims if draft is not None else None, calls)
            return ProviderResponse("generated", draft=draft, tool_calls=calls, usage=usage, receipt_ref=receipt,
                diagnostics=replace(diagnostics, parse_state="tools" if calls else "validated",
                                    visible=ResponseTextSummary.from_text(draft.text) if draft is not None else None))
        except Exception as error:
            logger.debug("[CompanionV2][开发者追踪] 模型回复处理失败 provider=%s stage=%s error_type=%s",
                         self.provider_id, failure.value, type(error).__name__, exc_info=True)
            raw = transcript.usage_receipt if transcript is not None and transcript.usage_receipt else (observed[-1] if observed else None)
            if transcript is not None and transcript.ended and transcript.finish == "content_filter":
                try:
                    self._current()
                    await self.bridge.verify_role(envelope.original.event.scope, envelope.original.role_binding,
                                                  envelope.original.role_instruction)
                except Exception:
                    failure = ModelFailure.ROLE_RECHECK
                else:
                    return ProviderResponse("generated", captured_output=CapturedModelOutput("", "refusal"),
                                            usage=self._usage(raw), receipt_ref=self._receipt(raw, receipt),
                                            diagnostics=replace(diagnostics, parse_state="refusal"))
            if parse_failed and verified_refusal:
                try:
                    self._current()
                    await self.bridge.verify_role(envelope.original.event.scope, envelope.original.role_binding,
                                                  envelope.original.role_instruction)
                except Exception:
                    failure = ModelFailure.ROLE_RECHECK
                else:
                    return ProviderResponse("generated", captured_output=CapturedModelOutput("", "refusal"),
                                            usage=self._usage(raw), receipt_ref=self._receipt(raw, receipt),
                                            diagnostics=replace(diagnostics, parse_state="refusal"))
            final_failure = ModelFailure.NATIVE_PARSE if parse_failed else failure
            diagnostics = replace(diagnostics, failure=final_failure,
                parse_state="contract_rejected" if final_failure is ModelFailure.WIRE_DECODE else diagnostics.parse_state)
            task_error_code = error.code if isinstance(error, TaskError) else "unavailable"
            if (not isinstance(task_error_code, str)
                    or re.fullmatch(r"[a-z0-9_.-]{1,80}", task_error_code) is None):
                task_error_code = "unavailable"
            status_code = getattr(error, "status_code", None)
            if type(status_code) is not int or not 100 <= status_code <= 599:
                status_code = "unavailable"
            error_type = type(error).__name__
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", error_type) is None:
                error_type = None
            diagnostics = replace(diagnostics, error_type=error_type,
                error_code=task_error_code if task_error_code != "unavailable" else None,
                status_code=status_code if type(status_code) is int else None)
            if (final_failure is ModelFailure.TRANSPORT and raw is None
                    and transcript is None and definitely_not_sent(error)):
                logger.warning("[CompanionV2] 模型连接未建立，请求未发送 provider=%s error_type=%s",
                               self.provider_id, error_type)
                return ProviderResponse("not_started", usage=Amount(0, 0), receipt_ref=receipt,
                                        failure=final_failure, diagnostics=diagnostics)
            logger.warning(
                "[CompanionV2] 模型适配器结果未知 provider=%s phase=%s failure=%s "
                "error_type=%s task_error_code=%s status_code=%s completion_present=%s "
                "finish_reason=%s parse_state=%s raw_chars=%s parsed_chars=%s",
                self.provider_id, final_failure.document()["phase"], final_failure.value,
                type(error).__name__, task_error_code, status_code, diagnostics.completion_present,
                diagnostics.finish_reason, diagnostics.parse_state,
                diagnostics.raw.chars if diagnostics.raw is not None else "unavailable",
                diagnostics.parsed.chars if diagnostics.parsed is not None else "unavailable")
            return ProviderResponse("unknown", usage=self._usage(raw), receipt_ref=self._receipt(raw, receipt),
                                    failure=final_failure, diagnostics=diagnostics)

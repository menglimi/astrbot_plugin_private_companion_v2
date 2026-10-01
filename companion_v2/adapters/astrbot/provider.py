"""One-attempt text transport for the verified AstrBot OpenAI-compatible class.

No host import or registration occurs here. This adapter bypasses text_chat's
outer ten-attempt loop and disables the SDK retry layer on a private client view.
The V2 gateway alone owns tool execution, fallback and durable accounting.
"""

from copy import copy, deepcopy
from dataclasses import dataclass
from uuid import uuid4

from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.model_gateway.failures import ModelFailure
from companion_v2.model_gateway.models import Amount, CapturedModelOutput, LocalProvider, ProviderResponse

from .model_wire import build_wire, decode_response
from .native import check_version, native_id
from .memory_output import capture, explicit_refusal, response_format
from .streaming import StreamTranscript


RESERVED_EXTRA = frozenset({"model", "messages", "tools", "functions", "function_call", "tool_choice",
    "stream", "stream_options", "max_tokens", "max_completion_tokens", "max_output_tokens", "n",
    "response_format", "extra_body"})


def provider_fingerprint(native):
    """Read-only identity of the selected configuration, without returning secrets."""
    return digest([native.provider_config, native.get_model(), sorted(native.default_params)])


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
            native_id(read(raw, "id"))
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
        try:
            wire = build_wire(envelope, model_name=envelope.model_override or self.model)
            self._estimate(envelope, wire)
            await self.bridge.verify_role(envelope.original.event.scope, envelope.original.role_binding,
                                          envelope.original.role_instruction)
            self._current()
            native = copy(self.native)
            native.provider_config = deepcopy(self.config)
            native.client = self.client.with_options(max_retries=0)
            if native.client.max_retries != 0:
                raise ValueError("client retry layer could not be disabled")
            streaming = self.streaming if envelope.original.streaming is None else envelope.original.streaming
            if streaming and envelope.original.output_format == "conversation":
                if not callable(getattr(native, "_query_stream", None)):
                    raise ValueError("native streaming transport is unavailable")
                transcript = StreamTranscript(native.client)
            tools = self.tool_set_type(tools=[self.function_tool_type(**t, handler=None) for t in wire.tools]) if wire.tools else None

            async def parse(completion, offered):
                # Retain actual usage even if the host parser rejects an empty/filtered result.
                nonlocal parse_failed, verified_refusal
                observed.append(completion)
                if transcript is not None:
                    transcript.verify(completion)
                verified_refusal = explicit_refusal(completion) or bool(transcript and transcript.refusal)
                if wire.output_format == "memory_reflection":
                    # Memory owns parsing and a durable recovery queue. Keep the
                    # provider's original text and completion reason, even when
                    # a native text parser would reject an empty/refused reply.
                    return completion
                try:
                    return await self.provider_type._parse_openai_completion(native, completion, offered)
                except Exception:
                    parse_failed = True
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
            self._current()
            if envelope.before_dispatch is None:
                raise ValueError("native model dispatch requires the live owner's fence")
            envelope.before_dispatch()
        except Exception:
            return ProviderResponse("not_started", usage=Amount(0, 0), receipt_ref=receipt,
                                    failure=ModelFailure.PREPARATION)
        failure = ModelFailure.TRANSPORT
        try:
            response = (await transcript.query(native, payload, tools) if transcript is not None
                        else await native._query(payload, tools, request_max_retries=1))
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
                return ProviderResponse("generated", captured_output=capture(observed[-1]), usage=usage, receipt_ref=receipt)
            if verified_refusal:
                return ProviderResponse("generated", captured_output=CapturedModelOutput("", "refusal"),
                                        usage=usage, receipt_ref=receipt)
            draft, calls = decode_response(response, wire)
            return ProviderResponse("generated", draft=draft, tool_calls=calls, usage=usage, receipt_ref=receipt)
        except Exception:
            raw = transcript.usage_receipt if transcript is not None and transcript.usage_receipt else (observed[-1] if observed else None)
            if parse_failed and verified_refusal:
                try:
                    self._current()
                    await self.bridge.verify_role(envelope.original.event.scope, envelope.original.role_binding,
                                                  envelope.original.role_instruction)
                except Exception:
                    failure = ModelFailure.ROLE_RECHECK
                else:
                    return ProviderResponse("generated", captured_output=CapturedModelOutput("", "refusal"),
                                            usage=self._usage(raw), receipt_ref=self._receipt(raw, receipt))
            return ProviderResponse("unknown", usage=self._usage(raw), receipt_ref=self._receipt(raw, receipt),
                                    failure=ModelFailure.NATIVE_PARSE if parse_failed else failure)

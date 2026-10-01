"""Trusted model task contracts. Usage and reservations have different meanings."""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import json
from typing import Awaitable, Callable

from companion_v2.conversation.foreground import ModelDraft, PromptRequest
from companion_v2.execution.models import Lane, ProviderBinding, encode
from companion_v2.identity_policy.models import _opaque

from .failures import ModelFailure


MAX_TOOL_CATALOG = 64


@dataclass(frozen=True)
class Amount:
    tokens: int
    cost_microusd: int
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_creation_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self):
        for value in (self.tokens, self.cost_microusd):
            if type(value) is not int or not 0 <= value <= 10**12:
                raise ValueError("usage must be bounded integer tokens and millionths of USD")
        for value in (self.input_tokens, self.cached_input_tokens, self.cache_creation_tokens, self.output_tokens):
            if value is not None and (type(value) is not int or not 0 <= value <= 10**12):
                raise ValueError("usage detail must be a bounded nonnegative token count")
        if (self.input_tokens is not None and self.cached_input_tokens is not None
                and self.cached_input_tokens > self.input_tokens):
            raise ValueError("cached input cannot exceed reported input")
        if (self.input_tokens is not None and self.cache_creation_tokens is not None
                and self.cached_input_tokens is not None
                and self.cached_input_tokens + self.cache_creation_tokens > self.input_tokens):
            raise ValueError("cache usage details cannot exceed reported input")


@dataclass(frozen=True)
class BudgetPolicy:
    installation: Amount
    bot: Amount
    role: Amount
    window: Amount
    background: Amount

    def __post_init__(self):
        if not all(isinstance(value, Amount) for value in (
                self.installation, self.bot, self.role, self.window, self.background)):
            raise ValueError("all daily budget ceilings must be explicit")
        if (self.background.tokens > self.installation.tokens
                or self.background.cost_microusd > self.installation.cost_microusd):
            raise ValueError("background ceiling cannot exceed the installation ceiling")


@dataclass(frozen=True)
class ModelTaskProfile:
    kind: str
    lane: Lane
    default_provider: str
    default_prompt: str
    default_fallback: str = ""
    max_output_tokens: int = 1024
    capabilities: tuple[str, ...] = ("text",)
    version: str = "1"
    replacement_rules: str = "[]"
    fallback_on_refusal: bool = False
    timeout_seconds: int = 60
    replacement_scope: str = "all"

    def __post_init__(self):
        for name in ("kind", "default_provider", "version"):
            _opaque(getattr(self, name), field=name)
        if not isinstance(self.lane, Lane) or not isinstance(self.default_prompt, str):
            raise ValueError("model tasks require an explicit lane and task prompt")
        if type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= 32768:
            raise ValueError("output ceiling is outside the local model profile")
        if self.default_fallback:
            _opaque(self.default_fallback, field="default_fallback")
        if not isinstance(self.default_fallback, str):
            raise ValueError("fallback must be an identifier or explicit empty string")
        if not self.capabilities or len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("model capabilities must be nonempty and unique")
        for capability in self.capabilities:
            _opaque(capability, field="model capability")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        from .replacement_rules import checked_rules
        checked_rules(self.replacement_rules)
        if type(self.fallback_on_refusal) is not bool:
            raise ValueError("refusal replacement must be an explicit boolean")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 600:
            raise ValueError("model timeout must be between 1 and 600 seconds")
        if self.replacement_scope not in ("all", "plugin", "conversation"):
            raise ValueError("replacement scope must name a supported task class")

    @property
    def group(self) -> str:
        return "model." + self.kind


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    action: str
    arguments_json: str

    def __post_init__(self):
        _opaque(self.call_id, field="tool call ID")
        _opaque(self.action, field="tool action")
        if not isinstance(self.arguments_json, str) or len(self.arguments_json) > 16384:
            raise ValueError("tool arguments must be bounded JSON")
        arguments = json.loads(self.arguments_json)
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be a JSON object")
        canonical = encode(arguments)
        if len(canonical) > 16384:
            raise ValueError("canonical tool arguments exceed the local limit")
        object.__setattr__(self, "arguments_json", canonical)


@dataclass(frozen=True)
class ToolSpec:
    action: str
    description: str
    parameters_json: str


@dataclass(frozen=True)
class ToolExchange:
    call: ToolCall
    result_json: str


@dataclass(frozen=True)
class ModelEnvelope:
    original: PromptRequest
    task_prompt: str
    max_output_tokens: int
    configuration_token: str
    tools: tuple[ToolSpec, ...] = ()
    tool_history: tuple[ToolExchange, ...] = ()
    # Ephemeral owner fence, never serialized or sent to the model. Native
    # adapters call it after asynchronous host preparation, just before I/O.
    before_dispatch: Callable[[], object] | None = field(default=None, compare=False, repr=False)
    model_override: str = ""
    provider_capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapturedModelOutput:
    """Unvalidated private output; receiving it does not authorize a fact write."""

    text: str = field(repr=False)
    finish_reason: str = "stop"

    def __post_init__(self):
        if not isinstance(self.text, str) or len(self.text) > 65536:
            raise ValueError("captured model output must be bounded text")
        if self.finish_reason not in ("stop", "length", "refusal", "invalid", "oversized"):
            raise ValueError("captured output requires a known completion classification")


@dataclass(frozen=True)
class ProviderResponse:
    status: str
    draft: ModelDraft | None = None
    usage: Amount | None = None
    receipt_ref: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    failure: ModelFailure | None = None
    captured_output: CapturedModelOutput | None = None

    def __post_init__(self):
        if self.status not in ("generated", "not_started", "unknown"):
            raise ValueError("provider result requires an explicit processing outcome")
        if self.failure is not None and (
                not isinstance(self.failure, ModelFailure) or self.status == "generated"):
            raise ValueError("only unsuccessful responses may carry a fixed failure classification")
        if (not isinstance(self.tool_calls, tuple) or len(self.tool_calls) > 8 or
                any(not isinstance(call, ToolCall) for call in self.tool_calls) or
                len({call.call_id for call in self.tool_calls}) != len(self.tool_calls)):
            raise ValueError("a model round may request at most eight distinct structured tools")
        if self.status == "generated":
            if (self.draft is not None and not isinstance(self.draft, ModelDraft)) or (
                    self.captured_output is not None and not isinstance(self.captured_output, CapturedModelOutput)) or (
                    sum((self.draft is not None, bool(self.tool_calls), self.captured_output is not None)) != 1):
                raise ValueError("a generated response contains one draft, tool round or private captured output")
        elif self.draft is not None or self.tool_calls or self.captured_output is not None:
            raise ValueError("unprocessed responses cannot contain a draft or tools")
        if self.usage is not None and (not isinstance(self.usage, Amount) or self.receipt_ref is None):
            raise ValueError("actual usage requires an adapter receipt")
        if self.receipt_ref is not None:
            _opaque(self.receipt_ref, field="provider receipt")
        if self.status == "not_started" and self.usage != Amount(0, 0):
            raise ValueError("fallback requires explicit zero usage and no processing")


@dataclass(frozen=True)
class LocalProvider:
    binding: ProviderBinding
    capabilities: tuple[str, ...]
    maximum_output_tokens: int
    reserve: Callable[[ModelEnvelope], Amount]
    generate: Callable[[ModelEnvelope], Awaitable[ProviderResponse]]
    transport: str = "local_test_adapter"
    default_streaming: bool = False
    supports_model_override: bool = False
    # 这一层实际会用的模型标识（适配器读宿主 get_model() 得来）。
    # 管理面把 provider 列成一个 id 时，多个同类型 provider 看起来完全一样，
    # 选错只能靠试。带上模型名才区分得开，这也是 V1 面板一直在显示的字段。
    #
    # 允许空串而不是必填：本地测试适配器和部分第三方传输没有"模型"这个概念，
    # 让它们编一个名字出来，比让它们留空更糟。
    model: str = ""

    def __post_init__(self):
        if type(self.default_streaming) is not bool:
            raise ValueError("provider stream default must be explicit")
        _opaque(self.transport, field="model transport")
        if type(self.model) is not str:
            raise ValueError("provider model identifier must be a string")
        if self.model:
            _opaque(self.model, field="provider model")
        if not isinstance(self.binding, ProviderBinding) or not inspect.iscoroutinefunction(self.generate):
            raise ValueError("local provider requires a binding and a cooperative async handler")
        if not callable(self.reserve) or inspect.iscoroutinefunction(self.reserve):
            raise ValueError("reservation estimator must be a bounded synchronous adapter function")
        if type(self.maximum_output_tokens) is not int or not 1 <= self.maximum_output_tokens <= 32768:
            raise ValueError("provider output limit must be explicit")
        if not self.capabilities or len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("provider capabilities must be explicit and unique")
        for capability in self.capabilities:
            _opaque(capability, field="provider capability")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        if type(self.supports_model_override) is not bool:
            raise ValueError("model override support must be explicit")


@dataclass(frozen=True)
class ModelCompletion:
    call_id: str
    draft: ModelDraft | None
    usage_known: bool
    tool_calls: tuple[ToolCall, ...] = ()
    captured_output: CapturedModelOutput | None = None

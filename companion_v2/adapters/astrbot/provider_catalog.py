"""Explicit additional native model adapters, with independent limits and tariffs."""

from dataclasses import dataclass

from companion_v2.execution.models import ProviderBinding, TaskError
from .provider import AstrBotTextProvider, UsageTariff, provider_fingerprint


@dataclass(frozen=True)
class TextProviderSettings:
    provider_id: str
    tariff: UsageTariff
    maximum_output_tokens: int = 2048
    maximum_input_estimate: int = 131072
    output_parameter: str = "max_tokens"
    streaming: bool = False

    def __post_init__(self):
        if (type(self.provider_id) is not str or not self.provider_id.strip()
                or self.provider_id != self.provider_id.strip() or len(self.provider_id) > 512
                or not isinstance(self.tariff, UsageTariff)
                or type(self.maximum_output_tokens) is not int or not 1 <= self.maximum_output_tokens <= 32768
                or type(self.maximum_input_estimate) is not int or not 1024 <= self.maximum_input_estimate <= 1000000
                or self.output_parameter not in ("max_tokens", "max_completion_tokens")
                or type(self.streaming) is not bool):
            raise ValueError("invalid additional model provider profile")


def assemble_providers(context, *, bridge, native_types, primary_id, additional=()):
    ids = [primary_id, *(item.provider_id for item in additional)]
    if len(ids) != len(set(ids)):
        raise ValueError("additional model providers must have distinct IDs")
    adapters = []
    for item in additional:
        native = context.get_provider_by_id(item.provider_id)
        if type(native) is not native_types.provider:
            raise TaskError("host_provider_unavailable", "an additional model has no verified native adapter")
        adapter = AstrBotTextProvider(context, bridge=bridge,
            binding=ProviderBinding("model.text", item.provider_id, native_types.version, provider_fingerprint(native)),
            provider_id=item.provider_id, version=native_types.version, provider_type=native_types.provider,
            function_tool_type=native_types.function_tool, tool_set_type=native_types.tool_set,
            tariff=item.tariff, maximum_output_tokens=item.maximum_output_tokens,
            maximum_input_estimate=item.maximum_input_estimate, output_parameter=item.output_parameter,
            streaming=item.streaming)
        if adapter.native is not native:
            raise TaskError("host_provider_changed", "additional model changed during assembly")
        adapter._current()
        adapters.append(adapter)
    return tuple(adapters)

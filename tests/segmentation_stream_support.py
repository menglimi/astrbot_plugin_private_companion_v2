"""Real AstrBot/OpenAI parsing with an offline, cancellable response stream."""

import inspect
from types import SimpleNamespace as NS

# This fixture redirects SDK import-time storage into a temporary directory.
from tests import test_astrbot_staging_host as host_support
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from openai.resources.chat.completions import AsyncCompletions
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from companion_v2.adapters.astrbot.provider import AstrBotTextProvider, UsageTariff
from tests.native_adapter_support import NativeFixture, final_text


USAGE = dict(prompt_tokens=30, completion_tokens=10, total_tokens=40,
             prompt_tokens_details={"cached_tokens": 10})


def chunk(content=None, *, finish=None, tools=None, usage=None, identifier="stream-1", reasoning=None, refusal=None):
    delta = {"content": content, "tool_calls": tools}
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    if refusal is not None:
        delta["refusal"] = refusal
    choices = [] if usage is not None and content is None and finish is None else [dict(index=0, delta=delta, finish_reason=finish)]
    return ChatCompletionChunk.model_validate(dict(id=identifier, model="fixture", created=1,
        object="chat.completion.chunk", choices=choices, usage=usage))


def text_chunks(text, *, size=1, finish="stop", usage=True):
    result = [chunk(text[index:index + size]) for index in range(0, len(text), size)]
    if finish is not None:
        result.append(chunk(finish=finish))
    if usage:
        result.append(chunk(usage=USAGE))
    return result


class ScriptedStream:
    def __init__(self, items):
        self.items = items
        self.closed = False
        self.iterator = self._iterate()

    async def _iterate(self):
        for item in self.items:
            if isinstance(item, BaseException):
                raise item
            if callable(item):
                item = await item()
            if item is not None:
                yield item

    def __aiter__(self):
        return self.iterator

    async def close(self):
        self.closed = True
        await self.iterator.aclose()


class ScriptedClient:
    def __init__(self, state=None, *, max_retries=2):
        self.state = state or NS(calls=[], streams=[], behavior=None, text=final_text())
        self.max_retries = max_retries
        self.base_url = NS(host="fixture.invalid")
        self.chat = NS(completions=NS(create=self.create))

    def with_options(self, *, max_retries):
        return ScriptedClient(self.state, max_retries=max_retries)

    async def create(self, **kwargs):
        assert self.max_retries == 0
        self.state.calls.append(kwargs)
        if not kwargs["stream"]:
            return ChatCompletion.model_validate(dict(id="whole-1", model="fixture", created=1,
                object="chat.completion", usage=USAGE, choices=[dict(index=0, finish_reason="stop",
                    message=dict(role="assistant", content=self.state.text))]))
        items = await self.state.behavior(kwargs) if self.state.behavior else text_chunks(self.state.text)
        stream = ScriptedStream(items)
        self.state.streams.append(stream)
        return stream


def native_provider():
    # Construction avoids creating even an HTTP client. All preparation, stream
    # accumulation, final parsing and tool descriptors use the installed SDK.
    provider = ProviderOpenAIOfficial.__new__(ProviderOpenAIOfficial)
    provider.provider_config = {"id": "native-model", "type": "openai_chat_completion",
                                "model": "fixture", "custom_extra_body": {}}
    provider.model_name = "fixture"
    provider.reasoning_key = "reasoning_content"
    provider.default_params = inspect.signature(AsyncCompletions.create).parameters.keys()
    provider.client = ScriptedClient()
    return provider


class StreamingFixture(NativeFixture):
    def setUp(self):
        super().setUp()
        self.native.provider = native_provider()
        self.native_model = self.real_model()
        self.client_state = self.native.provider.client.state

    def real_model(self, *, streaming=True):
        return AstrBotTextProvider(self.native, bridge=self.bridge, binding=self.providers[0].binding,
            provider_id="native-model", version="4.27.2", provider_type=ProviderOpenAIOfficial,
            function_tool_type=FunctionTool, tool_set_type=ToolSet,
            tariff=UsageTariff(2000000, 1000000, 4000000), maximum_output_tokens=100, streaming=streaming)

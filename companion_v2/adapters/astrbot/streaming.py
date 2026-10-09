"""Audit raw streaming chunks before AstrBot's lossy compatibility parser.

The native SDK still assembles the final completion. This transcript detects
missing ends, swallowed accumulator failures and mismatched tool arguments;
incremental content is offered only to the reply owner's structured decoder.
"""

from contextlib import aclosing
from types import SimpleNamespace

from .native import native_id


class StreamTranscript:
    def __init__(self, client, on_content=None):
        self.client = client
        self.stream = None
        self.response_id = None
        self.finish = None
        self.ended = False
        self.content = []
        self.calls = {}
        self.chars = 0
        self.chunks = 0
        self.usage_receipt = None
        self.refusal = False
        self.on_content = on_content

    def _fragment(self, value):
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("invalid stream fragment")
        self.chars += len(value)
        if self.chars > 1048576:
            raise ValueError("stream exceeds the bounded transcript")
        return value

    def observe(self, chunk):
        self.chunks += 1
        if self.chunks > 262144:
            raise ValueError("stream has too many chunks")
        identifier = native_id(chunk.id)
        if self.response_id is None:
            self.response_id = identifier
        if identifier != self.response_id or len(chunk.choices) > 1:
            raise ValueError("stream changed response identity or choice")
        choice = chunk.choices[0] if chunk.choices else None
        usage = getattr(chunk, "usage", None) or getattr(choice, "usage", None)
        if usage is not None:
            if isinstance(usage, dict):
                details = usage.get("prompt_tokens_details")
                input_details = usage.get("input_tokens_details")
                usage = SimpleNamespace(prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"), total_tokens=usage.get("total_tokens"),
                    prompt_tokens_details=SimpleNamespace(**details) if isinstance(details, dict) else details,
                    input_tokens_details=SimpleNamespace(**input_details) if isinstance(input_details, dict) else input_details,
                    cache_read_input_tokens=usage.get("cache_read_input_tokens"),
                    prompt_cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
                    cache_creation_input_tokens=usage.get("cache_creation_input_tokens"),
                    cache_creation_tokens=usage.get("cache_creation_tokens"),
                    cache_creation=SimpleNamespace(**usage["cache_creation"])
                        if isinstance(usage.get("cache_creation"), dict) else usage.get("cache_creation"))
            self.usage_receipt = SimpleNamespace(id=identifier, usage=usage)
        if choice is None:
            return
        if choice.index != 0:
            raise ValueError("stream changed choice index")
        delta = choice.delta
        if delta is not None:
            content = self._fragment(delta.content)
            calls = getattr(delta, "tool_calls", None) or ()
            refusal = self._fragment(getattr(delta, "refusal", None))
            self.refusal = self.refusal or bool(refusal)
            # Count reasoning too, but never expose it as user-visible content.
            reasoning = self._fragment(getattr(delta, "reasoning_content", None))
            if self.finish is not None and (content or calls or refusal or reasoning):
                raise ValueError("stream continued after its completion")
            self.content.append(content)
            for position, call in enumerate(calls):
                index = getattr(call, "index", None)
                # Match the native adapter's Gemini/proxy compatibility rule.
                index = position if index is None else index
                if type(index) is not int or not 0 <= index < 8:
                    raise ValueError("stream tool index is unbounded")
                item = self.calls.setdefault(index, {"id": [], "name": [], "arguments": []})
                item["id"].append(self._fragment(getattr(call, "id", None)))
                kind = getattr(call, "type", None)
                if kind not in (None, "function"):
                    raise ValueError("stream contains an unsupported tool")
                function = getattr(call, "function", None)
                if function:
                    for field in ("name", "arguments"):
                        item[field].append(self._fragment(getattr(function, field, None)))
        finish = choice.finish_reason
        if finish is not None:
            if self.finish is not None or finish not in ("stop", "tool_calls", "length", "content_filter"):
                raise ValueError("stream has an invalid completion boundary")
            self.finish = finish

    async def create(self, **kwargs):
        if self.stream is not None or kwargs.get("stream") is not True:
            raise ValueError("stream transport must make exactly one streaming request")
        self.stream = await self.client.chat.completions.create(**kwargs)

        async def chunks():
            async for chunk in self.stream:
                self.observe(chunk)
                choice = chunk.choices[0] if chunk.choices else None
                if (self.on_content is not None and choice is not None and choice.delta is not None
                        and choice.delta.content and not self.calls and not self.refusal):
                    await self.on_content(choice.delta.content)
                yield chunk
            self.ended = True
        return chunks()

    def client_view(self):
        # Keep native preparation helpers' ordinary client properties accessible.
        transcript = self

        class ClientView:
            chat = SimpleNamespace(completions=SimpleNamespace(create=transcript.create))

            def __getattr__(self, name):
                return getattr(transcript.client, name)
        return ClientView()

    def verify(self, raw):
        if not self.ended or self.finish is None or len(raw.choices) != 1:
            raise ValueError("stream never completed")
        choice = raw.choices[0]
        if (raw.id != self.response_id or choice.finish_reason != self.finish
                or (choice.message.content or "") != "".join(self.content)):
            raise ValueError("native stream assembly lost or changed content")
        calls = choice.message.tool_calls or ()
        if sorted(self.calls) != list(range(len(calls))):
            raise ValueError("native stream assembly lost a tool")
        for index, call in enumerate(calls):
            expected = {key: "".join(value) for key, value in self.calls[index].items()}
            if (call.id != expected["id"] or call.function.name != expected["name"]
                    or call.function.arguments != expected["arguments"] or call.type != "function"):
                raise ValueError("native stream assembly changed a tool")

    async def query(self, native, payload, tools):
        native.client = self.client_view()
        final = None
        try:
            async with aclosing(native._query_stream(payload, tools, request_max_retries=1)) as responses:
                async for response in responses:
                    if getattr(response, "is_chunk", False):
                        continue
                    if final is not None:
                        raise ValueError("native stream emitted multiple final responses")
                    final = response
            if final is None:
                raise ValueError("native stream ended without a complete response")
            return final
        finally:
            if self.stream is not None:
                await self.stream.close()

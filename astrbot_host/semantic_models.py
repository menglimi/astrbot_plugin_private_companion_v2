"""AstrBot embedding, rerank and visual-analysis ports; no provider secrets leave here."""

import inspect
import json
import os

from companion_v2.execution.models import TaskError, digest


SLANG_SEARCH_ENV = ("COMPANION_V2_SLANG_SEARCH_URL", "COMPANION_V2_SLANG_SEARCH_API_KEY",
                    "COMPANION_V2_SLANG_SEARCH_AUTH_HEADER", "COMPANION_V2_SLANG_SEARCH_AUTH_SCHEME")


async def awaited(value):
    return await value if inspect.isawaitable(value) else value


def _slang_search_results(batch, limit):
    items = getattr(batch, "items", ())
    results = []
    for item in items[:limit]:
        title = str(getattr(item, "title", "") or "").strip()
        if not title:
            continue
        results.append({"title": title[:200], "summary": str(getattr(item, "summary", "") or "").strip()[:400],
                        "source": str(getattr(item, "source", "") or "").strip()[:60]})
    return results


def configured_slang_search_port():
    """Build the reference search port from host environment, or return None when unset.

    Credentials stay in host environment variables exactly like the news source, so no
    secret is ever written into V2 configuration. A missing endpoint is not an error:
    the whole chain silently degrades to "no external reference".
    """
    values = {name: os.environ.get(name, "") for name in SLANG_SEARCH_ENV}
    url = values[SLANG_SEARCH_ENV[0]].strip()
    if not url:
        return None
    return NativeSlangSearch(url, values[SLANG_SEARCH_ENV[1]], values[SLANG_SEARCH_ENV[2]] or "Authorization",
                             values[SLANG_SEARCH_ENV[3]] or "Bearer")


class NativeSlangSearch:
    """Optional external reference search for group vocabulary; off unless an endpoint exists.

    Reuses the news JSON search port rather than adding another HTTP client, but builds one
    port per query because `WebSearchNewsPort` fixes its query at construction and folds it
    into the port fingerprint. Results are reference evidence only and must never overwrite
    an in-group usage.
    """

    def __init__(self, url, api_key="", auth_header="Authorization", auth_scheme="Bearer"):
        if type(url) is not str or not url.strip():
            raise ValueError("slang search needs an endpoint")
        self.url, self.api_key = url.strip(), api_key
        self.auth_header, self.auth_scheme = auth_header, auth_scheme

    @property
    def available(self):
        return True

    async def search(self, term, limit):
        if type(term) is not str or not 0 < len(term.strip()) <= 64:
            raise ValueError("slang search needs a bounded term")
        from .news import WebSearchNewsPort
        result_count = max(1, min(5, int(limit)))
        port = WebSearchNewsPort(url=self.url, query=term.strip(), result_count=result_count,
                                 api_key=self.api_key, auth_header=self.auth_header,
                                 auth_scheme=self.auth_scheme)
        batch = await port.fetch()
        return _slang_search_results(batch, result_count)


class NativeSemanticModels:
    def __init__(self, context, default_analysis="", slang_search=None):
        self.context, self.default_analysis = context, default_analysis
        self.slang_search = slang_search

    def providers(self, kind):
        getter = getattr(self.context, "get_all_providers" if kind == "analysis" else "get_all_" + kind + "_providers", None)
        values = getter() if callable(getter) else ()
        if not values and kind == "rerank":
            values = getattr(getattr(self.context, "provider_manager", None), "rerank_provider_insts", ())
        if isinstance(values, dict):
            values = values.values()
        return tuple(values or ())

    def resolve(self, identifier, kind):
        if kind == "analysis":
            identifier = identifier or self.default_analysis
        provider = None
        if identifier:
            for name in ("get_" + kind + "_provider_by_id", "get_provider_by_id"):
                getter = getattr(self.context, name, None)
                if callable(getter):
                    provider = getter(identifier)
                    if provider is not None:
                        break
        else:
            provider = next(iter(self.providers(kind)), None)
        methods = {"embedding": ("get_embedding", "get_embeddings", "get_embeddings_batch"),
                   "rerank": ("rerank",), "analysis": ("text_chat",)}[kind]
        if provider is None or not any(callable(getattr(provider, method, None)) for method in methods):
            raise TaskError("semantic_provider_unavailable", "no compatible " + kind + " provider is configured")
        return provider

    def binding(self, identifier, kind):
        provider = self.resolve(identifier, kind)
        config = getattr(provider, "provider_config", {})
        return kind + ":" + digest([type(provider).__module__, type(provider).__qualname__, config])

    def inventory(self):
        results = {}
        for kind in ("embedding", "rerank", "analysis"):
            results[kind] = [{"id": str(getattr(p, "provider_config", {}).get("id", "")),
                              "name": str(getattr(p, "provider_config", {}).get("id", ""))}
                             for p in self.providers(kind)]
        return results

    async def embed(self, identifier, texts):
        provider = self.resolve(identifier, "embedding")
        if callable(getattr(provider, "get_embeddings", None)):
            values = await awaited(provider.get_embeddings(texts))
        elif callable(getattr(provider, "get_embeddings_batch", None)):
            values = await awaited(provider.get_embeddings_batch(texts))
        else:
            values = [await awaited(provider.get_embedding(text)) for text in texts]
        if isinstance(values, dict):
            values = values.get("data", values.get("embeddings", values.get("vectors")))
        if not isinstance(values, (list, tuple)):
            values = getattr(values, "data", ())
        if values and all(isinstance(x, dict) and "index" in x for x in values):
            if sorted(x["index"] for x in values) != list(range(len(texts))):
                raise ValueError("embedding response indices mismatch")
            values = sorted(values, key=lambda x: x["index"])
        return values

    async def rerank(self, identifier, query, documents):
        provider = self.resolve(identifier, "rerank")
        value = await awaited(provider.rerank(query=query, documents=documents))
        if isinstance(value, dict):
            value = value.get("results", value.get("data"))
        if not isinstance(value, (list, tuple)):
            value = getattr(value, "results", ())
        scores = [0.0] * len(documents)
        seen = set()
        for result in value:
            index = result.get("index") if isinstance(result, dict) else getattr(result, "index", None)
            score = result.get("relevance_score", result.get("score")) if isinstance(result, dict) else getattr(result, "relevance_score", None)
            if type(index) is not int or index in seen or not 0 <= index < len(documents):
                raise ValueError("rerank response indices mismatch")
            scores[index] = score
            seen.add(index)
        if len(seen) != len(documents):
            raise ValueError("incomplete rerank response")
        return scores

    async def analyze(self, identifier, prompt, images=()):
        provider = self.resolve(identifier, "analysis")
        kwargs = {"prompt": prompt, "max_tokens": 1400}
        if images:
            kwargs["image_urls"] = list(images)
        response = await awaited(provider.text_chat(**kwargs))
        text = getattr(response, "completion_text", response)
        if not isinstance(text, str) or len(text) > 32000:
            raise ValueError("invalid analysis response")
        text = text.strip()
        if text.startswith("```") and text.endswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

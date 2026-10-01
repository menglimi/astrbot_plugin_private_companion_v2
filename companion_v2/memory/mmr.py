"""Pure maximum marginal relevance ordering for pre-filtered candidates."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import TypeVar


T = TypeVar("T")
Similarity = Callable[[T, T], float]


def _score(value: object, field: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{field} values must be finite numbers")
    return float(value)


def _vectors(values: Sequence[Sequence[float] | None], count: int) -> tuple[tuple[float, ...] | None, ...]:
    if len(values) != count:
        raise ValueError("vectors must align with candidates")
    result = []
    dimensions = None
    for vector in values:
        if vector is None:
            result.append(None)
            continue
        if isinstance(vector, (str, bytes)) or not vector:
            raise ValueError("each vector must have at least one dimension")
        normalized = tuple(_score(value, "vector") for value in vector)
        if dimensions is None:
            dimensions = len(normalized)
        elif len(normalized) != dimensions:
            raise ValueError("vectors must have consistent dimensions")
        result.append(normalized)
    return tuple(result)


def _cosine(left: tuple[float, ...] | None, right: tuple[float, ...] | None) -> float:
    if left is None or right is None:
        return 0.0
    left_norm, right_norm = math.hypot(*left), math.hypot(*right)
    if not left_norm or not right_norm:
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)))


def rank(
    candidates: Sequence[T],
    relevance_scores: Sequence[float],
    *,
    vectors: Sequence[Sequence[float] | None] | None = None,
    similarity: Similarity[T] | None = None,
    lambda_mult: float = 0.7,
    top_k: int | None = None,
) -> tuple[T, ...]:
    """Return a stable MMR ordering without inspecting or changing candidate data.

    Provide either aligned vectors or a pairwise similarity function. Similarity
    values use cosine scale [-1, 1]; absent vectors have neutral similarity 0.
    """
    items = tuple(candidates)
    if len(relevance_scores) != len(items):
        raise ValueError("relevance scores must align with candidates")
    relevance = tuple(_score(value, "relevance") for value in relevance_scores)
    if type(lambda_mult) not in (int, float) or not math.isfinite(lambda_mult) or not 0.0 <= lambda_mult <= 1.0:
        raise ValueError("lambda_mult must be between 0 and 1")
    if top_k is not None and (type(top_k) is not int or top_k < 0):
        raise ValueError("top_k must be a non-negative integer")
    if vectors is not None and similarity is not None:
        raise ValueError("provide vectors or similarity, not both")
    if vectors is None and similarity is None:
        vector_data = None
    else:
        vector_data = _vectors(vectors, len(items)) if vectors is not None else None

    def pair_similarity(left: int, right: int) -> float:
        if vector_data is not None:
            return _cosine(vector_data[left], vector_data[right])
        if similarity is None:
            return 0.0
        value = _score(similarity(items[left], items[right]), "similarity")
        if not -1.0 <= value <= 1.0:
            raise ValueError("similarity values must be between -1 and 1")
        return value

    limit = len(items) if top_k is None else min(top_k, len(items))
    remaining = list(range(len(items)))
    selected: list[int] = []
    while remaining and len(selected) < limit:
        best_index, best_score = remaining[0], None
        for index in remaining:
            redundancy = max((pair_similarity(index, chosen) for chosen in selected), default=0.0)
            score = lambda_mult * relevance[index] - (1.0 - lambda_mult) * redundancy
            if best_score is None or score > best_score:
                best_index, best_score = index, score
        selected.append(best_index)
        remaining.remove(best_index)
    return tuple(items[index] for index in selected)

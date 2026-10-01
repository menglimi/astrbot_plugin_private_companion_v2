"""Turn recorded ratings into taste the role may actually use.

C2-3a. The shelf already stores a rating on each review, so nothing new is
persisted here — what was missing is the aggregation, and the restraint around it:

* a rating only counts once ``preference_min_ratings`` of them exist, so one
  opinion cannot present itself as a preference;
* at most ``preference_max_terms`` terms enter a prompt, and the strongest come
  first, so the material stays bounded;
* the injected block is explicitly a *reference*, not an instruction, and says the
  role may disagree with it.

A rating of ``None`` means "read but not rated" and never contributes.
"""

from __future__ import annotations

from dataclasses import dataclass


PREFERENCE_HEADING = "阅读偏好参考（以下是口味参考，不是本轮要求，可以不同意）："
# A rated work below this contributes nothing: a single low score is closer to a
# mood than to taste.
NEUTRAL_RATING = 3


@dataclass(frozen=True)
class PreferenceTerm:
    """One aggregated taste signal, with the evidence that produced it."""

    term: str
    score: float
    ratings: int

    def __post_init__(self):
        if not isinstance(self.term, str) or not self.term.strip():
            raise ValueError("a preference term requires its text")
        if type(self.ratings) is not int or self.ratings < 1:
            raise ValueError("a preference term requires at least one rating")


def aggregate(reviews, *, min_ratings, max_terms):
    """Fold rated reviews into a bounded, strongest-first list of terms.

    ``reviews`` are ``ArchiveReview`` values; only ``rating`` and the entry they
    belong to are read. Ratings at or above ``NEUTRAL_RATING`` count as fondness,
    lower ones as aversion, and the sign is what makes a term a "more like this" or
    a "less like this" rather than a bare average.
    """
    if type(min_ratings) is not int or min_ratings < 1:
        raise ValueError("preference_min_ratings must be a positive integer")
    if type(max_terms) is not int or max_terms < 1:
        raise ValueError("preference_max_terms must be a positive integer")

    buckets: dict[str, list[int]] = {}
    for review in reviews:
        rating = getattr(review, "rating", None)
        if rating is None:
            continue
        entry_id = getattr(review, "entry_id", "")
        if not isinstance(entry_id, str) or not entry_id:
            continue
        buckets.setdefault(entry_id, []).append(int(rating))
    if not buckets:
        return ()

    total = sum(len(values) for values in buckets.values())
    if total < min_ratings:
        # Below the floor the honest answer is "not enough evidence yet", not a
        # weaker guess.
        return ()

    terms = []
    for entry_id, values in buckets.items():
        count = len(values)
        # Distance from neutral, averaged, keeps a 5 and a 1 from cancelling into
        # "no opinion" when both are strongly held.
        score = sum(value - NEUTRAL_RATING for value in values) / count
        if score == 0:
            continue
        terms.append(PreferenceTerm(entry_id, round(score, 3), count))
    # Strongest signal first; at equal strength a fond term outranks an aversion, so
    # the injected block leads with what the role likes rather than what it avoids.
    terms.sort(key=lambda item: (-abs(item.score), -item.score, item.term))
    return tuple(terms[:max_terms])


def influence_text(terms):
    """The prompt block, or an empty string when there is nothing to say."""
    if not terms:
        return ""
    liked = [item.term for item in terms if item.score > 0]
    disliked = [item.term for item in terms if item.score < 0]
    lines = [PREFERENCE_HEADING]
    if liked:
        lines.append("你更喜欢的作品：" + "、".join(liked))
    if disliked:
        lines.append("你不太喜欢的作品：" + "、".join(disliked))
    return "\n".join(lines)


__all__ = ["NEUTRAL_RATING", "PREFERENCE_HEADING", "PreferenceTerm", "aggregate", "influence_text"]

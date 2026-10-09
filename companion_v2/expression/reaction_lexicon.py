"""Communication-shaped synonym clusters for reaction lookup, without an embedding model.

V1 kept a deliberately small cluster table next to its reaction catalog and used
it twice: a shared cluster added a soft score (``reaction_asset_library.py:45-59``,
``:1298-1305``) and an alias sitting behind a negation such as "不开心" was blocked
from becoming a positive keyword hit (``:57-59``, ``:1162-1169``).  Both behaviours
are migrated here.  The table is prompt material, not an operator bound, so it
stays a module constant instead of a registered configuration field.

Alignment with :func:`companion_v2.memory.search.terms`: V2 tokenises CJK words
into their bigrams, so a naive alias table would score "安慰" twice — once as the
literal bigram and once again as a cluster bonus.  :func:`shared_clusters`
therefore drops clusters whose alias already matched literally on *both* sides,
and :func:`query_terms` drops the bigrams that only exist because a negated alias
was split apart.
"""

import re
from functools import lru_cache

from companion_v2.memory.search import terms


# Same ten communication-oriented clusters as V1; a shared cluster only adds a
# soft score and never replaces an explicit tag or the caller's own intent.
CLUSTERS = {
    "开心喜悦": ("开心", "高兴", "快乐", "愉快", "喜悦", "欢喜", "兴奋", "好耶", "庆祝", "鼓掌"),
    "安慰陪伴": ("安慰", "抱抱", "抱一抱", "陪伴", "哄哄", "哄一下", "心疼", "安抚", "鼓励", "加油", "没关系", "别难过", "别伤心"),
    "无语无奈": ("无语", "无奈", "服了", "不想说话", "说不出话", "沉默", "叹气", "扶额", "摊手"),
    "害羞脸红": ("害羞", "腼腆", "不好意思", "脸红", "扭捏"),
    "难过委屈": ("难过", "伤心", "低落", "委屈", "不开心", "不高兴", "想哭", "哭哭"),
    "惊讶意外": ("惊讶", "震惊", "意外", "吃惊", "啊这"),
    "生气恼火": ("生气", "恼火", "气愤", "发火", "愤怒"),
    "吐槽接梗": ("吐槽", "嫌弃", "质疑", "调侃", "接梗", "开玩笑"),
    "赞同回应": ("赞同", "同意", "认可", "点头", "收到", "可以"),
    "拒绝摇头": ("拒绝", "不要", "才不要", "不行", "摇头", "走开"),
}
NEGATION = re.compile(r"(?:不是|并非|不|没|未|别|莫|无)(?:太|很|怎么|再|够|那么|特别)?$")
_ALIASES = tuple(sorted({alias for aliases in CLUSTERS.values() for alias in aliases}, key=len, reverse=True))


def normalize(value):
    """V1 ``_semantic_features``: keep word characters only, case-folded."""
    return re.sub(r"[\W_]+", "", str(value or "").casefold())


def blocked_aliases(value):
    """Aliases preceded by a negation such as "不开心" or "并不高兴"."""
    text = normalize(value)
    if not text:
        return frozenset()
    blocked = set()
    for alias in _ALIASES:
        start = text.find(alias)
        while start >= 0:
            if NEGATION.search(text[max(0, start - 8):start]):
                blocked.add(alias)
            start = text.find(alias, start + max(1, len(alias)))
    return frozenset(blocked)


def clusters(value):
    """Cluster names reachable through a non-negated alias of ``value``."""
    text = normalize(value)
    if not text:
        return frozenset()
    blocked = blocked_aliases(value)
    return frozenset(name for name, aliases in CLUSTERS.items()
                     if any(alias in text and alias not in blocked for alias in aliases))


@lru_cache(maxsize=128)
def _query_side(value):
    """Per-query features; the scan path asks for the same query once per item."""
    text = normalize(value)
    blocked = {token for alias in blocked_aliases(value) for token in terms(alias)}
    return (clusters(value), frozenset(blocked), text)


def shared_clusters(query, document):
    """Cluster names shared by both texts, minus clusters the lexical layer scored.

    Called per candidate by :class:`~companion_v2.model_gateway.semantic_search.CatalogSearch`,
    so the query side is memoised: a real catalog scan asks the same question once
    per item.
    """
    query_clusters, blocked, query_text = _query_side(query)
    document_text = normalize(document)
    if not query_text or not document_text:
        return ()
    shared = query_clusters & clusters(document)
    return tuple(sorted(name for name in shared
                        if not any(alias in query_text and alias in document_text for alias in CLUSTERS[name])))


def query_terms(value):
    """V2 bigram terms with negated aliases removed (V1 ``find``:1165-1169).

    The bigram split of "不开心" contains "开心"; keeping it would turn a negated
    phrase into the positive keyword hit the negation pattern exists to prevent.
    """
    _clusters, blocked, _text = _query_side(value)
    return tuple(token for token in dict.fromkeys(terms(value))
                 if token not in blocked)

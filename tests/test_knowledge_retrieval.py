from datetime import datetime, timedelta, timezone
from pathlib import Path

from companion_v2.foundation.refs import AudienceRef, ScopeKind, ScopeRef, SubjectKind, SubjectRef
from companion_v2.knowledge.retrieval import (
    InMemoryKnowledgeProvider,
    KnowledgeCandidate,
    KnowledgeRetriever,
    query_for_context,
)
from companion_v2.sources.repositories import SourceRepository
from companion_v2.storage.runtime import StorageRuntime


NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)


def _scope(native_scope_id: str = "private-a") -> ScopeRef:
    return ScopeRef("installation-test", "onebot", ScopeKind.PRIVATE, native_scope_id)


def _subject(subject_id: str = "human-a") -> SubjectRef:
    return SubjectRef("installation-test", SubjectKind.HUMAN, subject_id)


def _query(text: str = "雨天", **kwargs):
    return query_for_context(text, scope=_scope(), role_id="mira", subject=_subject(),
                             audience=(_subject(),), **kwargs)


def test_retrieval_filters_authority_and_has_stable_alias_priority() -> None:
    candidates = (
        KnowledgeCandidate("alias", "米拉喜欢在雨天散步", scope=_scope(), role_id="mira",
                           audience=(_subject(),), name="Mira", aliases=("米拉",)),
        KnowledgeCandidate("wrong-role", "不应被读取", scope=_scope(), role_id="other",
                           audience=(_subject(),), keywords=("雨天",)),
        KnowledgeCandidate("wrong-scope", "不应被读取", scope=_scope("private-b"), role_id="mira",
                           audience=(_subject(),), keywords=("雨天",)),
        KnowledgeCandidate("disabled", "不应被读取", scope=_scope(), role_id="mira",
                           audience=(_subject(),), enabled=False, keywords=("雨天",)),
    )

    selection = KnowledgeRetriever(InMemoryKnowledgeProvider(candidates)).select(_query("米拉"))

    assert [hit.candidate.candidate_id for hit in selection.hits] == ["alias"]
    assert "背景参考" in selection.prompt


def test_retrieval_bounds_documents_deduplicates_neighbors_and_samples_misses() -> None:
    candidates = (
        KnowledgeCandidate("doc-0", "第一段资料", scope=_scope(), role_id="mira",
                           audience=(_subject(),), knowledge_base_id="kb", document_id="doc",
                           chunk_index=0, keywords=("雨天",)),
        KnowledgeCandidate("doc-1", "第二段资料", scope=_scope(), role_id="mira",
                           audience=(_subject(),), knowledge_base_id="kb", document_id="doc",
                           chunk_index=1, keywords=("雨天",)),
        KnowledgeCandidate("doc-2", "第二段资料", scope=_scope(), role_id="mira",
                           audience=(_subject(),), knowledge_base_id="kb", document_id="doc",
                           chunk_index=2, keywords=("雨天",)),
        KnowledgeCandidate("other", "另一份资料", scope=_scope(), role_id="mira",
                           audience=(_subject(),), knowledge_base_id="kb", document_id="other",
                           chunk_index=0, keywords=("雨天",)),
    )
    retriever = KnowledgeRetriever(candidates)

    bounded = retriever.select(_query("雨天", max_hits=3, max_chars=12, max_per_document=1))
    sampled = retriever.select(_query("不存在", max_hits=2, max_chars=100))

    assert [hit.candidate.candidate_id for hit in bounded.hits] == ["doc-0", "other"]
    assert bounded.characters <= 12
    assert sampled.sampled is True
    assert len(sampled.hits) == 2


def test_published_knowledge_is_invalid_after_source_retraction(tmp_path: Path) -> None:
    scope = _scope()
    subject = _subject()
    audience = AudienceRef(scope, (subject,))
    runtime = StorageRuntime.open(data_root=tmp_path / "v2", installation_id=scope.installation_id)
    try:
        sources = SourceRepository(runtime)
        retriever = KnowledgeRetriever((KnowledgeCandidate(
            "entry", "可撤回的背景资料", scope=scope, role_id="mira", audience=(subject,), keywords=("资料",)
        ),))
        selection = retriever.retrieve(_query("资料"), sources=sources, audience=audience, observed_at=NOW)
        reference = selection.hits[0].source
        assert reference is not None
        assert sources.validate_reference(reference, observed_at=NOW).is_success

        revoked = sources.revoke(reference, expected_governance_revision=1, observed_at=NOW + timedelta(minutes=1))

        assert revoked.is_success
        assert sources.validate_reference(reference, observed_at=NOW + timedelta(minutes=1)).failure.code == "source_revoked"
    finally:
        runtime.close()

"""Knowledge parsing, import, authorized retrieval and prompt-material contracts.

Format parsing stays in :mod:`parsing`; import and versioning in :mod:`importer`
and :mod:`catalog`; selection and the "reference, not fact" boundary in
:mod:`retrieval`; member entries as display attribution clues in :mod:`members`;
the turn-facing collaborator in :mod:`context`.
"""

from .catalog import (
    CatalogKnowledgeProvider,
    EntryDocument,
    KnowledgeCatalog,
    MemberEntry,
    SourceBinding,
    SourceVersion,
)
from .configuration import (
    KnowledgeConfigurationOwner,
    KnowledgeSettings,
    configuration_fields as knowledge_configuration_fields,
    read_settings as read_knowledge_settings,
)
from .context import (
    KnowledgeContext,
    MEMBER_CLUE_INSTRUCTION,
    MEMBER_CLUE_PURPOSE,
    as_knowledge_context,
    knowledge_context,
)
from .importer import (
    ImportPlan,
    ImportResult,
    ImportStatus,
    KnowledgeFormat,
    KnowledgeImporter,
    KnowledgeSourceReader,
    KnowledgeSourceSpec,
)
from .members import MemberClue, MemberClueSelection, select_member_clues
from .parsing import KnowledgeChunk, ParseBatch, ParseIssue, WorldbookEntry, parse_knowledge_rows, parse_worldbook
from .retrieval import (
    InMemoryKnowledgeProvider,
    KnowledgeCandidate,
    KnowledgeHit,
    KnowledgeProvider,
    KnowledgeQuery,
    KnowledgeRetriever,
    KnowledgeSelection,
    authorized,
    publish_material,
    query_for_context,
)

__all__ = (
    "KnowledgeChunk",
    "ParseBatch",
    "ParseIssue",
    "WorldbookEntry",
    "parse_knowledge_rows",
    "parse_worldbook",
    "InMemoryKnowledgeProvider",
    "KnowledgeCandidate",
    "KnowledgeHit",
    "KnowledgeProvider",
    "KnowledgeQuery",
    "KnowledgeRetriever",
    "KnowledgeSelection",
    "authorized",
    "publish_material",
    "query_for_context",
    "CatalogKnowledgeProvider",
    "EntryDocument",
    "KnowledgeCatalog",
    "MemberEntry",
    "SourceBinding",
    "SourceVersion",
    "KnowledgeConfigurationOwner",
    "KnowledgeSettings",
    "knowledge_configuration_fields",
    "read_knowledge_settings",
    "KnowledgeContext",
    "MEMBER_CLUE_INSTRUCTION",
    "MEMBER_CLUE_PURPOSE",
    "as_knowledge_context",
    "knowledge_context",
    "ImportPlan",
    "ImportResult",
    "ImportStatus",
    "KnowledgeFormat",
    "KnowledgeImporter",
    "KnowledgeSourceReader",
    "KnowledgeSourceSpec",
    "MemberClue",
    "MemberClueSelection",
    "select_member_clues",
)

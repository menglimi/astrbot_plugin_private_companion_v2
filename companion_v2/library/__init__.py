"""The reading archive: a provider-contract bookshelf of catalog entries and reading state.

The body stores only what it owns: catalog metadata, the source reference pointing at a
provider-held asset, per-entry consent, reading position and reviews. The work's text and
images stay with the provider, so novels and manga arrive through the same contract.
"""

from .models import (ArchiveConsent, ArchiveEntry, ArchiveReview, AssetReference, ConsentState,
                     EntryKind, EntryOrigin, EntryState, ReadingProgress)
from .repositories import ReadingArchiveRepository

__all__ = ["ArchiveConsent", "ArchiveEntry", "ArchiveReview", "AssetReference", "ConsentState",
           "EntryKind", "EntryOrigin", "EntryState", "ReadingArchiveRepository", "ReadingProgress"]

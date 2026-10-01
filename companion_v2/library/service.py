"""Read, review and record against the shelf, under one role-owned identity.

Authorization and scope come from the task context, never from the caller: every write
re-checks the context and reads the role's bookshelf settings at the current time. The
service stores catalog state only; a work's text stays with its provider, and a review
must cite what was actually read.
"""

from __future__ import annotations

from datetime import datetime

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.execution.service import outcome
from companion_v2.foundation.refs import RoleOwnerRef, normalize_utc

from .configuration import LibrarySettings
from .models import (ArchiveConsent, ArchiveEntry, ArchiveReview, AssetReference, ConsentState,
                     EntryKind, EntryOrigin, EntryState, ReadingProgress)
from .preferences import aggregate, influence_text
from .repositories import ReadingArchiveRepository
from .triggers import decide


CATALOG_ACTION = "library.catalog"
READ_ACTION = "library.read"


def role_owner(context):
    return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                        context.role_binding.role.subject_id)


def owner_key(context):
    """The shelf belongs to one role body, not to whichever window is looking at it."""
    return digest(["role-library.v1", role_owner(context)])


class ReadingArchiveService:
    def __init__(self, runtime, tasks, configuration, *, require_running=None):
        if runtime is not tasks.runtime:
            raise ValueError("the shelf must share its original task runtime")
        self.runtime, self.tasks = runtime, tasks
        self.settings = LibrarySettings(configuration)
        self.require_running = require_running
        self.entries = ReadingArchiveRepository(runtime)

    # --- shared guards -----------------------------------------------------------

    def _admit(self, context, action):
        if not isinstance(context, TaskContext):
            raise ValueError("the shelf requires its task context")
        if self.require_running is not None:
            self.require_running()
        now = normalize_utc(self.tasks.now(), field="library observed time")
        require(self.tasks.authorize_context(context, action=action, observed_at=now))
        settings = self.settings.read(context, now)
        if not settings["enabled"]:
            raise TaskError("library_disabled", "the bookshelf is off for this role")
        return now, settings

    def owner(self, context):
        return owner_key(context)

    # --- catalog ----------------------------------------------------------------

    def list_entries(self, context, *, after_id="", state=None, kind=None):
        now, settings = self._admit(context, CATALOG_ACTION)
        return self.entries.list(self.owner(context), after_id=after_id, state=state, kind=kind,
                                 limit=settings["max_entries_per_page"])

    def get_entry(self, context, entry_id):
        self._admit(context, CATALOG_ACTION)
        entry = self.entries.get(self.owner(context), entry_id)
        if entry is None:
            raise TaskError("archive_entry_missing", "the archive entry is unavailable")
        return entry

    @outcome
    def register_provider_entry(self, context, *, entry_id, kind, title, author, source,
                                metadata=(), state=EntryState.AVAILABLE, expected=None):
        """A provider announcing one of the works it supplies."""
        now, _ = self._admit(context, CATALOG_ACTION)
        if not isinstance(source, AssetReference):
            raise ValueError("a provider entry requires its asset reference")
        entry = ArchiveEntry(entry_id=entry_id, kind=EntryKind(kind), title=title, author=author,
                             origin=EntryOrigin.PROVIDER, state=state, revision=1,
                             created_at=now, updated_at=now, source=source,
                             metadata=tuple(sorted(dict(metadata).items())))
        return self.entries.put_entry(self.owner(context), entry, expected=expected)

    @outcome
    def withdraw_provider(self, context, provider_id):
        now, _ = self._admit(context, CATALOG_ACTION)
        return self.entries.withdraw_provider(self.owner(context), provider_id, updated_at=now)

    @outcome
    def add_manual_entry(self, context, *, entry_id, kind, title, author="", metadata=(), expected=None):
        """The operator's own list; never able to override a provider entry."""
        now, settings = self._admit(context, CATALOG_ACTION)
        if not settings["manual_entries_enabled"]:
            raise TaskError("library_manual_disabled", "manual shelf entries are off for this role")
        entry = ArchiveEntry(entry_id=entry_id, kind=EntryKind(kind), title=title, author=author,
                             origin=EntryOrigin.MANUAL, state=EntryState.AVAILABLE, revision=1,
                             created_at=now, updated_at=now, metadata=tuple(sorted(dict(metadata).items())))
        return self.entries.put_entry(self.owner(context), entry, expected=expected)

    @outcome
    def set_state(self, context, entry_id, state, *, expected):
        now, _ = self._admit(context, CATALOG_ACTION)
        return self.entries.set_state(self.owner(context), entry_id, state, expected=expected,
                                      updated_at=now)

    # --- reading state -----------------------------------------------------------

    @outcome
    def record_progress(self, context, entry_id, *, position, percent, note=""):
        now, _ = self._admit(context, READ_ACTION)
        return self.entries.put_progress(self.owner(context), ReadingProgress(
            entry_id=entry_id, position=tuple(sorted(dict(position).items())), percent=percent,
            note=note, updated_at=now))

    def progress(self, context, entry_id):
        self._admit(context, READ_ACTION)
        return self.entries.progress(self.owner(context), entry_id)

    # --- reviews -----------------------------------------------------------------

    @outcome
    def record_review(self, context, *, review_id, entry_id, body, rating, evidence, expected=None):
        now, settings = self._admit(context, READ_ACTION)
        if not settings["reviews_enabled"]:
            raise TaskError("library_reviews_disabled", "reviews are off for this role")
        existing = self.entries.review(self.owner(context), review_id)
        created = existing.created_at if existing else now
        review = ArchiveReview(review_id=review_id, entry_id=entry_id, body=body, rating=rating,
                               evidence=tuple(evidence), revision=1, created_at=created, updated_at=now)
        return self.entries.put_review(self.owner(context), review, expected=expected)

    def reviews(self, context, entry_id):
        self._admit(context, READ_ACTION)
        return self.entries.reviews(self.owner(context), entry_id)

    # --- consent -----------------------------------------------------------------

    @outcome
    def set_consent(self, context, entry_id, *, subject, granted):
        now, _ = self._admit(context, CATALOG_ACTION)
        reference = subject if type(subject) is str else digest([subject])
        return self.entries.put_consent(self.owner(context), ArchiveConsent(
            entry_id=entry_id, subject_json=reference,
            state=ConsentState.GRANTED if granted else ConsentState.REVOKED,
            revision=1, updated_at=now))

    def consent(self, context, entry_id, *, subject):
        self._admit(context, CATALOG_ACTION)
        reference = subject if type(subject) is str else digest([subject])
        return self.entries.consent(self.owner(context), entry_id, reference)

    # --- C2-3a: taste the role may actually use ----------------------------------

    def preference_terms(self, context):
        """Aggregated taste, or nothing when there is not enough evidence yet.

        Returns ``()`` in three distinct situations, and the caller is not told
        which: the switch is off, the shelf is off, or the ratings do not yet reach
        the declared minimum. A weaker guess would be worse than silence.
        """
        now, settings = self._admit(context, READ_ACTION)
        if not settings["preference_influence_enabled"]:
            return ()
        owner = self.owner(context)
        reviews = []
        for entry in self.entries.list(owner, limit=settings["max_entries_per_page"]):
            reviews.extend(self.entries.reviews(owner, entry.entry_id))
        return aggregate(reviews, min_ratings=settings["preference_min_ratings"],
                         max_terms=settings["preference_max_terms"])

    def preference_text(self, context):
        """The prompt block for the current taste, or an empty string."""
        return influence_text(self.preference_terms(context))

    # --- C2-3b: when the shelf may speak -----------------------------------------

    def trigger_due(self, context, action, *, seed_parts=()):
        """Whether the shelf may speak now. Reads the stored cursor, never memory."""
        now, settings = self._admit(context, READ_ACTION)
        cursor = self.entries.trigger_cursor(self.owner(context), action)
        return decide(settings, action, last_at=cursor, now=now, seed_parts=seed_parts)

    @outcome
    def record_trigger(self, context, action, *, seed_parts=()):
        """Gate and, when allowed, advance the cursor in the same call.

        Advancing on the same call is what makes the interval mean something: a
        caller that fires without recording would be able to fire again at once.
        """
        now, settings = self._admit(context, READ_ACTION)
        owner = self.owner(context)
        cursor = self.entries.trigger_cursor(owner, action)
        allowed, reason = decide(settings, action, last_at=cursor, now=now, seed_parts=seed_parts)
        if not allowed:
            return {"allowed": False, "reason": reason, "last_at": cursor}
        self.entries.put_trigger_cursor(owner, action, at=now)
        return {"allowed": True, "reason": "", "last_at": now}

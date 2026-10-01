"""Collect a complete dated inventory before explicitly selecting writing inputs.

All producers are read through their cursors in one SQLite snapshot. Collection
does not run a model, schedule a task, silently truncate or pick a literary theme.
"""

from dataclasses import dataclass
from datetime import datetime

from companion_v2.execution.models import TaskContext, TaskError, digest, require
from companion_v2.foundation.refs import RoleOwnerRef
from companion_v2.sources.repositories import SourceRepository

from .material_producer import JournalMaterialPage
from .materials import JournalMaterial, MAX_JOURNAL_MATERIALS, validate_materials
from .models import JournalContext
from .selection import needs_selection


@dataclass(frozen=True)
class JournalDayMaterials:
    context: JournalContext
    task_context_key: str
    collected_at: datetime
    materials: tuple[JournalMaterial, ...]
    page_counts: tuple[tuple[str, int], ...]

    @property
    def requires_selection(self):
        return needs_selection(self.materials)

    def select(self, material_ids=None) -> JournalMaterialPage:
        """Select exact candidate IDs; omitted IDs mean all, never the first page."""
        if material_ids is None:
            if self.requires_selection:
                raise TaskError("journal_material_selection_required", "the complete inventory needs an explicit selection")
            selected = self.materials
        else:
            if (not isinstance(material_ids, tuple) or len(material_ids) > MAX_JOURNAL_MATERIALS
                    or any(not isinstance(item, str) for item in material_ids)
                    or len(set(material_ids)) != len(material_ids)):
                raise ValueError("selected material IDs must be bounded, unique and immutable")
            by_id = {item.material_id: item for item in self.materials}
            if any(item not in by_id for item in material_ids):
                raise TaskError("journal_material_not_collected", "selection must refer to this dated inventory")
            selected = tuple(by_id[item] for item in material_ids)
        page = JournalMaterialPage(selected, None)
        validate_materials(page.materials, page.source_refs, page.activity_refs)
        return page


class JournalMaterialCollector:
    def __init__(self, tasks, role_life, *, activities, artifacts, readings, conversations,
                 screens=None, require_running=None):
        if tasks.runtime is not role_life.runtime:
            raise ValueError("journal collection must share the original V2 runtime")
        self.tasks, self.life, self.runtime = tasks, role_life, tasks.runtime
        self.activities, self.artifacts = activities, artifacts
        self.readings, self.conversations = readings, conversations
        self.screens = screens
        self.require_running = require_running
        self.sources = SourceRepository(self.runtime)

    def for_day(self, context: TaskContext, target: JournalContext, *, page_size=50) -> JournalDayMaterials:
        if not isinstance(context, TaskContext) or not isinstance(target, JournalContext):
            raise ValueError("journal collection needs an authorized task and dated scope")
        if type(page_size) is not int or not 1 <= page_size <= MAX_JOURNAL_MATERIALS:
            raise ValueError("collection page size must be between 1 and 64")
        if self.require_running is not None:
            self.require_running()
        owner = RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                             context.role_binding.role.subject_id)
        if target.scope != context.scope or target.key.owner != owner:
            raise TaskError("journal_context_mismatch", "journal collection cannot cross its role or conversation scope")
        with self.runtime.read_snapshot():
            at = self.tasks.now()
            require(self.tasks.authorize_context(context, action="role.journal.write", observed_at=at))
            readers = [
                ("activities", lambda cursor: self.activities.for_day(target, limit=page_size, after_id=cursor)),
                ("artifact_catalog", lambda cursor: self.artifacts.for_day(target, limit=page_size, after_id=cursor)),
                ("artifact_contents", lambda cursor: self.artifacts.contents_for_day(context, target, limit=page_size, after_id=cursor)),
                ("reading_contents", lambda cursor: self.readings.for_day(context, target, limit=page_size, after_id=cursor)),
                ("conversation", lambda cursor: self.conversations.for_day(context, target, limit=page_size, after_id=cursor)),
            ]
            if self.screens is not None:
                readers.append(("screen", lambda cursor: self.screens.for_day(context, target,
                    limit=page_size, after_id=cursor)))
            materials, page_counts = {}, []
            for name, read in readers:
                cursor, seen, pages = None, set(), 0
                while True:
                    page = read(cursor)
                    pages += 1
                    for item in page.materials:
                        if item.local_date != target.key.local_date:
                            raise TaskError("journal_context_mismatch", "producer returned material from another date")
                        if item.material_id in materials and materials[item.material_id] != item:
                            raise TaskError("journal_material_conflict", "one material identity has different contents")
                        materials[item.material_id] = item
                    cursor = page.next_cursor
                    if cursor is None:
                        break
                    if cursor in seen:
                        raise TaskError("journal_material_cursor_stalled", "producer did not advance its inventory cursor")
                    seen.add(cursor)
                page_counts.append((name, pages))
            inventory = JournalMaterialPage(tuple(materials.values()), None)
            source_refs = set(inventory.source_refs)
            for ref in source_refs:
                if ref.scope != target.scope:
                    raise TaskError("journal_context_mismatch", "collected source belongs to another scope")
                require(self.sources.validate_reference(ref, observed_at=at))
                source = require(self.sources.read(ref, resolved=context.actor, capability="role.journal.write",
                                                   observed_at=at, authorizer=self.tasks.identity))
                if not set(context.audience.recipients).issubset(source.audience.recipients):
                    raise TaskError("source_audience_mismatch", "collected source is not available to the writing audience")
                if source.content_hash != digest(source.payload):
                    raise TaskError("journal_source_changed", "collected text no longer matches its original hash")
            for ref in inventory.activity_refs:
                activity = self.life.activity(ref.lineage_id, owner=owner)
                if activity.scope != target.scope or activity.revision != ref.revision:
                    raise TaskError("journal_activity_changed", "collected activity must retain its exact scope and revision")
                if activity.reading is not None and activity.reading.source not in source_refs:
                    raise TaskError("journal_reading_source_required", "reading collection must retain its original source")
            return JournalDayMaterials(target, context.key, at, inventory.materials, tuple(page_counts))

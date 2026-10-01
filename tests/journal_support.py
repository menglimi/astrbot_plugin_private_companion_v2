"""Synthetic journal records in isolated V2 stores."""

from pathlib import Path
from tempfile import TemporaryDirectory

from companion_v2.execution.models import digest
from companion_v2.foundation.refs import AudienceRef, RoleOwnerRef, SourceRef, SubjectKind, SubjectRef, VersionRef
from companion_v2.role_work.journal import JournalContext, JournalDraft, JournalKey, JournalKind, RoleJournalService
from companion_v2.sources.models import SourceRecord
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import INSTALLATION, NOW, ROLE, SCOPE


class JournalFixture:
    def setUp(self):
        temporary = TemporaryDirectory(prefix="companion-v2-journal-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data"
        self.runtime = self.open_runtime()
        self.service = RoleJournalService(self.runtime, now=lambda: NOW)
        self.owner = RoleOwnerRef(INSTALLATION, SCOPE.bot_id, ROLE.subject_id)
        self.key = JournalKey(self.owner, JournalKind.DIARY, "2026-09-21")
        self.context = JournalContext(self.key, SCOPE, "Asia/Shanghai")
        self.draft = JournalDraft(self.context, body="今天读到第三章。\n\n有个问题还没想通。", form="碎片手记")

    def open_runtime(self):
        runtime = StorageRuntime.open(data_root=self.root, installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        return runtime

    def save(self, draft=None, *, revision=0, operation="write", **kwargs):
        return self.service.save(draft or self.draft, expected_revision=revision, operation_id=operation, **kwargs)

    def source(self, *, expires_at=None):
        ref = SourceRef("reading-note", "fixture", SCOPE, VersionRef("reading-note", 1), NOW, expires_at)
        audience = AudienceRef(SCOPE, (SubjectRef(INSTALLATION, SubjectKind.HUMAN, "reader"),))
        self.service.sources.publish(SourceRecord(ref, audience, digest("读到第三章"), "读到第三章"), observed_at=NOW).unwrap()
        return ref

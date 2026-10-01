"""Shared fixture for the Content orchestration slices: a relationship context and its runtime."""

from __future__ import annotations

from datetime import timezone

from companion_v2.configuration.models import ConfigLayer, ConfigTarget
from companion_v2.configuration.owners import SparseConfigurationOwner
from companion_v2.foundation.refs import AssetRef, RoleOwnerRef, SourceRef, VersionRef
from companion_v2.execution.models import TaskContext
from tests.test_daily_token_soft_limit import ModelFixture
from tests.test_management_access import NOW


class ContentOrchestrationFixture(ModelFixture):
    """One authorized private relationship plus the helpers the Content slices need."""

    def role_target(self, layer=ConfigLayer.ROLE):
        context = self.context
        if layer is ConfigLayer.INSTALLATION:
            return ConfigTarget(context.scope.installation_id, layer)
        return ConfigTarget(context.scope.installation_id, layer, context.role_binding.role,
                            bot_id=context.scope.bot_id)

    def configure(self, fields, **changes):
        owner = SparseConfigurationOwner(self.runtime)
        target = self.role_target()
        return owner.write(target, fields, changes=changes, reset=(),
                           expected_revision=owner.read(target, fields).revision, observed_at=NOW)

    def role_owner(self):
        context = self.context
        return RoleOwnerRef(context.scope.installation_id, context.scope.bot_id,
                            context.role_binding.role.subject_id)

    def work_source(self, identifier="work-version-1"):
        scope = self.context.scope
        return SourceRef(identifier, "content.native", scope, VersionRef(identifier, 1), NOW)

    def image_asset(self, identifier="asset-1", *, content_hash="a" * 64):
        return AssetRef(identifier, "image.native", self.context.scope, VersionRef(identifier, 1), content_hash)


__all__ = ["ContentOrchestrationFixture", "NOW", "TaskContext", "timezone"]

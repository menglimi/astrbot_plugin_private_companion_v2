"""Real independent Content domain, synthetic Star/model/platform, temporary data."""

import importlib
import os
from pathlib import Path
import sys
import traceback
from types import ModuleType, SimpleNamespace

from astrbot_host.native_extensions import NativeExtensionRegistry
from companion_v2.capabilities.models import CapabilityAuthorizationState
from companion_v2.capabilities.repositories import CapabilityRepository
from companion_v2.conversation.flow import ConversationPolicy
from tests.test_management_access import NOW, SCOPE


def content_builder():
    root = Path(os.environ.get("CONTENT_V2_PROVIDER_ROOT", Path(__file__).resolve().parents[2] /
                               "astrbot_plugin_content_companion" / "companion" / "content_v2"))
    if not (root / "assembly.py").is_file():
        raise RuntimeError("Content integration requires the native Content source package")
    name = "_companion_content_native_test"
    if name not in sys.modules:
        module = ModuleType(name)
        module.__path__ = [str(root)]
        sys.modules[name] = module
    return importlib.import_module(name + ".assembly").build_provider


class NativeContentFixture:
    def create_content_port(self, *, directory=None):
        self.content_directory = directory or self.root.parent / "content-provider"
        self.content_port = content_builder()(self.content_directory, version="0.2.3", live=lambda: None)
        self.content_port.now = self.clock.now
        self.addAsyncCleanup(self.content_port.close)
        self.content_star = SimpleNamespace(root_dir_name="astrbot_plugin_content_companion",
            name="astrbot_plugin_content_companion", version="0.2.3", activated=True,
            star_cls=SimpleNamespace(extension_api=SimpleNamespace(companion_v2_native=lambda: self.content_port)))
        self.native_context = SimpleNamespace(get_all_stars=lambda: (self.content_star,))
        self.native_registry = NativeExtensionRegistry(self.native_context, now=self.clock.now)
        self.addCleanup(self.native_registry.close)
        self.content_errors = []
        original_invoke = self.native_registry.invoke
        async def observe(*args):
            try:
                return await original_invoke(*args)
            except Exception as error:
                self.content_errors.append(repr(error))
                raise
        self.native_registry.invoke = observe
        return self.native_registry

    def content_grants(self, registry, *, scope=SCOPE, actor=None, acquire=True, role=None):
        repository = CapabilityRepository(self.runtime)
        registry.register_catalog(observed_at=self.clock.now()).unwrap()
        package = registry.declarations()[0].descriptor.package
        if acquire:
            repository.acquire(extension_id="content", package_id=package.package_id,
                package_version=package.package_version, expected_revision=0, observed_at=NOW).unwrap()
        if acquire or role is not None:
            repository.set_role_enabled(extension_id="content", role=role or self.window.role, bot_id=scope.bot_id,
                enabled=True, expected_revision=0, observed_at=NOW).unwrap()
        for capability in package.capabilities:
            repository.set_authorization(extension_id="content", capability_id=capability,
                subject=(actor or self.important).subject, scope=scope,
                state=CapabilityAuthorizationState.ACTIVE, expected_revision=0, observed_at=NOW).unwrap()

    async def content_host(self, **options):
        self.create_content_port()
        options.setdefault("policy", ConversationPolicy(0, 0, 180, 0))
        host = self.host(tool_port=self.native_registry, **options)
        original = host.application.generator.generate
        async def observed(run):
            try:
                return await original(run)
            except Exception:
                self.content_errors.append(traceback.format_exc())
                raise
        host.application.generator.generate = observed
        self.content_grants(self.native_registry)
        return await self.start(host)

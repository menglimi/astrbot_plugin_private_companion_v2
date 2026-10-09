"""Real V2 entry, synthetic peers, exercised only inside native acceptance."""

import asyncio
import importlib.util
import sys
import traceback
from types import ModuleType, SimpleNamespace as NS
from unittest.mock import patch


async def run_core(plugin_root, root, guard):
    # The worker has already set ASTRBOT_ROOT and installed dependency guards.
    from tests.test_astrbot_staging_host import WebContext, host_config
    from tests.native_adapter_support import FakeEvent, FakeProvider, FakeReverseApi, completion
    from tests.staging_bootstrap_support import wait_for_batch
    from tests.test_management_access import NOW
    from companion_v2.adapters.astrbot.staging import NativeAdapterTypes

    package = ModuleType("native_acceptance_core")
    package.__path__ = [str(plugin_root)]
    sys.modules[package.__name__] = package
    entry = importlib.import_module(package.__name__ + ".main")
    context = WebContext()
    stars = []
    context.get_all_stars = lambda: guard.catalog(stars)
    context.get_registered_star = lambda name: guard.discover(name, stars)
    config = host_config(staging={"profile_id": "native-acceptance", "delivery_mode": "onebot_private"})

    class Event(FakeEvent):
        def stop_event(self):
            self.stopped = True

    types = NativeAdapterTypes("4.27.2", Event, FakeProvider, NS, NS, FakeReverseApi)
    controller_type = entry.AstrBotStagingController
    def factory(native, settings, data_root):
        controller = controller_type(native, settings, data_root, native_types=types, now=lambda: NOW)
        failure = controller._failure
        def diagnostic(error, fallback):
            if getattr(error, "code", None) not in {"authorization_denied", "authorization_revoked"}:
                traceback.print_exception(error)
            return failure(error, fallback)
        controller._failure = diagnostic
        return controller
    with patch.object(entry.StarTools, "get_data_dir", return_value=root / "runtime" / "v2"), \
            patch.object(entry, "AstrBotStagingController", factory):
        plugin = entry.PrivateCompanionV2StagingPlugin(context, config)
    stars.append(NS(name=entry.PLUGIN_NAME, root_dir_name=entry.PLUGIN_NAME, version=entry.PLUGIN_VERSION,
                    activated=True, star_cls=plugin))
    checks, entered, release = [], asyncio.Event(), asyncio.Event()
    ctrl = plugin.staging
    routes = len(context.registered_web_apis)

    async def receive(identifier):
        event = Event(context, event_id=identifier)
        await plugin.receive_companion_message(event)
        assert not getattr(event, "stopped", False) and event.call_llm
        return ctrl.runtime.read_all("SELECT batch_id FROM conversation_batches ORDER BY rowid", ())[-1][0]

    try:
        await plugin.initialize()
        assert ctrl.runtime is None and not ctrl.status()["accepting"]
        assert [s.root_dir_name for s in context.get_all_stars()] == [entry.PLUGIN_NAME]
        manifest = plugin.extension_api.manifest()
        assert not any(p["installed"] for p in manifest["providers"])
        checks.append("entry_loaded_without_legacy_or_registered_optional_providers_and_without_auto_start")
        (await ctrl.initialize_profile()).unwrap()
        (await ctrl.start()).unwrap()
        assert context.provider.client.state.calls == [] and context.platform.client._api._wsr_api.calls == []
        checks.append("configured_start_has_no_model_or_platform_effect")
        batch = await receive("native-first")
        await wait_for_batch(ctrl.session, batch, timeout_seconds=10)
        assert (await ctrl.inspect(batch)).unwrap()["confirmed_delivery"]
        assert len(context.platform.client._api._wsr_api.calls) == 1
        checks.append("synthetic_conversation_executes_through_native_entry_and_records_local_ack")

        async def delayed(*_):
            entered.set()
            await release.wait()
            return completion()
        context.provider.client.state.behavior = delayed
        delayed_batch = await receive("native-revoked")
        await asyncio.wait_for(entered.wait(), 10)
        identity = ctrl.bootstrap.identity
        identity.revoke_grant(ctrl.bootstrap.grant_id("conversation.reply"),
                              revoked_at=NOW, expected_revision=identity.revision)
        assert ctrl.status()["accepting"]
        release.set()
        await wait_for_batch(ctrl.session, delayed_batch, timeout_seconds=10)
        assert len(context.platform.client._api._wsr_api.calls) == 1
        before = len(context.provider.client.state.calls)
        refused = await ctrl.session.receive(Event(context, event_id="native-after-revoke"))
        assert refused.failure is not None and refused.failure.code == "private_access_dialogue_denied"
        assert len(context.provider.client.state.calls) == before
        assert len(context.platform.client._api._wsr_api.calls) == 1
        checks.append("person_revocation_during_generation_blocks_late_send_and_further_model_calls")
        stopped = (await ctrl.stop()).unwrap()
        assert stopped.state == "stopped" and not stopped.pending_handles
        restarted = await ctrl.start()
        assert restarted.failure is not None and restarted.failure.code == "private_access_dialogue_denied"
        target = ctrl.bootstrap._target(NOW)
        access = identity.authorize(target.actor, scope=target.scope,
                                    capability="conversation.reply", observed_at=NOW)
        assert access.failure is not None and access.failure.code == "authorization_revoked"
        checks.append("stop_and_restart_do_not_restore_revoked_person_permission")
    finally:
        release.set()
        await plugin.terminate()
    assert ctrl.runtime is None and not context.registered_web_apis
    assert ctrl._terminated and not ctrl.status()["accepting"]
    checks.append("terminate_closes_database_handles_and_unregisters_owned_routes")
    guard.assert_clean()
    return {"native_independent": True, "checks": checks, "registered_routes": routes,
            "synthetic_model_calls": len(context.provider.client.state.calls),
            "synthetic_platform_acks": len(context.platform.client._api._wsr_api.calls),
            "legacy_installed": False, "legacy_imports": 0, "legacy_data_reads": 0,
            "optional_sources_present": (plugin_root.parent / "astrbot_plugin_image_companion").is_dir(),
            "pending_handles": 0, "remaining_routes": 0}

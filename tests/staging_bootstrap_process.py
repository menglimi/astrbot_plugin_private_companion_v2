"""Independent-process recovery fixture, exclusively using in-memory native peers."""

import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS

from companion_v2.adapters.astrbot.staging import NativeAdapterTypes
from companion_v2.adapters.astrbot.staging_bootstrap import AstrBotStagingBootstrap
from companion_v2.storage.runtime import StorageRuntime
from tests.native_adapter_support import FakeEvent, FakeHostContext, FakeProvider, FakeReverseApi
from tests.staging_bootstrap_support import database_contents, synthetic_configuration, wait_for_batch
from tests.test_management_access import INSTALLATION, NOW


async def run(mode, root):
    native = FakeHostContext()
    config = synthetic_configuration(native, delivery_mode="onebot_private")
    with StorageRuntime.open(data_root=root, installation_id=INSTALLATION) as runtime:
        bootstrap = AstrBotStagingBootstrap(runtime, native, configuration=config,
            native_types=NativeAdapterTypes("4.27.2", FakeEvent, FakeProvider, NS, NS, FakeReverseApi), now=lambda: NOW)
        if mode == "check-revoked":
            before = database_contents(runtime)
            print(json.dumps({"initialize": (await bootstrap.initialize()).failure.code,
                "load": bootstrap.load(runtime_instance_id="revoked-process").failure.code,
                "unchanged": before == database_contents(runtime)}), flush=True)
            return
        receipt = (await bootstrap.initialize()).unwrap()
        bootstrap.authorize_delivery(expires_at=NOW + timedelta(hours=1)).unwrap()
        session = bootstrap.load(runtime_instance_id=mode).unwrap()
        generation = 0 if mode == "seed-and-exit" else 1
        started = (await session.start(expected_task_generation=generation, expected_model_generation=generation)).unwrap()
        native.platform.client._api._wsr_api.error = TimeoutError("synthetic missing acknowledgement")
        batch = (await session.receive(FakeEvent(native))).unwrap()
        await wait_for_batch(session, batch)
        report = session.inspect(batch).unwrap()
        result = {"batch_id": batch, "delivery_receipts": report["delivery_receipts"],
            "model_calls": report["model"]["calls"], "replayed": receipt.replayed,
            "new_model_calls": len(native.provider.client.state.calls),
            "new_send_calls": len(native.platform.client._api._wsr_api.calls),
            "task_generation": started.task_generation}
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if mode == "seed-and-exit":
            # Exit without stopping the driver or closing SQLite, after the
            # unknown receipt commits. Recovery must keep its original operation.
            os._exit(0)
        await session.close()


if __name__ == "__main__":
    mode, root = sys.argv[1:]
    if mode not in ("seed-and-exit", "recover", "check-revoked"):
        raise SystemExit("unknown fixture mode")
    asyncio.run(run(mode, Path(root)))

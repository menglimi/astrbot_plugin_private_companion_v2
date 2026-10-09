"""The inbound no-reply ledger stays bounded and content-free."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.diagnostics.inbound import InboundNoReplyLedger
from companion_v2.storage.runtime import StorageRuntime
from tests.test_management_access import INSTALLATION


class InboundNoReplyLedgerTests(unittest.TestCase):
    def test_retains_only_the_500_most_recent_reason_records(self):
        temporary = TemporaryDirectory(prefix="companion-v2-no-reply-ledger-")
        self.addCleanup(temporary.cleanup)
        runtime = StorageRuntime.open(data_root=Path(temporary.name), installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        ledger = InboundNoReplyLedger(runtime)
        start = datetime(2026, 10, 5, tzinfo=timezone.utc)

        for index in range(501):
            ledger.record(reason_code="session_reply_disabled", observed_at=start + timedelta(seconds=index),
                          channel="private", origin_key="role-private", event_ref=f"{index:032x}")

        rows = runtime.read_all("SELECT * FROM inbound_no_replies ORDER BY observed_at, rowid", ())
        self.assertEqual(len(rows), 500)
        self.assertEqual(rows[0]["event_ref"], f"{1:032x}")
        self.assertEqual(rows[-1]["event_ref"], f"{500:032x}")
        self.assertEqual(set(rows[0].keys()), {"event_ref", "origin_key", "channel", "reason_code", "observed_at", "code"})

    def test_suppressed_outcome_is_kept_for_diagnostics_without_a_log_line(self):
        from companion_v2.diagnostics import inbound

        temporary = TemporaryDirectory(prefix="companion-v2-no-reply-suppressed-")
        self.addCleanup(temporary.cleanup)
        runtime = StorageRuntime.open(data_root=Path(temporary.name), installation_id=INSTALLATION)
        self.addCleanup(runtime.close)
        inbound.reset_reply_log()
        at = datetime(2026, 10, 5, tzinfo=timezone.utc)

        self.assertIsNone(InboundNoReplyLedger(runtime).emit(
            expectation=inbound.SUPPRESSED, stage="flow", turn="planned-cancel",
            reason_code="cancelled", observed_at=at, channel="private", origin_key="role-private"))

        row = runtime.read_one("SELECT reason_code, code FROM inbound_no_replies", ())
        self.assertEqual((row["reason_code"], row["code"]), ("cancelled", None))


if __name__ == "__main__":
    unittest.main()

"""Legacy room identity survives process restarts without retaining secrets."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from companion_v2.execution.models import TaskError
from companion_v2.storage.runtime import StorageRuntime
from companion_v2.together.mobile.requests import MobileRoomRequests


class MobileRoomRequestTests(unittest.TestCase):
    def test_pending_request_survives_storage_restart_and_cannot_change_context(self):
        with TemporaryDirectory(prefix="v2-mobile-room-journal-") as temporary:
            root = Path(temporary)
            with StorageRuntime.open(data_root=root, installation_id="mobile-rooms") as runtime:
                original = MobileRoomRequests(runtime).begin('user-a', 'context-a', 'call', now=100)
            with StorageRuntime.open(data_root=root, installation_id="mobile-rooms") as runtime:
                requests = MobileRoomRequests(runtime)
                self.assertEqual(requests.begin('user-a', 'context-a', 'call', now=10**10), original)
                with self.assertRaises(TaskError) as raised:
                    requests.begin('user-a', 'context-b', 'call', now=10**10)
                self.assertEqual(raised.exception.code, 'mobile_v2_context_changed')
                self.assertNotEqual(requests.begin('user-b', 'context-b', 'call', now=100), original)
                self.assertNotEqual(requests.begin('user-a', 'context-a', 'watch', now=100), original)

    def test_stale_completion_cannot_replace_next_request_after_confirmed_failure(self):
        with TemporaryDirectory(prefix="v2-mobile-room-journal-") as temporary:
            with StorageRuntime.open(data_root=Path(temporary), installation_id="mobile-rooms") as runtime:
                requests = MobileRoomRequests(runtime)
                original = requests.begin('user-a', 'context-a', 'call', now=100)
                requests.finish('user-a', 'call', original, {'state': 'failed', 'effect': 'not_committed'})
                current = requests.begin('user-a', 'context-a', 'call', now=100)
                requests.finish('user-a', 'call', original, {'state': 'succeeded', 'effect': 'committed',
                    'result': {'room': {'expires_at': 101, 'url': 'must-not-be-persisted'}}})
                self.assertEqual(requests.begin('user-a', 'context-a', 'call', now=102), current)
                rows = runtime.read_all("SELECT value FROM runtime_metadata WHERE key LIKE ?",
                                        ('together.mobile.request:%',))
                self.assertNotIn('must-not-be-persisted', repr(tuple(dict(row) for row in rows)))

    def test_missing_live_ticket_replaces_only_a_confirmed_success(self):
        with TemporaryDirectory(prefix="v2-mobile-room-journal-") as temporary:
            with StorageRuntime.open(data_root=Path(temporary), installation_id="mobile-rooms") as runtime:
                requests = MobileRoomRequests(runtime)
                original = requests.begin('user-a', 'context-a', 'call', now=100)
                self.assertEqual(requests.begin('user-a', 'context-a', 'call', now=100,
                    room_available=lambda _: False), original)
                requests.finish('user-a', 'call', original, {'state': 'succeeded', 'effect': 'committed',
                    'result': {'room': {'expires_at': 1000}}})
                self.assertEqual(requests.begin('user-a', 'context-a', 'call', now=100,
                    room_available=lambda _: None), original)
                self.assertNotEqual(requests.begin('user-a', 'context-a', 'call', now=100,
                    room_available=lambda _: False), original)


if __name__ == '__main__':
    unittest.main()

"""Persisted projections cannot acquire execution or SQLite write authority."""

import contextvars
import sqlite3

from companion_v2.execution.models import Lane, TaskError
from companion_v2.storage.runtime import StorageOpenError
from tests.test_execution import ExecutionFixture


class ExecutionReadOnlyTests(ExecutionFixture):
    def authorize(self, supervisor):
        return supervisor.authorize_context(self.context, action="configuration.read", observed_at=self.clock.now())

    def test_unstarted_projection_cannot_write_submit_claim_or_attach(self):
        supervisor = self.supervisor()
        before = self.runtime.read_one("SELECT COUNT(*) FROM execution_tasks", ())[0]
        with supervisor.read_only_context():
            self.assertTrue(self.authorize(supervisor).is_success)
            self.assertEqual(supervisor.check_generation().failure.code, "supervisor_fenced")
            self.assertEqual(supervisor.attach(expected_generation=1).failure.code, "supervisor_read_only")
            for operation in (lambda: supervisor.submit(self.spec()), lambda: supervisor.claim(Lane.FOREGROUND),
                              lambda: supervisor.start(expected_generation=1)):
                with self.assertRaises(StorageOpenError):
                    operation()
            # Even a repository that accidentally writes through a read helper
            # is constrained by SQLite, not just the transaction API.
            with self.assertRaises(sqlite3.OperationalError):
                self.runtime.read_one("DELETE FROM task_supervisor", ())
        self.assertIsNone(supervisor.generation)
        self.assertEqual(self.authorize(supervisor).failure.code, "supervisor_fenced")
        self.assertEqual(self.runtime.read_one("SELECT COUNT(*) FROM execution_tasks", ())[0], before)
        self.assertTrue(self.tasks.submit(self.spec()).is_success)

    def test_projection_cannot_borrow_an_existing_write_transaction(self):
        supervisor = self.supervisor()
        with self.runtime.transaction():
            with self.assertRaises(StorageOpenError), supervisor.read_only_context():
                self.fail("projection entered an existing write transaction")
            self.assertEqual(self.authorize(supervisor).failure.code, "supervisor_fenced")
            self.assertTrue(self.tasks.submit(self.spec()).is_success)

    def test_nested_exception_restores_outer_projection_and_sqlite_mode(self):
        supervisor = self.supervisor()
        with self.runtime.read_snapshot():
            with supervisor.read_only_context():
                with self.assertRaisesRegex(RuntimeError, "fixture"), supervisor.read_only_context():
                    raise RuntimeError("fixture")
                self.assertTrue(self.authorize(supervisor).is_success)
                with self.assertRaises(sqlite3.OperationalError):
                    self.runtime.read_one("DELETE FROM task_supervisor", ())
            self.assertEqual(self.authorize(supervisor).failure.code, "supervisor_fenced")
        self.assertTrue(self.tasks.submit(self.spec()).is_success)
        # Preserve a caller's pre-existing SQLite read-only setting as well.
        self.runtime.read_one("PRAGMA query_only = ON", ())
        try:
            with supervisor.read_only_context():
                self.assertTrue(self.authorize(supervisor).is_success)
            self.assertEqual(self.runtime.read_one("PRAGMA query_only", ())[0], 1)
        finally:
            self.runtime.read_one("PRAGMA query_only = OFF", ())

    def test_context_isolation_and_copied_context_cannot_outlive_projection(self):
        supervisor = self.supervisor()
        with supervisor.read_only_context():
            independent = contextvars.Context().run(self.authorize, supervisor)
            self.assertEqual(independent.failure.code, "supervisor_fenced")
            inherited = contextvars.copy_context()
            self.assertTrue(inherited.run(self.authorize, supervisor).is_success)
        self.assertEqual(inherited.run(self.authorize, supervisor).failure.code, "supervisor_fenced")

    def test_replaced_generation_cannot_become_a_read_only_observer(self):
        self.supervisor().start(expected_generation=1).unwrap()
        with self.assertRaises(TaskError) as raised, self.tasks.read_only_context():
            self.fail("replaced worker entered a projection")
        self.assertEqual(raised.exception.code, "supervisor_fenced")
        self.assertEqual(self.runtime.read_one("PRAGMA query_only", ())[0], 0)
        self.assertEqual(self.authorize(self.tasks).failure.code, "supervisor_fenced")

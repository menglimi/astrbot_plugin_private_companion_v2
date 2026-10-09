"""Role-plan page commands through real request parsing and isolated storage."""

from datetime import timedelta
import json
import unittest

from tests import test_role_state_api as state_support
from tests import test_astrbot_multi_state as multi_support
from tests.multi_host_support import MultiFixture
from tests.test_management_access import NOW
from tests.test_role_state import calendar_data
from companion_v2.agenda.models import Frequency, Schedule
from companion_v2.execution.models import encode
from companion_v2.identity_policy.models import AuthorizationTier


class CalendarAPITests(unittest.IsolatedAsyncioTestCase):
    request = state_support.StateAPITests.request
    initialize = state_support.StateAPITests.initialize

    async def asyncSetUp(self):
        await state_support.StateAPITests.asyncSetUp(self)
        self.app = (await self.initialize()).application
        self.serial = 0

    def ok(self, response):
        self.assertEqual(response["status"], "ok", response)
        return response["data"]

    async def item(self):
        return self.ok(await self.request())["calendar"]["items"][0]

    async def create(self, *, once=False):
        before = self.ok(await self.request())
        schedule = Schedule(NOW + timedelta(hours=1), "Asia/Shanghai",
                            Frequency.ONCE if once else Frequency.WEEKLY, count=None if once else 4)
        body = dict(action="calendar.create", operation_key="create-plan", id="page-plan",
                    expected_revision=0, view_token=before["create_token"],
                    data=calendar_data(schedule=json.loads(encode(schedule))),
                    sources=[json.loads(encode(self.source))])
        self.original_create = body
        self.ok(await self.request(data=body))
        replay = self.ok(await self.request(data=body))
        self.assertTrue(replay["replayed"])
        return await self.item()

    async def body(self, action, **values):
        self.serial += 1
        item = await self.item()
        return dict(action="calendar." + action, id=item["id"], operation_key="step-" + str(self.serial),
                    expected_revision=item["revision"], view_token=item["view_token"], **values)

    async def apply(self, action, **values):
        body = await self.body(action, **values)
        result = self.ok(await self.request(data=body))
        replay = self.ok(await self.request(data=body))
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["operation_id"], result["operation_id"])
        self.assertEqual((await self.item())["revision"], body["expected_revision"] + 1)
        return body, await self.item()

    def cancelled(self, reminder_id):
        self.assertEqual(self.app.agenda.repository.reminder(reminder_id).state, "cancelled")

    def allow_reminders(self):
        identity = self.app.tasks.identity
        for action in ("reminder.create", "reminder.deliver", "reminder.cancel"):
            identity.issue_grant(grant_id="calendar-page-" + action, subject=self.target.actor.subject,
                scope=self.target.scope, capability=action, tier=AuthorizationTier.STANDARD,
                valid_from=NOW, expected_revision=identity.revision)

    def no_external_calls(self):
        self.assertEqual(self.app.presence.active_handles, ())
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertEqual(self.native.platform.client._api._wsr_api.calls, [])

    async def test_complete_role_plan_lifecycle_preserves_sources_and_replaces_reminders(self):
        # Role calendar access is on by default; automatic planning remains independent.
        status = self.ok(await self.request())
        self.assertTrue(status["settings"]["calendar_enabled"])
        self.assertFalse(status["settings"]["planning_enabled"])
        original = await self.create()
        self.assertEqual(original["state"], "accepted")
        denied = await self.request(data=await self.body("remind", sequence=2))
        self.assertEqual(denied["data"]["code"], "authorization_denied", denied)
        self.assertEqual(await self.item(), original)
        self.allow_reminders()
        _, reminded = await self.apply("remind", sequence=2)
        first_reminder = reminded["reminder_id"]
        self.assertEqual(self.app.agenda.repository.reminder(first_reminder).schedule.anchor,
                         NOW + timedelta(days=14, hours=1))

        moved_to = NOW + timedelta(days=10, hours=3)
        _, moved = await self.apply("exception", data={"sequence": 2, "start": moved_to.isoformat()})
        self.cancelled(first_reminder)
        self.assertEqual(moved["schedule"], original["schedule"])
        self.assertEqual(moved["sources"], original["sources"])
        _, reminded = await self.apply("remind", sequence=2)
        moved_reminder = reminded["reminder_id"]
        self.assertEqual(self.app.agenda.repository.reminder(moved_reminder).schedule.anchor, moved_to)
        _, replacement = await self.apply("remind", sequence=0)
        self.cancelled(moved_reminder)
        _, skipped = await self.apply("exception", data={"sequence": 1, "start": None})
        self.cancelled(replacement["reminder_id"])
        self.assertIsNone(skipped["exceptions"]["1"])
        self.assertEqual(skipped["exceptions"]["2"], moved["exceptions"]["2"])
        operator = state_support.dashboard_operator(self.controller.runtime, "admin", at=NOW)
        window = self.app.calendar.occurrences(self.target, start=NOW, end=NOW + timedelta(days=30),
                                               operator=operator)
        self.assertEqual([item["sequence"] for item in window["items"]], [0, 2, 3])

        _, reminded = await self.apply("remind", sequence=0)
        new_schedule = Schedule(NOW + timedelta(hours=2), "Asia/Shanghai", Frequency.DAILY, count=3)
        revised_data = calendar_data(title="新的阅读安排", schedule=json.loads(encode(new_schedule)))
        _, revised = await self.apply("revise", data=revised_data, sources=skipped["sources"])
        self.cancelled(reminded["reminder_id"])
        self.assertEqual(revised["exceptions"], {})
        self.assertEqual(revised["sources"], original["sources"])
        self.assertEqual(revised["schedule"]["frequency"], "daily")
        self.assertIsNone(revised["reminder_id"])

        _, reminded = await self.apply("remind", sequence=1)
        cancel, cancelled = await self.apply("cancel")
        self.cancelled(reminded["reminder_id"])
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual(cancelled["sources"], original["sources"])
        self.assertEqual(self.app.calendar.occurrences(self.target, start=NOW, end=NOW + timedelta(days=7),
                                                      operator=operator)["items"], [])
        self.assertTrue(self.ok(await self.request(data=cancel))["replayed"])
        self.assertTrue(self.ok(await self.request(data=self.original_create))["replayed"])
        self.assertEqual((await self.item())["state"], "cancelled")
        self.no_external_calls()

    async def test_all_plan_mutations_reject_stale_revision_without_cancelling_reminder(self):
        await self.create()
        self.allow_reminders()
        await self.apply("remind", sequence=0)
        stale = [await self.body("revise", data=calendar_data(), sources=[json.loads(encode(self.source))]),
                 await self.body("exception", data={"sequence": 0, "start": None}),
                 await self.body("remind", sequence=0), await self.body("cancel")]
        _, current = await self.apply("presence", data={"presence": "安静阅读"})
        reminder = self.app.agenda.repository.reminder(current["reminder_id"])
        for body in stale:
            with self.subTest(action=body["action"]):
                response = await self.request(data=body)
                self.assertEqual(response["data"]["code"], "record_revision_conflict", response)
                self.assertEqual(await self.item(), current)
                self.assertEqual(self.app.agenda.repository.reminder(current["reminder_id"]), reminder)
        self.no_external_calls()

    async def test_exact_receipt_recovery_survives_policy_change_but_rechecks_authorization(self):
        await self.create()
        self.allow_reminders()
        reminder, _ = await self.apply("remind", sequence=0)
        _, current = await self.apply("remind", sequence=1)
        active = current["reminder_id"]
        self.assertTrue(self.ok(await self.request(data=reminder))["replayed"])
        self.assertEqual((await self.item())["reminder_id"], active)
        for changes in ({"sequence": 1}, {"view_token": "forged"}, {"expected_revision": 0}):
            result = await self.request(data=reminder | changes)
            self.assertEqual(result["data"]["code"], "idempotency_key_conflict", result)
        result = await self.request(data=reminder | {"operation_key": "new-stale-request"})
        self.assertEqual(result["data"]["code"], "state_view_stale", result)
        self.assertEqual((await self.item())["reminder_id"], active)
        operator = state_support.dashboard_operator(self.controller.runtime, "admin", at=NOW)
        policy = state_support.ObjectAccessPolicy(self.controller.runtime)
        policy.set_tier(operator.subject, AuthorizationTier.STANDARD, expected_revision=policy.revision, observed_at=NOW)
        denied = await self.request(data=reminder)
        self.assertIn(denied["data"]["code"], ("core_access_required", "authorization_denied"), denied)
        self.assertEqual(self.app.calendar.records.get(self.target, "page-plan")["reminder_id"], active)
        self.no_external_calls()

    async def test_occurrence_and_command_boundaries_leave_plan_unchanged(self):
        original = await self.create(once=True)
        for action, fields, code in (
            ("exception", {"data": {"sequence": 1, "start": None}}, "calendar_occurrence_missing"),
            ("remind", {"sequence": 1}, "calendar_reminder_past"),
            ("exception", {"data": {"sequence": True, "start": None}}, "state_command_invalid"),
            ("exception", {"data": {"sequence": 0, "start": "2026-09-26T10:00:00"}}, "state_command_invalid"),
            ("revise", {"data": calendar_data(kind="user_report")}, "calendar_kind_changed"),
            ("cancel", {"target_id": "other"}, "state_command_invalid"),
        ):
            with self.subTest(action=action, fields=fields):
                result = await self.request(data=await self.body(action, **fields))
                self.assertEqual(result["data"]["code"], code, result)
                self.assertEqual(await self.item(), original)
        await self.apply("revise", data=calendar_data(title="一次事件改期"), sources=original["sources"])
        self.assertEqual((await self.item())["schedule"]["frequency"], "once")
        self.no_external_calls()


class CalendarTargetAPITests(MultiFixture, unittest.IsolatedAsyncioTestCase):
    register = multi_support.MultiStateTests.register
    initialize = multi_support.MultiStateTests.initialize
    request = multi_support.MultiStateTests.request
    ok = multi_support.MultiStateTests.ok
    status = multi_support.MultiStateTests.status

    async def test_each_calendar_command_is_bound_to_original_target_and_role(self):
        await self.initialize()
        contexts = (("first", "role-a"), ("second", "role-a"), ("first", "role-b"))
        create = None
        for target, role in contexts:
            before = await self.status(target, role)
            body = dict(action="calendar.create", operation_key="create-plan", id="shared-id", expected_revision=0,
                        view_token=before["create_token"], data=calendar_data(title=target + "/" + role))
            self.ok(await self.request(target, role, data=body))
            create = create or body
        item = (await self.status())["calendar"]["items"][0]
        common = dict(operation_key="mutate", id=item["id"], expected_revision=item["revision"],
                      view_token=item["view_token"])
        commands = [create, dict(common, action="calendar.revise", data=calendar_data(), sources=[]),
                    dict(common, action="calendar.exception", data={"sequence": 0, "start": None}),
                    dict(common, action="calendar.remind", sequence=0), dict(common, action="calendar.cancel")]
        for target, role in contexts[1:]:
            before = (await self.status(target, role))["calendar"]
            for command in commands:
                with self.subTest(target=target, role=role, action=command["action"]):
                    result = await self.request(target, role, data=command)
                    expected = "idempotency_key_conflict" if command["action"] == "calendar.create" else "state_view_stale"
                    self.assertEqual(result["data"]["code"], expected, result)
                    fresh_key = await self.request(target, role, data=command | {"operation_key": "foreign-new-key"})
                    self.assertEqual(fresh_key["data"]["code"], "state_view_stale", fresh_key)
                    self.assertEqual((await self.status(target, role))["calendar"], before)
        self.assertEqual(self.native.provider.client.state.calls, [])
        self.assertTrue(all(not platform.client._api._wsr_api.calls for platform in self.native.platforms.values()))

"""Synthetic planning against real calendar, supervisor, memory and host owners."""

import asyncio
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
import json
import unittest
from zoneinfo import ZoneInfo

from companion_v2.agenda.annual_calendar import SCHEMA
from companion_v2.agenda.models import Frequency, Schedule
from companion_v2.agenda.planning import KIND, planning_profile
from companion_v2.agenda.planning_config import configured_annual_calendars, planning_values
from companion_v2.agenda.planning_inputs import capture, validate, MATERIAL_CHARS, planning_calendar_context
from companion_v2.agenda.planning_output import INSTRUCTION, parse_output
from companion_v2.configuration.models import ConfigurationError
from companion_v2.configuration.registry import FieldRegistry
from companion_v2.conversation.models import InboundConversationEvent
from companion_v2.execution.models import TaskError, digest, encode
from companion_v2.foundation.refs import SourceRef, VersionRef, OperationRef
from companion_v2.model_gateway.routing import configuration_fields
from companion_v2.proactive.management import ContactManagement
from companion_v2.role_work.growth import RoleGrowthRecord, GrowthKind
from companion_v2.role_work.growth.progress import growth_progress_profile
from companion_v2.role_work.growth.progress_management import GrowthProgressManagement
from companion_v2.role_work.models import RoleActivity, RoleActivityState
from companion_v2.sources.models import SourceRecord
from tests.test_management_access import NOW
from tests.test_role_state import StateFixture, calendar_data
from tests.test_role_tool_loop import answered


def output(at=NOW, **changes):
    return {"title": "读下一小节", "start": (at + timedelta(hours=1)).isoformat(), "minutes": 30,
            "detail": "先回顾上次疑问，再读一小节"} | changes


def annual(year, *, holidays=(), makeup_workdays=(), solar_terms=()):
    return {"schema": SCHEMA, "year": year, "holidays": list(holidays),
            "makeup_workdays": list(makeup_workdays), "solar_terms": list(solar_terms)}


class ConfiguredAnnualCalendarTests(unittest.TestCase):
    def test_utf8_byte_limit_rejects_oversized_multibyte_rows_and_blank_text(self):
        rows = [{"date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
                 "name": "节" * 64} for index in range(80)]
        value = json.dumps([annual(2026, solar_terms=rows)], ensure_ascii=False)
        self.assertLess(len(value), 16384)
        self.assertGreater(len(value.encode("utf-8")), 16384)
        for invalid in (value, " " * 16385):
            with self.subTest(size=len(invalid)), self.assertRaises(ConfigurationError):
                configured_annual_calendars(invalid)

    def test_timezone_window_keeps_configured_days_distinct_from_fixed_holidays(self):
        calendars = configured_annual_calendars(json.dumps([
            annual(2026, holidays=[{"name": "合成假期", "start": "2026-12-31", "end": "2026-12-31"}]),
            annual(2027, makeup_workdays=[{"date": "2027-01-01", "name": "合成调休"}],
                   solar_terms=[{"date": "2027-01-01", "name": "合成节气"},
                                {"date": "2027-01-03", "name": "窗口外节气"}]),
        ], ensure_ascii=False))
        context = planning_calendar_context(datetime(2026, 12, 31, 15, 30, tzinfo=timezone.utc),
                                            datetime(2027, 1, 1, 16, 0, tzinfo=timezone.utc),
                                            ZoneInfo("Asia/Shanghai"), calendars)
        self.assertEqual(context["today"]["local_date"], "2026-12-31")
        self.assertEqual(context["fixed_gregorian_holidays_in_window"],
                         [{"date": "2027-01-01", "name": "元旦"}])
        self.assertEqual(context["configured_annual_calendar"], {
            "basis": "operator_configured_annual_calendar", "years": [2026, 2027], "partial": False,
            "days": [
                {"date": "2026-12-31", "holiday": "合成假期", "makeup_workday": None, "solar_terms": []},
                {"date": "2027-01-01", "holiday": None, "makeup_workday": "合成调休",
                 "solar_terms": ["合成节气"]},
            ],
        })

    def test_expanded_holiday_is_bounded_and_marked_partial(self):
        calendars = configured_annual_calendars(json.dumps([
            annual(2026, holidays=[{"name": "合成休假", "start": "2026-01-01", "end": "2026-04-06"}])
        ], ensure_ascii=False))
        context = planning_calendar_context(datetime(2026, 1, 1, tzinfo=timezone.utc),
                                            datetime(2026, 5, 1, tzinfo=timezone.utc),
                                            ZoneInfo("UTC"), calendars)["configured_annual_calendar"]
        self.assertTrue(context["partial"])
        self.assertLess(len(context["days"]), 96)
        self.assertEqual(context["days"][0]["date"], "2026-01-01")
        self.assertLessEqual(sum(len(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                                 for row in context["days"]), 4096)


class PlanningOutputTests(unittest.TestCase):
    def job(self):
        return dict(mode="daily", at=NOW, end=NOW + timedelta(hours=16), slot="today",
            settings={"planning_max_items": 12, "planning_timezone": "Asia/Shanghai"},
            goal_refs={}, calendar_refs={}, existing=[])

    def test_fence_and_optional_fields_do_not_lose_valid_siblings(self):
        text = "```json\n" + json.dumps({"items": [output(), output(title="错误时长", minutes=-1),
            output(title="散步", detail="想看看落叶", start=(NOW + timedelta(hours=2)).isoformat())]}, ensure_ascii=False) + "\n```"
        items, rejected = parse_output(text, self.job())
        self.assertEqual([i[0]["title"] for i in items], ["读下一小节", "散步"])
        self.assertEqual(rejected, ({"index": 1, "code": "invalid_plan_item"},))

    def test_no_identity_or_unknown_parent_or_naive_time_enters_calendar(self):
        for changes in ({"owner": "forged"}, {"goal_id": "unknown"}, {"parent_id": "unknown"},
                        {"start": "2026-09-21T10:00:00"}, {"minutes": True}):
            with self.subTest(changes=changes), self.assertRaises(TaskError):
                parse_output(json.dumps({"items": [output(**changes)]}), self.job())

    def test_duplicate_items_and_existing_calendar_are_not_saved_twice(self):
        job = self.job()
        item = output()
        items, _ = parse_output(json.dumps([item, item]), job)
        self.assertEqual(len(items), 1)
        event = items[0][0]
        job["existing"] = [(event["title"], event["schedule"]["anchor"], event["duration_minutes"])]
        self.assertEqual(parse_output(json.dumps([item]), job)[0], [])

    def test_empty_plan_is_allowed_and_unfinished_json_is_not_inferred(self):
        self.assertEqual(parse_output('{"items":[]}', self.job()), ([], ()))
        with self.assertRaises(TaskError):
            parse_output('{"items":[', self.job())


class CalendarRefinementTests(StateFixture, unittest.IsolatedAsyncioTestCase):
    async def test_refinement_preserves_schedule_other_occurrences_and_revision_checks(self):
        _, app, context, manager = self.setup_state()
        self.configure(manager, calendar_enabled=True)
        data = calendar_data(schedule=json.loads(encode(Schedule(NOW + timedelta(hours=1), "Asia/Shanghai", Frequency.DAILY, count=3))))
        app.calendar.command(context, identifier="reading", action="create", expected_revision=0,
            operation_key="create", data=data)
        receipt = app.calendar.command(context, identifier="reading", action="refine", expected_revision=1,
            operation_key="refine", data={"sequence": 1, "detail": "继续第二小节，保留未完成的疑问"})
        self.assertEqual(receipt["revision"], 2)
        current = app.calendar.read(context, "reading")
        self.assertEqual(current["schedule"], data["schedule"])
        self.assertEqual(current["state"], "accepted")
        occurrences = app.calendar.occurrences(context, start=NOW, end=NOW + timedelta(days=3))["items"]
        self.assertEqual([x["detail"] for x in occurrences], [data["detail"], "继续第二小节，保留未完成的疑问", data["detail"]])
        with self.assertRaises(TaskError):
            app.calendar.command(context, identifier="reading", action="refine", expected_revision=1,
                operation_key="stale", data={"sequence": 1, "detail": "不能覆盖人工新稿"})
        self.assertTrue(app.calendar.command(context, identifier="reading", action="refine", expected_revision=1,
            operation_key="refine", data={"sequence": 1, "detail": "继续第二小节，保留未完成的疑问"})["replayed"])

    async def test_planning_options_require_core_and_do_not_issue_calendar_grants(self):
        _, app, context, manager = self.setup_state()
        self.configure(manager, planning_enabled=True, planning_horizon_days=180)
        with self.assertRaises(TaskError):
            app.calendar.access.check(context, "calendar.write")
        before = manager.status(self.core).unwrap()
        rejected = manager.command(self.important, dict(action="configure", operation_key="not-core",
            edit_token=before["edit_token"], changes={"calendar_enabled": True}))
        self.assertFalse(rejected.is_success)
        for changes in ({"planning_timezone": "Mars/Unknown"}, {"planning_horizon_days": 367},
                        {"planning_prompt": "过长" * 3000},
                        {"planning_annual_calendars": "{}"},
                        {"planning_annual_calendars": json.dumps([annual(2026), annual(2026)])},
                        {"planning_annual_calendars": json.dumps([
                            annual(2026, holidays=[{"name": "太多", "start": "2026-01-01", "end": "2026-04-08"}])])},
                        {"planning_annual_calendars": json.dumps([annual(2026)], ensure_ascii=False) + " " * 16385}):
            before = manager.status(self.core).unwrap()
            result = manager.command(self.core, dict(action="configure", operation_key="bad-" + str(len(str(changes))),
                edit_token=before["edit_token"], changes=changes))
            self.assertFalse(result.is_success)
            self.assertEqual(manager.status(self.core).unwrap()["settings"], before["settings"])


class CalendarPlanningTests(StateFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.profiles += (planning_profile("primary", max_output_tokens=100),
                          growth_progress_profile("primary", max_output_tokens=100))
        self.registry = FieldRegistry(version="planning-tests", fields=configuration_fields(self.profiles))

    async def ready(self, *, automatic=False):
        host, app, context, manager = self.setup_state()
        self.configure(manager, calendar_enabled=True, planning_enabled=True)
        await self.start(host)
        app.state_maintenance.bind(context, "这是原角色，喜欢阅读也愿意休息。")
        if not automatic:
            app.calendar_planning.next_checks[context.key] = NOW + timedelta(days=1)
        self.model_behavior = lambda envelope: self.response(envelope)
        return app, context, manager

    async def response(self, envelope):
        return answered(json.dumps({"items": [output(self.clock.now())]}, ensure_ascii=False))

    async def test_foreground_private_date_reads_role_calendar_without_turning_gaps_into_facts(self):
        app, context, manager = await self.ready()
        self.configure(manager, planning_annual_calendars=json.dumps([annual(2026,
            holidays=[{"name": "合成休假", "start": "2026-09-22", "end": "2026-09-22"}],
            solar_terms=[{"date": "2026-09-23", "name": "合成节气"}])], ensure_ascii=False))
        source = self.source(app, context, "date-input")
        event = InboundConversationEvent("date-event", context.actor.principal, context.scope,
                                         source, "text", "date-input", self.clock.now())
        batch = app.messages.accept(context, event, role_instruction="原角色提示").unwrap()
        row = app.messages.batch(batch)

        self.clock.advance(datetime(2026, 9, 21, 16, 30, tzinfo=timezone.utc) - self.clock.now())
        request = app.messages._request(row, context, self.clock.now())
        payload = json.loads(next(item.payload for item in request.context.materials
                                  if item.purpose == "local_calendar_context"))
        self.assertEqual(payload["local_date"], "2026-09-22")
        self.assertEqual(payload["configured_annual_calendar"]["listed_today"], {"holiday": "合成休假"})
        self.assertIn("未列日期和未配置年份", request.instruction)

        self.clock.advance(timedelta(days=1))
        next_day = app.messages._request(row, context, self.clock.now())
        payload = json.loads(next(item.payload for item in next_day.context.materials
                                  if item.purpose == "local_calendar_context"))
        self.assertEqual(payload["configured_annual_calendar"]["listed_today"],
                         {"solar_terms": ["合成节气"]})

    async def test_sealed_private_reply_receives_only_configured_upcoming_dates(self):
        app, context, _ = await self.ready()
        contact = ContactManagement(app, context)
        before = contact.status(self.core).unwrap()
        target_day = self.clock.now().astimezone(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=2)
        contact.configure(self.core, {"operation_key": "important-date-context",
            "edit_token": before["edit_token"], "changes": {
                "date_checkin_enabled": False,
                "important_dates": json.dumps([{"month": target_day.month, "day": target_day.day,
                                                "label": "相识纪念日"}], ensure_ascii=False),
                "important_date_lookahead_days": 2,
                "quiet_timezone": "Asia/Shanghai",
            }}).unwrap()
        source = self.source(app, context, "important-date-context")
        event = InboundConversationEvent("important-date-context", context.actor.principal, context.scope,
                                         source, "text", "important-date-context", self.clock.now())
        batch = app.messages.accept(context, event, role_instruction="原角色提示").unwrap()
        app.messages.seal(context, batch, deadline_at=self.clock.now() + timedelta(minutes=2)).unwrap()
        request = app.messages._request(app.messages.batch(batch), context, self.clock.now())
        material = next(item for item in request.context.materials if item.purpose == "upcoming_important_dates")
        projection = json.loads(material.payload)
        self.assertEqual(projection["entries"], [{"label": "相识纪念日", "date": target_day.isoformat(),
                                                  "days_until": 2, "calendar": "gregorian"}])
        self.assertIn("不证明用户与日期的关系", request.instruction)

    async def plan(self, app, context, *, slot="manual-day", mode="daily", occurrence=None):
        return await app.calendar_planning.run(context, app.state_maintenance.bindings[context.key][1],
            mode=mode, slot=slot, occurrence=occurrence)

    async def test_real_host_saves_same_calendar_and_only_once_without_delivery_or_completion(self):
        app, context, manager = await self.ready()
        result = await self.plan(app, context)
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(result["saved"], 1)
        entries = app.calendar.inventory(context)["items"]
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0]["kind"], entries[0]["state"]), ("role_plan", "accepted"))
        self.assertEqual(entries[0]["planning"]["mode"], "daily")
        self.assertEqual(manager.status(self.core).unwrap()["calendar"]["items"][0]["id"], entries[0]["id"])
        self.assertEqual(self.called[0].original.role_instruction, app.state_maintenance.bindings[context.key][1])
        self.assertEqual(self.sent, [])
        self.assertTrue((await self.plan(app, context))["replayed"])
        self.assertEqual(len(self.called), 1)
        self.advance(app, 86400)
        self.assertEqual(app.calendar.read(context, entries[0]["id"])["state"], "accepted")
        report = await app.close()
        self.assertEqual(report.pending_handles, ())

    async def test_concurrent_manual_change_blocks_stale_whole_plan(self):
        app, context, _ = await self.ready()
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(envelope):
            entered.set()
            await release.wait()
            return answered(json.dumps({"items": [output()]}))
        self.model_behavior = delayed
        task = asyncio.create_task(self.plan(app, context))
        await asyncio.wait_for(entered.wait(), 3)
        app.calendar.command(context, identifier="human-edit", action="create", expected_revision=0,
            operation_key="human-edit", data=calendar_data(title="人工安排"))
        release.set()
        result = await task
        self.assertNotEqual(result["state"], "succeeded")
        self.assertEqual([i["id"] for i in app.calendar.inventory(context)["items"]], ["human-edit"])

    async def test_configuration_disabled_during_generation_prevents_commit(self):
        app, context, manager = await self.ready()
        async def disable(envelope):
            self.configure(manager, planning_enabled=False)
            return answered(json.dumps({"items": [output()]}))
        self.model_behavior = disable
        result = await self.plan(app, context)
        self.assertNotEqual(result["state"], "succeeded")
        self.assertEqual(app.calendar.inventory(context)["items"], [])

    async def test_confirmed_goal_links_long_term_node_and_daily_step_with_revocable_sources(self):
        app, context, _ = await self.ready()
        self.grant(context.actor, context.scope, "role.growth.read")
        source = SourceRef("drawing-wish", "test", context.scope, VersionRef("drawing-wish", 1), NOW)
        body = "可以慢慢学水彩，保留休息时间。"
        app.messages.sources.publish(SourceRecord(source, context.audience, digest(body), body), observed_at=NOW).unwrap()
        owner = app.role_growth_context.reader.owner(context)
        app.role_growth.add(RoleGrowthRecord("watercolor", owner, context.scope, GrowthKind.GOAL,
            "练习水彩", "先熟悉色彩，再尝试风景", "尚未开始", (source,), NOW, NOW,
            proposed_by=context.actor.subject))
        app.role_growth.confirm("watercolor", owner=owner, scope=context.scope, expected_revision=1,
            operation_id="confirm-watercolor", actor=self.core.subject, observed_at=NOW)
        async def horizon(envelope):
            return answered(json.dumps({"items": [output(title="尝试第一张风景", start=(NOW + timedelta(days=7)).isoformat(), goal_id="watercolor")]}))
        self.model_behavior = horizon
        result = await self.plan(app, context, mode="horizon", slot="long-node")
        self.assertEqual(result["state"], "succeeded", result)
        long = app.calendar.inventory(context)["items"][0]
        self.assertEqual(long["planning"]["goal"], {"growth_id": "watercolor", "revision": 2})
        activity = app.role_life.add_activity(RoleActivity("watercolor-practice",
            context.role_binding.role.subject_id, context.scope, NOW, RoleActivityState.ACTIVE,
            description="到河边练习水彩"))
        app.role_life.transition_activity(activity.activity_id, owner=activity.owner,
            expected_revision=activity.revision, state=RoleActivityState.COMPLETED,
            operation_id="watercolor-practice-done", observed_at=NOW)
        async def progress(_):
            return answered(json.dumps({"growth_id": "watercolor",
                "progress_note": "完成一次河边水彩练习。"}, ensure_ascii=False))
        self.model_behavior = progress
        report = await app.growth_progress.run(context, app.state_maintenance.bindings[context.key][1],
            "activity", "watercolor-practice-done")
        self.assertEqual(report["state"], "succeeded", report)
        review = GrowthProgressManagement(app)
        item = review.list(operator=self.core, context=context).unwrap()["items"][0]
        self.assertEqual(item["base_revision"], 2)
        self.assertEqual(review.command(operator=self.core, context=context, review_id=item["review_id"],
            action="accept", expected_revision=2, view_token=item["view_token"],
            operation_key="accept-watercolor-practice").unwrap()["applied_revision"], 3)
        captured = capture(app.calendar_planning, context, app.state_maintenance.bindings[context.key][1],
            "daily", "after-growth-review")
        self.assertEqual(captured["goal_refs"]["watercolor"], {"growth_id": "watercolor", "revision": 3})
        self.assertEqual(captured["material"]["confirmed_goals_and_skills"][0]["progress_note"],
                         "完成一次河边水彩练习。")
        async def daily(envelope):
            return answered(json.dumps({"items": [output(title="练习调色", goal_id="watercolor", parent_id=long["id"])]}))
        self.model_behavior = daily
        result = await self.plan(app, context)
        self.assertEqual(result["state"], "succeeded", result)
        step = next(i for i in app.calendar.inventory(context)["items"] if i["id"] != long["id"])
        self.assertEqual(step["planning"]["goal"], {"growth_id": "watercolor", "revision": 3})
        self.assertEqual(step["planning"]["parent"], {"id": long["id"], "revision": 1})
        self.revoke_source(app, source)
        self.assertEqual(app.calendar.inventory(context)["items"], [])
        with self.assertRaises(TaskError):
            app.calendar.read(context, step["id"])

    async def test_refines_only_current_period_and_skips_expired_slots(self):
        app, context, _ = await self.ready()
        app.calendar.command(context, identifier="recurring", action="create", expected_revision=0,
            operation_key="recurring", data=calendar_data(schedule=json.loads(encode(
                Schedule(NOW + timedelta(minutes=5), "Asia/Shanghai", Frequency.DAILY, count=3)))))
        item = app.calendar.occurrences(context, start=NOW, end=NOW + timedelta(minutes=15))["items"][0]
        async def detail(envelope):
            return answered('{"detail":"先翻回书签，再读下一页"}')
        self.model_behavior = detail
        result = await self.plan(app, context, mode="refine", slot="first-refine", occurrence=item)
        self.assertEqual(result["state"], "succeeded", result)
        record = app.calendar.read(context, "recurring")
        self.assertEqual(record["details"], {"0": "先翻回书签，再读下一页"})
        self.assertEqual(record["state"], "accepted")
        self.assertFalse(record.get("reminder_id"))

    async def test_automatic_tick_uses_current_date_then_weekly_nodes(self):
        app, context, _ = await self.ready(automatic=True)
        await self.until(lambda: context.key in app.calendar_planning.results)
        first = app.calendar_planning.results[context.key]
        self.assertEqual(first["mode"], "daily", first)
        self.advance(app, 31)
        await self.until(lambda: app.calendar_planning.results[context.key].get("mode") == "horizon")
        self.assertEqual(app.state, "running", app.failure_code)
        self.assertEqual(len(self.called), 2)
        self.assertEqual(self.sent, [])

    async def test_calendar_material_is_bounded_and_marks_omitted_details(self):
        app, context, manager = await self.ready()
        self.configure(manager, planning_prompt="保留空闲" * 800, planning_annual_calendars=json.dumps([
            annual(2026, holidays=[{"name": "合成假期", "start": "2026-09-21", "end": "2026-12-25"}])
        ], ensure_ascii=False))
        for index in range(30):
            app.calendar.command(context, identifier=f"large-{index:03}", action="create", expected_revision=0,
                operation_key=f"large-{index:03}", data=calendar_data(title="待考虑的安排 " + str(index), detail="旧说明" * 1365))
        job = capture(app.calendar_planning, context, app.state_maintenance.bindings[context.key][1], "horizon", "bounded")
        self.assertLessEqual(len(json.dumps(job["material"], ensure_ascii=False)), MATERIAL_CHARS)
        self.assertTrue(job["material"]["calendar_context"]["configured_annual_calendar"]["partial"])
        self.assertTrue(job["material"]["coverage"]["material_limited"])
        self.assertTrue(job["material"]["coverage"]["calendar_details_partial"])
        self.assertLess(len(job["material"]["calendar"]), 30)

    async def test_planning_calendar_context_uses_role_timezone_without_claiming_leave(self):
        from datetime import datetime, timezone

        app, context, manager = await self.ready()
        self.configure(manager, planning_timezone="Asia/Shanghai", planning_horizon_days=120)
        self.clock.advance(datetime(2026, 9, 30, 16, 30, tzinfo=timezone.utc) - self.clock.now())
        instruction = app.state_maintenance.bindings[context.key][1]
        daily = capture(app.calendar_planning, context, instruction, "daily", "calendar-day")
        self.assertEqual(daily["material"]["calendar_context"]["today"]["local_date"], "2026-10-01")
        self.assertEqual(daily["material"]["calendar_context"]["today"]["weekday"], "星期四")
        self.assertEqual(daily["material"]["calendar_context"]["fixed_gregorian_holidays_in_window"],
                         [{"date": "2026-10-01", "name": "国庆节"}])
        horizon = capture(app.calendar_planning, context, instruction, "horizon", "calendar-horizon")
        self.assertEqual(horizon["material"]["calendar_context"]["fixed_gregorian_holidays_in_window"],
                         [{"date": "2026-10-01", "name": "国庆节"}, {"date": "2027-01-01", "name": "元旦"}])
        self.assertIn("不代表放假", INSTRUCTION)

    async def test_capture_uses_configured_annual_dates_and_rejects_stale_settings(self):
        app, context, manager = await self.ready()
        data = json.dumps([annual(2026, holidays=[
            {"name": "合成休假", "start": "2026-10-01", "end": "2026-10-02"}],
            makeup_workdays=[{"date": "2026-10-04", "name": "合成调休"}])], ensure_ascii=False)
        self.configure(manager, planning_annual_calendars=data)
        self.clock.advance(datetime(2026, 9, 30, 16, 30, tzinfo=timezone.utc) - self.clock.now())
        instruction = app.state_maintenance.bindings[context.key][1]
        daily = capture(app.calendar_planning, context, instruction, "daily", "configured-day")
        projected = daily["material"]["calendar_context"]["configured_annual_calendar"]
        self.assertEqual([row["date"] for row in projected["days"]], ["2026-10-01"])
        self.assertEqual(projected["days"][0]["holiday"], "合成休假")
        self.assertEqual(projected["basis"], "operator_configured_annual_calendar")
        horizon = capture(app.calendar_planning, context, instruction, "horizon", "configured-horizon")
        self.assertEqual([row["date"] for row in
                          horizon["material"]["calendar_context"]["configured_annual_calendar"]["days"]],
                         ["2026-10-01", "2026-10-02", "2026-10-04"])
        self.assertIn("未提供的年份或日期视为未知", INSTRUCTION)
        self.configure(manager, planning_annual_calendars="")
        with self.assertRaises(TaskError):
            validate(app.calendar_planning, horizon, self.clock.now())


    async def test_dst_gap_blocks_planning_without_faulting_host(self):
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        app, context, manager = await self.ready()
        self.configure(manager, planning_timezone="America/New_York", planning_refine_minutes=180)
        self.clock.advance(datetime(2027, 3, 14, 6, 30, tzinfo=timezone.utc) - self.clock.now())
        now = self.clock.now()
        app.calendar.command(context, identifier="dst-gap", action="create", expected_revision=0,
            operation_key="dst-gap", data=calendar_data(schedule=json.loads(encode(Schedule(
                datetime(2027, 3, 13, 7, 30, tzinfo=timezone.utc), "America/New_York", Frequency.DAILY, count=3)))))
        local = now.astimezone(ZoneInfo("America/New_York"))
        for mode, period in (("daily", local.date().isoformat()), ("horizon", "%04d-W%02d" % local.isocalendar()[:2])):
            slot = mode + ":America/New_York:" + period
            identifier = app.calendar_planning.identifier(context, slot)
            app.calendar_planning.operations.reserve(OperationRef(identifier, "calendar.planning", context.scope,
                VersionRef(identifier, 1), identifier), parameter_hash=digest(slot), observed_at=now).unwrap()
        app.calendar_planning.advance()
        self.assertEqual(app.calendar_planning.results[context.key]["state"], "blocked")
        self.assertEqual(app.calendar_planning.results[context.key]["code"], "schedule_needs_resolution")
        app.notify()
        await asyncio.sleep(0.02)
        self.assertEqual(app.state, "running", app.failure_code)

    async def test_moving_one_occurrence_retains_its_refinement_identity(self):
        app, context, _ = await self.ready()
        app.calendar.command(context, identifier="movable", action="create", expected_revision=0,
            operation_key="movable", data=calendar_data(schedule=json.loads(encode(Schedule(NOW + timedelta(minutes=5), "Asia/Shanghai")))))
        settings = app.role_state.settings(context)[0]
        # Mark the two broader opportunities so the scheduler reaches refinement.
        for _ in range(2):
            mode, slot, _ = app.calendar_planning.opportunity(context, settings, NOW)
            identifier = app.calendar_planning.identifier(context, slot)
            app.calendar_planning.operations.reserve(OperationRef(identifier, "calendar.planning", context.scope,
                VersionRef(identifier, 1), identifier), parameter_hash=digest(slot), observed_at=NOW).unwrap()
        original = app.calendar_planning.opportunity(context, settings, NOW)
        app.calendar.command(context, identifier="movable", action="exception", expected_revision=1,
            operation_key="move", data={"sequence": 0, "start": (NOW + timedelta(minutes=10)).isoformat()})
        moved = app.calendar_planning.opportunity(context, settings, NOW)
        self.assertEqual(original[1], moved[1])
        self.assertNotEqual(original[2]["start"], moved[2]["start"])

    async def test_invalid_model_output_keeps_original_calendar_and_does_not_replay(self):
        app, context, _ = await self.ready()
        async def malformed(envelope):
            return answered('{"items":[{"title":"半截')
        self.model_behavior = malformed
        result = await self.plan(app, context)
        self.assertNotEqual(result["state"], "succeeded")
        self.assertEqual(app.calendar.inventory(context)["items"], [])
        self.assertTrue((await self.plan(app, context))["replayed"])
        self.assertEqual(len(self.called), 1)

    async def test_shutdown_cancels_planning_and_restart_keeps_attempt_ledger(self):
        app, context, _ = await self.ready()
        entered = asyncio.Event()
        async def hanging(envelope):
            entered.set()
            await asyncio.Event().wait()
        self.model_behavior = hanging
        task = asyncio.create_task(self.plan(app, context))
        await asyncio.wait_for(entered.wait(), 3)
        await app.close()
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(app.calendar_planning.attempted(context, "manual-day"))
        self.assertEqual(app.calendar.records.list(context), ())
        self.assertEqual(app.calendar_planning.active_handles, ())

    async def test_the_daily_slot_is_gated_by_local_date_and_never_by_time_of_day(self):
        # C2-5: life_schedule_config.daily_plan_time is retired because V2 gates the
        # daily plan by local date, not by a time. V1 required "at or after 07:30"
        # (daily_state.py:10208-10213); here any hour on the same local day produces
        # the identical attempt key, which is what makes a configurable time
        # meaningless rather than merely missing.
        app, context, _ = await self.ready()
        settings = app.role_state.settings(context)[0]
        values = planning_values(settings)
        zone = ZoneInfo(values["planning_timezone"])
        day = self.clock.now().astimezone(zone).date()
        seen = set()
        for hour in range(24):
            local = datetime.combine(day, time(hour=hour, minute=5), tzinfo=zone)
            opportunity = app.calendar_planning.opportunity(context, values, local.astimezone(timezone.utc))
            self.assertIsNotNone(opportunity, f"hour {hour} produced no daily opportunity")
            self.assertEqual(opportunity[0], "daily")
            seen.add(opportunity[1])
        # One key for the whole local day, and it carries the date, not an hour.
        self.assertEqual(len(seen), 1, seen)
        slot = seen.pop()
        self.assertEqual(slot, "daily:" + values["planning_timezone"] + ":" + day.isoformat())
        self.assertNotIn(":", day.isoformat())

    async def test_the_next_local_day_is_a_new_slot(self):
        app, context, _ = await self.ready()
        settings = app.role_state.settings(context)[0]
        values = planning_values(settings)
        zone = ZoneInfo(values["planning_timezone"])
        day = self.clock.now().astimezone(zone).date()
        first = app.calendar_planning.opportunity(
            context, values, datetime.combine(day, time(23, 59), tzinfo=zone).astimezone(timezone.utc))
        after_midnight = datetime.combine(day + timedelta(days=1), time(0, 1), tzinfo=zone)
        second = app.calendar_planning.opportunity(context, values, after_midnight.astimezone(timezone.utc))
        self.assertNotEqual(first[1], second[1])
        self.assertTrue(second[1].endswith((day + timedelta(days=1)).isoformat()))

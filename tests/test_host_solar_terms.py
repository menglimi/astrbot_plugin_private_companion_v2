"""The host supplied solar-term table and its wiring into date context.

``companion_v2`` only ever consumes an injected lookup object, so the table is
the producer half of that contract: until it existed the automatic source
reported ``unavailable`` no matter how the private window was configured.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from astrbot_host.solar_terms import (
    MAXIMUM_YEAR, MINIMUM_YEAR, TERM_NAMES, SolarTermTablePort, configured_solar_term_port,
)
from companion_v2.conversation.date_context import project_local_date
from companion_v2.conversation.solar_terms import lookup_solar_terms, names_on


class SolarTermTableTests(unittest.TestCase):
    def test_every_term_of_a_year_is_produced_once_in_calendar_order(self):
        rows = SolarTermTablePort().terms(2026)
        self.assertEqual(len(rows), 24)
        self.assertEqual([name for _, name in rows], list(TERM_NAMES))
        self.assertEqual([day for day, _ in rows], sorted(day for day, _ in rows))
        self.assertTrue(all(day.year == 2026 for day, _ in rows))

    def test_known_dates_match_the_published_calendar(self):
        rows = dict((name, day) for day, name in SolarTermTablePort().terms(2026))
        # Values the mean-value formula reproduces exactly; the term boundary can
        # drift by one day at the edges, which is why the table is atmosphere only.
        self.assertEqual(rows["立春"], date(2026, 2, 4))
        self.assertEqual(rows["清明"], date(2026, 4, 5))
        self.assertEqual(rows["夏至"], date(2026, 6, 22))
        self.assertEqual(rows["冬至"], date(2026, 12, 22))

    def test_a_year_outside_the_fitted_range_is_refused(self):
        port = SolarTermTablePort()
        for year in (MINIMUM_YEAR - 1, MAXIMUM_YEAR + 1, "2026", None, 2026.0):
            with self.subTest(year=year):
                with self.assertRaises(ValueError):
                    port.terms(year)

    def test_the_port_returns_flat_pairs_the_consumer_accepts(self):
        lookup = lookup_solar_terms(SolarTermTablePort(), 2026)
        self.assertEqual(lookup.status, "available")
        self.assertEqual(names_on(lookup, date(2026, 2, 4)), ("立春",))

    def test_configured_port_needs_no_extra_switch_and_only_narrows_years(self):
        self.assertIsInstance(configured_solar_term_port(None), SolarTermTablePort)
        narrowed = configured_solar_term_port({"minimum_year": 2020, "maximum_year": 2030})
        self.assertEqual(narrowed.terms(2030)[0][0].year, 2030)
        with self.assertRaises(ValueError):
            narrowed.terms(2031)
        with self.assertRaises(ValueError):
            configured_solar_term_port(["not", "an", "object"])

    def test_repeated_lookups_reuse_one_table(self):
        port = SolarTermTablePort()
        self.assertIs(port.terms(2026), port.terms(2026))


class SolarTermDateContextTests(unittest.TestCase):
    def test_an_injected_table_makes_the_automatic_source_available(self):
        result = project_local_date(datetime(2026, 9, 23, 4, tzinfo=timezone.utc), "Asia/Shanghai",
                                    automatic_solar_terms_enabled=True, solar_term_port=SolarTermTablePort())
        automatic = result["automatic_solar_terms"]
        self.assertEqual(automatic["status"], "available")
        self.assertEqual(automatic["upcoming"], [{"date": "2026-09-24", "days_ahead": 1, "names": ["秋分"]}])

    def test_the_window_switch_still_decides_whether_the_table_is_consulted(self):
        class Recording(SolarTermTablePort):
            def __init__(self):
                super().__init__()
                self.calls = []

            def lookup(self, year):
                self.calls.append(year)
                return super().lookup(year)

        port = Recording()
        disabled = project_local_date(datetime(2026, 9, 23, 4, tzinfo=timezone.utc), "Asia/Shanghai",
                                      automatic_solar_terms_enabled=False, solar_term_port=port)
        self.assertEqual(disabled["automatic_solar_terms"]["status"], "disabled")
        self.assertEqual(port.calls, [])

    def test_no_injected_table_stays_unavailable(self):
        result = project_local_date(datetime(2026, 9, 23, 4, tzinfo=timezone.utc), "Asia/Shanghai",
                                    automatic_solar_terms_enabled=True)
        self.assertEqual(result["automatic_solar_terms"]["status"], "unavailable")

    def test_an_operator_calendar_still_overrides_the_automatic_table(self):
        calendar = type("Calendar", (), {
            "year": 2026,
            "on": lambda self, day: type("Day", (), {
                "holiday": None, "makeup_workday": None,
                "solar_terms": ("管理员秋分",) if day.isoformat() == "2026-09-23" else (),
            })(),
        })()
        result = project_local_date(datetime(2026, 9, 23, 4, tzinfo=timezone.utc), "Asia/Shanghai",
                                    annual_calendars=(calendar,),
                                    automatic_solar_terms_enabled=True, solar_term_port=SolarTermTablePort())
        automatic = result["automatic_solar_terms"]
        self.assertEqual(automatic["today"], ["管理员秋分"])
        self.assertEqual(automatic["effective_source"], "operator_configured_annual_calendar")


if __name__ == "__main__":
    unittest.main()

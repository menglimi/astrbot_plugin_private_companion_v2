"""Important dates are private, forward-only context within their configured window."""

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from companion_v2.proactive.date_context import project_important_dates


class ImportantDateContextTests(unittest.TestCase):
    def test_gregorian_date_uses_the_configured_private_timezone_and_window(self):
        at = datetime(2026, 9, 24, 16, 30, tzinfo=timezone.utc)
        settings = {"important_dates": '[{"month":9,"day":27,"label":"相识纪念日"}]',
                    "lookahead_days": 2, "timezone": "Asia/Shanghai"}
        result = project_important_dates(at, settings)
        self.assertEqual(result["timezone"], "Asia/Shanghai")
        self.assertEqual(result["entries"], [{"label": "相识纪念日", "date": "2026-09-27",
                                              "days_until": 2, "calendar": "gregorian"}])
        settings["lookahead_days"] = 1
        self.assertEqual(project_important_dates(at, settings)["entries"], [])

    def test_lunar_date_uses_the_local_lunar_projection(self):
        at = datetime(2026, 9, 24, 16, 30, tzinfo=timezone.utc)
        settings = {"important_dates": '[{"calendar":"lunar","month":8,"day":20,"label":"农历生日"}]',
                    "lookahead_days": 0, "timezone": "Asia/Shanghai"}
        with patch("companion_v2.proactive.date_context.lunar_date_parts", return_value=(2026, 8, 20, False)):
            result = project_important_dates(at, settings)
        self.assertEqual(result["entries"], [{"label": "农历生日", "date": "2026-09-25",
                                              "days_until": 0, "calendar": "lunar"}])

    def test_invalid_settings_do_not_fall_back_to_a_guessed_date(self):
        with self.assertRaises(ValueError):
            project_important_dates(datetime(2026, 9, 24, tzinfo=timezone.utc),
                {"important_dates": "[]", "lookahead_days": 31, "timezone": "Asia/Shanghai"})


if __name__ == "__main__":
    unittest.main()

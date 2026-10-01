from datetime import datetime, timezone

from companion_v2.conversation.date_context import project_local_date


class Provider:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def lookup(self, year):
        self.calls.append(year)
        return self.value


def test_automatic_provider_is_off_without_a_network_call():
    provider = Provider([{"date": "2026-09-25", "name": "秋分"}])
    result = project_local_date(datetime(2026, 9, 25, tzinfo=timezone.utc), "UTC", automatic_solar_terms_enabled=False, solar_term_port=provider)
    assert result["automatic_solar_terms"]["status"] == "disabled"
    assert provider.calls == []


def test_provider_data_is_projected_and_cross_year_lookup_is_supported():
    class CrossProvider(Provider):
        def lookup(self, year):
            self.calls.append(year)
            return [] if year == 2026 else [{"date": "2027-01-01", "name": "小寒"}]
    provider = CrossProvider(None)
    result = project_local_date(datetime(2026, 12, 31, 15, tzinfo=timezone.utc), "Asia/Shanghai",
                                automatic_solar_terms_enabled=True, solar_term_port=provider)
    assert result["automatic_solar_terms"]["status"] == "available"
    assert result["automatic_solar_terms"]["upcoming"] == [{"date": "2027-01-01", "days_ahead": 1, "names": ["小寒"]}]
    assert provider.calls == [2026, 2027]


def test_provider_failure_is_unavailable_and_missing_data_is_unknown():
    failed = Provider(None)
    failed.lookup = lambda year: (_ for _ in ()).throw(RuntimeError("offline"))
    assert project_local_date(datetime(2026, 1, 1, tzinfo=timezone.utc), "UTC",
                              automatic_solar_terms_enabled=True, solar_term_port=failed)["automatic_solar_terms"]["status"] == "unavailable"
    missing = Provider(None)
    assert project_local_date(datetime(2026, 1, 1, tzinfo=timezone.utc), "UTC",
                              automatic_solar_terms_enabled=True, solar_term_port=missing)["automatic_solar_terms"]["status"] == "unknown"


def test_configured_annual_terms_override_provider_on_today_and_lookahead():
    class Provider:
        def lookup(self, year):
            return [{"date": "2026-09-25", "name": "自动今天"},
                    {"date": "2026-09-26", "name": "自动节气"},
                    {"date": "2026-09-27", "name": "自动未来"}]

    result = project_local_date(
        datetime(2026, 9, 25, tzinfo=timezone.utc), "UTC",
        annual_calendars=(type("Calendar", (), {
            "year": 2026,
            "on": lambda self, day: type("Day", (), {
                "holiday": None, "makeup_workday": None,
                "solar_terms": ("管理员未来",) if day.isoformat() == "2026-09-26" else (),
            })(),
        })(),),
        automatic_solar_terms_enabled=True, solar_term_port=Provider())
    assert result["automatic_solar_terms"]["today"] == ["自动今天"]
    assert result["automatic_solar_terms"]["upcoming"] == [{
        "date": "2026-09-26", "days_ahead": 1, "names": ["管理员未来"]
    }, {"date": "2026-09-27", "days_ahead": 2, "names": ["自动未来"]}]

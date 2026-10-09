"""V1 weather configuration converts into V2 settings without silently changing meaning."""

import json
import unittest

from companion_v2.agenda.planning_config import (DEFAULTS as PLANNING_DEFAULTS,
                                                 WEATHER_MAX_AGE_MINUTES, WEATHER_MAX_AGE_MINIMUM,
                                                 configured_weather_location, validate_settings)
from companion_v2.legacy.weather_migration import (CONTACT, STATE, convert_weather_config,
                                                   severity_for_colour)


LOCATION = {"weather_city": "杭州", "weather_lat": 30.25, "weather_lon": 120.17}


def convert(**config):
    return convert_weather_config({**LOCATION, **config}).unwrap()


def planning_settings(migration):
    """Feed the converted values through V2's own planning validator.

    Checking the converter against the validator is what makes "the migration
    succeeds" mean something: a value the consumer would refuse is a migration that
    fails at save time with an error the operator cannot act on.
    """
    values = dict(PLANNING_DEFAULTS)
    values["calendar_enabled"] = True
    for field_id, value in migration.changes.items():
        if field_id.startswith(STATE + "."):
            values[field_id.split(".", 1)[1]] = value
    return values


class SeverityMappingTests(unittest.TestCase):
    def test_colour_tiers_map_rank_for_rank_onto_cap_severities(self):
        for colour, severity in (("blue", "minor"), ("yellow", "moderate"),
                                 ("orange", "severe"), ("red", "extreme")):
            with self.subTest(colour=colour):
                self.assertEqual(severity_for_colour(colour), severity)

    def test_v1_all_becomes_v2_no_filter(self):
        for value in ("all", "ALL", "全部", ""):
            with self.subTest(value=value):
                self.assertEqual(severity_for_colour(value), "")

    def test_chinese_colour_names_are_accepted(self):
        self.assertEqual(severity_for_colour("红色"), "extreme")

    def test_unknown_value_degrades_to_no_filter_rather_than_failing(self):
        self.assertEqual(severity_for_colour("violet"), "")


class LocationTests(unittest.TestCase):
    def test_location_becomes_the_v2_json_document(self):
        migration = convert()
        location = configured_weather_location(migration.changes[STATE + ".planning_weather_location"])
        self.assertEqual((location.name, location.latitude, location.longitude),
                         ("杭州", 30.25, 120.17))

    def test_the_produced_document_passes_v2_own_parser(self):
        """The converter must emit something the consumer accepts, not just JSON."""
        for refresh in (5, 30, 90, 120, 240, 360):
            with self.subTest(refresh=refresh):
                migration = convert(weather_refresh_minutes=refresh)
                location = configured_weather_location(
                    migration.changes[STATE + ".planning_weather_location"])
                self.assertEqual(location.name, "杭州")
                validate_settings(planning_settings(migration))

    def test_a_qweather_location_id_is_not_used_as_a_place_name(self):
        """A bare number would surface in the interface as an unreadable label."""
        migration = convert_weather_config({
            "weather_location": "101020100", "weather_lat": 30.25, "weather_lon": 120.17}).unwrap()
        self.assertNotIn(STATE + ".planning_weather_location", migration.changes)
        self.assertIn("weather_location", migration.skipped)
        needs_input = [item for item in migration.differences if item.kind == "needs_input"]
        self.assertTrue(needs_input)
        # Without a location the observation cannot be enabled, whatever V1 said.
        self.assertFalse(migration.changes[STATE + ".planning_weather_enabled"])

    def test_missing_coordinates_are_reported_rather_than_invented(self):
        migration = convert_weather_config({"weather_city": "杭州"}).unwrap()
        self.assertNotIn(STATE + ".planning_weather_location", migration.changes)
        self.assertFalse(migration.changes[STATE + ".planning_weather_enabled"])

    def test_zero_coordinates_are_treated_as_absent(self):
        migration = convert_weather_config({"weather_city": "杭州", "weather_lat": 0, "weather_lon": 0}).unwrap()
        self.assertNotIn(STATE + ".planning_weather_location", migration.changes)

    def test_city_is_preferred_over_location_when_both_are_names(self):
        migration = convert_weather_config({**LOCATION, "weather_location": "浙江省杭州市"}).unwrap()
        document = json.loads(migration.changes[STATE + ".planning_weather_location"])
        self.assertEqual(document["name"], "杭州")

    def test_an_overlong_name_is_truncated_to_what_v2_accepts(self):
        migration = convert_weather_config({**LOCATION, "weather_city": "城" * 200}).unwrap()
        document = json.loads(migration.changes[STATE + ".planning_weather_location"])
        self.assertEqual(len(document["name"]), 64)


class FreshnessTests(unittest.TestCase):
    def test_a_long_v1_interval_is_narrowed_and_reported(self):
        migration = convert(weather_refresh_minutes=360)
        self.assertEqual(migration.changes[STATE + ".planning_weather_max_age_minutes"],
                         WEATHER_MAX_AGE_MINUTES)
        narrowed = [item for item in migration.differences if item.kind == "narrowed"]
        self.assertEqual(len(narrowed), 1)
        self.assertEqual((narrowed[0].v1_value, narrowed[0].v2_value), ("360", "120"))

    def test_an_interval_inside_the_range_survives_unchanged_and_unremarked(self):
        migration = convert(weather_refresh_minutes=45)
        self.assertEqual(migration.changes[STATE + ".planning_weather_max_age_minutes"], 45)
        self.assertEqual([item for item in migration.differences if item.kind == "narrowed"], [])

    def test_a_zero_interval_is_lifted_to_the_floor_not_left_at_zero(self):
        """V2 rejects anything below the minimum, so zero would fail the save."""
        migration = convert(weather_refresh_minutes=0)
        self.assertEqual(migration.changes[STATE + ".planning_weather_max_age_minutes"],
                         WEATHER_MAX_AGE_MINIMUM)

    def test_an_unparsable_interval_falls_back_to_the_v1_default(self):
        migration = convert(weather_refresh_minutes="soon")
        self.assertEqual(migration.changes[STATE + ".planning_weather_max_age_minutes"], 90)


class BoundTests(unittest.TestCase):
    """Every converted integer must sit inside the range its V2 field declares."""

    def test_converted_values_stay_inside_their_declared_bounds(self):
        ranges = {STATE + ".planning_weather_max_age_minutes": (WEATHER_MAX_AGE_MINIMUM, WEATHER_MAX_AGE_MINUTES),
                  CONTACT + ".official_alert_poll_minutes": (1, 1440),
                  CONTACT + ".weather_sample_minutes": (10, 1440),
                  CONTACT + ".dedup_weather_window_minutes": (0, 2880)}
        for field_id, (minimum, maximum) in ranges.items():
            for probe in (-5, 0, 1, 3, 99, 1441, 99999):
                with self.subTest(field=field_id, value=probe):
                    source = ("environment_change_check_minutes" if field_id.endswith("weather_sample_minutes")
                              else "environment_change_cooldown_minutes" if field_id.endswith("dedup_weather_window_minutes")
                              else "weather_alert_refresh_minutes" if field_id.endswith("official_alert_poll_minutes")
                              else "weather_refresh_minutes")
                    value = convert(**{source: probe}).changes.get(field_id)
                    if value is None:
                        continue
                    self.assertGreaterEqual(value, minimum)
                    self.assertLessEqual(value, maximum)


class DifferenceReportingTests(unittest.TestCase):
    def test_credentials_are_not_carried_into_role_settings(self):
        migration = convert(weather_api_host="abc.xy.qweatherapi.com", weather_token="secret",
                            weather_alert_token="alert-secret")
        for field_id in migration.changes:
            self.assertNotIn("token", field_id)
            self.assertNotIn("api_host", field_id)
        self.assertNotIn("secret", json.dumps(migration.document(), ensure_ascii=False))

    def test_every_skipped_key_is_also_explained(self):
        """A skip the operator cannot see is indistinguishable from a bug."""
        migration = convert(weather_source="qweather", weather_amap_api_key="amap-key",
                            enable_yesterday_screen_diary_context=True,
                            weather_alert_api_key="alert-key",
                            mobile_location_weather_sensitivity="sensitive")
        explained = {item.field_id for item in migration.differences}
        for key in migration.skipped:
            with self.subTest(key=key):
                self.assertIn(key, explained)

    def test_the_alert_api_key_is_reported_without_reproducing_its_value(self):
        """V1 允许用它代替 weather_alert_token 存预警凭据；漏报等于悄悄丢一份凭据。"""
        migration = convert(weather_alert_api_key="alert-secret")
        self.assertIn("weather_alert_api_key", migration.skipped)
        explained = next(item for item in migration.differences
                         if item.field_id == "weather_alert_api_key")
        self.assertEqual(explained.kind, "not_migrated")
        self.assertEqual(explained.v1_value, "（已填写，值不在此显示）")
        self.assertNotIn("alert-secret", json.dumps(migration.document(), ensure_ascii=False))

    def test_mobile_location_sensitivity_is_reported_as_not_migrated(self):
        migration = convert(mobile_location_weather_sensitivity="sensitive")
        self.assertIn("mobile_location_weather_sensitivity", migration.skipped)
        explained = next(item for item in migration.differences
                         if item.field_id == "mobile_location_weather_sensitivity")
        self.assertEqual(explained.kind, "not_migrated")

    def test_the_cooldown_is_reported_as_resemanticised(self):
        migration = convert(environment_change_cooldown_minutes=90)
        item = next(item for item in migration.differences if item.kind == "resemanticised")
        self.assertEqual(migration.changes[CONTACT + ".dedup_weather_window_minutes"], 90)
        self.assertIn("event_revision", item.summary)

    def test_global_source_selector_is_left_for_plugin_configuration_migration(self):
        migration = convert_weather_config({"weather_source": "qweather"}).unwrap()
        self.assertNotIn("weather_source", migration.skipped)
        self.assertNotIn("weather_source", {item.field_id for item in migration.differences})

    def test_a_renamed_severity_is_reported_even_though_it_succeeded(self):
        migration = convert(weather_alert_min_severity="red")
        self.assertEqual(migration.changes[CONTACT + ".official_alert_min_severity"], "extreme")
        renamed = [item for item in migration.differences if item.kind == "renamed"]
        self.assertEqual((renamed[0].v1_value, renamed[0].v2_value), ("red", "extreme"))


class SwitchTests(unittest.TestCase):
    def test_v1_string_booleans_are_understood(self):
        for value in ("true", "True", "yes", "1", "on", True, 1):
            with self.subTest(value=value):
                self.assertTrue(convert(enable_weather_alerts=value)
                                .changes[CONTACT + ".official_weather_alert_enabled"])
        for value in ("false", "no", "0", "off", False, 0, ""):
            with self.subTest(value=value):
                self.assertFalse(convert(enable_weather_alerts=value)
                                 .changes[CONTACT + ".official_weather_alert_enabled"])

    def test_weather_context_on_without_a_location_is_downgraded_and_reported(self):
        migration = convert_weather_config({"enable_weather_context": True}).unwrap()
        self.assertFalse(migration.changes[STATE + ".planning_weather_enabled"])
        downgraded = [item for item in migration.differences if item.kind == "downgraded"]
        self.assertEqual(len(downgraded), 1)

    def test_weather_context_with_a_location_keeps_its_role_weather_meaning(self):
        migration = convert_weather_config({"enable_weather_context": True, **LOCATION}).unwrap()
        self.assertTrue(migration.changes[STATE + ".planning_weather_enabled"])
        self.assertNotIn(CONTACT + ".weather_checkin_enabled", migration.changes)

    def test_the_two_environment_settings_split_into_v2_shapes(self):
        migration = convert(enable_environment_change_proactive=True,
                            environment_change_check_minutes=15)
        self.assertTrue(migration.changes[CONTACT + ".weather_change_enabled"])
        self.assertEqual(migration.changes[CONTACT + ".weather_sample_minutes"], 15)


class InputTests(unittest.TestCase):
    def test_a_non_mapping_is_refused(self):
        for value in (None, [], "weather", 7):
            with self.subTest(value=value):
                self.assertFalse(convert_weather_config(value).is_success)

    def test_unknown_keys_are_ignored_so_an_older_install_still_converts(self):
        """V1 grew keys across releases; a stranger one must not abort the migration."""
        migration = convert(some_future_weather_flag=True, weather_refresh_minutes=60)
        self.assertEqual(migration.changes[STATE + ".planning_weather_max_age_minutes"], 60)

    def test_an_empty_configuration_still_produces_a_coherent_result(self):
        migration = convert_weather_config({}).unwrap()
        self.assertFalse(migration.changes[STATE + ".planning_weather_enabled"])
        self.assertFalse(migration.changes[CONTACT + ".official_weather_alert_enabled"])
        self.assertNotIn(STATE + ".planning_weather_location", migration.changes)

    def test_the_document_round_trips_through_json(self):
        migration = convert(weather_source="qweather", weather_refresh_minutes=360)
        restored = json.loads(json.dumps(migration.document(), ensure_ascii=False))
        self.assertEqual(sorted(restored["changes"]), sorted(migration.changes))


if __name__ == "__main__":
    unittest.main()

"""Tests for the time-alignment and leakage risks that can change conclusions."""
import unittest
from datetime import date, datetime, timedelta

from run_pilot import (UTC, HKT, PADDING_C, absolute_error_bounds,
                       coverage_hours, daily_diagnostic, day_window, select_issue)


def interval(a, b, value, variable="tmax"):
    origin = datetime(2024, 1, 1, tzinfo=UTC)
    return {"interval_start_utc": origin+timedelta(hours=a),
            "valid_time_utc": origin+timedelta(hours=b),
            "temperature_c": value, "short_name": variable, "source_id": str(b)}


class FairnessTests(unittest.TestCase):
    def test_hong_kong_day_is_previous_utc16_to_current_utc16(self):
        start, end = day_window(date(2024, 1, 2))
        self.assertEqual(start, datetime(2024, 1, 1, 16, tzinfo=UTC))
        self.assertEqual(end-start, timedelta(hours=24))

    def test_overlaps_do_not_double_count_coverage(self):
        start, end = day_window(date(2024, 1, 2))
        rows = [interval(12, 18, 20), interval(18, 21, 21), interval(18, 24, 22),
                interval(24, 30, 23), interval(30, 36, 24), interval(36, 42, 25)]
        self.assertEqual(coverage_hours(rows, start, end), 24)
        self.assertEqual(coverage_hours(rows[:-2], start, end), 14)

    def test_cross_midnight_peak_cannot_be_assigned_to_target_day(self):
        rows = [interval(12, 18, 30), interval(18, 24, 21), interval(24, 30, 22),
                interval(30, 36, 20), interval(36, 39, 21), interval(36, 42, 29)]
        result = daily_diagnostic(rows, date(2024, 1, 2), "tmax")
        self.assertEqual(result["inner_coverage_hours"], 21)
        self.assertEqual(result["gfs_lower_c"], 22-PADDING_C)
        self.assertEqual(result["gfs_upper_c"], 30+PADDING_C)
        self.assertFalse(result["exact_window_tiling"])

    def test_minimum_envelope_reverses_inner_and_outer_sets(self):
        rows = [interval(12, 18, 10, "tmin"), interval(18, 24, 14, "tmin"),
                interval(24, 30, 16, "tmin"), interval(30, 36, 17, "tmin"),
                interval(36, 42, 12, "tmin")]
        result = daily_diagnostic(rows, date(2024, 1, 2), "tmin")
        self.assertEqual(result["gfs_lower_c"], 10-PADDING_C)
        self.assertEqual(result["gfs_upper_c"], 14+PADDING_C)

    def test_missing_boundary_prevents_bounded_daily_score(self):
        rows = [interval(18, 24, 21), interval(24, 30, 22), interval(30, 36, 20)]
        result = daily_diagnostic(rows, date(2024, 1, 2), "tmax")
        self.assertIsNone(result["gfs_upper_c"])
        self.assertIsNone(result["gfs_lower_c"])

    def test_coarse_message_uses_its_own_quantization_allowance(self):
        rows = [interval(12, 18, 20), interval(18, 24, 21), interval(24, 30, 22),
                interval(30, 36, 20), interval(36, 42, 21)]
        rows[2]["packing_step_c"] = 0.1
        result = daily_diagnostic(rows, date(2024, 1, 2), "tmax")
        self.assertAlmostEqual(result["gfs_lower_c"], 21.9)
        self.assertAlmostEqual(result["gfs_upper_c"], 22.1)

    def test_instant_at_next_midnight_belongs_to_next_day(self):
        result = daily_diagnostic([interval(16, 16, 20, "2t"), interval(40, 40, 30, "2t")],
                                  date(2024, 1, 2), "tmax")
        self.assertEqual(result["sample_count"], 1)
        self.assertEqual(result["gfs_sampled_c"], 20)

    def test_error_interval_when_observation_lies_inside(self):
        self.assertEqual(absolute_error_bounds(19, 23, 21), (0, 2))
        self.assertEqual(absolute_error_bounds(19, 23, 25), (2, 6))
        with self.assertRaises(ValueError):
            absolute_error_bounds(23, 19, 21)

    def test_late_publication_cannot_enter_cutoff(self):
        cutoff = datetime(2024, 1, 1, 20, tzinfo=HKT)
        def issue(n, hour, publish_hour):
            return {"forecast_issue_id": n, "bulletin_time_hkt": datetime(2024, 1, 1, hour),
                    "published_time_utc": datetime(2024, 1, 1, publish_hour, tzinfo=HKT)}
        selected = select_issue([issue(1, 11, 11), issue(2, 19, 21), issue(3, 21, 21)], cutoff)
        self.assertEqual(selected["forecast_issue_id"], 1)

    def test_previous_day_bulletin_is_not_silently_reused(self):
        previous = {"forecast_issue_id": 1, "bulletin_time_hkt": datetime(2023, 12, 31, 19),
                    "published_time_utc": datetime(2023, 12, 31, 19, tzinfo=HKT)}
        with self.assertRaises(ValueError):
            select_issue([previous], datetime(2024, 1, 1, 20, tzinfo=HKT))


if __name__ == "__main__":
    unittest.main()

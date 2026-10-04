"""Offline checks: python -m unittest discover -s data_management/model_forecasts."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import manage_gfs as manager


class IndexTests(unittest.TestCase):
    INDEX = "\n".join((
        "1:0:d=2024010100:TMP:surface:6 hour fcst:",
        "2:100:d=2024010100:TMP:2 m above ground:6 hour fcst:",
        "3:200:d=2024010100:TMAX:2 m above ground:0-6 hour max fcst:",
        "4:300:d=2024010100:TMIN:2 m above ground:0-6 hour min fcst:",
        "5:400:d=2024010100:UGRD:10 m above ground:6 hour fcst:",
    ))

    def test_exact_ranges_and_height(self):
        result = manager.selected_ranges(self.INDEX, ["TMP", "TMAX", "TMIN"])
        self.assertEqual([(r[0], r[1]) for r in result], [(100, 199), (200, 299), (300, 399)])

    def test_open_ended_last_message(self):
        result = manager.selected_ranges(self.INDEX, ["TMP", "UGRD"])
        # UGRD is not 2 m: only the 2 m temperature is selected.
        self.assertEqual(len(result), 1)
        truncated_index = "\n".join(self.INDEX.splitlines()[:2])
        self.assertIsNone(manager.selected_ranges(truncated_index, ["TMP"])[0][1])

    def test_no_temperature_and_corrupt_index(self):
        for index in ("", "invalid", self.INDEX.replace("2:100:", "2:0:")):
            with self.assertRaises(ValueError):
                manager.selected_ranges(index, ["TMP"])
        with self.assertRaises(ValueError):
            manager.selected_ranges(self.INDEX, ["TMAX"])


class DecodeTests(unittest.TestCase):
    def setUp(self):
        import eccodes
        self.ec = eccodes
        gid = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
        try:
            for key, value in (
                ("dataDate", 20240101), ("dataTime", 0),
                ("typeOfLevel", "heightAboveGround"), ("level", 2),
                ("paramId", 167), ("stepUnits", 1), ("forecastTime", 6),
            ):
                eccodes.codes_set(gid, key, value)
            count = eccodes.codes_get(gid, "numberOfDataPoints")
            eccodes.codes_set_values(gid, [300.0] * count)
            self.message = eccodes.codes_get_message(gid)
        finally:
            eccodes.codes_release(gid)
        self.run = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.stations = [{"station_code": "TEST", "latitude": 40.0, "longitude": 10.0}]

    def test_kelvin_conversion_and_vintage(self):
        rows = manager.decode_temperature(self.message, self.stations, self.run, 6)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["temperature_c"], 26.85)
        self.assertEqual(rows[0]["valid_time_utc"], "2024-01-01T06:00:00+00:00")
        self.assertEqual(rows[0]["step_type"], "instant")

    def test_reject_wrong_run_and_hour(self):
        with self.assertRaises(ValueError):
            manager.decode_temperature(self.message, self.stations, self.run.replace(day=2), 6)
        with self.assertRaises(ValueError):
            manager.decode_temperature(self.message, self.stations, self.run, 9)

    def test_reject_truncated_messages(self):
        with self.assertRaises(ValueError):
            manager.decode_temperature(self.message[:-10], self.stations, self.run, 6)


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        directory = MagicMock()
        directory.glob.return_value = [Path("test/run/source.json")]
        self.args = SimpleNamespace(directory=directory, dry_run=False)

    def test_refresh_after_setup_and_failed_import(self):
        with patch.object(manager, "connect") as connection, \
             patch.object(manager, "load_download", side_effect=ValueError("invalid source")), \
             patch("schema_document.refresh_schema_document") as refresh:
            with self.assertRaisesRegex(ValueError, "invalid source"):
                manager.import_downloads(self.args)
            self.assertEqual(refresh.call_count, 2)
            # Mocked connection only: this test never connects to a real DB.
            connection.return_value.__enter__.return_value.execute.assert_called_once()

    def test_documentation_failure_is_not_silently_ignored(self):
        with patch.object(manager, "connect"), \
             patch("schema_document.refresh_schema_document", side_effect=OSError("locked file")):
            with self.assertRaisesRegex(RuntimeError, "Schema setup committed"):
                manager.import_downloads(self.args)

    def test_dry_run_does_not_connect_or_refresh(self):
        self.args.dry_run = True
        with patch.object(manager, "connect") as connection, \
             patch.object(manager, "load_download", return_value=({}, [{}])), \
             patch("schema_document.refresh_schema_document") as refresh:
            manager.import_downloads(self.args)
            connection.assert_not_called()
            refresh.assert_not_called()

    def test_snapshot_preserves_human_guidance(self):
        from schema_document import BEGIN_MARKER, END_MARKER, merge_snapshot
        first = merge_snapshot("Human instructions.\n", "Initial catalog")
        self.assertTrue(first.startswith("Human instructions.\n"))
        revised = merge_snapshot(first + "\nHuman footer.\n", "Updated catalog")
        self.assertTrue(revised.endswith("\nHuman footer.\n"))
        self.assertIn("Updated catalog", revised)
        self.assertNotIn("Initial catalog", revised)
        self.assertEqual(revised.count(BEGIN_MARKER), 1)
        self.assertEqual(revised.count(END_MARKER), 1)

    def test_invalid_snapshot_markers_are_rejected(self):
        from schema_document import BEGIN_MARKER, END_MARKER, merge_snapshot
        for content in (BEGIN_MARKER, END_MARKER, END_MARKER + BEGIN_MARKER,
                        BEGIN_MARKER + BEGIN_MARKER + END_MARKER):
            with self.assertRaises(ValueError):
                merge_snapshot(content, "New catalog")


if __name__ == "__main__":
    unittest.main()

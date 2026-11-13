"""Offline checks for coverage, field validation and atomic streaming commits."""
import unittest
import json
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
from pathlib import Path

import stream_gfs as stream


class CoverageTests(unittest.TestCase):
    def test_full_year_all_cycles_and_buffer(self):
        items = list(stream.tasks(date(2024, 12, 24), date(2026, 1, 1), [0, 6, 12, 18]))
        self.assertEqual(len(items), 96980)
        self.assertEqual(len(set(items)), len(items))
        self.assertEqual(items[-1][1], 192)
        self.assertEqual(items[0][0].isoformat(), '2024-12-24T00:00:00+00:00')
        self.assertEqual(items[-1][0].isoformat(), '2025-12-31T18:00:00+00:00')

    def test_resume_rejects_partial_or_wrong_station_extracts(self):
        conn = MagicMock()
        run = datetime(2025, 1, 1, tzinfo=timezone.utc)
        stations = [{'station_code': 'HKO', 'latitude': 22.3, 'longitude': 114.17}]
        conn.execute.return_value.fetchall.return_value = [
            (run, 0, stations, stream.FIELDS, 'HKO', ['instant']),
            (run, 3, stations, stream.FIELDS, 'HKO', ['instant', 'max', 'min']),
            (run, 6, stations, stream.FIELDS, 'HKO', ['instant', 'max']),
            (run, 9, [], stream.FIELDS, 'HKO', ['instant', 'max', 'min']),
        ]
        self.assertEqual(stream.completed_tasks(conn, date(2025, 1, 1), date(2026, 1, 1),
                                                [0, 6, 12, 18], stations), {(run, 0), (run, 3)})


class FieldTests(unittest.TestCase):
    def setUp(self):
        self.run = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.stations = [{'station_code': 'HKO'}]
        end = (self.run + timedelta(hours=3)).isoformat()
        self.rows = [dict(station_code='HKO', step_type=step, temperature_c=20.,
                          valid_time_utc=end,
                          interval_start_utc=end if step == 'instant' else self.run.isoformat())
                     for step in ['instant', 'max', 'min']]

    def test_valid_fields_and_missing_extreme(self):
        stream.validate_rows(self.rows, self.stations, self.run, 3)
        with self.assertRaises(ValueError):
            stream.validate_rows(self.rows[:2], self.stations, self.run, 3)

    def test_reject_duplicate_extreme_or_placeholder(self):
        self.rows[-1]['step_type'] = 'max'
        with self.assertRaises(ValueError):
            stream.validate_rows(self.rows, self.stations, self.run, 3)
        self.rows[-1]['step_type'] = 'min'
        self.rows[-1]['temperature_c'] = -273.15
        with self.assertRaises(ValueError):
            stream.validate_rows(self.rows, self.stations, self.run, 3)

    def test_reject_wrong_valid_time(self):
        self.rows[0]['valid_time_utc'] = self.run.isoformat()
        with self.assertRaises(ValueError):
            stream.validate_rows(self.rows, self.stations, self.run, 3)


class CommitTests(unittest.TestCase):
    def test_failed_readback_raises_inside_atomic_transaction(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        manifest = {key: 'test' for key in stream.SOURCE_COLUMNS}
        row = {key: 1 for key in stream.manager.VALUE_COLUMNS}
        row['station_code'] = 'HKO'
        with self.assertRaisesRegex(ValueError, 'Post-insert station row count'):
            stream.commit_source(conn, ('source sql', 'value sql'), manifest, [row])
        self.assertIs(conn.transaction.return_value.__exit__.call_args.args[0], ValueError)


class NativeWorkerTests(unittest.TestCase):
    def test_grib_metadata_decodes_in_isolated_workers(self):
        import eccodes as ec
        gid = ec.codes_grib_new_from_samples('regular_ll_sfc_grib2')
        try:
            message = ec.codes_get_message(gid)
        finally:
            ec.codes_release(gid)
        expected = stream.message_metadata(message)
        with ProcessPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(stream.message_metadata, [message] * 4))
        self.assertEqual(results, [expected] * 4)


@unittest.skipUnless(os.name == 'nt', 'Windows file-sharing regression')
class StatusSharingTests(unittest.TestCase):
    def test_reader_without_delete_sharing_does_not_stop_import(self):
        import ctypes
        from ctypes import wintypes
        create = ctypes.windll.kernel32.CreateFileW
        create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        create.restype = wintypes.HANDLE
        close = ctypes.windll.kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        with tempfile.TemporaryDirectory(dir=stream.manager.ROOT / 'tmp') as directory:
            path = Path(directory) / 'status.json'
            old = {'state': 'running', 'sources_done': 10}
            path.write_text(json.dumps(old), encoding='utf-8')
            # Share reads and writes, but not deletion/replacement: a genuine
            # Windows file handle, not a mock of the implementation.
            handle = create(str(path), 0x80000000, 3, None, 3, 0x80, None)
            self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
            state = {'state': 'running', 'sources_done': 11}
            try:
                self.assertFalse(stream.write_status(path, state, attempts=2, retry_delay=0))
                self.assertEqual(json.loads(path.read_text(encoding='utf-8')), old)
                self.assertEqual(state['sources_done'], 11)
            finally:
                close(handle)
            self.assertTrue(stream.write_status(path, state, attempts=2, retry_delay=0))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['sources_done'], 11)


if __name__ == '__main__':
    unittest.main()

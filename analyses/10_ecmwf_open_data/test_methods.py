"""Offline contract tests; no external HTTP calls or database writes."""
import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

SPEC = importlib.util.spec_from_file_location("ecmwf_investigation", Path(__file__).with_name("run_investigation.py"))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class Methods(unittest.TestCase):
    def test_historical_leads(self):
        self.assertEqual(len(m.STEPS), 57)
        self.assertIn(144, m.STEPS)
        self.assertNotIn(147, m.STEPS)
        self.assertIn(150, m.STEPS)
        self.assertEqual(m.STEPS[-1], 192)

    def test_old_archive_path(self):
        self.assertEqual(m.index_key(date(2024,1,1),168,"0p4-beta"),
                         "20240101/00z/0p4-beta/oper/20240101000000-168h-oper-fc.index")

    def test_new_archive_path(self):
        self.assertIn("/ifs/0p25/oper/",m.index_key(date(2025,1,1),24,"0p25"))

    def test_hong_kong_day(self):
        start,end=m.pilot.day_window(date(2025,1,2))
        self.assertEqual(start,datetime(2025,1,1,16,tzinfo=timezone.utc))
        self.assertEqual(end-start,timedelta(hours=24))

    def test_day_seven_needs_more_than_168_hours(self):
        run=datetime(2025,1,1,tzinfo=timezone.utc)
        _,end=m.pilot.day_window(date(2025,1,8))
        self.assertEqual((end-run).total_seconds()/3600,184)
        self.assertEqual(min(step for step in m.STEPS if step>=184),186)

    def test_union_not_sum(self):
        start=datetime(2025,1,1,tzinfo=timezone.utc)
        rows=[dict(interval_start_utc=start,valid_time_utc=start+timedelta(hours=6)),
              dict(interval_start_utc=start+timedelta(hours=3),valid_time_utc=start+timedelta(hours=9))]
        self.assertEqual(m.pilot.coverage_hours(rows,start,start+timedelta(days=1)),9)

    def test_temporal_envelope(self):
        run=datetime(2025,1,1,tzinfo=timezone.utc)
        rows=[]
        for end in range(3,73,3):
            for name,value in (("tmax",30.),("tmin",20.)):
                rows.append(dict(short_name=name,temperature_c=value,packing_step_c=.01,
                                 interval_start_utc=run+timedelta(hours=end-3),valid_time_utc=run+timedelta(hours=end),source_id=str(end)))
            rows.append(dict(short_name="2t",temperature_c=25.,valid_time_utc=run+timedelta(hours=end),source_id=str(end)))
        maximum=m.pilot.daily_diagnostic(rows,date(2025,1,2),"tmax")
        minimum=m.pilot.daily_diagnostic(rows,date(2025,1,2),"tmin")
        self.assertEqual(maximum["inner_coverage_hours"],21)
        self.assertEqual(maximum["outer_coverage_hours"],24)
        self.assertFalse(maximum["exact_window_tiling"])
        self.assertAlmostEqual(maximum["gfs_lower_c"],29.98)
        self.assertAlmostEqual(maximum["gfs_upper_c"],30.02)
        self.assertAlmostEqual(minimum["gfs_lower_c"],19.98)
        self.assertAlmostEqual(minimum["gfs_upper_c"],20.02)
        self.assertEqual(maximum["sample_count"],8)

    def test_partial_day_has_no_envelope(self):
        run=datetime(2025,1,1,tzinfo=timezone.utc)
        rows=[dict(short_name="tmax",temperature_c=30.,interval_start_utc=run+timedelta(hours=18),
                   valid_time_utc=run+timedelta(hours=21),source_id="one")]
        result=m.pilot.daily_diagnostic(rows,date(2025,1,2),"tmax")
        self.assertIsNone(result["gfs_lower_c"])
        self.assertEqual(result["outer_coverage_hours"],3)

    def test_absolute_error_bounds(self):
        self.assertEqual(m.pilot.absolute_error_bounds(25,27,26),(0,1))
        self.assertEqual(m.pilot.absolute_error_bounds(25,27,30),(3,5))
        with self.assertRaises(ValueError): m.pilot.absolute_error_bounds(27,25,26)

    def test_synthetic_metric_arithmetic(self):
        rows=m.metric_example()
        self.assertTrue(all(r["synthetic"] for r in rows))
        self.assertEqual(sum(r["hko_absolute_error_c"] for r in rows),5)
        self.assertEqual(sum(r["ifs_absolute_error_c"] for r in rows),3)
        self.assertAlmostEqual(sum(r["paired_difference_c"] for r in rows)/3,-2/3)

    def test_reject_full_grib_response(self):
        response=MagicMock()
        response.status_code=200
        response.__enter__.return_value=response
        with patch.object(m,"session") as mocked:
            mocked.return_value.get.return_value=response
            content,receipt=m.public_get("https://example.invalid/file",(10,19))
        self.assertIsNone(content)
        self.assertEqual(receipt["status"],200)
        response.iter_content.assert_not_called()

    def test_ignore_recorded_lead_zero_placeholders(self):
        base=dict(date="20250101",time="0000",type="fc",stream="oper",**{"class":"od"},levtype="sfc",_offset=0,_length=224)
        rows=[dict(base,param="2t",step="0"),dict(base,param="mx2t3",step="3"),dict(base,param="mn2t3",step="3")]
        content="\n".join(m.json.dumps(row) for row in rows).encode()
        metadata=dict(url="https://example.invalid/a.index",sha256=m.digest(content),retrieved_at_utc="2026-11-08T00:00:00+00:00")
        with patch.object(m,"cached_get",return_value=(content,metadata)):
            result,selected,_,_=m.inspect_index(date(2025,1,1),0,Path("unused"))
        self.assertEqual([row["param"] for row in selected],["2t"])
        self.assertEqual(len(result["excluded_mismatched_fields"]),2)

    def test_unexpected_nonzero_lead_mismatch_fails(self):
        row=dict(date="20250101",time="0000",type="fc",stream="oper",**{"class":"od"},levtype="sfc",_offset=0,_length=224,param="2t",step="23")
        with patch.object(m,"cached_get",return_value=(m.json.dumps(row).encode(),{})):
            with self.assertRaisesRegex(ValueError,"out-of-lead"):
                m.inspect_index(date(2025,1,1),24,Path("unused"))

    def test_reject_wrong_content_range(self):
        response=MagicMock()
        response.status_code=206
        response.headers={"Content-Range":"bytes 0-9/100"}
        response.__enter__.return_value=response
        with patch.object(m,"session") as mocked:
            mocked.return_value.get.return_value=response
            with self.assertRaisesRegex(ValueError,"Content-Range"):
                m.public_get("https://example.invalid/file",(10,19))

    def test_cache_rejects_tampering(self):
        temp_root=m.ROOT/"tmp"
        temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temporary:
            cache=Path(temporary)
            (cache/"message").write_bytes(b"changed")
            m.write_json(cache/"message.json",dict(sha256=m.digest(b"original"),url="https://example.invalid/",byte_range=None))
            with self.assertRaisesRegex(ValueError,"checksum"):
                m.cached_get(cache,"message","https://example.invalid/")


if __name__=="__main__": unittest.main()

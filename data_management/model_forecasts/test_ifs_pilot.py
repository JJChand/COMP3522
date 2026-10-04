import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import download_ifs_pilot as pilot


class IFSPilotTests(unittest.TestCase):
    def message(self, run_date=20240101):
        import eccodes as ec

        gid = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
        try:
            for key, value in (
                ("dataDate", run_date), ("dataTime", 0), ("paramId", 167),
                ("stepUnits", 1), ("forecastTime", 24), ("Ni", 17), ("Nj", 13),
                ("latitudeOfFirstGridPointInDegrees", 24),
                ("longitudeOfFirstGridPointInDegrees", 112),
                ("latitudeOfLastGridPointInDegrees", 21),
                ("longitudeOfLastGridPointInDegrees", 116),
                ("iDirectionIncrementInDegrees", 0.25),
                ("jDirectionIncrementInDegrees", 0.25),
            ):
                ec.codes_set(gid, key, value)
            ec.codes_set_values(gid, [290.0] * 221)
            return ec.codes_get_message(gid)
        finally:
            ec.codes_release(gid)

    def test_fixed_small_request(self):
        request = pilot.pilot_request()
        self.assertEqual(request["expver"], "1")
        self.assertEqual(request["type"], "fc")
        self.assertEqual(request["step"], "24")
        self.assertEqual(request["area"], "24/112/21/116")
        self.assertEqual(request["grid"], "0.25/0.25")
        self.assertNotIn("key", request)

    def test_decode_valid_and_reject_wrong_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.grib"
            path.write_bytes(self.message())
            self.assertEqual(pilot.validate_grib(path)[0]["numberOfDataPoints"], 221)
            path.write_bytes(self.message(20240102))
            with self.assertRaises(ValueError):
                pilot.validate_grib(path)

    def test_reject_two_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.grib"
            path.write_bytes(self.message() * 2)
            with self.assertRaises(ValueError):
                pilot.validate_grib(path)

    def test_progress_does_not_echo_server_details(self):
        with patch("builtins.print") as output:
            pilot.safe_progress("someone@example.test token=SECRET queued")
            output.assert_called_once_with("ECMWF status: queued", flush=True)


if __name__ == "__main__":
    unittest.main()

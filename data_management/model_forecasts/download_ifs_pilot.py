"""One historical operational IFS field; local download only, no DB connection."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
DEFAULT_DIRECTORY = HERE / "downloads" / "ifs_pilot"


def pilot_request():
    # Same run/parameter/lead as the user's catalogue request, plus a small
    # geographic subset and an explicit regridded output resolution.
    return {
        "class": "od", "stream": "oper", "expver": "1", "type": "fc",
        "date": "2024-01-01", "time": "00:00:00", "levtype": "sfc",
        "param": "167.128", "step": "24",
        "area": "24/112/21/116", "grid": "0.25/0.25",
    }


def credentials():
    from ecmwfapi.api import ANONYMOUS_APIKEY_VALUES, get_apikey_values

    values = get_apikey_values()
    if values == ANONYMOUS_APIKEY_VALUES or not all(values):
        raise ValueError("Authenticated ECMWF credentials are missing; configure .ecmwfapirc locally.")
    key, url, email = values
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.ecmwf.int" or parsed.username or parsed.password:
        raise ValueError("Use the official HTTPS API URL from the ECMWF key page.")
    return key, url, email


def safe_progress(message):
    # Client messages may contain personal details or signed download URLs.
    # Print only fixed status strings, never the raw server/client message.
    message = str(message).lower()
    for status in ("queued", "running", "complete", "done", "failed", "retry"):
        if status in message:
            print("ECMWF status: " + status, flush=True)
            return


def validate_grib(path):
    import eccodes as ec

    fields = []
    with Path(path).open("rb") as stream:
        while True:
            gid = ec.codes_grib_new_from_file(stream)
            if gid is None:
                break
            try:
                ec.codes_set(gid, "stepUnits", 1)
                metadata = {name: ec.codes_get(gid, name) for name in (
                    "edition", "paramId", "shortName", "dataDate", "dataTime",
                    "startStep", "endStep", "stepType", "units",
                    "validityDate", "validityTime", "gridType", "numberOfDataPoints",
                )}
                if (metadata["paramId"] != 167 or metadata["dataDate"] != 20240101 or
                    metadata["dataTime"] != 0 or metadata["endStep"] != 24 or
                    metadata["stepType"] != "instant" or
                    metadata["validityDate"] != 20240102 or metadata["validityTime"] != 0):
                    raise ValueError("Downloaded GRIB does not match the pilot run/variable/lead.")
                if metadata["units"] != "K":
                    raise ValueError("Unexpected temperature units in IFS pilot.")
                # Verify the requested geographic subset and 0.25-degree output.
                for name, expected in (
                    ("latitudeOfFirstGridPointInDegrees", 24.0),
                    ("longitudeOfFirstGridPointInDegrees", 112.0),
                    ("latitudeOfLastGridPointInDegrees", 21.0),
                    ("longitudeOfLastGridPointInDegrees", 116.0),
                    ("iDirectionIncrementInDegrees", 0.25),
                    ("jDirectionIncrementInDegrees", 0.25),
                ):
                    if abs(float(ec.codes_get(gid, name)) - expected) > 1e-6:
                        raise ValueError("Downloaded grid differs from the requested area/resolution.")
                if metadata["numberOfDataPoints"] != 221:
                    raise ValueError("Unexpected grid-point count in IFS pilot.")
                fields.append(metadata)
            finally:
                ec.codes_release(gid)
    if len(fields) != 1:
        raise ValueError("Expected exactly one GRIB field.")
    return fields


def run(args):
    from ecmwfapi import ECMWFService

    key, url, email = credentials()
    if args.check:
        print("Client installed; authenticated credential settings found. Values are not displayed.")
        print("Local check only: archive entitlement has not been tested.")
        return
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    name = "ifs_oper_20240101_00_f024_2t_hk_025"
    target = directory / (name + ".grib")
    manifest_path = directory / (name + ".json")
    request = pilot_request()
    if target.exists() or manifest_path.exists():
        if not target.exists() or not manifest_path.exists():
            raise ValueError("Existing pilot is incomplete; use another --directory rather than overwrite it.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if manifest.get("mars_request") != request or manifest.get("sha256") != digest:
            raise ValueError("Existing pilot metadata/checksum differs; refusing overwrite.")
        validate_grib(target)
        print("Verified cached pilot: " + str(target))
        return
    partial = directory / (name + ".grib.part")
    if partial.exists():
        raise ValueError("Partial download exists; use another --directory to preserve it.")
    print("Requesting one IFS temperature field (2024-01-01 00 UTC, +24 h).", flush=True)
    print("Hong Kong subset on a regridded 0.25-degree output grid. No database writes.", flush=True)
    try:
        service = ECMWFService("mars", key=key, url=url, email=email,
                               verbose=False, quiet=True, log=safe_progress)
        service.execute(request, str(partial))
    except Exception as exc:
        # Do not expose raw exceptions: they may contain email, token or URLs.
        lowered = str(exc).lower()
        if "restricted" in lowered or "unauthor" in lowered or "permission" in lowered or "access denied" in lowered:
            raise RuntimeError("ECMWF rejected archive access. Registration/key alone does not grant operational IFS archive entitlement.") from None
        raise RuntimeError("ECMWF request failed. Check archive entitlement, key validity, network and ECMWF service status. Raw error withheld to protect credentials.") from None
    fields = validate_grib(partial)
    digest = hashlib.sha256(partial.read_bytes()).hexdigest()
    manifest = {
        "provider": "ECMWF", "model": "IFS", "product": "operational deterministic forecast",
        "mars_request": request, "catalogue_url": "https://apps.ecmwf.int/archive-catalogue/",
        "run_time_utc": "2024-01-01T00:00:00+00:00", "forecast_hour": 24,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "availability_time_utc": None, "sha256": digest,
        "size_bytes": partial.stat().st_size, "grib_metadata": fields,
        "processing": "ECMWF server-side area subset and regridding to 0.25 degrees; not native IFS resolution.",
        "database_imported": False,
    }
    partial.rename(target)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Downloaded and validated: " + str(target))
    print("Saved request/checksum metadata: " + str(manifest_path))
    print("No database connection or writes. This is a pilot, not daily Tmax/Tmin.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check local client/credentials without network access")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, RuntimeError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Pilot failed. Check local credentials, dependencies and files; details withheld to protect secrets.", file=sys.stderr)
        sys.exit(1)

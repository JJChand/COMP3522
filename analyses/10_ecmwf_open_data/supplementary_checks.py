"""Small mirror, cycle and coastal-grid checks; public data and local files only."""
from datetime import date
import json
from pathlib import Path

import eccodes as ec

import run_investigation as inv


def run():
    results,cache=inv.HERE/"results",inv.HERE/"cache"
    db=json.loads((results/"database_check.json").read_text(encoding="utf-8"))
    station=db["station"]
    checks=[]
    key=inv.index_key(date(2025,1,1),24,"0p25")
    for provider,url in [
        ("AWS",inv.BASES["aws"]+key),
        ("Google",inv.BASES["google"]+key),
        ("ECMWF rolling endpoint","https://data.ecmwf.int/forecasts/"+key),
        ("Azure anonymous, no SAS","https://ai4edataeuwest.blob.core.windows.net/ecmwf/"+key),
        ("AWS 0.1-degree historical probe",inv.BASES["aws"]+key.replace("0p25","0p1").replace("-fc.index","-fc-sfc.index")),
    ]:
        body,receipt=inv.public_get(url)
        checks.append(dict(provider=provider,**receipt))
    for day,step in [(date(2024,3,5),168),(date(2024,3,6),168),
                     (date(2024,9,18),24),(date(2024,9,19),24),
                     (date(2024,11,12),24),(date(2024,11,13),24)]:
        key=inv.index_key(day,step,"0p25")
        body,receipt=inv.public_get(inv.BASES["google"]+key)
        fields=[] if body is None else [json.loads(line) for line in body.decode().splitlines() if line.strip()]
        parameters=sorted({f["param"] for f in fields if f.get("param") in inv.PARAMETERS})
        checks.append(dict(provider="Google transition cross-check",run_date=day.isoformat(),forecast_hour=step,
                           parameters=parameters,**receipt))
    # Historical short cycles used scda, not today's oper naming. No blanket
    # conclusion about all cycles/years is made from these individual probes.
    for hour,stream,step in [(12,"oper",168),(6,"scda",90),(6,"scda",144),(6,"scda",168)]:
        key=f"20250101/{hour:02d}z/ifs/0p25/{stream}/20250101{hour:02d}0000-{step}h-{stream}-fc.index"
        _,receipt=inv.public_get(inv.BASES["aws"]+key)
        checks.append(dict(provider="AWS historical cycle probe",cycle_utc=hour,forecast_hour=step,stream=stream,**receipt))
    inv.write_json(results/"access_checks.json",checks)
    aux,inventory,placeholders=[],[],[]
    for day in inv.PILOT_DATES:
        result,_,index_rows,_=inv.inspect_index(day,0,cache)
        surface=[r for r in index_rows if r.get("levtype")=="sfc"]
        inventory.append(dict(run_date=day.isoformat(),surface_parameters=sorted({r["param"] for r in surface}),
                              has_lsm=any(r["param"]=="lsm" for r in surface),
                              has_surface_geopotential=any(r["param"] in ("z","gh","orog") for r in surface),
                              excluded_mismatched_fields=result["excluded_mismatched_fields"]))
        for field in surface:
            if field["param"] in ("mx2t3","mn2t3") and int(field.get("step",0)) != 0:
                body,receipt=inv.get_field(day,0,result,field,cache)
                gid=ec.codes_new_from_message(body)
                try:
                    point=ec.codes_grib_find_nearest(gid,station["latitude"],station["longitude"],npoints=1)[0]
                    placeholders.append(dict(run_date=day.isoformat(),file_lead=0,index_step=field["step"],
                                             decoded_end_step=ec.codes_get(gid,"endStep"),parameter=field["param"],
                                             value=float(point["value"]),units=ec.codes_get(gid,"units"),
                                             field_bytes=len(body),sha256=receipt["sha256"],excluded=True))
                finally:
                    ec.codes_release(gid)
        for field in surface:
            if field["param"] not in ("lsm","z","gh","orog"):
                continue
            body,receipt=inv.get_field(day,0,result,field,cache)
            gid=ec.codes_new_from_message(body)
            try:
                for point in ec.codes_grib_find_nearest(gid,station["latitude"],station["longitude"],npoints=4):
                    unit=ec.codes_get(gid,"units")
                    value=float(point["value"])
                    aux.append(dict(run_date=day.isoformat(),parameter=field["param"],
                                    parameter_id=ec.codes_get(gid,"paramId"),unit=unit,
                                    latitude=float(point["lat"]),longitude=(float(point["lon"])+180)%360-180,
                                    distance_km=float(point["distance"]),value=value,
                                    model_height_m=value/9.80665 if field["param"]=="z" else None,
                                    source_url=receipt["url"],sha256=receipt["sha256"]))
            finally:
                ec.codes_release(gid)
    inv.write_json(results/"surface_parameter_inventory.json",inventory)
    inv.write_json(results/"excluded_placeholder_fields.json",placeholders)
    inv.write_csv(results/"coastal_grid_auxiliary.csv",aux)
    print(json.dumps(dict(access_checks=len(checks),auxiliary_points=len(aux),surface_inventory=inventory),indent=2))


if __name__=="__main__": run()

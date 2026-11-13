"""Build the repository-style technical findings report from saved evidence."""
from collections import Counter
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np

from run_investigation import HERE, write_csv, write_json

RESULTS=HERE/"results"
BLUE="#285B8F"
ORANGE="#C67525"
GRAY="#D9DFE5"
DARK="#252C34"


def load(name):
    return json.loads((RESULTS/name).read_text(encoding="utf-8"))


def md_table(columns,rows):
    return "\n".join(["| "+" | ".join(columns)+" |","| "+" | ".join("---" for _ in columns)+" |"]+
                     ["| "+" | ".join(str(x) for x in row)+" |" for row in rows])


def availability_regimes(anchors):
    regimes=[]
    for step in (24,168):
        current=None
        for row in sorted((r for r in anchors if r["forecast_hour"]==step),key=lambda r:r["run_date"]):
            key=(row["status"],row.get("resolution"),row.get("has_max"),row.get("has_min"))
            if current is None or current["key"]!=key:
                if current: regimes.append({k:v for k,v in current.items() if k!="key"})
                current=dict(key=key,forecast_hour=step,start_run_date=row["run_date"],end_run_date=row["run_date"],
                             run_count=0,resolution=row.get("resolution"),has_extrema=bool(row.get("has_max") and row.get("has_min")),status=row["status"])
            current["end_run_date"]=row["run_date"]
            current["run_count"]+=1
        if current: regimes.append({k:v for k,v in current.items() if k!="key"})
    return regimes


def save_figure(fig,name):
    fig.savefig(RESULTS/(name+".png"),dpi=180,bbox_inches="tight",facecolor="white")
    plt.close(fig)


def charts(anchors,cases,aux,station,examples):
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"axes.titlesize":14,
                         "axes.labelcolor":DARK,"text.color":DARK,"axes.spines.top":False,"axes.spines.right":False})
    dates=sorted({r["run_date"] for r in anchors})
    lookup={(r["run_date"],r["forecast_hour"]):r for r in anchors}
    matrix=[]
    for step in (24,168):
        matrix.append([0 if lookup[(d,step)]["status"]!="ok" else 2 if lookup[(d,step)]["has_max"] and lookup[(d,step)]["has_min"] else 1 for d in dates])
    fig,ax=plt.subplots(figsize=(12,3))
    ax.imshow(matrix,aspect="auto",interpolation="nearest",cmap=ListedColormap([ORANGE,GRAY,BLUE]),vmin=0,vmax=2)
    ticks=sorted(set([0,len(dates)-1]+[i for i,d in enumerate(dates) if d.endswith("-01-01") or d.endswith("-07-01")]))
    ax.set_xticks(ticks,[dates[i] for i in ticks])
    ax.set_yticks([0,1],["+24 h","+168 h"])
    ax.set_title("Historical IFS temperature availability: two anchor leads",loc="left",pad=18)
    ax.legend(handles=[Patch(facecolor=GRAY,label="Instantaneous 2t only"),Patch(facecolor=BLUE,label="2t + native min/max"),Patch(facecolor=ORANGE,label="Unavailable index")],
              loc="upper left",bbox_to_anchor=(0,-.27),ncol=3,frameon=False)
    fig.text(.125,-.12,"Every daily 00 UTC run, 2024–2025. Other leads/cycles are not fully audited. Isolated 2024-09-18 occurrence retained.",fontsize=10)
    save_figure(fig,"historical_coverage")
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True)
    for ax,variable in zip(axes,("tmax","tmin")):
        group=[c for c in cases if c["run_date"]=="2025-01-01" and c["variable"]==variable]
        x=np.array([c["lead_days"] for c in group])
        middle=np.array([c["interval_midpoint_c"] for c in group])
        low=np.array([c["interval_lower_c"] for c in group]);high=np.array([c["interval_upper_c"] for c in group])
        ax.errorbar(x,middle,yerr=np.array([middle-low,high-middle]),fmt="o-",color=BLUE,capsize=5,label="Interval proxy midpoint + sensitivity envelope")
        ax.plot(x,[c["sampled_extreme_c"] for c in group],"s--",color=ORANGE,label="Instantaneous sampled extreme")
        ax.set_ylabel(variable.upper()+" (°C)")
        ax.grid(axis="y",color="#E5E8EB",linewidth=.6)
        ax.axvline(5.5,color="#777777",linestyle=":",linewidth=1)
    axes[0].set_title("2025 engineering pilot: two daily-extreme approximations",loc="left",pad=15)
    axes[0].legend(frameon=False,fontsize=10,loc="best")
    axes[1].set_xticks(range(1,8),["D"+str(x) for x in range(1,8)])
    axes[1].set_xlabel("HKT target day after the single 2025-01-01 00 UTC run")
    fig.text(.125,.015,"Envelopes are conditional sensitivity ranges, NOT confidence intervals or certified bounds. Native consistency warnings remain.",fontsize=10)
    fig.tight_layout(rect=(0,.04,1,1))
    save_figure(fig,"daily_proxy_sensitivity")
    fig,ax=plt.subplots(figsize=(9,6))
    for run,color,marker in (("2024-01-01",ORANGE,"s"),("2025-01-01",BLUE,"o")):
        points=[r for r in aux if r["run_date"]==run and r["parameter"]=="lsm"]
        ax.scatter([r["longitude"] for r in points],[r["latitude"] for r in points],s=100,marker=marker,
                   facecolors="none",edgecolors=color,label=run+" public grid")
        for p in points:
            ax.annotate(f"LSM {p['value']:.2f}",(p["longitude"],p["latitude"]),xytext=(5,7 if run.startswith("2025") else -15),textcoords="offset points",color=color,fontsize=10)
    ax.scatter([station["longitude"]],[station["latitude"]],marker="*",s=180,color=DARK,label="HKO Headquarters")
    ax.set_xlabel("Longitude (°E)");ax.set_ylabel("Latitude (°N)")
    ax.set_aspect(1/np.cos(np.deg2rad(station["latitude"])))
    ax.set_title("Public-grid coordinates and land fractions near HKO",loc="left",pad=15)
    ax.legend(frameon=False,loc="lower right")
    ax.grid(color="#E5E8EB",linewidth=.6)
    fig.text(.125,.015,"Coordinate comparison, not a coastline map. LSM is a decoded public-grid land fraction, not a temperature correction.",fontsize=9)
    save_figure(fig,"coastal_grid_comparison")
    fig,ax=plt.subplots(figsize=(8,4.5))
    x=np.arange(len(examples))
    for offset,key,label,color in ((-.18,"hko_absolute_error_c","HKO",GRAY),(.18,"ifs_absolute_error_c","IFS",BLUE)):
        bars=ax.bar(x+offset,[r[key] for r in examples],width=.35,label=label,color=color,edgecolor=DARK,linewidth=.6)
        ax.bar_label(bars,fmt="%.0f",padding=4)
    ax.set_ylim(0,2.6);ax.set_xticks(x,[r["case"] for r in examples]);ax.set_ylabel("Absolute error (°C)")
    ax.set_title("Synthetic metric example—not measured forecast skill",loc="left",pad=15)
    ax.legend(frameon=False);ax.grid(axis="y",color="#E5E8EB",linewidth=.6);ax.set_axisbelow(True)
    fig.text(.125,-.015,"HKO MAE = 1.667°C; IFS MAE = 1.000°C; paired difference = −0.667°C. Three invented days, one fixed lead.",fontsize=10)
    save_figure(fig,"metric_example")


def run():
    meta=load("run_metadata.json");anchors=load("historical_index_audit.json")
    cases=load("daily_reconstruction_cases.json");db=load("database_check.json")
    verification=load("verification.json");access=load("access_checks.json")
    inventory=load("surface_parameter_inventory.json");placeholders=load("excluded_placeholder_fields.json")
    import csv
    with (RESULTS/"coastal_grid_auxiliary.csv").open(encoding="utf-8",newline="") as f:
        aux=[{k:float(v) if k in ("latitude","longitude","distance_km","value") else v for k,v in r.items()} for r in csv.DictReader(f)]
    examples=[dict(case="Day A",observed_tmax_c=25,hko_forecast_c=27,ifs_forecast_c=26,hko_absolute_error_c=2,ifs_absolute_error_c=1,paired_difference_c=-1),
              dict(case="Day B",observed_tmax_c=28,hko_forecast_c=27,ifs_forecast_c=29,hko_absolute_error_c=1,ifs_absolute_error_c=1,paired_difference_c=0),
              dict(case="Day C",observed_tmax_c=30,hko_forecast_c=32,ifs_forecast_c=29,hko_absolute_error_c=2,ifs_absolute_error_c=1,paired_difference_c=-1)]
    regimes=availability_regimes(anchors)
    write_csv(RESULTS/"availability_regimes.csv",regimes)
    write_csv(RESULTS/"native_crossfield_warnings.csv",meta["consistency"]["violations"])
    charts(anchors,cases,aux,db["station"],examples)
    coverage_table=md_table(["Year","Lead checked","Expected runs","Index + 2t available","Native min/max present"],
                            [[r["year"],"+"+str(r["forecast_hour"])+" h",r["expected"],r["has_2t"],r["has_extrema"]] for r in meta["coverage"]])
    regimes_table=md_table(["Lead","Run dates, inclusive","Resolution","Native interval extrema","Runs"],
                           [["+"+str(r["forecast_hour"])+" h",r["start_run_date"]+" to "+r["end_run_date"],r["resolution"],"Present" if r["has_extrema"] else "Absent",r["run_count"]] for r in regimes])
    pilots_table=md_table(["Initialization","Leads to +192 h","Decoded fields","Raw field MB","Nearest point","Distance"],
                          [[p["run_date"]+" 00 UTC",p["lead_count"],p["field_count"],f"{p['field_bytes']/1e6:.2f}",
                            f"{p['grid_points'][0][0]:.2f}°N, {p['grid_points'][0][1]:.2f}°E",f"{p['grid_points'][0][2]:.2f} km"] for p in meta["pilots"]])
    extrema_cases=[c for c in cases if c["interval_midpoint_c"] is not None]
    width_min=min(c["reconstruction_width_c"] for c in extrema_cases);width_max=max(c["reconstruction_width_c"] for c in extrema_cases)
    consistency=meta["consistency"]
    nearest_lsm={day:min((r for r in aux if r["run_date"]==day and r["parameter"]=="lsm"),key=lambda r:r["distance_km"])["value"] for day in ("2024-01-01","2025-01-01")}
    height=min((r for r in aux if r["parameter"]=="z"),key=lambda r:r["distance_km"])["model_height_m"]
    projection=meta["pilots"][1]["field_bytes"]*365/1e9
    daily_table=md_table(["Target date","Endpoint","Midpoint proxy °C","Sensitivity envelope °C","Inner / outer coverage h"],
                         [[c["valid_date"],c["variable"],f"{c['interval_midpoint_c']:.3f}",f"{c['interval_lower_c']:.3f}–{c['interval_upper_c']:.3f}",f"{c['inner_coverage_hours']:.0f} / {c['outer_coverage_hours']:.0f}"] for c in extrema_cases])
    example_table=md_table(["Synthetic case","Observed Tmax","HKO forecast","IFS forecast","HKO absolute error","IFS absolute error","IFS − HKO error"],
                           [[r["case"],r["observed_tmax_c"],r["hko_forecast_c"],r["ifs_forecast_c"],r["hko_absolute_error_c"],r["ifs_absolute_error_c"],r["paired_difference_c"]] for r in examples])
    links=json.loads((HERE/"research_sources.json").read_text(encoding="utf-8"))
    quality_findings=[
        dict(finding="2024 native-extrema schema is not uniform",severity="High",evidence="+24: 50/366; +168: 301/366 runs with both extrema",
             confidence="Direct full-period anchor-index measurement",risk="Unlabelled target/proxy changes across years",remediation="Pin period/variables and preserve an explicit fallback policy"),
        dict(finding="Lead-zero extrema placeholders",severity="High",evidence="Two 224-byte +3 h messages inside +0 file decode to 0 K",
             confidence="Direct decoded GRIB evidence",risk="Wrong lead or 0 K ingested as a valid forecast",remediation="Implemented narrow, logged filtering and regression test"),
        dict(finding="Native instantaneous/extrema inconsistency",severity="High for certified-bound claims",evidence=f"{consistency['endpoint_violations_after_disclosed_padding']}/{consistency['endpoint_comparisons']} comparisons exceed the chosen allowance",
             confidence="Direct decoded evidence; cause unresolved",risk="Sensitivity envelope misrepresented as guaranteed accuracy",remediation="Retain warning and proxy interpretation; seek provider clarification"),
        dict(finding="Coastal grid representativeness differs",severity="Medium",evidence="Nearest distance 20.97 vs 9.71 km; public LSM 0.6875 vs 0.390625",
             confidence="Direct grid/static-field measurements; no causal attribution",risk="Product skill and spatial mismatch conflated",remediation="Freeze extraction method and retain four-neighbor sensitivity"),
        dict(finding="Historical real-time availability unverified",severity="High for operational-fairness claims",evidence="No validated original per-file reception/publication timestamps",
             confidence="Verified gap in the inspected acquisition contract",risk="Future information or an older cycle selected unequally",remediation="Keep fixed-cycle retrospective label or verify release timing separately"),
        dict(finding="IFS database writer not implemented",severity="Medium",evidence="Live columns and offline payload are compatible; no INSERT performed",
             confidence="Live catalog plus offline row validation, not transaction testing",risk="GFS-only loader applied to incompatible manifests",remediation="Dedicated idempotent adapter with post-commit canonical-guide refresh")]
    write_csv(RESULTS/"source_quality_findings.csv",quality_findings)
    source_section="\n".join(f"- [{s['title']}]({s['url']}): {s['role']}." for s in links)
    report=f"""# ECMWF Open Data can support a 2025 benchmark, with explicit approximation and ingestion rules

## Executive summary

- **MARS authorization is not required for the public historical data tested here.** All **{len(anchors):,}** index checks succeeded: +24 and +168 hours for every daily 00 UTC run in 2024–2025. This establishes two anchor leads, not every file in the archive.
- **2025 is the cleanest candidate for the main comparison.** Native min/max fields are present at both anchors for all 365 runs. In 2024, they are present for only 50/366 runs at +24 hours and 301/366 at +168 hours; early-year data cannot silently use the same native-extrema pipeline.
- **The engineering pipeline now works end to end locally:** two complete lead sets, {consistency['decoded_rows']} decoded temperature fields, HKT daily reconstruction, and {meta['observed_paired_cases']} HKO forecast/observation joins. Existing external-model columns can hold the fields after an adapter; no database change or import was made.
- **Accepted approximation does not mean exact recovery.** The 2025 interval proxy gives 14 daily-endpoint cases, but {consistency['endpoint_violations_after_disclosed_padding']} native endpoint comparisons exceed the disclosed numerical allowance. Retain sensitivity ranges and source-quality flags; do not call these guaranteed bounds or confidence intervals.

This investigation was executed on **2026-11-08 HKT**. The intended task is data management and feasibility, not metric ownership or a definitive model ranking. The metric below is a proposal for the teammate. Run dates and target dates are distinguished throughout.

## 1. Access: use the public cloud archive, not the existing MARS pilot

The existing `download_ifs_pilot.py` requests the restricted historical MARS service. A valid key without archive entitlement cannot make that route work. The tested public routes are a different service:

- [AWS ECMWF bucket](https://registry.opendata.aws/ecmwf-forecasts/): anonymous HTTPS index and byte-range reads succeeded.
- Google Cloud mirror: the checked 2025 index has the **same SHA-256** as AWS; transition-date cross-checks are saved in `access_checks.json`.
- ECMWF's own rolling endpoint returned 404 for the old 2025 file tested here; this is not evidence that the cloud history is absent.
- Direct anonymous Azure access returned 409 in the probe. The official client supports public SAS-token handling, so this is not a claim that Azure requires a paid archive account.

The official [`ecmwf-opendata` client](https://github.com/ecmwf/ecmwf-opendata) is distinct from `ecmwf-api-client`. The investigation implements the documented public index-plus-byte-range protocol directly using already installed requests/ecCodes. Neither an ECMWF key nor an AWS account is used. All stored URLs are public and unsigned. Failed requests can retry/fall back, but are never converted into invented forecast values.

Current documentation adds **0.1° from 20 October 2026**, including split surface/pressure files. That is not a retrospective upgrade to the 2024–2025 inputs; the correctly named historical 0.1° surface-file probe returned 404. Always pin the historical product/resolution, rather than downloading today's default model and treating it as a historical forecast. [Current naming and release notes](https://confluence.ecmwf.int/spaces/DAC/pages/272310539/ECMWF+open+data+real-time+forecasts+from+IFS+and+AIFS)

## 2. Historical coverage is good, but the variable schema changes within 2024

{coverage_table}

![Two-anchor historical availability](historical_coverage.png)

The audit checks one operational deterministic initialization per date, `class=od`, `stream=oper`, `type=fc`, at **00 UTC**. Every selected index field must match that date/time/lead identity. A public operational-forecast record is not ERA5, an analysis field or a later hindcast. The audit does not assert every intermediate lead or every other cycle is complete.

The actual contiguous regimes, rather than dates inferred from announcements, are:

{regimes_table}

Consequential details:

- The selected public grid changes from 0.4° to 0.25° on **29 February 2024**. This is an output-grid change, not a claim that native model resolution equals 0.25°. [Historical announcement](https://www.ecmwf.int/en/about/media-centre/news/2024/ecmwf-releases-much-larger-open-dataset)
- +168-hour six-hour min/max become continuously present on **6 March 2024** in this audit. Shorter-lead three-hour fields do **not** become complete at the same time.
- +24-hour three-hour extrema appear once on **18 September 2024**, disappear again, then are continuously present from **13 November 2024**. The isolated occurrence's cause is not established. Google transition probes agree with the sampled AWS field lists. Do not assume the 12 November model-upgrade announcement means every 00 UTC output changed that day.
- For historical 2025-01-01, 12 UTC +168 hours is present; 06 UTC `scda` +144 is present but +168 returns 404. These individual probes demonstrate why today's stream/cycle rules must not be applied blindly to old files; they are not a full all-cycle audit.

**Implication:** a 2025 primary study is feasible with the accepted daily approximation. A full 2024–2025 study needs an explicit sampled/hybrid policy or additional archive fields. It must not backfill missing native extrema with zero, a mean temperature, reanalysis, or an unlabelled different proxy. Narrowing to 2025 is a recommendation, not an unrequested change to the team's final scope. A 2025 target-date study also needs late-December 2024 initialization buffers; those full lead sets are not downloaded here.

## 3. Real downloads, decoding and provenance—not only catalogue browsing

{pilots_table}

Each complete pilot contains 57 published lead times: +0 to +144 every 3 hours, then +150 to +192 every 6 hours. There is no +147-hour lead in this schedule. The 2025 run contains 57 instantaneous `2t` fields, 48 each of `mx2t3/mn2t3`, and 8 each of `mx2t6/mn2t6`. The January 2024 run contains only 57 `2t` fields.

The decoder checks GRIB2 message boundaries, parameter ID/name, forecast initialization and validity, height above ground, processing type, units, grid spacing and finite values. Temperatures are converted by **C = K − 273.15**. Download byte ranges must return an exact HTTP 206 range; a full HTTP 200 multivariable object is refused. Checksums, original units, native parameter names, intervals, coordinates and retrieval timestamps are retained.

**A real ingestion trap was detected and guarded against.** The 2025 lead-zero file contains two 224-byte min/max entries labelled +3 hours; their decoded temperature is **0 K**. They are excluded, recorded in `excluded_placeholder_fields.json`, and covered by an offline regression test. The genuine +3-hour min/max come from the correct +3-hour file. A naive concatenation could confuse the two. Similar behavior is reported in the [official client's issue tracker](https://github.com/ecmwf/ecmwf-opendata/issues/76); the local finding is supported by decoded bytes, not the issue report alone.

## 4. Daily HKT reconstruction: the approximation is usable, with honest limits

For target date D, use **D−1 16:00 UTC to D 16:00 UTC**, corresponding to 00:00–24:00 HKT. For one endpoint at a time:

- **Tmax:** the largest wholly contained interval maximum forms the lower side; the largest overlapping interval maximum forms the upper side.
- **Tmin:** the smallest overlapping interval minimum forms the lower side; the smallest wholly contained interval minimum forms the upper side.
- Add the existing pilot's numerical allowance to each relevant side: max(0.02°C, one inspected quantization step). The tested IFS packing step is 0.03125°C. This is a disclosed sensitivity allowance, not a certified error bound.
- Use the **midpoint of that endpoint's envelope** as an explicit deterministic proxy when a single value is required. Keep the endpoints, width, original samples and method label alongside it. This is not the midpoint between daily Tmin and Tmax.

**A +168-hour file alone does not cover HKT lead day 7.** For a 00 UTC run
(08:00 HKT), that target day ends at +184 hours; the first available six-hour
interval ending beyond it is +186 hours. The complete pilots therefore fetch
through +192 as a buffer. The historical +168 anchor is a variable-availability
check, not proof of complete daily coverage; production still needs all
contributing leads.

The midpoint minimizes the worst distance to the two envelope edges under absolute loss; it is **not** established as unbiased, calibrated or the most likely model extreme. That modest rationale does not turn the envelope into a probability distribution.

In the 2025 pilot, outer interval unions cover all 24 hours. Fully contained intervals cover 21 hours for D1–D5, but only **18 hours for D6–D7**, where output has become six-hourly. Durations are unions, not sums of overlapping/nested intervals. Extrema are never split by subtracting them or scaling temperature by the fraction of an interval inside the day. Current sensitivity widths are {width_min:.4f}–{width_max:.4f}°C for these 14 cases, not a general forecast-uncertainty estimate.

![Daily reconstruction sensitivity](daily_proxy_sensitivity.png)

### Native field consistency is an unresolved qualification, not hidden by the narrow ranges

Across {consistency['endpoint_comparisons']} interval-versus-instantaneous endpoint checks, {consistency['endpoint_raw_violations']} have a positive numerical discrepancy, and **{consistency['endpoint_violations_after_disclosed_padding']} remain beyond the two-field allowance**. The maximum raw discrepancy is **{consistency['max_raw_violation_c']:.4f}°C**. For example, instantaneous `2t` at +123 hours exceeds the corresponding `mx2t3` value at the same public grid point.

This weakens the premise that all fields describe one perfectly consistent, already-interpolated temperature path. Its cause is **not established** here: do not attribute it solely to packing, interpolation or a model bug. An [ECMWF forum user reports analogous behavior](https://forum.ecmwf.int/t/inconsistencies-between-t2m-and-mn2t3-mn2t6-mx2t3-mx2t6-fields-after-interpolation-to-station-points/14190), but that is not an official resolution. Accordingly, our envelopes remain **conditional sensitivity ranges**, not certified bounds on the model's true daily endpoint. The accepted approximation can still support a clearly labelled retrospective study; preserve these warnings and compare approximation sensitivity rather than silently increasing padding until a check passes.

{daily_table}

The 2024 pilot's sampled extrema remain separate; no missing interval extrema are invented. The complete daily-case export includes the selected HKO forecast, complete HQ observation, fixed cutoff, exact window and source fingerprints. **28 joined endpoint cases are not 28 independent forecast runs:** they come from only two model initializations, and only the 2025 run has full interval reconstruction.

## 5. Geography: a coastal point matters even when coordinates match across models

HKO Headquarters is at {db['station']['latitude']:.5f}°N, {db['station']['longitude']:.5f}°E, with documented ground elevation **{db['station']['elevation_m']} m**. The two tested grids select different nearest points, as shown above. The 2025 IFS coordinate matches the existing GFS pilot's 22.25°N, 114.25°E coordinate; matching coordinates does not prove matching model land mask or orography.

The nearest public-grid IFS land fraction is **{nearest_lsm['2024-01-01']:.4f} in 2024** and **{nearest_lsm['2025-01-01']:.4f} in 2025**. These decoded, coarsened public-grid mask values describe mixed coastal representation. They are not observed land coverage, and do not alone prove the binary classification of a native computational grid point. The 2025 surface geopotential gives a geopotential height of about **{float(height):.1f} m**, versus the HQ ground elevation of 32 m. No lapse-rate or bias correction is applied. Surface geopotential is absent from the inspected January 2024 surface file, so that comparison is left unavailable rather than borrowed from 2025.

![Coastal grid comparison](coastal_grid_comparison.png)

The four neighboring coordinates and temperatures are saved for a pre-specified spatial sensitivity check. Do not choose a different "best" grid point each day after observing its error. Any station calibration must be fit outside the evaluation targets and frozen. The benchmark compares a public HKO forecast product and raw IFS output at an HQ reference, not all of Hong Kong or the intrinsic ability of entire agencies. Geographic differences are a possible representativeness issue, not a demonstrated cause of this pilot's errors. [ECMWF coastal/orographic guidance](https://confluence.ecmwf.int/spaces/FUG/pages/673551774/Section+9.6.2+Coastal+island+mountain+and+ice+effects)

## 6. Database compatibility: an adapter is needed, not automatically new tables

The live `.env` database was inspected in a read-only repeatable-read transaction. Existing source tables contain **65 GFS source subsets** for the January 2024 pilot and no imported IFS model. Both HQ observation series contain all 731 requested dates, numeric and marked C. The canonical schema reference remains [DATABASE_AGENT_GUIDE.md](../../../DATABASE_AGENT_GUIDE.md); `database_check.json` is a bounded inspection receipt, not a second maintained schema document.

| Input difference | Required engineering |
| --- | --- |
| ECMWF JSON-lines `.index` versus NOAA textual `.idx` | Separate index parser and explicit requested-lead filtering; implemented for this investigation |
| Native `mx2t3/mn2t3/mx2t6/mn2t6` versus GFS labels | Preserve native short names/IDs in storage; use analysis aliases only for shared reconstruction |
| Different valid-time spacing and encoded intervals | Decode GRIB `startStep/endStep/stepType`; never infer all intervals from requested spacing |
| Kelvin versus HKO Celsius | Retain source unit/value and store converted Celsius; implemented |
| 0.4°/0.25° and coastal-grid differences | Save grid spacing, extraction method, coordinates, distance, mask/orography diagnostics |
| Public archive bytes versus existing GFS manifests | Add an IFS manifest/import adapter; do not feed these files to `manage_gfs.py import` |
| Source fingerprints versus PostgreSQL UUID keys | Deterministic UUID mapping, source/temperature FK linkage and explicit archive-root convention |
| Daily approximation versus original subdaily source | Keep original fields; create derived cases separately only after the team's specification |

The **existing two external-model tables can represent this deterministic temperature subset without new columns**, according to the inspected columns/constraints and the offline payload check. `import_payload_preview.json` contains {consistency['decoded_rows']} source/extract pairs with native names and valid UUIDs; these are **not inserted**. Its source grain is one downloaded single-field subset, so source count need not equal lead count. The preview's explicit `archive_root=repository_root` must be respected by any future adapter; old GFS readers assume their own downloads root.

Still needed before production import: a dedicated transactional/idempotent IFS writer, reviewed manifest/path policy, restart/failure tests, and the mandatory post-commit live refresh of `DATABASE_AGENT_GUIDE.md`. There is no write option in this investigation. Adding ensemble members, additional stations or other variables would need another grain/contract review; compatibility here does not prove those wider uses.

## 7. Timing, storage, licensing and optional variables

**Timing.** Initialization, field validity, public release, object last-modified and our later retrieval are different timestamps. The example AWS and Google index timestamps differ even for identical bytes. They are useful evidence to retain, not verified original per-file availability. This pilot keeps the existing fixed **00 UTC run / 20:00 HKT cutoff scenario**, selecting HKO only when both bulletin and RSS timestamps precede the cutoff. It does not claim that this is the latest available model run. Scheduled dissemination is not proof every required historical file arrived on time. [Historical schedule](https://confluence.ecmwf.int/pages/viewpage.action?pageId=600793086)

**Storage.** The complete 2025 pilot's selected global temperature messages occupy **{meta['pilots'][1]['field_bytes']/1e6:.2f} MB**. Multiplying that one January sample gives approximately **{projection:.2f} GB** for one run/day for 365 days, or **{projection*2:.2f} GB** for two full-horizon runs/day. These are planning extrapolations, excluding initialization buffers, indexes, manifests, backups and compression/seasonal variation. The January 2024 pilot is smaller because its parameter set is incomplete, not because two years of equivalent variables are necessarily cheap. Byte ranges select global variable messages, not a Hong Kong spatial crop. Saving only station extracts greatly reduces downstream storage; retention/deletion of original global messages should be an explicit policy, not an automatic destructive step.

**Licence.** The public catalogue uses CC BY 4.0 with ECMWF terms. Retain attribution, product/version, source URLs, retrieval dates and checksums in the handoff. Free public downloading and authorized MARS archive services are distinct; open licensing alone does not establish every service is free. [ECMWF licence and access terms](https://www.ecmwf.int/en/forecasts/datasets/open-data)

**Other variables, not part of this temperature pilot.** Native `tp` is accumulated precipitation and needs correct interval de-accumulation and unit handling; it is not automatically HKO PSR. Pressure-level `r` is not near-surface RH. `2t` with `2d` can support sampled near-surface RH where both exist, but not automatically daily RH extrema. The January 2024 sample lacks `2d`; optional-variable feasibility also changes over time. AIFS and ensembles must remain separately labelled products; ERA5 must not substitute for an original forecast.

## 8. Candidate metric for the teammate: paired difference in MAE

This is a **proposal**, not a change to the team's final evaluation design. At one fixed lead, variable and reference station, and on the same eligible dates, define:

    d_i = abs(IFS_proxy_i − observed_i) − abs(HKO_i − observed_i)
    paired ΔMAE = mean(d_i)

Negative means the IFS proxy has smaller absolute error; positive means HKO has smaller absolute error. Keep Tmax and Tmin separate. Use only common matched cases, but also report each product's coverage and exclusion reasons so a common-case restriction does not hide missing difficult weather.

### Worked example: invented data, not this pilot's forecast skill

{example_table}

All temperatures/errors are in °C. HKO MAE = (2+1+2)/3 = **1.667°C**; IFS MAE = (1+1+1)/3 = **1.000°C**; paired difference = (−1+0−1)/3 = **−0.667°C**. This supports the statement "IFS was closer by an average 0.667°C in these three invented matched cases," not "IFS is generally better."

![Synthetic paired-error illustration](metric_example.png)

**Why this works:** each difference faces the same observed weather, units remain interpretable, and absolute errors do not cancel as signed bias does. Pairing prevents one product being scored on a different mix of dates; the paired mean equals the difference in MAEs only when membership/weights match. Compared with RMSE it is less dominated by a single large error. These benefits do not repair spatial, timing or reconstruction differences by themselves.

**Respect the approximation.** If one endpoint's reconstruction envelope is [26,28]°C and the observation is 30°C, its midpoint proxy has absolute error 3°C. Under the envelope assumption its possible error spans 2–4°C. If HKO predicts 29°C (error 1°C), the paired difference is +2°C, with a conditional sensitivity range of +1 to +3°C. That sign is robust to the stated envelope, but the envelope is not certified here and is not a statistical confidence interval. If an observation lies inside a wide reconstruction range, do not automatically award error zero: that would reward ambiguity rather than accurate point prediction.

Use mean signed error as a directional diagnostic and RMSE as a large-error diagnostic if the teammate needs them. Do not use temperature-Celsius MAPE as the default, and do not apply probabilistic prediction-interval scores to these non-probabilistic reconstruction ranges. Statistical uncertainty, seasonal splits and time-block resampling remain with the teammate; the two fixed pilots cannot establish a general ranking or independent lead-time effects.

## 9. Valuable research findings and the next engineering boundary

1. **IFS is no longer categorically blocked by MARS access.** The public cloud route supplies the tested operational history anonymously.
2. **A release announcement is not a coverage guarantee.** The two extrema families have different first/stable dates, including an isolated 2024 short-lead occurrence. Sampling only one date could miss this.
3. **The daily approximation becomes structurally coarser at long lead.** D6–D7 have 18 rather than 21 hours of wholly contained interval coverage in the 2025 run; approximation sensitivity belongs in the handoff.
4. **A small envelope is not proof of accurate reconstruction.** Native endpoint inconsistencies survive the stated numerical allowance. Keep flags and seek clarification rather than silently treating precision as certainty.
5. **Coastal representativeness is measurable.** The nearest-point distance changes from 20.97 to 9.71 km and the public-grid land fraction changes materially; no causal attribution or post-hoc correction is justified from these checks alone.
6. **Schema mismatch is manageable.** The database's generic source/temperature columns are sufficient for this subset; parser, naming, interval, provenance and import contracts are the remaining work.

Recommended next engineering step: use the working 2025 path to implement the IFS import adapter and a resumable all-required-leads acquisition plan, after the team fixes target dates, cycles/cutoff and proxy policy. Include late-2024 initialization buffers. Preserve raw fields and approximation flags. If the team insists on a uniform native-extrema 2024–2025 study, ask ECMWF specifically about the missing historical three-hour fields rather than requesting unrestricted data without a narrow need. MARS access alone would still not guarantee exact HKT daily windows.

**Not done:** a full-period raw GRIB download/import, an adopted metric protocol, verified latest-available operational selection, causal explanation of source inconsistencies, or a definitive HKO/GFS/IFS ranking. These are not required to finish this initial investigation. No contact was sent to ECMWF and no paid access was purchased.

## Verification and reproducibility

The offline verifier passed **{verification['checks']} scoped checks**: cached-byte hashes, nearest-one re-extraction versus saved nearest-four extraction, independent hourly-cell coverage/range/error arithmetic, and offline target-column compatibility. This does not certify the known native-field inconsistency, historical availability or forecast skill. The main acquisition receipt is `run_metadata.json`; source-quality discrepancies are in `native_crossfield_warnings.csv`.

The compact [source-quality register](source_quality_findings.csv) records each
material issue's severity, directness of evidence, downstream risk and remediation.

Scripts, commands and boundaries are in [the investigation README](../README.md). The report and static figures are rebuilt from the saved local evidence. Native GRIB/index cache files are ignored by Git but retained locally. Exact queries live in `run_investigation.py`; credentials do not appear in any result. **Database writes: none.** The canonical guide and committed schema were not changed by this investigation.

## Sources

Public archive indexes and GRIB messages are the controlling evidence for measured coverage/values. The CSV/JSON receipts retain their exact URLs and hashes. Documentation below supplies definitions and context; current documentation does not override historical file contents.

{source_section}
"""
    (RESULTS/"findings.md").write_text(report,encoding="utf-8")
    print("Built findings.md and four static research figures from saved evidence.")


if __name__=="__main__": run()

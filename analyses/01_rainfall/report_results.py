"""Write a concise answer to both course questions from fresh aggregate CSVs."""

import csv
from collections import defaultdict
from pathlib import Path


RESULTS = Path(__file__).resolve().parent / "results"
BANDS = {"Low": (0, 30), "Medium Low": (30, 45), "Medium": (45, 55),
         "Medium High": (55, 70), "High": (70, 101)}
CATEGORIES = ("Low", "Medium Low", "Medium", "Medium High", "High")


def read(name):
    with (RESULTS / name).open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def count_positive_by_stratum(rows, stratum, metric):
    grouped = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    for row in rows:
        if row["metric"] != metric:
            continue
        cell = grouped[row[stratum]][row["rain_group"]]
        n = int(row["n_forecasts"])
        cell[0] += n
        cell[1] += n * float(row["mae_c"])
    differences = {}
    for key, groups in grouped.items():
        wet = groups.get("at_least_10_mm")
        other = groups.get("under_10_mm")
        if wet and other:
            differences[key] = wet[1] / wet[0] - other[1] / other[0]
    return sum(value > 0 for value in differences.values()), len(differences)


def range_assessment(row):
    low, high = BANDS[row["psr_category"]]
    rate = float(row["observed_rate_pct"])
    ci_low = float(row["cluster_ci_low_pct"])
    ci_high = float(row["cluster_ci_high_pct"])
    if ci_low >= high:
        return "proxy frequency above forecast range; CI entirely above"
    if ci_high < low:
        return "proxy frequency below forecast range; CI entirely below"
    if not low <= rate < high:
        return "point estimate outside forecast range; CI overlaps it"
    return "point estimate within forecast range"


def main():
    coverage = read("temperature_rain_coverage.csv")[0]
    overall = read("temperature_error_by_rain_overall.csv")
    differences = read("temperature_mae_difference_overall.csv")
    by_lead = read("temperature_mae_difference_by_lead.csv")
    by_year = read("temperature_error_by_rain_and_year.csv")
    by_month = read("temperature_error_by_rain_and_month.csv")
    area_coverage = read("psr_area_target_coverage.csv")[0]
    area = read("psr_area_calibration.csv")
    area_by_lead = read("psr_area_calibration_by_lead_group.csv")
    proxy = {row["psr_category"]: row for row in read("psr_calibration.csv")}
    weights = read("psr_area_weights.csv")
    if coverage["start_inclusive"] != "2022-01-01" or coverage["end_exclusive"] != "2026-01-01":
        raise ValueError("Expected the complete 2022–2025 temperature period")
    if int(area_coverage["panel_stations"]) != 22 or len(weights) != 22:
        raise ValueError("Expected 22 area-weighted rainfall stations")
    if abs(sum(float(row["weight"]) for row in weights) - 1) > 0.001:
        raise ValueError("Area weights do not sum to one")
    if not all(row["psr_category"] in proxy for row in area):
        raise ValueError("The area and unweighted PSR categories differ")
    if not area_by_lead:
        raise ValueError("The area-weighted PSR lead-group results are missing")

    lines = [
        "# Rainfall and HKO forecast verification, 2022–2025", "",
        "## 1. Temperature forecast accuracy and observed rainfall", "",
        f"Complete HKO Headquarters Tmax, Tmin, and rainfall values were available "
        f"on {coverage['usable_all_three_days']} of {coverage['calendar_days']} calendar days. "
        "Rainfall groups use the station's realized daily total: at least 10 mm "
        "versus under 10 mm. One latest bulletin per issue day and valid date "
        "contributes each full-day lead from 1 to 9.", "",
    ]
    for metric in ("Tmax", "Tmin"):
        groups = {row["rain_group"]: row for row in overall if row["metric"] == metric}
        diff = next(row for row in differences if row["metric"] == metric)
        wet = groups["at_least_10_mm"]
        other = groups["under_10_mm"]
        estimate = float(diff["mae_difference_c"])
        ci_low = float(diff["cluster_ci_low_c"])
        ci_high = float(diff["cluster_ci_high_c"])
        direction = "higher" if estimate > 0 else "lower" if estimate < 0 else "the same"
        supported = (ci_low > 0) or (ci_high < 0)
        leads = [row for row in by_lead if row["metric"] == metric]
        higher = sum(float(row["mae_difference_c"]) > 0 for row in leads)
        years_higher, years_n = count_positive_by_stratum(by_year, "valid_year", metric)
        months_higher, months_n = count_positive_by_stratum(by_month, "valid_month", metric)
        lines += [
            f"**{metric}:** MAE was {wet['mae_c']}°C on ≥10 mm days "
            f"({wet['n_forecasts']} forecasts) and {other['mae_c']}°C on <10 mm "
            f"days ({other['n_forecasts']} forecasts). The rainy-day MAE was "
            f"{direction} by {abs(estimate):.3f}°C (rainy minus other: "
            f"{estimate:+.3f}°C; 95% valid-date cluster bootstrap interval "
            f"{ci_low:+.3f} to {ci_high:+.3f}°C). "
            + ("The interval excludes zero." if supported else
               "The interval includes zero, so the direction is uncertain."),
            f"Higher rainy-day MAE appeared in {higher}/{len(leads)} lead-day "
            f"comparisons, {years_higher}/{years_n} years, and "
            f"{months_higher}/{months_n} calendar months.", "",
        ]

    lines += [
        "This is a retrospective association. Rainfall was observed after the "
        "forecast was issued, and season or other weather conditions can affect "
        "both rainfall and forecast error. It does not establish that rain caused "
        "the error difference.", "",
        "## 2. Probability of Significant Rain calibration", "",
        "The [HKO PSR labels](https://www.hko.gov.hk/en/wxinfo/currwx/fnd.htm) "
        "are **issued probability forecasts**, not an independent reference "
        "standard. HKO says that, among 100 forecasts labelled Medium Low, "
        "significant rain should occur about 30–44 times. The comparison "
        "below asks whether rainfall happened that often when HKO issued each "
        "label. It does not compare observations with an arbitrary target.", "",
        f"The observed event is a 22-station Voronoi land-area weighted daily "
        f"rainfall estimate of at least 10 mm. The land mask is "
        f"{area_coverage['land_area_km2']} km². "
        f"{area_coverage['complete_target_days']} days had complete observations "
        f"at all fixed stations; {area_coverage['trace_ambiguous_days']} days "
        "were excluded because Trace could change the event label. "
        "The same latest-bulletin rule and leads 1–9 apply.", "",
        "| Issued PSR label | HKO forecast probability | Observed proxy frequency | "
        "95% date-cluster interval | Forecasts | Unweighted proxy | Assessment under proxy |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in area:
        category = row["psr_category"]
        lines.append(
            f"| {category} | {row['hko_probability_band']} | "
            f"{row['observed_rate_pct']}% | "
            f"{row['cluster_ci_low_pct']}–{row['cluster_ci_high_pct']}% | "
            f"{row['n_forecasts']} | {proxy[category]['observed_rate_pct']}% | "
            f"{range_assessment(row)} |"
        )
    outside = sum(not BANDS[row["psr_category"]][0] <=
                  float(row["observed_rate_pct"]) <
                  BANDS[row["psr_category"]][1] for row in area)
    clear = sum(float(row["cluster_ci_high_pct"]) < BANDS[row["psr_category"]][0]
                or float(row["cluster_ci_low_pct"]) >= BANDS[row["psr_category"]][1]
                for row in area)
    n_cases = sum(int(row["n_forecasts"]) for row in area)
    n_events = sum(int(row["n_significant_rain_forecasts"]) for row in area)
    rates = {row["psr_category"]: float(row["observed_rate_pct"]) for row in area}
    medium_low = next(row for row in area if row["psr_category"] == "Medium Low")
    ordered_rates = [rates[category] for category in CATEGORIES if category in rates]
    monotonic = all(first <= second for first, second in zip(ordered_rates, ordered_rates[1:]))
    lines += [
        "", f"**What the comparison shows:** Across {n_cases:,} forecast cases, "
        f"the proxy event occurred {n_events:,} times "
        f"({100 * n_events / n_cases:.1f}%). The frequency rises from "
        f"{rates['Low']:.1f}% for Low to {rates['High']:.1f}% for High. "
        f"{outside} of {len(area)} category point estimates fall outside "
        f"their forecast probability ranges; for {clear}, the entire 95% "
        "interval is outside. "
        + ("Observed rates rise with each higher PSR category." if monotonic else
           "Observed rates do not rise consistently with PSR category."), "",
        "The **Medium Low** forecast range is 30–44%, but the proxy event "
        f"occurred in {medium_low['observed_rate_pct']}% of its forecast cases "
        f"(95% interval {medium_low['cluster_ci_low_pct']}–"
        f"{medium_low['cluster_ci_high_pct']}%). "
        "That is evidence of a lower event frequency than the category "
        "forecasts *for this proxy and selected sample*. Low (<30%) and High "
        "(≥70%) are open-ended ranges; a rate inside either range alone "
        "cannot demonstrate forecast skill or precise calibration.", "",
        "### By forecast lead", "",
        "| PSR | Lead days | Event rate | 95% date-cluster interval | Forecasts |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in area_by_lead:
        lines.append(
            f"| {row['psr_category']} | {row['lead_group']} | "
            f"{row['observed_rate_pct']}% | "
            f"{row['cluster_ci_low_pct']}–{row['cluster_ci_high_pct']}% | "
            f"{row['n_forecasts']} |"
        )
    lines += [
        "",
        "These rates compare the issued forecast categories with a declared "
        "station-based estimate of rainfall generally over Hong Kong. HKO "
        "does not prescribe this exact 22-station land-area target; therefore "
        "the result is conditional on our proxy and complete-day sample, and "
        "does not establish the Observatory's official calibration. The "
        "unweighted rates provide one target sensitivity check. Lead-group "
        "rates differ, so do not generalize a pooled rate to every forecast "
        "horizon.", "",
        "![Temperature MAE by lead](temperature_error_by_rain.png)", "",
        "![Area-weighted PSR calibration](psr_area_calibration.png)", "",
        "## References and data provenance", "",
        "The numerical results above were calculated from the read-only "
        "`course_project.project` database and the aggregate CSVs listed below. "
        "The external references define the forecasts, observation markers, "
        "geographic source data, and geometry method. They do not supply or "
        "independently verify the event rates in this report.", "",
        "### Forecast and observation definitions", "",
        "1. [Hong Kong Observatory, 9-day Weather Forecast, Note 3]"
        "(https://www.hko.gov.hk/en/wxinfo/currwx/fnd.htm) — the PSR forecast "
        "event (daily rainfall of at least 10 mm generally over Hong Kong), "
        "five probability ranges, and the ‘per 100 forecasts’ interpretation.",
        "2. [Hong Kong Observatory, Q & A for Probability of Significant Rain]"
        "(https://www.hko.gov.hk/en/education/weather/rain/00568-Q-%26-A-for-Probability-of-Significant-Rain.html) "
        "— why PSR is a probability forecast and how the 10 mm threshold is defined.",
        "3. [Hong Kong Observatory, Open Data API Documentation]"
        "(https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf) "
        "— HKO daily maximum/minimum temperature data types and station-code "
        "definitions. The archived bulletin vintages used here "
        "come from the project database, not a current API response.",
        "4. [Hong Kong Observatory, Daily Total Rainfall Data Dictionary]"
        "(https://data.weather.gov.hk/weatherAPI/doc/data_dictionary_daily_total_rainfall.pdf) "
        "— `C` means complete data and `***` means unavailable.",
        "5. [Hong Kong Observatory, The Year's Weather 2025]"
        "(https://www.weather.gov.hk/en/wxinfo/pastwx/2025/ywx2025.htm) "
        "and [HKO daily rainfall display]"
        "(https://www.hko.gov.hk/en/cis/dailyElement.htm?ele=RF&y=2022) "
        "— explain the `Trace` rainfall notation (less than 0.05 mm).",
        "6. [COMP3522 database schema guide](../../../DATABASE_AGENT_GUIDE.md) "
        "— local record of the imported `project` tables, their grains, "
        "series codes, forecast vintages, station metadata, and provenance.", "",
        "### Geographic sources and computation", "",
        "7. [Home Affairs Department district-boundary dataset]"
        "(https://data.gov.hk/en-data/dataset/hk-had-json1-hong-kong-administrative-boundaries) "
        "and [JSON used by the script]"
        "(https://www.had.gov.hk/psi/hong-kong-administrative-boundaries/hksar_18_district_boundary.json) "
        "— the 18 district polygons; the raw district union includes sea.",
        "8. [Lands Department topographic dataset metadata]"
        "(https://portal.csdi.gov.hk/csdi-webpage/metadata/landsd_rcd_1637221775627_85634/html) "
        "and [CSDI HYDRPOLY feature layer]"
        "(https://portal.csdi.gov.hk/server/rest/services/common/landsd_rcd_1637221775627_85634/FeatureServer/7) "
        "— source of `CLASS='EWB'` and `TYPE='SEF'` sea-fill polygons "
        "subtracted from the district union.",
        "9. [Lands Department, Hong Kong Geographic Data 2026]"
        "(https://www.landsd.gov.hk/en/resources/mapping-information/hk-geographic-data.html) "
        "and [Area of the HKSAR table]"
        "(https://www.landsd.gov.hk/doc/en/mapping/ehkg/individual_PDF/AreaOfHKSAR_eHKG2026.pdf) "
        "— the published 1,114.57 km² land area used as a plausibility check "
        "on the constructed 1,115.65 km² land mask.",
        "10. [Shapely `voronoi_polygons` documentation]"
        "(https://shapely.readthedocs.io/en/latest/reference/shapely.voronoi_polygons.html) "
        "— ordered Voronoi cells for the 22 fixed station points.",
        "11. [pyproj `Transformer` documentation]"
        "(https://pyproj4.github.io/pyproj/stable/api/transformer.html) "
        "— longitude/latitude to metric Hong Kong projection conversion "
        "before area calculation.", "",
        "### Reproducible local outputs", "",
        "- Temperature: [overall differences](temperature_mae_difference_overall.csv), "
        "[group MAE and bias](temperature_error_by_rain_overall.csv), and "
        "[analysis code](../analyze_temperature_rain.py).",
        "- PSR: [area-weighted category counts and rates](psr_area_calibration.csv), "
        "[lead-group rates](psr_area_calibration_by_lead_group.csv), "
        "[station area weights](psr_area_weights.csv), "
        "[unweighted sensitivity result](psr_calibration.csv), and "
        "[analysis code](../analyze_psr_area.py).", "",
    ]
    output = RESULTS / "research_conclusions.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

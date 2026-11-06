"""Summarize the read-only matched_cases.sql result and reconcile it to RQ4."""
import argparse
from collections import defaultdict
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


START, END = date(2022, 1, 1), date(2026, 1, 1)
METRICS = {"tmax": ("Tmax", "°C"), "rh_min": ("RH minimum", "pp"), "rh_max": ("RH maximum", "pp")}
LEADS = tuple(range(1, 10))
SEASONS = ("DJF", "MAM", "JJA", "SON")
N_BOOTSTRAP, SEED = 4000, 3522
HERE = Path(__file__).resolve().parent


def season(day):
    return SEASONS[(day.month % 12) // 3]


def periods(day):
    year = str(day.year)
    part = season(day)
    return ("year", year), ("season", part), ("year_season", f"{year}-{part}")


def bootstrap(losses, days):
    # Every forecast for a valid date moves together in its Monday-based HKT week.
    weeks = defaultdict(list)
    for i, day in enumerate(days):
        weeks[day - timedelta(days=day.weekday())].append(i)
    totals = np.array([np.nansum(losses[idx], axis=0) for idx in weeks.values()])
    counts = np.array([np.isfinite(losses[idx]).sum(axis=0) for idx in weeks.values()])
    rng = np.random.default_rng(SEED)
    replicates = []
    for start in range(0, N_BOOTSTRAP, 200):
        draws = rng.integers(len(weeks), size=(min(200, N_BOOTSTRAP - start), len(weeks)))
        sums = totals[draws].sum(axis=1)
        ns = counts[draws].sum(axis=1)
        replicates.extend(np.divide(sums, ns, out=np.full_like(sums, np.nan), where=ns > 0))
    return np.asarray(replicates), len(weeks)


def interval(replicates):
    return dict(zip(("mae_ci95_low", "mae_ci95_high"), np.nanquantile(replicates, [.025, .975])))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: f"{v:.8f}" if isinstance(v, (float, np.floating)) else v
                             for k, v in row.items()})


def reconcile(cases, rq4_dir):
    expected = {}
    for name in ("temperature_accuracy_by_lead.csv", "rh_accuracy_by_lead.csv"):
        with (rq4_dir / name).open(newline="", encoding="utf-8-sig") as inp:
            for row in csv.DictReader(inp):
                if row["selection"] == "daily_latest" and row["metric"] in METRICS:
                    key = row["metric"], int(row["lead_days"])
                    expected[key] = int(row["n"]), float(row["mae"])
    if set(expected) != {(metric, lead) for metric in METRICS for lead in LEADS}:
        raise ValueError("Published RQ4 reference does not contain the 27 expected rows")
    for (metric, lead), (n, mae) in expected.items():
        values = [loss for (_, k), loss in cases[metric].items() if k == lead]
        if len(values) != n or not np.isclose(np.mean(values), mae, rtol=0, atol=1e-10):
            raise ValueError(f"Published RQ4 mismatch for {metric}, lead {lead}")
    return len(expected)


def chart(summary):
    fig, axes = plt.subplots(3, 2, figsize=(9.8, 8.2), layout="constrained")
    colors = ("#25587c", "#704572", "#287264")
    for (metric, (label, unit)), row, color in zip(METRICS.items(), axes, colors):
        for ax, period_type, order in zip(row, ("year", "season"),
                                          (["2022", "2023", "2024", "2025"], SEASONS)):
            by_period = {r["period"]: r for r in summary
                         if r["metric"] == metric and r["period_type"] == period_type}
            data = [by_period[p] for p in order]
            x = np.arange(len(data))
            mae = np.array([r["mae_equal_lead"] for r in data])
            bounds = [mae - [r["mae_ci95_low"] for r in data],
                      [r["mae_ci95_high"] for r in data] - mae]
            ax.errorbar(x, mae, yerr=bounds, fmt="o", color=color, capsize=4)
            ax.set_xticks(x, order)
            ax.set_ylim(bottom=0)
            ax.set_ylabel(f"{label} MAE ({unit})")
            ax.grid(axis="y", alpha=.25)
            ax.spines[["top", "right"]].set_visible(False)
        ceiling = max(ax.get_ylim()[1] for ax in row)
        for ax in row:
            ax.set_ylim(0, ceiling)
    axes[0, 0].set_title("By HKT target year", loc="left")
    axes[0, 1].set_title("By HKT target season", loc="left")
    fig.suptitle("HKO 9-day forecast MAE against Headquarters observations\n"
                 "Equal weight for leads 1–9; bars are 95% week-block intervals", fontsize=13)
    fig.savefig(HERE / "annual_seasonal_mae.png", dpi=155)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bridge_json", type=Path, help="Local result of the bridge query")
    parser.add_argument("--rq4-results", type=Path,
                        default=HERE.parents[2] / "05_rq4_accuracy_by_lead" / "results")
    args = parser.parse_args()
    result = json.loads(args.bridge_json.read_text(encoding="utf-8-sig"))["result"]
    rows = result["rows"]
    if result["truncated"] or len(rows) != 12 or len({(r["metric"], r["year"]) for r in rows}) != 12:
        raise ValueError("Missing, duplicate or truncated metric-year inputs")
    checks = rows[0]["checks"]
    for key in ("duplicate_rh_dates", "duplicate_actual_keys", "conflicting_captures",
                "bad_lead_dates", "missing_publication_timestamps",
                "publication_at_or_after_valid_start"):
        if checks[key] != 0:
            raise ValueError(f"Source check failed: {key}")
    dates = [START + timedelta(days=i) for i in range((END - START).days)]
    for key in ("tmax_dates", "rh_report_dates", "valid_rh_dates"):
        if checks[key] != len(dates):
            raise ValueError(f"Incomplete observations: {key}")
    cases = defaultdict(dict)
    for row in rows:
        for date_str, lead, loss in row["losses"]:
            day = date.fromisoformat(date_str)
            loss = float(loss)
            if not (START <= day < END and day.year == row["year"] and lead in LEADS
                    and np.isfinite(loss) and loss >= 0):
                raise ValueError(f"Invalid case: {row['metric']}, {day}, lead {lead}")
            key = day, lead
            if key in cases[row["metric"]]:
                raise ValueError(f"Duplicate case: {row['metric']}, {day}, lead {lead}")
            cases[row["metric"]][key] = loss

    reference_checks = reconcile(cases, args.rq4_results)
    groups = defaultdict(list)
    for day in dates:
        for period in periods(day):
            groups[period].append(day)
    summary, by_lead = [], []
    def period_order(item):
        kind, period = item
        if kind == "year":
            return 0, period, 0
        if kind == "season":
            return 1, "", SEASONS.index(period)
        year, part = period.split("-")
        return 2, year, SEASONS.index(part)

    for kind, period in sorted(groups, key=period_order):
        days = groups[kind, period]
        for metric, (_, unit) in METRICS.items():
            losses = np.array([[cases[metric].get((d, lead), np.nan) for lead in LEADS] for d in days])
            have = np.isfinite(losses)
            count = have.sum(axis=0)
            if not np.all(count):
                raise ValueError(f"Missing lead for {metric}, {period}")
            means = np.nanmean(losses, axis=0)
            reps, n_weeks = bootstrap(losses, days)
            complete = have.all(axis=1)
            ident = dict(period_type=kind, period=period, metric=metric, unit=unit)
            summary.append(dict(**ident, mae_equal_lead=means.mean(), **interval(reps.mean(axis=1)),
                                mae_pooled_cases=np.nanmean(losses),
                                mae_complete_days=losses[complete].mean(),
                                n_cases=int(count.sum()), n_possible_cases=len(days) * len(LEADS),
                                n_valid_days=int(have.any(axis=1).sum()), n_complete_days=int(complete.sum()),
                                n_calendar_days=len(days), n_week_blocks=n_weeks))
            for i, lead in enumerate(LEADS):
                by_lead.append(dict(**ident, lead_days=lead, mae=means[i], **interval(reps[:, i]),
                                    n_cases=int(count[i]), n_calendar_days=len(days)))

    write_csv(HERE / "mae_summary.csv", summary)
    write_csv(HERE / "mae_by_lead.csv", by_lead)
    chart(summary)
    missing = {metric: [[d.isoformat(), lead] for d in dates for lead in LEADS
                        if (d, lead) not in cases[metric]] for metric in METRICS}
    audit = dict(period_start=str(START), period_end_exclusive=str(END), source_checks=checks,
                 n_rq4_rows_reconciled=reference_checks, rq4_mae_absolute_tolerance=1e-10,
                 input_losses_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True,
                                                               separators=(",", ":")).encode()).hexdigest(),
                 missing_valid_date_lead_keys=missing,
                 bootstrap_replicates=N_BOOTSTRAP, bootstrap_seed=SEED)
    (HERE / "verification.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

"""Plot fresh PSR calibration with date-clustered uncertainty and HKO bands."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


RESULTS = Path(__file__).resolve().parent / "results"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--area", action="store_true",
                    help="plot the Hong Kong land-area weighted result")
args = parser.parse_args()
stem = "psr_area_calibration" if args.area else "psr_calibration"
with (RESULTS / f"{stem}.csv").open(newline="", encoding="utf-8") as file:
    rows = list(csv.DictReader(file))
if not rows:
    raise ValueError("Run the corresponding PSR analysis before plotting")

bands = {"Low": (0, 30), "Medium Low": (30, 44), "Medium": (45, 54),
         "Medium High": (55, 69), "High": (70, 100)}
fig, ax = plt.subplots(figsize=(9, 4.8), layout="constrained")
fig.patch.set_facecolor("white")
for y, row in enumerate(rows):
    low, high = bands[row["psr_category"]]
    rate = float(row["observed_rate_pct"])
    ci_low = float(row["cluster_ci_low_pct"])
    ci_high = float(row["cluster_ci_high_pct"])
    ax.barh(y, high - low, left=low, height=0.42, color="#e1e7ed", zorder=1)
    ax.errorbar(rate, y, xerr=[[rate - ci_low], [ci_high - rate]],
                color="#1764a0", fmt="o", capsize=3, markersize=7, zorder=3)
    label_x = ci_high + 1.5 if ci_high < 88 else ci_low - 1.5
    ax.text(label_x, y, f"{rate:.1f}%  (n={row['n_forecasts']})",
            ha="left" if ci_high < 88 else "right", va="center", fontsize=9)
ax.set_yticks(range(len(rows)), [row["psr_category"] for row in rows])
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.set_xticks(range(0, 101, 20))
ax.set_xlabel("Observed frequency of ≥10 mm day (%)")
target = "land-area weighted rainfall" if args.area else "fixed-station rainfall proxy"
ax.set_title(f"Issued PSR forecasts vs {target}", loc="left", fontsize=13)
ax.grid(axis="x", color="#edf0f2")
ax.set_axisbelow(True)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.text(0, -0.23, "Dot: observed proxy rate   Whisker: 95% date-cluster interval   Grey bar: forecast probability range",
        transform=ax.transAxes, fontsize=8.5, color="#485460")
method = ("2022–2025; 22-station Voronoi land-area weights; one bulletin per issue day and valid date."
          if args.area else
          "2022–2025; 22-station complete-day mean; one bulletin per issue day and valid date.")
ax.text(0, -0.35, method,
        transform=ax.transAxes, fontsize=8.5, color="#485460")
fig.savefig(RESULTS / f"{stem}.png", dpi=180,
            bbox_inches="tight", facecolor="white")

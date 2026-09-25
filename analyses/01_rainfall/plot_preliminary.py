"""Plot the preliminary PSR calibration percentages supplied in the project note."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


RESULTS = Path(__file__).resolve().parent / "results"
with (RESULTS / "psr_calibration_preliminary.csv").open(newline="", encoding="utf-8") as source:
    rows = list(csv.DictReader(source))

assert len(rows) == 5 and [row["psr_category"] for row in rows] == [
    "Low", "Medium Low", "Medium", "Medium High", "High"
]

# These are HKO's published category bands; the open-ended bands are drawn to
# the 0% and 100% plot boundaries.
bands = [(0, 30), (30, 44), (45, 54), (55, 69), (70, 100)]
rates = [float(row["observed_significant_rain_rate_pct"]) for row in rows]
labels = [row["psr_category"] for row in rows]

fig, ax = plt.subplots(figsize=(9, 4.7), layout="constrained")
fig.patch.set_facecolor("white")
ax.set_facecolor("white")
for y, (low, high) in enumerate(bands):
    ax.barh(y, high - low, left=low, height=0.42, color="#e1e7ed", zorder=1)
    ax.scatter(rates[y], y, s=85, color="#1764a0", edgecolors="white", linewidths=1, zorder=3)
    ax.annotate(f"{rates[y]:.1f}%", (rates[y], y), xytext=(9, 0),
                textcoords="offset points", va="center", color="#1764a0", fontsize=10)
ax.set_yticks(range(len(labels)), labels)
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.set_xticks(range(0, 101, 20))
ax.set_xlabel("Observed frequency of rainfall ≥10 mm (%)")
ax.set_title("Preliminary PSR calibration, 2022–2025", loc="left", fontsize=14, pad=14)
ax.grid(axis="x", color="#edf0f2")
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.text(0, -0.23, "Blue dot: observed rate     Grey bar: HKO probability band",
        transform=ax.transAxes, fontsize=9, color="#485460")
ax.text(0, -0.35, "Earlier exploratory query: unweighted 22-station mean; reported 682/1,461 days. Category counts unavailable.",
        transform=ax.transAxes, fontsize=8.5, color="#485460")
fig.savefig(RESULTS / "psr_calibration_preliminary.png", dpi=180, bbox_inches="tight", facecolor="white")

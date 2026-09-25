"""Plot temperature MAE by rainfall group and forecast lead from aggregate CSV."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


RESULTS = Path(__file__).resolve().parent / "results"
source = RESULTS / "temperature_error_by_rain_and_lead.csv"
with source.open(newline="", encoding="utf-8") as file:
    rows = list(csv.DictReader(file))
if not rows:
    raise ValueError(f"No analysis rows in {source}")

fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), sharey=True, layout="constrained")
fig.patch.set_facecolor("white")
styles = {
    "under_10_mm": ("<10 mm", "#1764a0", "o"),
    "at_least_10_mm": ("≥10 mm", "#bd6b2a", "s"),
}
for ax, metric in zip(axes, ("Tmax", "Tmin")):
    for group, (label, color, marker) in styles.items():
        points = sorted(
            ((int(row["lead_days"]), float(row["mae_c"])) for row in rows
             if row["metric"] == metric and row["rain_group"] == group)
        )
        if points:
            ax.plot(*zip(*points), label=label, color=color, marker=marker,
                    linewidth=2, markersize=5)
    ax.set(title=metric, xlabel="Forecast lead (days)", xticks=range(1, 10), xlim=(1, 9))
    ax.grid(axis="y", color="#e8edf0")
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
axes[0].set_ylabel("Mean absolute error (°C)")
axes[1].legend(title="HKO station rainfall", frameon=False)
fig.suptitle("Temperature forecast error by observed rainfall", fontsize=14)
fig.savefig(RESULTS / "temperature_error_by_rain.png", dpi=180,
            bbox_inches="tight", facecolor="white")

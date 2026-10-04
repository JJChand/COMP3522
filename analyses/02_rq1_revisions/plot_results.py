"""Render RQ1 figures directly from the reviewed aggregate CSVs."""
import csv
import json
import os
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / 'results'
# Keep Matplotlib's cache within the workspace, not the user's home directory.
os.environ.setdefault('MPLCONFIGDIR', str(RESULTS.parent / '.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

LABELS = {'tmin': 'Minimum temperature', 'tmax': 'Maximum temperature',
          'rh_min': 'Minimum relative humidity', 'rh_max': 'Maximum relative humidity'}
STYLES = {'consecutive_le24h': ('#2369A1', '-', 'o', 'Successive archived (gap ≤24 h)'),
          'daily_latest': ('#B66D18', '--', 's', 'Daily latest (consecutive issue days)')}


def main():
    with (RESULTS / 'revision_by_lead.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    metadata = json.loads((RESULTS / 'run_metadata.json').read_text(encoding='utf-8'))
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False,
                         'axes.spines.right': False, 'figure.facecolor': 'white'})
    period = f"{metadata['start_inclusive']} ≤ target date < {metadata['end_exclusive']} (HKT)"
    for field, lower, upper, name, title in (
        ('mean_absolute_revision', 'mar_ci95_low', 'mar_ci95_high', 'mean_absolute_revision.png', 'RQ1 · Size of forecast revisions'),
        ('revision_frequency_pct', 'frequency_ci95_low_pct', 'frequency_ci95_high_pct', 'revision_frequency.png', 'RQ1 · Frequency of nonzero forecast revisions'),
    ):
        fig, axes = plt.subplots(2, 2, figsize=(12, 8.7))
        for ax, (metric, label) in zip(axes.flat, LABELS.items()):
            for scope, (color, line, marker, scope_label) in STYLES.items():
                selected = sorted((r for r in rows if r['metric'] == metric and r['scope'] == scope), key=lambda r: int(r['lead_days']))
                comparable = [r for r in selected if int(r['lead_days']) < 9]
                x = [int(r['lead_days']) for r in comparable]
                y = [float(r[field]) for r in comparable]
                ax.plot(x, y, color=color, linestyle=line, marker=marker, markersize=4, linewidth=1.7, label=scope_label)
                if comparable and all(r[lower] and r[upper] for r in comparable):
                    ax.fill_between(x, [float(r[lower]) for r in comparable], [float(r[upper]) for r in comparable], color=color, alpha=0.13)
                # Do not draw a trajectory into structurally different lead-9 pairs.
                for boundary in (r for r in selected if int(r['lead_days']) == 9):
                    value = float(boundary[field])
                    ax.plot([9], [value], linestyle='none', marker='D', color='#555555',
                            markerfacecolor='white', markersize=5, label='Lead 9: within-day pairs only')
                    if boundary[lower] and boundary[upper]:
                        ax.vlines(9, float(boundary[lower]), float(boundary[upper]), color='#555555', linewidth=1)
            ax.set_title(label, loc='left', fontsize=12)
            ax.set_xlabel('Later forecast lead (calendar days)')
            ax.set_xticks(range(1, 10))
            ax.set_xlim(0.7, 9.3)
            ax.set_ylim(bottom=0)
            if field == 'revision_frequency_pct':
                ax.set_ylim(0, 100)
                ax.set_ylabel('Pairs with a nonzero revision (%)')
            else:
                ax.set_ylabel('Mean absolute revision (' + ('°C' if metric.startswith('t') else 'percentage points') + ')')
            ax.grid(axis='y', color='#dddddd', linewidth=0.6)
            ax.set_axisbelow(True)
        handles, legend_labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(handles, legend_labels, loc='upper center', bbox_to_anchor=(0.5, 0.93), ncol=2, frameon=False)
        fig.suptitle(title + '\n' + period, fontsize=16, y=0.995)
        fig.text(0.06, 0.024,
                 'Shading: 95% target-date cluster bootstrap intervals; no correction for serial dependence.\n'
                 'Lead 9 is a separate within-day-only point. Pair counts and provenance: adjacent CSVs and run_metadata.json.', fontsize=9)
        fig.tight_layout(rect=(0.025, 0.075, 0.995, 0.88))
        fig.savefig(RESULTS / name, dpi=160)
        plt.close(fig)
    print('RQ1 plots saved.')


if __name__ == '__main__':
    main()

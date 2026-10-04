"""Local reproducible figures for the user-requested per-RQ results folders."""
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parent / '.mplconfig'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS = ('#2369A1', '#B66D18', '#65703F', '#A04E7D')
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'figure.facecolor': 'white', 'axes.axisbelow': True})


def panels(title, labels):
    fig, axes = plt.subplots(1, len(labels), figsize=(6*len(labels), 4.5), squeeze=False, sharey=True)
    for ax, label in zip(axes.flat, labels):
        ax.set_title(label, loc='left')
        ax.grid(axis='y', color='#dedede', linewidth=.6)
    fig.suptitle(title + ' · 2022–2025', fontsize=15)
    return fig, list(axes.flat)


def save(fig, folder, filename, note='Source: local HKO database; counts and definitions in adjacent CSVs.', bottom=.07):
    fig.text(.04, .025, note, fontsize=9)
    fig.tight_layout(rect=(0, bottom, 1, .94))
    fig.savefig(folder / filename, dpi=150)
    plt.close(fig)

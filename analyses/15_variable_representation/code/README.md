# Reproduction code

These scripts and notebooks preserve the executed three-family experiment. Model fitting uses the definitions-only cells in `research/task1_variable_selection.ipynb`; no database connection is used. The accompanying executed notebook retains the original numerical outputs and two figures. Notebook root discovery was changed to the included requirements-file marker; local absolute output paths were redacted. The experiment scripts preserve the validated source logic; text line endings are normalized to LF.

## Environment and checks

From this `code/` directory, install the pinned-compatible ranges in `requirements-variable-selection.txt`, using Python 3.12. Tested execution versions are in `../results/versions.json`. CPU only; no CUDA is needed.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-variable-selection.txt
.\.venv\Scripts\python.exe -X utf8 scripts/test_task1_three_family_representation.py
```

The focused unit tests run without real data. A complete synthetic run is also available:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/task1_three_family_representation.py --synthetic --alpha-count 8 --bootstrap-draws 30
```

## Real-data rerun boundary

The frozen observations are **not included** in this publication. Re-running the real fit requires the five original files listed by `../results/input_manifest.json` plus `manifest.json`, placed at:

```text
code/data/derived/task1_variable_selection_20261117/inputs/
```

The loader checks all frozen-file hashes, station/unit/family metadata and QC before fitting. The source inputs cover 2022–2025: HQ temperature extrema/RH endpoints/rainfall/cloud, Airport mean wind speed and King's Park sunshine. QC C is required for CSV series; RYES RH has no corresponding completeness flag. Common complete dates are 1,458; no missing-value imputation. Daily date labels are treated as HKT days; original within-day aggregation windows were not separately reverified. HQ rain is not territory-level PSR truth. No acquisition script, credentials or raw source snapshots are published.

With those exact inputs available, from this directory:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/task1_three_family_representation.py
# Or execute and save notebook outputs without opening a local kernel port:
.\.venv\Scripts\python.exe -X utf8 scripts/run_task1_three_family_notebook.py
```

For interactive Jupyter execution, select a kernel using this environment and open `research/task1_three_family_representation.ipynb`. Each run creates a new UTC directory and ZIP under `data/derived/task1_three_family_representation_20261118/`. The original settings/validation describe the local unnormalized source hashes (including notebook/root/output and text-line-ending differences). The public file hashes are recorded separately in `../results/publication_manifest.json`.

Full local predictions and their ZIP are omitted; `analysis_validation.json` records the original prediction recomputation and QR cross-check. It is not a new verification of those omitted rows by a repository reader. See `../README.md` and `../FINDINGS_ZH.md` for the bounded scientific interpretation.

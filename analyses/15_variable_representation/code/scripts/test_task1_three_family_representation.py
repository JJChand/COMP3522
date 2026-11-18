"""Synthetic checks and independent verification of saved ablation results."""
import argparse
import hashlib
import json
from pathlib import Path
import unittest
import zipfile

import numpy as np
import pandas as pd

import task1_three_family_representation as experiment


class RepresentationChecks(unittest.TestCase):
    def test_core_inputs_and_whole_family_exclusion(self):
        methods = experiment.notebook_methods()
        for target in experiment.TARGETS:
            core = experiment.columns_for(methods, target, "three_family")
            full = experiment.columns_for(methods, target, "full")
            self.assertEqual(core, list(experiment.CORE))
            self.assertTrue(set(core) < set(full))
            self.assertTrue(all(methods.FAMILY_OF[c] != methods.FAMILY_OF[target] for c in full))
        self.assertEqual(set(experiment.columns_for(methods, "cloud", "full"))-set(experiment.CORE), {"wind_speed"})
        self.assertEqual(set(experiment.columns_for(methods, "wind_speed", "full"))-set(experiment.CORE), {"cloud", "sunshine"})

    def test_paired_identity_omitted_signal_and_reverse_sign(self):
        dates = pd.date_range("2025-01-01", "2025-12-31").delete([5, 6, 98])
        rng = np.random.default_rng(621)
        signal = rng.normal(size=len(dates))
        truth = signal+rng.normal(scale=.05, size=len(dates))
        for block in (7, 14):
            score = experiment.paired_scores(dates, truth, signal, signal, np.zeros(len(dates)), block, 100, 12)
            self.assertEqual(score["delta_mse"], 0)
            self.assertEqual(score["skill_gap_ci_high"], 0)
            lost = experiment.paired_scores(dates, truth, np.zeros(len(dates)), signal, np.zeros(len(dates)), block, 100, 12)
            self.assertGreater(lost["skill_gap_ci_low"], .9)
            reversed_score = experiment.paired_scores(dates, truth, signal, np.zeros(len(dates)), np.zeros(len(dates)), block, 100, 12)
            self.assertLess(reversed_score["delta_mse_ci_high"], 0)
            np.testing.assert_allclose(lost["skill_gap"], -reversed_score["skill_gap"])

    def test_zero_baseline_duplicate_and_bad_scope(self):
        dates = pd.date_range("2025-01-01", periods=100)
        zero = np.zeros(100)
        score = experiment.paired_scores(dates, zero, zero, zero, zero, 7, 100, 13)
        self.assertTrue(np.isnan(score["skill_gap"]))
        self.assertEqual(score["bootstrap_status"], "unavailable")
        with self.assertRaises(ValueError):
            experiment.paired_scores(dates[[0, 0]], zero[:2], zero[:2], zero[:2], zero[:2], 7, 100, 13)
        with self.assertRaises(ValueError):
            experiment.columns_for(experiment.notebook_methods(), "sunshine", "unknown")


def verify_run(folder):
    folder = Path(folder)
    manifest = json.loads((folder/"result_manifest.json").read_text())
    with zipfile.ZipFile(folder.with_suffix(".zip")) as archive:
        assert archive.testzip() is None
        for name, expected in manifest["files"].items():
            assert hashlib.sha256((folder/name).read_bytes()).hexdigest() == expected
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
    pred = pd.read_csv(folder/"predictions.csv")
    key = ["scenario", "evaluation_year", "target", "scope", "method"]
    assert not pred.duplicated(key+["date_hkt"]).any()
    pred["loss"] = (pred.observed-pred.predicted)**2
    pred["base_loss"] = (pred.observed-pred.seasonal_baseline)**2
    recomputed = pred.groupby(key)[["loss", "base_loss"]].mean().reset_index()
    mse = recomputed.pivot(index=["scenario", "evaluation_year", "target", "method"], columns="scope", values="loss").reset_index()
    comparison = pd.read_csv(folder/"comparison.csv")
    check = comparison.merge(mse, on=["scenario", "evaluation_year", "target", "method"], validate="many_to_one")
    assert len(check) == len(comparison) == 432
    np.testing.assert_allclose(check.three_family_mse, check.three_family, atol=1e-10)
    np.testing.assert_allclose(check.full_mse, check.full, atol=1e-10)
    np.testing.assert_allclose(check.skill_gap, check.full_skill-check.three_family_skill, atol=1e-12)
    np.testing.assert_allclose(check.delta_mse, check.three_family_mse-check.full_mse, atol=1e-10)
    baseline = recomputed.groupby(["scenario", "evaluation_year", "target"]).base_loss.agg(["min", "max"])
    np.testing.assert_allclose(baseline["min"], baseline["max"], atol=1e-12)
    statuses = pd.read_csv(folder/"status.csv")
    assert len(statuses) == 432 and statuses.status.eq("ok").all()
    dates = pd.to_datetime(statuses.last_train_date)
    first = pd.to_datetime(statuses.first_test_date)
    assert (first-dates).dt.days.ge(8).all()
    for _, group in pred.groupby(["scenario", "evaluation_year", "target"]):
        reference = group.loc[group.scope.eq("full") & group.method.eq("ols"), ["date_hkt", "observed", "seasonal_baseline"]].reset_index(drop=True)
        for _, candidate in group.groupby(["scope", "method"]):
            pd.testing.assert_frame_equal(reference, candidate[["date_hkt", "observed", "seasonal_baseline"]].reset_index(drop=True))
    models = pd.read_csv(folder/"bayesian_models.csv")
    weights = models.groupby(key).posterior_weight.sum()
    np.testing.assert_allclose(weights, 1, atol=1e-12)
    cv = pd.read_csv(folder/"lasso_cv.csv")
    assert cv.loc[cv.selected, "status"].eq("ok").all() and cv.selected.sum() == 54
    assert comparison.bootstrap_status.eq("ok").all()
    return dict(manifest_hashes_verified=len(manifest["files"]), prediction_rows=len(pred),
                metric_rows=len(comparison), model_statuses=len(statuses),
                max_mse_recompute_error=float(max(abs(check.three_family_mse-check.three_family).max(), abs(check.full_mse-check.full).max())),
                lasso_failed_alphas=int(cv.status.ne("ok").sum()), all_checks_passed=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir")
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RepresentationChecks))
    if not result.wasSuccessful():
        raise SystemExit(1)
    if args.run_dir:
        print(json.dumps(verify_run(args.run_dir), indent=2))

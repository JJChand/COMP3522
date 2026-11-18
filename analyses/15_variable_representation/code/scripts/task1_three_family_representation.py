"""Reconstruct omitted weather channels from temperature, RH and rainfall.

Reuse the reviewed notebook's QC, seasonal, LASSO and Bayesian implementations.
Run through research/task1_three_family_representation.ipynb or this CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from types import SimpleNamespace
import zipfile

import nbformat
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/task1_variable_selection.ipynb"
INPUT = ROOT / "data/derived/task1_variable_selection_20261117/inputs"
OUTPUT = ROOT / "data/derived/task1_three_family_representation_20261118"
TARGETS = ("wind_speed", "cloud", "sunshine")
CORE = ("tmax", "tmin", "rh_min", "rh_max", "rainfall")
SEED = 20261118


def notebook_methods():
    notebook = nbformat.read(SOURCE, as_version=4)
    nbformat.validate(notebook)
    namespace = {"__name__": "representation_notebook_methods"}
    # Execute definitions only; never execute saved fitting or export cells.
    for index in (2, 3, 7):
        cell = notebook.cells[index]
        assert cell.cell_type == "code"
        assert set(cell.metadata.get("tags", [])) & {"parameters", "definitions"}
        exec(compile(cell.source, str(SOURCE), "exec"), namespace)
    return SimpleNamespace(**namespace)


def columns_for(methods, target, scope):
    if target not in TARGETS or scope not in ("three_family", "full"):
        raise ValueError("Unexpected target or input scope")
    columns = list(CORE) if scope == "three_family" else methods.predictor_columns(target)
    assert all(methods.FAMILY_OF[c] != methods.FAMILY_OF[target] for c in columns)
    return columns


def paired_scores(dates, truth, restricted, full, baseline, block, draws, seed):
    """Same calendar resamples for both models and baseline; positive gap = loss."""
    dates = pd.DatetimeIndex(dates)
    if not dates.is_unique or not dates.is_monotonic_increasing or len(set(dates.year)) != 1:
        raise ValueError("Paired bootstrap needs ordered distinct dates in one year")
    loss = np.column_stack([(truth-restricted)**2, (truth-full)**2, (truth-baseline)**2])
    if not np.isfinite(loss).all():
        raise ValueError("Nonfinite paired losses")
    calendar = pd.date_range(f"{dates[0].year}-01-01", f"{dates[0].year}-12-31")
    daily = np.full((len(calendar), 3), np.nan)
    daily[calendar.get_indexer(dates)] = loss
    rng = np.random.default_rng(seed)
    starts = rng.integers(len(calendar), size=(draws, math.ceil(len(calendar)/block)))
    indices = ((starts[..., None]+np.arange(block)) % len(calendar)).reshape(draws, -1)[:, :len(calendar)]
    sampled = daily[indices]
    counts = np.isfinite(sampled[:, :, 0]).sum(axis=1)
    means = np.divide(np.nansum(sampled, axis=1), counts[:, None],
                      out=np.full((draws, 3), np.nan), where=counts[:, None] > 0)
    mse = loss.mean(axis=0)
    values = {"delta_mse": (float(mse[0]-mse[1]), means[:, 0]-means[:, 1])}
    if mse[2] > 1e-12:
        safe = means[:, 2] > 1e-12
        rskill = np.divide(means[:, 2]-means[:, 0], means[:, 2], out=np.full(draws, np.nan), where=safe)
        fskill = np.divide(means[:, 2]-means[:, 1], means[:, 2], out=np.full(draws, np.nan), where=safe)
        values.update(three_family_skill=(float(1-mse[0]/mse[2]), rskill),
                      full_skill=(float(1-mse[1]/mse[2]), fskill),
                      skill_gap=(float((mse[0]-mse[1])/mse[2]), fskill-rskill))
    else:
        values.update({name: (np.nan, np.full(draws, np.nan))
                       for name in ("three_family_skill", "full_skill", "skill_gap")})
    result = dict(n_test=len(dates), three_family_mse=float(mse[0]), full_mse=float(mse[1]),
                  baseline_mse=float(mse[2]), block_calendar_days=block)
    valid_counts = []
    for name, (point, sampled_values) in values.items():
        finite = sampled_values[np.isfinite(sampled_values)]
        valid_counts.append(len(finite))
        bounds = np.quantile(finite, [.025, .975]) if len(finite) >= .9*draws else (np.nan, np.nan)
        result.update({name: point, name+"_ci_low": float(bounds[0]), name+"_ci_high": float(bounds[1])})
    result["valid_bootstrap_draws"] = min(valid_counts)
    result["bootstrap_status"] = "ok" if min(valid_counts) >= .9*draws else "unavailable"
    return result


def run_experiment(synthetic=False, n_alpha=40, draws=1000):
    methods = notebook_methods()
    long, manifest, catalog = methods.synthetic_input() if synthetic else methods.load_frozen(INPUT)
    rows = {name: [] for name in ("predictions", "comparison", "status", "lasso_cv",
                                  "lasso_coefficients", "bayesian_models", "bayesian_pips", "ols_coefficients")}
    coverage = None
    for scenario, trace in {"primary": .025, "trace_lower": 0., "trace_upper": .05}.items():
        wide, coverage = methods.prepare_panel(long, trace)
        data = methods.transform_panel(wide)
        assert len(data) == 1458 if not synthetic else len(data) > 1000
        for year in (2023, 2024, 2025):
            print(f"{scenario}: {year}", flush=True)
            train = data.loc[data.index < pd.Timestamp(f"{year}-01-01")-pd.Timedelta(days=7)]
            test = data.loc[data.index.year == year]
            if len(train) < 180 or len(test) < 60:
                raise ValueError("Insufficient common training/evaluation dates; no automatic narrowing")
            assert train.index.max() < test.index.min()-pd.Timedelta(days=7)
            z, znew = methods.seasonal_basis(train.index), methods.seasonal_basis(test.index)
            for target in TARGETS:
                key = dict(scenario=scenario, evaluation_year=year, target=target)
                y, truth = train[target].to_numpy(), test[target].to_numpy()
                baseline = znew@np.linalg.lstsq(z, y, rcond=None)[0]
                full_columns = columns_for(methods, target, "full")
                full_setup = None
                try:
                    full_setup = methods.bayesian_setup(train.index, z, train[full_columns].to_numpy(), y)
                except (ValueError, np.linalg.LinAlgError) as exc:
                    print(f"Bayesian setup unavailable: {key}: {exc}", flush=True)
                predictions = {}
                for scope in ("three_family", "full"):
                    columns = columns_for(methods, target, scope)
                    scope_key = dict(**key, scope=scope)
                    x, xnew = train[columns].to_numpy(), test[columns].to_numpy()
                    local = {}
                    try:
                        design, new_design = np.column_stack([z, x]), np.column_stack([znew, xnew])
                        methods.rank_guard(design, "fixed OLS "+scope)
                        beta = np.linalg.lstsq(design, y, rcond=None)[0]
                        local["ols"] = new_design@beta
                        for name, coef in zip(["intercept", "sin1", "cos1", "sin2", "cos2"]+columns, beta):
                            rows["ols_coefficients"].append(dict(**scope_key, predictor=name, coefficient=float(coef)))
                    except (ValueError, np.linalg.LinAlgError) as exc:
                        rows["status"].append(dict(**scope_key, method="ols", status="unavailable", reason=str(exc)))
                    try:
                        prediction, coef, native, alpha, cv = methods.select_lasso(train.index, z, x, y, znew, xnew, n_alpha)
                        local["lasso"] = prediction
                        rows["lasso_cv"].extend(dict(**scope_key, **record) for record in cv)
                        for name, value, native_value in zip(columns, coef, native):
                            rows["lasso_coefficients"].append(dict(**scope_key, predictor=name,
                                coefficient_standardized=float(value), coefficient_native=float(native_value),
                                selected=bool(abs(value) > 1e-10), alpha=alpha))
                    except (ValueError, np.linalg.LinAlgError, methods.ConvergenceWarning) as exc:
                        rows["status"].append(dict(**scope_key, method="lasso", status="unavailable", reason=str(exc)))
                    for g_factor, pi in itertools.product((.25, 1., 4.), (.25, .5)):
                        name = "bayesian_bma" if (g_factor, pi) == (1., .5) else f"bayes_g{g_factor:g}_pi{pi:g}"
                        try:
                            if full_setup is None:
                                raise ValueError("Shared full-model training AR(1) setup unavailable")
                            indices = [full_columns.index(c) for c in columns]
                            # Hold covariance fixed across scopes to isolate the predictor-set comparison.
                            setup = dict(full_setup, rx=full_setup["rx"][:, indices], wx=full_setup["wx"][:, indices])
                            prediction, pips, models = methods.bayesian_select(setup, columns, znew, xnew, len(y)*g_factor, pi)
                            local[name] = prediction
                            bayes_key = dict(**scope_key, method=name, g_factor=g_factor, inclusion_prior=pi,
                                             rho=setup["rho"], whitened_residual_lag1=setup["whitened_residual_lag1"])
                            rows["bayesian_models"].extend(dict(**bayes_key, **record) for record in models)
                            rows["bayesian_pips"].extend(dict(**bayes_key, predictor_family=f, pip=float(v)) for f, v in pips.items())
                        except (ValueError, np.linalg.LinAlgError) as exc:
                            rows["status"].append(dict(**scope_key, method=name, status="unavailable", reason=str(exc)))
                    for name, prediction in local.items():
                        if not np.isfinite(prediction).all():
                            raise ValueError("Nonfinite prediction")
                        predictions[(scope, name)] = prediction
                        rows["status"].append(dict(**scope_key, method=name, status="ok", reason="",
                            inputs="|".join(columns), n_train=len(train), n_test=len(test),
                            last_train_date=train.index.max().date().isoformat(), first_test_date=test.index.min().date().isoformat()))
                        rows["predictions"].extend(dict(**scope_key, method=name, date_hkt=date.date().isoformat(),
                            observed=float(value), predicted=float(pred), seasonal_baseline=float(base))
                            for date, value, pred, base in zip(test.index, truth, prediction, baseline))
                for name in sorted({name for _, name in predictions}):
                    if ("three_family", name) not in predictions or ("full", name) not in predictions:
                        continue
                    for block in (7, 14):
                        rows["comparison"].append(dict(**key, method=name, unit=methods.UNITS[target],
                            **paired_scores(test.index, truth, predictions[("three_family", name)],
                                predictions[("full", name)], baseline, block, draws, SEED+year*17+TARGETS.index(target))))
    return {name: pd.DataFrame(records) for name, records in rows.items()}, coverage, manifest, catalog


def plot_results(results, output):
    import matplotlib.pyplot as plt
    data = results["comparison"].query("scenario=='primary' and method=='ols' and block_calendar_days==7")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for ax, target in zip(axes, TARGETS):
        group = data.loc[data.target.eq(target)].sort_values("evaluation_year")
        for scope, offset, color in (("three_family", -.07, "#356a9a"), ("full", .07, "#ad5729")):
            value = group[scope+"_skill"].to_numpy()*100
            low, high = (group[scope+"_skill_ci_"+end].to_numpy()*100 for end in ("low", "high"))
            positions = np.arange(3)+offset
            ax.vlines(positions, low, high, color=color)
            ax.scatter(positions, value, color=color, label=scope.replace("_", " "), s=25)
        ax.set(title=target, xticks=np.arange(3), xticklabels=group.evaluation_year.astype(str))
        ax.axhline(0, color="#777777", lw=.8)
    axes[0].set_ylabel("MSE skill vs seasonal baseline (%)")
    axes[0].legend(fontsize=9)
    fig.suptitle("OLS: information coverage on future-year observations; paired 95% block CI")
    fig.tight_layout()
    fig.savefig(output/"ols_skill.png")
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    for ax, target in zip(axes, TARGETS):
        for name, offset, color in (("ols", -.15, "#356a9a"), ("lasso", 0, "#ad5729"), ("bayesian_bma", .15, "#397d62")):
            group = results["comparison"].query("scenario=='primary' and block_calendar_days==7 and target==@target and method==@name").sort_values("evaluation_year")
            positions = np.arange(len(group))+offset
            ax.vlines(positions, group.skill_gap_ci_low*100, group.skill_gap_ci_high*100, color=color)
            ax.scatter(positions, group.skill_gap*100, color=color, label=name, s=25)
        ax.set(title=target, xticks=np.arange(3), xticklabels=[2023, 2024, 2025])
        ax.axhline(0, color="#777777", lw=.8)
    axes[0].set_ylabel("Full skill minus three-family skill (percentage points)")
    axes[0].legend(fontsize=9)
    fig.suptitle("Cost of retaining only temperature, RH and rainfall; positive = full model better")
    fig.tight_layout()
    fig.savefig(output/"paired_skill_gap.png")
    plt.close(fig)


def execute(synthetic=False, n_alpha=40, draws=1000):
    methods = notebook_methods()
    stamp = methods.datetime.now(methods.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = OUTPUT/("synthetic_validation" if synthetic else "results")/stamp
    output.mkdir(parents=True, exist_ok=False)
    with methods.threadpool_limits(limits=1):
        results, coverage, manifest, catalog = run_experiment(synthetic, n_alpha, draws)
    for name, frame in results.items():
        frame.to_csv(output/(name+".csv"), index=False)
    coverage.to_csv(output/"coverage.csv", index=False)
    methods.json_save(output/"input_manifest.json", manifest)
    methods.json_save(output/"channel_catalog.json", catalog)
    settings = dict(synthetic=synthetic, seed=SEED, alpha_grid_size=n_alpha, bootstrap_draws=draws,
        core_channels=CORE, targets=TARGETS, outer_years=[2023, 2024, 2025], gap_calendar_days=7,
        trace_values_mm={"primary": .025, "trace_lower": 0, "trace_upper": .05},
        primary_estimator="fixed OLS, no family significance filtering", bayes_rho="shared full-model training estimate",
        equivalence_margin=None, interpretation="Exploratory same-day observation coverage; no forecast/causal/social ranking",
        notebook_definition_sha256=methods.digest(SOURCE), script_sha256=methods.digest(__file__))
    methods.json_save(output/"settings.json", settings)
    versions = {name: methods.importlib.metadata.version(name) for name in
                ("numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "matplotlib", "nbformat", "nbclient")}
    methods.json_save(output/"versions.json", versions)
    plot_results(results, output)
    methods.json_save(output/"result_manifest.json", {"files": {p.name: methods.digest(p) for p in sorted(output.iterdir())}})
    with zipfile.ZipFile(output.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as archive:
        for path in output.iterdir():
            archive.write(path, path.name)
    print(f"Results: {output}", flush=True)
    return output, results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--alpha-count", type=int, default=40)
    parser.add_argument("--bootstrap-draws", type=int, default=1000)
    args = parser.parse_args()
    execute(args.synthetic, args.alpha_count, args.bootstrap_draws)

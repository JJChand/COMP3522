"""Build the local handoff summary from executed aggregates, never invented values."""
import csv
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common.task1 import ANALYSES,FOLDERS,table as source_table


def table(rows,fields):
    """Format CSV numerics at reading precision without altering underlying exports."""
    displayed=[]
    for row in rows:
        selected={}
        for key in fields:
            value=row.get(key)
            if value=='':
                value=None
            elif isinstance(value,str):
                try:
                    value=float(value) if '.' in value or 'e' in value.lower() else int(value)
                except ValueError:
                    pass
            selected[key]=value
        displayed.append(selected)
    return source_table(displayed,fields)


def read(rq,name):
    with (ANALYSES/FOLDERS[rq]/'results'/name).open(encoding='utf-8',newline='') as handle:
        return list(csv.DictReader(handle))


def main():
    statuses={2:'Executed: temperature/RH revisions and PSR categories',
              3:'Executed: temperature and validated daily-report RH revision usefulness',
              4:'Executed: temperature/RH accuracy and matched reference skill',
              5:'Executed: temperature/RH bias by lead, season and year',
              6:'All named metrics executed against disclosed rainfall proxies, not exact HKO territorial labels',
              7:'All named factor directions executed for temperature errors and revisions; post-event context'}
    body=['# Part 1: executed findings and remaining evidence gaps','',
          'Target dates: 2022-01-01–2025-12-31. Local database, read-only. Task 2 remains on hold.','',
          'All RQ folders contain executed concrete results and a findings report. This is **not a claim that '
          'every originally named verification component is complete**: PSR verification uses spatial proxies, '
          'and their equivalence to the official territorial event is not established. RH daily-report endpoints '
          'are now validated and scored; they are explicitly provisional and have no CSV completeness flag.','',
          '## Coverage and report index','',
          '| RQ | Status | Findings report |','| --- | --- | --- |',
          '| RQ1 | Previously executed and independently verified | [Revision size/frequency](02_rq1_revisions/results/findings.md) |']
    for rq,folder in FOLDERS.items():
        if not (ANALYSES/folder/'results/findings.md').is_file():
            raise ValueError('Missing findings: '+folder)
        body.append(f'| RQ{rq} | {statuses[rq]} | [RQ{rq} report]({folder}/results/findings.md) |')
    ffi=[r for r in read(2,'flip_flop_summary.csv') if r['scope']=='consecutive_le24h']
    body+=['','## RQ2: back-and-forth revisions','',
           table(ffi,['metric','unit','mean_target_ffi','n_adjacent_nonzero_sign_pairs','adjacent_reversal_rate_pct','compressed_reversal_rate_pct']),
           '', 'FFI is in the original measurement unit, not a reversal percentage. Adjacent reversals require two '
           'immediately adjacent nonzero changes; compressed reversals skip zeros, not archive gaps. PSR transition counts are categorical.','',
           table(read(2,'psr_transition_summary.csv'),['scope','n_pairs','n_changed','change_rate_pct']),
           '', '## RQ3: are changes useful?','',
           table([r for r in read(3,'usefulness_overall.csv') if r['scope']=='consecutive_le24h' and r['denominator']=='changed_only'],
                 ['metric','n_pairs','usefulness_rate_pct','ci95_low_pct','ci95_high_pct','mean_absolute_error_reduction','error_reduction_unit']),
           '', 'Changed-only rates must not be confused with all-pair rates. Temperature errors use °C; RH uses percentage points. '
           'Primary lead-9 temperature comparisons have seven changed pairs per variable and concern same-day boundary updates; RH counts are separate.','',
           '## RQ4: lead-time accuracy and skill','',
           table([r for r in read(4,'temperature_accuracy_by_lead.csv') if r['selection']=='daily_latest' and r['lead_days'] in ('1','9')],
                 ['metric','lead_days','n','mae','rmse']),
           '', 'Units: °C; HKO Headquarters point station, not a territory-wide mean.','',
           '### RH endpoint accuracy','',
           table([r for r in read(4,'rh_accuracy_by_lead.csv') if r['selection']=='daily_latest' and r['lead_days'] in ('1','9')],
                 ['metric','lead_days','n','mae','rmse']),
           '', 'Units: percentage points. HKOReadingsMinRH/MaxRH daily JSON reports, joined on report_date, not bulletin publication date. '
           'All 1,461 dates pass numeric/date/range checks; the reports explicitly mark data as provisional with limited validation and lack a CSV-style completeness flag. '
           '[HKO field definitions](https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf), printed pages 36–37.','',
           '### Matched reference skill','',
           table([r for r in read(4,'baseline_skill_by_lead.csv') if r['selection']=='daily_latest' and r['lead_days'] in ('1','9') and r['baseline'] in ('climatology_mean','persistence_lag2')],
                 ['metric','lead_days','baseline','n_matched','mae_skill','mse_skill']),
           '', 'Positive skill means lower error on the same matched cases. Climatology is frozen at 1991–2020; '
           'persistence is a retrospective past-day comparator because publication times are unverified. '
           'RH mean-range consistency is not RH-extrema MAE/RMSE.','',
           table([r for r in read(4,'rh_baseline_skill_by_lead.csv') if r['selection']=='daily_latest' and r['lead_days'] in ('1','9') and r['baseline'] in ('climatology_mean_2022','persistence_lag2')],
                 ['metric','lead_days','baseline','verification_period','n_matched','mae_skill','mse_skill']),
           '', 'RH reference: freeze 2022 ±15-calendar-day means; verify only 2023–2025, never the training year. '
           'This one-year seasonal reference is not the temperature 1991–2020 normal. RH persistence is also a retrospective comparator.','',
           '## RQ5: signed bias','',
           table(read(5,'bias_overall.csv'),['metric','n_forecasts','mean_error_c','calendar7day_block_ci95_low','calendar7day_block_ci95_high']),
           '', 'Units: °C; positive means over-forecasting. Seasonal/year tables and lead×season×year cross-tables '
           'are in the RQ5 report/folder; pooled differences are not causal improvements.','',
           table(read(5,'rh_bias_overall.csv'),['metric','n_forecasts','mean_error_pp','calendar7day_block_ci95_low','calendar7day_block_ci95_high']),
           '', 'RH units: percentage points; positive means over-forecasting. RH season/year/lead tables are saved separately.','',
           '## RQ6: PSR and rainfall proxies','',
           table([r for r in read(6,'brier_scores.csv') if r['lead_group']=='all'],
                 ['proxy','n_forecasts','event_rate','midpoint_bs','bs_lower_bound','bs_upper_bound']),
           '', 'Midpoint Brier scores assume category midpoints; score bounds are not confidence intervals. '
           'The weighted 22-station daily-mean rainfall ≥10 mm event is not the exact territorial HKO verification label.','',
           table([r for r in read(6,'contingency_tables.csv') if r['proxy']=='area_weighted_22' and r['lead_group']=='all'],
                 ['alarm_rule','tp','fp','fn','tn','hit_rate','false_alarm_ratio']),
           '', 'Reliability diagrams, published bands, lead-group breakdowns and target coverage are in RQ6. '
           'The retained-report rainfall audit finds only point daily rainfall and cumulative-like fields, '
           'not a confirmed daily territorial label; see [the source audit](07_rq6_psr_calibration/results/rainfall_report_audit.json).','',
           '## RQ7: associated conditions','',
           table([r for r in read(7,'stratified_contrasts.csv') if r['outcome_kind']=='absolute_error' and r['factor'] in ('rain10','change_high','spread_high')],
                 ['metric','factor','n_cases','mean_difference_c','ci95_low','ci95_high']),
           '', 'High-versus-low differences after lead/season stratification; change-high means ≥2 °C day-to-day '
           'change and spread-high uses a fixed 2022 panel median. These estimates use common-support cases and '
           '7-day block bootstrap intervals, not causal tests. Season and weather-narrative comparisons, '
           'revision outcomes, coefficients, correlations and holdout SHAP are included in the RQ7 report.','',
           table(read(7,'join_coverage.csv'),['metric','outcome_kind','eligible_cases','matched_cases','excluded_cases','matched_dates']),
           '', table([r for r in read(7,'model_diagnostics.csv') if r['subset']=='holdout_2025'],
                     ['metric','outcome_kind','n_cases','r_squared','mae_c','train_mean_baseline_mae_c']),
           '', 'The fixed-panel join excludes many days. Low/negative holdout R² limits explanations; linear SHAP '
           'ranks this model’s attributions, not established causal importance. Chronological holdout does not '
           'turn realized target-day weather into information available at issuance.','',
           '## Evidence and reproducibility','',
           'Each folder’s README gives the run command. `run_metadata.json` records input fingerprints and '
           'software versions; `verification.json` records the independent checks and their actual scope. '
           'Source SQL and shared method tests are in `common/`. Raw records and credentials are not exported.','',
           '| RQ | Independent aggregate groups checked |','| --- | ---: |']
    for rq,folder in FOLDERS.items():
        receipt=json.loads((ANALYSES/folder/'results/verification.json').read_text(encoding='utf-8'))
        body.append(f"| RQ{rq} | {receipt['independent_aggregate_checks']} |")
    body+=['', 'Independent live SQL covers RQ2 directions/PSR counts, RQ3 temperature/RH usefulness, RQ4 temperature/RH accuracy '
           'and matched temperature baselines, and RQ5 temperature/RH bias. Separately written Python checks daily-latest RH reference scores '
           'and all 732 frozen RH calendar bins (included in the RQ4 count). RQ6 checks cover all three proxies '
           'and all/1–3/4–6/7–9 lead groups: reliability counts/rates/bands, all Brier codings and bounds, '
           'confusion cells, hit rate, false alarm ratio, false-positive rate, coverage and unique exported grain. '
           'RQ7 checks cover joins/outcome means. These checks do not independently prove bootstrap intervals, FFI '
           'summaries, coefficient uncertainty or SHAP rankings; synthetic tests check representative method '
           'edge cases. Figures were visually inspected, including the corrected RQ3 legend/sample labels '
           'and aligned RQ4/RQ5 scales.','',
           '## What is needed to close the remaining scope?','',
           'The previously reported RH-extrema gap was a catalog-only inference: the daily JSON reports already contained '
           'matching endpoints. The read-only source audit now validates all 1,461 dates and the analysis scores them. '
           'No database import was needed. Daily mean RH was never substituted for the endpoints. The guide documents '
           'the corrected mapping and its missing-completeness-flag caveat.','',
           'Exact territorial PSR calibration needs the official realized event label or an agreed research '
           'definition accepting the documented spatial proxy. Operational persistence requires historical '
           'publication-availability evidence. These gaps are distinct from successful script execution.','']
    path=ANALYSES/'PART1_FINDINGS.md'
    path.write_text('\n'.join(body),encoding='utf-8')
    print('Part 1 summary:',path)


if __name__=='__main__':
    main()

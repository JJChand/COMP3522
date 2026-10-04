"""Validated daily HKO RH extrema from retained weather/radiation reports.

These JSON readings have no CSV-style completeness flag. Validation is not a
claim that they are finalized climatological observations. Never use mean RH
as an endpoint and never join using the next day's bulletin publication date.
"""
from collections import Counter
from datetime import timedelta
import math
import re

RH_FIELDS = {'rh_min': 'observed_rh_min_text', 'rh_max': 'observed_rh_max_text'}
DOCUMENTATION = 'https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf'


def number(value):
    if value is None or not re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?', str(value).strip()):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def validate_reports(reports, start, end, csv_observed=None):
    """Return endpoint maps and aggregate audit; exclude invalid dates/readings."""
    counts = Counter(r['report_date'] for r in reports)
    if any(n > 1 for n in counts.values()):
        raise ValueError('RH report dates are not unique; mapping requires review')
    output = {metric: {} for metric in RH_FIELDS}
    rejected, yearly, publication_lags, publication_times = Counter(), Counter(), Counter(), Counter()
    temperature_matches, temperature_mismatches, temperature_missing = Counter(), Counter(), Counter()
    mean_checks, mean_outside = 0, 0
    quality_notes = Counter()
    for row in reports:
        target = row['report_date']
        if target is None or not start <= target < end:
            rejected['outside_study_or_null_date'] += 1
            continue
        if row['source_observation_date'] != target.strftime('%Y%m%d'):
            rejected['source_date_disagrees'] += 1
            continue
        values = {m: number(row[field]) for m, field in RH_FIELDS.items()}
        if any(v is None for v in values.values()):
            rejected['missing_or_nonnumeric_endpoint'] += 1
            continue
        if any(not 0 <= v <= 100 for v in values.values()):
            rejected['endpoint_outside_0_100'] += 1
            continue
        if values['rh_min'] > values['rh_max']:
            rejected['minimum_exceeds_maximum'] += 1
            continue
        for metric, value in values.items():
            output[metric][target] = value
        yearly[target.year] += 1
        if row.get('source_quality_note'):
            quality_notes[row['source_quality_note']] += 1
        publication_lags['null' if row['bulletin_date'] is None else str((row['bulletin_date']-target).days)] += 1
        publication_times[str(row['bulletin_time'])] += 1
        if csv_observed:
            for metric in ('tmin', 'tmax'):
                report_value = number(row['observed_' + metric + '_text'])
                official = csv_observed[metric].get(target)
                if report_value is None or official is None:
                    temperature_missing[metric] += 1
                elif abs(report_value-official) < 1e-9:
                    temperature_matches[metric] += 1
                else:
                    temperature_mismatches[metric] += 1
            mean = csv_observed['rh_mean'].get(target)
            if mean is not None:
                mean_checks += 1
                mean_outside += not values['rh_min'] <= mean <= values['rh_max']
    expected = {start + timedelta(days=i) for i in range((end-start).days)}
    audit = dict(
        source_table='project.hko_multistation_report', station='Hong Kong Observatory',
        observed_fields={'rh_min': 'HKOReadingsMinRH', 'rh_max': 'HKOReadingsMaxRH'},
        unit='percent', error_unit='percentage_points', observation_date='report_date = ReportTimeInfoDate',
        official_definition_source=DOCUMENTATION, documentation_pages='36–37 (printed pages), station/attribute/date definitions',
        source_completeness_marker='not supplied in retained JSON; numeric/date/range validation only',
        source_quality_notes=dict(quality_notes),
        n_reports=len(reports), n_expected_dates=len(expected), n_valid_dates=len(output['rh_min']),
        n_missing_or_rejected_dates=len(expected-set(output['rh_min'])), rejected_by_reason=dict(rejected),
        valid_dates_by_year={str(y): n for y, n in sorted(yearly.items())},
        bulletin_minus_observation_days=dict(publication_lags), bulletin_times=dict(publication_times),
        temperature_crosscheck_matches=dict(temperature_matches),
        temperature_crosscheck_mismatches=dict(temperature_mismatches),
        temperature_crosscheck_missing=dict(temperature_missing),
        mean_rh_crosscheck_n=mean_checks, mean_rh_outside_report_extrema_n=mean_outside,
        mean_rh_crosscheck_interpretation='sanity check only; agreement does not establish finalized RH completeness',
    )
    return output, audit

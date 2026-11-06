WITH raw AS (
    SELECT d.valid_date, d.lead_days, d.forecast_issue_id,
           i.bulletin_time_hkt, i.published_time_utc, d.forecast_tmax_c,
           d.forecast_rh_min_pct, d.forecast_rh_max_pct
    FROM project.hko_forecast_daily d
    JOIN project.hko_forecast_issue i USING (forecast_issue_id)
    WHERE d.valid_date >= DATE '2022-01-01' AND d.valid_date < DATE '2026-01-01'
), canonical AS (
    SELECT DISTINCT ON (valid_date, bulletin_time_hkt) *
    FROM raw
    ORDER BY valid_date, bulletin_time_hkt, forecast_issue_id
), daily_latest AS (
    SELECT DISTINCT ON (valid_date, bulletin_time_hkt::date) *
    FROM canonical
    ORDER BY valid_date, bulletin_time_hkt::date, bulletin_time_hkt DESC, forecast_issue_id DESC
), tmax AS (
    SELECT o.observation_date AS valid_date, o.value_numeric AS actual
    FROM project.hko_daily_observation o
    JOIN project.hko_observation_series s USING (observation_series_id)
    WHERE s.series_code = 'obs_hko_daily_tmax' AND o.data_completeness = 'C'
      AND o.value_numeric IS NOT NULL
      AND o.observation_date >= DATE '2022-01-01' AND o.observation_date < DATE '2026-01-01'
), rh_report AS (
    SELECT report_date AS valid_date,
           report_json->>'ReportTimeInfoDate' AS source_date,
           btrim(report_json->>'HKOReadingsMinRH') AS lo,
           btrim(report_json->>'HKOReadingsMaxRH') AS hi
    FROM project.hko_multistation_report
    WHERE report_date >= DATE '2022-01-01' AND report_date < DATE '2026-01-01'
), rh_numeric AS (
    SELECT valid_date,
           CASE WHEN lo ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN lo::numeric END AS lo,
           CASE WHEN hi ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN hi::numeric END AS hi
    FROM rh_report
    WHERE source_date = to_char(valid_date, 'YYYYMMDD')
), actuals AS (
    SELECT valid_date, 'tmax' AS metric, actual FROM tmax
    UNION ALL
    SELECT valid_date, metric, actual
    FROM rh_numeric
    CROSS JOIN LATERAL (VALUES ('rh_min', lo), ('rh_max', hi)) endpoints(metric, actual)
    WHERE lo >= 0 AND hi <= 100 AND lo <= hi
), pairs AS (
    SELECT d.valid_date, d.lead_days, f.metric, abs(f.forecast - a.actual) AS loss
    FROM daily_latest d
    CROSS JOIN LATERAL (VALUES ('tmax', d.forecast_tmax_c),
                               ('rh_min', d.forecast_rh_min_pct),
                               ('rh_max', d.forecast_rh_max_pct)) f(metric, forecast)
    JOIN actuals a ON a.valid_date = d.valid_date AND a.metric = f.metric
    WHERE d.lead_days BETWEEN 1 AND 9 AND f.forecast IS NOT NULL
), audit AS (
    SELECT jsonb_build_object(
        'tmax_dates', (SELECT count(*) FROM tmax),
        'rh_report_dates', (SELECT count(*) FROM rh_report),
        'valid_rh_dates', (SELECT count(*) FROM actuals WHERE metric = 'rh_min'),
        'duplicate_rh_dates', (SELECT count(*) - count(DISTINCT valid_date) FROM rh_report),
        'duplicate_actual_keys', (SELECT count(*) - count(DISTINCT (valid_date, metric)) FROM actuals),
        'conflicting_captures', (
            SELECT count(*) FROM (
                SELECT valid_date, bulletin_time_hkt FROM raw GROUP BY 1, 2
                HAVING count(DISTINCT (lead_days, forecast_tmax_c, forecast_rh_min_pct, forecast_rh_max_pct)) > 1
            ) conflicts
        ),
        'bad_lead_dates', (SELECT count(*) FROM daily_latest
            WHERE lead_days BETWEEN 1 AND 9 AND valid_date - bulletin_time_hkt::date <> lead_days),
        'missing_publication_timestamps', (SELECT count(*) FROM daily_latest
            WHERE lead_days BETWEEN 1 AND 9 AND published_time_utc IS NULL),
        'publication_at_or_after_valid_start', (SELECT count(*) FROM daily_latest
            WHERE lead_days BETWEEN 1 AND 9 AND published_time_utc >=
                (valid_date::timestamp AT TIME ZONE 'Asia/Hong_Kong'))
    ) AS checks
)
SELECT metric, extract(year FROM valid_date)::integer AS year,
       jsonb_agg(jsonb_build_array(to_char(valid_date, 'YYYY-MM-DD'), lead_days, loss)
                 ORDER BY valid_date, lead_days) AS losses,
       (SELECT checks FROM audit) AS checks
FROM pairs
GROUP BY 1, 2
ORDER BY 1, 2;

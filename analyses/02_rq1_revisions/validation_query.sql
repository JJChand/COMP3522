-- Independent SQL implementation of all RQ1 numeric pairs and summaries.
WITH canonical AS (
    SELECT DISTINCT ON (f.valid_date, i.bulletin_time_hkt)
           f.valid_date, i.bulletin_time_hkt, f.lead_days,
           f.forecast_tmin_c, f.forecast_tmax_c,
           f.forecast_rh_min_pct, f.forecast_rh_max_pct
    FROM project.hko_forecast_daily f
    JOIN project.hko_forecast_issue i USING (forecast_issue_id)
    WHERE f.valid_date >= %(start)s AND f.valid_date < %(end)s
    ORDER BY f.valid_date, i.bulletin_time_hkt, f.forecast_issue_id
), numbered AS (
    SELECT *, dense_rank() OVER (ORDER BY bulletin_time_hkt) AS release_number
    FROM canonical
), daily AS (
    SELECT DISTINCT ON (valid_date, bulletin_time_hkt::date) *
    FROM numbered ORDER BY valid_date, bulletin_time_hkt::date, bulletin_time_hkt DESC
), selected AS (
    SELECT 'all_archived_pairs'::text AS scope, * FROM numbered
    UNION ALL
    SELECT 'daily_latest'::text AS scope, * FROM daily
), numeric_rows AS (
    SELECT scope, valid_date, bulletin_time_hkt, lead_days, release_number,
           v.metric, v.value
    FROM selected
    CROSS JOIN LATERAL (VALUES
        ('tmin', forecast_tmin_c), ('tmax', forecast_tmax_c),
        ('rh_min', forecast_rh_min_pct), ('rh_max', forecast_rh_max_pct)
    ) v(metric, value)
), lagged AS (
    SELECT *, lag(value) OVER w AS previous_value,
           lag(lead_days) OVER w AS previous_lead,
           lag(bulletin_time_hkt) OVER w AS previous_time,
           lag(release_number) OVER w AS previous_number
    FROM numeric_rows
    WINDOW w AS (PARTITION BY scope, valid_date, metric ORDER BY bulletin_time_hkt)
), eligible AS (
    SELECT *, value - previous_value AS revision
    FROM lagged
    WHERE lead_days BETWEEN 1 AND 9 AND previous_lead BETWEEN 1 AND 9
      AND value IS NOT NULL AND previous_value IS NOT NULL
      AND (scope <> 'daily_latest' OR bulletin_time_hkt::date - previous_time::date = 1)
), scopes AS (
    SELECT scope, metric, lead_days, valid_date, revision FROM eligible
    UNION ALL
    SELECT 'consecutive_le24h', metric, lead_days, valid_date, revision
    FROM eligible WHERE scope = 'all_archived_pairs'
      AND bulletin_time_hkt - previous_time <= INTERVAL '24 hours'
      AND release_number - previous_number = 1
)
SELECT scope, metric, lead_days, count(*) AS n_pairs,
       count(DISTINCT valid_date) AS n_target_dates,
       count(*) FILTER (WHERE revision <> 0) AS n_changed,
       avg(abs(revision)) AS mean_absolute_revision,
       100.0 * count(*) FILTER (WHERE revision <> 0) / count(*) AS revision_frequency_pct
FROM scopes GROUP BY scope, metric, lead_days ORDER BY scope, metric, lead_days;

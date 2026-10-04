-- Independent frozen calendar reference and retrospective past-day comparators.
WITH histories AS (
 SELECT s.series_code,o.observation_date,o.value_numeric,
 make_date(2000,extract(month FROM o.observation_date)::int,extract(day FROM o.observation_date)::int)-DATE '2000-01-01' ref_day
 FROM project.hko_daily_observation o JOIN project.hko_observation_series s USING(observation_series_id)
 WHERE s.series_code IN('obs_hko_daily_tmin','obs_hko_daily_tmax')
 AND o.observation_date>=DATE '1991-01-01' AND o.observation_date<%(end)s
 AND o.data_completeness='C' AND o.value_numeric IS NOT NULL
), climate AS MATERIALIZED (
 SELECT h.series_code,mod(h.ref_day+d.offset_days+366,366) AS ref_day,avg(h.value_numeric) mean_c,
 percentile_cont(0.5) WITHIN GROUP(ORDER BY h.value_numeric) median_c
 FROM histories h CROSS JOIN generate_series(-2,2) d(offset_days)
 WHERE h.observation_date<DATE '2021-01-01'
 GROUP BY h.series_code,mod(h.ref_day+d.offset_days+366,366)
), canonical AS (
 SELECT DISTINCT ON(d.valid_date,i.bulletin_time_hkt) d.*,i.bulletin_time_hkt
 FROM project.hko_forecast_daily d JOIN project.hko_forecast_issue i USING(forecast_issue_id)
 WHERE d.valid_date >= %(start)s AND d.valid_date < %(end)s
 ORDER BY d.valid_date,i.bulletin_time_hkt,d.forecast_issue_id
), selected AS (
 SELECT DISTINCT ON(valid_date,bulletin_time_hkt::date) * FROM canonical
 ORDER BY valid_date,bulletin_time_hkt::date,bulletin_time_hkt DESC,forecast_issue_id DESC
), temp AS MATERIALIZED (
 SELECT s.*,v.metric,v.forecast,v.code
 FROM selected s CROSS JOIN LATERAL (VALUES
 ('tmin',s.forecast_tmin_c,'obs_hko_daily_tmin'),('tmax',s.forecast_tmax_c,'obs_hko_daily_tmax')) v(metric,forecast,code)
 WHERE lead_days BETWEEN 1 AND 9 AND v.forecast IS NOT NULL
), joined AS (
 SELECT t.*,a.value_numeric actual,c.mean_c,c.median_c,p1.value_numeric lag1_c,p2.value_numeric lag2_c
 FROM temp t JOIN histories a ON a.series_code=t.code AND a.observation_date=t.valid_date
 JOIN climate c ON c.series_code=t.code AND c.ref_day=a.ref_day
 LEFT JOIN histories p1 ON p1.series_code=t.code AND p1.observation_date=t.bulletin_time_hkt::date-1
 LEFT JOIN histories p2 ON p2.series_code=t.code AND p2.observation_date=t.bulletin_time_hkt::date-2
), errors AS (
 SELECT j.*,v.baseline,forecast-actual forecast_error,v.reference_c-actual reference_error
 FROM joined j CROSS JOIN LATERAL (VALUES
 ('climatology_mean',mean_c),('climatology_median',median_c),('persistence_lag1',lag1_c),('persistence_lag2',lag2_c)) v(baseline,reference_c)
 WHERE reference_c IS NOT NULL
)
SELECT metric,lead_days,baseline,count(*) n_matched,avg(abs(forecast_error)) forecast_mae,
 avg(abs(reference_error)) baseline_mae,sqrt(avg(forecast_error^2)) forecast_rmse,
 sqrt(avg(reference_error^2)) baseline_rmse,
 1-avg(abs(forecast_error))/nullif(avg(abs(reference_error)),0) mae_skill,
 1-avg(forecast_error^2)/nullif(avg(reference_error^2),0) mse_skill
FROM errors GROUP BY metric,lead_days,baseline ORDER BY metric,lead_days,baseline;

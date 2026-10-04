-- Independent live SQL: canonicalize identical captures after loader conflict audit.
-- Preserve original target trajectory before lead/gap filtering.
WITH raw AS (
 SELECT d.*,i.bulletin_time_hkt,i.general_situation
 FROM project.hko_forecast_daily d JOIN project.hko_forecast_issue i USING(forecast_issue_id)
 WHERE d.valid_date >= %(start)s AND d.valid_date < %(end)s
), canonical AS (
 SELECT DISTINCT ON(valid_date,bulletin_time_hkt) * FROM raw
 ORDER BY valid_date,bulletin_time_hkt,forecast_issue_id
), times AS (
 SELECT bulletin_time_hkt, row_number() OVER(ORDER BY bulletin_time_hkt) seq
 FROM (SELECT DISTINCT bulletin_time_hkt FROM canonical) t
), selected AS (
 SELECT 'consecutive_le24h'::text scope,c.*,t.seq FROM canonical c JOIN times t USING(bulletin_time_hkt)
 UNION ALL
 SELECT 'daily_latest', c.*,t.seq FROM (
  SELECT DISTINCT ON(valid_date,bulletin_time_hkt::date) * FROM canonical
  ORDER BY valid_date,bulletin_time_hkt::date,bulletin_time_hkt DESC,forecast_issue_id DESC
 ) c JOIN times t USING(bulletin_time_hkt)
), numeric AS (
 SELECT s.*,v.metric,v.forecast FROM selected s
 CROSS JOIN LATERAL (VALUES ('tmin',forecast_tmin_c),('tmax',forecast_tmax_c),
                            ('rh_min',forecast_rh_min_pct),('rh_max',forecast_rh_max_pct)) v(metric,forecast)
), lagged AS (
 SELECT *,lag(forecast) OVER w earlier,
 lag(lead_days) OVER w earlier_lead,lag(bulletin_time_hkt) OVER w earlier_time,lag(seq) OVER w earlier_seq
 FROM numeric WINDOW w AS(PARTITION BY scope,valid_date,metric ORDER BY bulletin_time_hkt)
), pairs AS (
 SELECT * FROM lagged WHERE lead_days BETWEEN 1 AND 9 AND earlier_lead BETWEEN 1 AND 9
 AND forecast IS NOT NULL AND earlier IS NOT NULL
 AND bulletin_time_hkt>earlier_time
 AND ((scope='daily_latest' AND bulletin_time_hkt::date-earlier_time::date=1)
  OR (scope='consecutive_le24h' AND seq-earlier_seq=1 AND bulletin_time_hkt-earlier_time<=interval '24 hours'))
), observed AS (
 SELECT o.observation_date valid_date,
 CASE s.series_code WHEN 'obs_hko_daily_tmin' THEN 'tmin' WHEN 'obs_hko_daily_tmax' THEN 'tmax' END metric,
 o.value_numeric actual
 FROM project.hko_daily_observation o JOIN project.hko_observation_series s USING(observation_series_id)
 WHERE s.series_code IN('obs_hko_daily_tmin','obs_hko_daily_tmax')
 AND o.observation_date >= %(start)s AND o.observation_date < %(end)s
 AND o.data_completeness='C' AND o.value_numeric IS NOT NULL
 UNION ALL
 SELECT r.report_date,v.metric,v.actual
 FROM project.hko_multistation_report r
 CROSS JOIN LATERAL (SELECT
 CASE WHEN r.report_json->>'HKOReadingsMinRH' ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN (r.report_json->>'HKOReadingsMinRH')::numeric END lo,
 CASE WHEN r.report_json->>'HKOReadingsMaxRH' ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN (r.report_json->>'HKOReadingsMaxRH')::numeric END hi) parsed
 CROSS JOIN LATERAL (VALUES ('rh_min',parsed.lo),('rh_max',parsed.hi)) v(metric,actual)
 WHERE r.report_date >= %(start)s AND r.report_date < %(end)s
 AND r.report_json->>'ReportTimeInfoDate'=to_char(r.report_date,'YYYYMMDD')
 AND parsed.lo BETWEEN 0 AND 100 AND parsed.hi BETWEEN 0 AND 100 AND parsed.lo<=parsed.hi
), paired_actual AS (
 SELECT p.*,a.actual,abs(earlier-actual)-abs(forecast-actual) benefit
 FROM pairs p JOIN observed a ON a.valid_date=p.valid_date
 AND a.metric=p.metric
), temp_cases AS (
 SELECT n.*,a.actual,n.forecast-a.actual error,
 CASE WHEN extract(month FROM n.valid_date) IN(12,1,2) THEN 'DJF'
      WHEN extract(month FROM n.valid_date) BETWEEN 3 AND 5 THEN 'MAM'
      WHEN extract(month FROM n.valid_date) BETWEEN 6 AND 8 THEN 'JJA' ELSE 'SON' END season,
 extract(year FROM n.valid_date)::int AS target_year
 FROM numeric n JOIN observed a ON a.valid_date=n.valid_date
 AND a.metric=n.metric
 WHERE n.lead_days BETWEEN 1 AND 9 AND forecast IS NOT NULL
), psr_lagged AS (
 SELECT *,lag(psr) OVER w before_psr,lag(lead_days) OVER w previous_lead,
 lag(bulletin_time_hkt) OVER w previous_time,lag(seq) OVER w previous_seq
 FROM selected WINDOW w AS(PARTITION BY scope,valid_date ORDER BY bulletin_time_hkt)
), psr_pairs AS (
 SELECT * FROM psr_lagged WHERE lead_days BETWEEN 1 AND 9 AND previous_lead BETWEEN 1 AND 9
 AND bulletin_time_hkt>previous_time
 AND ((scope='daily_latest' AND bulletin_time_hkt::date-previous_time::date=1)
 OR (scope='consecutive_le24h' AND seq-previous_seq=1 AND bulletin_time_hkt-previous_time<=interval '24 hours'))
), answers AS (
 SELECT 2 rq,'direction' kind,scope,metric,lead_days::text dimension,
 jsonb_build_object('n_pairs',count(*),'n_increase',count(*) FILTER(WHERE forecast>earlier),
 'n_decrease',count(*) FILTER(WHERE forecast<earlier),'n_unchanged',count(*) FILTER(WHERE forecast=earlier)) result
 FROM pairs GROUP BY scope,metric,lead_days
 UNION ALL
 SELECT 2,'psr_transition',scope,before_psr,psr,
 jsonb_build_object('n_pairs',count(*)) FROM psr_pairs GROUP BY scope,before_psr,psr
 UNION ALL
 SELECT 3,'usefulness',scope,metric,denominator,
 jsonb_build_object('n_pairs',count(*),'n_improved',count(*) FILTER(WHERE benefit>0),
 'n_worsened',count(*) FILTER(WHERE benefit<0),'n_tied',count(*) FILTER(WHERE benefit=0),
 'mean_absolute_error_reduction',avg(benefit),'usefulness_rate_pct',100.0*count(*) FILTER(WHERE benefit>0)/count(*))
 FROM paired_actual CROSS JOIN LATERAL (VALUES ('all_pairs'),('changed_only')) d(denominator)
 WHERE denominator='all_pairs' OR forecast<>earlier GROUP BY scope,metric,denominator
 UNION ALL
 SELECT 4,'accuracy','daily_latest',metric,lead_days::text,
 jsonb_build_object('n',count(*),'mae',avg(abs(error)),'rmse',sqrt(avg(error*error)),'bias',avg(error))
 FROM temp_cases WHERE scope='daily_latest' GROUP BY metric,lead_days
 UNION ALL
 SELECT 5,'bias_overall','daily_latest',metric,'overall',jsonb_build_object('n_forecasts',count(*),CASE WHEN metric LIKE 'rh_%%' THEN 'mean_error_pp' ELSE 'mean_error_c' END,avg(error))
 FROM temp_cases WHERE scope='daily_latest' GROUP BY metric
 UNION ALL
 SELECT 5,'bias_season','daily_latest',metric,season,jsonb_build_object('n_forecasts',count(*),CASE WHEN metric LIKE 'rh_%%' THEN 'mean_error_pp' ELSE 'mean_error_c' END,avg(error))
 FROM temp_cases WHERE scope='daily_latest' GROUP BY metric,season
 UNION ALL
 SELECT 5,'bias_year','daily_latest',metric,target_year::text,jsonb_build_object('n_forecasts',count(*),CASE WHEN metric LIKE 'rh_%%' THEN 'mean_error_pp' ELSE 'mean_error_c' END,avg(error))
 FROM temp_cases WHERE scope='daily_latest' GROUP BY metric,target_year
)
SELECT * FROM answers ORDER BY rq,kind,scope,metric,dimension;

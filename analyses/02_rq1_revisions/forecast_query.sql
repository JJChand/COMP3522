-- All archived vintages, bounded by target date. Issue time is HKT, not retrieval time.
SELECT f.forecast_issue_id, i.source_file_id, s.relative_path,
       i.bulletin_time_hkt, i.title, i.published_time_utc,
       f.valid_date, f.lead_days,
       f.forecast_tmin_c, f.forecast_tmax_c,
       f.forecast_rh_min_pct, f.forecast_rh_max_pct,
       f.psr, f.wind, f.weather
FROM project.hko_forecast_daily AS f
JOIN project.hko_forecast_issue AS i USING (forecast_issue_id)
JOIN project.hko_source_file AS s USING (source_file_id)
WHERE f.valid_date >= %(start)s AND f.valid_date < %(end)s
ORDER BY f.valid_date, i.bulletin_time_hkt, f.forecast_issue_id;

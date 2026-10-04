-- Temperature history supports a frozen 1991-2020 climatology and past-day baselines.
-- Other elements are restricted to the study period. Preserve nonnumeric markers.
SELECT o.observation_series_id, o.observation_date, o.value_numeric, o.value_text,
       o.data_completeness, s.series_code, s.station_name, s.metric_name,
       s.unit, s.title_en, s.source_file_id, p.relative_path
FROM project.hko_daily_observation o
JOIN project.hko_observation_series s USING (observation_series_id)
JOIN project.hko_source_file p USING (source_file_id)
WHERE o.observation_date < %(end)s
  AND ((s.series_code IN ('obs_hko_daily_tmax', 'obs_hko_daily_tmin')
        AND o.observation_date >= %(history_start)s)
    OR (s.series_code = ANY(%(study_codes)s)
        AND o.observation_date >= %(start)s))
ORDER BY o.observation_series_id, o.observation_date;

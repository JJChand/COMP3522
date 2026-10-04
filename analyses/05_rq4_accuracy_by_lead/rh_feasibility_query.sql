-- Read-only measurement availability; do not confuse forecasts with observations.
WITH catalog AS (
 SELECT s.*,f.relative_path
 FROM project.hko_observation_series s JOIN project.hko_source_file f USING(source_file_id)
), humidity AS (
 SELECT * FROM catalog
 WHERE lower(concat_ws(' ',series_code,title_en,metric_name)) ~ '(humid|relative.humidity|(^|[^a-z])rh([^a-z]|$))'
), obs AS (
 SELECT s.observation_series_id,count(*) n_rows,
 count(*) FILTER(WHERE o.value_numeric IS NOT NULL AND o.data_completeness='C') n_complete_numeric,
 min(o.observation_date) first_date,max(o.observation_date) last_date
 FROM humidity s JOIN project.hko_daily_observation o USING(observation_series_id)
 WHERE o.observation_date >= %(start)s AND o.observation_date < %(end)s
 GROUP BY s.observation_series_id
), reports AS (
 SELECT report_date,report_json FROM project.hko_multistation_report
 WHERE report_date >= %(start)s AND report_date < %(end)s
), report_keys AS (
 SELECT k.key field_name,count(*) n_reports
 FROM reports r CROSS JOIN LATERAL jsonb_object_keys(r.report_json) k(key)
 GROUP BY k.key
)
SELECT jsonb_build_object(
 'observation_catalog_series_count',(SELECT count(*) FROM catalog),
 'humidity_series',coalesce((SELECT jsonb_agg(to_jsonb(s)||coalesce(to_jsonb(o)-'observation_series_id','{}'::jsonb)
     ORDER BY s.observation_series_id) FROM humidity s LEFT JOIN obs o USING(observation_series_id)),'[]'::jsonb),
 'daily_report_count',(SELECT count(*) FROM reports),
 'distinct_report_dates',(SELECT count(DISTINCT report_date) FROM reports),
 'report_field_inventory',coalesce((SELECT jsonb_agg(to_jsonb(k) ORDER BY field_name) FROM report_keys k),'[]'::jsonb),
 'humidity_candidate_report_fields',coalesce((SELECT jsonb_agg(to_jsonb(k) ORDER BY field_name)
     FROM report_keys k WHERE lower(field_name) ~ '(humid|relative|rh)'),'[]'::jsonb),
 'humidity_source_csvs',coalesce((SELECT jsonb_agg(jsonb_build_object('source_file_id',f.source_file_id,
       'relative_path',f.relative_path,'imported_series_id',s.observation_series_id) ORDER BY f.source_file_id)
     FROM project.hko_source_file f LEFT JOIN project.hko_observation_series s USING(source_file_id)
     WHERE f.source_kind='observation_csv' AND lower(f.relative_path) ~ '(humid|relative|rh)'),'[]'::jsonb)
) AS evidence;

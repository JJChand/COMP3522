-- Bounded source-definition check, not a rainfall event-label substitution.
SELECT r.report_id, r.source_file_id, r.report_date,
       r.report_json->>'HKOReadingsRainfall' AS rainfall_text,
       r.report_json->>'HKOReadingsAccumRainfall' AS accumulated_text,
       r.report_json->>'HKOReadingsAvgRainfall' AS average_text,
       (SELECT jsonb_object_agg(e.key, e.value)
        FROM jsonb_each_text(r.report_json) AS e(key, value)
        WHERE e.key ILIKE '%%rain%%') AS rainfall_fields,
       f.relative_path AS source_relative_path
FROM project.hko_multistation_report AS r
JOIN project.hko_source_file AS f USING (source_file_id)
WHERE r.report_date >= %(start)s AND r.report_date < %(end)s
ORDER BY r.report_date, r.report_id;

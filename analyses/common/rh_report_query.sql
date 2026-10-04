-- Field meanings and date alignment must be audited before endpoint scoring.
SELECT r.report_id,r.source_file_id,r.report_date,r.bulletin_date,r.bulletin_time,
       r.report_json->>'ReportTimeInfoDate' AS source_observation_date,
       r.report_json->>'HKOReadingsMinRH' AS observed_rh_min_text,
       r.report_json->>'HKOReadingsMaxRH' AS observed_rh_max_text,
       r.report_json->>'HKOReadingsMinTemp' AS observed_tmin_text,
       r.report_json->>'HKOReadingsMaxTemp' AS observed_tmax_text,
       r.report_json->>'NoteDesc' AS source_note,
       r.report_json->>'NoteDesc3' AS source_quality_note,
       f.relative_path AS source_relative_path
FROM project.hko_multistation_report r JOIN project.hko_source_file f USING(source_file_id)
WHERE r.report_date >= %(start)s AND r.report_date < %(end)s
ORDER BY r.report_date,r.report_id;

-- Aggregate retained report footnotes: detect RH measurement-definition changes.
SELECT v.field_name,v.note,count(*) AS n_reports,
       min(r.report_date) AS first_report_date,max(r.report_date) AS last_report_date
FROM project.hko_multistation_report r
CROSS JOIN LATERAL (VALUES
 ('NoteDesc',r.report_json->>'NoteDesc'),('NoteDesc1',r.report_json->>'NoteDesc1'),
 ('NoteDesc2',r.report_json->>'NoteDesc2'),('NoteDesc3',r.report_json->>'NoteDesc3')) v(field_name,note)
WHERE r.report_date >= %(start)s AND r.report_date < %(end)s
AND nullif(btrim(v.note),'') IS NOT NULL
GROUP BY v.field_name,v.note ORDER BY first_report_date,v.field_name;

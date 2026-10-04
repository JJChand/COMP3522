# COMP3522 repository instructions

Read `DATABASE_AGENT_GUIDE.md` before database work. Use the repository-root
`.env` for connections; never print or commit credentials. Database operations
are read-only unless the user authorizes changes.

## Required schema-documentation maintenance

Whenever you modify the database, update `DATABASE_AGENT_GUIDE.md` in the same task.
Inspect the committed live catalog rather than documenting only planned SQL.
For schema changes, record tables/views, column types and nullability,
constraints, indexes and joins, plus interpretation or usage changes.
For data-only imports, refresh the documented import status.
Do not call the task complete until documentation matches the committed state.
If a partial import or documentation refresh fails, report the committed scope
and the documentation gap explicitly. This rule does not authorize DB writes.

Refresh the guide's generated live snapshot with:

```powershell
.\.venv\Scripts\python.exe data_management/model_forecasts/schema_document.py
```

`DATABASE_AGENT_GUIDE.md` is the single schema reference. Keep human
interpretation outside its generated live-snapshot section. Do not create a
separate schema document or include credentials or raw datasets in the guide.

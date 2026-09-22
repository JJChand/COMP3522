[CmdletBinding()]
param(
    [datetime] $StartDate = [datetime] '2022-01-01',
    [datetime] $EndDate = [datetime] '2022-01-08',
    [ValidateRange(1, 100000)]
    [int] $Limit = 100,
    [string] $OutputDirectory = (Join-Path $PSScriptRoot 'results'),
    [string] $PsqlPath,
    [string] $EnvFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($EndDate -le $StartDate) {
    throw '-EndDate must be later than -StartDate.'
}

$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repositoryRoot '.env'
}

function Import-PostgresEnvFile {
    param([string] $Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }

    $allowedNames = @('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')
    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $Path) {
        $lineNumber++
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }

        if ($trimmed -notmatch '^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            throw "Invalid .env syntax at line $lineNumber in $Path"
        }

        $name = $Matches[1]
        if ($name -notin $allowedNames) {
            continue
        }

        $value = $Matches[2].Trim()
        if ($value.Length -ge 2) {
            $first = $value[0]
            $last = $value[$value.Length - 1]
            if (($first -eq '"' -and $last -eq '"') -or
                ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        $existing = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ([string]::IsNullOrWhiteSpace($existing)) {
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

Import-PostgresEnvFile -Path $EnvFile

foreach ($variableName in @('PGUSER', 'PGPASSWORD')) {
    $value = [Environment]::GetEnvironmentVariable($variableName)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Missing required environment variable: $variableName"
    }
}

if (-not (Test-Path Env:PGHOST)) {
    $env:PGHOST = 'localhost'
}
if (-not (Test-Path Env:PGPORT)) {
    $env:PGPORT = '5432'
}
if (-not (Test-Path Env:PGDATABASE)) {
    $env:PGDATABASE = 'course_project'
}

function Resolve-PsqlPath {
    param([string] $RequestedPath)

    if ($RequestedPath) {
        return (Resolve-Path -LiteralPath $RequestedPath).Path
    }

    $command = Get-Command 'psql.exe' -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    foreach ($candidate in @(
        'D:\PostgreSQL\bin\psql.exe',
        'C:\Program Files\PostgreSQL\17\bin\psql.exe'
    )) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw 'psql.exe was not found. Install PostgreSQL client tools or pass -PsqlPath.'
}

$PsqlPath = Resolve-PsqlPath -RequestedPath $PsqlPath
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$startIso = $StartDate.ToString('yyyy-MM-dd')
$endIso = $EndDate.ToString('yyyy-MM-dd')
$psqlVariables = @(
    '-v', "start_date=$startIso",
    '-v', "end_date=$endIso",
    '-v', "row_limit=$Limit",
    '-v', 'tmax_series=obs_hko_daily_tmax',
    '-v', 'tmin_series=obs_hko_daily_tmin'
)

function Invoke-ReadOnlyCsvQuery {
    param(
        [Parameter(Mandatory)] [string] $Query,
        [Parameter(Mandatory)] [string] $OutputPath
    )

    $arguments = @(
        '-X',
        '--no-password',
        '--csv',
        '--set', 'ON_ERROR_STOP=1',
        '--host', $env:PGHOST,
        '--port', $env:PGPORT,
        '--dbname', $env:PGDATABASE,
        '--username', $env:PGUSER
    ) + $script:psqlVariables + @('--file=-')

    $output = $Query | & $script:PsqlPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "psql failed with exit code $LASTEXITCODE while creating $OutputPath"
    }

    $records = @($output | ConvertFrom-Csv)
    if ($records.Count -eq 0) {
        throw "Query returned no rows; refusing to write empty $OutputPath"
    }

    $output | Set-Content -LiteralPath $OutputPath -Encoding utf8
    return $records.Count
}

$connectionCheckSql = @'
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    current_setting('search_path') AS search_path,
    PostGIS_Full_Version() AS postgis_version;
'@

$tableCountsSql = @'
SELECT 'source files' AS object_name, count(*) AS row_count
FROM project.hko_source_file
UNION ALL
SELECT 'forecast issues', count(*) FROM project.hko_forecast_issue
UNION ALL
SELECT 'forecast days', count(*) FROM project.hko_forecast_daily
UNION ALL
SELECT 'observation series', count(*) FROM project.hko_observation_series
UNION ALL
SELECT 'daily observations', count(*) FROM project.hko_daily_observation
UNION ALL
SELECT 'multistation reports', count(*) FROM project.hko_multistation_report
UNION ALL
SELECT 'stations', count(*) FROM project.hko_station
ORDER BY object_name;
'@

$temperatureSampleSql = @'
WITH actual_tmax AS (
    SELECT
        observation_date AS valid_date,
        value_numeric AS observed_tmax_c,
        value_text AS observed_tmax_text,
        data_completeness AS tmax_data_completeness,
        source_relative_path AS tmax_source_relative_path
    FROM project.v_hko_daily_observation
    WHERE series_code = :'tmax_series'
      AND observation_date >= :'start_date'::date
      AND observation_date < :'end_date'::date
),
actual_tmin AS (
    SELECT
        observation_date AS valid_date,
        value_numeric AS observed_tmin_c,
        value_text AS observed_tmin_text,
        data_completeness AS tmin_data_completeness,
        source_relative_path AS tmin_source_relative_path
    FROM project.v_hko_daily_observation
    WHERE series_code = :'tmin_series'
      AND observation_date >= :'start_date'::date
      AND observation_date < :'end_date'::date
)
SELECT
    i.forecast_issue_id,
    i.bulletin_time_hkt,
    f.valid_date,
    f.lead_days,
    f.forecast_tmax_c,
    tx.observed_tmax_c,
    f.forecast_tmax_c - tx.observed_tmax_c AS tmax_error_c,
    f.forecast_tmin_c,
    tn.observed_tmin_c,
    f.forecast_tmin_c - tn.observed_tmin_c AS tmin_error_c,
    tx.observed_tmax_text,
    tn.observed_tmin_text,
    tx.tmax_data_completeness,
    tn.tmin_data_completeness,
    sf.relative_path AS forecast_source_relative_path,
    tx.tmax_source_relative_path,
    tn.tmin_source_relative_path
FROM project.hko_forecast_daily AS f
JOIN project.hko_forecast_issue AS i
  ON i.forecast_issue_id = f.forecast_issue_id
JOIN project.hko_source_file AS sf
  ON sf.source_file_id = i.source_file_id
LEFT JOIN actual_tmax AS tx
  ON tx.valid_date = f.valid_date
LEFT JOIN actual_tmin AS tn
  ON tn.valid_date = f.valid_date
WHERE f.valid_date >= :'start_date'::date
  AND f.valid_date < :'end_date'::date
  AND f.lead_days BETWEEN 1 AND 9
ORDER BY i.bulletin_time_hkt, f.valid_date
LIMIT :row_limit;
'@

$previousPgOptions = if (Test-Path Env:PGOPTIONS) { $env:PGOPTIONS } else { $null }
$env:PGOPTIONS = '-c default_transaction_read_only=on'

try {
    $rowCounts = [ordered]@{
        'connection_check.csv' = Invoke-ReadOnlyCsvQuery `
            -Query $connectionCheckSql `
            -OutputPath (Join-Path $OutputDirectory 'connection_check.csv')
        'table_counts.csv' = Invoke-ReadOnlyCsvQuery `
            -Query $tableCountsSql `
            -OutputPath (Join-Path $OutputDirectory 'table_counts.csv')
        'forecast_temperature_sample.csv' = Invoke-ReadOnlyCsvQuery `
            -Query $temperatureSampleSql `
            -OutputPath (Join-Path $OutputDirectory 'forecast_temperature_sample.csv')
    }

    $metadata = [ordered]@{
        generated_at_utc = [datetime]::UtcNow.ToString('o')
        start_date_inclusive = $startIso
        end_date_exclusive = $endIso
        lead_days = @(1, 9)
        requested_sample_limit = $Limit
        series_codes = @('obs_hko_daily_tmax', 'obs_hko_daily_tmin')
        row_counts = $rowCounts
    }
    $metadata | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $OutputDirectory 'run_metadata.json') -Encoding utf8
}
finally {
    if ($null -eq $previousPgOptions) {
        Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
    }
    else {
        $env:PGOPTIONS = $previousPgOptions
    }
}

Write-Host "Fetch succeeded. Results: $OutputDirectory"
foreach ($entry in $rowCounts.GetEnumerator()) {
    Write-Host "  $($entry.Key): $($entry.Value) row(s)"
}

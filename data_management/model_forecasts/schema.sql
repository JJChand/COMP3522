-- Run only through the import command, inside its transaction.
-- New external-model tables; existing HKO tables remain the reference sources.
CREATE TABLE IF NOT EXISTS project.external_model_source (
    source_id uuid PRIMARY KEY,
    provider text NOT NULL,
    model text NOT NULL,
    product text NOT NULL,
    run_time_utc timestamptz NOT NULL,
    forecast_hour integer NOT NULL CHECK (forecast_hour >= 0),
    source_url text NOT NULL,
    index_url text NOT NULL,
    retrieved_at_utc timestamptz NOT NULL,
    subset_relative_path text NOT NULL,
    subset_sha256 text NOT NULL CHECK (length(subset_sha256) = 64),
    subset_size_bytes bigint NOT NULL CHECK (subset_size_bytes > 0),
    manifest jsonb NOT NULL,
    imported_at_utc timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_url, subset_sha256)
);

CREATE TABLE IF NOT EXISTS project.external_model_temperature (
    source_id uuid NOT NULL REFERENCES project.external_model_source(source_id),
    station_code text NOT NULL REFERENCES project.hko_station(station_code),
    message_number integer NOT NULL CHECK (message_number > 0),
    parameter_id integer NOT NULL,
    short_name text NOT NULL,
    parameter_name text NOT NULL,
    step_type text NOT NULL,
    interval_start_utc timestamptz NOT NULL,
    valid_time_utc timestamptz NOT NULL,
    target_latitude double precision NOT NULL,
    target_longitude double precision NOT NULL,
    grid_latitude double precision NOT NULL,
    grid_longitude double precision NOT NULL,
    grid_distance_km double precision NOT NULL CHECK (grid_distance_km >= 0),
    extraction_method text NOT NULL CHECK (extraction_method = 'nearest_grid_point'),
    source_value double precision NOT NULL,
    source_unit text NOT NULL,
    temperature_c double precision NOT NULL,
    PRIMARY KEY (source_id, station_code, message_number),
    CHECK (interval_start_utc <= valid_time_utc)
);

CREATE INDEX IF NOT EXISTS external_model_temperature_valid_time_idx
ON project.external_model_temperature (valid_time_utc, station_code);
CREATE INDEX IF NOT EXISTS external_model_source_run_time_idx
ON project.external_model_source (model, run_time_utc, forecast_hour);

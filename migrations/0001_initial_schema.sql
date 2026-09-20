BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TYPE equipment_class AS ENUM (
    'dump_truck',
    'excavator',
    'road_roller',
    'loader_crane',
    'concrete_mixer',
    'bulldozer',
    'truck',
    'mobile_crane',
    'tower_crane',
    'piling_rig'
);

CREATE TYPE observation_source AS ENUM (
    'upload',
    'camera_snapshot',
    'rtsp_frame',
    'synthetic'
);

CREATE TYPE observation_status AS ENUM (
    'queued',
    'processing',
    'analyzed',
    'rejected'
);

CREATE TYPE rule_expectation AS ENUM ('required', 'optional', 'unexpected');
CREATE TYPE deviation_kind AS ENUM (
    'missing_required_equipment',
    'unexpected_equipment',
    'count_outside_range',
    'insufficient_evidence',
    'schedule_conflict'
);
CREATE TYPE deviation_severity AS ENUM ('info', 'warning', 'critical');
CREATE TYPE deviation_status AS ENUM ('open', 'acknowledged', 'resolved', 'dismissed');

CREATE TABLE projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    object_type text NOT NULL CHECK (length(trim(object_type)) BETWEEN 1 AND 100),
    timezone text NOT NULL DEFAULT 'Europe/Moscow',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE zones (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code text NOT NULL,
    name text NOT NULL,
    boundary geometry(Polygon, 4326),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, code)
);

CREATE TABLE cameras (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    zone_id uuid REFERENCES zones(id) ON DELETE SET NULL,
    code text NOT NULL,
    name text NOT NULL,
    source_uri_secret_ref text,
    location geometry(Point, 4326),
    coverage geometry(Polygon, 4326),
    calibration jsonb NOT NULL DEFAULT '{}'::jsonb,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, code),
    CHECK (jsonb_typeof(calibration) = 'object')
);

CREATE TABLE work_stages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    zone_id uuid NOT NULL REFERENCES zones(id) ON DELETE RESTRICT,
    parent_id uuid REFERENCES work_stages(id) ON DELETE RESTRICT,
    code text NOT NULL,
    name text NOT NULL,
    planned_start timestamptz NOT NULL,
    planned_end timestamptz NOT NULL,
    planned_period tstzrange GENERATED ALWAYS AS (
        tstzrange(planned_start, planned_end, '[)')
    ) STORED,
    observable_from_camera boolean NOT NULL DEFAULT false,
    source_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, zone_id, code),
    CHECK (planned_end > planned_start),
    CHECK (jsonb_typeof(source_payload) = 'object')
);

CREATE TABLE equipment_rules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stage_id uuid NOT NULL REFERENCES work_stages(id) ON DELETE CASCADE,
    equipment equipment_class NOT NULL,
    expectation rule_expectation NOT NULL,
    min_count integer NOT NULL DEFAULT 0 CHECK (min_count >= 0),
    max_count integer CHECK (max_count IS NULL OR max_count >= min_count),
    min_confidence real NOT NULL DEFAULT 0.60 CHECK (min_confidence BETWEEN 0 AND 1),
    persistence_frames integer NOT NULL DEFAULT 3 CHECK (persistence_frames > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (stage_id, equipment, expectation)
);

CREATE TABLE media_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket text NOT NULL,
    object_key text NOT NULL,
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    media_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    width_px integer NOT NULL CHECK (width_px > 0),
    height_px integer NOT NULL CHECK (height_px > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (bucket, object_key),
    UNIQUE (sha256)
);

CREATE TABLE observations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    camera_id uuid NOT NULL REFERENCES cameras(id) ON DELETE RESTRICT,
    zone_id uuid NOT NULL REFERENCES zones(id) ON DELETE RESTRICT,
    asset_id uuid NOT NULL REFERENCES media_assets(id) ON DELETE RESTRICT,
    source observation_source NOT NULL,
    status observation_status NOT NULL DEFAULT 'queued',
    captured_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    analyzed_at timestamptz,
    idempotency_key uuid NOT NULL,
    correlation_id uuid NOT NULL,
    rejection_reason text,
    UNIQUE (project_id, idempotency_key),
    CHECK (status <> 'analyzed' OR analyzed_at IS NOT NULL)
);

CREATE TABLE detections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    observation_id uuid NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    equipment equipment_class NOT NULL,
    confidence real NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    x_min real NOT NULL CHECK (x_min BETWEEN 0 AND 1),
    y_min real NOT NULL CHECK (y_min BETWEEN 0 AND 1),
    x_max real NOT NULL CHECK (x_max BETWEEN 0 AND 1),
    y_max real NOT NULL CHECK (y_max BETWEEN 0 AND 1),
    model_version text NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (x_min < x_max AND y_min < y_max),
    CHECK (jsonb_typeof(attributes) = 'object')
);

CREATE TABLE deviations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    stage_id uuid NOT NULL REFERENCES work_stages(id) ON DELETE RESTRICT,
    zone_id uuid NOT NULL REFERENCES zones(id) ON DELETE RESTRICT,
    kind deviation_kind NOT NULL,
    severity deviation_severity NOT NULL,
    status deviation_status NOT NULL DEFAULT 'open',
    title text NOT NULL,
    explanation text NOT NULL,
    rule_snapshot jsonb NOT NULL,
    expected_snapshot jsonb NOT NULL,
    observed_snapshot jsonb NOT NULL,
    fingerprint char(64) NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    first_detected_at timestamptz NOT NULL,
    last_detected_at timestamptz NOT NULL,
    acknowledged_at timestamptz,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, fingerprint),
    CHECK (last_detected_at >= first_detected_at),
    CHECK (jsonb_typeof(rule_snapshot) = 'object'),
    CHECK (jsonb_typeof(expected_snapshot) IN ('array', 'object')),
    CHECK (jsonb_typeof(observed_snapshot) IN ('array', 'object'))
);

CREATE TABLE deviation_evidence (
    deviation_id uuid NOT NULL REFERENCES deviations(id) ON DELETE CASCADE,
    observation_id uuid NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    asset_id uuid NOT NULL REFERENCES media_assets(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (deviation_id, observation_id)
);

CREATE TABLE outbox_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    event_type text NOT NULL,
    subject text NOT NULL,
    payload jsonb NOT NULL,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error text,
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX zones_boundary_gix ON zones USING gist (boundary);
CREATE INDEX cameras_location_gix ON cameras USING gist (location);
CREATE INDEX cameras_coverage_gix ON cameras USING gist (coverage);
CREATE INDEX work_stages_active_idx ON work_stages USING gist (project_id, zone_id, planned_period);
CREATE INDEX observations_timeline_idx ON observations (project_id, zone_id, captured_at DESC);
CREATE INDEX observations_processing_idx ON observations (status, received_at)
    WHERE status IN ('queued', 'processing');
CREATE INDEX detections_observation_idx ON detections (observation_id, equipment, confidence DESC);
CREATE INDEX deviations_open_idx ON deviations (project_id, severity, last_detected_at DESC)
    WHERE status IN ('open', 'acknowledged');
CREATE INDEX outbox_unpublished_idx ON outbox_events (created_at)
    WHERE published_at IS NULL;

CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER zones_updated_at BEFORE UPDATE ON zones
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER cameras_updated_at BEFORE UPDATE ON cameras
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER work_stages_updated_at BEFORE UPDATE ON work_stages
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER equipment_rules_updated_at BEFORE UPDATE ON equipment_rules
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER deviations_updated_at BEFORE UPDATE ON deviations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;

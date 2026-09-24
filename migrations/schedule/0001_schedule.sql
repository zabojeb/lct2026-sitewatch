BEGIN;

CREATE TABLE schedule_revisions (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    request_sha256 char(64) NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    timezone text NOT NULL CHECK (length(trim(timezone)) BETWEEN 1 AND 100),
    source text NOT NULL CHECK (length(trim(source)) BETWEEN 1 AND 1000),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, idempotency_key),
    UNIQUE (project_id, id)
);

CREATE TABLE work_stages (
    id uuid PRIMARY KEY,
    revision_id uuid NOT NULL REFERENCES schedule_revisions(id) ON DELETE RESTRICT,
    code text NOT NULL,
    parent_code text,
    name text NOT NULL,
    zone_code text NOT NULL,
    planned_start timestamptz NOT NULL,
    planned_end timestamptz NOT NULL,
    observable_from_camera boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (revision_id, zone_code, code),
    CHECK (planned_end > planned_start)
);

CREATE TABLE equipment_rules (
    stage_id uuid NOT NULL REFERENCES work_stages(id) ON DELETE RESTRICT,
    equipment_class text NOT NULL,
    expectation text NOT NULL CHECK (expectation IN ('required', 'optional', 'unexpected')),
    min_count integer NOT NULL CHECK (min_count >= 0),
    max_count integer CHECK (max_count IS NULL OR max_count >= min_count),
    min_confidence real NOT NULL CHECK (min_confidence BETWEEN 0 AND 1),
    persistence_frames integer NOT NULL CHECK (persistence_frames > 0),
    source text NOT NULL CHECK (length(trim(source)) BETWEEN 1 AND 1000),
    PRIMARY KEY (stage_id, equipment_class)
);

CREATE TABLE active_schedule_revisions (
    project_id uuid PRIMARY KEY,
    revision_id uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (project_id, revision_id) REFERENCES schedule_revisions(project_id, id)
);

CREATE TABLE outbox_events (
    id uuid PRIMARY KEY,
    subject text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error text
);

CREATE INDEX schedule_revisions_project_created_idx
    ON schedule_revisions (project_id, created_at DESC);
CREATE INDEX work_stages_revision_idx ON work_stages (revision_id, zone_code, planned_start);
CREATE INDEX outbox_unpublished_idx ON outbox_events (created_at)
    WHERE published_at IS NULL;

COMMIT;

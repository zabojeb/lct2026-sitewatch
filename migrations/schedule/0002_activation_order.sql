BEGIN;

ALTER TABLE schedule_revisions ADD COLUMN activation_version bigint;
WITH ranked AS (
    SELECT id, row_number() OVER (PARTITION BY project_id ORDER BY created_at, id) AS version
    FROM schedule_revisions
)
UPDATE schedule_revisions AS revision
SET activation_version = ranked.version
FROM ranked WHERE ranked.id = revision.id;
ALTER TABLE schedule_revisions
    ADD CONSTRAINT schedule_revision_activation_version_positive CHECK (activation_version > 0),
    ADD CONSTRAINT schedule_revision_project_version_unique UNIQUE (project_id, activation_version);

ALTER TABLE active_schedule_revisions ADD COLUMN version bigint;
UPDATE active_schedule_revisions AS active
SET version = revision.activation_version
FROM schedule_revisions AS revision WHERE revision.id = active.revision_id;
ALTER TABLE active_schedule_revisions
    ALTER COLUMN version SET NOT NULL,
    ADD CONSTRAINT active_schedule_version_positive CHECK (version > 0);

CREATE FUNCTION schedule_revision_requires_activation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM schedule_revisions WHERE id = NEW.id AND activation_version IS NULL) THEN
        RAISE EXCEPTION 'schedule revision must be activated before commit';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER schedule_revision_activation_guard
AFTER INSERT OR UPDATE ON schedule_revisions
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION schedule_revision_requires_activation();

COMMIT;

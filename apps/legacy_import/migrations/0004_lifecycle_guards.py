"""Canonical identity, per-run observations and PostgreSQL lifecycle guards."""

import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

_TOKEN_VALIDATOR = django.core.validators.RegexValidator(
    message="Yalnız kiçik hərf, rəqəm, nöqtə, alt xətt və defis istifadə edilə bilər.",
    regex="^[a-z0-9][a-z0-9._-]*$",
)
_SHA256_VALIDATOR = django.core.validators.RegexValidator(
    message="Dəyər kiçik hərfli 64 simvolluq SHA-256 hex digest olmalıdır.",
    regex="^[0-9a-f]{64}$",
)
_OPAQUE_KEY_VALIDATOR = django.core.validators.RegexValidator(
    message="Açar yalnız opaque identifikator simvollarından ibarət olmalıdır.",
    regex="^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$",
)
_MODEL_LABEL_VALIDATOR = django.core.validators.RegexValidator(
    message="Target model etiketi app_label.model_name formatında olmalıdır.",
    regex="^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$",
)


_FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION legacy_import_run_identity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    observed_migrated bigint;
    observed_skipped bigint;
    observed_quarantined bigint;
    blocking_issues bigint;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'pending'
           OR NEW.started_at IS NOT NULL
           OR NEW.finished_at IS NOT NULL
           OR NEW.migrated_count <> 0
           OR NEW.skipped_count <> 0
           OR NEW.quarantined_count <> 0
           OR NEW.failure_code <> ''
        THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy migration run pristine pending kimi yaradılmalıdır';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.source_system IS DISTINCT FROM OLD.source_system
       OR NEW.snapshot_sha256 IS DISTINCT FROM OLD.snapshot_sha256
       OR NEW.snapshot_size_bytes IS DISTINCT FROM OLD.snapshot_size_bytes
       OR NEW.source_row_count IS DISTINCT FROM OLD.source_row_count
       OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
       OR NEW.transform_version IS DISTINCT FROM OLD.transform_version
       OR NEW.mode IS DISTINCT FROM OLD.mode
       OR NEW.origin IS DISTINCT FROM OLD.origin
       OR NEW.initiated_by_id IS DISTINCT FROM OLD.initiated_by_id
    THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy migration run identity dəyişdirilə bilməz';
    END IF;

    IF OLD.status = 'pending' THEN
        IF OLD.started_at IS NOT NULL
           OR OLD.finished_at IS NOT NULL
           OR OLD.migrated_count <> 0
           OR OLD.skipped_count <> 0
           OR OLD.quarantined_count <> 0
           OR OLD.failure_code <> ''
           OR NEW.status <> 'running'
           OR NEW.started_at IS NULL
           OR NEW.started_at < OLD.created_at
           OR NEW.finished_at IS NOT NULL
           OR NEW.migrated_count <> 0
           OR NEW.skipped_count <> 0
           OR NEW.quarantined_count <> 0
           OR NEW.failure_code <> ''
        THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy migration pending-running keçidi etibarsızdır';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.status = 'running' THEN
        IF OLD.started_at IS NULL
           OR OLD.finished_at IS NOT NULL
           OR OLD.migrated_count <> 0
           OR OLD.skipped_count <> 0
           OR OLD.quarantined_count <> 0
           OR OLD.failure_code <> ''
           OR NEW.status NOT IN ('succeeded', 'failed', 'cancelled')
           OR NEW.started_at IS DISTINCT FROM OLD.started_at
           OR NEW.finished_at IS NULL
           OR NEW.finished_at < NEW.started_at
        THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy migration running-terminal keçidi etibarsızdır';
        END IF;

        SELECT
            COUNT(*) FILTER (WHERE state = 'migrated'),
            COUNT(*) FILTER (WHERE state = 'skipped'),
            COUNT(*) FILTER (WHERE state = 'quarantined')
        INTO observed_migrated, observed_skipped, observed_quarantined
        FROM public.legacy_import_legacyentityobservation
        WHERE run_id = OLD.id;

        IF NEW.migrated_count <> observed_migrated
           OR NEW.skipped_count <> observed_skipped
           OR NEW.quarantined_count <> observed_quarantined
           OR NEW.migrated_count + NEW.skipped_count + NEW.quarantined_count
                > NEW.source_row_count
        THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy migration terminal sayları observation ledger ilə uyğun deyil';
        END IF;

        IF NEW.status = 'succeeded' THEN
            IF NEW.failure_code <> ''
               OR NEW.migrated_count + NEW.skipped_count + NEW.quarantined_count
                    <> NEW.source_row_count
            THEN
                RAISE EXCEPTION USING ERRCODE = '23514',
                    MESSAGE = 'legacy migration success invariant-i pozulub';
            END IF;
            SELECT COUNT(*) INTO blocking_issues
            FROM public.legacy_import_legacymigrationissue
            WHERE run_id = OLD.id
              AND severity IN ('error', 'critical')
              AND review_status NOT IN ('resolved', 'waived');
            IF blocking_issues <> 0 THEN
                RAISE EXCEPTION USING ERRCODE = '23514',
                    MESSAGE = 'legacy migration success üçün bloklayıcı issue mövcuddur';
            END IF;
        ELSIF NEW.failure_code = '' THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy migration non-success terminal kod tələb edir';
        END IF;
        RETURN NEW;
    END IF;

    RAISE EXCEPTION USING ERRCODE = '23514',
        MESSAGE = 'terminal legacy migration run dəyişdirilə bilməz';
END;
$$;

CREATE OR REPLACE FUNCTION legacy_import_map_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    run_row record;
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.id IS DISTINCT FROM OLD.id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.source_system IS DISTINCT FROM OLD.source_system
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
        OR NEW.legacy_pk IS DISTINCT FROM OLD.legacy_pk
        OR NEW.created_run_id IS DISTINCT FROM OLD.created_run_id
        OR NEW.source_row_hash IS DISTINCT FROM OLD.source_row_hash
        OR NEW.transform_version IS DISTINCT FROM OLD.transform_version
        OR NEW.target_model_label IS DISTINCT FROM OLD.target_model_label
        OR NEW.target_pk IS DISTINCT FROM OLD.target_pk
        OR NEW.state IS DISTINCT FROM OLD.state
        OR NEW.reconciliation_status IS DISTINCT FROM OLD.reconciliation_status
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'canonical legacy entity mapping dəyişdirilə bilməz';
    END IF;

    SELECT run.organization_id, run.source_system, run.transform_version, run.status
    INTO run_row
    FROM public.legacy_import_legacymigrationrun AS run
    WHERE run.id = NEW.created_run_id
    FOR UPDATE;

    IF NOT FOUND
       OR run_row.organization_id <> NEW.organization_id
       OR run_row.source_system <> NEW.source_system
       OR run_row.transform_version <> NEW.transform_version
       OR run_row.status <> 'running'
    THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'canonical entity map matching running run tələb edir';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION legacy_import_observation_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    run_row record;
    map_row record;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy entity observation dəyişdirilə bilməz';
    END IF;

    SELECT run.organization_id, run.source_system, run.transform_version, run.status
    INTO run_row
    FROM public.legacy_import_legacymigrationrun AS run
    WHERE run.id = NEW.run_id
    FOR UPDATE;

    SELECT entity_map.organization_id, entity_map.source_system,
           entity_map.source_row_hash, entity_map.transform_version,
           entity_map.target_model_label, entity_map.target_pk,
           entity_map.state, entity_map.reconciliation_status,
           entity_map.created_run_id
    INTO map_row
    FROM public.legacy_import_legacyentitymap AS entity_map
    WHERE entity_map.id = NEW.entity_map_id
    FOR UPDATE;

    IF NOT FOUND
       OR run_row.status <> 'running'
       OR run_row.organization_id <> NEW.organization_id
       OR run_row.source_system <> map_row.source_system
       OR run_row.transform_version <> NEW.transform_version
       OR map_row.organization_id <> NEW.organization_id
       OR map_row.source_row_hash <> NEW.source_row_hash
       OR map_row.transform_version <> NEW.transform_version
       OR map_row.target_model_label <> NEW.target_model_label
       OR map_row.target_pk <> NEW.target_pk
       OR map_row.state <> NEW.state
       OR map_row.reconciliation_status <> NEW.reconciliation_status
    THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy observation run və canonical mapping ilə uyğun deyil';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION legacy_import_issue_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    run_row record;
    old_rank integer;
    new_rank integer;
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.id IS DISTINCT FROM OLD.id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.run_id IS DISTINCT FROM OLD.run_id
        OR NEW.source_table IS DISTINCT FROM OLD.source_table
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
        OR NEW.legacy_pk IS DISTINCT FROM OLD.legacy_pk
        OR NEW.rule_code IS DISTINCT FROM OLD.rule_code
        OR NEW.payload_digest IS DISTINCT FROM OLD.payload_digest
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy migration issue identity dəyişdirilə bilməz';
    END IF;

    SELECT run.organization_id, run.source_system, run.transform_version, run.status
    INTO run_row
    FROM public.legacy_import_legacymigrationrun AS run
    WHERE run.id = NEW.run_id
    FOR UPDATE;

    IF NOT FOUND OR run_row.organization_id <> NEW.organization_id THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy migration issue run scope ilə uyğun deyil';
    END IF;
    IF TG_OP = 'INSERT' AND run_row.status <> 'running' THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy migration issue yalnız running run-a yazıla bilər';
    END IF;
    IF NEW.entity_map_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM public.legacy_import_legacyentitymap AS entity_map
        JOIN public.legacy_import_legacyentityobservation AS observation
          ON observation.entity_map_id = entity_map.id
         AND observation.run_id = NEW.run_id
        WHERE entity_map.id = NEW.entity_map_id
          AND entity_map.organization_id = NEW.organization_id
          AND entity_map.source_system = run_row.source_system
          AND entity_map.transform_version = run_row.transform_version
          AND entity_map.entity_type = NEW.entity_type
          AND entity_map.legacy_pk = NEW.legacy_pk
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy issue canonical entity observation ilə uyğun deyil';
    END IF;

    IF TG_OP = 'UPDATE' AND run_row.status <> 'running' AND (
        NEW.entity_map_id IS DISTINCT FROM OLD.entity_map_id
        OR NEW.severity IS DISTINCT FROM OLD.severity
        OR NEW.review_status IS NOT DISTINCT FROM OLD.review_status
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'terminal run issue-sunda yalnız review status dəyişə bilər';
    END IF;
    IF TG_OP = 'UPDATE' AND run_row.status = 'running'
       AND NEW.severity IS DISTINCT FROM OLD.severity
    THEN
        old_rank := CASE OLD.severity
            WHEN 'info' THEN 0 WHEN 'warning' THEN 1
            WHEN 'error' THEN 2 WHEN 'critical' THEN 3 ELSE -1 END;
        new_rank := CASE NEW.severity
            WHEN 'info' THEN 0 WHEN 'warning' THEN 1
            WHEN 'error' THEN 2 WHEN 'critical' THEN 3 ELSE -1 END;
        IF new_rank < old_rank OR NEW.review_status <> 'open' THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy issue severity yalnız open escalation ola bilər';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

ALTER TABLE public.legacy_import_legacyentityobservation ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.legacy_import_legacyentityobservation FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON public.legacy_import_legacyentityobservation;
CREATE POLICY rls_tenant_isolation ON public.legacy_import_legacyentityobservation
    USING (
        current_setting('app.bypass_rls', true) = 'on'
        OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'on'
        OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
    );

DROP TRIGGER IF EXISTS legacy_import_run_identity
    ON public.legacy_import_legacymigrationrun;
CREATE TRIGGER legacy_import_run_identity
BEFORE INSERT OR UPDATE ON public.legacy_import_legacymigrationrun
FOR EACH ROW EXECUTE FUNCTION legacy_import_run_identity_guard();

DROP TRIGGER IF EXISTS legacy_import_observation_integrity
    ON public.legacy_import_legacyentityobservation;
CREATE TRIGGER legacy_import_observation_integrity
BEFORE INSERT OR UPDATE ON public.legacy_import_legacyentityobservation
FOR EACH ROW EXECUTE FUNCTION legacy_import_observation_integrity_guard();

DROP TRIGGER IF EXISTS legacy_import_observation_no_delete
    ON public.legacy_import_legacyentityobservation;
CREATE TRIGGER legacy_import_observation_no_delete
BEFORE DELETE ON public.legacy_import_legacyentityobservation
FOR EACH ROW EXECUTE FUNCTION legacy_import_delete_guard();

DROP TRIGGER IF EXISTS legacy_import_observation_no_truncate
    ON public.legacy_import_legacyentityobservation;
CREATE TRIGGER legacy_import_observation_no_truncate
BEFORE TRUNCATE ON public.legacy_import_legacyentityobservation
FOR EACH STATEMENT EXECUTE FUNCTION legacy_import_truncate_guard();

CREATE UNIQUE INDEX IF NOT EXISTS legacy_run_active_scope_uniq
ON public.legacy_import_legacymigrationrun (
    organization_id, source_system, snapshot_sha256, transform_version
)
WHERE status = 'running';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_app_role') THEN
        REVOKE TRUNCATE, REFERENCES, TRIGGER
            ON TABLE public.legacy_import_legacyentityobservation FROM rls_app_role;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON TABLE public.legacy_import_legacyentityobservation TO rls_app_role;
    END IF;
END;
$$;
"""


_REVERSE_SQL = r"""
DROP INDEX IF EXISTS public.legacy_run_active_scope_uniq;
DROP TRIGGER IF EXISTS legacy_import_observation_no_truncate
    ON public.legacy_import_legacyentityobservation;
DROP TRIGGER IF EXISTS legacy_import_observation_no_delete
    ON public.legacy_import_legacyentityobservation;
DROP TRIGGER IF EXISTS legacy_import_observation_integrity
    ON public.legacy_import_legacyentityobservation;
DROP POLICY IF EXISTS rls_tenant_isolation
    ON public.legacy_import_legacyentityobservation;
ALTER TABLE public.legacy_import_legacyentityobservation NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public.legacy_import_legacyentityobservation DISABLE ROW LEVEL SECURITY;
DROP FUNCTION IF EXISTS legacy_import_observation_integrity_guard();

DROP TRIGGER IF EXISTS legacy_import_run_identity
    ON public.legacy_import_legacymigrationrun;
CREATE TRIGGER legacy_import_run_identity
BEFORE UPDATE ON public.legacy_import_legacymigrationrun
FOR EACH ROW EXECUTE FUNCTION legacy_import_run_identity_guard();

CREATE OR REPLACE FUNCTION legacy_import_run_identity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.source_system IS DISTINCT FROM OLD.source_system
       OR NEW.snapshot_sha256 IS DISTINCT FROM OLD.snapshot_sha256
       OR NEW.snapshot_size_bytes IS DISTINCT FROM OLD.snapshot_size_bytes
       OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
       OR NEW.transform_version IS DISTINCT FROM OLD.transform_version
       OR NEW.mode IS DISTINCT FROM OLD.mode
       OR NEW.origin IS DISTINCT FROM OLD.origin
    THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy migration run identity dəyişdirilə bilməz';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION legacy_import_map_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.source_system IS DISTINCT FROM OLD.source_system
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
        OR NEW.legacy_pk IS DISTINCT FROM OLD.legacy_pk
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy entity map identity dəyişdirilə bilməz';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.legacy_import_legacymigrationrun AS run
        WHERE run.id = NEW.created_run_id
          AND run.organization_id = NEW.organization_id
          AND run.source_system = NEW.source_system
          AND run.transform_version = NEW.transform_version
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy entity map run scope ilə uyğun deyil';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION legacy_import_issue_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.run_id IS DISTINCT FROM OLD.run_id
        OR NEW.source_table IS DISTINCT FROM OLD.source_table
        OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
        OR NEW.legacy_pk IS DISTINCT FROM OLD.legacy_pk
        OR NEW.rule_code IS DISTINCT FROM OLD.rule_code
        OR NEW.payload_digest IS DISTINCT FROM OLD.payload_digest
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy migration issue identity dəyişdirilə bilməz';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.legacy_import_legacymigrationrun AS run
        WHERE run.id = NEW.run_id AND run.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy migration issue run scope ilə uyğun deyil';
    END IF;
    IF NEW.entity_map_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM public.legacy_import_legacyentitymap AS entity_map
        JOIN public.legacy_import_legacymigrationrun AS run ON run.id = NEW.run_id
        WHERE entity_map.id = NEW.entity_map_id
          AND entity_map.organization_id = NEW.organization_id
          AND entity_map.source_system = run.source_system
          AND entity_map.transform_version = run.transform_version
          AND entity_map.entity_type = NEW.entity_type
          AND entity_map.legacy_pk = NEW.legacy_pk
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy migration issue entity map identity ilə uyğun deyil';
    END IF;
    RETURN NEW;
END;
$$;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FORWARD_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("legacy_import", "0003_security_hardening")]

    operations = [
        migrations.CreateModel(
            name="LegacyEntityObservation",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "source_row_hash",
                    models.CharField(max_length=64, validators=[_SHA256_VALIDATOR]),
                ),
                (
                    "transform_version",
                    models.CharField(max_length=64, validators=[_TOKEN_VALIDATOR]),
                ),
                (
                    "target_model_label",
                    models.CharField(blank=True, default="", max_length=100, validators=[_MODEL_LABEL_VALIDATOR]),
                ),
                (
                    "target_pk",
                    models.CharField(blank=True, default="", max_length=255, validators=[_OPAQUE_KEY_VALIDATOR]),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("migrated", "Miqrasiya edilib"),
                            ("skipped", "Buraxılıb"),
                            ("quarantined", "Quarantine"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "reconciliation_status",
                    models.CharField(
                        choices=[
                            ("pending", "Gözləyir"),
                            ("verified", "Təsdiqlənib"),
                            ("mismatch", "Uyğunsuzluq"),
                            ("not_applicable", "Tətbiq edilmir"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "entity_map",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="observations",
                        to="legacy_import.legacyentitymap",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="legacy_entity_observations",
                        to="organizations.organization",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="entity_observations",
                        to="legacy_import.legacymigrationrun",
                    ),
                ),
            ],
            options={"ordering": ["run_id", "entity_map_id"]},
        ),
        migrations.AddIndex(
            model_name="legacyentityobservation",
            index=models.Index(fields=["organization", "run", "state"], name="legacy_obs_org_run_state"),
        ),
        migrations.AddConstraint(
            model_name="legacyentityobservation",
            constraint=models.UniqueConstraint(fields=("run", "entity_map"), name="legacy_obs_run_map_uniq"),
        ),
        migrations.AddConstraint(
            model_name="legacyentityobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(("source_row_hash__regex", "^[0-9a-f]{64}$")),
                name="legacy_obs_row_sha_hex",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacyentityobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(("transform_version__regex", "^[a-z0-9][a-z0-9._-]*$")),
                name="legacy_obs_transform_token",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacyentityobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("target_model_label", ""),
                    ("target_model_label__regex", "^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"),
                    _connector="OR",
                ),
                name="legacy_obs_model_label",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacyentityobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("target_pk", ""),
                    ("target_pk__regex", "^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$"),
                    _connector="OR",
                ),
                name="legacy_obs_target_pk_token",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacyentityobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("state", "migrated"),
                        models.Q(("target_model_label", ""), _negated=True),
                        models.Q(("target_pk", ""), _negated=True),
                    ),
                    models.Q(
                        ("state__in", ["skipped", "quarantined"]),
                        ("target_model_label", ""),
                        ("target_pk", ""),
                    ),
                    _connector="OR",
                ),
                name="legacy_obs_target_by_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacyentityobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(("state__in", ["migrated", "skipped", "quarantined"])),
                name="legacy_obs_state_choice",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacyentityobservation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("reconciliation_status__in", ["pending", "verified", "mismatch", "not_applicable"])
                ),
                name="legacy_obs_recon_choice",
            ),
        ),
        migrations.RunPython(_apply, _revert),
    ]

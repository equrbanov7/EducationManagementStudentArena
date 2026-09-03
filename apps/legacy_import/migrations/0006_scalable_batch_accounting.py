"""Append-only hash-chained accounting for multi-million-row imports."""

import uuid

import django.core.validators
import django.db.models.deletion
import django.db.models.expressions
from django.conf import settings
from django.db import migrations, models

_RUN_GUARD_FORWARD = r"""
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
       OR NEW.accounting_mode IS DISTINCT FROM OLD.accounting_mode
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

        IF OLD.accounting_mode = 'batch' THEN
            SELECT COALESCE(SUM(migrated_count), 0),
                   COALESCE(SUM(skipped_count), 0),
                   COALESCE(SUM(quarantined_count), 0)
              INTO observed_migrated, observed_skipped, observed_quarantined
              FROM public.legacy_import_legacyimportbatch
             WHERE run_id = OLD.id;
        ELSE
            SELECT COUNT(*) FILTER (WHERE state = 'migrated'),
                   COUNT(*) FILTER (WHERE state = 'skipped'),
                   COUNT(*) FILTER (WHERE state = 'quarantined')
              INTO observed_migrated, observed_skipped, observed_quarantined
              FROM public.legacy_import_legacyentityobservation
             WHERE run_id = OLD.id;
        END IF;

        IF NEW.migrated_count <> observed_migrated
           OR NEW.skipped_count <> observed_skipped
           OR NEW.quarantined_count <> observed_quarantined
           OR NEW.migrated_count + NEW.skipped_count + NEW.quarantined_count
                > NEW.source_row_count
        THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy migration terminal sayları accounting ledger ilə uyğun deyil';
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
REVOKE ALL ON FUNCTION legacy_import_run_identity_guard() FROM PUBLIC;
"""


_RUN_GUARD_RESTORE = (
    _RUN_GUARD_FORWARD.replace(
        """        IF OLD.accounting_mode = 'batch' THEN
            SELECT COALESCE(SUM(migrated_count), 0),
                   COALESCE(SUM(skipped_count), 0),
                   COALESCE(SUM(quarantined_count), 0)
              INTO observed_migrated, observed_skipped, observed_quarantined
              FROM public.legacy_import_legacyimportbatch
             WHERE run_id = OLD.id;
        ELSE
            SELECT COUNT(*) FILTER (WHERE state = 'migrated'),
                   COUNT(*) FILTER (WHERE state = 'skipped'),
                   COUNT(*) FILTER (WHERE state = 'quarantined')
              INTO observed_migrated, observed_skipped, observed_quarantined
              FROM public.legacy_import_legacyentityobservation
             WHERE run_id = OLD.id;
        END IF;
""",
        """        SELECT COUNT(*) FILTER (WHERE state = 'migrated'),
               COUNT(*) FILTER (WHERE state = 'skipped'),
               COUNT(*) FILTER (WHERE state = 'quarantined')
          INTO observed_migrated, observed_skipped, observed_quarantined
          FROM public.legacy_import_legacyentityobservation
         WHERE run_id = OLD.id;
""",
    )
    .replace("       OR NEW.accounting_mode IS DISTINCT FROM OLD.accounting_mode\n", "")
    .replace(
        "terminal sayları accounting ledger ilə uyğun deyil",
        "terminal sayları observation ledger ilə uyğun deyil",
    )
)


_BATCH_FORWARD = r"""
CREATE OR REPLACE FUNCTION legacy_import_batch_integrity_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    run_row record;
    predecessor record;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy import batch dəyişdirilə bilməz';
    END IF;

    SELECT run.organization_id, run.status, run.accounting_mode
      INTO run_row
      FROM public.legacy_import_legacymigrationrun AS run
     WHERE run.id = NEW.run_id
     FOR UPDATE;
    IF NOT FOUND
       OR run_row.organization_id IS DISTINCT FROM NEW.organization_id
       OR run_row.status <> 'running'
       OR run_row.accounting_mode <> 'batch'
       OR NOT EXISTS (
            SELECT 1 FROM public.auth_user AS actor
             WHERE actor.id = NEW.recorded_by_id AND actor.is_active
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'legacy import batch matching active run və actor tələb edir';
    END IF;

    IF NEW.sequence = 1 THEN
        IF NEW.previous_chain_digest <> '' OR EXISTS (
            SELECT 1 FROM public.legacy_import_legacyimportbatch AS batch
             WHERE batch.run_id = NEW.run_id
               AND batch.source_table = NEW.source_table
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy import ilk batch zənciri etibarsızdır';
        END IF;
    ELSE
        SELECT batch.last_legacy_pk, batch.chain_digest,
               batch.entity_type, batch.contract_fingerprint
          INTO predecessor
          FROM public.legacy_import_legacyimportbatch AS batch
         WHERE batch.run_id = NEW.run_id
           AND batch.source_table = NEW.source_table
           AND batch.sequence = NEW.sequence - 1
         FOR UPDATE;
        IF NOT FOUND
           OR NEW.first_legacy_pk <= predecessor.last_legacy_pk
           OR NEW.previous_chain_digest IS DISTINCT FROM predecessor.chain_digest
           OR NEW.entity_type IS DISTINCT FROM predecessor.entity_type
           OR NEW.contract_fingerprint IS DISTINCT FROM predecessor.contract_fingerprint
        THEN
            RAISE EXCEPTION USING ERRCODE = '23514',
                MESSAGE = 'legacy import batch predecessor zənciri etibarsızdır';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

ALTER TABLE public.legacy_import_legacyimportbatch ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.legacy_import_legacyimportbatch FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON public.legacy_import_legacyimportbatch;
CREATE POLICY rls_tenant_isolation ON public.legacy_import_legacyimportbatch
    USING (
        current_setting('app.bypass_rls', true) = 'on'
        OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'on'
        OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
    );

CREATE TRIGGER legacy_import_batch_integrity
BEFORE INSERT OR UPDATE ON public.legacy_import_legacyimportbatch
FOR EACH ROW EXECUTE FUNCTION legacy_import_batch_integrity_guard();
CREATE TRIGGER legacy_import_batch_no_delete
BEFORE DELETE ON public.legacy_import_legacyimportbatch
FOR EACH ROW EXECUTE FUNCTION legacy_import_delete_guard();
CREATE TRIGGER legacy_import_batch_no_truncate
BEFORE TRUNCATE ON public.legacy_import_legacyimportbatch
FOR EACH STATEMENT EXECUTE FUNCTION legacy_import_truncate_guard();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rls_app_role') THEN
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
          ON TABLE public.legacy_import_legacyimportbatch FROM rls_app_role;
        GRANT SELECT, INSERT
          ON TABLE public.legacy_import_legacyimportbatch TO rls_app_role;
    END IF;
END;
$$;
REVOKE ALL ON FUNCTION legacy_import_batch_integrity_guard() FROM PUBLIC;
"""


_BATCH_REVERSE = r"""
DROP TRIGGER IF EXISTS legacy_import_batch_no_truncate
    ON public.legacy_import_legacyimportbatch;
DROP TRIGGER IF EXISTS legacy_import_batch_no_delete
    ON public.legacy_import_legacyimportbatch;
DROP TRIGGER IF EXISTS legacy_import_batch_integrity
    ON public.legacy_import_legacyimportbatch;
DROP POLICY IF EXISTS rls_tenant_isolation
    ON public.legacy_import_legacyimportbatch;
ALTER TABLE public.legacy_import_legacyimportbatch NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public.legacy_import_legacyimportbatch DISABLE ROW LEVEL SECURITY;
DROP FUNCTION IF EXISTS legacy_import_batch_integrity_guard();
"""


def install_postgres_guards(_apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_BATCH_FORWARD)
    schema_editor.execute(_RUN_GUARD_FORWARD)
    schema_editor.execute("SET LOCAL app.bypass_rls = 'off'")


def remove_postgres_guards(apps, schema_editor):
    Batch = apps.get_model("legacy_import", "LegacyImportBatch")
    database_alias = schema_editor.connection.alias
    if schema_editor.connection.vendor == "postgresql":
        # FORCE RLS otherwise hides evidence when no tenant context is set.
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    if Batch.objects.using(database_alias).exists():
        raise RuntimeError("legacy_import_0006_reverse_stop:batch_evidence_exists")
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_BATCH_REVERSE)
    schema_editor.execute(_RUN_GUARD_RESTORE)


class Migration(migrations.Migration):
    dependencies = [
        ("legacy_import", "0005_reviewed_mapping_versions"),
        ("organizations", "0027_seed_grade_approval_permissions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="legacymigrationrun",
            name="accounting_mode",
            field=models.CharField(
                choices=[("row", "Row ledger"), ("batch", "Batch ledger")],
                default="row",
                max_length=8,
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationrun",
            constraint=models.CheckConstraint(
                condition=models.Q(("accounting_mode__in", ["row", "batch"])),
                name="legacy_run_accounting_choice",
            ),
        ),
        migrations.CreateModel(
            name="LegacyImportBatch",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                (
                    "source_table",
                    models.CharField(
                        max_length=64,
                        validators=[
                            django.core.validators.RegexValidator(
                                message=("Yalnız kiçik hərf, rəqəm, nöqtə, alt xətt və defis " "istifadə edilə bilər."),
                                regex="^[a-z0-9][a-z0-9._-]*$",
                            )
                        ],
                    ),
                ),
                (
                    "entity_type",
                    models.CharField(
                        max_length=64,
                        validators=[
                            django.core.validators.RegexValidator(
                                message=("Yalnız kiçik hərf, rəqəm, nöqtə, alt xətt və defis " "istifadə edilə bilər."),
                                regex="^[a-z0-9][a-z0-9._-]*$",
                            )
                        ],
                    ),
                ),
                ("sequence", models.PositiveIntegerField()),
                ("first_legacy_pk", models.PositiveBigIntegerField()),
                ("last_legacy_pk", models.PositiveBigIntegerField()),
                ("source_row_count", models.PositiveIntegerField()),
                ("migrated_count", models.PositiveIntegerField(default=0)),
                ("skipped_count", models.PositiveIntegerField(default=0)),
                ("quarantined_count", models.PositiveIntegerField(default=0)),
                *[
                    (
                        name,
                        models.CharField(
                            max_length=64,
                            validators=[
                                django.core.validators.RegexValidator(
                                    message=("Dəyər kiçik hərfli 64 simvolluq SHA-256 hex digest " "olmalıdır."),
                                    regex="^[0-9a-f]{64}$",
                                )
                            ],
                        ),
                    )
                    for name in (
                        "contract_fingerprint",
                        "source_digest",
                        "classification_digest",
                        "target_digest",
                        "chain_digest",
                    )
                ],
                (
                    "previous_chain_digest",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=64,
                        validators=[
                            django.core.validators.RegexValidator(
                                message=("Dəyər kiçik hərfli 64 simvolluq SHA-256 hex digest " "olmalıdır."),
                                regex="^[0-9a-f]{64}$",
                            )
                        ],
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="legacy_import_batches",
                        to="organizations.organization",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="recorded_legacy_import_batches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="batches",
                        to="legacy_import.legacymigrationrun",
                    ),
                ),
            ],
            options={
                "ordering": ["run_id", "source_table", "entity_type", "sequence"],
                "indexes": [
                    models.Index(
                        fields=["organization", "run", "source_table"],
                        name="legacy_batch_org_run_table",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "source_table", "sequence"),
                        name="legacy_batch_run_table_seq_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("sequence__gte", 1)),
                        name="legacy_batch_sequence_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("source_row_count__gte", 1)),
                        name="legacy_batch_rows_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("first_legacy_pk__lte", models.F("last_legacy_pk"))),
                        name="legacy_batch_pk_range_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("first_legacy_pk__gte", 1)),
                        name="legacy_batch_first_pk_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("last_legacy_pk__gte", 1)),
                        name="legacy_batch_last_pk_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "source_row_count__lte",
                                django.db.models.expressions.CombinedExpression(
                                    django.db.models.expressions.CombinedExpression(
                                        models.F("last_legacy_pk"),
                                        "-",
                                        models.F("first_legacy_pk"),
                                    ),
                                    "+",
                                    models.Value(1),
                                ),
                            )
                        ),
                        name="legacy_batch_rows_within_pk_range",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "source_row_count",
                                django.db.models.expressions.CombinedExpression(
                                    django.db.models.expressions.CombinedExpression(
                                        models.F("migrated_count"),
                                        "+",
                                        models.F("skipped_count"),
                                    ),
                                    "+",
                                    models.F("quarantined_count"),
                                ),
                            )
                        ),
                        name="legacy_batch_counts_total",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("previous_chain_digest", ""), ("sequence", 1)),
                            models.Q(
                                ("previous_chain_digest__regex", "^[0-9a-f]{64}$"),
                                ("sequence__gt", 1),
                            ),
                            _connector="OR",
                        ),
                        name="legacy_batch_previous_shape",
                    ),
                    *[
                        models.CheckConstraint(
                            condition=models.Q((f"{field_name}__regex", "^[0-9a-f]{64}$")),
                            name=constraint_name,
                        )
                        for field_name, constraint_name in (
                            ("contract_fingerprint", "legacy_batch_contract_sha_hex"),
                            ("source_digest", "legacy_batch_source_sha_hex"),
                            ("classification_digest", "legacy_batch_class_sha_hex"),
                            ("target_digest", "legacy_batch_target_sha_hex"),
                            ("chain_digest", "legacy_batch_chain_sha_hex"),
                        )
                    ],
                ],
            },
        ),
        migrations.RunPython(install_postgres_guards, remove_postgres_guards),
    ]

"""Add stable correction locators and the append-only reversal ledger."""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_CORRECTION_TABLES = [
    "registrar_journalcorrection",
    "registrar_lessoncorrection",
    "registrar_selfworkcorrection",
    "registrar_courseworkcorrection",
    "registrar_componentscorecorrection",
]

_V1_IMMUTABLE_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_correction_evidence_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    old_payload jsonb;
    new_payload jsonb;
    old_actor text;
    new_actor text;
    old_instructor text;
    new_instructor text;
    old_lesson text;
    new_lesson text;
BEGIN
    old_payload := to_jsonb(OLD)
        - 'updated_at' - 'corrected_by_id' - 'old_instructor_id'
        - 'new_instructor_id' - 'lesson_id';
    new_payload := to_jsonb(NEW)
        - 'updated_at' - 'corrected_by_id' - 'old_instructor_id'
        - 'new_instructor_id' - 'lesson_id';
    IF new_payload IS DISTINCT FROM old_payload THEN
        RAISE EXCEPTION 'registrar correction evidence is immutable' USING ERRCODE = '23514';
    END IF;

    old_actor := to_jsonb(OLD) ->> 'corrected_by_id';
    new_actor := to_jsonb(NEW) ->> 'corrected_by_id';
    IF new_actor IS DISTINCT FROM old_actor AND new_actor IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction actor cannot be reassigned' USING ERRCODE = '23514';
    END IF;
    old_instructor := to_jsonb(OLD) ->> 'old_instructor_id';
    new_instructor := to_jsonb(NEW) ->> 'old_instructor_id';
    IF new_instructor IS DISTINCT FROM old_instructor AND new_instructor IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction old instructor cannot be reassigned' USING ERRCODE = '23514';
    END IF;
    old_instructor := to_jsonb(OLD) ->> 'new_instructor_id';
    new_instructor := to_jsonb(NEW) ->> 'new_instructor_id';
    IF new_instructor IS DISTINCT FROM old_instructor AND new_instructor IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction new instructor cannot be reassigned' USING ERRCODE = '23514';
    END IF;
    old_lesson := to_jsonb(OLD) ->> 'lesson_id';
    new_lesson := to_jsonb(NEW) ->> 'lesson_id';
    IF new_lesson IS DISTINCT FROM old_lesson AND new_lesson IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction lesson cannot be reassigned' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.registrar_guard_correction_evidence_immutable() FROM PUBLIC;
"""

_V2_IMMUTABLE_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_correction_evidence_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    old_payload jsonb;
    new_payload jsonb;
    relation_key text;
    old_value text;
    new_value text;
BEGIN
    old_payload := to_jsonb(OLD)
        - 'updated_at' - 'corrected_by_id' - 'old_instructor_id'
        - 'new_instructor_id' - 'lesson_id' - 'lesson_mark_id';
    new_payload := to_jsonb(NEW)
        - 'updated_at' - 'corrected_by_id' - 'old_instructor_id'
        - 'new_instructor_id' - 'lesson_id' - 'lesson_mark_id';
    IF new_payload IS DISTINCT FROM old_payload THEN
        RAISE EXCEPTION 'registrar correction evidence is immutable' USING ERRCODE = '23514';
    END IF;

    FOREACH relation_key IN ARRAY ARRAY[
        'corrected_by_id', 'old_instructor_id', 'new_instructor_id',
        'lesson_id', 'lesson_mark_id'
    ] LOOP
        old_value := to_jsonb(OLD) ->> relation_key;
        new_value := to_jsonb(NEW) ->> relation_key;
        IF new_value IS DISTINCT FROM old_value AND new_value IS NOT NULL THEN
            RAISE EXCEPTION 'registrar correction relation cannot be reassigned' USING ERRCODE = '23514';
        END IF;
    END LOOP;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.registrar_guard_correction_evidence_immutable() FROM PUBLIC;
"""

_REVERSAL_GUARD_FUNCTIONS = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_correction_no_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    has_rows boolean;
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        IF COALESCE((SELECT usesuper FROM pg_user WHERE usename = session_user), false) THEN
            -- Superuser (DBA / Django test flush) trigger-i onsuz da DROP edə bilər.
            RETURN NULL;
        END IF;
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %%I.%%I)',
            TG_TABLE_SCHEMA,
            TG_TABLE_NAME
        ) INTO has_rows;
        IF NOT has_rows THEN
            RETURN NULL;
        END IF;
    END IF;
    RAISE EXCEPTION 'registrar correction evidence is append-only: %%', TG_OP
        USING ERRCODE = '23514';
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_correction_reversal_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    old_payload jsonb;
    new_payload jsonb;
BEGIN
    old_payload := to_jsonb(OLD) - 'reverted_by_id';
    new_payload := to_jsonb(NEW) - 'reverted_by_id';
    IF new_payload IS DISTINCT FROM old_payload THEN
        RAISE EXCEPTION 'registrar correction reversal evidence is immutable'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.reverted_by_id IS DISTINCT FROM OLD.reverted_by_id
       AND NEW.reverted_by_id IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction reversal actor cannot be reassigned'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_correction_reversal_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    target_organization uuid;
BEGIN
    IF NEW.reverted_by_id IS NULL
       OR NEW.reverted_by_ref IS DISTINCT FROM NEW.reverted_by_id::text THEN
        RAISE EXCEPTION 'registrar correction reversal actor attribution is invalid'
            USING ERRCODE = '23514';
    END IF;
    IF NOT public.registrar_actor_can_write_for_organization(
        NEW.organization_id,
        NEW.reverted_by_id
    ) THEN
        RAISE EXCEPTION 'registrar correction reversal actor is not authorized for the organization'
            USING ERRCODE = '23514';
    END IF;

    target_organization := COALESCE(
        (SELECT organization_id FROM public.registrar_journalcorrection
          WHERE id = NEW.journal_correction_id),
        (SELECT organization_id FROM public.registrar_lessoncorrection
          WHERE id = NEW.lesson_correction_id),
        (SELECT organization_id FROM public.registrar_selfworkcorrection
          WHERE id = NEW.selfwork_correction_id),
        (SELECT organization_id FROM public.registrar_courseworkcorrection
          WHERE id = NEW.coursework_correction_id),
        (SELECT organization_id FROM public.registrar_componentscorecorrection
          WHERE id = NEW.component_correction_id)
    );
    IF target_organization IS DISTINCT FROM NEW.organization_id THEN
        RAISE EXCEPTION 'registrar correction reversal target must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_assert_correction_reversal_integrity()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.registrar_journalcorrection correction
          LEFT JOIN public.registrar_lessonmark mark ON mark.id = correction.lesson_mark_id
         WHERE correction.lesson_mark_ref IS NULL
            OR correction.lesson_ref IS NULL
            OR correction.enrollment_ref IS NULL
            OR (
                correction.lesson_mark_id IS NOT NULL
                AND (
                    mark.id IS NULL
                    OR correction.lesson_mark_ref IS DISTINCT FROM mark.id
                    OR correction.lesson_ref IS DISTINCT FROM mark.lesson_id
                    OR correction.enrollment_ref IS DISTINCT FROM mark.enrollment_id
                )
            )
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_correctionreversal reversal
         WHERE reversal.reverted_by_ref = ''
            OR reversal.reason_code IS DISTINCT FROM 'operator_revert'
            OR (
                reversal.reverted_by_id IS NOT NULL
                AND reversal.reverted_by_ref IS DISTINCT FROM reversal.reverted_by_id::text
            )
            OR COALESCE(
                (SELECT organization_id FROM public.registrar_journalcorrection
                  WHERE id = reversal.journal_correction_id),
                (SELECT organization_id FROM public.registrar_lessoncorrection
                  WHERE id = reversal.lesson_correction_id),
                (SELECT organization_id FROM public.registrar_selfworkcorrection
                  WHERE id = reversal.selfwork_correction_id),
                (SELECT organization_id FROM public.registrar_courseworkcorrection
                  WHERE id = reversal.coursework_correction_id),
                (SELECT organization_id FROM public.registrar_componentscorecorrection
                  WHERE id = reversal.component_correction_id)
            ) IS DISTINCT FROM reversal.organization_id
    ) THEN
        RAISE EXCEPTION 'registrar correction reversal integrity precheck failed'
            USING ERRCODE = '23514';
    END IF;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_guard_correction_no_delete() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_correction_reversal_immutable() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_correction_reversal_insert() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_assert_correction_reversal_integrity() FROM PUBLIC;
"""


def _suspend_update_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _CORRECTION_TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_correction_evidence_immutable_guard ON public.{table}")


def _restore_v1_update_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_V1_IMMUTABLE_FUNCTION)
    for table in _CORRECTION_TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER registrar_correction_evidence_immutable_guard BEFORE UPDATE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_correction_evidence_immutable()"
        )


def _backfill_locators(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute("""
        UPDATE registrar_journalcorrection
           SET lesson_mark_ref = lesson_mark_id,
               lesson_ref = (
                   SELECT lesson_id FROM registrar_lessonmark
                    WHERE registrar_lessonmark.id = registrar_journalcorrection.lesson_mark_id
               ),
               enrollment_ref = (
                   SELECT enrollment_id FROM registrar_lessonmark
                    WHERE registrar_lessonmark.id = registrar_journalcorrection.lesson_mark_id
               )
        """)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM registrar_journalcorrection "
            "WHERE lesson_mark_ref IS NULL OR lesson_ref IS NULL OR enrollment_ref IS NULL"
        )
        invalid_count = cursor.fetchone()[0]
    if invalid_count:
        raise RuntimeError("journal correction locator backfill precheck failed")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'off'")


def _install_schema_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_V2_IMMUTABLE_FUNCTION)
    schema_editor.execute(_REVERSAL_GUARD_FUNCTIONS)
    for table in _CORRECTION_TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER registrar_correction_evidence_immutable_guard BEFORE UPDATE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_correction_evidence_immutable()"
        )
        schema_editor.execute(
            f"CREATE TRIGGER registrar_correction_evidence_delete_guard BEFORE DELETE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_correction_no_delete()"
        )
        schema_editor.execute(
            f"CREATE TRIGGER registrar_correction_evidence_truncate_guard BEFORE TRUNCATE ON public.{table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION public.registrar_guard_correction_no_delete()"
        )
    table = "public.registrar_correctionreversal"
    schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    schema_editor.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON {table}")
    schema_editor.execute(f"""
        CREATE POLICY rls_tenant_isolation ON {table}
        USING (
            current_setting('app.bypass_rls', true) = 'on'
            OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        WITH CHECK (
            current_setting('app.bypass_rls', true) = 'on'
            OR organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')
        )
        """)
    schema_editor.execute(
        f"CREATE TRIGGER registrar_correction_reversal_insert_guard BEFORE INSERT ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_correction_reversal_insert()"
    )
    schema_editor.execute(
        f"CREATE TRIGGER registrar_correction_reversal_immutable_guard BEFORE UPDATE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_correction_reversal_immutable()"
    )
    schema_editor.execute(
        f"CREATE TRIGGER registrar_correction_evidence_delete_guard BEFORE DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_correction_no_delete()"
    )
    schema_editor.execute(
        f"CREATE TRIGGER registrar_correction_evidence_truncate_guard BEFORE TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.registrar_guard_correction_no_delete()"
    )
    schema_editor.execute("SELECT public.registrar_assert_correction_reversal_integrity()")
    schema_editor.execute("SET LOCAL app.bypass_rls = 'off'")


def _remove_schema_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    table = "public.registrar_correctionreversal"
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_correction_evidence_truncate_guard ON {table}")
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_correction_evidence_delete_guard ON {table}")
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_correction_reversal_immutable_guard ON {table}")
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_correction_reversal_insert_guard ON {table}")
    schema_editor.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON {table}")
    schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for correction_table in _CORRECTION_TABLES:
        schema_editor.execute(
            "DROP TRIGGER IF EXISTS registrar_correction_evidence_truncate_guard " f"ON public.{correction_table}"
        )
        schema_editor.execute(
            "DROP TRIGGER IF EXISTS registrar_correction_evidence_delete_guard " f"ON public.{correction_table}"
        )
        schema_editor.execute(
            "DROP TRIGGER IF EXISTS registrar_correction_evidence_immutable_guard " f"ON public.{correction_table}"
        )
    schema_editor.execute("DROP FUNCTION IF EXISTS public.registrar_assert_correction_reversal_integrity()")
    schema_editor.execute("DROP FUNCTION IF EXISTS public.registrar_guard_correction_reversal_insert()")
    schema_editor.execute("DROP FUNCTION IF EXISTS public.registrar_guard_correction_reversal_immutable()")
    schema_editor.execute("DROP FUNCTION IF EXISTS public.registrar_guard_correction_no_delete()")
    schema_editor.execute(_V1_IMMUTABLE_FUNCTION)


def _noop(apps, schema_editor):
    return None


def _ensure_safe_reverse(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    CorrectionReversal = apps.get_model("registrar", "CorrectionReversal")
    JournalCorrection = apps.get_model("registrar", "JournalCorrection")
    if CorrectionReversal.objects.exists() or JournalCorrection.objects.filter(lesson_mark_id__isnull=True).exists():
        raise RuntimeError("0043 reverse stopped: v2 correction or reversal evidence exists")


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("registrar", "0042_remaining_migration_target_integrity"),
    ]

    operations = [
        migrations.RunPython(_suspend_update_guards, _restore_v1_update_guards),
        migrations.AddField(
            model_name="journalcorrection",
            name="enrollment_ref",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="journalcorrection",
            name="lesson_mark_ref",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="journalcorrection",
            name="lesson_ref",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(_backfill_locators, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="journalcorrection",
            name="enrollment_ref",
            field=models.UUIDField(db_index=True, editable=False),
        ),
        migrations.AlterField(
            model_name="journalcorrection",
            name="lesson_mark_ref",
            field=models.UUIDField(db_index=True, editable=False),
        ),
        migrations.AlterField(
            model_name="journalcorrection",
            name="lesson_ref",
            field=models.UUIDField(db_index=True, editable=False),
        ),
        migrations.AlterField(
            model_name="journalcorrection",
            name="lesson_mark",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="corrections",
                to="registrar.lessonmark",
            ),
        ),
        migrations.AlterField(
            model_name="journalcorrection",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="journal_corrections",
                to="organizations.organization",
            ),
        ),
        migrations.AlterField(
            model_name="lessoncorrection",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="lesson_corrections",
                to="organizations.organization",
            ),
        ),
        migrations.AlterField(
            model_name="selfworkcorrection",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="selfwork_corrections",
                to="organizations.organization",
            ),
        ),
        migrations.AlterField(
            model_name="selfworkcorrection",
            name="topic",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="corrections",
                to="registrar.selfworktopic",
            ),
        ),
        migrations.AlterField(
            model_name="selfworkcorrection",
            name="enrollment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="selfwork_corrections",
                to="registrar.enrollment",
            ),
        ),
        migrations.AlterField(
            model_name="courseworkcorrection",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="coursework_corrections",
                to="organizations.organization",
            ),
        ),
        migrations.AlterField(
            model_name="courseworkcorrection",
            name="enrollment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="coursework_corrections",
                to="registrar.enrollment",
            ),
        ),
        migrations.AlterField(
            model_name="componentscorecorrection",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="component_corrections",
                to="organizations.organization",
            ),
        ),
        migrations.AlterField(
            model_name="componentscorecorrection",
            name="component",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="corrections",
                to="registrar.assessmentcomponent",
            ),
        ),
        migrations.AlterField(
            model_name="componentscorecorrection",
            name="enrollment",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="component_corrections",
                to="registrar.enrollment",
            ),
        ),
        migrations.CreateModel(
            name="CorrectionReversal",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reverted_by_ref", models.CharField(editable=False, max_length=64)),
                (
                    "reason_code",
                    models.CharField(
                        choices=[("operator_revert", "Operator reverted the latest correction")],
                        default="operator_revert",
                        editable=False,
                        max_length=32,
                    ),
                ),
                (
                    "component_correction",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversal",
                        to="registrar.componentscorecorrection",
                    ),
                ),
                (
                    "coursework_correction",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversal",
                        to="registrar.courseworkcorrection",
                    ),
                ),
                (
                    "journal_correction",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversal",
                        to="registrar.journalcorrection",
                    ),
                ),
                (
                    "lesson_correction",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversal",
                        to="registrar.lessoncorrection",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="correction_reversals",
                        to="organizations.organization",
                    ),
                ),
                (
                    "reverted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="correction_reversals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "selfwork_correction",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reversal",
                        to="registrar.selfworkcorrection",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["organization", "-created_at"], name="reg_rev_org_created_idx")],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("component_correction__isnull", True),
                                ("coursework_correction__isnull", True),
                                ("journal_correction__isnull", False),
                                ("lesson_correction__isnull", True),
                                ("selfwork_correction__isnull", True),
                            )
                            | models.Q(
                                ("component_correction__isnull", True),
                                ("coursework_correction__isnull", True),
                                ("journal_correction__isnull", True),
                                ("lesson_correction__isnull", False),
                                ("selfwork_correction__isnull", True),
                            )
                            | models.Q(
                                ("component_correction__isnull", True),
                                ("coursework_correction__isnull", True),
                                ("journal_correction__isnull", True),
                                ("lesson_correction__isnull", True),
                                ("selfwork_correction__isnull", False),
                            )
                            | models.Q(
                                ("component_correction__isnull", True),
                                ("coursework_correction__isnull", False),
                                ("journal_correction__isnull", True),
                                ("lesson_correction__isnull", True),
                                ("selfwork_correction__isnull", True),
                            )
                            | models.Q(
                                ("component_correction__isnull", False),
                                ("coursework_correction__isnull", True),
                                ("journal_correction__isnull", True),
                                ("lesson_correction__isnull", True),
                                ("selfwork_correction__isnull", True),
                            )
                        ),
                        name="reg_rev_exactly_one_target",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("reason_code", "operator_revert")),
                        name="reg_rev_known_reason_code",
                    ),
                ],
            },
        ),
        migrations.RunPython(_install_schema_guards, _remove_schema_guards),
        migrations.RunPython(_noop, _ensure_safe_reverse),
    ]

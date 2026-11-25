"""«Qrupdan çıxar» (sahib 2026-11-25): qrup → QRUPSUZ keçidi rəsmi, sübutlu axın kimi.

0045 qrup dəyişikliyini yalnız ``registrar_begin_student_group_transfer`` + ``…_finalize_…`` cütünə buraxır və
hədəfi NULL olan keçidi («student group transfer target is invalid») rədd edirdi. Tələbəni xaric etmədən /
dondurmadan sadəcə qrupdan çıxarmaq üçün:

* ``GroupTransferEvidence.new_group`` NULL ola bilər (NULL = qrupdan çıxarılma);
* ``begin`` NULL hədəfi YALNIZ köhnə qrup doludursa qəbul edir (qrupsuzu «yenidən çıxarmaq» olmaz); aktor
  səlahiyyəti, tenant/sessiya atributu, cari dövr, qeydiyyatların kilidi və gözlənilən id siyahısı eynidir;
  ``app.registrar_group_transfer_new_group`` NULL üçün ``'<null>'`` yazılır (trigger onunla müqayisə edir);
* ``finalize`` çıxarılmada varis TƏLƏB ETMİR: köhnə qrupun cari dövr qeydiyyatları ``dropped`` + varissiz olmalı,
  audit ``successor_enrollment_ids`` boş, qeydin qrupu NULL olmalıdır. Köçürmə qolu dəyişmir.

Trigger (``registrar_guard_student_group_transfer``) toxunulmur — NULL-u əvvəldən ``'<null>'`` kimi müqayisə edir.
Funksiya imzaları dəyişmir → mövcud GRANT-lar (``rls_app_role`` / ``emsarena_app``) qalır.
"""

import importlib

import django.db.models.deletion
from django.db import migrations, models

_REVERSE_STOP = "registrar_0127_reverse_group_removal_evidence_present"

_FUNCTION_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_begin_student_group_transfer(
    target_evidence uuid,
    target_record uuid,
    expected_old_group uuid,
    target_new_group uuid,
    target_period uuid,
    target_actor bigint
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    record_org uuid;
    record_student bigint;
    actual_old_group uuid;
    session_actor bigint;
    session_org uuid;
    owner_bypass boolean;
    expected_ids jsonb := '[]'::jsonb;
    transaction_ref text := pg_current_xact_id()::text;
BEGIN
    SELECT organization_id, student_id, group_id
      INTO record_org, record_student, actual_old_group
      FROM public.registrar_studentacademicrecord
     WHERE id = target_record
     FOR UPDATE;
    IF NOT FOUND OR actual_old_group IS DISTINCT FROM expected_old_group THEN
        RAISE EXCEPTION 'student group transfer source changed'
            USING ERRCODE = '23514';
    END IF;
    owner_bypass := current_setting('app.bypass_rls', true) = 'on'
        AND session_user = current_user;
    IF NOT owner_bypass THEN
        BEGIN
            session_actor := NULLIF(current_setting('app.current_user_id', true), '')::bigint;
            session_org := NULLIF(current_setting('app.current_org_id', true), '')::uuid;
        EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
            session_actor := NULL;
            session_org := NULL;
        END;
        IF session_actor IS DISTINCT FROM target_actor
           OR session_org IS DISTINCT FROM record_org THEN
            RAISE EXCEPTION 'group transfer session attribution does not match actor and tenant'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    IF target_new_group IS NULL THEN
        -- 0127: NULL hədəf = qrupdan çıxarılma; yalnız qrupu olan qeyd üçün.
        IF actual_old_group IS NULL THEN
            RAISE EXCEPTION 'student group transfer target is invalid'
                USING ERRCODE = '23514';
        END IF;
    ELSIF target_new_group IS NOT DISTINCT FROM actual_old_group
       OR NOT EXISTS (
           SELECT 1 FROM public.organizations_orgunit target
            WHERE target.id = target_new_group
              AND target.organization_id = record_org
              AND target.unit_type = 'group'
       ) THEN
        RAISE EXCEPTION 'student group transfer target is invalid'
            USING ERRCODE = '23514';
    END IF;
    IF NOT public.registrar_actor_can_write_for_organization(record_org, target_actor) THEN
        RAISE EXCEPTION 'student group transfer actor is not authorized'
            USING ERRCODE = '23514';
    END IF;
    IF target_period IS NULL THEN
        IF EXISTS (
            SELECT 1 FROM public.organizations_academicperiod
             WHERE organization_id = record_org AND is_current AND is_active
        ) THEN
            RAISE EXCEPTION 'current academic period is required for group transfer'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NOT EXISTS (
        SELECT 1 FROM public.organizations_academicperiod
         WHERE id = target_period AND organization_id = record_org AND is_current AND is_active
    ) THEN
        RAISE EXCEPTION 'group transfer period must be the current tenant period'
            USING ERRCODE = '23514';
    END IF;

    IF target_period IS NOT NULL AND actual_old_group IS NOT NULL THEN
        PERFORM 1
          FROM public.registrar_enrollment enrollment
          JOIN public.registrar_courseoffering offering
            ON offering.id = enrollment.offering_id
         WHERE enrollment.student_id = record_student
           AND enrollment.organization_id = record_org
           AND enrollment.status = 'enrolled'
           AND offering.period_id = target_period
           AND offering.group_id = actual_old_group
         FOR UPDATE OF enrollment;
        SELECT COALESCE(jsonb_agg(enrollment.id::text ORDER BY enrollment.id::text), '[]'::jsonb)
          INTO expected_ids
          FROM public.registrar_enrollment enrollment
          JOIN public.registrar_courseoffering offering
            ON offering.id = enrollment.offering_id
         WHERE enrollment.student_id = record_student
           AND enrollment.organization_id = record_org
           AND enrollment.status = 'enrolled'
           AND offering.period_id = target_period
           AND offering.group_id = actual_old_group;
    END IF;

    INSERT INTO public.registrar_grouptransferevidence (
        id, organization_id, record_id, old_group_id, new_group_id, period_id,
        actor_ref, transaction_id, expected_enrollment_ids, audit_ref,
        is_finalized, created_at
    ) VALUES (
        target_evidence, record_org, target_record, actual_old_group,
        target_new_group, target_period, target_actor, transaction_ref,
        expected_ids, NULL, false, statement_timestamp()
    );

    PERFORM set_config('app.registrar_group_transfer_evidence', target_evidence::text, true);
    PERFORM set_config('app.registrar_group_transfer_record', target_record::text, true);
    PERFORM set_config(
        'app.registrar_group_transfer_old_group',
        COALESCE(actual_old_group::text, '<null>'),
        true
    );
    PERFORM set_config(
        'app.registrar_group_transfer_new_group',
        COALESCE(target_new_group::text, '<null>'),
        true
    );
    PERFORM set_config('app.registrar_group_transfer_actor', target_actor::text, true);
    PERFORM set_config('app.registrar_group_transfer_txid', transaction_ref, true);

    UPDATE public.registrar_studentacademicrecord
       SET group_id = target_new_group, updated_at = statement_timestamp()
     WHERE id = target_record;

    PERFORM set_config('app.registrar_group_transfer_evidence', '', true);
    PERFORM set_config('app.registrar_group_transfer_record', '', true);
    PERFORM set_config('app.registrar_group_transfer_old_group', '', true);
    PERFORM set_config('app.registrar_group_transfer_new_group', '', true);
    PERFORM set_config('app.registrar_group_transfer_actor', '', true);
    PERFORM set_config('app.registrar_group_transfer_txid', '', true);
    RETURN target_evidence;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_finalize_student_group_transfer(
    target_evidence uuid,
    target_audit uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    evidence record;
    audit_changes jsonb;
    expected_ids text[];
    moved_ids text[];
    successor_ids text[];
    actual_successor_ids text[];
BEGIN
    SELECT * INTO evidence
      FROM public.registrar_grouptransferevidence
     WHERE id = target_evidence
     FOR UPDATE;
    IF NOT FOUND OR evidence.is_finalized
       OR evidence.transaction_id IS DISTINCT FROM pg_current_xact_id()::text THEN
        RAISE EXCEPTION 'group transfer evidence is not pending in this transaction'
            USING ERRCODE = '23514';
    END IF;
    SELECT changes INTO audit_changes
      FROM public.audit_auditlog audit
     WHERE audit.id = target_audit
       AND audit.organization_id = evidence.organization_id
       AND audit.user_id = evidence.actor_ref
       AND audit.action = 'update'
       AND audit.resource_type = 'registrar.group_transfer'
       AND audit.resource_id = evidence.record_id::text
       AND audit.old_values ->> 'group_id' = COALESCE(evidence.old_group_id::text, '')
       AND audit.new_values ->> 'group_id' = COALESCE(evidence.new_group_id::text, '');
    IF NOT FOUND OR jsonb_typeof(audit_changes -> 'moved_enrollment_ids') <> 'array'
       OR jsonb_typeof(audit_changes -> 'successor_enrollment_ids') <> 'array' THEN
        RAISE EXCEPTION 'group transfer audit does not match pending evidence'
            USING ERRCODE = '23514';
    END IF;

    SELECT ARRAY(
        SELECT value FROM jsonb_array_elements_text(evidence.expected_enrollment_ids) items(value)
         ORDER BY value
    ) INTO expected_ids;
    SELECT ARRAY(
        SELECT value FROM jsonb_array_elements_text(audit_changes -> 'moved_enrollment_ids') items(value)
         ORDER BY value
    ) INTO moved_ids;
    SELECT ARRAY(
        SELECT value FROM jsonb_array_elements_text(audit_changes -> 'successor_enrollment_ids') items(value)
         ORDER BY value
    ) INTO successor_ids;

    IF evidence.new_group_id IS NULL THEN
        -- 0127: qrupdan çıxarılma — köhnə qrupun cari dövr qeydiyyatları tarixçəyə (``dropped``) keçir,
        -- varis YARANMIR; qeyd qrupsuz qalır.
        IF evidence.old_group_id IS NULL
           OR moved_ids IS DISTINCT FROM expected_ids
           OR cardinality(successor_ids) <> 0 THEN
            RAISE EXCEPTION 'group removal audit enrollment set is incomplete'
                USING ERRCODE = '23514';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM unnest(expected_ids) expected_id
              LEFT JOIN public.registrar_enrollment old_enrollment
                ON old_enrollment.id::text = expected_id
              LEFT JOIN public.registrar_courseoffering old_offering
                ON old_offering.id = old_enrollment.offering_id
             WHERE old_enrollment.id IS NULL
                OR old_enrollment.status <> 'dropped'
                OR old_enrollment.superseded_by_id IS NOT NULL
                OR old_offering.period_id IS DISTINCT FROM evidence.period_id
                OR old_offering.group_id IS DISTINCT FROM evidence.old_group_id
        ) OR EXISTS (
            SELECT 1
              FROM public.registrar_enrollment enrollment
              JOIN public.registrar_courseoffering offering
                ON offering.id = enrollment.offering_id
              JOIN public.registrar_studentacademicrecord record
                ON record.id = evidence.record_id
             WHERE enrollment.student_id = record.student_id
               AND enrollment.status = 'enrolled'
               AND offering.period_id = evidence.period_id
               AND offering.group_id = evidence.old_group_id
        ) OR NOT EXISTS (
            SELECT 1 FROM public.registrar_studentacademicrecord record
             WHERE record.id = evidence.record_id
               AND record.group_id IS NULL
        ) THEN
            RAISE EXCEPTION 'group removal enrollment postcondition failed'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        IF moved_ids IS DISTINCT FROM expected_ids
           OR cardinality(successor_ids) IS DISTINCT FROM cardinality(expected_ids) THEN
            RAISE EXCEPTION 'group transfer audit enrollment set is incomplete'
                USING ERRCODE = '23514';
        END IF;

        SELECT COALESCE(
            array_agg(enrollment.superseded_by_id::text ORDER BY enrollment.superseded_by_id::text),
            ARRAY[]::text[]
        ) INTO actual_successor_ids
          FROM public.registrar_enrollment enrollment
         WHERE enrollment.id::text = ANY(expected_ids);
        IF actual_successor_ids IS DISTINCT FROM successor_ids OR EXISTS (
            SELECT 1
              FROM unnest(expected_ids) expected_id
              LEFT JOIN public.registrar_enrollment old_enrollment
                ON old_enrollment.id::text = expected_id
              LEFT JOIN public.registrar_courseoffering old_offering
                ON old_offering.id = old_enrollment.offering_id
              LEFT JOIN public.registrar_enrollment successor
                ON successor.id = old_enrollment.superseded_by_id
              LEFT JOIN public.registrar_courseoffering new_offering
                ON new_offering.id = successor.offering_id
             WHERE old_enrollment.id IS NULL
                OR old_enrollment.status <> 'dropped'
                OR old_enrollment.student_id IS DISTINCT FROM successor.student_id
                OR old_offering.period_id IS DISTINCT FROM evidence.period_id
                OR old_offering.group_id IS DISTINCT FROM evidence.old_group_id
                OR successor.status <> 'enrolled'
                OR new_offering.period_id IS DISTINCT FROM evidence.period_id
                OR new_offering.group_id IS DISTINCT FROM evidence.new_group_id
                OR new_offering.subject_id IS DISTINCT FROM old_offering.subject_id
        ) OR EXISTS (
            SELECT 1
              FROM public.registrar_enrollment enrollment
              JOIN public.registrar_courseoffering offering
                ON offering.id = enrollment.offering_id
              JOIN public.registrar_studentacademicrecord record
                ON record.id = evidence.record_id
             WHERE enrollment.student_id = record.student_id
               AND enrollment.status = 'enrolled'
               AND offering.period_id = evidence.period_id
               AND offering.group_id = evidence.old_group_id
        ) OR NOT EXISTS (
            SELECT 1 FROM public.registrar_studentacademicrecord record
             WHERE record.id = evidence.record_id
               AND record.group_id = evidence.new_group_id
        ) THEN
            RAISE EXCEPTION 'group transfer enrollment postcondition failed'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    UPDATE public.registrar_grouptransferevidence
       SET audit_ref = target_audit, is_finalized = true
     WHERE id = target_evidence;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_begin_student_group_transfer(uuid, uuid, uuid, uuid, uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_finalize_student_group_transfer(uuid, uuid) FROM PUBLIC;
"""

_REPLACED = ("registrar_begin_student_group_transfer(", "registrar_finalize_student_group_transfer(")


def _set_rls_bypass(schema_editor, enabled):
    schema_editor.execute("SELECT set_config('app.bypass_rls', %s, true)", ["on" if enabled else "off"])


def _previous_sql() -> str:
    """0045-in bu iki funksiyanın ORİJİNAL mətni (geri qaytarma üçün — kopyalanmır, mənbədən kəsilir)."""
    source = importlib.import_module("apps.registrar.migrations.0045_reference_identity_and_group_transfer")
    marker = "CREATE OR REPLACE FUNCTION public."
    blocks = [marker + chunk for chunk in source._FUNCTION_SQL.split(marker)[1:]]
    picked = [block.split("\nREVOKE ALL")[0] for block in blocks if block[len(marker) :].startswith(_REPLACED)]
    if len(picked) != len(_REPLACED):
        raise RuntimeError("registrar_0127_previous_function_sql_not_found")
    return "\n".join(picked)


def _install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    _set_rls_bypass(schema_editor, True)
    try:
        schema_editor.execute(_FUNCTION_SQL)
    finally:
        _set_rls_bypass(schema_editor, False)


def _restore(apps, schema_editor):
    """Geri qaytarma: qrupdan çıxarılma sübutu varsa DAYAN (0045 forması NULL hədəfi tanımır, sütun NOT NULL olur)."""
    if schema_editor.connection.vendor != "postgresql":
        return
    _set_rls_bypass(schema_editor, True)
    try:
        evidence = apps.get_model("registrar", "GroupTransferEvidence")
        if evidence.objects.filter(new_group__isnull=True).exists():
            raise RuntimeError(_REVERSE_STOP)
        schema_editor.execute(_previous_sql())
    finally:
        _set_rls_bypass(schema_editor, False)


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0126_admission_channel_contract_label"),
    ]

    operations = [
        migrations.AlterField(
            model_name="grouptransferevidence",
            name="new_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="organizations.orgunit",
            ),
        ),
        # Funksiyalar sütundan SONRA: geri qaytarmada əvvəl ``_restore`` (NULL sübut varsa dayanır), sonra NOT NULL.
        migrations.RunPython(_install, _restore),
    ]

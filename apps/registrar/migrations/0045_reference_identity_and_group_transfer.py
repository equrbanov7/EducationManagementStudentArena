"""Freeze academic reference identity and authorize exact group transfers."""

import uuid

import django.db.models.deletion
from django.db import migrations, models

_REVERSE_STOP = "registrar_0045_reverse_reference_history_present"

_FUNCTION_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_reference_identity()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    field_name text;
BEGIN
    FOREACH field_name IN ARRAY TG_ARGV LOOP
        IF (to_jsonb(NEW) -> field_name) IS DISTINCT FROM
           (to_jsonb(OLD) -> field_name) THEN
            RAISE EXCEPTION 'registrar reference identity is immutable: %%', field_name
                USING ERRCODE = '23514';
        END IF;
    END LOOP;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_conditional_parent_identity()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    has_evidence boolean := false;
BEGIN
    IF TG_ARGV[0] = 'course_offering' THEN
        IF NEW.subject_id IS NOT DISTINCT FROM OLD.subject_id
           AND NEW.period_id IS NOT DISTINCT FROM OLD.period_id
           AND NEW.group_id IS NOT DISTINCT FROM OLD.group_id THEN
            RETURN NEW;
        END IF;
        has_evidence :=
            EXISTS (SELECT 1 FROM public.registrar_enrollment WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_lesson WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_assessmentscheme WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_scheduleslot WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_assessmentcomponent WHERE offering_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_selfworktopic WHERE offering_id = OLD.id);
    ELSIF TG_ARGV[0] = 'assessment_component' THEN
        IF NEW.offering_id IS NOT DISTINCT FROM OLD.offering_id
           AND NEW.rubric_id IS NOT DISTINCT FROM OLD.rubric_id THEN
            RETURN NEW;
        END IF;
        has_evidence :=
            EXISTS (SELECT 1 FROM public.registrar_componentscore WHERE component_id = OLD.id)
            OR EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE component_id = OLD.id)
            OR EXISTS (
                SELECT 1 FROM public.registrar_componentscorecorrection
                 WHERE component_id = OLD.id
            );
    ELSIF TG_ARGV[0] = 'curriculum' THEN
        IF NEW.program_id IS NOT DISTINCT FROM OLD.program_id THEN
            RETURN NEW;
        END IF;
        has_evidence :=
            EXISTS (SELECT 1 FROM public.registrar_curriculumsubject WHERE curriculum_id = OLD.id)
            OR EXISTS (
                SELECT 1 FROM public.registrar_studentacademicrecord
                 WHERE curriculum_id = OLD.id
            );
    ELSE
        RAISE EXCEPTION 'unknown registrar conditional identity guard'
            USING ERRCODE = '23514';
    END IF;

    IF has_evidence THEN
        RAISE EXCEPTION 'registrar parent identity has dependent evidence'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_student_group_transfer()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    evidence_text text;
    evidence_id uuid;
    actor_text text;
    actor_id bigint;
BEGIN
    IF NEW.group_id IS NOT DISTINCT FROM OLD.group_id THEN
        RETURN NEW;
    END IF;

    evidence_text := current_setting('app.registrar_group_transfer_evidence', true);
    actor_text := current_setting('app.registrar_group_transfer_actor', true);
    BEGIN
        evidence_id := NULLIF(evidence_text, '')::uuid;
        actor_id := NULLIF(actor_text, '')::bigint;
    EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
        evidence_id := NULL;
        actor_id := NULL;
    END;

    IF evidence_id IS NULL
       OR current_setting('app.registrar_group_transfer_record', true)
           IS DISTINCT FROM OLD.id::text
       OR current_setting('app.registrar_group_transfer_old_group', true)
           IS DISTINCT FROM COALESCE(OLD.group_id::text, '<null>')
       OR current_setting('app.registrar_group_transfer_new_group', true)
           IS DISTINCT FROM COALESCE(NEW.group_id::text, '<null>')
       OR current_setting('app.registrar_group_transfer_txid', true)
           IS DISTINCT FROM pg_current_xact_id()::text
       OR actor_id IS NULL
       OR NOT EXISTS (
           SELECT 1 FROM public.registrar_grouptransferevidence evidence
            WHERE evidence.id = evidence_id
              AND evidence.record_id = OLD.id
              AND evidence.organization_id = NEW.organization_id
              AND evidence.old_group_id IS NOT DISTINCT FROM OLD.group_id
              AND evidence.new_group_id IS NOT DISTINCT FROM NEW.group_id
              AND evidence.actor_ref = actor_id
              AND evidence.transaction_id = pg_current_xact_id()::text
              AND NOT evidence.is_finalized
       )
       OR NOT public.registrar_actor_can_write_for_organization(
           NEW.organization_id,
           actor_id
       ) THEN
        RAISE EXCEPTION 'student group change requires an exact authorized transfer'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

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
    IF target_new_group IS NULL OR target_new_group IS NOT DISTINCT FROM actual_old_group
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
    PERFORM set_config('app.registrar_group_transfer_new_group', target_new_group::text, true);
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
       AND audit.new_values ->> 'group_id' = evidence.new_group_id::text;
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

    UPDATE public.registrar_grouptransferevidence
       SET audit_ref = target_audit, is_finalized = true
     WHERE id = target_evidence;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_group_transfer_evidence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'group transfer evidence is append-only' USING ERRCODE = '23514';
    END IF;
    IF OLD.is_finalized OR NEW.id IS DISTINCT FROM OLD.id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.record_id IS DISTINCT FROM OLD.record_id
       OR NEW.old_group_id IS DISTINCT FROM OLD.old_group_id
       OR NEW.new_group_id IS DISTINCT FROM OLD.new_group_id
       OR NEW.period_id IS DISTINCT FROM OLD.period_id
       OR NEW.actor_ref IS DISTINCT FROM OLD.actor_ref
       OR NEW.transaction_id IS DISTINCT FROM OLD.transaction_id
       OR NEW.expected_enrollment_ids IS DISTINCT FROM OLD.expected_enrollment_ids
       OR NOT NEW.is_finalized
       OR OLD.audit_ref IS NOT NULL OR NEW.audit_ref IS NULL THEN
        RAISE EXCEPTION 'group transfer evidence is append-only' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_group_transfer_finalized()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.registrar_grouptransferevidence evidence
         WHERE evidence.id = NEW.id AND evidence.is_finalized AND evidence.audit_ref IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'pending group transfer evidence cannot commit'
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_group_transfer_no_truncate()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF COALESCE((SELECT usesuper FROM pg_user WHERE usename = session_user), false) THEN
        -- Superuser (DBA / Django test flush) trigger-i onsuz da DROP edə bilər.
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'group transfer evidence cannot be truncated' USING ERRCODE = '23514';
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_guard_reference_identity() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_conditional_parent_identity() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_student_group_transfer() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_begin_student_group_transfer(uuid, uuid, uuid, uuid, uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_finalize_student_group_transfer(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_group_transfer_evidence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_group_transfer_finalized() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_group_transfer_no_truncate() FROM PUBLIC;
"""

_IMMUTABLE_TRIGGERS = (
    ("registrar_enrollment", ("offering_id",)),
    ("registrar_lesson", ("offering_id",)),
    ("registrar_lessonmark", ("lesson_id", "enrollment_id")),
    ("registrar_assessmentscheme", ("offering_id",)),
    ("registrar_scheduleslot", ("offering_id",)),
    ("registrar_componentscore", ("component_id", "enrollment_id")),
    (
        "registrar_criterionscore",
        ("component_id", "criterion_id", "enrollment_id"),
    ),
    ("registrar_selfworktopic", ("offering_id",)),
    ("registrar_selfworkmark", ("topic_id", "enrollment_id")),
    ("registrar_coursework", ("enrollment_id",)),
    ("registrar_finalgrade", ("enrollment_id",)),
    ("registrar_resitrecord", ("enrollment_id",)),
    ("registrar_rubriccriterion", ("rubric_id",)),
)

_CONDITIONAL_TRIGGERS = (
    (
        "registrar_courseoffering",
        ("subject_id", "period_id", "group_id"),
        "course_offering",
    ),
    (
        "registrar_assessmentcomponent",
        ("offering_id", "rubric_id"),
        "assessment_component",
    ),
    ("registrar_curriculum", ("program_id",), "curriculum"),
)


def _set_rls_bypass(schema_editor, enabled):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "SELECT set_config('app.bypass_rls', %s, true)",
            ["on" if enabled else "off"],
        )


def _install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    _set_rls_bypass(schema_editor, True)
    try:
        schema_editor.execute(_FUNCTION_SQL)
        for table, fields in _IMMUTABLE_TRIGGERS:
            event_fields = ", ".join(fields)
            arguments = ", ".join("'%s'" % field for field in fields)
            schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_reference_identity_guard " f"ON public.{table}")
            schema_editor.execute(
                "CREATE TRIGGER registrar_reference_identity_guard "
                f"BEFORE UPDATE OF {event_fields} ON public.{table} "
                "FOR EACH ROW EXECUTE FUNCTION "
                f"public.registrar_guard_reference_identity({arguments})"
            )
        for table, fields, kind in _CONDITIONAL_TRIGGERS:
            event_fields = ", ".join(fields)
            schema_editor.execute(
                "DROP TRIGGER IF EXISTS registrar_conditional_parent_identity_guard " f"ON public.{table}"
            )
            schema_editor.execute(
                "CREATE TRIGGER registrar_conditional_parent_identity_guard "
                f"BEFORE UPDATE OF {event_fields} ON public.{table} "
                "FOR EACH ROW EXECUTE FUNCTION "
                f"public.registrar_guard_conditional_parent_identity('{kind}')"
            )
        schema_editor.execute(
            "DROP TRIGGER IF EXISTS registrar_student_group_transfer_guard " "ON public.registrar_studentacademicrecord"
        )
        schema_editor.execute(
            "CREATE TRIGGER registrar_student_group_transfer_guard "
            "BEFORE UPDATE OF group_id ON public.registrar_studentacademicrecord "
            "FOR EACH ROW EXECUTE FUNCTION "
            "public.registrar_guard_student_group_transfer()"
        )
        schema_editor.execute(
            "CREATE TRIGGER registrar_group_transfer_evidence_guard "
            "BEFORE UPDATE OR DELETE ON public.registrar_grouptransferevidence "
            "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_group_transfer_evidence()"
        )
        schema_editor.execute(
            "CREATE CONSTRAINT TRIGGER registrar_group_transfer_finalize_guard "
            "AFTER INSERT ON public.registrar_grouptransferevidence "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.registrar_guard_group_transfer_finalized()"
        )
        schema_editor.execute(
            "CREATE TRIGGER registrar_group_transfer_truncate_guard "
            "BEFORE TRUNCATE ON public.registrar_grouptransferevidence "
            "FOR EACH STATEMENT EXECUTE FUNCTION "
            "public.registrar_guard_group_transfer_no_truncate()"
        )
        schema_editor.execute(
            "ALTER TABLE public.registrar_grouptransferevidence ENABLE ROW LEVEL SECURITY; "
            "ALTER TABLE public.registrar_grouptransferevidence FORCE ROW LEVEL SECURITY; "
            "DROP POLICY IF EXISTS rls_tenant_isolation "
            "ON public.registrar_grouptransferevidence; "
            "CREATE POLICY rls_tenant_isolation ON public.registrar_grouptransferevidence "
            "USING (current_setting('app.bypass_rls', true) = 'on' OR "
            "organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')) "
            "WITH CHECK (current_setting('app.bypass_rls', true) = 'on' OR "
            "organization_id::text = NULLIF(current_setting('app.current_org_id', true), ''))"
        )
        schema_editor.execute(
            "DO $roles$ DECLARE role_name text; BEGIN "
            "FOREACH role_name IN ARRAY ARRAY['rls_app_role', 'emsarena_app'] LOOP "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN "
            "EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE "
            "public.registrar_grouptransferevidence FROM %%I', role_name); "
            "EXECUTE format('GRANT SELECT ON TABLE "
            "public.registrar_grouptransferevidence TO %%I', role_name); "
            "EXECUTE format('GRANT EXECUTE ON FUNCTION "
            "public.registrar_begin_student_group_transfer(uuid, uuid, uuid, uuid, uuid, bigint) "
            "TO %%I', role_name); "
            "EXECUTE format('GRANT EXECUTE ON FUNCTION "
            "public.registrar_finalize_student_group_transfer(uuid, uuid) TO %%I', role_name); "
            "END IF; END LOOP; END $roles$"
        )
    finally:
        _set_rls_bypass(schema_editor, False)


def _remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, _fields in _IMMUTABLE_TRIGGERS:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_reference_identity_guard ON public.{table}")
    for table, _fields, _kind in _CONDITIONAL_TRIGGERS:
        schema_editor.execute(
            "DROP TRIGGER IF EXISTS registrar_conditional_parent_identity_guard " f"ON public.{table}"
        )
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS registrar_student_group_transfer_guard " "ON public.registrar_studentacademicrecord"
    )
    for trigger in (
        "registrar_group_transfer_truncate_guard",
        "registrar_group_transfer_finalize_guard",
        "registrar_group_transfer_evidence_guard",
    ):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger} ON public.registrar_grouptransferevidence")
    schema_editor.execute("DROP POLICY IF EXISTS rls_tenant_isolation " "ON public.registrar_grouptransferevidence")
    schema_editor.execute(
        "ALTER TABLE public.registrar_grouptransferevidence NO FORCE ROW LEVEL SECURITY; "
        "ALTER TABLE public.registrar_grouptransferevidence DISABLE ROW LEVEL SECURITY"
    )
    for signature in (
        "registrar_guard_group_transfer_no_truncate()",
        "registrar_guard_group_transfer_finalized()",
        "registrar_guard_group_transfer_evidence()",
        "registrar_finalize_student_group_transfer(uuid, uuid)",
        "registrar_begin_student_group_transfer(uuid, uuid, uuid, uuid, uuid, bigint)",
        "registrar_guard_student_group_transfer()",
        "registrar_guard_conditional_parent_identity()",
        "registrar_guard_reference_identity()",
    ):
        schema_editor.execute(f"DROP FUNCTION IF EXISTS public.{signature}")


def _conditional_history_exists(apps):
    links = (
        ("CourseOffering", "Enrollment", "offering_id"),
        ("CourseOffering", "Lesson", "offering_id"),
        ("CourseOffering", "AssessmentScheme", "offering_id"),
        ("CourseOffering", "ScheduleSlot", "offering_id"),
        ("CourseOffering", "AssessmentComponent", "offering_id"),
        ("CourseOffering", "SelfWorkTopic", "offering_id"),
        ("AssessmentComponent", "ComponentScore", "component_id"),
        ("AssessmentComponent", "CriterionScore", "component_id"),
        (
            "AssessmentComponent",
            "ComponentScoreCorrection",
            "component_id",
        ),
        ("Curriculum", "CurriculumSubject", "curriculum_id"),
        ("Curriculum", "StudentAcademicRecord", "curriculum_id"),
    )
    for parent_name, child_name, field in links:
        parent = apps.get_model("registrar", parent_name)
        child = apps.get_model("registrar", child_name)
        parent_ids = parent.objects.values("pk")
        if child.objects.filter(**{f"{field}__in": parent_ids}).exists():
            return True
    return False


def _ensure_safe_reverse(apps, schema_editor):
    protected_models = (
        "Enrollment",
        "Lesson",
        "LessonMark",
        "AssessmentScheme",
        "ScheduleSlot",
        "ComponentScore",
        "CriterionScore",
        "SelfWorkTopic",
        "SelfWorkMark",
        "CourseWork",
        "FinalGrade",
        "ResitRecord",
        "RubricCriterion",
        "StudentAcademicRecord",
        "GroupTransferEvidence",
    )
    _set_rls_bypass(schema_editor, True)
    try:
        if any(
            apps.get_model("registrar", model_name).objects.exists() for model_name in protected_models
        ) or _conditional_history_exists(apps):
            raise RuntimeError(_REVERSE_STOP)
    finally:
        _set_rls_bypass(schema_editor, False)


def _noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_alter_auditlog_action"),
        ("registrar", "0044_criterion_score_component_identity"),
    ]

    operations = [
        migrations.CreateModel(
            name="GroupTransferEvidence",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("actor_ref", models.PositiveBigIntegerField()),
                ("transaction_id", models.CharField(max_length=64)),
                ("expected_enrollment_ids", models.JSONField(default=list)),
                ("audit_ref", models.UUIDField(blank=True, null=True)),
                ("is_finalized", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "new_group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="organizations.orgunit",
                    ),
                ),
                (
                    "old_group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="organizations.orgunit",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="group_transfer_evidence",
                        to="organizations.organization",
                    ),
                ),
                (
                    "period",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="organizations.academicperiod",
                    ),
                ),
                (
                    "record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="group_transfer_evidence",
                        to="registrar.studentacademicrecord",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["organization", "record", "-created_at"],
                        name="reg_group_evidence_lookup_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("record", "transaction_id"),
                        name="uniq_group_transfer_record_transaction",
                    )
                ],
            },
        ),
        migrations.RunPython(_install_postgres_guards, _remove_postgres_guards),
        migrations.RunPython(_noop, _ensure_safe_reverse),
    ]

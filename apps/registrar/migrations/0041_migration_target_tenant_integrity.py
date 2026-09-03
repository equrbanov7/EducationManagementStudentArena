"""Protect the legacy-migration registrar target graph at database level.

The guards deliberately stop on pre-existing violations.  They never rewrite
academic rows or infer memberships during deployment.
"""

from django.db import migrations

_FUNCTION_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_member_has_permission(
    target_organization uuid,
    target_user bigint,
    required_permission text
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
    SELECT EXISTS (
        SELECT 1
          FROM public.organizations_membership membership
          JOIN public.organizations_role role
            ON role.id = membership.role_id
           AND role.organization_id = target_organization
           AND role.is_active
         WHERE membership.organization_id = target_organization
           AND membership.user_id = target_user
           AND membership.is_active
           AND (
               required_permission = ''
               OR (
                   required_permission = 'grade.input'
                   AND (
                       COALESCE(role.permissions, '[]'::jsonb) ? 'grade.input'
                       OR COALESCE(role.permissions, '[]'::jsonb) ? 'grading.input'
                       OR COALESCE(role.permissions, '[]'::jsonb) ? 'grade.*'
                       OR COALESCE(role.permissions, '[]'::jsonb) ? 'grading.*'
                       OR COALESCE(role.permissions, '[]'::jsonb) ? '*'
                   )
               )
           )
    );
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_organization_immutable()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
        RAISE EXCEPTION 'registrar target organization is immutable'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_same_org_fk()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    relation_id uuid;
    parent_organization uuid;
BEGIN
    relation_id := NULLIF(to_jsonb(NEW) ->> TG_ARGV[0], '')::uuid;
    IF relation_id IS NULL THEN
        RETURN NEW;
    END IF;

    EXECUTE format(
        'SELECT organization_id FROM public.%%I WHERE id = $1',
        TG_ARGV[1]
    ) INTO parent_organization USING relation_id;

    -- Dynamic EXECUTE does not update PL/pgSQL's FOUND flag.  A missing row
    -- leaves this required parent organization NULL, which DISTINCT catches.
    IF parent_organization IS DISTINCT FROM NEW.organization_id THEN
        RAISE EXCEPTION 'registrar target parent must belong to the same organization: %%', TG_ARGV[2]
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_active_member()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    target_user bigint;
    required_permission text := TG_ARGV[1];
BEGIN
    target_user := NULLIF(to_jsonb(NEW) ->> TG_ARGV[0], '')::bigint;
    IF target_user IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT public.registrar_member_has_permission(
        NEW.organization_id,
        target_user,
        required_permission
    ) THEN
        RAISE EXCEPTION 'registrar user reference lacks an active authorized membership: %%', TG_ARGV[2]
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_student_record_coherence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    curriculum_program uuid;
BEGIN
    SELECT curriculum.program_id
      INTO curriculum_program
      FROM public.registrar_curriculum curriculum
     WHERE curriculum.id = NEW.curriculum_id;
    IF NOT FOUND OR curriculum_program IS DISTINCT FROM NEW.program_id THEN
        RAISE EXCEPTION 'student record curriculum must belong to its program'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_lesson_mark_coherence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    lesson_offering uuid;
    enrollment_offering uuid;
BEGIN
    SELECT lesson.offering_id
      INTO lesson_offering
      FROM public.registrar_lesson lesson
     WHERE lesson.id = NEW.lesson_id;
    SELECT enrollment.offering_id
      INTO enrollment_offering
      FROM public.registrar_enrollment enrollment
     WHERE enrollment.id = NEW.enrollment_id;
    IF lesson_offering IS NULL
       OR enrollment_offering IS NULL
       OR lesson_offering IS DISTINCT FROM enrollment_offering THEN
        RAISE EXCEPTION 'lesson mark lesson and enrollment must share an offering'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_component_score_coherence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    component_offering uuid;
    enrollment_offering uuid;
BEGIN
    SELECT component.offering_id
      INTO component_offering
      FROM public.registrar_assessmentcomponent component
     WHERE component.id = NEW.component_id;
    SELECT enrollment.offering_id
      INTO enrollment_offering
      FROM public.registrar_enrollment enrollment
     WHERE enrollment.id = NEW.enrollment_id;
    IF component_offering IS NULL
       OR enrollment_offering IS NULL
       OR component_offering IS DISTINCT FROM enrollment_offering THEN
        RAISE EXCEPTION 'component score component and enrollment must share an offering'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_offering_course_organization()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    course_organization uuid;
BEGIN
    IF NEW.course_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT course.organization_id
      INTO course_organization
      FROM public.courses_course course
     WHERE course.id = NEW.course_id;
    IF NOT FOUND OR course_organization IS DISTINCT FROM NEW.organization_id THEN
        RAISE EXCEPTION 'offering course must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_assert_migration_target_integrity()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.registrar_program child
          JOIN public.organizations_orgunit parent ON parent.id = child.specialty_unit_id
         WHERE child.specialty_unit_id IS NOT NULL
           AND child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_curriculum child
          JOIN public.registrar_program parent ON parent.id = child.program_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_curriculumsubject child
          JOIN public.registrar_curriculum curriculum ON curriculum.id = child.curriculum_id
          JOIN public.registrar_subject subject ON subject.id = child.subject_id
         WHERE child.organization_id IS DISTINCT FROM curriculum.organization_id
            OR child.organization_id IS DISTINCT FROM subject.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_studentacademicrecord child
          JOIN public.registrar_program program ON program.id = child.program_id
          JOIN public.registrar_curriculum curriculum ON curriculum.id = child.curriculum_id
          LEFT JOIN public.organizations_orgunit group_unit ON group_unit.id = child.group_id
         WHERE child.organization_id IS DISTINCT FROM program.organization_id
            OR child.organization_id IS DISTINCT FROM curriculum.organization_id
            OR (child.group_id IS NOT NULL AND child.organization_id IS DISTINCT FROM group_unit.organization_id)
            OR child.program_id IS DISTINCT FROM curriculum.program_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_courseoffering child
          JOIN public.registrar_subject subject ON subject.id = child.subject_id
          JOIN public.organizations_academicperiod period ON period.id = child.period_id
          LEFT JOIN public.organizations_orgunit group_unit ON group_unit.id = child.group_id
          LEFT JOIN public.courses_course course ON course.id = child.course_id
         WHERE child.organization_id IS DISTINCT FROM subject.organization_id
            OR child.organization_id IS DISTINCT FROM period.organization_id
            OR (child.group_id IS NOT NULL AND child.organization_id IS DISTINCT FROM group_unit.organization_id)
            OR (child.course_id IS NOT NULL AND child.organization_id IS DISTINCT FROM course.organization_id)
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_enrollment child
          JOIN public.registrar_courseoffering parent ON parent.id = child.offering_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_scheduleslot child
          JOIN public.registrar_courseoffering parent ON parent.id = child.offering_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_assessmentscheme child
          JOIN public.registrar_courseoffering parent ON parent.id = child.offering_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_lesson child
          JOIN public.registrar_courseoffering parent ON parent.id = child.offering_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_lessonmark child
          JOIN public.registrar_lesson lesson ON lesson.id = child.lesson_id
          JOIN public.registrar_enrollment enrollment ON enrollment.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM lesson.organization_id
            OR child.organization_id IS DISTINCT FROM enrollment.organization_id
            OR lesson.offering_id IS DISTINCT FROM enrollment.offering_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_assessmentcomponent child
          JOIN public.registrar_courseoffering parent ON parent.id = child.offering_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_componentscore child
          JOIN public.registrar_assessmentcomponent component ON component.id = child.component_id
          JOIN public.registrar_enrollment enrollment ON enrollment.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM component.organization_id
            OR child.organization_id IS DISTINCT FROM enrollment.organization_id
            OR component.offering_id IS DISTINCT FROM enrollment.offering_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_finalgrade child
          JOIN public.registrar_enrollment parent ON parent.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) THEN
        RAISE EXCEPTION 'registrar migration target cross-organization precheck failed'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM public.registrar_studentacademicrecord record
         WHERE NOT public.registrar_member_has_permission(record.organization_id, record.student_id, '')
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_enrollment enrollment
         WHERE NOT public.registrar_member_has_permission(enrollment.organization_id, enrollment.student_id, '')
    ) THEN
        RAISE EXCEPTION 'registrar migration target student membership precheck failed'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM public.registrar_courseoffering offering
         WHERE offering.instructor_id IS NOT NULL
           AND NOT public.registrar_member_has_permission(
               offering.organization_id,
               offering.instructor_id,
               'grade.input'
           )
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_lesson lesson
         WHERE lesson.instructor_id IS NOT NULL
           AND NOT public.registrar_member_has_permission(
               lesson.organization_id,
               lesson.instructor_id,
               'grade.input'
           )
    ) THEN
        RAISE EXCEPTION 'registrar migration target instructor membership precheck failed'
            USING ERRCODE = '23514';
    END IF;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_member_has_permission(uuid, bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_organization_immutable() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_same_org_fk() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_active_member() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_student_record_coherence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_lesson_mark_coherence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_component_score_coherence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_offering_course_organization() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_assert_migration_target_integrity() FROM PUBLIC;
"""

_SAME_ORG_LINKS = [
    ("registrar_program", "specialty_unit_id", "organizations_orgunit", "specialty_unit"),
    ("registrar_curriculum", "program_id", "registrar_program", "program"),
    ("registrar_curriculumsubject", "curriculum_id", "registrar_curriculum", "curriculum"),
    ("registrar_curriculumsubject", "subject_id", "registrar_subject", "subject"),
    ("registrar_studentacademicrecord", "program_id", "registrar_program", "program"),
    ("registrar_studentacademicrecord", "curriculum_id", "registrar_curriculum", "curriculum"),
    ("registrar_studentacademicrecord", "group_id", "organizations_orgunit", "group"),
    ("registrar_courseoffering", "subject_id", "registrar_subject", "subject"),
    ("registrar_courseoffering", "period_id", "organizations_academicperiod", "period"),
    ("registrar_courseoffering", "group_id", "organizations_orgunit", "group"),
    ("registrar_enrollment", "offering_id", "registrar_courseoffering", "offering"),
    ("registrar_scheduleslot", "offering_id", "registrar_courseoffering", "offering"),
    ("registrar_assessmentscheme", "offering_id", "registrar_courseoffering", "offering"),
    ("registrar_lesson", "offering_id", "registrar_courseoffering", "offering"),
    ("registrar_lessonmark", "lesson_id", "registrar_lesson", "lesson"),
    ("registrar_lessonmark", "enrollment_id", "registrar_enrollment", "enrollment"),
    ("registrar_assessmentcomponent", "offering_id", "registrar_courseoffering", "offering"),
    ("registrar_componentscore", "component_id", "registrar_assessmentcomponent", "component"),
    ("registrar_componentscore", "enrollment_id", "registrar_enrollment", "enrollment"),
    ("registrar_finalgrade", "enrollment_id", "registrar_enrollment", "enrollment"),
]

_IMMUTABLE_TABLES = sorted(
    {table for table, _field, _parent, _label in _SAME_ORG_LINKS}
    | {parent for _table, _field, parent, _label in _SAME_ORG_LINKS}
    | {"courses_course"}
)

_MEMBER_LINKS = [
    ("registrar_studentacademicrecord", "student_id", "", "student"),
    ("registrar_enrollment", "student_id", "", "student"),
    ("registrar_courseoffering", "instructor_id", "grade.input", "instructor"),
    ("registrar_lesson", "instructor_id", "grade.input", "instructor"),
]

_COHERENCE_LINKS = [
    (
        "registrar_courseoffering",
        "course_id, organization_id",
        "registrar_guard_offering_course_organization",
    ),
    (
        "registrar_studentacademicrecord",
        "program_id, curriculum_id, organization_id",
        "registrar_guard_student_record_coherence",
    ),
    (
        "registrar_lessonmark",
        "lesson_id, enrollment_id, organization_id",
        "registrar_guard_lesson_mark_coherence",
    ),
    (
        "registrar_componentscore",
        "component_id, enrollment_id, organization_id",
        "registrar_guard_component_score_coherence",
    ),
]

_FUNCTIONS = [
    "registrar_assert_migration_target_integrity()",
    "registrar_guard_offering_course_organization()",
    "registrar_guard_component_score_coherence()",
    "registrar_guard_lesson_mark_coherence()",
    "registrar_guard_student_record_coherence()",
    "registrar_guard_active_member()",
    "registrar_guard_same_org_fk()",
    "registrar_guard_organization_immutable()",
    "registrar_member_has_permission(uuid, bigint, text)",
]


def _trigger_name(prefix, field):
    return f"registrar_{prefix}_{field.removesuffix('_id')}_guard"


def _install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    # FORCE-RLS applies even to a non-superuser table owner.  The precheck must
    # inspect every tenant, so use the existing policy's transaction-local
    # migration bypass and clear it again before this operation returns.
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_FUNCTION_SQL)
    schema_editor.execute("SELECT public.registrar_assert_migration_target_integrity()")

    for table in _IMMUTABLE_TABLES:
        name = "registrar_organization_immutable_guard"
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE UPDATE OF organization_id ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_organization_immutable()"
        )

    for table, field, parent, label in _SAME_ORG_LINKS:
        name = _trigger_name("same_org", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF {field}, organization_id ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_org_fk('{field}', '{parent}', '{label}')"
        )

    for table, field, permission, label in _MEMBER_LINKS:
        name = _trigger_name("active_member", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF {field}, organization_id ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_active_member('{field}', '{permission}', '{label}')"
        )

    for table, fields, function_name in _COHERENCE_LINKS:
        name = f"registrar_{function_name.removeprefix('registrar_guard_')}_guard"
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF {fields} ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{function_name}()"
        )
    schema_editor.execute("SET LOCAL app.bypass_rls = 'off'")


def _remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, fields, function_name in reversed(_COHERENCE_LINKS):
        del fields
        name = f"registrar_{function_name.removeprefix('registrar_guard_')}_guard"
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
    for table, field, _permission, _label in reversed(_MEMBER_LINKS):
        name = _trigger_name("active_member", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
    for table, field, _parent, _label in reversed(_SAME_ORG_LINKS):
        name = _trigger_name("same_org", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
    for table in reversed(_IMMUTABLE_TABLES):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_organization_immutable_guard ON public.{table}")
    for function_signature in _FUNCTIONS:
        schema_editor.execute(f"DROP FUNCTION IF EXISTS public.{function_signature}")


class Migration(migrations.Migration):
    dependencies = [("registrar", "0040_assessment_scheme_publish_invariant")]

    operations = [
        migrations.RunPython(_install_postgres_guards, _remove_postgres_guards),
    ]

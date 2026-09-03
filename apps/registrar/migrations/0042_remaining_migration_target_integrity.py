"""Protect the remaining legacy-migration registrar target relations.

This is deliberately a stop-only migration: the precheck reports historical
tenant/coherence defects and never rewrites academic or audit evidence.
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
          JOIN public.organizations_organization organization
            ON organization.id = membership.organization_id
           AND organization.is_active
          JOIN public.organizations_role role
            ON role.id = membership.role_id
           AND role.organization_id = target_organization
           AND role.is_active
          JOIN public.auth_user actor
            ON actor.id = membership.user_id
           AND actor.is_active
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

CREATE OR REPLACE FUNCTION public.registrar_actor_belongs_to_organization(
    target_organization uuid,
    target_user bigint
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
         WHERE membership.organization_id = target_organization
           AND membership.user_id = target_user
    ) OR EXISTS (
        SELECT 1
          FROM public.organizations_organization organization
         WHERE organization.id = target_organization
           AND organization.owner_id = target_user
    ) OR EXISTS (
        SELECT 1
          FROM public.auth_user actor
         WHERE actor.id = target_user
           AND actor.is_superuser
    );
$function$;

CREATE OR REPLACE FUNCTION public.registrar_actor_can_write_for_organization(
    target_organization uuid,
    target_user bigint
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
          JOIN public.organizations_organization organization
            ON organization.id = membership.organization_id
           AND organization.is_active
          JOIN public.organizations_role role
            ON role.id = membership.role_id
           AND role.organization_id = target_organization
           AND role.is_active
          JOIN public.auth_user actor
            ON actor.id = membership.user_id
           AND actor.is_active
         WHERE membership.organization_id = target_organization
           AND membership.user_id = target_user
           AND membership.is_active
    ) OR EXISTS (
        SELECT 1
          FROM public.organizations_organization organization
          JOIN public.auth_user actor
            ON actor.id = organization.owner_id
           AND actor.is_active
         WHERE organization.id = target_organization
           AND organization.is_active
           AND organization.owner_id = target_user
    ) OR EXISTS (
        SELECT 1
          FROM public.auth_user actor
          JOIN public.organizations_organization organization
            ON organization.id = target_organization
           AND organization.is_active
         WHERE actor.id = target_user
           AND actor.is_active
           AND actor.is_superuser
    );
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_same_org_actor()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    target_user bigint;
BEGIN
    target_user := NULLIF(to_jsonb(NEW) ->> TG_ARGV[0], '')::bigint;
    IF target_user IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT public.registrar_actor_can_write_for_organization(
        NEW.organization_id,
        target_user
    ) THEN
        RAISE EXCEPTION 'registrar actor must belong to the same organization: %%', TG_ARGV[1]
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_same_org_historical_actor()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    target_user bigint;
BEGIN
    target_user := NULLIF(to_jsonb(NEW) ->> TG_ARGV[0], '')::bigint;
    IF target_user IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT public.registrar_actor_belongs_to_organization(
        NEW.organization_id,
        target_user
    ) THEN
        RAISE EXCEPTION 'registrar historical actor must belong to the same organization: %%', TG_ARGV[1]
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_same_offering_pair()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    left_id uuid;
    right_id uuid;
    left_offering uuid;
    right_offering uuid;
BEGIN
    left_id := NULLIF(to_jsonb(NEW) ->> TG_ARGV[0], '')::uuid;
    right_id := NULLIF(to_jsonb(NEW) ->> TG_ARGV[2], '')::uuid;
    IF left_id IS NULL OR right_id IS NULL THEN
        RAISE EXCEPTION 'registrar offering-coherence relation is required: %%', TG_ARGV[4]
            USING ERRCODE = '23514';
    END IF;

    EXECUTE format(
        'SELECT offering_id FROM public.%%I WHERE id = $1',
        TG_ARGV[1]
    ) INTO left_offering USING left_id;
    EXECUTE format(
        'SELECT offering_id FROM public.%%I WHERE id = $1',
        TG_ARGV[3]
    ) INTO right_offering USING right_id;

    IF left_offering IS NULL
       OR right_offering IS NULL
       OR left_offering IS DISTINCT FROM right_offering THEN
        RAISE EXCEPTION 'registrar relations must share an offering: %%', TG_ARGV[4]
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_criterion_score_coherence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    criterion_rubric uuid;
    enrollment_offering uuid;
BEGIN
    SELECT criterion.rubric_id
      INTO criterion_rubric
      FROM public.registrar_rubriccriterion criterion
     WHERE criterion.id = NEW.criterion_id;
    SELECT enrollment.offering_id
      INTO enrollment_offering
      FROM public.registrar_enrollment enrollment
     WHERE enrollment.id = NEW.enrollment_id;

    IF criterion_rubric IS NULL
       OR enrollment_offering IS NULL
       OR NOT EXISTS (
           SELECT 1
             FROM public.registrar_assessmentcomponent component
            WHERE component.rubric_id = criterion_rubric
              AND component.offering_id = enrollment_offering
       ) THEN
        RAISE EXCEPTION 'criterion score rubric must be attached to the enrollment offering'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

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
        - 'updated_at'
        - 'corrected_by_id'
        - 'old_instructor_id'
        - 'new_instructor_id'
        - 'lesson_id';
    new_payload := to_jsonb(NEW)
        - 'updated_at'
        - 'corrected_by_id'
        - 'old_instructor_id'
        - 'new_instructor_id'
        - 'lesson_id';
    IF new_payload IS DISTINCT FROM old_payload THEN
        RAISE EXCEPTION 'registrar correction evidence is immutable'
            USING ERRCODE = '23514';
    END IF;

    old_actor := to_jsonb(OLD) ->> 'corrected_by_id';
    new_actor := to_jsonb(NEW) ->> 'corrected_by_id';
    IF new_actor IS DISTINCT FROM old_actor AND new_actor IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction actor cannot be reassigned'
            USING ERRCODE = '23514';
    END IF;

    old_instructor := to_jsonb(OLD) ->> 'old_instructor_id';
    new_instructor := to_jsonb(NEW) ->> 'old_instructor_id';
    IF new_instructor IS DISTINCT FROM old_instructor AND new_instructor IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction old instructor cannot be reassigned'
            USING ERRCODE = '23514';
    END IF;
    old_instructor := to_jsonb(OLD) ->> 'new_instructor_id';
    new_instructor := to_jsonb(NEW) ->> 'new_instructor_id';
    IF new_instructor IS DISTINCT FROM old_instructor AND new_instructor IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction new instructor cannot be reassigned'
            USING ERRCODE = '23514';
    END IF;

    old_lesson := to_jsonb(OLD) ->> 'lesson_id';
    new_lesson := to_jsonb(NEW) ->> 'lesson_id';
    IF new_lesson IS DISTINCT FROM old_lesson AND new_lesson IS NOT NULL THEN
        RAISE EXCEPTION 'registrar correction lesson cannot be reassigned'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_assert_remaining_target_integrity()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.registrar_groupelectivechoice child
          JOIN public.organizations_orgunit group_unit ON group_unit.id = child.group_id
          JOIN public.organizations_academicperiod period ON period.id = child.period_id
          JOIN public.registrar_subject subject ON subject.id = child.chosen_subject_id
         WHERE child.organization_id IS DISTINCT FROM group_unit.organization_id
            OR child.organization_id IS DISTINCT FROM period.organization_id
            OR child.organization_id IS DISTINCT FROM subject.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_rubriccriterion child
          JOIN public.registrar_rubric parent ON parent.id = child.rubric_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_assessmentcomponent child
          JOIN public.registrar_rubric parent ON parent.id = child.rubric_id
         WHERE child.rubric_id IS NOT NULL
           AND child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_criterionscore child
          JOIN public.registrar_rubriccriterion criterion ON criterion.id = child.criterion_id
          JOIN public.registrar_enrollment enrollment ON enrollment.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM criterion.organization_id
            OR child.organization_id IS DISTINCT FROM enrollment.organization_id
            OR NOT EXISTS (
                SELECT 1
                  FROM public.registrar_assessmentcomponent component
                 WHERE component.rubric_id = criterion.rubric_id
                   AND component.offering_id = enrollment.offering_id
            )
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_selfworktopic child
          JOIN public.registrar_courseoffering parent ON parent.id = child.offering_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_selfworkmark child
          JOIN public.registrar_selfworktopic topic ON topic.id = child.topic_id
          JOIN public.registrar_enrollment enrollment ON enrollment.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM topic.organization_id
            OR child.organization_id IS DISTINCT FROM enrollment.organization_id
            OR topic.offering_id IS DISTINCT FROM enrollment.offering_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_coursework child
          JOIN public.registrar_enrollment parent ON parent.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_resitrecord child
          JOIN public.registrar_enrollment parent ON parent.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_journalcorrection child
          JOIN public.registrar_lessonmark parent ON parent.id = child.lesson_mark_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_lessoncorrection child
          JOIN public.registrar_lesson parent ON parent.id = child.lesson_id
         WHERE child.lesson_id IS NOT NULL
           AND child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_selfworkcorrection child
          JOIN public.registrar_selfworktopic topic ON topic.id = child.topic_id
          JOIN public.registrar_enrollment enrollment ON enrollment.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM topic.organization_id
            OR child.organization_id IS DISTINCT FROM enrollment.organization_id
            OR topic.offering_id IS DISTINCT FROM enrollment.offering_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_courseworkcorrection child
          JOIN public.registrar_enrollment parent ON parent.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM parent.organization_id
    ) OR EXISTS (
        SELECT 1
          FROM public.registrar_componentscorecorrection child
          JOIN public.registrar_assessmentcomponent component ON component.id = child.component_id
          JOIN public.registrar_enrollment enrollment ON enrollment.id = child.enrollment_id
         WHERE child.organization_id IS DISTINCT FROM component.organization_id
            OR child.organization_id IS DISTINCT FROM enrollment.organization_id
            OR component.offering_id IS DISTINCT FROM enrollment.offering_id
    ) THEN
        RAISE EXCEPTION 'remaining registrar migration target relation precheck failed'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.registrar_groupelectivechoice child
         WHERE child.decided_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.decided_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_scheduleslot child
         WHERE child.created_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.created_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_assessmentscheme child
         WHERE (child.submitted_by_id IS NOT NULL AND NOT public.registrar_actor_belongs_to_organization(
                    child.organization_id, child.submitted_by_id
               ))
            OR (child.chair_approved_by_id IS NOT NULL AND NOT public.registrar_actor_belongs_to_organization(
                    child.organization_id, child.chair_approved_by_id
               ))
            OR (child.dean_approved_by_id IS NOT NULL AND NOT public.registrar_actor_belongs_to_organization(
                    child.organization_id, child.dean_approved_by_id
               ))
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_lesson child
         WHERE child.created_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.created_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_lessonmark child
         WHERE child.entered_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.entered_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_componentscore child
         WHERE child.entered_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.entered_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_criterionscore child
         WHERE child.entered_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.entered_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_selfworkmark child
         WHERE child.entered_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.entered_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_coursework child
         WHERE child.entered_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.entered_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_finalgrade child
         WHERE child.entered_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.entered_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_resitrecord child
         WHERE child.decided_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.decided_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_journalcorrection child
         WHERE child.corrected_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.corrected_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_lessoncorrection child
         WHERE (child.corrected_by_id IS NOT NULL AND NOT public.registrar_actor_belongs_to_organization(
                    child.organization_id, child.corrected_by_id
               ))
            OR (child.old_instructor_id IS NOT NULL AND NOT public.registrar_actor_belongs_to_organization(
                    child.organization_id, child.old_instructor_id
               ))
            OR (child.new_instructor_id IS NOT NULL AND NOT public.registrar_actor_belongs_to_organization(
                    child.organization_id, child.new_instructor_id
               ))
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_selfworkcorrection child
         WHERE child.corrected_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.corrected_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_courseworkcorrection child
         WHERE child.corrected_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.corrected_by_id
           )
    ) OR EXISTS (
        SELECT 1 FROM public.registrar_componentscorecorrection child
         WHERE child.corrected_by_id IS NOT NULL
           AND NOT public.registrar_actor_belongs_to_organization(
               child.organization_id, child.corrected_by_id
           )
    ) THEN
        RAISE EXCEPTION 'remaining registrar migration target actor precheck failed'
            USING ERRCODE = '23514';
    END IF;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_actor_belongs_to_organization(uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_actor_can_write_for_organization(uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_member_has_permission(uuid, bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_same_org_actor() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_same_org_historical_actor() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_same_offering_pair() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_criterion_score_coherence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_correction_evidence_immutable() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_assert_remaining_target_integrity() FROM PUBLIC;
"""

_RESTORE_0041_MEMBER_FUNCTION_SQL = r"""
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
REVOKE ALL ON FUNCTION public.registrar_member_has_permission(uuid, bigint, text) FROM PUBLIC;
"""


_SAME_ORG_LINKS = [
    ("registrar_groupelectivechoice", "group_id", "organizations_orgunit", "group"),
    ("registrar_groupelectivechoice", "period_id", "organizations_academicperiod", "period"),
    ("registrar_groupelectivechoice", "chosen_subject_id", "registrar_subject", "chosen_subject"),
    ("registrar_rubriccriterion", "rubric_id", "registrar_rubric", "rubric"),
    ("registrar_assessmentcomponent", "rubric_id", "registrar_rubric", "rubric"),
    ("registrar_criterionscore", "criterion_id", "registrar_rubriccriterion", "criterion"),
    ("registrar_criterionscore", "enrollment_id", "registrar_enrollment", "enrollment"),
    ("registrar_selfworktopic", "offering_id", "registrar_courseoffering", "offering"),
    ("registrar_selfworkmark", "topic_id", "registrar_selfworktopic", "topic"),
    ("registrar_selfworkmark", "enrollment_id", "registrar_enrollment", "enrollment"),
    ("registrar_coursework", "enrollment_id", "registrar_enrollment", "enrollment"),
    ("registrar_resitrecord", "enrollment_id", "registrar_enrollment", "enrollment"),
    ("registrar_journalcorrection", "lesson_mark_id", "registrar_lessonmark", "lesson_mark"),
    ("registrar_lessoncorrection", "lesson_id", "registrar_lesson", "lesson"),
    ("registrar_selfworkcorrection", "topic_id", "registrar_selfworktopic", "topic"),
    ("registrar_selfworkcorrection", "enrollment_id", "registrar_enrollment", "enrollment"),
    ("registrar_courseworkcorrection", "enrollment_id", "registrar_enrollment", "enrollment"),
    (
        "registrar_componentscorecorrection",
        "component_id",
        "registrar_assessmentcomponent",
        "component",
    ),
    ("registrar_componentscorecorrection", "enrollment_id", "registrar_enrollment", "enrollment"),
]

_NEW_IMMUTABLE_TABLES = [
    "registrar_groupelectivechoice",
    "registrar_rubric",
    "registrar_rubriccriterion",
    "registrar_criterionscore",
    "registrar_selfworktopic",
    "registrar_selfworkmark",
    "registrar_coursework",
    "registrar_resitrecord",
    "registrar_journalcorrection",
    "registrar_lessoncorrection",
    "registrar_selfworkcorrection",
    "registrar_courseworkcorrection",
    "registrar_componentscorecorrection",
]

_ACTOR_LINKS = [
    ("registrar_groupelectivechoice", "decided_by_id", "decided_by"),
    ("registrar_scheduleslot", "created_by_id", "created_by"),
    ("registrar_assessmentscheme", "submitted_by_id", "submitted_by"),
    ("registrar_assessmentscheme", "chair_approved_by_id", "chair_approved_by"),
    ("registrar_assessmentscheme", "dean_approved_by_id", "dean_approved_by"),
    ("registrar_lesson", "created_by_id", "created_by"),
    ("registrar_lessonmark", "entered_by_id", "entered_by"),
    ("registrar_componentscore", "entered_by_id", "entered_by"),
    ("registrar_criterionscore", "entered_by_id", "entered_by"),
    ("registrar_selfworkmark", "entered_by_id", "entered_by"),
    ("registrar_coursework", "entered_by_id", "entered_by"),
    ("registrar_finalgrade", "entered_by_id", "entered_by"),
    ("registrar_resitrecord", "decided_by_id", "decided_by"),
    ("registrar_journalcorrection", "corrected_by_id", "corrected_by"),
    ("registrar_lessoncorrection", "corrected_by_id", "corrected_by"),
    ("registrar_selfworkcorrection", "corrected_by_id", "corrected_by"),
    ("registrar_courseworkcorrection", "corrected_by_id", "corrected_by"),
    ("registrar_componentscorecorrection", "corrected_by_id", "corrected_by"),
]

_HISTORICAL_ACTOR_LINKS = [
    ("registrar_lessoncorrection", "old_instructor_id", "old_instructor"),
]

_ACTIVE_MEMBER_LINKS = [
    ("registrar_lessoncorrection", "new_instructor_id", "grade.input", "new_instructor"),
]

_OFFERING_PAIRS = [
    (
        "registrar_selfworkmark",
        "topic_id",
        "registrar_selfworktopic",
        "enrollment_id",
        "registrar_enrollment",
        "self-work mark",
    ),
    (
        "registrar_selfworkcorrection",
        "topic_id",
        "registrar_selfworktopic",
        "enrollment_id",
        "registrar_enrollment",
        "self-work correction",
    ),
    (
        "registrar_componentscorecorrection",
        "component_id",
        "registrar_assessmentcomponent",
        "enrollment_id",
        "registrar_enrollment",
        "component correction",
    ),
]

_CORRECTION_TABLES = [
    "registrar_journalcorrection",
    "registrar_lessoncorrection",
    "registrar_selfworkcorrection",
    "registrar_courseworkcorrection",
    "registrar_componentscorecorrection",
]

_FUNCTIONS = [
    "registrar_assert_remaining_target_integrity()",
    "registrar_guard_correction_evidence_immutable()",
    "registrar_guard_criterion_score_coherence()",
    "registrar_guard_same_offering_pair()",
    "registrar_guard_same_org_historical_actor()",
    "registrar_guard_same_org_actor()",
    "registrar_actor_can_write_for_organization(uuid, bigint)",
    "registrar_actor_belongs_to_organization(uuid, bigint)",
]


def _trigger_name(prefix, field):
    return f"registrar_{prefix}_{field.removesuffix('_id')}_guard"


def _install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_FUNCTION_SQL)
    schema_editor.execute("SELECT public.registrar_assert_remaining_target_integrity()")

    for table in _NEW_IMMUTABLE_TABLES:
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

    for table, field, label in _ACTOR_LINKS:
        name = _trigger_name("same_org_actor", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF {field}, organization_id ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_org_actor('{field}', '{label}')"
        )

    for table, field, label in _HISTORICAL_ACTOR_LINKS:
        name = _trigger_name("same_org_historical_actor", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF {field}, organization_id ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_org_historical_actor("
            f"'{field}', '{label}')"
        )

    for table, field, permission, label in _ACTIVE_MEMBER_LINKS:
        name = _trigger_name("active_member", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF {field}, organization_id ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_active_member('{field}', '{permission}', '{label}')"
        )

    for table, left_field, left_table, right_field, right_table, label in _OFFERING_PAIRS:
        name = "registrar_same_offering_pair_guard"
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF "
            f"{left_field}, {right_field}, organization_id ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_offering_pair("
            f"'{left_field}', '{left_table}', '{right_field}', '{right_table}', '{label}')"
        )

    name = "registrar_criterion_score_coherence_guard"
    table = "registrar_criterionscore"
    schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
    schema_editor.execute(
        f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF criterion_id, enrollment_id, organization_id "
        f"ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_criterion_score_coherence()"
    )

    for table in _CORRECTION_TABLES:
        name = "registrar_correction_evidence_immutable_guard"
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} BEFORE UPDATE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_correction_evidence_immutable()"
        )
    schema_editor.execute("SET LOCAL app.bypass_rls = 'off'")


def _remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(_CORRECTION_TABLES):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_correction_evidence_immutable_guard ON public.{table}")
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS registrar_criterion_score_coherence_guard ON public.registrar_criterionscore"
    )
    for table, _left_field, _left_table, _right_field, _right_table, _label in reversed(_OFFERING_PAIRS):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_same_offering_pair_guard ON public.{table}")
    for table, field, _permission, _label in reversed(_ACTIVE_MEMBER_LINKS):
        name = _trigger_name("active_member", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
    for table, field, _label in reversed(_HISTORICAL_ACTOR_LINKS):
        name = _trigger_name("same_org_historical_actor", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        # Compatibility cleanup for pre-final development installs where this
        # historical snapshot briefly used the active-actor trigger name.
        old_name = _trigger_name("same_org_actor", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {old_name} ON public.{table}")
    for table, field, _label in reversed(_ACTOR_LINKS):
        name = _trigger_name("same_org_actor", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
    for table, field, _parent, _label in reversed(_SAME_ORG_LINKS):
        name = _trigger_name("same_org", field)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
    for table in reversed(_NEW_IMMUTABLE_TABLES):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_organization_immutable_guard ON public.{table}")
    schema_editor.execute(_RESTORE_0041_MEMBER_FUNCTION_SQL)
    for function_signature in _FUNCTIONS:
        schema_editor.execute(f"DROP FUNCTION IF EXISTS public.{function_signature}")


class Migration(migrations.Migration):
    dependencies = [("registrar", "0041_migration_target_tenant_integrity")]

    operations = [
        migrations.RunPython(_install_postgres_guards, _remove_postgres_guards),
    ]

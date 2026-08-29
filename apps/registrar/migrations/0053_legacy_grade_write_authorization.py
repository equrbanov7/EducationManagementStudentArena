"""Bind legacy-grade evidence writes to an authenticated, RBAC-authorized actor.

0052 established tenant RLS and append-only storage.  This follow-up closes the
orthogonal tenant-internal authorization boundary: ordinary members must not be
able to forge imported source facts or append an Exam Center verification.
"""

from django.db import migrations

_FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_actor_can_import_legacy_grade(
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
           AND (
               COALESCE(role.permissions, '[]'::jsonb) ? '*'
               OR COALESCE(role.permissions, '[]'::jsonb) ? 'member.invite'
               OR COALESCE(role.permissions, '[]'::jsonb) ? 'member.*'
           )
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

CREATE OR REPLACE FUNCTION public.registrar_actor_can_review_legacy_grade(
    target_organization uuid,
    target_fact uuid,
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
           AND (
               COALESCE(role.permissions, '[]'::jsonb) ? '*'
               OR COALESCE(role.permissions, '[]'::jsonb) ? 'final_score.entry'
               OR COALESCE(role.permissions, '[]'::jsonb) ? 'final_score.*'
           )
           AND (
               role.scope_type = 'organization'
               OR (
                   role.scope_type = 'unit'
                   AND membership.scope_unit_id IS NOT NULL
                   AND EXISTS (
                       SELECT 1
                         FROM public.registrar_legacygradefact fact
                         JOIN public.registrar_enrollment enrollment
                           ON enrollment.id = fact.enrollment_id
                          AND enrollment.organization_id = target_organization
                         JOIN public.registrar_courseoffering offering
                           ON offering.id = enrollment.offering_id
                          AND offering.organization_id = target_organization
                         JOIN public.organizations_orgunit target_unit
                           ON target_unit.id = offering.group_id
                          AND target_unit.organization_id = target_organization
                          AND target_unit.is_active
                         JOIN public.organizations_orgunit scope_unit
                           ON scope_unit.id = membership.scope_unit_id
                          AND scope_unit.organization_id = target_organization
                          AND scope_unit.is_active
                        WHERE fact.id = target_fact
                          AND fact.organization_id = target_organization
                          AND (
                              target_unit.path = scope_unit.path
                              OR target_unit.path LIKE scope_unit.path || '/%%'
                          )
                   )
               )
           )
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

CREATE OR REPLACE FUNCTION public.registrar_guard_legacy_grade_fact_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    session_actor bigint;
BEGIN
    IF NEW.requires_exam_center_review IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'legacy grade fact requires exam-center review'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.mapping_status NOT IN (
        'linked', 'conflict', 'group_mismatch', 'discarded_source', 'unresolved'
    ) THEN
        RAISE EXCEPTION 'legacy grade fact mapping status is invalid'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.mapping_issue_code IS DISTINCT FROM (CASE NEW.mapping_status
        WHEN 'linked' THEN ''
        WHEN 'conflict' THEN 'legacy_grade_fact_conflict'
        WHEN 'group_mismatch' THEN 'legacy_grade_fact_group_mismatch'
        WHEN 'discarded_source' THEN 'legacy_grade_fact_discarded_source'
        WHEN 'unresolved' THEN 'legacy_grade_fact_unresolved'
    END) THEN
        RAISE EXCEPTION 'legacy grade fact mapping issue is inconsistent'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.mapping_status IN ('linked', 'conflict') THEN
        IF NEW.enrollment_id IS NULL OR COALESCE(NEW.source_enrollment_ref, '') = '' THEN
            RAISE EXCEPTION 'linked legacy grade fact requires source and target enrollment keys'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.enrollment_id IS NOT NULL THEN
        RAISE EXCEPTION 'unresolved legacy grade fact cannot target an enrollment'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.enrollment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
          FROM public.registrar_enrollment enrollment
         WHERE enrollment.id = NEW.enrollment_id
           AND enrollment.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'legacy grade fact enrollment must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    IF current_setting('app.bypass_rls', true) IS DISTINCT FROM 'on' THEN
        BEGIN
            session_actor := NULLIF(current_setting('app.current_user_id', true), '')::bigint;
        EXCEPTION WHEN invalid_text_representation THEN
            session_actor := NULL;
        END;
        IF session_actor IS NULL OR NOT public.registrar_actor_can_import_legacy_grade(
            NEW.organization_id,
            session_actor
        ) THEN
            RAISE EXCEPTION 'legacy grade fact import actor is not authorized'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_legacy_grade_review_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    session_actor bigint;
    expected_name text;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.registrar_legacygradefact fact
         WHERE fact.id = NEW.fact_id
           AND fact.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'legacy grade review fact must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.reviewed_by_id IS NULL OR NOT public.registrar_actor_can_write_for_organization(
        NEW.organization_id,
        NEW.reviewed_by_id
    ) THEN
        RAISE EXCEPTION 'legacy grade reviewer is not authorized for the organization'
            USING ERRCODE = '23514';
    END IF;
    SELECT COALESCE(
               NULLIF(BTRIM(actor.first_name || ' ' || actor.last_name), ''),
               actor.username
           )
      INTO expected_name
      FROM public.auth_user actor
     WHERE actor.id = NEW.reviewed_by_id
       AND actor.is_active;
    IF expected_name IS NULL OR NEW.reviewed_by_name IS DISTINCT FROM expected_name THEN
        RAISE EXCEPTION 'legacy grade reviewer name snapshot is invalid'
            USING ERRCODE = '23514';
    END IF;
    IF current_setting('app.bypass_rls', true) IS DISTINCT FROM 'on' THEN
        BEGIN
            session_actor := NULLIF(current_setting('app.current_user_id', true), '')::bigint;
        EXCEPTION WHEN invalid_text_representation THEN
            session_actor := NULL;
        END;
        IF session_actor IS NULL OR session_actor <> NEW.reviewed_by_id THEN
            RAISE EXCEPTION 'legacy grade reviewer must match the authenticated actor'
                USING ERRCODE = '23514';
        END IF;
        IF NOT public.registrar_actor_can_review_legacy_grade(
            NEW.organization_id,
            NEW.fact_id,
            NEW.reviewed_by_id
        ) THEN
            RAISE EXCEPTION 'legacy grade reviewer lacks final-score review permission'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_actor_can_import_legacy_grade(uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_actor_can_review_legacy_grade(uuid, uuid, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_legacy_grade_fact_insert() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_legacy_grade_review_insert() FROM PUBLIC;
"""


_REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_legacy_grade_fact_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF NEW.requires_exam_center_review IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'legacy grade fact requires exam-center review'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.enrollment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
          FROM public.registrar_enrollment enrollment
         WHERE enrollment.id = NEW.enrollment_id
           AND enrollment.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'legacy grade fact enrollment must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_legacy_grade_review_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM public.registrar_legacygradefact fact
         WHERE fact.id = NEW.fact_id
           AND fact.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'legacy grade review fact must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.reviewed_by_id IS NULL OR NOT public.registrar_actor_can_write_for_organization(
        NEW.organization_id,
        NEW.reviewed_by_id
    ) THEN
        RAISE EXCEPTION 'legacy grade reviewer is not authorized for the organization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_guard_legacy_grade_fact_insert() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_legacy_grade_review_insert() FROM PUBLIC;
DROP FUNCTION IF EXISTS public.registrar_actor_can_review_legacy_grade(uuid, uuid, bigint);
DROP FUNCTION IF EXISTS public.registrar_actor_can_import_legacy_grade(uuid, bigint);
"""


def _forward(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_FORWARD_SQL)


def _backward(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [("registrar", "0052_legacy_grade_evidence")]

    operations = [migrations.RunPython(_forward, _backward)]

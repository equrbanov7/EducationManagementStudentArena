"""Scope criterion evidence to one component and enforce atomic roll-ups."""

from collections import defaultdict
from decimal import Decimal, InvalidOperation

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Count

_BACKFILL_RESOLUTION_STOP = "registrar_0044_component_resolution_failed"
_BACKFILL_POINTS_STOP = "registrar_0044_points_invalid"
_BACKFILL_TOTAL_STOP = "registrar_0044_component_total_mismatch"
_REVERSE_DUPLICATE_STOP = "registrar_0044_reverse_duplicate_component_evidence"
_REVERSE_IDENTITY_STOP = "registrar_0044_reverse_component_identity_loss"


def _set_rls_bypass(schema_editor, enabled):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "SELECT set_config('app.bypass_rls', %s, true)",
            ["on" if enabled else "off"],
        )


def _backfill_component_identity(apps, schema_editor):
    CriterionScore = apps.get_model("registrar", "CriterionScore")
    ComponentScore = apps.get_model("registrar", "ComponentScore")
    AssessmentComponent = apps.get_model("registrar", "AssessmentComponent")
    _set_rls_bypass(schema_editor, True)
    try:
        assignments = []
        totals = defaultdict(lambda: Decimal("0"))
        component_max = {}
        for score in CriterionScore.objects.select_related("criterion", "enrollment").order_by("pk"):
            candidates = list(
                AssessmentComponent.objects.filter(
                    organization_id=score.organization_id,
                    offering_id=score.enrollment.offering_id,
                    rubric_id=score.criterion.rubric_id,
                ).values_list("pk", "max_score")[:2]
            )
            if len(candidates) != 1:
                raise RuntimeError(_BACKFILL_RESOLUTION_STOP)
            try:
                points = Decimal(score.points)
                points_are_valid = points.is_finite() and points >= 0 and points <= Decimal(score.criterion.max_points)
            except (InvalidOperation, TypeError, ValueError):
                points_are_valid = False
            if not points_are_valid:
                raise RuntimeError(_BACKFILL_POINTS_STOP)
            component_id, max_score = candidates[0]
            score.component_id = component_id
            assignments.append(score)
            key = (component_id, score.enrollment_id, score.organization_id)
            totals[key] += points
            component_max[key] = Decimal(max_score)

        for (component_id, enrollment_id, organization_id), total in totals.items():
            stored = list(
                ComponentScore.objects.filter(
                    organization_id=organization_id,
                    component_id=component_id,
                    enrollment_id=enrollment_id,
                ).values_list("score", flat=True)[:2]
            )
            expected = min(total, component_max[(component_id, enrollment_id, organization_id)])
            if len(stored) != 1 or Decimal(stored[0]) != expected:
                raise RuntimeError(_BACKFILL_TOTAL_STOP)

        if assignments:
            CriterionScore.objects.bulk_update(assignments, ["component"])
    finally:
        _set_rls_bypass(schema_editor, False)


def _ensure_safe_reverse(apps, schema_editor):
    CriterionScore = apps.get_model("registrar", "CriterionScore")
    AssessmentComponent = apps.get_model("registrar", "AssessmentComponent")
    _set_rls_bypass(schema_editor, True)
    try:
        duplicate = (
            CriterionScore.objects.values("criterion_id", "enrollment_id")
            .annotate(row_count=Count("pk"))
            .filter(row_count__gt=1)
            .exists()
        )
        if duplicate:
            raise RuntimeError(_REVERSE_DUPLICATE_STOP)
        for score in CriterionScore.objects.select_related("criterion", "enrollment").order_by("pk"):
            candidates = list(
                AssessmentComponent.objects.filter(
                    organization_id=score.organization_id,
                    offering_id=score.enrollment.offering_id,
                    rubric_id=score.criterion.rubric_id,
                ).values_list("pk", flat=True)[:2]
            )
            if len(candidates) != 1 or candidates[0] != score.component_id:
                raise RuntimeError(_REVERSE_IDENTITY_STOP)
    finally:
        _set_rls_bypass(schema_editor, False)


_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_guard_criterion_score_coherence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    component_org uuid;
    component_offering uuid;
    component_rubric uuid;
    criterion_org uuid;
    criterion_rubric uuid;
    criterion_max numeric;
    enrollment_org uuid;
    enrollment_offering uuid;
BEGIN
    SELECT organization_id, offering_id, rubric_id
      INTO component_org, component_offering, component_rubric
      FROM public.registrar_assessmentcomponent WHERE id = NEW.component_id;
    SELECT organization_id, rubric_id, max_points
      INTO criterion_org, criterion_rubric, criterion_max
      FROM public.registrar_rubriccriterion WHERE id = NEW.criterion_id;
    SELECT organization_id, offering_id
      INTO enrollment_org, enrollment_offering
      FROM public.registrar_enrollment WHERE id = NEW.enrollment_id;

    IF component_org IS NULL OR criterion_org IS NULL OR enrollment_org IS NULL
       OR component_rubric IS NULL
       OR NEW.organization_id IS DISTINCT FROM component_org
       OR NEW.organization_id IS DISTINCT FROM criterion_org
       OR NEW.organization_id IS DISTINCT FROM enrollment_org
       OR component_offering IS DISTINCT FROM enrollment_offering
       OR component_rubric IS DISTINCT FROM criterion_rubric
       OR NEW.points < 0 OR NEW.points > criterion_max THEN
        RAISE EXCEPTION 'criterion score component coherence violation'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_assert_criterion_component_integrity()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM public.registrar_criterionscore score
          LEFT JOIN public.registrar_assessmentcomponent component ON component.id = score.component_id
          LEFT JOIN public.registrar_rubriccriterion criterion ON criterion.id = score.criterion_id
          LEFT JOIN public.registrar_enrollment enrollment ON enrollment.id = score.enrollment_id
         WHERE component.id IS NULL OR criterion.id IS NULL OR enrollment.id IS NULL
            OR component.rubric_id IS NULL
            OR score.organization_id IS DISTINCT FROM component.organization_id
            OR score.organization_id IS DISTINCT FROM criterion.organization_id
            OR score.organization_id IS DISTINCT FROM enrollment.organization_id
            OR component.offering_id IS DISTINCT FROM enrollment.offering_id
            OR component.rubric_id IS DISTINCT FROM criterion.rubric_id
            OR score.points < 0 OR score.points > criterion.max_points
    ) OR EXISTS (
        SELECT 1
          FROM (
              SELECT score.component_id, score.enrollment_id, score.organization_id,
                     SUM(score.points) AS total_points, component.max_score
                FROM public.registrar_criterionscore score
                JOIN public.registrar_assessmentcomponent component ON component.id = score.component_id
               GROUP BY score.component_id, score.enrollment_id, score.organization_id, component.max_score
          ) totals
          LEFT JOIN public.registrar_componentscore component_score
            ON component_score.component_id = totals.component_id
           AND component_score.enrollment_id = totals.enrollment_id
           AND component_score.organization_id = totals.organization_id
         WHERE component_score.id IS NULL
            OR component_score.score IS DISTINCT FROM LEAST(totals.total_points, totals.max_score)
    ) THEN
        RAISE EXCEPTION 'criterion score component precheck failed'
            USING ERRCODE = '23514';
    END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_assert_rubric_score_total(
    target_component uuid,
    target_enrollment uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    expected numeric;
    target_org uuid;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.registrar_criterionscore
         WHERE component_id = target_component AND enrollment_id = target_enrollment
    ) THEN
        RETURN;
    END IF;
    SELECT LEAST(SUM(score.points), component.max_score), component.organization_id
      INTO expected, target_org
      FROM public.registrar_criterionscore score
      JOIN public.registrar_assessmentcomponent component ON component.id = score.component_id
     WHERE score.component_id = target_component AND score.enrollment_id = target_enrollment
     GROUP BY component.max_score, component.organization_id;
    IF NOT EXISTS (
        SELECT 1 FROM public.registrar_componentscore component_score
         WHERE component_score.component_id = target_component
           AND component_score.enrollment_id = target_enrollment
           AND component_score.organization_id = target_org
           AND component_score.score IS NOT DISTINCT FROM expected
    ) THEN
        RAISE EXCEPTION 'rubric criterion total must match component score'
            USING ERRCODE = '23514';
    END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_rubric_score_total()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF TG_OP <> 'INSERT' THEN
        PERFORM public.registrar_assert_rubric_score_total(OLD.component_id, OLD.enrollment_id);
    END IF;
    IF TG_OP <> 'DELETE' THEN
        PERFORM public.registrar_assert_rubric_score_total(NEW.component_id, NEW.enrollment_id);
    END IF;
    RETURN NULL;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_component_rubric_evidence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE component_id = OLD.id)
           OR EXISTS (SELECT 1 FROM public.registrar_componentscore WHERE component_id = OLD.id) THEN
            RAISE EXCEPTION 'component rubric evidence is protected' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF (EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE component_id = OLD.id)
        OR EXISTS (SELECT 1 FROM public.registrar_componentscore WHERE component_id = OLD.id))
       AND (NEW.organization_id IS DISTINCT FROM OLD.organization_id
            OR NEW.offering_id IS DISTINCT FROM OLD.offering_id
            OR NEW.name IS DISTINCT FROM OLD.name
            OR NEW.rubric_id IS DISTINCT FROM OLD.rubric_id
            OR NEW.max_score IS DISTINCT FROM OLD.max_score) THEN
        RAISE EXCEPTION 'component rubric evidence is protected' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_criterion_rubric_evidence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE criterion_id = OLD.id) THEN
            RAISE EXCEPTION 'criterion rubric evidence is protected' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF EXISTS (SELECT 1 FROM public.registrar_criterionscore WHERE criterion_id = OLD.id)
       AND (NEW.organization_id IS DISTINCT FROM OLD.organization_id
            OR NEW.rubric_id IS DISTINCT FROM OLD.rubric_id
            OR NEW.name IS DISTINCT FROM OLD.name
            OR NEW.max_points IS DISTINCT FROM OLD.max_points)
    THEN
        RAISE EXCEPTION 'criterion rubric evidence is protected' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_rubric_delete_with_evidence()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF EXISTS (
            SELECT 1 FROM public.registrar_criterionscore score
            JOIN public.registrar_rubriccriterion criterion ON criterion.id = score.criterion_id
            WHERE criterion.rubric_id = OLD.id
        ) THEN
            RAISE EXCEPTION 'rubric evidence is protected' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.registrar_criterionscore score
        JOIN public.registrar_rubriccriterion criterion ON criterion.id = score.criterion_id
        WHERE criterion.rubric_id = OLD.id
    ) AND (
        NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.name IS DISTINCT FROM OLD.name
    ) THEN
        RAISE EXCEPTION 'rubric evidence is protected' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.registrar_guard_rubric_evidence_no_truncate()
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
    IF EXISTS (SELECT 1 FROM public.registrar_criterionscore) THEN
        RAISE EXCEPTION 'rubric evidence cannot be truncated' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$function$;

REVOKE ALL ON FUNCTION public.registrar_guard_criterion_score_coherence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_assert_criterion_component_integrity() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_assert_rubric_score_total(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_rubric_score_total() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_component_rubric_evidence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_criterion_rubric_evidence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_rubric_delete_with_evidence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.registrar_guard_rubric_evidence_no_truncate() FROM PUBLIC;
"""

_RESTORE_0042_SQL = r"""
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
    SELECT criterion.rubric_id INTO criterion_rubric
      FROM public.registrar_rubriccriterion criterion WHERE criterion.id = NEW.criterion_id;
    SELECT enrollment.offering_id INTO enrollment_offering
      FROM public.registrar_enrollment enrollment WHERE enrollment.id = NEW.enrollment_id;
    IF criterion_rubric IS NULL OR enrollment_offering IS NULL OR NOT EXISTS (
        SELECT 1 FROM public.registrar_assessmentcomponent component
         WHERE component.rubric_id = criterion_rubric
           AND component.offering_id = enrollment_offering
    ) THEN
        RAISE EXCEPTION 'criterion score rubric must be attached to the enrollment offering'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.registrar_guard_criterion_score_coherence() FROM PUBLIC;
"""


def _install_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute(_GUARD_SQL)
    schema_editor.execute("SELECT public.registrar_assert_criterion_component_integrity()")
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS registrar_criterion_score_coherence_guard " "ON public.registrar_criterionscore"
    )
    schema_editor.execute(
        "CREATE TRIGGER registrar_criterion_score_coherence_guard "
        "BEFORE INSERT OR UPDATE OF component_id, criterion_id, enrollment_id, organization_id, points "
        "ON public.registrar_criterionscore FOR EACH ROW "
        "EXECUTE FUNCTION public.registrar_guard_criterion_score_coherence()"
    )
    for table in ("registrar_criterionscore", "registrar_componentscore"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_rubric_total_guard ON public.{table}")
        schema_editor.execute(
            "CREATE CONSTRAINT TRIGGER registrar_rubric_total_guard "
            f"AFTER INSERT OR UPDATE OR DELETE ON public.{table} "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION public.registrar_guard_rubric_score_total()"
        )
    trigger_sql = [
        (
            "registrar_component_rubric_evidence_update_guard",
            "BEFORE UPDATE OF organization_id, offering_id, name, rubric_id, max_score",
            "registrar_assessmentcomponent",
            "registrar_guard_component_rubric_evidence",
        ),
        (
            "registrar_component_rubric_evidence_delete_guard",
            "BEFORE DELETE",
            "registrar_assessmentcomponent",
            "registrar_guard_component_rubric_evidence",
        ),
        (
            "registrar_criterion_rubric_evidence_update_guard",
            "BEFORE UPDATE OF organization_id, rubric_id, name, max_points",
            "registrar_rubriccriterion",
            "registrar_guard_criterion_rubric_evidence",
        ),
        (
            "registrar_criterion_rubric_evidence_delete_guard",
            "BEFORE DELETE",
            "registrar_rubriccriterion",
            "registrar_guard_criterion_rubric_evidence",
        ),
        (
            "registrar_rubric_evidence_delete_guard",
            "BEFORE DELETE",
            "registrar_rubric",
            "registrar_guard_rubric_delete_with_evidence",
        ),
        (
            "registrar_rubric_evidence_update_guard",
            "BEFORE UPDATE OF organization_id, name",
            "registrar_rubric",
            "registrar_guard_rubric_delete_with_evidence",
        ),
    ]
    for name, event, table, function in trigger_sql:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
        schema_editor.execute(
            f"CREATE TRIGGER {name} {event} ON public.{table} FOR EACH ROW " f"EXECUTE FUNCTION public.{function}()"
        )
    for table in ("registrar_rubric", "registrar_rubriccriterion", "registrar_assessmentcomponent"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_rubric_evidence_truncate_guard ON public.{table}")
        schema_editor.execute(
            "CREATE TRIGGER registrar_rubric_evidence_truncate_guard "
            f"BEFORE TRUNCATE ON public.{table} FOR EACH STATEMENT "
            "EXECUTE FUNCTION public.registrar_guard_rubric_evidence_no_truncate()"
        )
    schema_editor.execute("SET LOCAL app.bypass_rls = 'off'")


def _remove_postgres_guards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("registrar_rubric", "registrar_rubriccriterion", "registrar_assessmentcomponent"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_rubric_evidence_truncate_guard ON public.{table}")
    trigger_tables = [
        ("registrar_rubric_evidence_update_guard", "registrar_rubric"),
        ("registrar_rubric_evidence_delete_guard", "registrar_rubric"),
        ("registrar_criterion_rubric_evidence_delete_guard", "registrar_rubriccriterion"),
        ("registrar_criterion_rubric_evidence_update_guard", "registrar_rubriccriterion"),
        ("registrar_component_rubric_evidence_delete_guard", "registrar_assessmentcomponent"),
        ("registrar_component_rubric_evidence_update_guard", "registrar_assessmentcomponent"),
    ]
    for name, table in trigger_tables:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{table}")
    for table in ("registrar_componentscore", "registrar_criterionscore"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_rubric_total_guard ON public.{table}")
    schema_editor.execute(
        "DROP TRIGGER IF EXISTS registrar_criterion_score_coherence_guard " "ON public.registrar_criterionscore"
    )
    for signature in (
        "registrar_guard_rubric_evidence_no_truncate()",
        "registrar_guard_rubric_delete_with_evidence()",
        "registrar_guard_criterion_rubric_evidence()",
        "registrar_guard_component_rubric_evidence()",
        "registrar_guard_rubric_score_total()",
        "registrar_assert_rubric_score_total(uuid, uuid)",
        "registrar_assert_criterion_component_integrity()",
    ):
        schema_editor.execute(f"DROP FUNCTION IF EXISTS public.{signature}")
    schema_editor.execute(_RESTORE_0042_SQL)
    schema_editor.execute(
        "CREATE TRIGGER registrar_criterion_score_coherence_guard "
        "BEFORE INSERT OR UPDATE OF criterion_id, enrollment_id, organization_id "
        "ON public.registrar_criterionscore FOR EACH ROW "
        "EXECUTE FUNCTION public.registrar_guard_criterion_score_coherence()"
    )


def _noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):
    dependencies = [("registrar", "0043_correction_reversal_ledger")]

    operations = [
        migrations.AddField(
            model_name="criterionscore",
            name="component",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="criterion_scores",
                to="registrar.assessmentcomponent",
            ),
        ),
        migrations.RunPython(_backfill_component_identity, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="criterionscore",
            name="component",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="criterion_scores",
                to="registrar.assessmentcomponent",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="criterionscore",
            name="uniq_criterion_enrollment_score",
        ),
        migrations.AddConstraint(
            model_name="criterionscore",
            constraint=models.UniqueConstraint(
                fields=("component", "criterion", "enrollment"),
                name="uniq_component_criterion_enrollment_score",
            ),
        ),
        migrations.AddIndex(
            model_name="criterionscore",
            index=models.Index(
                fields=["component", "enrollment"],
                name="reg_crit_comp_enroll_idx",
            ),
        ),
        migrations.AlterField(
            model_name="criterionscore",
            name="criterion",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="scores",
                to="registrar.rubriccriterion",
            ),
        ),
        migrations.RunPython(_install_postgres_guards, _remove_postgres_guards),
        migrations.RunPython(_noop, _ensure_safe_reverse),
    ]

"""``legacy_repair_journal_enrollments`` — canlı bazanın dəyişməsinə qarşı sərtləşdirmə (2026-09-25 insidenti).

Production-da tətbiq qonaq yazılışın mənbə qrupu canlıda olmadığı üçün PG qoruyucusunda yıxıldı və
dəstə-dəstə commit yarımçıq vəziyyət qoydu.  Sınanan müqavilə:

1. HƏR modelin HƏR FK-sı təsnif olunub; canlıda (eyni təşkilatda) olmayan istinad AÇIQ qərardır:
   mənbə qrup → NULL (``on_delete=SET_NULL`` semantikası), açılışın qrupu → ``skip_missing_group_id``,
   plandan kənar komponent → ``skip_parent`` (+ diaqnostika siyahısı), ``grade.input``-suz müəllim → NULL;
2. tətbiq HƏR ŞEY və ya HEÇ NƏ-dir: yazının ortasında DB xətası heç nə saxlamır (audit də yox);
3. yarımçıq vəziyyətin (yalnız açılış/sxem/komponent/mövzu) üzərinə təkrar tətbiq bərpanı tamamlayır —
   planın öz açılışları (pk + bu sha256-lı ``create`` auditi) «legacy deyil» sayılmır.
"""

import uuid

from django.apps import apps as django_apps
from django.db import IntegrityError

import pytest

from apps.legacy_import.services import repair_enrollments_apply as applier
from apps.legacy_import.services.repair_enrollments_refs import check_fk_coverage, classify_fk
from apps.legacy_import.services.repair_plan_file import RepairPlanError
from apps.legacy_import.services.repair_support import RepairContext, scoped_atomic
from apps.legacy_import.tests import journal_points_harness as harness
from apps.legacy_import.tests import test_repair_journal_enrollments as base

pytestmark = pytest.mark.django_db
# Əsas dəstin fixture-ləri və köməkçiləri (plan qurucusu, ssenari).
actor = base.actor
allow_running_source_run = base.allow_running_source_run
Target = base.Target
_model = base._model
_plan = base._plan
_scenario = base._scenario


def _context(target, actor):
    return RepairContext(organization=target.org, actor=actor, apply=True, limit=0)


def _audits(target):
    return django_apps.get_model("audit", "AuditLog").objects.filter(
        organization=target.org, reason__startswith="legacy_repair:journal_enrollments"
    )


def test_every_foreign_key_of_every_plan_model_is_classified():
    check_fk_coverage()
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_fk_unclassified:registrar.enrollment.x_id"):
        classify_fk("registrar.enrollment", "x_id")


@pytest.mark.parametrize("where", ["missing", "other_organization"])
def test_a_guest_source_group_absent_from_the_live_tenant_becomes_null(actor, where):
    target = Target(actor, f"live-guest-{where}")
    instances = _scenario(target)
    guest = instances[3]
    if where == "missing":
        guest.source_group_id = uuid.uuid4()
    else:
        other = harness.organization(actor, "live-guest-other-org")
        guest.source_group_id = base._unit(other, "foreign").pk
    plan = _plan(target, instances)

    decided = applier.decide(target.org, plan)
    assert decided.counters["enrollment:null_source_group_id"] == 1
    assert decided.counters["enrollment:create"] == 2
    applier.apply_decided(_context(target, actor), decided, plan=plan, plan_sha256=plan.sha256)

    restored = _model("Enrollment").objects.get(pk=guest.pk)
    assert restored.source_group_id is None and restored.added_by_id == actor.pk  # SET_NULL son vəziyyəti
    assert _model("FinalGrade").objects.get(enrollment=restored).exam_score is not None


def test_a_missing_offering_group_skips_the_offering_and_all_of_its_children(actor):
    target = Target(actor, "live-missing-group")
    instances = _scenario(target)
    instances[0].group_id = uuid.uuid4()  # yeni açılışın qrupu canlıda yoxdur
    decided = applier.decide(target.org, _plan(target, instances))

    assert decided.counters["courseoffering:skip_missing_group_id"] == 1
    assert decided.counters["assessmentscheme:skip_parent"] == 1
    assert decided.counters["assessmentcomponent:skip_parent"] == 1
    assert decided.counters["componentscore:skip_parent"] == 1
    assert decided.counters["enrollment:create"] == 1  # mövcud açılışa qonaq yazılış qalır


def test_a_missing_external_component_is_a_reported_skip(actor):
    target = Target(actor, "live-missing-component")
    instances = _scenario(target)
    score = instances[8]
    ghost = str(uuid.uuid4())
    score.component_id = ghost
    decided = applier.decide(target.org, _plan(target, instances))

    assert decided.counters["componentscore:skip_parent"] == 1
    assert decided.missing_external == {"registrar.assessmentcomponent": [ghost]}


def test_an_instructor_without_grade_input_is_nulled_at_decision_time(actor, django_user_model):
    target = Target(actor, "live-instructor")
    instances = _scenario(target)
    instances[0].instructor_id = django_user_model.objects.create_user(username="no.grade.input", password="x").pk
    plan = _plan(target, instances)
    decided = applier.decide(target.org, plan)
    assert decided.counters["courseoffering:null_instructor_id"] == 1
    applier.apply_decided(_context(target, actor), decided, plan=plan, plan_sha256=plan.sha256)
    assert _model("CourseOffering").objects.get(pk=instances[0].pk).instructor_id is None


def test_the_apply_is_all_or_nothing(actor, monkeypatch):
    target = Target(actor, "live-atomic")
    instances = _scenario(target)
    plan = _plan(target, instances)
    decided = applier.decide(target.org, plan)
    offerings_before = _model("CourseOffering").objects.count()

    def boom(*_args, **_kwargs):
        raise IntegrityError("simulated failure after offerings and enrollments")

    monkeypatch.setattr(_model("FinalGrade").objects, "bulk_create", boom)
    with pytest.raises(IntegrityError):
        applier.apply_decided(_context(target, actor), decided, plan=plan, plan_sha256=plan.sha256)

    assert _model("CourseOffering").objects.count() == offerings_before
    assert not _model("Enrollment").objects.filter(student=target.student).exists()
    assert not _audits(target).exists()


def test_a_reapply_over_a_partial_state_completes_the_restore(actor):
    target = Target(actor, "live-partial")
    instances = _scenario(target)
    plan = _plan(target, instances)
    context = _context(target, actor)
    decided = applier.decide(target.org, plan)
    # Köhnə (dəstə-dəstə commit) tətbiqin yarımçıq vəziyyəti: yalnız 4 valideyn növü yazılıb.
    with scoped_atomic(context):
        for kind in ("registrar.courseoffering", "registrar.assessmentscheme", "registrar.assessmentcomponent"):
            batch = [d for d in decided.decisions if d.kind == kind and d.action == "create"]
            applier._write_kind(context, kind, batch, plan_sha256=plan.sha256)
    assert not _audits(target).filter(reason__endswith="xülasə").exists()

    again = applier.decide(target.org, plan)
    assert again.counters["courseoffering:already_present"] == 1
    assert again.counters["enrollment:create"] == 2 and "enrollment:skip_offering_not_legacy" not in again.counters
    written = applier.apply_decided(context, again, plan=plan, plan_sha256=plan.sha256)
    assert written["enrollment"] == 2 and written["componentscore"] == 1 and written["finalgrade"] == 1

    third = applier.decide(target.org, plan)
    assert {action for (_kind, action), _n in base._counts(third)} <= {"already_present", "skip_offering_mismatch"}


def test_offerings_already_present_without_this_plans_audit_are_not_trusted(actor):
    target = Target(actor, "live-foreign-offering")
    instances = _scenario(target)
    new_offering = instances[0]
    new_offering.save()  # eyni pk ilə, amma bu planın auditi YOXDUR (başqa yolla yaranıb)
    decided = applier.decide(target.org, _plan(target, instances))
    assert decided.counters["courseoffering:already_present"] == 1
    assert decided.counters["enrollment:skip_offering_not_legacy"] == 1  # fake yazılış yad açılışa yazılmır

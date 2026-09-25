"""``legacy_repair_journal_enrollments`` — hazırda oxuyanların atılmış jurnal yazılışları.

Sınanan müqavilə:

1. «hazırda oxuyan» tərifi (E1/E2/E3) və dilim qaydası (öz qrup → həmin dövrün
   qrupu → ilk dilim) deterministikdir;
2. tətbiq: yeni açılış + sxem + komponent, qonaq yazılış (``source_group``), dərs,
   xana, bal, yekun canlıya köçür; mövcud sətir üstündən yazılmır; ikinci icra 0;
3. başqasının (tələbə, açılış) yazılışı varsa sətir və uşaqları atlanır;
   aktiv üzvlüyü olmayan tələbə, 2026/2027 açılışı, fərqli açılışın dərsinə xana
   — atlanır (PG qoruyucularından ƏVVƏL);
4. ``--limit`` yalnız ilk N yazılışı və onların valideynlərini işləyir;
5. ön-şərt: plan qurulanda klonda tətbiq olunmuş J12 planı canlıda da tətbiq
   olunmayıbsa HEÇ NƏ edilmir;
6. əmr qapıları: sha256 məcburi, dry-run default, markersiz baza üçün
   ``--i-know-this-is-production``.
"""

import datetime
import uuid
from decimal import Decimal
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from apps.legacy_import.models import LegacyMigrationRun
from apps.legacy_import.services import repair_enrollments_apply as applier
from apps.legacy_import.services import repair_lesson_recovery as planner
from apps.legacy_import.services import repair_support
from apps.legacy_import.services.repair_enrollments_extract import record_of
from apps.legacy_import.services.repair_enrollments_select import _choose_slice, _current_students, _evidence_slice
from apps.legacy_import.services.repair_plan_file import LoadedPlan, write_plan
from apps.legacy_import.services.repair_support import RepairContext
from apps.legacy_import.services.table_plan import SOURCE_SNAPSHOT_SHA256
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db
REPAIR = "journal_enrollments"


# ── saf qaydalar ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "cohort", "labels", "placed", "expected"),
    [
        (0, (2024, "bak"), {"2025/2026 Payız"}, False, "E2_cohort_bak"),
        (0, (2022, "bak"), {"2025/2026 Yaz"}, False, None),  # 2026-da məzun
        (0, (2022, "bak"), {"2025/2026 Yaz"}, True, "E1_placed_2026_27"),  # uzadılıb, 2026/2027-də yerləşib
        (0, (2025, "mag"), {"2025/2026 Payız"}, False, "E2_cohort_mag"),
        (0, (2024, "mag"), {"2025/2026 Payız"}, False, None),  # magistr 2026-da bitirib
        (0, (0, "bak"), {"2025/2026 Yaz"}, False, "E3_unknown_cohort_active_spring"),
        (0, (0, "bak"), {"2025/2026 Payız"}, False, None),  # yalnız payız — son semestrdə yoxdur
        (1, (2025, "bak"), {"2025/2026 Yaz"}, True, None),  # azadedildi=1 heç vaxt cari deyil
        (0, (2024, "bak"), {"2024/2025 Yaz"}, False, None),  # 2025/2026-da jurnal yoxdur
    ],
)
def test_the_current_student_definition(status, cohort, labels, placed, expected):
    current = _current_students(
        students={"7": ("70", "migrated")},
        status={7: status},
        cohort={7: cohort},
        activity={7: labels},
        placed={70} if placed else set(),
    )
    assert current.get(7, (None, None))[1] == expected


def test_the_slice_rule_prefers_own_group_then_same_period_then_primary():
    slices = [("2", "unit-a"), ("3", "unit-b"), ("4", "unit-c")]
    assert _choose_slice(slices, sar_unit="unit-b", same_period_units=set()) == ("3", "unit-b", "own_group")
    assert _choose_slice(slices, sar_unit="x", same_period_units={"unit-c"}) == ("4", "unit-c", "same_period_group")
    assert _choose_slice(slices, sar_unit="x", same_period_units={"unit-c", "unit-b"})[2] == "same_period_group_first"
    assert _choose_slice(slices, sar_unit="x", same_period_units=set()) == ("2", "unit-a", "primary_slice")


def test_a_deleted_group_journal_is_placed_only_on_single_group_evidence():
    refs = {"unit-a": "41", "unit-b": "42"}
    assert _evidence_slice({"unit-a"}, refs) == ([("41", "unit-a", "")], "")
    assert _evidence_slice(set(), refs) == ([], "no_group_evidence")
    assert _evidence_slice({"unit-a", "unit-b"}, refs) == ([], "ambiguous_group")
    assert _evidence_slice({"unit-x"}, refs) == ([], "no_slice")  # legacy-dən gəlməyən qrup


# ── tətbiq (əl ilə qurulmuş plan) ────────────────────────────────────────────


@pytest.fixture
def actor(django_user_model):
    return django_user_model.objects.create_user(username="repair-enroll-actor", password="x", is_superuser=True)


@pytest.fixture(autouse=True)
def allow_running_source_run(monkeypatch):
    monkeypatch.setattr(
        planner,
        "SOURCE_RUN_STATUSES",
        (LegacyMigrationRun.Status.SUCCEEDED, LegacyMigrationRun.Status.RUNNING),
    )


def _model(name):
    return django_apps.get_model("registrar", name)


def _unit(org, name):
    return django_apps.get_model("organizations", "OrgUnit").objects.create(
        organization=org, name=name, unit_type="group", slug=f"grp-{name}-{uuid.uuid4().hex[:6]}"
    )


class Target:
    """Canlı vəziyyət: köçürülmüş açılış (ledger MIGRATED) + tələbələr."""

    def __init__(self, actor, slug):
        self.org = harness.organization(actor, slug)
        self.run = harness.running_run(self.org, actor, table_plan=harness.plan(harness.tables()))
        self.offering, self.enrollments, _l = harness.seed_journal_target(self.org, actor, self.run.pk, lesson_slots=())
        self.own_group = _unit(self.org, "own")
        self.other_group = _unit(self.org, "other")
        user_model = django_apps.get_model("auth", "User")
        self.student = user_model.objects.create_user(username="guest.student", password="x")
        self.student.profile.organization = self.org
        self.student.profile.save(update_fields=["organization"])
        harness.activate_member(self.org, self.student, "student")

    def header(self):
        return {
            "repair": REPAIR,
            "organization_id": str(self.org.pk),
            "source_snapshot_sha256": SOURCE_SNAPSHOT_SHA256,
            "source_run_id": str(self.run.pk),
        }


def _plan(target, instances, restore_keys=None):
    records: dict[str, list] = {}
    for instance in instances:
        record = record_of(instance)
        if record["kind"] == "registrar.enrollment":
            record["restore_key"] = (restore_keys or {}).get(record["pk"], f"uq:{instance.student_id}")
        records.setdefault(record["kind"], []).append(record)
    return LoadedPlan(header=target.header(), records=records, sha256="e" * 64)


def _scenario(target):
    """Yeni açılış (+sxem, komponent) + mövcud açılışa qonaq yazılış + dərs/xana/bal/yekun."""

    org = target.org
    new_offering = _model("CourseOffering")(
        pk=uuid.uuid4(),
        organization=org,
        subject_id=target.offering.subject_id,
        period_id=target.offering.period_id,
        group=target.other_group,
        lesson_hours=0,
        is_active=True,
    )
    scheme = _model("AssessmentScheme")(
        pk=uuid.uuid4(), organization=org, offering_id=new_offering.pk, approval_status="approved", is_published=True
    )
    component = _model("AssessmentComponent")(
        pk=uuid.uuid4(),
        organization=org,
        offering_id=new_offering.pk,
        name="Kollokvium 1",
        kind="kollokvium",
        max_score=10,
        order=1,
    )
    guest = _model("Enrollment")(
        pk=uuid.uuid4(),
        organization=org,
        student=target.student,
        offering=target.offering,
        kind="mandatory",
        status="enrolled",
        source_group=target.own_group,
        added_by_id=target.org.owner_id,
    )
    fake = _model("Enrollment")(
        pk=uuid.uuid4(), organization=org, student=target.student, offering_id=new_offering.pk, kind="mandatory"
    )
    lesson = _model("Lesson")(
        pk=uuid.uuid4(),
        organization=org,
        offering=target.offering,
        date=datetime.date(2021, 12, 30),
        start_time=datetime.time(14, 0),
        kind="seminar",
        hours=2,
        is_legacy_synthesised=True,
    )
    mark = _model("LessonMark")(
        pk=uuid.uuid4(), organization=org, lesson_id=lesson.pk, enrollment_id=guest.pk, status="present", score=7
    )
    wrong_mark = _model("LessonMark")(
        pk=uuid.uuid4(), organization=org, lesson_id=lesson.pk, enrollment_id=fake.pk, status="absent"
    )
    score = _model("ComponentScore")(
        pk=uuid.uuid4(), organization=org, component_id=component.pk, enrollment_id=fake.pk, score=Decimal("8")
    )
    final = _model("FinalGrade")(pk=uuid.uuid4(), organization=org, enrollment_id=guest.pk, exam_score=Decimal("30"))
    return [new_offering, scheme, component, guest, fake, lesson, mark, wrong_mark, score, final]


def _apply(target, actor, plan):
    context = RepairContext(organization=target.org, actor=actor, apply=True, limit=0)
    decided = applier.decide(target.org, plan)
    return decided, applier.apply_decided(context, decided, plan=plan, plan_sha256=plan.sha256)


def test_the_plan_restores_offerings_guest_enrollments_and_scores_once(actor):
    target = Target(actor, "enroll-apply")
    plan = _plan(target, _scenario(target))
    decided, written = _apply(target, actor, plan)

    assert decided.counters["enrollment:create"] == 2
    assert decided.counters["lessonmark:skip_offering_mismatch"] == 1  # PG coherence-dən ƏVVƏL tutulur
    guest = _model("Enrollment").objects.get(student=target.student, offering=target.offering)
    assert guest.source_group_id == target.own_group.pk and guest.added_by_id == actor.pk  # «alt qrup» çipi
    assert _model("LessonMark").objects.get(enrollment=guest).score == Decimal("7.00")
    assert _model("FinalGrade").objects.get(enrollment=guest).exam_score == Decimal("30.00")
    new = _model("CourseOffering").objects.get(group=target.other_group)
    assert new.assessment_scheme.is_published and new.assessment_scheme.approval_status == "approved"
    assert _model("ComponentScore").objects.get(enrollment__offering=new).score == Decimal("8.00")
    assert written["enrollment"] == 2 and written["lessonmark"] == 1
    audits = django_apps.get_model("audit", "AuditLog").objects.filter(
        organization=target.org, reason__startswith="legacy_repair:journal_enrollments"
    )
    assert (
        audits.filter(reason__endswith="enrollment").count() == 2
        and audits.filter(reason__endswith="xülasə").count() == 1
    )

    again = applier.decide(target.org, plan)
    assert all(action in ("already_present", "skip_offering_mismatch") for (_k, action), _n in _counts(again))
    second = applier.apply_decided(
        RepairContext(organization=target.org, actor=actor, apply=True, limit=0), again, plan=plan, plan_sha256="e" * 64
    )
    assert not any(second.values())
    assert audits.filter(reason__endswith="xülasə").count() == 1  # boş təkrar icra iz qoymur


def _counts(decided):
    from collections import Counter

    return Counter((d.kind, d.action) for d in decided.decisions).items()


def test_a_foreign_enrollment_is_never_merged_and_its_children_are_skipped(actor):
    target = Target(actor, "enroll-foreign")
    instances = _scenario(target)
    _model("Enrollment").objects.create(organization=target.org, student=target.student, offering=target.offering)
    plan = _plan(target, instances)
    decided, _written = _apply(target, actor, plan)
    assert decided.counters["enrollment:skip_enrollment_exists"] == 1
    assert decided.counters["finalgrade:skip_parent"] == 1 and decided.counters["lessonmark:skip_parent"] == 1
    assert not _model("FinalGrade").objects.filter(enrollment__student=target.student).exists()


def test_inactive_students_and_non_legacy_offerings_are_untouchable(actor):
    target = Target(actor, "enroll-guards")
    period = django_apps.get_model("organizations", "AcademicPeriod").objects.create(
        organization=target.org,
        name="Payız",
        academic_year="2026/2027",
        period_type="semester",
        start_date=datetime.date(2026, 9, 15),
        end_date=datetime.date(2027, 1, 31),
    )
    current = _model("CourseOffering")(
        pk=uuid.uuid4(), organization=target.org, subject_id=target.offering.subject_id, period=period, lesson_hours=0
    )
    stranger = django_apps.get_model("auth", "User").objects.create_user(username="no.membership", password="x")
    records = [
        current,
        _model("Enrollment")(pk=uuid.uuid4(), organization=target.org, student=stranger, offering=target.offering),
        _model("Enrollment")(pk=uuid.uuid4(), organization=target.org, student=target.student, offering_id=current.pk),
    ]
    decided = applier.decide(target.org, _plan(target, records))
    assert decided.counters["courseoffering:skip_offering_not_legacy"] == 1
    assert decided.counters["enrollment:skip_student_inactive"] == 1
    assert decided.counters["enrollment:skip_parent"] == 1


def test_limit_only_processes_the_first_enrollments_and_their_parents(actor):
    target = Target(actor, "enroll-limit")
    instances = _scenario(target)
    plan = _plan(target, instances)
    decided = applier.decide(target.org, plan, limit=1)
    assert decided.counters["enrollment:create"] == 1 and decided.counters["enrollment:skip_limit"] == 1


def test_extraction_takes_only_restored_rows_and_counts_the_rest(actor):
    from collections import Counter

    from django.utils import timezone

    from apps.legacy_import.services.repair_enrollments_extract import extract

    target = Target(actor, "enroll-extract")
    since = timezone.now()
    instances = _scenario(target)
    new_offering, _scheme, _component, guest, fake, lesson, _mark, wrong_mark, _score, _final = instances
    for instance in instances:
        if instance is not wrong_mark:  # başqa açılışın dərsinə xana — PG onu onsuz da rədd edir
            instance.save()
    original = next(iter(target.enrollments.values()))
    _model("LessonMark").objects.create(organization=target.org, lesson=lesson, enrollment=original, status="present")

    records, report = extract(
        target.org,
        since=since,
        restored={"uq:guest": str(guest.pk), "uq:fake": str(fake.pk)},
        new_offerings={str(new_offering.pk)},
    )

    assert Counter(record["kind"] for record in records) == {
        "registrar.courseoffering": 1,
        "registrar.assessmentscheme": 1,
        "registrar.assessmentcomponent": 1,
        "registrar.enrollment": 2,
        "registrar.lesson": 1,
        "registrar.lessonmark": 1,
        "registrar.componentscore": 1,
        "registrar.finalgrade": 1,
    }
    assert report["LessonMark"] == {"plan": 1, "foreign_new": 1, "updated_existing": 0}
    assert {r["restore_key"] for r in records if r["kind"] == "registrar.enrollment"} == {"uq:guest", "uq:fake"}
    assert all("kind" not in r["fields"] or r["kind"] != r["fields"]["kind"] for r in records)


def test_a_plan_field_unknown_to_the_live_model_is_refused():
    from apps.legacy_import.services.repair_enrollments_specs import coerce
    from apps.legacy_import.services.repair_plan_file import RepairPlanError

    assert coerce(_model("FinalGrade"), {"exam_score": "30.00"})["exam_score"] == Decimal("30.00")
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_field_unknown:registrar.finalgrade.legacy_x"):
        coerce(_model("FinalGrade"), {"exam_score": "30.00", "legacy_x": 1})


def test_an_incompatible_plan_is_refused_before_anything_is_written(actor):
    from apps.legacy_import.services.repair_plan_file import RepairPlanError

    target = Target(actor, "enroll-fields")
    plan = _plan(target, _scenario(target))
    plan.records["registrar.finalgrade"][0]["fields"]["legacy_x"] = 1
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_field_unknown"):
        applier.decide(target.org, plan)
    assert not _model("CourseOffering").objects.filter(group=target.other_group).exists()


def test_excluding_pairs_after_the_replay_drops_only_their_own_rows():
    from apps.legacy_import.services.repair_enrollments_plan import _drop_excluded

    records = [
        {"kind": "registrar.courseoffering", "pk": "o-kept", "fields": {}},
        {"kind": "registrar.courseoffering", "pk": "o-orphan", "fields": {}},
        {"kind": "registrar.assessmentscheme", "pk": "sc-orphan", "fields": {"offering_id": "o-orphan"}},
        {"kind": "registrar.assessmentcomponent", "pk": "c-kept", "fields": {"offering_id": "o-kept"}},
        {"kind": "registrar.assessmentcomponent", "pk": "c-only-excluded", "fields": {"offering_id": "o-kept"}},
        {"kind": "registrar.enrollment", "pk": "e1", "fields": {"offering_id": "o-kept"}},
        {"kind": "registrar.componentscore", "pk": "s1", "fields": {"component_id": "c-kept"}},
    ]
    report = {
        "AssessmentComponent": {"plan": 2, "foreign_new": 0, "updated_existing": 0},
        "CourseOffering": {"plan": 2, "foreign_new": 0, "updated_existing": 0},
        "AssessmentScheme": {"plan": 1, "foreign_new": 0, "updated_existing": 0},
    }
    header = {
        "restored_pairs": {
            "uq:1": {"category": "fake", "slice_rule": "own_group"},
            "uq:2": {"category": "deleted", "slice_rule": "same_period_group"},
        },
        "selected_pairs": {"fake": 1, "deleted": 1},
        "slice_rules": {"fake:own_group": 1, "deleted:same_period_group": 1},
        "skipped": {},
    }
    kept, report = _drop_excluded(records, report, header, excluded=["uq:2"], reason="not_in_roster")
    assert [r["pk"] for r in kept] == ["o-kept", "c-kept", "e1", "s1"]
    assert report["AssessmentComponent"] == {"plan": 1, "foreign_new": 1, "updated_existing": 0}
    assert report["CourseOffering"]["plan"] == 1 and report["AssessmentScheme"]["plan"] == 0
    assert set(header["restored_pairs"]) == {"uq:1"} and header["selected_pairs"] == {"fake": 1}
    assert header["slice_rules"] == {"fake:own_group": 1} and header["skipped"] == {"deleted:not_in_roster": 1}
    assert header["excluded_after_replay"] == {
        "reason": "not_in_roster",
        "pairs": 1,
        "dropped_assessmentcomponent": 1,
        "dropped_assessmentscheme": 1,
        "dropped_courseoffering": 1,
    }


def test_a_second_journal_of_the_same_offering_joins_the_restored_enrollment(actor):
    from dataclasses import replace

    from apps.legacy_import.models import LegacyEntityMap
    from apps.legacy_import.services.repair_enrollments_replay import _create_enrollments
    from apps.legacy_import.services.repair_enrollments_select import RestorePair, Selection

    target = Target(actor, "enroll-merge")
    context = harness.context(rows_by_table=harness.tables(), run=target.run, organization=target.org, actor=actor)
    lecture = RestorePair(
        category="k9",
        uniqid="LECTUREJRN",
        legacy_student=77,
        user_id=target.student.pk,
        group_ref="2",
        group_unit=str(target.own_group.pk),
        offering_pk=str(target.offering.pk),
        guest_unit="",
        slice_rule="primary_slice",
        period_pk=str(target.offering.period_id),
        subject_pk=str(target.offering.subject_id),
    )
    seminar = replace(lecture, uniqid="SEMINARJRN")
    restored, skipped = _create_enrollments(context, selection=Selection(pairs=[lecture, seminar]), fake_slices={})

    assert restored["LECTUREJRN:77"] == restored["SEMINARJRN:77"]
    assert skipped == {"merged:k9": 1}
    assert _model("Enrollment").objects.filter(student=target.student, offering=target.offering).count() == 1
    sealed = LegacyEntityMap.objects.filter(
        created_run=target.run, entity_type="journal_enrollment", legacy_pk__in=["LECTUREJRN:77", "SEMINARJRN:77"]
    )
    assert {row.target_pk for row in sealed} == {restored["LECTUREJRN:77"]} and sealed.count() == 2


def test_the_plan_refuses_to_run_before_its_prerequisite_j12_plan(actor):
    from apps.legacy_import.services.repair_enrollments_plan import applied_prerequisites
    from apps.legacy_import.services.repair_plan_file import RepairPlanError
    from core.audit import log_action
    from core.constants import AuditAction

    target = Target(actor, "enroll-prereq")
    plan = _plan(target, _scenario(target))
    digest = "a" * 64
    plan.header["prerequisites"] = [{"repair": "lesson_recovery", "plan_sha256": digest}]
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_prerequisite_missing:lesson_recovery:aaaaaaaaaaaa"):
        applier.decide(target.org, plan)
    assert not _model("Enrollment").objects.filter(student=target.student).exists()

    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=target.org,
        resource_type="legacy_import.repair",
        resource_id=digest,
        reason="legacy_repair:lesson_recovery: xülasə",
    )
    assert applied_prerequisites(target.org) == [{"repair": "lesson_recovery", "plan_sha256": digest}]
    assert applier.decide(target.org, plan).counters["enrollment:create"] == 2


# ── əmr qapıları ─────────────────────────────────────────────────────────────


def _manifest(tmp_path, target):
    plan = _plan(target, _scenario(target))
    rows = [record for kind in plan.records for record in plan.records[kind]]
    order = {kind: index for index, kind in enumerate(applier.SPECS)}
    return write_plan(
        str(tmp_path / "enroll.jsonl.gz"), header=plan.header, records=sorted(rows, key=lambda r: order[r["kind"]])
    )


def _call(*args):
    out = StringIO()
    call_command("legacy_repair_journal_enrollments", *args, stdout=out)
    return out.getvalue()


def test_the_command_is_dry_run_by_default_and_needs_the_production_flag(actor, tmp_path, monkeypatch):
    target = Target(actor, "enroll-cmd")
    manifest = _manifest(tmp_path, target)
    base = ("--organization", target.org.slug, "--actor", actor.username, "--plan", manifest.path)
    with pytest.raises(CommandError, match="legacy_repair_plan_sha256_required"):
        _call(*base)
    output = _call(*base, "--plan-sha256", manifest.sha256)
    assert "DRY-RUN" in output and not _model("Enrollment").objects.filter(student=target.student).exists()
    monkeypatch.setattr(repair_support, "database_is_disposable_target", lambda: False)
    with pytest.raises(CommandError, match="legacy_repair_target_not_disposable"):
        _call(*base, "--plan-sha256", manifest.sha256, "--apply")
    output = _call(*base, "--plan-sha256", manifest.sha256, "--apply", "--i-know-this-is-production")
    assert "APPLY" in output and _model("Enrollment").objects.filter(student=target.student).count() == 2

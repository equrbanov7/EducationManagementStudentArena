"""``legacy_repair_lesson_recovery`` — J12-nin ARTIQ köçürülmüş hədəfdə təmiri.

Sınanan müqavilə:

1. plan faylı deterministik, ``0600``, sha256 ilə möhürlü; səhv/qırıq/yad plan
   fail-closed rədd edilir və mövcud plan heç vaxt üstündən yazılmır;
2. plan YALNIZ atılabilən (markerli) bazada qurulur;
3. uçdan-uca: klonda J12-nin ÖZ kodu ilə qurulan plan canlı bazaya tətbiq
   olunanda MƏHZ J12-nin yazacağı sətirlər yaranır, ikinci tətbiq 0 dəyişiklikdir;
4. canlı xana/dərs HEÇ VAXT üstündən yazılmır, 2026/2027 və kəsimdən sonrakı
   data toxunulmazdır, icazəsiz müəllim uydurulmur (boş qalır);
5. əmr qapıları: sha256 məcburi, dry-run default, markersiz bazada ``--apply``
   yalnız ``--i-know-this-is-production`` ilə.
"""

import datetime
import gzip
import json
import os
from decimal import Decimal
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction

import pytest

from apps.legacy_import.models import LegacyMigrationRun
from apps.legacy_import.services import repair_lesson_recovery as planner
from apps.legacy_import.services import repair_lesson_recovery_apply as applier
from apps.legacy_import.services import repair_support
from apps.legacy_import.services.rehearsal_journal_marks_phase import JournalMarksPhase
from apps.legacy_import.services.repair_plan_file import LoadedPlan, RepairPlanError, read_plan, write_plan
from apps.legacy_import.services.repair_support import RepairContext
from apps.legacy_import.services.table_plan import SOURCE_SNAPSHOT_SHA256
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db

HEADER = {"repair": planner.REPAIR_KEY, "organization_id": "x"}


class _Rollback(Exception):
    """Klonu əvvəlki vəziyyətinə qaytarmaq üçün (plan faylı diskdə qalır)."""


@pytest.fixture
def actor(django_user_model):
    return django_user_model.objects.create_user(username="repair-j12-actor", password="x", is_superuser=True)


@pytest.fixture
def allow_running_source_run(monkeypatch):
    """Harness-in import run-u RUNNING-dir; production qapısı isə ``succeeded`` istəyir."""

    monkeypatch.setattr(
        planner,
        "SOURCE_RUN_STATUSES",
        (LegacyMigrationRun.Status.SUCCEEDED, LegacyMigrationRun.Status.RUNNING),
    )


def _lessons(org):
    return django_apps.get_model("registrar", "Lesson").objects.filter(organization=org)


def _marks(org):
    return django_apps.get_model("registrar", "LessonMark").objects.filter(organization=org)


def _audits(org):
    return django_apps.get_model("audit", "AuditLog").objects.filter(
        organization=org, reason__startswith=planner.AUDIT_REASON
    )


# ── plan faylı ───────────────────────────────────────────────────────────────


def test_the_plan_file_is_deterministic_private_and_sealed(tmp_path):
    records = [{"kind": "lesson", "pk": "a"}, {"kind": "mark", "lesson_id": "a", "score": "7"}]
    first = write_plan(str(tmp_path / "one.jsonl.gz"), header=HEADER, records=records)
    second = write_plan(str(tmp_path / "two.jsonl.gz"), header=HEADER, records=records)

    assert first.sha256 == second.sha256  # gzip mtime=0 + sıralı açarlar
    assert oct(os.stat(first.path).st_mode & 0o777) == "0o600"
    manifest = json.loads((tmp_path / "one.jsonl.gz.manifest.json").read_text())
    assert manifest["sha256"] == first.sha256 and manifest["counts"] == {"lesson": 1, "mark": 1}
    loaded = read_plan(first.path, expected_sha256=first.sha256, repair=planner.REPAIR_KEY)
    assert [row["pk"] for row in loaded.of("lesson")] == ["a"] and loaded.of("mark")[0]["score"] == "7"


def test_a_plan_is_never_overwritten(tmp_path):
    path = str(tmp_path / "plan.jsonl.gz")
    write_plan(path, header=HEADER, records=[])
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_exists"):
        write_plan(path, header=HEADER, records=[])


@pytest.mark.parametrize("sha", ["", "abc", "0" * 64])
def test_reading_requires_the_exact_sha256(tmp_path, sha):
    manifest = write_plan(str(tmp_path / "p.jsonl.gz"), header=HEADER, records=[])
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_sha256"):
        read_plan(manifest.path, expected_sha256=sha, repair=planner.REPAIR_KEY)


def test_a_foreign_or_tampered_plan_is_refused(tmp_path):
    manifest = write_plan(str(tmp_path / "p.jsonl.gz"), header=HEADER, records=[{"kind": "mark"}])
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_repair_mismatch"):
        read_plan(manifest.path, expected_sha256=manifest.sha256, repair="another_repair")

    forged = tmp_path / "forged.jsonl.gz"
    with gzip.open(forged, "wb") as stream:
        for payload in (
            {"kind": "header", "format": "emsarena-legacy-repair-plan", "format_version": 1, **HEADER},
            {"kind": "mark"},
            {"kind": "footer", "counts": {"mark": 2}},  # footer iki xana deyir, fayl bir daşıyır
        ):
            stream.write((json.dumps(payload) + "\n").encode())
    from apps.legacy_import.services.repair_plan_file import file_sha256

    with pytest.raises(RepairPlanError, match="legacy_repair_plan_count_mismatch"):
        read_plan(str(forged), expected_sha256=file_sha256(str(forged)), repair=planner.REPAIR_KEY)


# ── plan: yalnız atılabilən klonda ───────────────────────────────────────────


def test_building_a_plan_is_refused_without_the_disposable_marker(actor, tmp_path, monkeypatch):
    monkeypatch.setattr(planner, "database_is_disposable_target", lambda: False)
    org = harness.organization(actor, "j12-repair-marker")
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_target_not_disposable"):
        planner.build_plan(organization=org, actor=actor, source_factory=None, out_path=str(tmp_path / "p.jsonl.gz"))
    assert not (tmp_path / "p.jsonl.gz").exists()


# ── uçdan-uca: klonda plan → canlıda tətbiq ─────────────────────────────────


def _import_state(actor, slug, rows):
    """Production vəziyyəti: J1-J4 işləyib, dərs cədvəli BOŞ (J12 yox idi)."""

    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk, lesson_slots=())
    harness.authorize_import_actor(org, actor)
    JournalMarksPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    return org, run


def _build_on_clone_and_roll_back(actor, org, run, rows, path, monkeypatch):
    """Klonda planı qur, klonu geri qaytar — plan faylı və J12-nin nəticəsi qalır."""

    monkeypatch.setattr(planner, "database_is_disposable_target", lambda: True)
    notes = []
    snapshot = {}
    try:
        with transaction.atomic():
            built = planner.build_plan(
                organization=org,
                actor=actor,
                source_factory=harness.factory(rows),
                out_path=path,
                source_run_id=str(run.pk),
                note=notes.append,
                table_plan=harness.plan(rows),
            )
            snapshot["lessons"] = sorted(
                (lesson.date, lesson.start_time, lesson.kind, lesson.hours)
                for lesson in _lessons(org).filter(is_legacy_synthesised=True)
            )
            snapshot["marks"] = sorted(
                (mark.enrollment.student.username, mark.status, mark.score) for mark in _marks(org)
            )
            raise _Rollback
    except _Rollback:
        pass
    return built, snapshot


def test_a_plan_built_on_the_clone_restores_exactly_what_j12_writes(
    actor, tmp_path, monkeypatch, allow_running_source_run
):
    rows = harness.tables(
        dates=[],
        points=[
            harness.point_row(1, point="7", sem_muh=0, month_id="12", day_number="30"),
            harness.point_row(2, point="qb", student_id=harness.STUDENT_B),
        ],
    )
    try:
        org, run = _import_state(actor, "j12-repair-e2e", rows)
        assert _lessons(org).count() == 0 and _marks(org).count() == 0  # J4 xanaları ata bilmədi

        built, expected = _build_on_clone_and_roll_back(
            actor, org, run, rows, str(tmp_path / "plan.jsonl.gz"), monkeypatch
        )
        # Klon geri qayıtdı: canlı baza hələ də bərpasızdır.
        assert _lessons(org).count() == 0 and _marks(org).count() == 0
        assert built.manifest.counts == {"lesson": 1, "mark": 2}

        plan = read_plan(built.manifest.path, expected_sha256=built.manifest.sha256, repair=planner.REPAIR_KEY)
        assert plan.header["source_run_id"] == str(run.pk)
        assert plan.header["planning_transform_version"].startswith(planner.REPAIR_TRANSFORM_FAMILY)
        context = RepairContext(organization=org, actor=actor, apply=True, limit=0)

        decided = applier.decide(org, plan)
        assert decided.counters["lesson:create"] == 1 and decided.counters["mark:create"] == 2
        written = applier.apply_decided(context, decided, plan=plan, plan_sha256=plan.sha256)

        restored = _lessons(org).get()
        assert restored.is_legacy_synthesised is True and restored.created_by_id is None
        assert [(restored.date, restored.start_time, restored.kind, restored.hours)] == expected["lessons"]
        assert sorted((m.enrollment.student.username, m.status, m.score) for m in _marks(org)) == expected["marks"]
        assert written["dərs yaradıldı"] == 1 and written["xana yaradıldı"] == 2
        absent = _marks(org).get(status="absent").enrollment
        absent.refresh_from_db()
        assert absent.absence_hours == restored.hours  # qayıb saatı bərpa olundu
        assert _audits(org).filter(resource_type="registrar.Lesson").count() == 1
        assert _audits(org).filter(resource_type="registrar.Enrollment").count() == 1
        assert _audits(org).filter(resource_type="legacy_import.repair").count() == 1

        # İdempotent: ikinci icra 0 dəyişiklik.
        again = applier.decide(org, plan)
        assert again.counters["lesson:already_present"] == 1 and again.counters["mark:already_present"] == 2
        second = applier.apply_decided(context, again, plan=plan, plan_sha256=plan.sha256)
        assert second["dərs yaradıldı"] == 0 and second["xana yaradıldı"] == 0
        assert second["absence_hours dəyişdi"] == 0
        assert _lessons(org).count() == 1 and _marks(org).count() == 2
        # Heç nə dəyişməyən təkrar icra audit cədvəlinə də iz qoymur.
        assert _audits(org).count() == 3
    finally:
        harness.clear_import_actor()


# ── tətbiq qaydaları (əl ilə qurulmuş plan) ──────────────────────────────────


def _live_target(actor, slug):
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(harness.tables()))
    offering, enrollments, _lessons_map = harness.seed_journal_target(org, actor, run.pk, lesson_slots=())
    return org, run, offering, enrollments


def _plan(org, run, lessons=(), marks=(), facts=()):
    header = {
        "repair": planner.REPAIR_KEY,
        "organization_id": str(org.pk),
        "source_snapshot_sha256": SOURCE_SNAPSHOT_SHA256,
        "source_run_id": str(run.pk),
    }
    records = {"lesson": list(lessons), "mark": list(marks), "fact": list(facts)}
    return LoadedPlan(header=header, records={k: v for k, v in records.items() if v}, sha256="f" * 64)


def _lesson(offering, pk, *, date="2021-12-30", start="14:00", instructor=None):
    return {
        "kind": "lesson",
        "pk": pk,
        "offering_id": str(offering.pk),
        "date": date,
        "start_time": start,
        "end_time": None,
        "lesson_kind": "seminar",
        "hours": 2,
        "topic": "",
        "room_id": None,
        "instructor_id": instructor,
        "seal_key": "sl:p:1:2",
        "rule_codes": [],
    }


def _mark(lesson_pk, enrollment, status="present", score="7"):
    return {
        "kind": "mark",
        "lesson_id": lesson_pk,
        "enrollment_id": str(enrollment.pk),
        "status": status,
        "score": score,
    }


LESSON_PK = "5d2b3f4e-6a7b-4c8d-9e0f-1a2b3c4d5e6f"


def test_a_live_mark_is_never_overwritten(actor, allow_running_source_run):
    org, run, offering, enrollments = _live_target(actor, "j12-apply-conflict")
    live = django_apps.get_model("registrar", "Lesson").objects.create(
        organization=org, offering=offering, date=datetime.date(2021, 12, 30), start_time=datetime.time(14), hours=2
    )
    django_apps.get_model("registrar", "LessonMark").objects.create(
        organization=org, lesson=live, enrollment=enrollments[harness.STUDENT_A], status="present", score=Decimal("9")
    )
    plan = _plan(
        org,
        run,
        lessons=[_lesson(offering, LESSON_PK)],
        marks=[_mark(LESSON_PK, enrollments[harness.STUDENT_A]), _mark(LESSON_PK, enrollments[harness.STUDENT_B])],
    )
    decided = applier.decide(org, plan)
    # Eyni slotda canlı dərs var → YENİ dərs yaranmır, xanalar ona bağlanır.
    assert decided.counters["lesson:reuse_existing"] == 1
    assert decided.counters["mark:live_conflict"] == 1 and decided.counters["mark:create"] == 1
    applier.apply_decided(
        RepairContext(organization=org, actor=actor, apply=True, limit=0), decided, plan=plan, plan_sha256="f" * 64
    )
    assert _lessons(org).count() == 1
    kept = _marks(org).get(enrollment=enrollments[harness.STUDENT_A])
    assert kept.score == Decimal("9.00")  # canlı dəyər TOXUNULMAZ
    assert _marks(org).get(enrollment=enrollments[harness.STUDENT_B]).lesson_id == live.pk


def test_non_legacy_offerings_and_post_cutoff_dates_are_untouchable(actor, allow_running_source_run):
    org, run, offering, enrollments = _live_target(actor, "j12-apply-cutoff")
    period = django_apps.get_model("organizations", "AcademicPeriod").objects.create(
        organization=org,
        name="Payız",
        academic_year="2026/2027",
        period_type="semester",
        start_date=datetime.date(2026, 9, 15),
        end_date=datetime.date(2027, 1, 31),
    )
    current = django_apps.get_model("registrar", "CourseOffering").objects.create(
        organization=org, subject=offering.subject, period=period, lesson_hours=0, is_active=True
    )
    other_pk = "6d2b3f4e-6a7b-4c8d-9e0f-1a2b3c4d5e6f"
    plan = _plan(
        org,
        run,
        lessons=[_lesson(current, LESSON_PK, date="2026-10-01"), _lesson(offering, other_pk, date="2026-09-10")],
    )
    decided = applier.decide(org, plan)
    assert decided.counters["lesson:skip_offering_not_legacy"] == 1
    assert decided.counters["lesson:skip_date_after_cutoff"] == 1
    applier.apply_decided(
        RepairContext(organization=org, actor=actor, apply=True, limit=0), decided, plan=plan, plan_sha256="f" * 64
    )
    assert _lessons(org).count() == 0


def test_an_instructor_who_lost_grade_input_is_not_invented(actor, allow_running_source_run, django_user_model):
    """Açılışın müəllimi sonradan üzvlüyünü itiribsə dərs müəllimsiz yaranır (PG qoruyucusu onu rədd edərdi)."""

    org, run, offering, enrollments = _live_target(actor, "j12-apply-instructor")
    teacher = django_user_model.objects.create_user(username="left-teacher", password="x")
    harness.activate_member(org, teacher, "teacher", permissions=["grade.input"])
    type(offering).objects.filter(pk=offering.pk).update(instructor=teacher)
    assert applier.grade_input_users(org, [teacher.pk]) == {teacher.pk}
    django_apps.get_model("organizations", "Membership").objects.filter(organization=org, user=teacher).update(
        is_active=False
    )
    plan = _plan(
        org,
        run,
        lessons=[_lesson(offering, LESSON_PK, instructor=teacher.pk)],
        marks=[_mark(LESSON_PK, enrollments[42])],
    )
    decided = applier.decide(org, plan)
    assert decided.counters["  instructor_dropped (icazəsiz müəllim → boş)"] == 1
    applier.apply_decided(
        RepairContext(organization=org, actor=actor, apply=True, limit=0), decided, plan=plan, plan_sha256="f" * 64
    )
    assert _lessons(org).get().instructor_id is None and _marks(org).count() == 1


def test_a_plan_for_another_tenant_or_import_run_is_refused(actor, allow_running_source_run):
    org, run, offering, _enrollments = _live_target(actor, "j12-apply-foreign")
    foreign = _plan(org, run)
    foreign.header["organization_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_organization_mismatch"):
        applier.decide(org, foreign)
    stale = _plan(org, run)
    stale.header["source_run_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_source_run_unknown"):
        applier.decide(org, stale)


def test_limit_processes_only_the_first_units(actor, allow_running_source_run):
    org, run, offering, enrollments = _live_target(actor, "j12-apply-limit")
    other_pk = "7d2b3f4e-6a7b-4c8d-9e0f-1a2b3c4d5e6f"
    plan = _plan(
        org,
        run,
        lessons=[_lesson(offering, LESSON_PK), _lesson(offering, other_pk, date="2021-12-31")],
        marks=[_mark(LESSON_PK, enrollments[42]), _mark(other_pk, enrollments[42])],
    )
    decided = applier.decide(org, plan, limit=1)
    assert len(decided.units) == 1 and decided.counters["lesson:create"] == 1


# ── əmr qapıları ─────────────────────────────────────────────────────────────


def _manifest(tmp_path, org, run, offering, enrollments):
    plan = _plan(org, run, lessons=[_lesson(offering, LESSON_PK)], marks=[_mark(LESSON_PK, enrollments[42])])
    return write_plan(
        str(tmp_path / "cmd.jsonl.gz"),
        header=plan.header,
        records=[*plan.of("lesson"), *plan.of("mark")],
    )


def _call(*args):
    out = StringIO()
    call_command("legacy_repair_lesson_recovery", *args, stdout=out)
    return out.getvalue()


def test_the_command_is_dry_run_by_default_and_requires_the_sha256(actor, tmp_path, allow_running_source_run):
    org, run, offering, enrollments = _live_target(actor, "j12-cmd-dry")
    manifest = _manifest(tmp_path, org, run, offering, enrollments)
    base = ("--organization", org.slug, "--actor", actor.username, "--plan", manifest.path)
    with pytest.raises(CommandError, match="legacy_repair_plan_sha256_required"):
        _call(*base)
    output = _call(*base, "--plan-sha256", manifest.sha256)
    assert "DRY-RUN" in output and "lesson:create" in output
    assert _lessons(org).count() == 0 and _marks(org).count() == 0


def test_apply_on_an_unmarked_database_needs_the_production_flag(
    actor, tmp_path, monkeypatch, allow_running_source_run
):
    org, run, offering, enrollments = _live_target(actor, "j12-cmd-apply")
    manifest = _manifest(tmp_path, org, run, offering, enrollments)
    monkeypatch.setattr(repair_support, "database_is_disposable_target", lambda: False)
    base = ("--organization", org.slug, "--actor", actor.username, "--plan", manifest.path)
    with pytest.raises(CommandError, match="legacy_repair_target_not_disposable"):
        _call(*base, "--plan-sha256", manifest.sha256, "--apply")
    output = _call(*base, "--plan-sha256", manifest.sha256, "--apply", "--i-know-this-is-production")
    assert "APPLY" in output and _lessons(org).filter(is_legacy_synthesised=True).count() == 1
    assert _marks(org).count() == 1
    # İkinci icra: 0 dəyişiklik.
    again = _call(*base, "--plan-sha256", manifest.sha256, "--apply", "--i-know-this-is-production")
    assert "lesson:already_present" in again and _marks(org).count() == 1


def test_build_plan_mode_refuses_apply(actor, tmp_path, monkeypatch):
    monkeypatch.setattr(repair_support, "database_is_disposable_target", lambda: True)
    org = harness.organization(actor, "j12-cmd-build")
    with pytest.raises(CommandError, match="legacy_repair_plan_mode_conflict"):
        _call("--organization", org.slug, "--actor", actor.username, "--build-plan", str(tmp_path / "x"), "--apply")


def test_build_context_scopes_rls_to_the_tenant_and_actor(actor):
    """Production rolu NOBYPASSRLS-dir: kontekstsiz ORM sorğuları boş qayıdırdı."""

    from django.db import connection

    org = harness.organization(actor, "j12-rls-scope")
    context = repair_support.build_context({"organization": org.slug, "actor": actor.username, "limit": 0})
    assert context.organization == org and context.actor == actor and context.apply is False
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('app.current_org_id', true), current_setting('app.current_user_id', true), "
            "current_setting('app.bypass_rls', true)"
        )
        tenant, user, bypass = cursor.fetchone()
    assert (tenant, user, bypass) == (str(org.pk), str(actor.pk), "off")

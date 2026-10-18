"""Semestr açılışı hər qrupun ÖZ qəbul ili planından (sahib qaydası 2026-10-19) + istehlakçıların uyğunluğu.

Kilidlənən qaydalar:

* qrupun qəbul ili: ``settings.admission_year`` (legacy olmayan), yoxdursa addan;
* kohort planı varsa — o; yoxdursa ən son plan + «Bu qəbul ili üçün təsdiqlənmiş plan yoxdur — ən son plan
  tətbiq olundu» xəbərdarlığı; qəbul ili bilinmirsə — ən son plan + ayrıca xəbərdarlıq;
* köhnə qayda ilə yaranmış açılış SİLİNMİR, «qrupun öz planında yoxdur» kimi sayılır;
* sillabus saatı (``plan_hours``) və dərs yükü tapşırığı (``workload.generation``) eyni kohort qaydası ilə.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar import cohort_plans, plan_hours, semester_open
from apps.registrar.models import CourseOffering, Curriculum, CurriculumSubject, Program, Subject
from apps.syllabus.tests.factories import make_org
from core.constants import AcademicPeriodType, OrgUnitType

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    org = make_org("cohort-univ")
    faculty = OrgUnit.objects.create(organization=org, name="Fak", slug="ch-fak", unit_type=OrgUnitType.FACULTY)
    specialty = OrgUnit.objects.create(
        organization=org, name="İxtisas", slug="ch-ixt", unit_type=OrgUnitType.SPECIALTY, parent=faculty
    )

    def group(name, slug, settings):
        return OrgUnit.objects.create(
            organization=org, name=name, slug=slug, unit_type=OrgUnitType.GROUP, parent=specialty, settings=settings
        )

    g25 = group("CH-251", "ch-251", {"admission_year": 2025})
    g23 = group("CH-231", "ch-231", {"course_year": 2, "admission_year": 2023})  # 2023 planı yoxdur
    gx = group("CH-X", "ch-x", {"course_year": 2})  # qəbul ili bilinmir
    period = AcademicPeriod.objects.create(
        organization=org,
        name="Payız",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year="2026/2027",
        start_date="2026-09-15",
        end_date="2027-01-31",
        is_current=True,
    )
    period.refresh_from_db()  # mətn tarixləri → `date`
    program = Program.objects.create(organization=org, code="CH-P", name="Kohort proqramı", specialty_unit=specialty)
    plan25 = Curriculum.objects.create(organization=org, program=program, admission_year=2025, status="approved")
    plan26 = Curriculum.objects.create(organization=org, program=program, admission_year=2026, status="approved")
    old_only = Subject.objects.create(organization=org, code="CH-A", name="2025 planının fənni", ects=5)
    new_only = Subject.objects.create(organization=org, code="CH-B", name="2026 planının fənni", ects=5)
    shared = Subject.objects.create(organization=org, code="CH-C", name="Ortaq fənn", ects=5)
    first_sem = Subject.objects.create(organization=org, code="CH-F", name="Birinci semestr fənni", ects=5)

    def row(plan, subject, semester, lecture=30):
        return CurriculumSubject.objects.create(
            organization=org, curriculum=plan, subject=subject, semester_number=semester, lecture_hours=lecture
        )

    row(plan25, old_only, 3)
    row(plan25, shared, 3, lecture=45)
    row(plan25, first_sem, 1)
    row(plan26, new_only, 3)
    row(plan26, shared, 3, lecture=15)
    row(plan26, first_sem, 1, lecture=60)
    return {
        "org": org,
        "period": period,
        "program": program,
        "g25": g25,
        "g23": g23,
        "gx": gx,
        "plan25": plan25,
        "plan26": plan26,
        "old_only": old_only,
        "new_only": new_only,
        "shared": shared,
        "first_sem": first_sem,
    }


def _subjects(world, group):
    return set(
        CourseOffering.objects.filter(organization=world["org"], period=world["period"], group=group).values_list(
            "subject__code", flat=True
        )
    )


def test_group_cohort_year_prefers_settings_then_name():
    unit = OrgUnit(name="236 K", settings={"admission_year": 2025})
    assert cohort_plans.group_cohort_year(unit) == 2025
    legacy = OrgUnit(name="233 K", settings={"admission_year": 2026, "legacy": {"id": 1}})
    assert cohort_plans.group_cohort_year(legacy) == 2023  # köçürmə ayarı idxal ilidir — ad işləyir
    assert cohort_plans.group_cohort_year(OrgUnit(name="Xidməti", settings={})) is None


def test_each_group_opens_from_its_own_cohort_plan_with_fallback_warnings(world):
    result = semester_open.generate_offerings(
        organization=world["org"], period=world["period"], programs=[world["program"]], semester_number=3
    )
    assert _subjects(world, world["g25"]) == {"CH-A", "CH-C"}
    assert _subjects(world, world["g23"]) == {"CH-B", "CH-C"}  # 2023 planı yoxdur → ən son (2026)
    assert _subjects(world, world["gx"]) == {"CH-B", "CH-C"}
    fallbacks = {item["group"]: item["reason"] for item in result["cohort_fallbacks"]}
    assert fallbacks == {"CH-231": cohort_plans.FALLBACK_NO_PLAN, "CH-X": cohort_plans.FALLBACK_UNKNOWN_YEAR}
    text = " ".join(result["warnings"])
    assert "Bu qəbul ili üçün təsdiqlənmiş plan yoxdur — ən son plan tətbiq olundu" in text
    assert "CH-231" in text and "CH-X" in text and "CH-251" not in text
    hours = CourseOffering.objects.get(group=world["g25"], subject=world["shared"]).lesson_hours
    assert hours == 45  # kohort planının saatı

    again = semester_open.generate_offerings(
        organization=world["org"], period=world["period"], programs=[world["program"]], semester_number=3
    )
    assert again["created"] == 0 and again["existing"] == result["created"]


def test_old_rule_offerings_are_kept_and_reported(world):
    legacy = CourseOffering.objects.create(
        organization=world["org"], subject=world["new_only"], period=world["period"], group=world["g25"]
    )
    semester_open.generate_offerings(
        organization=world["org"], period=world["period"], programs=[world["program"]], semester_number=3
    )
    assert CourseOffering.objects.filter(pk=legacy.pk, is_active=True).exists()  # silinmir
    warnings = cohort_plans.period_cohort_warnings(world["org"], world["period"])
    assert warnings["mismatch_count"] == 1
    assert warnings["mismatch_examples"] == ["2026 planının fənni · CH-251"]
    assert any("avtomatik silinmir" in message for message in warnings["messages"])
    assert {item["group"] for item in warnings["fallbacks"]} == {"CH-231", "CH-X"}


def test_plan_hours_follow_the_group_cohort(world):
    g25_offering = CourseOffering.objects.create(
        organization=world["org"], subject=world["shared"], period=world["period"], group=world["g25"]
    )
    g23_offering = CourseOffering.objects.create(
        organization=world["org"], subject=world["shared"], period=world["period"], group=world["g23"]
    )
    assert plan_hours.plan_hours_for_offering(g25_offering) == {"lecture": 45}
    assert plan_hours.plan_hours_for_offering(g23_offering) == {"lecture": 15}  # ən son plan


def test_workload_generation_picks_rows_of_the_studying_cohort(world):
    from apps.workload.services.generation import _plan_rows_for

    rows, latest = _plan_rows_for(world["org"], [world["program"]], "2026/2027")
    picked = {(row.semester_number, row.subject.code, row.curriculum.admission_year) for row in rows}
    # Semestr 1 → 2026 qəbulu, semestr 3 → 2025 qəbulu.
    assert picked == {(1, "CH-F", 2026), (3, "CH-A", 2025), (3, "CH-C", 2025)}
    assert latest[world["program"].pk] == world["plan26"]
    rows_no_year, _ = _plan_rows_for(world["org"], [world["program"]])
    assert {row.curriculum_id for row in rows_no_year} == {world["plan26"].pk}


def test_legacy_group_course_and_cohort_come_from_one_source(world):
    """Rəy 2026-10-19: köçürülmüş qrupda ``admission_year`` İDXAL ilidir — kurs da, plan da addan gəlir."""
    from apps.registrar import services

    legacy = OrgUnit.objects.create(
        organization=world["org"],
        name="2/255 K",  # ad şablonu → 2025 qəbulu
        slug="ch-legacy",
        unit_type=OrgUnitType.GROUP,
        parent=world["g25"].parent,
        settings={"legacy": {"source": "atis"}, "admission_year": 2026},
    )
    assert cohort_plans.group_cohort_year(legacy) == 2025
    assert services.group_course_year(legacy, "2026/2027") == 2  # idxal ili (2026) olsaydı — 1-ci kurs
    assert legacy in semester_open.groups_for_semester(
        world["org"], world["program"], semester_number=3, academic_year="2026/2027"
    )
    semester_open.generate_offerings(
        organization=world["org"], period=world["period"], programs=[world["program"]], semester_number=3
    )
    assert _subjects(world, legacy) == {"CH-A", "CH-C"}  # 2025 planı
    warnings = cohort_plans.period_cohort_warnings(world["org"], world["period"])
    assert "2/255 K" not in {item["group"] for item in warnings["fallbacks"]}
    assert warnings["mismatch_count"] == 0


def test_workload_uses_group_cohort_and_reports_fallbacks(world):
    from apps.workload.services.generation import _groups_by_specialty, _plan_rows_for

    OrgUnit.objects.filter(pk__in=[world["g23"].pk, world["gx"].pk]).update(is_active=False)
    specialty_id = world["program"].specialty_unit_id
    group_map = _groups_by_specialty(world["org"], [specialty_id], "2026/2027")
    fallbacks: list = []
    rows, _latest = _plan_rows_for(world["org"], [world["program"]], "2026/2027", group_map, fallbacks)
    # Semestr 3 → oxuyan qrupun (CH-251) kohortu 2025; semestr 1 → qrup yoxdur, tədris ilindən 2026.
    assert {(row.semester_number, row.curriculum.admission_year) for row in rows} == {(1, 2026), (3, 2025)}
    assert fallbacks == []

    OrgUnit.objects.filter(pk=world["g25"].pk).update(is_active=False)
    OrgUnit.objects.filter(pk=world["g23"].pk).update(is_active=True)  # yalnız 2023 qəbulu — planı yoxdur
    group_map = _groups_by_specialty(world["org"], [specialty_id], "2026/2027")
    rows, _latest = _plan_rows_for(world["org"], [world["program"]], "2026/2027", group_map, fallbacks)
    assert {(row.semester_number, row.curriculum.admission_year) for row in rows} == {(1, 2026), (3, 2026)}
    assert [(item["semester"], item["admission_year"]) for item in fallbacks] == [(3, 2023)]


def test_workload_fallback_warning_when_cohort_plan_missing(world):
    from apps.workload.services.generation import _plan_rows_for

    world["plan25"].is_active = False  # eyni kohortun yeni versiyası təsdiqlənib → köhnə sətir vermir
    world["plan25"].save(update_fields=["is_active"])
    fallbacks: list = []
    rows, _latest = _plan_rows_for(world["org"], [world["program"]], "2026/2027", None, fallbacks)
    assert {row.curriculum.admission_year for row in rows} == {2026}
    assert [(item["semester"], item["admission_year"], item["plan_year"]) for item in fallbacks] == [(3, 2025, 2026)]
    text = " ".join(cohort_plans.fallback_messages(fallbacks))
    assert "Bu qəbul ili üçün təsdiqlənmiş plan yoxdur — ən son plan tətbiq olundu" in text
    assert "2025 qəbulu · semestr 3" in text

"""Database-level RLS tenant-isolation tests for the registrar tables.

Mirrors apps/organizations/tests/test_rls.py: data is created as the bypass
superuser, then the connection switches to the non-superuser ``rls_app_role``
(``SET LOCAL ROLE``) inside the test transaction so the RLS policies are
enforced. Each test asserts a tenant only sees its own
Program/Subject/Curriculum/CurriculumSubject rows.
"""

from django.contrib.auth import get_user_model
from django.db import connection

import pytest

from apps.organizations.models import Membership, Organization
from apps.registrar.models import Curriculum, CurriculumSubject, Program, Subject
from core.constants import OrganizationType, OrgUnitType

User = get_user_model()

pytestmark = pytest.mark.postgres


def _is_pg():
    return connection.vendor == "postgresql"


def _set(name, value):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _enable_rls_for_tenant(org_id):
    """Disable bypass, pin the tenant, and drop to the restricted app role.

    The role switch is transaction-scoped (``SET LOCAL``); the surrounding
    ``db`` fixture wraps the whole test in one transaction, so it stays in
    effect for every subsequent query in the test and reverts on rollback.
    """
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", str(org_id))
    _set("app.current_user_id", "")
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests(db):
    if not _is_pg():
        yield
        return
    _set("app.bypass_rls", "on")
    _set("app.current_org_id", "")
    try:
        yield
    finally:
        _set("app.bypass_rls", "off")
        _set("app.current_org_id", "")


@pytest.fixture()
def two_org_curricula():
    if not _is_pg():
        pytest.skip("registrar RLS tests require PostgreSQL")
    owner_a = User.objects.create_user("reg_a", "reg_a@x.test", "pw")
    owner_b = User.objects.create_user("reg_b", "reg_b@x.test", "pw")
    org_a = Organization.objects.create(
        name="Reg Org A",
        slug="reg-org-a",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner_a,
        status="active",
        is_active=True,
    )
    org_b = Organization.objects.create(
        name="Reg Org B",
        slug="reg-org-b",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner_b,
        status="active",
        is_active=True,
    )
    for org, code in ((org_a, "A"), (org_b, "B")):
        prog = Program.objects.create(organization=org, code=f"P-{code}", name=f"Program {code}")
        subj = Subject.objects.create(organization=org, code=f"S-{code}", name=f"Subject {code}")
        cur = Curriculum.objects.create(organization=org, program=prog, admission_year=2024)
        CurriculumSubject.objects.create(organization=org, curriculum=cur, subject=subj, semester_number=1)
    return org_a, org_b


def test_program_isolation(two_org_curricula):
    org_a, _org_b = two_org_curricula
    _enable_rls_for_tenant(org_a.pk)
    codes = set(Program.objects.values_list("code", flat=True))
    assert codes == {"P-A"}, f"tenant A saw cross-tenant programs: {codes}"


def test_subject_and_curriculum_isolation(two_org_curricula):
    _org_a, org_b = two_org_curricula
    _enable_rls_for_tenant(org_b.pk)
    subject_codes = set(Subject.objects.values_list("code", flat=True))
    curricula_years = list(Curriculum.objects.values_list("admission_year", flat=True))
    rows = CurriculumSubject.objects.count()
    assert subject_codes == {"S-B"}
    assert curricula_years == [2024]
    assert rows == 1, "tenant B must only see its own curriculum rows"


def test_missing_tenant_context_denies_all(two_org_curricula):
    _enable_rls_for_tenant("")  # no tenant → deny-all (secure default)
    assert Program.objects.count() == 0
    assert Subject.objects.count() == 0
    assert CurriculumSubject.objects.count() == 0


# ── Enrollment-layer RLS isolation (U2) ──────────────────────────────────────


@pytest.fixture()
def two_org_enrollments(two_org_curricula):
    """Add a student record + offering + enrollment to each org's data."""
    from apps.organizations.models import AcademicPeriod, OrgUnit
    from apps.registrar.models import CourseOffering, Curriculum, Enrollment, StudentAcademicRecord, Subject

    org_a, org_b = two_org_curricula
    for org, code in ((org_a, "A"), (org_b, "B")):
        subject = Subject.objects.get(organization=org, code=f"S-{code}")
        curriculum = Curriculum.objects.get(organization=org)
        group = OrgUnit.objects.create(
            organization=org, name=f"G-{code}", slug=f"g-{code.lower()}", unit_type=OrgUnitType.GROUP
        )
        period = AcademicPeriod.objects.create(
            organization=org,
            name=f"P-{code}",
            period_type="semester",
            academic_year="2024/2025",
            start_date="2024-09-01",
            end_date="2025-01-31",
        )
        student = User.objects.create_user(f"enr_{code}", f"enr_{code}@x.test", "pw")
        Membership.objects.create(
            organization=org,
            user=student,
            role=org.roles.get(name="student"),
            is_active=True,
        )
        StudentAcademicRecord.objects.create(
            organization=org,
            student=student,
            program=curriculum.program,
            curriculum=curriculum,
            group=group,
            admission_year=2024,
        )
        offering = CourseOffering.objects.create(organization=org, subject=subject, period=period, group=group)
        Enrollment.objects.create(organization=org, student=student, offering=offering)
    return org_a, org_b


def test_student_record_and_enrollment_isolation(two_org_enrollments):
    from apps.registrar.models import CourseOffering, Enrollment, StudentAcademicRecord

    org_a, _org_b = two_org_enrollments
    _enable_rls_for_tenant(org_a.pk)
    assert StudentAcademicRecord.objects.count() == 1
    assert CourseOffering.objects.count() == 1
    assert Enrollment.objects.count() == 1
    # The only visible enrollment belongs to tenant A's student.
    assert Enrollment.objects.get().student.username == "enr_A"


def test_enrollment_deny_all_without_tenant(two_org_enrollments):
    from apps.registrar.models import Enrollment, GroupElectiveChoice, StudentAcademicRecord

    _enable_rls_for_tenant("")
    assert StudentAcademicRecord.objects.count() == 0
    assert Enrollment.objects.count() == 0
    assert GroupElectiveChoice.objects.count() == 0


# ── Electronic-journal RLS isolation (U3) ────────────────────────────────────


@pytest.fixture()
def two_org_journals(two_org_enrollments):
    """Add an assessment scheme + a lesson + a lesson mark to each org."""
    import datetime

    from apps.registrar import gradebook
    from apps.registrar.models import CourseOffering, Enrollment

    org_a, org_b = two_org_enrollments
    for org in (org_a, org_b):
        offering = CourseOffering.objects.get(organization=org)
        gradebook.ensure_assessment_scheme(offering=offering)
        lesson = gradebook.create_lesson(allow_past=True, offering=offering, date=datetime.date(2024, 10, 1))
        enrollment = Enrollment.objects.get(organization=org)
        gradebook.save_marks(
            enforce_day=False,
            offering=offering,
            entries=[{"lesson_id": lesson.id, "enrollment_id": enrollment.id, "status": "absent"}],
        )
    return org_a, org_b


def test_journal_isolation(two_org_journals):
    from apps.registrar.models import AssessmentScheme, Lesson, LessonMark

    org_a, _org_b = two_org_journals
    _enable_rls_for_tenant(org_a.pk)
    assert AssessmentScheme.objects.count() == 1
    assert Lesson.objects.count() == 1
    assert LessonMark.objects.count() == 1
    assert set(LessonMark.objects.values_list("organization_id", flat=True)) == {org_a.pk}


def test_journal_deny_all_without_tenant(two_org_journals):
    from apps.registrar.models import AssessmentScheme, Lesson, LessonMark

    _enable_rls_for_tenant("")
    assert AssessmentScheme.objects.count() == 0
    assert Lesson.objects.count() == 0
    assert LessonMark.objects.count() == 0


# ── Timetable RLS isolation (U4) ─────────────────────────────────────────────


@pytest.fixture()
def two_org_schedules(two_org_enrollments):
    """Add a schedule slot to each org's offering."""
    import datetime

    from apps.registrar import schedule
    from apps.registrar.models import CourseOffering

    org_a, org_b = two_org_enrollments
    for org in (org_a, org_b):
        offering = CourseOffering.objects.get(organization=org)
        schedule.create_slot(
            offering=offering, weekday=1, start_time=datetime.time(9, 0), end_time=datetime.time(10, 30)
        )
    return org_a, org_b


def test_schedule_isolation(two_org_schedules):
    from apps.registrar.models import ScheduleSlot

    org_a, _org_b = two_org_schedules
    _enable_rls_for_tenant(org_a.pk)
    assert ScheduleSlot.objects.count() == 1
    assert set(ScheduleSlot.objects.values_list("organization_id", flat=True)) == {org_a.pk}


def test_schedule_deny_all_without_tenant(two_org_schedules):
    from apps.registrar.models import ScheduleSlot

    _enable_rls_for_tenant("")
    assert ScheduleSlot.objects.count() == 0


# ── Finals / resit RLS isolation (U3+) ───────────────────────────────────────


@pytest.fixture()
def two_org_finals(two_org_enrollments):
    """Add a final grade + a resit to each org's enrollment."""
    from apps.registrar.models import Enrollment, FinalGrade, ResitReason, ResitRecord

    org_a, org_b = two_org_enrollments
    for org in (org_a, org_b):
        enrollment = Enrollment.objects.get(organization=org)
        FinalGrade.objects.create(organization=org, enrollment=enrollment, exam_score=40)
        ResitRecord.objects.create(organization=org, enrollment=enrollment, reason=ResitReason.TOTAL)
    return org_a, org_b


def test_finals_isolation(two_org_finals):
    from apps.registrar.models import FinalGrade, ResitRecord

    org_a, _org_b = two_org_finals
    _enable_rls_for_tenant(org_a.pk)
    assert FinalGrade.objects.count() == 1
    assert ResitRecord.objects.count() == 1
    assert set(FinalGrade.objects.values_list("organization_id", flat=True)) == {org_a.pk}


def test_finals_deny_all_without_tenant(two_org_finals):
    from apps.registrar.models import FinalGrade, ResitRecord

    _enable_rls_for_tenant("")
    assert FinalGrade.objects.count() == 0
    assert ResitRecord.objects.count() == 0

"""Sahib 2026-10-27: «tyutor və laborantlar müəllimlərin keçilmiş dərs yükünə baxa bilsin, əlavə olaraq özlərinə aid
olan kafedra sillabusa, dərs materialı varsa ona baxmaq olsun».

Nəyi qoruyur (DEFOLT rol şablonları ilə — signal təşkilat yaradılanda əkir):

1. **Keçilmiş dərslər** — kafedra əhatəli laborant / tyutor öz kafedrasının müəllimlərinin dərslərini görür
   (köçürülmüş strukturda qrup kafedranın altında DEYİL — əvvəl boş idi); başqa kafedranınkı görünmür.
2. **Sillabus** — kafedranın sillabusu açılır (önizləmə + sənəd + PDF), başqa kafedranınkı 403/404; yazı
   (bölmə yadda saxlama, qərar, yaratma) rədd edilir.
3. **Dərs materialı** — «Kafedra materialları» bölməsi: əhatədəki qovluğun DƏRC EDİLMİŞ materialı görünür və
   endirilir; qaralama material, başqa kafedra və yazı əməli bağlıdır.
4. **Menyu** — tyutor / laborant bəndləri görür; adi müəllim və tələbə dəyişmir.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import lessons_log as lessons_service
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonKind, Subject
from apps.subject_folder import public as folders
from apps.subject_folder.services import unit_view
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

pytestmark = pytest.mark.django_db

User = get_user_model()
PDF = b"%PDF-1.4 material"
UNIT_SECTION = "unit-subject-folders"


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.UNIVERSITY_MODE = True


def _user(name):
    return User.objects.create_user(name, f"{name}@qku.edu.az", "pw", first_name=name.title(), last_name="Test")


def _member(org, user, role, unit):
    Membership.objects.create(
        user=user, organization=org, role=org.roles.get(name=role), scope_unit=unit, is_primary=True, is_active=True
    )
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role"])


def _approved_syllabus(org, offering, chair):
    syllabus = Syllabus.objects.create(
        organization=org,
        offering=offering,
        subject=offering.subject,
        period=offering.period,
        author=offering.instructor,
        chair_unit=chair,
    )
    now = timezone.now()
    version = SyllabusVersion.objects.create(
        organization=org,
        syllabus=syllabus,
        major=1,
        status="approved",
        locked_at=now,
        approved_at=now,
        approved_by=offering.instructor,
    )
    SyllabusSection.objects.create(organization=org, version=version, section_id="week", data={"rows": []})
    syllabus.approved_version = version
    syllabus.current_version = version
    syllabus.save(update_fields=["approved_version", "current_version", "updated_at"])
    return syllabus, version


@pytest.fixture
def world(django_capture_on_commit_callbacks):
    owner = _user("tl_owner")
    with bypass_rls():
        org = Organization.objects.create(
            name="TL Univ", slug="tl-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        faculty = OrgUnit.objects.create(organization=org, name="Fakültə", slug="tl-f", unit_type=OrgUnitType.FACULTY)
        chair = OrgUnit.objects.create(
            organization=org, name="Proqramlaşdırma", slug="tl-c1", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        other_chair = OrgUnit.objects.create(
            organization=org, name="Riyaziyyat", slug="tl-c2", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        specialty = OrgUnit.objects.create(
            organization=org, name="İT", slug="tl-s", unit_type=OrgUnitType.SPECIALTY, parent=faculty
        )
        group = OrgUnit.objects.create(
            organization=org, name="101 İT", slug="tl-g1", unit_type=OrgUnitType.GROUP, parent=specialty
        )
        other_group = OrgUnit.objects.create(
            organization=org, name="102 İT", slug="tl-g2", unit_type=OrgUnitType.GROUP, parent=specialty
        )
        period = AcademicPeriod.objects.create(
            organization=org,
            name="Payız 2026",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date="2026-09-01",
            end_date="2027-01-31",
            is_current=True,
        )
        teacher, other_teacher = _user("tl_teacher"), _user("tl_other")
        laborant, tutor, student = _user("tl_laborant"), _user("tl_tutor"), _user("tl_student")
        _member(org, teacher, "teacher", chair)
        _member(org, other_teacher, "teacher", other_chair)
        _member(org, laborant, "lab_assistant", chair)
        _member(org, tutor, "tutor", chair)
        _member(org, student, "student", group)
        subject = Subject.objects.create(organization=org, code="TL101", name="Alqoritmlər", chair_unit=chair)
        other_subject = Subject.objects.create(
            organization=org, code="TL202", name="Riyazi analiz", chair_unit=other_chair
        )
        offering = CourseOffering.objects.create(
            organization=org, subject=subject, period=period, group=group, instructor=teacher, lesson_hours=30
        )
        other_offering = CourseOffering.objects.create(
            organization=org,
            subject=other_subject,
            period=period,
            group=other_group,
            instructor=other_teacher,
            lesson_hours=30,
        )
        Enrollment.objects.create(organization=org, student=student, offering=offering, status="enrolled")
        lesson_date = dt.date(2026, 10, 5)
        lesson = Lesson.objects.create(
            organization=org,
            offering=offering,
            date=lesson_date,
            kind=LessonKind.LECTURE,
            topic="Kafedranın mövzusu",
            hours=2,
            instructor=teacher,
        )
        other_lesson = Lesson.objects.create(
            organization=org,
            offering=other_offering,
            date=lesson_date,
            kind=LessonKind.LECTURE,
            topic="Başqa kafedranın mövzusu",
            hours=2,
            instructor=other_teacher,
        )
        syllabus, version = _approved_syllabus(org, offering, chair)
        other_syllabus, _ = _approved_syllabus(org, other_offering, other_chair)

    def _folder(owner_user, subj, off):
        folder, _created, _summary = folders.create_folder(
            organization=org, subject=subj, owner=owner_user, by_user=owner_user, period=period
        )
        with django_capture_on_commit_callbacks(execute=True):
            folders.assign_folder(folder, [off], by_user=owner_user)
        folder.refresh_from_db()
        return folder

    folder = _folder(teacher, subject, offering)
    other_folder = _folder(other_teacher, other_subject, other_offering)
    published = folders.create_material(
        folder,
        by_user=teacher,
        kind="file",
        title="Mühazirə slaydı",
        file=SimpleUploadedFile("slayd.pdf", PDF, content_type="application/pdf"),
        is_published=True,
    )
    hidden = folders.create_material(
        folder,
        by_user=teacher,
        kind="file",
        title="Qaralama qeyd",
        file=SimpleUploadedFile("q.pdf", PDF, content_type="application/pdf"),
    )
    foreign = folders.create_material(
        other_folder,
        by_user=other_teacher,
        kind="file",
        title="Başqa kafedranın slaydı",
        file=SimpleUploadedFile("b.pdf", PDF, content_type="application/pdf"),
        is_published=True,
    )
    return locals()


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def _sections(world, user):
    response = _client(user, world["org"]).get(reverse("accounts:profile"))
    assert response.status_code == 200
    return set(response.context["allowed_sections"])


# ── Menyu ────────────────────────────────────────────────────────────────────


def test_laborant_and_tutor_see_the_read_only_sections(world):
    for key in ("laborant", "tutor"):
        sections = _sections(world, world[key])
        assert {"lessons-log", "syllabus-list", UNIT_SECTION} <= sections, key
        # Qərar səthləri açılmır (laborantın müəllim bayrağı ilə gələn öz qovluq bölmələri əvvəlki kimidir).
        assert not {"syllabus-review", "question-chair-review", "workload-distribution"} & sections, key


def test_teacher_and_student_menus_do_not_change(world):
    teacher_sections = _sections(world, world["teacher"])
    assert UNIT_SECTION not in teacher_sections
    assert {"lessons-log", "syllabus-list", "subject-folders"} <= teacher_sections
    student_sections = _sections(world, world["student"])
    assert not {UNIT_SECTION, "lessons-log", "syllabus-list"} & student_sections
    assert "my-subject-folders" in student_sections


def test_role_templates_carry_the_keys(world):
    org = world["org"]
    for role in ("tutor", "program_coordinator", "lab_assistant"):
        permissions = org.roles.get(name=role).permissions
        assert "syllabus.view" in permissions and "subject_folder.view_unit" in permissions, role
        assert "syllabus.edit" not in permissions and "syllabus.approve" not in permissions, role
    for role in ("teacher", "student", "chair_head", "dean"):
        assert "subject_folder.view_unit" not in org.roles.get(name=role).permissions, role


# ── Keçilmiş dərslər ────────────────────────────────────────────────────────


def test_kafedra_scoped_supervisor_sees_own_kafedra_lessons_only(world):
    org = world["org"]
    for key in ("laborant", "tutor"):
        user = world[key]
        assert lessons_service.is_supervisor(user, org)
        visible = set(lessons_service.scoped_lessons(user, org, supervisor=True).values_list("pk", flat=True))
        assert world["lesson"].pk in visible, key
        assert world["other_lesson"].pk not in visible, key


def test_lessons_log_section_renders_kafedra_lessons(world):
    response = _client(world["laborant"], world["org"]).get(
        reverse("accounts:profile"), {"section": "lessons-log", "ll_range": "all", "ll_season": "all"}
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "Kafedranın mövzusu" in body
    assert "Başqa kafedranın mövzusu" not in body


def test_teacher_lessons_scope_unchanged(world):
    org, teacher = world["org"], world["teacher"]
    assert not lessons_service.is_supervisor(teacher, org)
    visible = set(lessons_service.scoped_lessons(teacher, org, supervisor=False).values_list("pk", flat=True))
    assert visible == {world["lesson"].pk}


# ── Sillabus ────────────────────────────────────────────────────────────────


def test_syllabus_view_in_scope_and_denied_outside(world):
    for key in ("laborant", "tutor"):
        client = _client(world[key], world["org"])
        own, other = world["syllabus"].pk, world["other_syllabus"].pk
        assert client.get(reverse("accounts:syllabus_preview", args=[own])).status_code == 200, key
        assert client.get(reverse("accounts:syllabus_detail", args=[own])).status_code == 200, key
        assert client.get(reverse("accounts:syllabus_preview", args=[other])).status_code == 403, key
        assert client.get(reverse("accounts:syllabus_detail", args=[other])).status_code == 404, key
        assert client.get(reverse("accounts:syllabus_detail_pdf", args=[other])).status_code == 404, key


def test_syllabus_list_shows_only_own_kafedra(world):
    response = _client(world["laborant"], world["org"]).get(reverse("accounts:profile"), {"section": "syllabus-list"})
    assert response.status_code == 200
    body = response.content.decode()
    assert "Alqoritmlər" in body
    assert "Riyazi analiz" not in body


def test_syllabus_writes_are_denied(world):
    client = _client(world["laborant"], world["org"])
    version = world["version"]
    save = client.post(
        reverse("accounts:syllabus_section_save", args=[version.pk]),
        data='{"section": "info", "data": {"teacher": "x"}, "revision": 1}',
        content_type="application/json",
    )
    assert save.status_code in (403, 404)
    decision = client.post(
        reverse("accounts:syllabus_decision", args=[version.pk]),
        data='{"action": "approve"}',
        content_type="application/json",
    )
    assert decision.status_code == 404
    create = client.post(
        reverse("accounts:syllabus_action"),
        data='{"action": "create", "offering": "%s"}' % world["offering"].pk,
        content_type="application/json",
    )
    assert create.status_code == 403
    version.refresh_from_db()
    assert version.status == "approved"


# ── Dərs materialı ──────────────────────────────────────────────────────────


def test_unit_view_scope(world):
    org = world["org"]
    for key in ("laborant", "tutor"):
        visible = set(unit_view.visible_folders(world[key], org).values_list("pk", flat=True))
        assert visible == {world["folder"].pk}, key
    assert not unit_view.has_unit_view(world["teacher"], org)
    assert not unit_view.has_unit_view(world["student"], org)


def test_unit_materials_panel_lists_and_opens_own_kafedra_folder(world):
    client = _client(world["laborant"], world["org"])
    listing = client.get(reverse("accounts:profile"), {"section": UNIT_SECTION})
    assert listing.status_code == 200
    body = listing.content.decode()
    assert world["folder"].title in body
    assert world["other_folder"].title not in body

    opened = client.get(reverse("accounts:profile"), {"section": UNIT_SECTION, "sf_folder": world["folder"].pk})
    body = opened.content.decode()
    assert "Mühazirə slaydı" in body
    assert "Qaralama qeyd" not in body
    assert "data-sf-post" not in body and "data-sf-open" not in body

    foreign = client.get(reverse("accounts:profile"), {"section": UNIT_SECTION, "sf_folder": world["other_folder"].pk})
    assert "Başqa kafedranın slaydı" not in foreign.content.decode()


def test_material_download_scope(world):
    url = lambda material: reverse("subject_folder:material_download", args=[material.pk])  # noqa: E731
    for key in ("laborant", "tutor"):
        client = _client(world[key], world["org"])
        assert client.get(url(world["published"])).status_code == 200, key
        assert client.get(url(world["hidden"])).status_code == 404, key
        assert client.get(url(world["foreign"])).status_code == 404, key
    # Qeydiyyatı olmayan tələbə başqa kafedranın materialını endirə bilmir (dəyişməyib).
    assert _client(world["student"], world["org"]).get(url(world["foreign"])).status_code == 404


def test_material_writes_are_denied(world):
    client = _client(world["laborant"], world["org"])
    folder = world["folder"]
    before = folder.materials.count()
    response = client.post(
        reverse("subject_folder:action"),
        {"action": "material_save", "folder": str(folder.pk), "kind": "link", "title": "X", "url": "https://x.test"},
    )
    assert response.status_code in (403, 404)
    unpublish = client.post(
        reverse("subject_folder:action"),
        {"action": "material_publish", "material": str(world["published"].pk), "published": "0"},
    )
    assert unpublish.status_code in (400, 403, 404)
    assert folder.materials.count() == before
    world["published"].refresh_from_db()
    assert world["published"].is_published


def test_student_cannot_open_unit_section(world):
    response = _client(world["student"], world["org"]).get(reverse("accounts:profile"), {"section": UNIT_SECTION})
    assert "Mühazirə slaydı" not in response.content.decode()


# ── Mövcud tenant: miqrasiya 0074 ───────────────────────────────────────────


def test_migration_0074_grants_idempotently_and_reverts_only_new_key(world):
    import importlib

    from django.apps import apps as django_apps

    migration = importlib.import_module("apps.organizations.migrations.0074_tutor_laborant_unit_view")
    org = world["org"]
    with bypass_rls():
        role = org.roles.get(name="lab_assistant")
        role.permissions = ["course.view", "journal.lessons_unit"]
        role.save(update_fields=["permissions"])
        migration.forward(django_apps, None)
        migration.forward(django_apps, None)
        role.refresh_from_db()
        assert role.permissions == ["course.view", "journal.lessons_unit", "syllabus.view", "subject_folder.view_unit"]
        assert "subject_folder.view_unit" in org.roles.get(name="trustee").permissions
        migration.backward(django_apps, None)
        role.refresh_from_db()
    assert role.permissions == ["course.view", "journal.lessons_unit", "syllabus.view"]

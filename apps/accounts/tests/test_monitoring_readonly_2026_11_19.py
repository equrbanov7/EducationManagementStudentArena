"""Monitorinq şöbəsi — bütün təşkilat üzrə YALNIZ-OXU (sahib 2026-11-19).

Sahib: «Monitorinq şöbəsinə jurnallara, sillabuslara, fənn qovluqlarına FULL baxmaq icazəsi ver. Dərs cədvəlinə,
cədvəl idarəetməsinə baxmaq icazəsi olsun … Keçilmiş dərslərə və s. də icazəsi olsun.»

Nəyi qoruyur (DEFOLT rol şablonu ilə — signal təşkilat yaradılanda əkir; üzvlükdə ``scope_unit`` = «Monitorinq
şöbəsi», yəni miqrasiya 0085-dən sonrakı prod vəziyyəti):

1. **Menyu** — oxu bölmələri görünür; idarəetmə / qərar bölmələri görünmür.
2. **Jurnal** — siyahı bütün təşkilat, İSTƏNİLƏN kafedranın jurnalı və xlsx açılır; yazı rədd edilir.
3. **Sillabus** — istənilən kafedranın sillabusu açılır; bölmə yazısı / qərar / yaratma rədd edilir.
4. **Fənn qovluqları** — hər kafedranın dərc edilmiş materialı görünür və endirilir; yazı rədd edilir.
5. **Cədvəl idarəetməsi** — yalnız-oxu render (redaktə idarələri yoxdur); üç yazı endpoint-i 403.
6. **Keçilmiş dərslər** — nəzarət görünüşü bütün təşkilat üzrə.
7. **Siyahılar** — müəllimlər, tələbələr, qruplar, semestr, tədris planı, dərs yükü icmalı, analitika fraqmentləri 200.
"""

from __future__ import annotations

import datetime as dt
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import journal_access
from apps.registrar import lessons_log as lessons_service
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    LessonKind,
    Program,
    ScheduleSlot,
    StudentAcademicRecord,
    Subject,
)
from apps.subject_folder import public as folders
from apps.subject_folder.services import unit_view
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

pytestmark = pytest.mark.django_db

User = get_user_model()
PDF = b"%PDF-1.4 material"
MONITORS = ("head", "staff")

READ_SECTIONS = {
    "my-journal",
    "lessons-log",
    "syllabus-list",
    "unit-subject-folders",
    "schedule-manage",
    "people-teachers",
    "people-students",
    "groups-registry",
    "org-structure-tree",
    "chair-profile",
    "programs-registry",
    "subject-catalog",
    "curriculum-editor",
    "semester-opening",
    "workload-overview",
    "analytics",
    "academic-records",
    "student-registry",
}
#: İdarəetmə / qərar / başqa şöbənin səthləri — monitorinqdə OLMAMALIDIR.
FORBIDDEN_SECTIONS = {
    "workload-distribution",
    "workload-center",
    "workload-visa",
    "workload-approval",
    "teaching-handover",
    "syllabus-review",
    "question-chair-review",
    "journal-close",
    "journal-hygiene",
    "exam-score-entry",
    "rim-center",
    "audit-log",
    "org-roles",
    "org-members",
    "accounting",
    "hr-analytics",
    "evaluation-results",
    "student-intake",
    "student-admission",
    "system-settings",
    "system-monitoring",
    "account-password-reset",
    "subgroup-placement",
    "subject-folders",
}


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
    """İki AYRI fakültə (hərəsində kafedra + ixtisas + qrup + müəllim + jurnal + sillabus + qovluq) və şöbə."""
    owner = _user("mn_owner")
    today = dt.date.today()
    # Cədvəl şəbəkəsi B.e.–Şənbə göstərir: bazar günü düşən dərs/slot kart kimi görünmür (CI bazar günü düşürdü).
    lesson_day = today - dt.timedelta(days=7)
    if lesson_day.isoweekday() == 7:
        lesson_day -= dt.timedelta(days=1)
    with bypass_rls():
        org = Organization.objects.create(
            name="MN Univ", slug="mn-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        department = OrgUnit.objects.create(
            organization=org, name="Monitorinq şöbəsi", slug="mn-dep", unit_type=OrgUnitType.DEPARTMENT
        )
        period = AcademicPeriod.objects.create(
            organization=org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date=today - dt.timedelta(days=40),
            end_date=today + dt.timedelta(days=80),
            is_current=True,
        )
        sides = {}
        for key, subject_name in (("a", "Alqoritmlər"), ("b", "Riyazi analiz")):
            faculty = OrgUnit.objects.create(
                organization=org, name=f"Fakültə {key.upper()}", slug=f"mn-f-{key}", unit_type=OrgUnitType.FACULTY
            )
            chair = OrgUnit.objects.create(
                organization=org,
                name=f"Kafedra {key.upper()}",
                slug=f"mn-c-{key}",
                unit_type=OrgUnitType.CHAIR,
                parent=faculty,
            )
            specialty = OrgUnit.objects.create(
                organization=org,
                name=f"İxtisas {key.upper()}",
                slug=f"mn-s-{key}",
                unit_type=OrgUnitType.SPECIALTY,
                parent=faculty,
            )
            group = OrgUnit.objects.create(
                organization=org,
                name=f"10{key.upper()} qrup",
                slug=f"mn-g-{key}",
                unit_type=OrgUnitType.GROUP,
                parent=specialty,
            )
            teacher, student = _user(f"mn_teacher_{key}"), _user(f"mn_student_{key}")
            _member(org, teacher, "teacher", chair)
            _member(org, student, "student", group)
            subject = Subject.objects.create(
                organization=org, code=f"MN10{key.upper()}", name=subject_name, chair_unit=chair
            )
            offering = CourseOffering.objects.create(
                organization=org, subject=subject, period=period, group=group, instructor=teacher, lesson_hours=30
            )
            Enrollment.objects.create(organization=org, student=student, offering=offering, status="enrolled")
            program = Program.objects.create(organization=org, code=f"MNP{key.upper()}", name=f"Proqram {key.upper()}")
            curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2026)
            StudentAcademicRecord.objects.create(
                organization=org,
                student=student,
                program=program,
                curriculum=curriculum,
                group=group,
                admission_year=2026,
            )
            lesson = Lesson.objects.create(
                organization=org,
                offering=offering,
                date=lesson_day,
                kind=LessonKind.LECTURE,
                topic=f"Mövzu {key.upper()} kafedrası",
                hours=2,
                start_time=dt.time(10, 10),
                end_time=dt.time(11, 40),
                instructor=teacher,
                created_by=teacher,
            )
            slot = ScheduleSlot.objects.create(
                organization=org,
                offering=offering,
                weekday=lesson.date.isoweekday(),  # dərsin günü — otaq cədvəl slotundan tapılsın
                start_time=dt.time(10, 10),
                end_time=dt.time(11, 40),
                kind="lecture",
                room=f"30{1 if key == 'a' else 2}",
            )
            syllabus, version = _approved_syllabus(org, offering, chair)
            sides[key] = {
                "faculty": faculty,
                "chair": chair,
                "group": group,
                "teacher": teacher,
                "student": student,
                "subject": subject,
                "offering": offering,
                "lesson": lesson,
                "slot": slot,
                "syllabus": syllabus,
                "version": version,
            }
        head, staff = _user("mn_head"), _user("mn_staff")
        # Prod vəziyyəti (miqrasiya 0085-dən sonra): ORGANIZATION rolu, üzvlükdə şöbə qalır.
        _member(org, head, "monitoring_head", department)
        _member(org, staff, "monitoring_staff", department)

    for key, side in sides.items():
        folder, _created, _summary = folders.create_folder(
            organization=org, subject=side["subject"], owner=side["teacher"], by_user=side["teacher"], period=period
        )
        with django_capture_on_commit_callbacks(execute=True):
            folders.assign_folder(folder, [side["offering"]], by_user=side["teacher"])
        folder.refresh_from_db()
        side["folder"] = folder
        side["published"] = folders.create_material(
            folder,
            by_user=side["teacher"],
            kind="file",
            title=f"Slayd {key.upper()}",
            file=SimpleUploadedFile("slayd.pdf", PDF, content_type="application/pdf"),
            is_published=True,
        )
        side["draft"] = folders.create_material(
            folder,
            by_user=side["teacher"],
            kind="file",
            title=f"Qaralama {key.upper()}",
            file=SimpleUploadedFile("q.pdf", PDF, content_type="application/pdf"),
        )
        side["task"] = folders.create_task(
            folder, by_user=side["teacher"], kind="homework", title=f"Ev tapşırığı {key.upper()}"
        )
    return {"org": org, "period": period, "department": department, "head": head, "staff": staff, **sides}


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


def _section(world, user, section, **params):
    return _client(user, world["org"]).get(reverse("accounts:profile"), {"section": section, **params})


# ── 1. Menyu ─────────────────────────────────────────────────────────────────


def test_monitor_menu_has_the_read_surfaces_and_no_management_surface(world):
    for key in MONITORS:
        sections = _sections(world, world[key])
        assert READ_SECTIONS <= sections, (key, READ_SECTIONS - sections)
        assert not FORBIDDEN_SECTIONS & sections, (key, FORBIDDEN_SECTIONS & sections)


def test_plain_admin_unit_head_still_sees_no_academic_surface(world):
    """Köçürülməyən inzibati şöbə müdiri (məs. Arxiv) əvvəlki kimidir — rolun özü genişlənmir."""
    org = world["org"]
    other = _user("mn_archive_head")
    with bypass_rls():
        archive = OrgUnit.objects.create(
            organization=org, name="Arxiv şöbəsi", slug="mn-arch", unit_type=OrgUnitType.DEPARTMENT
        )
        _member(org, other, "admin_unit_head", archive)
    sections = _sections(world, other)
    assert not {"my-journal", "lessons-log", "syllabus-list", "unit-subject-folders"} & sections


# ── 2. Jurnal ────────────────────────────────────────────────────────────────


def test_journal_list_is_org_wide(world):
    for key in MONITORS:
        response = _client(world[key], world["org"]).get(reverse("registrar:journal_list"))
        assert response.status_code == 200
        assert response.context["journal_is_broad"]
        listed = {row.id for row in response.context["offerings"]}
        assert {world["a"]["offering"].id, world["b"]["offering"].id} <= listed, key


def test_any_chairs_journal_opens_read_only_with_xlsx(world):
    for key in MONITORS:
        client = _client(world[key], world["org"])
        for side in ("a", "b"):
            offering = world[side]["offering"]
            page = client.get(reverse("registrar:journal_detail", args=[offering.id]))
            assert page.status_code == 200, (key, side)
            assert page.context["can_edit"] is False
            assert page.context["show_lesson_timing"] is True  # əməkdaş: saat + otaq görünür
            body = page.content.decode()
            assert world[side]["subject"].name in body
            assert f'data-room="{world[side]["slot"].room} · cədvəl üzrə"' in body, (key, side)
            xlsx = client.get(reverse("registrar:journal_xlsx", args=[offering.id]))
            assert xlsx.status_code == 200, (key, side)
            assert journal_access.can_observe_journal(world[key], offering)
            assert not journal_access.can_edit_journal(world[key], offering)
            assert not journal_access.is_direct_editor(world[key], offering)


def test_journal_writes_are_refused(world):
    offering, lesson = world["a"]["offering"], world["a"]["lesson"]
    for key in MONITORS:
        client = _client(world[key], world["org"])
        url = reverse("registrar:journal_detail", args=[offering.id])
        add = client.post(url, {"action": "add_lesson", "lesson_date": dt.date.today().isoformat(), "kind": "lecture"})
        assert add.status_code in (403, 404), key
        marks = client.post(url, {"action": "save_marks"})
        assert marks.status_code in (403, 404), key
        edit = client.post(
            reverse("registrar:journal_lesson_action", args=[offering.id, lesson.id]),
            {"action": "update_lesson", "lesson_date": lesson.date.isoformat(), "topic": "DƏYİŞDİ"},
        )
        assert edit.status_code in (302, 403, 404), key
        delete = client.post(
            reverse("registrar:journal_lesson_action", args=[offering.id, lesson.id]), {"action": "delete_lesson"}
        )
        assert delete.status_code in (302, 403, 404), key
    with bypass_rls():
        assert Lesson.objects.filter(offering=offering).count() == 1
        lesson.refresh_from_db()
    assert lesson.topic == "Mövzu A kafedrası"


# ── 3. Sillabus ──────────────────────────────────────────────────────────────


def test_any_chairs_syllabus_opens(world):
    for key in MONITORS:
        client = _client(world[key], world["org"])
        for side in ("a", "b"):
            pk = world[side]["syllabus"].pk
            assert client.get(reverse("accounts:syllabus_preview", args=[pk])).status_code == 200, (key, side)
            assert client.get(reverse("accounts:syllabus_detail", args=[pk])).status_code == 200, (key, side)
        listing = _section(world, world[key], "syllabus-list")
        assert listing.status_code == 200
        body = listing.content.decode()
        assert "Alqoritmlər" in body and "Riyazi analiz" in body, key


def test_syllabus_writes_are_refused(world):
    version = world["b"]["version"]
    for key in MONITORS:
        client = _client(world[key], world["org"])
        save = client.post(
            reverse("accounts:syllabus_section_save", args=[version.pk]),
            data='{"section": "info", "data": {"teacher": "x"}, "revision": 1}',
            content_type="application/json",
        )
        assert save.status_code in (403, 404), key
        decision = client.post(
            reverse("accounts:syllabus_decision", args=[version.pk]),
            data='{"action": "reject", "comment": "x"}',
            content_type="application/json",
        )
        assert decision.status_code in (403, 404), key
        create = client.post(
            reverse("accounts:syllabus_action"),
            data='{"action": "create", "offering": "%s"}' % world["b"]["offering"].pk,
            content_type="application/json",
        )
        assert create.status_code == 403, key
    version.refresh_from_db()
    assert version.status == "approved"


# ── 4. Fənn qovluqları ───────────────────────────────────────────────────────


def test_every_chairs_folder_and_published_material_is_visible(world):
    org = world["org"]
    both = {world["a"]["folder"].pk, world["b"]["folder"].pk}
    for key in MONITORS:
        assert set(unit_view.visible_folders(world[key], org).values_list("pk", flat=True)) == both, key
        listing = _section(world, world[key], "unit-subject-folders").content.decode()
        assert world["a"]["folder"].title in listing and world["b"]["folder"].title in listing, key
        opened = _section(world, world[key], "unit-subject-folders", sf_folder=world["b"]["folder"].pk)
        body = opened.content.decode()
        # TAM baxış (sahib: «fənn qovluqlarına FULL baxmaq»): jurnalı oxuyan əməkdaş dərc edilməmiş materialı və
        # tapşırıqları da görür — nişanla; yazı idarəsi yenə render olunmur.
        assert "Slayd B" in body and "Qaralama B" in body and "Ev tapşırığı B" in body
        assert "Tam baxış (yalnız oxu)" in body and "dərc edilməyib" in body
        assert "data-sf-post" not in body and "data-sf-open" not in body  # yazı idarəsi render olunmur
        client = _client(world[key], org)
        for side in ("a", "b"):
            url = reverse("subject_folder:material_download", args=[world[side]["published"].pk])
            assert client.get(url).status_code == 200, (key, side)
            # Dərc edilməmiş materialın endirilməsi də açıqdır — mövcud «əhatəli əməkdaş» qaydası: ``journal.view``
            # əhatəsi qrupu örtən aktor qovluğu YALNIZ OXUYUR (``subject_folder.services.access.is_staff_viewer``).
            hidden = reverse("subject_folder:material_download", args=[world[side]["draft"].pk])
            assert client.get(hidden).status_code == 200, (key, side)


def test_folder_writes_are_refused(world):
    folder, published = world["a"]["folder"], world["a"]["published"]
    before = folder.materials.count()
    for key in MONITORS:
        client = _client(world[key], world["org"])
        save = client.post(
            reverse("subject_folder:action"),
            {"action": "material_save", "folder": str(folder.pk), "kind": "link", "title": "X", "url": "https://x.t"},
        )
        assert save.status_code in (403, 404), key
        unpublish = client.post(
            reverse("subject_folder:action"),
            {"action": "material_publish", "material": str(published.pk), "published": "0"},
        )
        assert unpublish.status_code in (400, 403, 404), key
    assert folder.materials.count() == before
    published.refresh_from_db()
    assert published.is_published


# ── 5. Cədvəl idarəetməsi ────────────────────────────────────────────────────


def test_schedule_management_opens_read_only_for_any_group_and_teacher(world):
    for key in MONITORS:
        for side in ("a", "b"):
            response = _section(world, world[key], "schedule-manage", sm_group=str(world[side]["group"].id))
            assert response.status_code == 200, (key, side)
            body = response.content.decode()
            assert "smtx__table" in body and "data-sedit-read-only" in body, (key, side)
            assert 'data-can-edit="0"' in body
            for marker in ("data-sedit-new", "data-sedit-slot", 'id="seditCell"', 'id="seditMove"', 'id="seditParked"'):
                assert marker not in body, (key, side, marker)
            assert "smtx-card" in body  # mövcud slot yalnız-oxu kart kimi
            assert world["a"]["group"].name in body and world["b"]["group"].name in body  # hər iki fakültənin qrupu
        by_teacher = _section(
            world, world[key], "schedule-manage", sm_view="teacher", sm_teacher=str(world["b"]["teacher"].pk)
        )
        assert by_teacher.status_code == 200
        teacher_body = by_teacher.content.decode()
        # Müəllim süzgəci hər iki fakültənin müəllimini təklif edir; cədvəl şəbəkəsi yalnız-oxu render olunur.
        assert "Mn_Teacher_A" in teacher_body and "Mn_Teacher_B" in teacher_body, key
        assert "smtx__table" in teacher_body and "data-sedit-read-only" in teacher_body, key


def test_schedule_write_endpoints_are_forbidden(world):
    side = world["a"]
    cell = {
        "action": "save",
        "group_id": str(side["group"].id),
        "period_id": str(world["period"].id),
        "subject_id": str(side["subject"].id),
        "instructor_id": str(side["teacher"].id),
        "weekday": 2,
        "time_slot": "10:10|11:40",
        "week_type": "all",
        "slot_kind": "lecture",
        "room": "",
    }
    for key in MONITORS:
        client = _client(world[key], world["org"])
        editor = client.post(
            reverse("accounts:schedule_editor_action"), data=json.dumps(cell), content_type="application/json"
        )
        assert editor.status_code == 403, key
        delete = client.post(
            reverse("accounts:schedule_editor_action"),
            data=json.dumps({"action": "delete", "slot_id": str(side["slot"].id)}),
            content_type="application/json",
        )
        assert delete.status_code == 403, key
        assert client.post(reverse("accounts:schedule_manage_check"), {}).status_code == 403, key
        assert client.post(reverse("accounts:schedule_manage_action"), {}).status_code == 403, key
    with bypass_rls():
        assert ScheduleSlot.objects.filter(offering=side["offering"]).count() == 1


# ── 6. Keçilmiş dərslər ──────────────────────────────────────────────────────


def test_lessons_log_supervision_is_org_wide(world):
    org = world["org"]
    both = {world["a"]["lesson"].pk, world["b"]["lesson"].pk}
    for key in MONITORS:
        user = world[key]
        assert lessons_service.is_supervisor(user, org)
        with bypass_rls():
            visible = set(lessons_service.scoped_lessons(user, org, supervisor=True).values_list("pk", flat=True))
        assert visible == both, key
        body = _section(world, user, "lessons-log", ll_range="all", ll_season="all").content.decode()
        assert "Mövzu A kafedrası" in body and "Mövzu B kafedrası" in body, key


# ── 7. Siyahılar ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "section",
    [
        "people-teachers",
        "people-students",
        "groups-registry",
        "semester-opening",
        "curriculum-editor",
        "workload-overview",
        "analytics",
        "student-registry",
        "org-structure-tree",
        "subject-catalog",
    ],
)
def test_read_sections_render(world, section):
    client = _client(world["head"], world["org"])
    fragment = client.get(reverse("accounts:profile_section_fragment", kwargs={"section": section}))
    assert fragment.status_code == 200, section


def test_people_lists_are_org_wide_and_actions_are_forbidden(world):
    """Müəllim / tələbə kataloqu hər iki fakültəni göstərir (kontakt sütunu olmadan da render olunur); əməl 403."""
    client = _client(world["head"], world["org"])
    with bypass_rls():
        teachers = client.get(reverse("accounts:people_list", kwargs={"kind": "teachers"})).json()
        students = client.get(reverse("accounts:people_list", kwargs={"kind": "students"})).json()
    assert {"mn_teacher_a", "mn_teacher_b"} <= {row["username"] for row in teachers["results"]}
    assert {"mn_student_a", "mn_student_b"} <= {row["username"] for row in students["results"]}
    blocked = client.post(
        reverse("accounts:people_action"),
        data=json.dumps({"action": "block", "user_id": world["a"]["teacher"].pk, "reason": "monitorinq testi"}),
        content_type="application/json",
    )
    assert blocked.status_code == 403
    world["a"]["teacher"].refresh_from_db()
    assert world["a"]["teacher"].is_active

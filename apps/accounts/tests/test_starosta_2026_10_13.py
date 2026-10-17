"""Starosta — təyinat qaydaları + «Starosta» bölməsinin məzmunu (2026-10-13 (gecə)).

Sahib: «qrupa starosta əlavə etmək yerinə yenidən bax, problem olan hissəni dəyiş», «starosta kabinetdə əsas
üstünlüyü o olmalıdır ki, seçmə fənn ya da başqa qrupun nə işi olarsa görünsün», «Qrupum yerinə Starosta
bilinsin». Kilidlənən müqavilə:

* təyinat YALNIZ qrup reyestrinin əməli ilə (`accounts:group_lead_action`): açar (`unit.group_manage` /
  `role.assign`) + əhatə, yalnız qrupun qeydiyyatlı tələbəsi, bir qrupda bir starosta (dəyiş = köhnə
  götürülür), `scope_unit` = qrup, audit + bildiriş; götürmə tələbənin `student` üzvlüyünə toxunmur;
* ümumi rol axınları (`grant_role`, «Rol təyin et») `lead_student` vermir;
* köçürülmüş starosta köhnə qrupun bölməsini görmür; `repair_group_leads` sınıq sətirləri düzəldir;
* bölmə: seçmə fənlər + götürənlərin adları, birləşmiş dərslər (başqa qrupun jurnalı / qonaq qrup / axın),
  alt qruplar, cədvəl, imtahan, qrup elanı; yoldaşların qayıbı və təkrar fənni GÖRÜNMÜR; ad «Starosta».
"""

from __future__ import annotations

import datetime
from io import StringIO

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import (
    AcademicStatus,
    CourseOffering,
    Curriculum,
    Enrollment,
    EnrollmentKind,
    Program,
    ScheduleSlot,
    SlotKind,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

LEAD_PERMISSIONS = ["course.view", "exam.view", "appeal.create", "member.view", "analytics.view_own"]
STUDENT_PERMISSIONS = ["course.view", "exam.view", "appeal.create"]


def _role(org, name, *, level, scope_type, permissions):
    role, _created = Role.objects.update_or_create(
        organization=org,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": scope_type,
            "permissions": list(permissions),
            "is_active": True,
        },
    )
    return role


@override_settings(UNIVERSITY_MODE=True)
class StarostaTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.owner = User.objects.create_user("st_owner", "st_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ST Univ",
                slug="st-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="st-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.other_faculty = OrgUnit.objects.create(
                organization=cls.org, name="Başqa fakültə", slug="st-fac2", unit_type=OrgUnitType.FACULTY
            )
            specialty = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="İxtisas",
                slug="st-spec",
                unit_type=OrgUnitType.SPECIALTY,
            )
            other_specialty = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.other_faculty,
                name="İxtisas 2",
                slug="st-spec2",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, parent=specialty, name="ST-101", slug="st-101", unit_type=OrgUnitType.GROUP
            )
            cls.neighbour = OrgUnit.objects.create(
                organization=cls.org, parent=specialty, name="ST-102", slug="st-102", unit_type=OrgUnitType.GROUP
            )
            cls.subgroup = OrgUnit.objects.create(
                organization=cls.org,
                parent=specialty,
                name="ST-101-1",
                slug="st-101-1",
                unit_type=OrgUnitType.GROUP,
                settings={"parent_group": str(cls.group.pk)},
            )
            cls.far_group = OrgUnit.objects.create(
                organization=cls.org,
                parent=other_specialty,
                name="FAR-1",
                slug="far-1",
                unit_type=OrgUnitType.GROUP,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=90),
            )
            cls.program = Program.objects.create(
                organization=cls.org, specialty_unit=specialty, code="ST", name="Proqram"
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2026)

            cls.student_role = _role(
                cls.org, "student", level=10, scope_type=RoleScopeType.UNIT, permissions=STUDENT_PERMISSIONS
            )
            cls.lead_role = _role(
                cls.org, "lead_student", level=30, scope_type=RoleScopeType.UNIT, permissions=LEAD_PERMISSIONS
            )
            coordinator_role = _role(
                cls.org,
                "program_coordinator",
                level=45,
                scope_type=RoleScopeType.UNIT,
                permissions=["unit.view", "unit.group_manage", "member.view"],
            )
            cls.rim_role = _role(
                cls.org,
                "rim_operator",
                level=70,
                scope_type=RoleScopeType.ORGANIZATION,
                # QA-2 F-03 (2026-10-17): `role.assign` starosta üçün yalnız tələbə tərəfi açarı ilə (real RİM rəhbəri).
                permissions=["role.assign", "role.view", "org.manage_members", "member.view", "people.view_students"],
            )

            cls.ali = cls._student("st_ali", "Əli", "Abbasov", "1001", cls.group)
            cls.bina = cls._student("st_bina", "Binə", "Bayramova", "1002", cls.group)
            cls.cavid = cls._student("st_cavid", "Cavid", "Cəfərov", "1003", cls.group)
            cls.leave = cls._student(
                "st_leave", "Dilarə", "Dadaşova", "1004", cls.group, status=AcademicStatus.ACADEMIC_LEAVE
            )
            cls.neighbour_student = cls._student("st_nb", "Elnur", "Əliyev", "2001", cls.neighbour)
            cls.sub_student = cls._student("st_sub", "Fərid", "Fərzəliyev", "3001", cls.subgroup)
            cls.far_student = cls._student("st_far", "Gülnar", "Qasımova", "4001", cls.far_group)

            cls.coordinator = User.objects.create_user("st_coord", "c@qku.edu.az", "pw", first_name="Koord")
            Membership.objects.create(
                user=cls.coordinator,
                organization=cls.org,
                role=coordinator_role,
                scope_unit=cls.faculty,
                is_active=True,
            )
            cls.rim = User.objects.create_user("st_rim", "r@qku.edu.az", "pw", first_name="Rim")
            Membership.objects.create(user=cls.rim, organization=cls.org, role=cls.rim_role, is_active=True)
            cls.teacher = User.objects.create_user(
                "st_teacher", "t@qku.edu.az", "pw", first_name="Pərvin", last_name="Müəllimova"
            )
            teacher_role = _role(
                cls.org, "teacher", level=60, scope_type=RoleScopeType.UNIT, permissions=["course.view", "grade.input"]
            )
            Membership.objects.create(
                user=cls.teacher, organization=cls.org, role=teacher_role, scope_unit=cls.faculty, is_active=True
            )

    @classmethod
    def _student(cls, username, first, last, number, group, *, status=AcademicStatus.ENROLLED):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=first, last_name=last)
        UserProfile.objects.filter(user=user).update(organization=cls.org, institutional_identifier=number)
        Membership.objects.create(user=user, organization=cls.org, role=cls.student_role, is_active=True)
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2026,
            status=status,
        )
        return user

    def record(self, user):
        return StudentAcademicRecord.objects.get(organization=self.org, student=user)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def post_lead(self, actor, **data):
        return self.client_for(actor).post(reverse("accounts:group_lead_action"), data)

    def assign(self, actor, user, group=None):
        return self.post_lead(
            actor, action="assign", group_id=str((group or self.group).pk), record_id=str(self.record(user).pk)
        )

    def active_leads(self, group=None):
        return list(
            Membership.objects.filter(
                organization=self.org, role__name="lead_student", is_active=True, scope_unit=group or self.group
            ).values_list("user__username", flat=True)
        )

    def sections_of(self, user):
        response = self.client_for(user).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return set(response.context["allowed_sections"])

    def fragment(self, user):
        return self.client_for(user).get(reverse("accounts:profile_section_fragment", kwargs={"section": "my-group"}))


class GroupLeadAssignmentTest(StarostaTestBase):
    def test_coordinator_assigns_group_scoped_lead_and_section_opens(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.assign(self.coordinator, self.ali)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.active_leads(), ["st_ali"])
        # Tələbə üzvlüyü toxunulmaz qalır (starosta ƏLAVƏ sətirdir).
        self.assertTrue(Membership.objects.filter(user=self.ali, role=self.student_role, is_active=True).exists())
        self.assertIn("my-group", self.sections_of(self.ali))
        Notification = django_apps.get_model("notifications", "InAppNotification")
        self.assertTrue(Notification.objects.filter(recipient=self.ali).exists())
        AuditLog = django_apps.get_model("audit", "AuditLog")
        self.assertTrue(AuditLog.objects.filter(organization=self.org, new_values__event="assigned").exists())

    def test_replacing_keeps_exactly_one_active_lead_and_notifies_both(self):
        self.assign(self.coordinator, self.ali)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.assign(self.coordinator, self.bina)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.active_leads(), ["st_bina"])
        self.assertNotIn("my-group", self.sections_of(self.ali))
        self.assertIn("my-group", self.sections_of(self.bina))
        Notification = django_apps.get_model("notifications", "InAppNotification")
        self.assertTrue(Notification.objects.filter(recipient=self.ali, title__icontains="başa").exists())

    def test_same_lead_again_is_rejected(self):
        self.assign(self.coordinator, self.ali)
        response = self.assign(self.coordinator, self.ali)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "already_lead")

    def test_only_enrolled_student_of_that_group(self):
        for user in (self.neighbour_student, self.leave):
            with self.subTest(user=user.username):
                response = self.assign(self.coordinator, user)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["error"], "not_group_student")
        self.assertEqual(self.active_leads(), [])
        bogus = self.post_lead(self.coordinator, action="assign", group_id=str(self.group.pk), record_id="x")
        self.assertEqual(bogus.status_code, 409)

    def test_group_outside_actor_scope_is_404_and_students_forbidden(self):
        response = self.assign(self.coordinator, self.far_student, group=self.far_group)
        self.assertEqual(response.status_code, 404)
        for actor in (self.ali, self.teacher):
            with self.subTest(actor=actor.username):
                self.assertEqual(self.assign(actor, self.bina).status_code, 403)
        self.assertEqual(self.active_leads(self.far_group), [])

    def test_role_assign_holder_can_assign_org_wide(self):
        response = self.assign(self.rim, self.far_student, group=self.far_group)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.active_leads(self.far_group), ["st_far"])

    def test_remove_keeps_student_membership(self):
        self.assign(self.coordinator, self.ali)
        response = self.post_lead(self.coordinator, action="remove", group_id=str(self.group.pk), reason="test")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.active_leads(), [])
        self.assertTrue(Membership.objects.filter(user=self.ali, role=self.student_role, is_active=True).exists())
        self.assertNotIn("my-group", self.sections_of(self.ali))
        again = self.post_lead(self.coordinator, action="remove", group_id=str(self.group.pk))
        self.assertEqual(again.status_code, 409)

    def test_assign_repairs_stale_unscoped_lead_row(self):
        with bypass_rls():
            Membership.objects.create(user=self.cavid, organization=self.org, role=self.lead_role, is_active=True)
        self.assertNotIn("my-group", self.sections_of(self.cavid))
        self.assign(self.coordinator, self.cavid)
        self.assertFalse(
            Membership.objects.filter(
                user=self.cavid, role=self.lead_role, scope_unit__isnull=True, is_active=True
            ).exists()
        )
        self.assertIn("my-group", self.sections_of(self.cavid))

    def test_transferred_lead_loses_old_group_section(self):
        self.assign(self.coordinator, self.ali)
        with bypass_rls():
            # Rəsmi köçürmə xidmətinin nəticəsini simulyasiya: qeyd başqa qrupda (trigger testdə yoxdur).
            StudentAcademicRecord.objects.filter(student=self.ali).update(status=AcademicStatus.EXPELLED)
        self.assertNotIn("my-group", self.sections_of(self.ali))
        self.assertEqual(self.fragment(self.ali).status_code, 403)

    def test_generic_grant_role_cannot_create_lead(self):
        from django.contrib.messages import get_messages

        superadmin = User.objects.create_superuser("st_super", "s@qku.edu.az", "pw")
        response = self.client_for(superadmin).post(
            reverse("accounts:manage_roles"),
            {
                "action": "grant_role",
                "user_id": str(self.bina.pk),
                "role_id": str(self.lead_role.pk),
                "scope_unit": str(self.faculty.pk),
            },
        )
        self.assertFalse(Membership.objects.filter(user=self.bina, role=self.lead_role).exists())
        texts = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("Starosta", texts)

    def test_registry_row_shows_starosta(self):
        self.assign(self.coordinator, self.ali)
        response = self.client_for(self.coordinator).get(reverse("accounts:profile"), {"section": "groups-registry"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-lead-username="st_ali"')
        self.assertContains(response, "tofGroupLeadDialog")

    def test_repair_command_dry_run_then_apply(self):
        with bypass_rls():
            Membership.objects.create(user=self.cavid, organization=self.org, role=self.lead_role, is_active=True)
        out = StringIO()
        call_command("repair_group_leads", "--org", self.org.slug, stdout=out)
        self.assertIn("no_scope", out.getvalue())
        self.assertEqual(self.active_leads(), [])
        call_command("repair_group_leads", "--org", self.org.slug, "--apply", stdout=StringIO())
        self.assertEqual(self.active_leads(), ["st_cavid"])


class StarostaSectionContentTest(StarostaTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            Membership.objects.create(
                user=cls.ali, organization=cls.org, role=cls.lead_role, scope_unit=cls.group, is_active=True
            )
            math_ = Subject.objects.create(organization=cls.org, code="RIY", name="Riyaziyyat")
            elective = Subject.objects.create(organization=cls.org, code="SEC1", name="Rəqəmsal incəsənət")
            history = Subject.objects.create(organization=cls.org, code="TAR", name="Azərbaycan tarixi")
            retake = Subject.objects.create(organization=cls.org, code="TKR", name="Təkrar fənn")
            secret = Subject.objects.create(organization=cls.org, code="GIZ", name="Gizli fənn")

            own_math = CourseOffering.objects.create(
                organization=cls.org,
                subject=math_,
                period=cls.period,
                group=cls.group,
                lesson_hours=30,
                instructor=cls.teacher,
            )
            # Seçmə: qonşu qrupun jurnalında, bizim qrupdan yalnız Binə.
            nb_elective = CourseOffering.objects.create(
                organization=cls.org, subject=elective, period=cls.period, group=cls.neighbour, lesson_hours=30
            )
            # Tarix: qonşu qrupun tələbəsi bizim jurnala «alt qrupdan əlavə».
            own_history = CourseOffering.objects.create(
                organization=cls.org, subject=history, period=cls.period, group=cls.group, lesson_hours=30
            )
            nb_retake = CourseOffering.objects.create(
                organization=cls.org, subject=retake, period=cls.period, group=cls.neighbour, lesson_hours=30
            )
            far_secret = CourseOffering.objects.create(
                organization=cls.org, subject=secret, period=cls.period, group=cls.far_group, lesson_hours=30
            )
            nb_math = CourseOffering.objects.create(
                organization=cls.org,
                subject=math_,
                period=cls.period,
                group=cls.neighbour,
                lesson_hours=30,
                instructor=cls.teacher,
            )
            for user in (cls.ali, cls.bina, cls.cavid):
                Enrollment.objects.create(organization=cls.org, student=user, offering=own_math, absence_hours=9)
                Enrollment.objects.create(organization=cls.org, student=user, offering=own_history)
            Enrollment.objects.create(
                organization=cls.org, student=cls.bina, offering=nb_elective, kind=EnrollmentKind.ELECTIVE
            )
            Enrollment.objects.create(
                organization=cls.org, student=cls.neighbour_student, offering=own_history, source_group=cls.neighbour
            )
            Enrollment.objects.create(
                organization=cls.org, student=cls.cavid, offering=nb_retake, kind=EnrollmentKind.RETAKE
            )
            Enrollment.objects.create(organization=cls.org, student=cls.far_student, offering=far_secret)
            # Axın: eyni müəllim + fənn + vaxt, hər ikisi mühazirə.
            for offering in (own_math, nb_math):
                ScheduleSlot.objects.create(
                    organization=cls.org,
                    offering=offering,
                    weekday=2,
                    start_time=datetime.time(9, 0),
                    end_time=datetime.time(10, 20),
                    kind=SlotKind.LECTURE,
                    room="301",
                )
            Exam = django_apps.get_model("exams", "Exam")
            start = timezone.now() + datetime.timedelta(days=7)
            exam = Exam.objects.create(
                organization=cls.org,
                author=cls.teacher,
                title="Riyaziyyat aralıq",
                exam_type="written",
                start_datetime=start,
                end_datetime=start + datetime.timedelta(hours=1),
                is_active=True,
            )
            exam.allowed_units.add(cls.group)
            Exam.objects.create(
                organization=cls.org,
                author=cls.teacher,
                title="Uzaq qrupun imtahanı",
                exam_type="written",
                start_datetime=start,
                end_datetime=start + datetime.timedelta(hours=1),
                is_active=True,
            ).allowed_units.add(cls.far_group)
            Announcement = django_apps.get_model("announcements", "Announcement")
            published = timezone.now() - datetime.timedelta(hours=1)
            Announcement.objects.create(
                organization=cls.org,
                title="Fakültə tələbələrinə elan",
                status="published",
                audience_families=["students"],
                audience_units=[str(cls.faculty.pk)],
                publish_at=published,
            )
            Announcement.objects.create(
                organization=cls.org,
                title="Başqa fakültənin elanı",
                status="published",
                audience_families=["students"],
                audience_units=[str(cls.other_faculty.pk)],
                publish_at=published,
            )

    def html(self):
        response = self.fragment(self.ali)
        self.assertEqual(response.status_code, 200)
        return response.json()["html"]

    def test_section_label_is_starosta(self):
        response = self.client_for(self.ali).get(reverse("accounts:profile"))
        self.assertContains(response, 'data-section="my-group"')
        self.assertContains(response, 'data-title="Starosta"')
        self.assertNotContains(response, ">Qrupum<")

    def test_electives_and_takers_by_name(self):
        html = self.html()
        self.assertIn("Rəqəmsal incəsənət", html)
        self.assertIn("seçmə", html)
        self.assertIn("Binə Bayramova", html)

    def test_joint_lessons_and_subgroups(self):
        html = self.html()
        # Tarix — qonşu qrupdan qonaq; seçmə — qonşu qrupun jurnalı; axın — qonşu qrupun mühazirəsi.
        self.assertIn("ST-102", html)
        self.assertIn("Azərbaycan tarixi", html)
        self.assertIn("ST-101-1", html)
        self.assertIn("Fərid Fərzəliyev", html)

    def test_timetable_exams_announcements(self):
        html = self.html()
        self.assertIn("09:00", html)
        self.assertIn("Riyaziyyat aralıq", html)
        self.assertNotIn("Uzaq qrupun imtahanı", html)
        self.assertIn("Fakültə tələbələrinə elan", html)
        self.assertNotIn("Başqa fakültənin elanı", html)

    def test_privacy_no_classmate_attendance_retake_or_foreign_subjects(self):
        html = self.html()
        self.assertNotIn("Təkrar fənn", html)
        self.assertNotIn("Gizli fənn", html)
        self.assertNotIn("@qku.edu.az", html)
        self.assertNotIn("Dilarə Dadaşova", html)
        # Öz qayıbı: 9 / 60 saat → 15%; yoldaşların sətri davamiyyət daşımır.
        self.assertIn("15%", html)
        from apps.registrar.group_academic import group_students, group_subjects

        data = group_subjects(self.group, period=self.period, students=group_students(self.group))
        for subject in data["subjects"]:
            self.assertNotIn("absence_hours", subject)

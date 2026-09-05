"""View-level tests for the teacher electronic journal (U3): access + lesson + marks."""

import datetime

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import AttendanceStatus, Enrollment, Lesson, LessonKind, LessonMark, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jv_owner", "jv_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JV Univ",
                slug="jv-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="jv-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            cls.teacher = User.objects.create_user("jv_teacher", "jv_teacher@qku.edu.az", "pw")
            cls.other_teacher = User.objects.create_user("jv_other", "jv_other@qku.edu.az", "pw")
            cls.student = User.objects.create_user("jv_student", "jv_student@qku.edu.az", "pw")
            for user in (cls.teacher, cls.other_teacher):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 60
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            cls.enrollment = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.offering)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_journal_list_shows_own_offering(self):
        resp = self._client(self.teacher).get(reverse("registrar:journal_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CS101")

    def test_other_teacher_list_excludes_offering(self):
        # Adi müəllim yalnız öz jurnalını görür — başqasının CS101-i görünməməlidir.
        resp = self._client(self.other_teacher).get(reverse("registrar:journal_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "CS101")

    def test_corrector_sees_all_offerings_broad(self):
        # Korrektor (superuser → can_correct_journal) BÜTÜN org jurnallarını görür,
        # dərs deməsə də; müəllim/fakültə/kafedra/qrup filtrləri görünür.
        with bypass_rls():
            admin = User.objects.create_user("jv_admin", "jv_admin@qku.edu.az", "pw", is_superuser=True)
        resp = self._client(admin).get(reverse("registrar:journal_list"), {"year": "2024/2025"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CS101")  # başqasının dərsi, amma korrektor görür
        self.assertContains(resp, 'name="teacher"')  # müəllim filtri
        self.assertContains(resp, 'name="faculty"')  # fakültə filtri
        # Mövcud olmayan müəllim üzrə süzgəc → CS101 çıxmır.
        resp2 = self._client(admin).get(
            reverse("registrar:journal_list"), {"year": "2024/2025", "teacher": str(self.student.id)}
        )
        self.assertNotContains(resp2, "CS101")

    def test_journal_detail_renders(self):
        resp = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "jv_student")

    def test_correction_toggle_visible_for_corrector_only(self):
        with bypass_rls():
            admin = User.objects.create_user("jv_corr", "jv_corr@qku.edu.az", "pw", is_superuser=True)
        # Korrektor jurnalı açanda "Jurnal düzəlişi" toggle-ı görünür.
        resp = self._client(admin).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertContains(resp, "jd2-correct-toggle")
        # Adi müəllim toggle-ı görmür.
        resp2 = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertNotContains(resp2, "jd2-correct-toggle")

    def test_correction_mode_renders_inline_editor(self):
        with bypass_rls():
            admin = User.objects.create_user("jv_corr2", "jv_corr2@qku.edu.az", "pw", is_superuser=True)
        # ?correct=1 → eyni səhifədə audited düzəliş editoru (ayrı səhifə YOX).
        resp = self._client(admin).get(reverse("registrar:journal_detail", args=[self.offering.id]), {"correct": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-correction-root")  # correction.js kökü (=.jd2)
        self.assertContains(resp, "is-correcting")  # correction rejimi NORMAL grid-in özündə (xanalar düymə olur)
        self.assertContains(resp, "data-corr-form")  # audited düzəliş modalı (səbəb/qeyd/PDF)
        # Adi müəllim ?correct=1 versə də editor açılmır (korrektor deyil).
        resp2 = self._client(self.teacher).get(
            reverse("registrar:journal_detail", args=[self.offering.id]), {"correct": "1"}
        )
        self.assertNotContains(resp2, "data-correction-root")

    def test_non_instructor_cannot_access(self):
        resp = self._client(self.other_teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 404)

    def test_offering_loader_denies_missing_active_organization_context(self):
        from apps.registrar.journal_access import offering_or_404

        request = RequestFactory().get(reverse("registrar:journal_detail", args=[self.offering.id]))
        request.user = self.teacher
        request.organization = None
        request.org_memberships = []
        with self.assertRaises(Http404):
            offering_or_404(request, self.offering.id)

    def test_instructor_membership_revocation_denies_journal_get(self):
        client = self._client(self.teacher)
        with bypass_rls():
            Membership.objects.filter(user=self.teacher, organization=self.org).update(is_active=False)
        response = client.get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(response.status_code, 404)

    def test_instructor_role_deactivation_denies_journal_get(self):
        client = self._client(self.teacher)
        with bypass_rls():
            self.org.roles.filter(name="teacher").update(is_active=False)
        response = client.get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(response.status_code, 404)

    def test_grade_input_revocation_denies_journal_get_and_post(self):
        from django.utils import timezone as _tz

        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=self.offering,
                date=_tz.localdate(),
                kind=LessonKind.SEMINAR,
            )
        client = self._client(self.teacher)
        with bypass_rls():
            self.org.roles.filter(name="teacher").update(permissions=[])
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        self.assertEqual(client.get(url).status_code, 404)
        response = client.post(
            url,
            {
                f"cell__{lesson.id}__{self.enrollment.id}": "1",
                f"score__{lesson.id}__{self.enrollment.id}": "9",
            },
        )
        self.assertEqual(response.status_code, 404)
        with bypass_rls():
            self.assertFalse(LessonMark.objects.filter(lesson=lesson, enrollment=self.enrollment).exists())

    def test_anonymous_redirected_to_login(self):
        resp = Client().get(reverse("registrar:journal_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_add_lesson(self):
        from django.utils import timezone as _tz

        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "add_lesson",
                "lesson_date": _tz.localdate().isoformat(),
                "lesson_kind": "seminar",
                "lesson_hours": "2",
                "lesson_time": "08:30|10:00",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.offering)
            self.assertEqual(lesson.kind, LessonKind.SEMINAR)

    def test_add_lesson_requires_time(self):
        """Dərs saatı seçilmədən yeni dərs yaradılmır (server-side məcburi)."""
        from django.utils import timezone as _tz

        client = self._client(self.teacher)
        client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "add_lesson",
                "lesson_date": _tz.localdate().isoformat(),
                "lesson_kind": "seminar",
                "lesson_hours": "2",
            },  # lesson_time YOX
        )
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())

    def test_add_lesson_topic_over_255_is_rejected_not_500(self):
        """QA 2026-09-05 JOURNAL-TEACHER-01: 255+ simvol mövzu DB DataError (500) verirdi."""
        from django.utils import timezone as _tz

        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "add_lesson",
                "lesson_date": _tz.localdate().isoformat(),
                "lesson_kind": "seminar",
                "lesson_hours": "2",
                "lesson_time": "08:30|10:00",
                "lesson_topic": "M" * 300,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "255 simvol")
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())

    def test_add_lesson_invalid_or_student_instructor_is_rejected_not_500(self):
        """QA 2026-09-05 JOURNAL-TEACHER-02: 'abc' → ValueError, tələbə id → IntegrityError (500)."""
        from django.utils import timezone as _tz

        client = self._client(self.teacher)
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        base = {
            "action": "add_lesson",
            "lesson_date": _tz.localdate().isoformat(),
            "lesson_kind": "seminar",
            "lesson_hours": "2",
            "lesson_time": "08:30|10:00",
        }
        for bad in ("abc", str(self.student.pk)):
            resp = client.post(url, {**base, "lesson_instructor": bad})
            self.assertEqual(resp.status_code, 302, bad)
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())

    def test_save_marks_on_locked_journal_reports_error_not_success(self):
        """QA 2026-09-05 JOURNAL-TEACHER-04: kilidli jurnala POST «yadda saxlanıldı (0 xana)» deyirdi."""
        from apps.registrar.models import ApprovalStatus, AssessmentScheme

        with bypass_rls():
            from apps.registrar import gradebook as _gb

            _gb.ensure_assessment_scheme(offering=self.offering)
            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status=ApprovalStatus.APPROVED
            )
        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {"action": "save_marks", "att__1__1": "absent"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jurnal bağlıdır")
        self.assertNotContains(resp, "yadda saxlanıldı")

    def test_add_lesson_duplicate_time_rejected(self):
        """Eyni gündə eyni dərs saatına ikinci dərs yaradılmır."""
        from django.utils import timezone as _tz

        client = self._client(self.teacher)
        today = _tz.localdate().isoformat()
        payload = {
            "action": "add_lesson",
            "lesson_date": today,
            "lesson_kind": "seminar",
            "lesson_hours": "2",
            "lesson_time": "10:10|11:40",
        }
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        client.post(url, payload)
        client.post(url, payload)  # eyni tarix+saat → rədd
        with bypass_rls():
            self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 1)

    def test_add_lesson_past_date_rejected(self):
        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "add_lesson",
                "lesson_date": "2024-10-01",
                "lesson_kind": "seminar",
                "lesson_hours": "2",
                "lesson_time": "08:30|10:00",  # saat verilir → yalnız keçmiş-tarix rədd olunur
            },
        )
        self.assertEqual(resp.status_code, 302)  # xəta mesajı ilə geri
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())

    def test_save_marks_records_attendance_and_score(self):
        from django.utils import timezone as _tz

        with bypass_rls():
            # YENİ işarə yalnız dərsin öz günündə yazıla bilər → bu günkü dərs.
            lesson = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=_tz.localdate(), kind=LessonKind.SEMINAR
            )
        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                f"cell__{lesson.id}__{self.enrollment.id}": "1",
                f"absent__{lesson.id}__{self.enrollment.id}": "on",
                f"score__{lesson.id}__{self.enrollment.id}": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
            self.assertEqual(mark.status, AttendanceStatus.ABSENT)

    def test_other_teacher_cannot_post(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 1))
        client = self._client(self.other_teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {f"cell__{lesson.id}__{self.enrollment.id}": "1", f"absent__{lesson.id}__{self.enrollment.id}": "on"},
        )
        self.assertEqual(resp.status_code, 404)
        with bypass_rls():
            self.assertFalse(LessonMark.objects.filter(lesson=lesson, enrollment=self.enrollment).exists())


class JournalFinalsViewTest(JournalViewTest):
    """Final-exam + publish actions on the journal page (U3+)."""

    def test_teacher_cannot_write_final_exam_score_via_journal_post(self):
        """QA 2026-09-05 JOURNAL-TEACHER-08: yekun imtahan balı İmtahan Mərkəzinin (`final_score.entry`)
        səthidir; müəllim UI-da olmayan `exam__` sahəsini crafted POST ilə yaza bilirdi."""
        from apps.registrar.models import FinalGrade

        client = self._client(self.teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {"action": "save_finals", f"exam__{self.enrollment.id}": "42"},
        )
        self.assertEqual(resp.status_code, 404)
        with bypass_rls():
            self.assertFalse(FinalGrade.objects.filter(enrollment=self.enrollment, exam_score=42).exists())

    def test_superuser_instructor_can_still_record_exam_score(self):
        from apps.registrar.models import FinalGrade

        with bypass_rls():
            self.teacher.is_superuser = True
            self.teacher.save(update_fields=["is_superuser"])
        try:
            client = self._client(self.teacher)
            resp = client.post(
                reverse("registrar:journal_detail", args=[self.offering.id]),
                {"action": "save_finals", f"exam__{self.enrollment.id}": "42"},
            )
            self.assertEqual(resp.status_code, 302)
            with bypass_rls():
                fg = FinalGrade.objects.get(enrollment=self.enrollment)
                self.assertEqual(str(fg.exam_score), "42.00")
        finally:
            with bypass_rls():
                self.teacher.is_superuser = False
                self.teacher.save(update_fields=["is_superuser"])

    def test_save_components_and_scores(self):
        from apps.registrar.models import AssessmentComponent, ComponentScore

        client = self._client(self.teacher)
        # 1) Define two components.
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "save_components",
                "comp_id__0": "",
                "comp_name__0": "Seminar",
                "comp_max__0": "20",
                "comp_id__1": "",
                "comp_name__1": "Kollokvium",
                "comp_max__1": "30",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            comps = {c.name: c for c in AssessmentComponent.objects.filter(offering=self.offering)}
            self.assertEqual(set(comps), {"Seminar", "Kollokvium"})
        # 2) Enter a component score.
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "save_component_scores",
                f"cscore__{comps['Seminar'].id}__{self.enrollment.id}": "18",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            cs = ComponentScore.objects.get(component=comps["Seminar"], enrollment=self.enrollment)
            self.assertEqual(str(cs.score), "18.00")

    def test_direct_publish_is_denied(self):
        client = self._client(self.teacher)
        resp = client.post(reverse("registrar:journal_detail", args=[self.offering.id]), {"action": "publish"})
        self.assertEqual(resp.status_code, 404)
        with bypass_rls():
            from apps.registrar.models import ApprovalStatus, AssessmentScheme

            scheme = AssessmentScheme.objects.get(offering=self.offering)
            self.assertEqual(scheme.approval_status, ApprovalStatus.DRAFT)
            self.assertFalse(scheme.is_published)

    def test_non_instructor_cannot_save_finals(self):
        client = self._client(self.other_teacher)
        resp = client.post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {"action": "save_finals", f"exam__{self.enrollment.id}": "42"},
        )
        self.assertEqual(resp.status_code, 404)

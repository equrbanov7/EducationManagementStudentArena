"""Sənədli düzəliş qapıları — kilid bağlananda PDF-siz dəyişiklik keçməməlidir.

2026-08 auditi: jurnal tablarında `allow_locked = is_superuser or is_ikt_rehber`
güzəşti vardı. Nəticədə RİM (İKT) rəhbəri — və eyni zamanda həmin fənnin müəllimi
olan istifadəçi — 2 saatlıq redaktə pəncərəsini SƏNƏDSİZ keçib dərsi, sərbəst iş
işarəsini və kurs işi balını dəyişə bilirdi. Bu dəst həmin yolların bağlandığını,
NORMAL iş axınının isə pozulmadığını sənədləşdirir.

Sınaqlar üç sualı ayrı-ayrı yoxlayır:
  1. NORMAL axın — müəllim pəncərə daxilində sənədsiz yazır (POZULMAMALIDIR);
  2. KİLİDDƏN SONRA — sənədsiz cəhd RƏDD olunur, sənədlə (PDF) keçir;
  3. İCAZƏSİZ aktor — jurnala ümumiyyətlə çata bilmir.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, journal_extras, services
from apps.registrar.models import (
    AttendanceStatus,
    CorrectionReason,
    CourseWork,
    Enrollment,
    Lesson,
    LessonCorrection,
    LessonKind,
    LessonMark,
    SelfWorkMark,
    SelfWorkTopic,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

_TWO_HOURS_AGO = datetime.timedelta(hours=3)


def _pdf(name="esas.pdf"):
    """%PDF magic — core.upload_security imza yoxlamasından keçsin."""
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class _JournalGateSetup(TestCase):
    """Bir fənn açılışı; müəllimi eyni zamanda RİM (İKT) rəhbəridir.

    Bu, auditdə tapılan real konfiqurasiyadır: `ikt_rehber` rolunda `grade.*`
    olduğu üçün belə istifadəçi offering-in müəllimi təyin edilə bilir və
    `is_direct_editor` ONA DA true qaytarır."""

    def setUp(self):
        self.owner = User.objects.create_user("dg_owner", "dg_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="DG Univ",
                slug="dg-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="dg-g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            # Müəllim = RİM rəhbəri (auditdə tapılan risk konfiqurasiyası).
            self.ikt_teacher = User.objects.create_user("dg_ikt", "dg_ikt@qku.edu.az", "pw")
            self.plain_teacher = User.objects.create_user("dg_teacher", "dg_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("dg_student", "dg_student@qku.edu.az", "pw")
            self.outsider = User.objects.create_user("dg_out", "dg_out@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.ikt_teacher,
                organization=self.org,
                role=self.org.roles.get(name="ikt_rehber"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=self.plain_teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=self.student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            self.offering = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=self.period, group=self.group
            )
            self.offering.instructor = self.ikt_teacher
            self.offering.lesson_hours = 60
            self.offering.save(update_fields=["instructor", "lesson_hours"])
            self.enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.offering
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _lesson(self, *, kind=LessonKind.SEMINAR, date=None):
        with bypass_rls():
            return gradebook.create_lesson(
                offering=self.offering,
                date=date or timezone.localdate(),
                kind=kind,
                hours=2,
                created_by=self.ikt_teacher,
                allow_past=True,
            )

    @staticmethod
    def _freeze(queryset, field="created_at"):
        """Sətri 2 saatlıq pəncərədən kənara çıxar (auto_now* sahələri update ilə)."""
        queryset.update(**{field: timezone.now() - _TWO_HOURS_AGO})


class LessonActionDocumentGateTest(_JournalGateSetup):
    def _post_update(self, client, lesson, *, with_document, topic="Yenilənmiş mövzu"):
        data = {
            "action": "update_lesson",
            "lesson_date": lesson.date.isoformat(),
            "lesson_kind": lesson.kind,
            "lesson_topic": topic,
            "lesson_hours": "2",
        }
        if with_document:
            data["correction_reason"] = CorrectionReason.TECHNICAL
            data["correction_note"] = "Mövzu səhv yazılıb — protokol əsasında düzəldilir."
            data["correction_document"] = _pdf()
        return client.post(
            reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id]),
            data,
        )

    def test_normal_flow_in_window_needs_no_document(self):
        """NORMAL İŞ AXINI: müəllim pəncərə daxilində sənədsiz dərsi redaktə edir."""
        lesson = self._lesson()
        resp = self._post_update(self._client(self.ikt_teacher), lesson, with_document=False)
        self.assertEqual(resp.status_code, 302)
        lesson.refresh_from_db()
        self.assertEqual(lesson.topic, "Yenilənmiş mövzu")
        self.assertFalse(LessonCorrection.objects.filter(lesson=lesson).exists())

    def test_after_window_without_document_is_rejected(self):
        """Pəncərə bitib: RİM rəhbəri (həm də müəllim) SƏNƏDSİZ dəyişə bilmir."""
        lesson = self._lesson()
        self._freeze(Lesson.objects.filter(pk=lesson.pk))
        resp = self._post_update(self._client(self.ikt_teacher), lesson, with_document=False)
        self.assertEqual(resp.status_code, 302)
        lesson.refresh_from_db()
        self.assertNotEqual(lesson.topic, "Yenilənmiş mövzu")
        self.assertFalse(LessonCorrection.objects.filter(lesson=lesson).exists())

    def test_after_window_with_document_passes_and_is_audited(self):
        """Sənədlə (səbəb + qeyd + PDF) eyni dəyişiklik keçir və audit olunur."""
        lesson = self._lesson()
        self._freeze(Lesson.objects.filter(pk=lesson.pk))
        resp = self._post_update(self._client(self.ikt_teacher), lesson, with_document=True)
        self.assertEqual(resp.status_code, 302)
        lesson.refresh_from_db()
        self.assertEqual(lesson.topic, "Yenilənmiş mövzu")
        correction = LessonCorrection.objects.get(lesson=lesson)
        self.assertTrue(correction.document)
        self.assertEqual(correction.corrected_by_id, self.ikt_teacher.id)
        self.assertTrue(gradebook.grade_audit.get_grade_history(offering=self.offering))

    def test_after_window_deletion_without_document_is_rejected(self):
        lesson = self._lesson()
        self._freeze(Lesson.objects.filter(pk=lesson.pk))
        resp = self._client(self.ikt_teacher).post(
            reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id]),
            {"action": "delete_lesson", "do_delete": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Lesson.objects.filter(pk=lesson.pk).exists())

    def test_after_window_deletion_with_document_passes(self):
        lesson = self._lesson()
        self._freeze(Lesson.objects.filter(pk=lesson.pk))
        resp = self._client(self.ikt_teacher).post(
            reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id]),
            {
                "action": "delete_lesson",
                "do_delete": "1",
                "correction_reason": CorrectionReason.OFFICIAL,
                "correction_note": "Dərs səhvən açılıb — kafedra qərarı ilə silinir.",
                "correction_document": _pdf(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Lesson.objects.filter(pk=lesson.pk).exists())
        self.assertTrue(LessonCorrection.objects.filter(is_deletion=True).exists())

    def test_outsider_gets_404(self):
        lesson = self._lesson()
        resp = self._client(self.outsider).post(
            reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id]),
            {"action": "update_lesson", "lesson_topic": "hack"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_student_gets_404(self):
        lesson = self._lesson()
        resp = self._client(self.student).post(
            reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id]),
            {"action": "update_lesson", "lesson_topic": "hack"},
        )
        self.assertEqual(resp.status_code, 404)


class SelfWorkDocumentGateTest(_JournalGateSetup):
    def _topic(self):
        with bypass_rls():
            return journal_extras.add_selfwork_topic(offering=self.offering, title="Mövzu 1")

    def _post_mark(self, client, topic, value):
        return client.post(
            reverse("registrar:journal_selfwork_action", args=[self.offering.id]),
            {f"sw__{topic.id}__{self.enrollment.id}": value},
        )

    def test_normal_flow_marking_done_needs_no_document(self):
        """NORMAL: müəllim təhvili işarələyir — sənəd tələb olunmur."""
        topic = self._topic()
        resp = self._post_mark(self._client(self.ikt_teacher), topic, "1")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SelfWorkMark.objects.get(topic=topic, enrollment=self.enrollment).done)

    def test_revoking_after_window_without_document_is_rejected(self):
        """1→0 geri alma pəncərədən sonra RİM rəhbəri üçün də sənədsiz keçmir."""
        topic = self._topic()
        self._post_mark(self._client(self.ikt_teacher), topic, "1")
        self._freeze(SelfWorkMark.objects.filter(topic=topic, enrollment=self.enrollment), field="updated_at")
        resp = self._post_mark(self._client(self.ikt_teacher), topic, "0")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(SelfWorkMark.objects.get(topic=topic, enrollment=self.enrollment).done)

    def test_revoking_after_window_with_document_passes(self):
        """Sənədli düzəliş rejimi (correction_apply) eyni dəyişikliyi keçirir."""
        topic = self._topic()
        self._post_mark(self._client(self.ikt_teacher), topic, "1")
        self._freeze(SelfWorkMark.objects.filter(topic=topic, enrollment=self.enrollment), field="updated_at")
        resp = self._client(self.ikt_teacher).post(
            reverse("registrar:correction_apply", args=[self.offering.id]),
            {
                "target": "selfwork",
                "topic_id": str(topic.id),
                "enrollment_id": str(self.enrollment.id),
                "new_done": "0",
                "reason": CorrectionReason.TECHNICAL,
                "note": "Səhv işarələnib — protokol əsasında geri alınır.",
                "document": _pdf(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SelfWorkMark.objects.get(topic=topic, enrollment=self.enrollment).done)

    def test_topic_deletion_is_audited(self):
        """Mövzu silinməsi tələbənin giriş balını aşağı salır → audit izi qalmalıdır."""
        topic = self._topic()
        self._post_mark(self._client(self.ikt_teacher), topic, "1")
        with bypass_rls():
            self.assertTrue(journal_extras.delete_selfwork_topic(topic=topic, by_user=self.ikt_teacher))
        self.assertFalse(SelfWorkTopic.objects.filter(pk=topic.pk).exists())
        history = gradebook.grade_audit.get_grade_history(offering=self.offering)
        deletions = [
            change
            for entry in history
            for change in entry["changes"]
            if change.get("new") == "—" and "Sərbəst iş" in str(change.get("item"))
        ]
        self.assertTrue(deletions, "Sərbəst iş mövzusunun silinməsi audit izinə düşməlidir.")


class CourseWorkDocumentGateTest(_JournalGateSetup):
    def _post(self, client, score):
        return client.post(
            reverse("registrar:journal_coursework_save", args=[self.offering.id]),
            {
                "cw_enrollment": str(self.enrollment.id),
                "cw_topic": "Kurs işi mövzusu",
                "cw_score": str(score),
            },
        )

    def test_normal_flow_first_write_needs_no_document(self):
        resp = self._post(self._client(self.ikt_teacher), 70)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(int(CourseWork.objects.get(enrollment=self.enrollment).score), 70)

    def test_rewrite_after_window_without_document_is_rejected(self):
        self._post(self._client(self.ikt_teacher), 70)
        self._freeze(CourseWork.objects.filter(enrollment=self.enrollment))
        resp = self._post(self._client(self.ikt_teacher), 95)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(int(CourseWork.objects.get(enrollment=self.enrollment).score), 70)

    def test_rewrite_after_window_with_document_passes(self):
        self._post(self._client(self.ikt_teacher), 70)
        self._freeze(CourseWork.objects.filter(enrollment=self.enrollment))
        resp = self._client(self.ikt_teacher).post(
            reverse("registrar:correction_apply", args=[self.offering.id]),
            {
                "target": "coursework",
                "enrollment_id": str(self.enrollment.id),
                "new_score_cw": "95",
                "new_topic": "Kurs işi mövzusu",
                "reason": CorrectionReason.APPEAL,
                "note": "Apellyasiya komissiyasının qərarı.",
                "document": _pdf(),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(int(CourseWork.objects.get(enrollment=self.enrollment).score), 95)


class MarkWriteStillWorksTest(_JournalGateSetup):
    """Reqressiya qoruması: gündəlik bal/davamiyyət yazısı sənədsiz qalır."""

    def test_teacher_writes_marks_without_document(self):
        lesson = self._lesson()
        resp = self._client(self.ikt_teacher).post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                f"att__{lesson.id}__{self.enrollment.id}": AttendanceStatus.PRESENT,
                f"score__{lesson.id}__{self.enrollment.id}": "8",
            },
        )
        self.assertEqual(resp.status_code, 302)
        mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
        self.assertEqual(int(mark.score), 8)


class AdminScoreReadOnlyTest(TestCase):
    """Django admin qiymət sahələrini redaktə edə bilməməlidir.

    Admin forması sənəd, vaxt pəncərəsi, ``journal.correct`` və audit izi
    olmadan bal dəyişdirməyə imkan verirdi — sistemdəki yeganə tam bypass."""

    def _readonly(self, model):
        from django.contrib import admin as django_admin

        return set(django_admin.site._registry[model].get_readonly_fields(None))

    def test_lesson_mark_score_fields_are_readonly(self):
        self.assertTrue({"status", "score"} <= self._readonly(LessonMark))

    def test_final_grade_score_fields_are_readonly(self):
        from apps.registrar.models import FinalGrade

        self.assertTrue({"exam_score", "bonus"} <= self._readonly(FinalGrade))

    def test_resit_score_fields_are_readonly(self):
        from apps.registrar.models import ResitRecord

        self.assertTrue({"resit_score", "status"} <= self._readonly(ResitRecord))


class DelegatedCorrectorTest(_JournalGateSetup):
    """«RİM rəhbərinin təyin etdiyi işçi» — `journal.correct` alan istənilən rol.

    Ayrıca rol yaradılmır: RİM rəhbəri icazə redaktorundan açarı verir, həmin
    rolu daşıyan işçi bu andan sənədli düzəliş edə bilir (sənədsiz — yox)."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.staffer = User.objects.create_user("dg_staff", "dg_staff@qku.edu.az", "pw")
            self.staff_role = self.org.roles.get(name="teacher")
            Membership.objects.create(
                user=self.staffer,
                organization=self.org,
                role=self.staff_role,
                is_primary=True,
                is_active=True,
            )
        self.lesson = self._lesson()
        self.mark = LessonMark.objects.create(
            organization=self.org,
            lesson=self.lesson,
            enrollment=self.enrollment,
            status=AttendanceStatus.ABSENT,
        )

    def _grant_journal_correct(self):
        with bypass_rls():
            self.staff_role.permissions = sorted(set(self.staff_role.permissions or []) | {"journal.correct"})
            self.staff_role.save(update_fields=["permissions", "updated_at"])

    def _apply(self, *, with_document):
        data = {
            "target": "grade",
            "mark_id": str(self.mark.id),
            "field": "attendance",
            "new_status": AttendanceStatus.EXCUSED,
            "reason": CorrectionReason.MEDICAL,
            "note": "Xəstəlik vərəqəsi təqdim olunub.",
        }
        if with_document:
            data["document"] = _pdf()
        return self._client(self.staffer).post(reverse("registrar:correction_apply", args=[self.offering.id]), data)

    def test_without_permission_the_endpoint_is_404(self):
        self.assertEqual(self._apply(with_document=True).status_code, 404)

    def test_delegated_role_without_document_is_rejected(self):
        self._grant_journal_correct()
        resp = self._apply(with_document=False)
        self.assertEqual(resp.status_code, 302)
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.status, AttendanceStatus.ABSENT)

    def test_delegated_role_with_document_passes(self):
        from apps.registrar.models import JournalCorrection

        self._grant_journal_correct()
        resp = self._apply(with_document=True)
        self.assertEqual(resp.status_code, 302)
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.status, AttendanceStatus.EXCUSED)
        correction = JournalCorrection.objects.get(lesson_mark=self.mark)
        self.assertTrue(correction.document)
        self.assertEqual(correction.corrected_by_id, self.staffer.id)


class BackDatedLessonAuditTest(_JournalGateSetup):
    """Keçmiş tarixə dərs açılması (İKT/superuser override) audit izinə düşür."""

    def test_past_dated_lesson_creation_is_audited(self):
        past = timezone.localdate() - datetime.timedelta(days=7)
        resp = self._client(self.ikt_teacher).post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "add_lesson",
                "lesson_date": past.isoformat(),
                "lesson_kind": LessonKind.SEMINAR,
                "lesson_time": "08:30|10:00",
                "lesson_hours": "2",
                "lesson_topic": "Geriyə-dönük dərs",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Lesson.objects.filter(offering=self.offering, date=past).exists())
        history = gradebook.grade_audit.get_grade_history(offering=self.offering)
        overrides = [
            change for entry in history for change in entry["changes"] if "override" in str(change.get("new", ""))
        ]
        self.assertTrue(overrides, "Keçmiş tarixə açılan dərs audit izinə düşməlidir.")

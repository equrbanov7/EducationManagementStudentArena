"""RİM semestr-sonu toplu jurnal bağlaması + təsdiq zəncirinin ləğvi (2026-08).

Sahibin qərarı: jurnal təsdiqə GETMİR (müəllim → kafedra → dekan zənciri yoxdur).
Semestr sonunda RİM dövr üzrə jurnalları — bütün təşkilat / fakültə / kafedra
əhatəsində — toplu bağlayır; səhv bağlama SƏBƏBLƏ geri qaytarıla bilər.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import corrections, finals, gradebook, journal_close, journal_close_notices, services
from apps.registrar.models import (
    ApprovalStatus,
    AttendanceStatus,
    CorrectionField,
    CorrectionReason,
    Curriculum,
    CurriculumSubject,
    JournalCloseNotice,
    JournalCloseScope,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _pdf(name="doc.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class _JournalCloseBase(TestCase):
    """İki fakültə × bir kafedra × bir qrup — əhatə seçimini yoxlamaq üçün."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jc_owner", "jc_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JC Univ",
                slug="jc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty_a = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə A", slug="jc-fa", unit_type=OrgUnitType.FACULTY
            )
            cls.chair_a = OrgUnit.objects.create(
                organization=cls.org,
                name="Kafedra A",
                slug="jc-ka",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.faculty_a,
            )
            cls.group_a = OrgUnit.objects.create(
                organization=cls.org, name="GA", slug="jc-ga", unit_type=OrgUnitType.GROUP, parent=cls.chair_a
            )
            cls.faculty_b = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə B", slug="jc-fb", unit_type=OrgUnitType.FACULTY
            )
            cls.chair_b = OrgUnit.objects.create(
                organization=cls.org,
                name="Kafedra B",
                slug="jc-kb",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.faculty_b,
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org, name="GB", slug="jc-gb", unit_type=OrgUnitType.GROUP, parent=cls.chair_b
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
            cls.rim = User.objects.create_user("jc_rim", "jc_rim@qku.edu.az", "pw")
            cls.teacher = User.objects.create_user("jc_teacher", "jc_teacher@qku.edu.az", "pw")
            cls.dean = User.objects.create_user("jc_dean", "jc_dean@qku.edu.az", "pw")
            for user, role, unit in (
                (cls.rim, "ikt_rehber", None),
                (cls.teacher, "teacher", None),
                (cls.dean, "dean", cls.faculty_a),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=unit,
                    is_primary=True,
                    is_active=True,
                )
            cls.offering_a = cls._make_offering("CS101", cls.group_a, "jc_student_a", 2024)
            cls.offering_b = cls._make_offering("CS201", cls.group_b, "jc_student_b", 2023)

    @classmethod
    def _make_offering(cls, code, group, student_username, admission_year):
        program = Program.objects.create(organization=cls.org, code=code, name=f"Proqram {code}")
        curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=admission_year)
        subject = Subject.objects.create(organization=cls.org, code=code, name=f"Fənn {code}")
        CurriculumSubject.objects.create(
            organization=cls.org, curriculum=curriculum, subject=subject, semester_number=1
        )
        student = User.objects.create_user(student_username, f"{student_username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=student,
            organization=cls.org,
            role=cls.org.roles.get(name="student"),
            is_primary=True,
            is_active=True,
        )
        record = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=program,
            curriculum=curriculum,
            group=group,
            admission_year=admission_year,
        )
        services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
        offering = student.enrollments.get().offering
        offering.instructor = cls.teacher
        offering.save(update_fields=["instructor"])
        return offering

    def _status(self, offering):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=offering)
        return scheme.approval_status, scheme.is_published


class ApprovalChainRemovedTest(_JournalCloseBase):
    """Təsdiq axını ARTIQ MÖVCUD DEYİL — nə servis, nə URL, nə POST action."""

    def test_approval_service_module_is_gone(self):
        with self.assertRaises(ImportError):
            __import__("apps.registrar.approval", fromlist=["submit_for_approval"])

    def test_scope_module_has_no_chain_functions(self):
        from apps.registrar import journal_scope

        for name in ("submit_for_approval", "chair_approve", "dean_approve", "return_for_revision"):
            self.assertFalse(hasattr(journal_scope, name), name)

    def test_approvals_inbox_url_is_gone(self):
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse("registrar:approvals_inbox")

    def test_submit_action_no_longer_changes_state(self):
        client = self._login(self.teacher)
        client.post(reverse("registrar:journal_detail", args=[self.offering_a.id]), {"action": "submit_approval"})
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.DRAFT, False))

    def test_dean_opens_journal_read_only_for_roster_management(self):
        """Dekan jurnalı YALNIZ siyahı idarəsi üçün açır — redaktə hüququ VERİLMİR.

        Təsdiq zənciri (rəyçi oxu yolu) ləğv olunmuş qalır. 2026-08-də dekana
        `journal.roster` verildi (alt qrupdan tələbə əlavə/geri götürmə), ona görə
        səhifə AÇILIR; amma `can_edit` yalanır və POST yolu bağlıdır.
        """
        client = self._login(self.dean)
        resp = client.get(reverse("registrar:journal_detail", args=[self.offering_a.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["can_manage_roster"])
        self.assertFalse(resp.context["can_edit"])
        self.assertFalse(resp.context["can_correct_journal"])
        # Redaktə POST-u (bal yazma) dekan üçün bağlıdır.
        self.assertEqual(
            client.post(reverse("registrar:journal_detail", args=[self.offering_a.id]), {}).status_code, 404
        )

    def test_dean_cannot_open_journal_outside_own_faculty(self):
        """Əhatə (scope) fail-closed: başqa fakültənin jurnalı hələ də 404-dür."""
        resp = self._login(self.dean).get(reverse("registrar:journal_detail", args=[self.offering_b.id]))
        self.assertEqual(resp.status_code, 404)

    def test_teacher_journal_starts_open(self):
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.DRAFT, False))
        with bypass_rls():
            self.assertFalse(gradebook.journal_is_locked(self.offering_a))

    def _login(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class BulkCloseScopeTest(_JournalCloseBase):
    def test_close_faculty_scope_touches_only_that_subtree(self):
        with bypass_rls():
            result = journal_close.close_journals(
                organization=self.org, period=self.period, unit=self.faculty_a, by_user=self.rim
            )
        self.assertEqual(result["closed"], 1)
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.APPROVED, True))
        self.assertEqual(self._status(self.offering_b), (ApprovalStatus.DRAFT, False))

    def test_close_department_scope_touches_only_that_chair(self):
        with bypass_rls():
            journal_close.close_journals(organization=self.org, period=self.period, unit=self.chair_b, by_user=self.rim)
        self.assertEqual(self._status(self.offering_b), (ApprovalStatus.APPROVED, True))
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.DRAFT, False))

    def test_close_whole_organization(self):
        with bypass_rls():
            result = journal_close.close_journals(organization=self.org, period=self.period, by_user=self.rim)
        self.assertEqual(result["closed"], 2)
        self.assertEqual(result["scope_label"], "Bütün təşkilat")
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.APPROVED, True))
        self.assertEqual(self._status(self.offering_b), (ApprovalStatus.APPROVED, True))

    def test_close_is_idempotent(self):
        with bypass_rls():
            first = journal_close.close_journals(organization=self.org, period=self.period, by_user=self.rim)
            second = journal_close.close_journals(organization=self.org, period=self.period, by_user=self.rim)
        self.assertEqual(first["closed"], 2)
        self.assertEqual(second["closed"], 0)
        self.assertEqual(second["already"], 2)
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.APPROVED, True))

    def test_close_creates_missing_schemes(self):
        with bypass_rls():
            from apps.registrar.models import AssessmentScheme

            AssessmentScheme.objects.all().delete()
            result = journal_close.close_journals(organization=self.org, period=self.period, by_user=self.rim)
            self.assertEqual(AssessmentScheme.objects.filter(is_published=True).count(), 2)
        self.assertEqual(result["created"], 2)

    def test_preview_counts_open_and_closed(self):
        with bypass_rls():
            before = journal_close.preview(organization=self.org, period=self.period, unit=self.faculty_a)
            journal_close.close_journals(
                organization=self.org, period=self.period, unit=self.faculty_a, by_user=self.rim
            )
            after = journal_close.preview(organization=self.org, period=self.period, unit=self.faculty_a)
        self.assertEqual((before["total"], before["open"], before["closed"]), (1, 1, 0))
        self.assertEqual((after["total"], after["open"], after["closed"]), (1, 0, 1))

    def test_close_respects_check_constraint_pair(self):
        """Bağlama HƏMİŞƏ approved+published cütünü yazır (DB invariantı)."""
        with bypass_rls():
            journal_close.close_journals(organization=self.org, period=self.period, by_user=self.rim)
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering_a)
            with self.assertRaises(IntegrityError), transaction.atomic():
                type(scheme).objects.filter(pk=scheme.pk).update(is_published=False)


class ReopenTest(_JournalCloseBase):
    def test_reopen_requires_reason(self):
        with bypass_rls():
            journal_close.close_journals(organization=self.org, period=self.period, by_user=self.rim)
            with self.assertRaises(ValidationError):
                journal_close.reopen_journals(organization=self.org, period=self.period, by_user=self.rim, reason="   ")
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.APPROVED, True))

    def test_reopen_restores_draft(self):
        with bypass_rls():
            journal_close.close_journals(organization=self.org, period=self.period, by_user=self.rim)
            result = journal_close.reopen_journals(
                organization=self.org,
                period=self.period,
                unit=self.faculty_a,
                by_user=self.rim,
                reason="Səhv fakültə seçilmişdi",
            )
        self.assertEqual(result["reopened"], 1)
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.DRAFT, False))
        self.assertEqual(self._status(self.offering_b), (ApprovalStatus.APPROVED, True))

    def test_reopen_is_idempotent(self):
        # Sxem sətirlərini yarat (müəllim jurnalı açmış kimi), sonra AÇIQ ikən aç.
        self._status(self.offering_a)
        self._status(self.offering_b)
        with bypass_rls():
            second = journal_close.reopen_journals(
                organization=self.org, period=self.period, by_user=self.rim, reason="onsuz da açıq"
            )
        self.assertEqual(second["reopened"], 0)
        self.assertEqual(second["already"], 2)
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.DRAFT, False))


class ClosePermissionTest(_JournalCloseBase):
    def test_teacher_cannot_close(self):
        with bypass_rls(), self.assertRaises(PermissionDenied):
            journal_close.close_journals(organization=self.org, period=self.period, by_user=self.teacher)
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.DRAFT, False))

    def test_dean_without_permission_cannot_close(self):
        """`dean` rolunda `journal.close` YOXDUR (yalnız RİM-ə verilir)."""
        with bypass_rls(), self.assertRaises(PermissionDenied):
            journal_close.close_journals(
                organization=self.org, period=self.period, unit=self.faculty_a, by_user=self.dean
            )

    def test_unit_scoped_actor_cannot_close_other_unit(self):
        """`journal.close` verilmiş UNIT rolu yalnız öz alt-ağacını bağlaya bilər."""
        with bypass_rls():
            role = self.org.roles.get(name="dean")
            role.permissions = list(role.permissions or []) + ["journal.close"]
            role.save(update_fields=["permissions"])
            # Öz fakültəsi — icazəlidir.
            journal_close.close_journals(
                organization=self.org, period=self.period, unit=self.faculty_a, by_user=self.dean
            )
            # Başqa fakültə — rədd.
            with self.assertRaises(PermissionDenied):
                journal_close.close_journals(
                    organization=self.org, period=self.period, unit=self.faculty_b, by_user=self.dean
                )
            # Bütün təşkilat — rədd (org-wide deyil).
            with self.assertRaises(PermissionDenied):
                journal_close.close_journals(organization=self.org, period=self.period, by_user=self.dean)
        self.assertEqual(self._status(self.offering_b), (ApprovalStatus.DRAFT, False))

    def test_view_forbids_actor_without_permission(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = client.post(reverse("accounts:journal_close"), {"action": "close"})
        self.assertEqual(resp.status_code, 403)


class ClosedJournalWriteTest(_JournalCloseBase):
    """Bağlı jurnal: adi yazı RƏDD, sənədli düzəliş QƏBUL."""

    def _seminar_mark(self):
        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering_a,
                date=datetime.date(2024, 10, 1),
                kind=LessonKind.SEMINAR,
                hours=2,
            )
            enrollment = self.offering_a.enrollments.get()
            mark = LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=enrollment,
                status=AttendanceStatus.PRESENT,
                score=Decimal("3"),
            )
        return lesson, mark

    def test_normal_write_is_rejected_when_closed(self):
        lesson, _mark = self._seminar_mark()
        enrollment = self.offering_a.enrollments.get()
        with bypass_rls():
            journal_close.close_journals(
                organization=self.org, period=self.period, unit=self.faculty_a, by_user=self.rim
            )
            written = gradebook.save_marks(
                offering=self.offering_a,
                entries=[
                    {
                        "lesson_id": str(lesson.id),
                        "enrollment_id": str(enrollment.id),
                        "status": AttendanceStatus.PRESENT,
                        "score": "9",
                    }
                ],
                by_user=self.teacher,
                enforce_day=False,
            )
        self.assertEqual(written, 0)

    def test_documented_correction_still_applies_when_closed(self):
        _lesson, mark = self._seminar_mark()
        with bypass_rls():
            journal_close.close_journals(
                organization=self.org, period=self.period, unit=self.faculty_a, by_user=self.rim
            )
            corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=9,
                reason=CorrectionReason.APPEAL,
                note="Apellyasiya qərarı",
                document=_pdf(),
                by_user=self.rim,
            )
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal("9"))
        # Jurnal HƏLƏ də bağlıdır — düzəliş kilidi açmır.
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.APPROVED, True))

    def test_teacher_cannot_publish_directly(self):
        with bypass_rls(), self.assertRaises(PermissionDenied):
            finals.publish_offering(offering=self.offering_a, by_user=self.teacher)
        self.assertEqual(self._status(self.offering_a), (ApprovalStatus.DRAFT, False))


class CloseAuditTest(_JournalCloseBase):
    def _audit_rows(self):
        from apps.audit.models import AuditLog

        return list(AuditLog.objects.filter(resource_type=journal_close.AUDIT_RESOURCE_TYPE).order_by("created_at"))

    def test_close_and_reopen_write_audit_rows(self):
        with bypass_rls():
            journal_close.close_journals(
                organization=self.org,
                period=self.period,
                unit=self.faculty_a,
                by_user=self.rim,
                reason="Semestr sonu",
            )
            journal_close.reopen_journals(
                organization=self.org,
                period=self.period,
                unit=self.faculty_a,
                by_user=self.rim,
                reason="Səhv bağlama",
            )
            rows = self._audit_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].user_id, self.rim.id)
        self.assertIn("Fakültə A", rows[0].resource_repr)
        self.assertEqual(rows[0].changes["changed"], 1)
        self.assertEqual(rows[0].changes["scope"], "Fakültə A")
        self.assertEqual(rows[1].reason, "Səhv bağlama")
        self.assertEqual(rows[1].changes["action"], "jurnal açıldı")


DEFAULT_NOTICE_DATE = datetime.date(2025, 1, 20)


class CloseNoticeTest(_JournalCloseBase):
    """Xəbərdarlıq zolağı: doğru müəllimlərə görünür, tarix keçəndə itir."""

    def _notice(self, *, scope, unit=None, closes_on=DEFAULT_NOTICE_DATE):
        with bypass_rls():
            return JournalCloseNotice.objects.create(
                organization=self.org,
                period=self.period,
                scope=scope,
                org_unit=unit,
                closes_on=closes_on,
            )

    def test_org_notice_reaches_every_offering(self):
        self._notice(scope=JournalCloseScope.ORGANIZATION)
        today = datetime.date(2025, 1, 10)
        with bypass_rls():
            for offering in (self.offering_a, self.offering_b):
                self.assertIsNotNone(journal_close_notices.journal_banner(offering, today))

    def test_faculty_notice_only_reaches_that_subtree(self):
        self._notice(scope=JournalCloseScope.FACULTY, unit=self.faculty_a)
        today = datetime.date(2025, 1, 10)
        with bypass_rls():
            self.assertIsNotNone(journal_close_notices.journal_banner(self.offering_a, today))
            self.assertIsNone(journal_close_notices.journal_banner(self.offering_b, today))

    def test_department_notice_only_reaches_that_chair(self):
        self._notice(scope=JournalCloseScope.DEPARTMENT, unit=self.chair_b)
        today = datetime.date(2025, 1, 10)
        with bypass_rls():
            self.assertIsNone(journal_close_notices.journal_banner(self.offering_a, today))
            self.assertIsNotNone(journal_close_notices.journal_banner(self.offering_b, today))

    def test_inactive_notice_is_not_shown(self):
        notice = self._notice(scope=JournalCloseScope.ORGANIZATION)
        with bypass_rls():
            notice.is_active = False
            notice.save(update_fields=["is_active"])
            self.assertIsNone(journal_close_notices.journal_banner(self.offering_a, datetime.date(2025, 1, 10)))

    def test_notice_disappears_after_the_deadline(self):
        self._notice(scope=JournalCloseScope.ORGANIZATION, closes_on=datetime.date(2025, 1, 20))
        with bypass_rls():
            # Son gün — hələ görünür (tarix DAXİLDİR).
            self.assertIsNotNone(journal_close_notices.journal_banner(self.offering_a, datetime.date(2025, 1, 20)))
            # Ertəsi gün — itir.
            self.assertIsNone(journal_close_notices.journal_banner(self.offering_a, datetime.date(2025, 1, 21)))
            state = journal_close_notices.notice_state(self.offering_a, datetime.date(2025, 1, 21))
        self.assertEqual(state["status"], "passed")

    def test_nearest_deadline_wins_when_several_apply(self):
        self._notice(scope=JournalCloseScope.ORGANIZATION, closes_on=datetime.date(2025, 1, 25))
        self._notice(scope=JournalCloseScope.FACULTY, unit=self.faculty_a, closes_on=datetime.date(2025, 1, 15))
        with bypass_rls():
            banner = journal_close_notices.journal_banner(self.offering_a, datetime.date(2025, 1, 10))
        self.assertEqual(banner["closes_on"], datetime.date(2025, 1, 15))

    def test_marquee_uses_the_kollokvium_component(self):
        """Şablon eyni `jd2-kmarquee` komponentini təkrar istifadə edir."""
        self._notice(scope=JournalCloseScope.ORGANIZATION, closes_on=datetime.date(2999, 1, 1))
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = client.get(reverse("registrar:journal_detail", args=[self.offering_a.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-journal-close-marquee")
        self.assertContains(resp, "jd2-kmarquee__item")

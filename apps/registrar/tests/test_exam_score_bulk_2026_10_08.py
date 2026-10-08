"""Tutum testi 2026-10-08 — imtahan balının TOPLU yazısı (``exam_score_bulk``).

«jf exam-score save» (25 tələbə) ~1 190 sorğu edirdi (sətir başına ~47). Burada:

* **Ekvivalentlik** — eyni ilkin vəziyyətli iki açılışda köhnə sətir-sətir yol
  (``_save_sequential`` → ``record_exam_score``) və toplu yol (``save_rows``) EYNİ
  nəticəni, eyni ``FinalGrade`` / ``ExamScoreEntry`` / ``ResitRecord`` / audit izini verir —
  cari dövr, bitmiş dövr (dəyişiklik bağlı + ilk daxiletmə sənədlə) və düzəliş rejimi;
  ilk daxiletmə, eyni bal, eyni cəm + fərqli sual bölgüsü, sənədsiz/sənədli dəyişiklik,
  apellyasiya növü, boş / xətalı / tavandan böyük bal, aktiv olmayan qeydiyyat, təkrar
  imtahan hüququnun yaranması və silinməsi;
* **Sorğu büdcəsi** — ``save_roster_scores`` sorğu sayı sətir sayından ASILI DEYİL (4 → 20);
* **Dublikat qeydiyyat** — eyni tələbə iki dəfə gələrsə köhnə ardıcıl semantika qalır;
* **Paralel saxlama** — eyni siyahı əks sıra ilə iki işçidə: deadlock yoxdur (kilid sırası sabit);
* **Rol-əvvəl müəllim siyahısı** — ``integrity.eligible_instructor_user_ids`` əvvəlki
  (bütün üzvlükləri oxuyan) qayda ilə eyni dəsti qaytarır, sorğu sayı üzv sayından asılı deyil.
"""

from __future__ import annotations

import tempfile
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

import pytest

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import exam_score_bulk
from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_sheets as sheets
from apps.registrar import integrity, services
from apps.registrar.exam_score_period_lock import CURRENT_PERIOD, PeriodWritePolicy
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    CorrectionReason,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    ExamScoreEntry,
    FinalGrade,
    Program,
    ResitRecord,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.tests.test_grade_write_concurrency import _run_parallel
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.permissions import has_permission
from core.rls import bypass_rls

User = get_user_model()

_MEDIA = tempfile.mkdtemp(prefix="ese-bulk-media-")

#: Tələbə başına giriş balı (GENERIC komponent, max 50) — keçən / kəsilən qarışığı.
ENTRY_SCORES = [40, 40, 40, 40, 40, 5, 40, 40, 40, 40, 40, 45, 40]


def _pdf(name="teqdimat.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


def _seed(target, students):
    """Fiksturu ``target``-ə (sinif və ya test obyekti) yaz — TestCase və TransactionTestCase üçün ortaq."""
    target.owner = User.objects.create_user("esb_owner", "esb_owner@qku.edu.az", "pw")
    with bypass_rls():
        target.org = Organization.objects.create(
            name="ESB Univ",
            slug="esb-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=target.owner,
            status="active",
            is_active=True,
        )
        target.group = OrgUnit.objects.create(
            organization=target.org, name="ESB-1", slug="esb-g1", unit_type=OrgUnitType.GROUP
        )
        target.period = AcademicPeriod.objects.create(
            organization=target.org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2024/2025",
            start_date="2024-09-01",
            end_date="2025-01-31",
            is_current=True,
        )
        program = Program.objects.create(organization=target.org, code="ESB", name="P", absence_limit_percent=25)
        curriculum = Curriculum.objects.create(organization=target.org, program=program, admission_year=2024)
        for code in ("ESBA", "ESBB"):
            subject = Subject.objects.create(organization=target.org, code=code, name=f"Fənn {code}")
            CurriculumSubject.objects.create(
                organization=target.org, curriculum=curriculum, subject=subject, semester_number=1
            )
        target.center = User.objects.create_user("esb_center", "esb_center@qku.edu.az", "pw")
        Membership.objects.create(
            user=target.center,
            organization=target.org,
            role=target.org.roles.get(name="exam_center_head"),
            is_primary=True,
            is_active=True,
        )
        student_role = target.org.roles.get(name="student")
        for index in range(students):
            student = User.objects.create_user(
                f"esb_s{index:02d}",
                f"esb_s{index:02d}@qku.edu.az",
                "pw",
                first_name="Ad",
                last_name=f"S{index:02d}",
            )
            Membership.objects.create(
                user=student, organization=target.org, role=student_role, is_primary=True, is_active=True
            )
            record = StudentAcademicRecord.objects.create(
                organization=target.org,
                student=student,
                program=program,
                curriculum=curriculum,
                group=target.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=record, period=target.period, semester_number=1)
        target.offerings = list(
            CourseOffering.objects.filter(organization=target.org, period=target.period).order_by("subject__code")
        )
        for offering in target.offerings:
            component = AssessmentComponent.objects.create(
                organization=target.org, offering=offering, name="Seminar", kind=ComponentKind.GENERIC, max_score=50
            )
            enrollments = list(offering.enrollments.order_by("student__username"))
            ComponentScore.objects.bulk_create(
                [
                    ComponentScore(
                        organization=target.org,
                        component=component,
                        enrollment=enrollment,
                        score=ENTRY_SCORES[index % len(ENTRY_SCORES)],
                    )
                    for index, enrollment in enumerate(enrollments)
                ]
            )


class _BulkFixture(TestCase):
    """Bir qrup, İKİ fənn (A, B) — eyni tələbələr hər iki açılışda (ekiz ilkin vəziyyət)."""

    STUDENTS = len(ENTRY_SCORES)

    @classmethod
    def setUpTestData(cls):
        _seed(cls, cls.STUDENTS)

    def _enrollments(self, offering):
        return list(offering.enrollments.select_related("student").order_by("student__username"))


@override_settings(MEDIA_ROOT=_MEDIA)
class BulkEquivalenceTest(_BulkFixture):
    """Köhnə sətir-sətir yol ↔ toplu yol: eyni girişdən eyni vəziyyət."""

    maxDiff = None

    def _seed_prior(self, offering):
        """Hər iki açılışda EYNİ əvvəlki daxiletmələr (sual şəbəkəli vərəq + bir neçə bal)."""
        enrollments = self._enrollments(offering)
        prior_sheet = sheets.create_sheet(offering=offering, by_user=self.center, question_count=5, question_max=10)
        for index, score in ((1, "20"), (2, "20"), (3, "20"), (5, "20"), (9, "10"), (10, "15")):
            service.record_exam_score(enrollment=enrollments[index], score=score, by_user=self.center)
        service.record_exam_score(
            enrollment=enrollments[7],
            score="",
            question_scores=["5", "5", "5", "5", "5"],
            by_user=self.center,
            sheet=prior_sheet,
        )
        Enrollment.objects.filter(pk=enrollments[8].pk).update(status=Enrollment.Status.DROPPED)
        return enrollments

    def _rows(self, enrollments):
        def justified(**extra):
            return {"reason": CorrectionReason.values[0], "note": "protokol", **extra}

        return [
            {"enrollment_id": str(enrollments[0].id), "score": "45"},
            {"enrollment_id": str(enrollments[1].id), "score": "30"},  # sənədsiz dəyişiklik
            {"enrollment_id": str(enrollments[2].id), "score": "48", **justified(evidence=_pdf("s2.pdf"))},
            {"enrollment_id": str(enrollments[3].id), "score": "20"},  # eyni bal
            {"enrollment_id": str(enrollments[4].id), "score": ""},  # boş
            {"enrollment_id": str(enrollments[5].id), "score": "10", **justified()},  # təkrar imtahan səbəbi
            {"enrollment_id": str(enrollments[6].id), "score": "", "question_scores": ["10", "8", "", "7"]},
            {
                "enrollment_id": str(enrollments[7].id),
                "score": "",
                "question_scores": ["10", "5", "5", "5", "0"],  # eyni cəm (25), fərqli bölgü
                **justified(evidence=_pdf("s7.pdf")),
            },
            {"enrollment_id": str(enrollments[8].id), "score": "30"},  # aktiv deyil
            {"enrollment_id": str(enrollments[9].id), "score": "45", **justified()},  # partiya skanı ilə
            {"enrollment_id": str(enrollments[10].id), "score": "16", "kind": "appeal", **justified()},
            {"enrollment_id": str(enrollments[11].id), "score": "60"},  # tavandan böyük
            {"enrollment_id": str(enrollments[12].id), "score": "abc"},  # xətalı
            {"enrollment_id": str(uuid.uuid4()), "score": "30"},  # naməlum qeydiyyat
        ]

    def _snapshot(self, offering, result, enrollments):
        names = {str(e.id): e.student.username for e in enrollments}
        enrollment_ids = [e.id for e in enrollments]
        entries = ExamScoreEntry.objects.filter(enrollment_id__in=enrollment_ids)
        grades = {
            names[str(g.enrollment_id)]: (str(g.exam_score), g.entered_by_id, str(g.bonus))
            for g in FinalGrade.objects.filter(enrollment_id__in=enrollment_ids)
        }
        entry_rows = sorted(
            (
                names[str(e.enrollment_id)],
                e.kind,
                str(e.old_score),
                str(e.new_score),
                e.question_scores,
                e.reason,
                e.note,
                bool(e.evidence),
                e.entered_by_name,
                e.sheet_id is not None,
            )
            for e in entries
        )
        resits = sorted(
            (names[str(r.enrollment_id)], r.reason, r.status, str(r.resit_score), r.decided_by_id)
            for r in ResitRecord.objects.filter(enrollment_id__in=enrollment_ids)
        )
        entry_logs = sorted(
            (log.action, log.user_id, log.reason, str(log.changes))
            for log in AuditLog.objects.filter(
                resource_type="registrar.exam_score_entry", resource_id__in=[str(e.pk) for e in entries]
            )
        )
        grade_logs = sorted(
            (log.action, log.user_id, log.reason, str(log.changes), str(log.new_values), log.resource_repr[4:])
            for log in AuditLog.objects.filter(resource_type="registrar.grade.final", resource_id=str(offering.pk))
        )
        normalized = dict(result)
        # Sıra hər açılışda öz ``enrollment_id``-lərinə görədir — müqayisə sırasızdır.
        normalized["errors"] = sorted(
            (names.get(label, "?id" if len(label) == 36 else label), msg) for label, msg in result["errors"]
        )
        normalized["failed_by_enrollment"] = sorted(
            (names.get(key, "?id"), msg) for key, msg in result["failed_by_enrollment"].items()
        )
        normalized["written_ids"] = sorted(names[key] for key in result["written_ids"])
        return {
            "result": normalized,
            "grades": grades,
            "entries": entry_rows,
            "resits": resits,
            "entry_logs": entry_logs,
            "grade_logs": grade_logs,
        }

    def _run_both(self, policy):
        with bypass_rls():
            seq_offering, bulk_offering = self.offerings
            seq_enrollments = self._seed_prior(seq_offering)
            bulk_enrollments = self._seed_prior(bulk_offering)
            seq_sheet = sheets.create_sheet(
                offering=seq_offering, by_user=self.center, question_count=5, question_max=10, evidence=_pdf()
            )
            bulk_sheet = sheets.create_sheet(
                offering=bulk_offering, by_user=self.center, question_count=5, question_max=10, evidence=_pdf()
            )
            seq_rows = sorted(self._rows(seq_enrollments), key=lambda r: r["enrollment_id"])
            seq_result = exam_score_bulk._save_sequential(
                offering=seq_offering,
                ordered=seq_rows,
                by_user=self.center,
                request=None,
                sheet=seq_sheet,
                policy=policy,
            )
            bulk_result = exam_score_bulk.save_rows(
                offering=bulk_offering,
                rows=self._rows(bulk_enrollments),
                by_user=self.center,
                request=None,
                sheet=bulk_sheet,
                policy=policy,
            )
            sequential = self._snapshot(seq_offering, seq_result, seq_enrollments)
            bulk = self._snapshot(bulk_offering, bulk_result, bulk_enrollments)
        return sequential, bulk

    def _assert_same(self, policy):
        sequential, bulk = self._run_both(policy)
        for key in sequential:
            self.assertEqual(bulk[key], sequential[key], f"toplu yol fərqlidir: {key}")
        return bulk

    def test_current_period_matches_sequential_path(self):
        bulk = self._assert_same(CURRENT_PERIOD)
        # Ssenari həqiqətən hər budağı işlədir (boş müqayisə «keçməsin»).
        # s0, s2, s5, s6, s7, s9, s10 yazılır; s1 (sənədsiz), s8 / naməlum (aktiv deyil),
        # s11 (tavan), s12 (rəqəm deyil) rədd; s3 (eyni bal), s4 (boş) toxunulmur.
        self.assertEqual((bulk["result"]["written"], bulk["result"]["failed"], bulk["result"]["skipped"]), (7, 5, 2))
        self.assertIn(("esb_s10", "appeal"), {(row[0], row[1]) for row in bulk["entries"]})
        self.assertTrue(bulk["resits"], "kəsilən tələbə üçün təkrar imtahan hüququ qalmalıdır")
        self.assertNotIn("esb_s09", {row[0] for row in bulk["resits"]}, "keçən tələbənin hüququ silinməlidir")

    def test_locked_period_without_correction_mode_matches(self):
        self._assert_same(PeriodWritePolicy(locked=True, correction_mode=False, first_entry_needs_document=True))

    def test_locked_period_correction_mode_matches(self):
        self._assert_same(PeriodWritePolicy(locked=True, correction_mode=True, first_entry_needs_document=False))

    def test_duplicate_rows_keep_sequential_semantics(self):
        with bypass_rls():
            enrollment = self._enrollments(self.offerings[0])[0]
            rows = [
                {"enrollment_id": str(enrollment.id), "score": "30"},
                {"enrollment_id": str(enrollment.id), "score": "35"},  # ikinci = sənədsiz dəyişiklik
            ]
            result = service.save_roster_scores(offering=self.offerings[0], rows=rows, by_user=self.center)
            self.assertEqual((result["written"], result["failed"]), (1, 1))
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, Decimal("30"))


class BulkSaveQueryBudgetTest(_BulkFixture):
    """``save_roster_scores`` sorğu sayı sətir sayından asılı deyil (ilk daxiletmə + düzəliş).

    Eyni açılışda iki ayrı tələbə dəsti (4 və 14 sətir) ölçülür; hər dəstdə bir kəsilən
    tələbə var (giriş 5) — ikisində də BİR təkrar imtahan INSERT-i olur, qalan fərq sırf
    sətir sayıdır. Əvvəlcə isitmə (sxem, dövr, fənn, ContentType, AuditLog sxem keşi).
    """

    STUDENTS = 22

    def _count(self, rows, **kwargs):
        with CaptureQueriesContext(connection) as ctx:
            result = service.save_roster_scores(offering=self.offering, rows=rows, by_user=self.center, **kwargs)
        return len(ctx.captured_queries), result

    def test_first_entry_and_correction_budgets_do_not_scale(self):
        with bypass_rls():
            self.offering = self.offerings[0]
            enrollments = self._enrollments(self.offering)
            small, big = enrollments[3:7], enrollments[7:21]  # giriş 5: indeks 5 və 18
            self._count([{"enrollment_id": str(enrollments[21].id), "score": "30"}])  # isitmə

            def first(rows):
                return [{"enrollment_id": str(e.id), "score": str(20 + i)} for i, e in enumerate(rows)]

            small_first, result = self._count(first(small))
            self.assertEqual(result["written"], 4)
            big_first, result = self._count(first(big))
            self.assertEqual(result["written"], 14)
            self.assertEqual(big_first, small_first, f"ilk daxiletmə: 4 sətir → {small_first}, 14 → {big_first}")

            sheet = sheets.create_sheet(offering=self.offering, by_user=self.center, evidence=_pdf())

            def corrections(rows):
                return [
                    {
                        "enrollment_id": str(e.id),
                        "score": str(40 + i % 5),
                        "reason": CorrectionReason.values[0],
                        "note": "n",
                    }
                    for i, e in enumerate(rows)
                ]

            small_fix, result = self._count(corrections(small), sheet=sheet)
            self.assertEqual(result["written"], 4)
            big_fix, result = self._count(corrections(big), sheet=sheet)
            self.assertEqual(result["written"], 14)
            self.assertEqual(big_fix, small_fix, f"düzəliş: 4 sətir → {small_fix}, 14 → {big_fix}")
            # Kəskin deqradasiya tavanı (dəqiq büdcə deyil): əvvəl 25 sətir ≈ 1 190 sorğu idi.
            self.assertLessEqual(big_fix, 30)


class EligibleInstructorIdsTest(TestCase):
    """Rol-əvvəl sorğu əvvəlki «bütün üzvlükləri oxu + Python-da süz» qaydası ilə eynidir."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("eii_owner", "eii_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="EII Univ",
                slug="eii-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.other = Organization.objects.create(
                name="EII Other",
                slug="eii-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            teacher_role = cls.org.roles.get(name="teacher")
            inactive_role = Role.objects.create(
                organization=cls.org, name="eii_inactive_teacher", permissions=["grade.*"], is_active=False
            )
            wildcard_role = Role.objects.create(organization=cls.org, name="eii_wildcard", permissions=["*"])
            cases = {
                "teacher": (teacher_role, True, True),
                "wildcard": (wildcard_role, True, True),
                "student": (cls.org.roles.get(name="student"), True, True),
                "inactive_membership": (teacher_role, False, True),
                "inactive_role": (inactive_role, True, True),
                "inactive_user": (teacher_role, True, False),
            }
            cls.users = {}
            for key, (role, membership_active, user_active) in cases.items():
                user = User.objects.create_user(f"eii_{key}", f"eii_{key}@qku.edu.az", "pw", is_active=user_active)
                Membership.objects.create(
                    user=user, organization=cls.org, role=role, is_primary=True, is_active=membership_active
                )
                cls.users[key] = user
            # Başqa təşkilatın müəllimi — bu təşkilatın siyahısına düşmür.
            foreign = User.objects.create_user("eii_foreign", "eii_foreign@qku.edu.az", "pw")
            Membership.objects.create(
                user=foreign, organization=cls.other, role=cls.other.roles.get(name="teacher"), is_primary=True
            )

    def _legacy_ids(self):
        """2026-10-08-dən əvvəlki tətbiq (bütün üzvlüklər + rol icazəsi Python-da)."""
        memberships = Membership.objects.filter(
            organization_id=self.org.pk,
            organization__is_active=True,
            user__is_active=True,
            is_active=True,
            role__is_active=True,
            role__organization_id=self.org.pk,
        ).select_related("role")
        return {
            m.user_id
            for m in memberships
            if has_permission(list(m.role.permissions or []), integrity.INSTRUCTOR_PERMISSION)
        }

    def test_same_set_as_membership_scan(self):
        with bypass_rls():
            ids = integrity.eligible_instructor_user_ids(organization=self.org)
            self.assertEqual(ids, self._legacy_ids())
        self.assertIn(self.users["teacher"].pk, ids)
        self.assertIn(self.users["wildcard"].pk, ids)
        for key in ("student", "inactive_membership", "inactive_role", "inactive_user"):
            self.assertNotIn(self.users[key].pk, ids, key)

    def test_query_count_does_not_grow_with_members(self):
        student_role = self.org.roles.get(name="student")
        with bypass_rls():
            with CaptureQueriesContext(connection) as before:
                integrity.eligible_instructor_user_ids(organization=self.org)
            extra = User.objects.bulk_create(
                [User(username=f"eii_x{k}", email=f"eii_x{k}@qku.edu.az", password="!") for k in range(40)]
            )
            Membership.objects.bulk_create(
                [Membership(user=u, organization=self.org, role=student_role, is_active=True) for u in extra]
            )
            with CaptureQueriesContext(connection) as after:
                ids = integrity.eligible_instructor_user_ids(organization=self.org)
        self.assertEqual(len(after), len(before))
        self.assertLessEqual(len(after), 2)
        self.assertFalse(ids & {u.pk for u in extra})


@pytest.mark.postgres
class BulkSaveConcurrencyTest(TransactionTestCase):
    """2026-10-05 deadlock ssenarisi: iki işçi EYNİ siyahını əks sıra ilə saxlayır.

    Toplu kilid (``ORDER BY id … FOR UPDATE``) sırası sabitdir — biri gözləyir, deadlock yoxdur;
    ikinci işçi birincinin yazısını kilidDƏN SONRA təzə oxuyur (eyni bal → toxunmur).
    """

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        _seed(self, 8)

    def test_parallel_saves_of_the_same_roster_do_not_deadlock(self):
        offering_id = self.offerings[0].pk
        with bypass_rls():
            ids = [
                str(pk)
                for pk in Enrollment.objects.filter(offering_id=offering_id).order_by("id").values_list("id", flat=True)
            ]

        def save(order):
            def run():
                with transaction.atomic():
                    offering = CourseOffering.objects.get(pk=offering_id)
                    rows = [{"enrollment_id": eid, "score": "30"} for eid in order]
                    return service.save_roster_scores(offering=offering, rows=rows, by_user=self.center)

            return run

        results = _run_parallel([save(ids), save(list(reversed(ids)))])
        self.assertEqual(sorted(r["written"] for r in results), [0, len(ids)])
        self.assertEqual(sorted(r["skipped"] for r in results), [0, len(ids)])
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.filter(enrollment__offering_id=offering_id).count(), len(ids))
            self.assertEqual(ExamScoreEntry.objects.filter(enrollment__offering_id=offering_id).count(), len(ids))

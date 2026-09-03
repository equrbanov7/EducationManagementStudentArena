"""Fənnin başqa müəllimə TƏHVİLİ — icazə, əhatə, blokerlər, audit, geri qaytarma.

Sahibin ssenarisi: «tarix fənnini Elvin keçir, Elvin işdən çıxdı, o fənni Əliyə
assign edə bilim, jurnal artıq Əlinin olsun, o görsün.»

Bu dəst dörd qırmızı xətti kilidləyir:

1. **Köhnə data DƏYİŞMİR** — bal, davamiyyət və ``Lesson.instructor`` toxunulmaz.
2. **Tarixi/bağlı semestr TOXUNULMAZ** — bağlı jurnal və bitmiş dövr bloklanır.
3. **Səlahiyyət fail-closed** — müəllimin özündə açar yoxdur, dekan yalnız öz
   fakültəsində, açarsız aktor 403.
4. **Geri qaytarıla bilən** — səhv təyinat auditlə geri qaytarılır.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, handover, handover_actions, services
from apps.registrar.models import (
    ApprovalStatus,
    AttendanceStatus,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
    TeachingHandover,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class HandoverBase(TestCase):
    """İki fakültə × kafedra × qrup — əhatə (scope) qapısını yoxlamaq üçün."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("th_owner", "th_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="TH Univ",
                slug="th-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty_a = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə A", slug="th-fa", unit_type=OrgUnitType.FACULTY
            )
            cls.chair_a = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra A", slug="th-ka", unit_type=OrgUnitType.CHAIR, parent=cls.faculty_a
            )
            cls.group_a = OrgUnit.objects.create(
                organization=cls.org, name="GA", slug="th-ga", unit_type=OrgUnitType.GROUP, parent=cls.chair_a
            )
            cls.faculty_b = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə B", slug="th-fb", unit_type=OrgUnitType.FACULTY
            )
            cls.chair_b = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra B", slug="th-kb", unit_type=OrgUnitType.CHAIR, parent=cls.faculty_b
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org, name="GB", slug="th-gb", unit_type=OrgUnitType.GROUP, parent=cls.chair_b
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
            cls.past_period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2023/2024 Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2023/2024",
                start_date="2024-02-01",
                end_date="2024-06-30",
                is_current=False,
            )
            cls.rim = User.objects.create_user("th_rim", "th_rim@qku.edu.az", "pw")
            cls.dean = User.objects.create_user("th_dean", "th_dean@qku.edu.az", "pw")
            cls.old_teacher = User.objects.create_user("th_elvin", "th_elvin@qku.edu.az", "pw")
            cls.new_teacher = User.objects.create_user("th_ali", "th_ali@qku.edu.az", "pw")
            cls.other_teacher = User.objects.create_user("th_other", "th_other@qku.edu.az", "pw")
            for user, role, unit in (
                (cls.rim, "ikt_rehber", None),
                (cls.dean, "dean", cls.faculty_a),
                (cls.old_teacher, "teacher", None),
                (cls.new_teacher, "teacher", None),
                (cls.other_teacher, "teacher", None),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=unit,
                    is_primary=True,
                    is_active=True,
                )
            cls.offering_a = cls._make_offering("HIST101", cls.group_a, "th_student_a", 2024, cls.period)
            cls.offering_b = cls._make_offering("BIO201", cls.group_b, "th_student_b", 2023, cls.period)
            cls.offering_past = cls._make_offering("OLD100", cls.group_a, "th_student_c", 2022, cls.past_period)

    @classmethod
    def _make_offering(cls, code, group, student_username, admission_year, period):
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
        services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
        offering = student.enrollments.get(offering__period=period).offering
        offering.instructor = cls.old_teacher
        offering.save(update_fields=["instructor"])
        return offering

    def _login(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _reassign(self, actor=None, offering=None, target=None, reason="Müəllim işdən çıxdı"):
        return handover_actions.reassign(
            actor=actor or self.rim,
            organization=self.org,
            offering_id=(offering or self.offering_a).pk,
            new_instructor_id=(target or self.new_teacher).pk,
            reason=reason,
        )


class PermissionAndScopeTest(HandoverBase):
    def test_rim_and_dean_carry_the_key_but_teacher_does_not(self):
        with bypass_rls():
            self.assertTrue(handover.can_reassign(self.rim, self.org))
            self.assertTrue(handover.can_reassign(self.dean, self.org))
            self.assertFalse(handover.can_reassign(self.old_teacher, self.org))

    def test_teacher_without_key_is_refused(self):
        with bypass_rls(), self.assertRaises(PermissionDenied):
            self._reassign(actor=self.old_teacher)

    def test_dean_scope_is_limited_to_own_faculty(self):
        """Dekan öz fakültəsində təhvil verir, qonşu fakültədə isə bloklanır."""
        with bypass_rls():
            self.assertEqual(
                handover.blockers(self.offering_b, actor=self.dean, organization=self.org),
                ["outside_scope"],
            )
            with self.assertRaises(handover_actions.HandoverError) as ctx:
                self._reassign(actor=self.dean, offering=self.offering_b)
            self.assertEqual(ctx.exception.code, "blocked")
            self._reassign(actor=self.dean, offering=self.offering_a)
        self.offering_a.refresh_from_db()
        self.assertEqual(self.offering_a.instructor_id, self.new_teacher.pk)

    def test_scoped_offerings_is_fail_closed_for_keyless_actor(self):
        with bypass_rls():
            self.assertEqual(handover.scoped_offerings(self.old_teacher, self.org).count(), 0)
            self.assertGreaterEqual(handover.scoped_offerings(self.rim, self.org).count(), 3)

    def test_teacher_cannot_hand_over_their_own_subject(self):
        """Açarı olsa belə müəllim ÖZ jurnalını başqasının üstünə ata bilməz."""
        with bypass_rls():
            self.assertIn(
                "actor_is_current_instructor",
                handover.blockers(self.offering_a, actor=self.old_teacher, organization=self.org),
            )

    def test_target_must_hold_grade_input(self):
        student = User.objects.get(username="th_student_a")
        with bypass_rls(), self.assertRaises(handover_actions.HandoverError) as ctx:
            self._reassign(target=student)
        self.assertEqual(ctx.exception.code, "target_not_eligible")


class HistoricalSemesterTest(HandoverBase):
    """Tarixi/bağlı jurnal TOXUNULMAZ — sahibin qərarı (bax handover.py başlığı)."""

    def test_closed_journal_is_blocked(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering_a)
            scheme.is_published = True
            scheme.approval_status = ApprovalStatus.APPROVED
            scheme.save(update_fields=["is_published", "approval_status"])
            self.assertIn("journal_closed", handover.blockers(self.offering_a, actor=self.rim, organization=self.org))
            with self.assertRaises(handover_actions.HandoverError):
                self._reassign()
        self.offering_a.refresh_from_db()
        self.assertEqual(self.offering_a.instructor_id, self.old_teacher.pk)

    def test_past_period_is_blocked(self):
        with bypass_rls():
            self.assertIn("past_period", handover.blockers(self.offering_past, actor=self.rim, organization=self.org))
            with self.assertRaises(handover_actions.HandoverError):
                self._reassign(offering=self.offering_past)
        self.offering_past.refresh_from_db()
        self.assertEqual(self.offering_past.instructor_id, self.old_teacher.pk)

    def test_current_flag_beats_the_end_date(self):
        """Rəsmi uzadılmış (is_current) semestr bitmiş sayılmır."""
        today = datetime.date(2025, 6, 1)
        self.assertFalse(handover.period_is_past(self.period, today))
        self.assertTrue(handover.period_is_past(self.past_period, today))


class DataPreservationTest(HandoverBase):
    """Köhnə müəllimin yazdığı HEÇ NƏ dəyişmir — sahibin qırmızı xətti."""

    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering_a,
                date=datetime.date(2024, 10, 1),
                kind=LessonKind.SEMINAR,
                hours=2,
                created_by=self.old_teacher,
                instructor=self.old_teacher,
            )
            self.mark = LessonMark.objects.create(
                organization=self.org,
                lesson=self.lesson,
                enrollment=self.offering_a.enrollments.get(),
                status=AttendanceStatus.PRESENT,
                score=8,
                entered_by=self.old_teacher,
            )

    def test_marks_and_lesson_author_survive_the_handover(self):
        with bypass_rls():
            self._reassign()
            self.lesson.refresh_from_db()
            self.mark.refresh_from_db()
        self.assertEqual(self.lesson.instructor_id, self.old_teacher.pk)
        self.assertEqual(self.lesson.created_by_id, self.old_teacher.pk)
        self.assertEqual(self.mark.entered_by_id, self.old_teacher.pk)
        self.assertEqual(int(self.mark.score), 8)
        self.assertEqual(self.mark.status, AttendanceStatus.PRESENT)

    def test_handover_record_snapshots_both_names(self):
        with bypass_rls():
            self._reassign()
            record = TeachingHandover.objects.get(offering=self.offering_a)
        self.assertEqual(record.from_instructor_id, self.old_teacher.pk)
        self.assertEqual(record.to_instructor_id, self.new_teacher.pk)
        self.assertTrue(record.from_instructor_name)
        self.assertTrue(record.to_instructor_name)
        self.assertEqual(record.performed_by_id, self.rim.pk)
        self.assertFalse(record.is_reverted)

    def test_audit_row_is_written(self):
        from apps.audit.models import AuditLog

        with bypass_rls():
            self._reassign()
            rows = list(
                AuditLog.objects.filter(resource_type=handover_actions.AUDIT_RESOURCE_TYPE).values(
                    "changes", "old_values", "new_values"
                )
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["changes"]["action"], "handover.assigned")
        self.assertEqual(rows[0]["new_values"]["instructor"], self.new_teacher.get_username())

    def test_new_teacher_is_notified(self):
        from apps.notifications.models import InAppNotification

        with bypass_rls():
            self._reassign()
            notes = list(InAppNotification.objects.filter(recipient=self.new_teacher))
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].metadata.get("kind"), "teaching_handover")


class JournalOwnershipTest(HandoverBase):
    """Jurnal sahibliyi köçür: yeni müəllim yazır, köhnəsi yalnız oxuyur."""

    def test_new_teacher_can_edit_and_old_one_cannot(self):
        with bypass_rls():
            self._reassign()
        url = reverse("registrar:journal_detail", args=[self.offering_a.id])

        new_resp = self._login(self.new_teacher).get(url)
        self.assertEqual(new_resp.status_code, 200)
        self.assertTrue(new_resp.context["can_edit"])

        old_client = self._login(self.old_teacher)
        old_resp = old_client.get(url)
        self.assertEqual(old_resp.status_code, 200, "köhnə müəllim tarixçəni görməlidir")
        self.assertFalse(old_resp.context["can_edit"])
        self.assertTrue(old_resp.context["handover_observer"])
        # Yazma yolu TAM bağlıdır (POST → 404, mövcudluq sızmır).
        self.assertEqual(old_client.post(url, {}).status_code, 404)

    def test_old_teacher_keeps_the_journal_in_their_list(self):
        from apps.registrar import page_contexts

        with bypass_rls():
            self._reassign()
            request = self._login(self.old_teacher).get(reverse("registrar:journal_list")).wsgi_request
            context = page_contexts.journal_list_context(self.old_teacher, request=request)
        ids = {str(row["offering"].id) for row in context["rows"]} if "rows" in context else set()
        if not ids:  # kontekst açarı fərqlidirsə offering siyahısını birbaşa yoxla
            ids = {str(item.id) for item in context.get("offerings", [])}
        self.assertIn(str(self.offering_a.id), ids)

    def test_unrelated_teacher_still_gets_404(self):
        """Təhvil üçüncü şəxsə görünüş AÇMIR — yalnız KÖHNƏ müəllimə."""
        with bypass_rls():
            self._reassign()
        resp = self._login(self.other_teacher).get(reverse("registrar:journal_detail", args=[self.offering_a.id]))
        self.assertEqual(resp.status_code, 404)


class RevertTest(HandoverBase):
    def test_revert_restores_the_previous_instructor(self):
        with bypass_rls():
            result = self._reassign()
            record_id = result["handover_ids"][0]
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv təyinat")
            record = TeachingHandover.objects.get(pk=record_id)
        self.offering_a.refresh_from_db()
        self.assertEqual(self.offering_a.instructor_id, self.old_teacher.pk)
        self.assertTrue(record.is_reverted)
        self.assertEqual(record.reverted_by_id, self.rim.pk)

    def test_second_revert_is_refused(self):
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv")
            with self.assertRaises(handover_actions.HandoverError) as ctx:
                handover_actions.revert(
                    actor=self.rim, organization=self.org, handover_id=record_id, reason="Yenə səhv"
                )
        self.assertEqual(ctx.exception.code, "already_reverted")

    def test_revert_is_refused_when_the_chain_moved_on(self):
        with bypass_rls():
            first = self._reassign()["handover_ids"][0]
            self._reassign(target=self.other_teacher)
            with self.assertRaises(handover_actions.HandoverError) as ctx:
                handover_actions.revert(actor=self.rim, organization=self.org, handover_id=first, reason="Geri")
        self.assertEqual(ctx.exception.code, "chain_moved")

    def test_reason_is_mandatory(self):
        with bypass_rls(), self.assertRaises(handover_actions.HandoverError) as ctx:
            self._reassign(reason=" ")
        self.assertEqual(ctx.exception.code, "reason_required")

    def test_read_only_access_ends_after_revert(self):
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv")
            self.offering_a.refresh_from_db()
            self.assertFalse(handover.is_handover_observer(self.new_teacher, self.offering_a))


class BulkHandoverTest(HandoverBase):
    """«Elvin işdən çıxdı» — bütün fənləri, hər birini AYRI müəllimə."""

    def test_rows_may_target_different_teachers(self):
        with bypass_rls():
            result = handover_actions.bulk_reassign(
                actor=self.rim,
                organization=self.org,
                items=[
                    {"offering_id": self.offering_a.pk, "new_instructor_id": self.new_teacher.pk},
                    {"offering_id": self.offering_b.pk, "new_instructor_id": self.other_teacher.pk},
                ],
                reason="Kadr dəyişikliyi",
            )
        self.assertEqual(result["count"], 2)
        self.offering_a.refresh_from_db()
        self.offering_b.refresh_from_db()
        self.assertEqual(self.offering_a.instructor_id, self.new_teacher.pk)
        self.assertEqual(self.offering_b.instructor_id, self.other_teacher.pk)

    def test_one_blocked_row_rolls_the_whole_batch_back(self):
        """Atomiklik: yarımçıq nəticə qalmır (bax handover_actions.py başlığı)."""
        with bypass_rls(), self.assertRaises(handover_actions.HandoverError):
            handover_actions.bulk_reassign(
                actor=self.rim,
                organization=self.org,
                items=[
                    {"offering_id": self.offering_a.pk, "new_instructor_id": self.new_teacher.pk},
                    {"offering_id": self.offering_past.pk, "new_instructor_id": self.new_teacher.pk},
                ],
                reason="Kadr dəyişikliyi",
            )
        self.offering_a.refresh_from_db()
        self.assertEqual(self.offering_a.instructor_id, self.old_teacher.pk)
        with bypass_rls():
            self.assertEqual(TeachingHandover.objects.count(), 0)


class HandoverApiTest(HandoverBase):
    """JSON səthi — fail-closed davranış + müqavilə açarları."""

    def test_endpoints_are_closed_for_a_plain_teacher(self):
        client = self._login(self.old_teacher)
        for name in ("handover_offerings", "handover_teachers", "handover_options", "handover_history"):
            payload = client.get(reverse(f"accounts:{name}")).json()
            self.assertFalse(payload["has_access"], name)
        denied = client.post(
            reverse("accounts:handover_action"),
            data={"action": "reassign", "reason": "test"},
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_offering_rows_expose_blockers_and_impact(self):
        payload = self._login(self.rim).get(reverse("accounts:handover_offerings")).json()
        self.assertTrue(payload["has_access"])
        rows = {row["id"]: row for row in payload["results"]}
        current = rows[str(self.offering_a.id)]
        self.assertTrue(current["can_transfer"])
        self.assertEqual(current["instructor"]["id"], str(self.old_teacher.pk))
        self.assertIn("students", current)
        past = rows[str(self.offering_past.id)]
        self.assertFalse(past["can_transfer"])
        self.assertEqual([blocker["code"] for blocker in past["blockers"]], ["past_period"])
        # Bloker MƏTNİ də göndərilir (a11y: rəng tək daşıyıcı deyil).
        self.assertTrue(past["blockers"][0]["label"])

    def test_teacher_picker_uses_the_lazy_paging_contract(self):
        payload = self._login(self.rim).get(reverse("accounts:handover_teachers") + "?role=target&limit=1").json()
        self.assertIn("has_more", payload)
        self.assertEqual(len(payload["results"]), 1)
        self.assertIn("text", payload["results"][0])

    def test_source_picker_lists_only_scoped_instructors(self):
        payload = self._login(self.dean).get(reverse("accounts:handover_teachers") + "?role=source").json()
        self.assertEqual([row["id"] for row in payload["results"]], [str(self.old_teacher.pk)])

    def test_post_reassigns_and_history_exposes_revert(self):
        client = self._login(self.rim)
        response = client.post(
            reverse("accounts:handover_action"),
            data={
                "action": "reassign",
                "reason": "Müəllim işdən çıxdı",
                "items": [{"offering_id": str(self.offering_a.id), "new_instructor_id": str(self.new_teacher.pk)}],
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        history = client.get(reverse("accounts:handover_history")).json()
        self.assertEqual(history["total"], 1)
        self.assertTrue(history["results"][0]["can_revert"])


class HistoryRevertContractTest(HandoverBase):
    """Tarixçə sətrinin ``can_revert``-i SERVERİN həqiqətən qəbul etdiyi ilə eynidir.

    ⚠️ Pozulmuş müqavilə: ``_history_row`` yalnız «geri qaytarılmayıb + zəncir
    yerindədir» şərtinə baxırdı və :data:`~apps.registrar.handover_actions.
    REVERT_BLOCKER_CODES`-a BAXMIRDI.  Dövr təhvil ilə geri qaytarma arasında
    bitəndə sətir ``can_revert=True`` qaytarır, JS düyməni AKTİV çəkir, POST isə
    409 verirdi — istifadəçi üçün həmişə xəta verən düymə.

    Burada hər bloker üçün İKİ tərəf birlikdə yoxlanılır: oxu səthi düyməni
    söndürür VƏ mutasiya eyni kodla 409 qaytarır.
    """

    def _history(self, client=None):
        payload = (client or self._login(self.rim)).get(reverse("accounts:handover_history")).json()
        return payload["results"][0]

    def _codes(self, row):
        return [blocker["code"] for blocker in row["revert_blockers"]]

    def _post_revert(self, client, record_id):
        return client.post(
            reverse("accounts:handover_action"),
            data={"action": "revert", "handover_id": record_id, "reason": "Səhv təyinat"},
            content_type="application/json",
        )

    def test_a_revertible_row_stays_revertible(self):
        """Normal axın pozulmur: bloker yoxdursa düymə var və POST işləyir."""
        client = self._login(self.rim)
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
        row = self._history(client)
        self.assertTrue(row["can_revert"])
        self.assertEqual(row["revert_blockers"], [])
        self.assertEqual(self._post_revert(client, str(record_id)).status_code, 200)

    def test_an_expired_period_disables_the_button_and_names_the_reason(self):
        client = self._login(self.rim)
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            AcademicPeriod.objects.filter(pk=self.period.pk).update(
                is_current=False, end_date=datetime.date.today() - datetime.timedelta(days=1)
            )
        row = self._history(client)
        self.assertFalse(row["can_revert"])
        self.assertEqual(self._codes(row), ["past_period"])
        # Etiket BOŞ ola bilməz — «—» əvəzinə səbəb yazılır (a11y: rəng tək daşıyıcı deyil).
        self.assertTrue(row["revert_blockers"][0]["label"])
        # …və server həqiqətən eyni koda görə imtina edir (müqavilənin ikinci tərəfi).
        response = self._post_revert(client, str(record_id))
        self.assertEqual(response.status_code, 409)
        # ⚠️ Xəta zərfinin açarı ``error``-dur, ``code`` DEYİL (bax
        # ``views/handover/actions.py::_error``) — sətrin bloker kodu isə
        # ``codes`` massivində gəlir.  Müqavilənin bağlandığı yer məhz budur:
        # oxu səthinin söndürmə səbəbi ilə mutasiyanın imtina səbəbi EYNİ koddur.
        body = response.json()
        self.assertEqual(body["error"], "blocked")
        self.assertEqual(body["codes"], self._codes(row))

    def test_a_closed_journal_disables_the_button(self):
        client = self._login(self.rim)
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering_a)
            scheme.is_published = True
            scheme.approval_status = ApprovalStatus.APPROVED
            scheme.save(update_fields=["is_published", "approval_status"])
        row = self._history(client)
        self.assertFalse(row["can_revert"])
        self.assertEqual(self._codes(row), ["journal_closed"])
        self.assertEqual(self._post_revert(client, str(record_id)).status_code, 409)

    def test_an_inactive_offering_disables_the_button(self):
        client = self._login(self.rim)
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            CourseOffering.objects.filter(pk=self.offering_a.pk).update(is_active=False)
        row = self._history(client)
        self.assertFalse(row["can_revert"])
        self.assertEqual(self._codes(row), ["offering_inactive"])
        self.assertEqual(self._post_revert(client, str(record_id)).status_code, 409)

    def test_a_moved_chain_now_says_why_instead_of_a_dash(self):
        """Zəncir irəli gedəndə düymə ƏVVƏL də yox idi — amma səbəb DEYİLMİRDİ."""
        client = self._login(self.rim)
        with bypass_rls():
            stale_id = str(self._reassign()["handover_ids"][0])
            # İkinci təhvil: fənn artıq başqasındadır, ilk sətir «köhnəlir».
            self._reassign(target=self.other_teacher, reason="Yenidən dəyişiklik")
        payload = client.get(reverse("accounts:handover_history")).json()
        stale = next(row for row in payload["results"] if row["id"] == stale_id)
        self.assertFalse(stale["can_revert"])
        self.assertEqual(self._codes(stale), ["chain_moved"])
        self.assertTrue(stale["revert_blockers"][0]["label"])

    def test_a_reverted_row_carries_no_blockers(self):
        """Geri qaytarılmış sətirdə düymə onsuz da yoxdur — səbəb siyahısı boşdur."""
        client = self._login(self.rim)
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv təyinat")
        row = self._history(client)
        self.assertTrue(row["is_reverted"])
        self.assertFalse(row["can_revert"])
        self.assertEqual(row["revert_blockers"], [])

    def test_the_history_page_does_not_pay_per_row(self):
        """Blokerlər sətir-sətir hesablansa da sorğu sayı sətir sayı ilə BÖYÜMÜR.

        ⚠️ İddia BƏRABƏRLİK deyil, «böyümür»dür.  İki GET arasında sessiya/icazə
        keşi qızır, yəni ikinci sorğu birincidən BİR NEÇƏ sorğu AZ ola bilər —
        bərabərlik iddiası həmin qızmanı qüsur kimi göstərirdi (ölçülmüş: 20 → 17).
        Qorunan invariant N+1-in olmamasıdır: 1 sətirdən 3 sətrə keçəndə sorğu
        sayı ARTMAMALIDIR.  (Əvvəl artırdı: ``_revert_blocker_codes``
        ``organization``-u ötürmədiyi üçün ``blockers`` içindəki
        ``offering.organization`` FK-sı hər sətirdə yüklənirdi.)
        İlk ölçmədən əvvəl bir «isti» GET edilir ki, keş hər iki ölçmədə eyni
        vəziyyətdə olsun.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client = self._login(self.rim)
        with bypass_rls():
            self._reassign()
        url = reverse("accounts:handover_history")
        client.get(url)  # keşi qızdır — ölçmə soyuq-start xərcini saymasın
        with CaptureQueriesContext(connection) as one_row:
            client.get(url)
        with bypass_rls():
            self._reassign(offering=self.offering_b, target=self.other_teacher)
            self._reassign(target=self.other_teacher, reason="İkinci dəyişiklik")
        with CaptureQueriesContext(connection) as three_rows:
            response = client.get(url)
        self.assertEqual(len(response.json()["results"]), 3)
        self.assertLessEqual(
            len(three_rows.captured_queries),
            len(one_row.captured_queries),
            f"sətir başına sorğu: 1 sətir={len(one_row.captured_queries)}, "
            f"3 sətir={len(three_rows.captured_queries)}",
        )


class SectionRegistryTest(HandoverBase):
    """Bölmə DÖRD siyahıda da olmalıdır + yalnız açarı olana görünməlidir."""

    def test_section_is_registered_everywhere(self):
        from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS

        self.assertIn("teaching-handover", SECTION_PARTIALS)
        self.assertIn("teaching-handover", AJAX_SAFE_SECTIONS)

    def test_menu_visibility_follows_the_permission_key(self):
        from apps.accounts.views._helpers.rbac_sections import apply_permission_section_gates

        for user, expected in ((self.rim, True), (self.dean, True), (self.old_teacher, False)):
            sections = set()
            with bypass_rls():
                flags = apply_permission_section_gates(user, self.org, sections, is_superadmin=False, is_owner=False)
            self.assertEqual(flags["can_reassign_teaching"], expected, user.username)
            self.assertEqual("teaching-handover" in sections, expected, user.username)

    def test_permission_key_is_catalogued_with_a_label(self):
        from apps.organizations.permissions import PERMISSION_LABELS, get_all_permissions

        self.assertIn("journal.reassign", get_all_permissions())
        self.assertTrue(str(PERMISSION_LABELS["journal.reassign"]))


class SectionRenderTest(HandoverBase):
    """Bölmə HƏQİQƏTƏN render olunur — şablon + kontekst + AJAX fraqmenti."""

    def test_full_page_section_renders_the_spa_frame(self):
        response = self._login(self.rim).get(reverse("accounts:profile") + "?section=teaching-handover")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("data-thx-root", body)
        # Endpoint URL-ləri data-atributla ötürülür (CSP: inline JS yoxdur).
        self.assertIn(reverse("accounts:handover_offerings"), body)
        self.assertIn(reverse("accounts:handover_action"), body)
        # Sidebar keçidi yalnız icazəsi olana görünür.
        self.assertIn("?section=teaching-handover", body)

    def test_ajax_fragment_endpoint_serves_the_section(self):
        response = self._login(self.rim).get(
            reverse("accounts:profile_section_fragment", args=["teaching-handover"]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("data-thx-root", response.content.decode())

    def test_teacher_sees_neither_the_menu_entry_nor_the_fragment(self):
        client = self._login(self.old_teacher)
        page = client.get(reverse("accounts:profile")).content.decode()
        self.assertNotIn("?section=teaching-handover", page)
        fragment = client.get(reverse("accounts:profile_section_fragment", args=["teaching-handover"]))
        self.assertEqual(fragment.status_code, 403)

    def test_no_inline_style_or_script_block_in_the_section_template(self):
        """CSP qapısı: bölmə şablonunda inline `<style>` / `<script>…</script>` YOXDUR."""
        import pathlib
        import re

        from django.conf import settings

        template = pathlib.Path(settings.BASE_DIR) / (
            "apps/accounts/templates/accounts/profile/sections/_teaching_handover.html"
        )
        markup = template.read_text(encoding="utf-8")
        self.assertNotIn("<style", markup)
        self.assertIsNone(re.search(r"<script(?![^>]*\ssrc=)", markup))


class RevertBlockerTest(HandoverBase):
    """Təhvil ilə geri qaytarma ARASINDA dövr bitə bilər — invariant orada da işləsin.

    ``handover.py`` başlığındakı «təhvilin özü heç vaxt bağlı jurnalda baş verə
    bilmir» arqumenti geri qaytarmaya şamil olunmurdu: təhvil cari semestrdə
    edilirdi, sonra semestr bitirdi, ``blockers`` ``past_period`` qaytarırdı,
    lakin ``revert`` yenə də tarixi açılışın müəllimini yenidən yazırdı.
    """

    def _expire_the_period(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.period.pk).update(
                is_current=False,
                end_date=datetime.date.today() - datetime.timedelta(days=1),
            )

    def test_revert_is_refused_after_the_period_ended(self):
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
        self._expire_the_period()
        with bypass_rls():
            self.offering_a.refresh_from_db()
            self.assertIn("past_period", handover.blockers(self.offering_a, actor=self.rim, organization=self.org))
            with self.assertRaises(handover_actions.HandoverError) as ctx:
                handover_actions.revert(
                    actor=self.rim, organization=self.org, handover_id=record_id, reason="Geri qaytar"
                )
        self.assertEqual(ctx.exception.code, "blocked")
        self.assertIn("past_period", ctx.exception.codes)
        # Tarixi açılışın müəllimi TOXUNULMAZ qalır və sətir «geri qaytarılıb» olmur.
        self.offering_a.refresh_from_db()
        self.assertEqual(self.offering_a.instructor_id, self.new_teacher.pk)
        with bypass_rls():
            self.assertFalse(TeachingHandover.objects.get(pk=record_id).is_reverted)

    def test_revert_is_refused_when_the_offering_went_inactive(self):
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            CourseOffering.objects.filter(pk=self.offering_a.pk).update(is_active=False)
            with self.assertRaises(handover_actions.HandoverError) as ctx:
                handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Geri")
        self.assertEqual(ctx.exception.code, "blocked")
        self.assertIn("offering_inactive", ctx.exception.codes)

    def test_revert_is_refused_when_the_journal_was_closed_meanwhile(self):
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering_a)
            scheme.is_published = True
            scheme.approval_status = ApprovalStatus.APPROVED
            scheme.save(update_fields=["is_published", "approval_status"])
            with self.assertRaises(handover_actions.HandoverError) as ctx:
                handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Geri")
        self.assertEqual(ctx.exception.code, "blocked")
        self.assertIn("journal_closed", ctx.exception.codes)

    def test_revert_still_works_while_the_period_is_current(self):
        """Qapı yalnız TARİXİ dövrə bağlanır — normal axın pozulmur."""
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv")
        self.offering_a.refresh_from_db()
        self.assertEqual(self.offering_a.instructor_id, self.old_teacher.pk)


class RevertAuditDirectionTest(HandoverBase):
    """Audit sətri geri qaytarmada TƏRS istiqaməti göstərməlidir (komissiya oxuyur)."""

    def _audit_rows(self):
        from apps.audit.models import AuditLog

        return list(
            AuditLog.objects.filter(resource_type=handover_actions.AUDIT_RESOURCE_TYPE)
            .order_by("created_at")
            .values("changes", "old_values", "new_values", "resource_repr")
        )

    def test_revert_row_records_to_from_not_from_to(self):
        old_name, new_name = self.old_teacher.get_username(), self.new_teacher.get_username()
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv")
            rows = self._audit_rows()

        self.assertEqual([row["changes"]["action"] for row in rows], ["handover.assigned", "handover.reverted"])
        assigned, reverted = rows
        self.assertEqual(assigned["old_values"]["instructor"], old_name)
        self.assertEqual(assigned["new_values"]["instructor"], new_name)
        # Geri qaytarma: faktiki dəyişiklik to → from.
        self.assertEqual(reverted["old_values"]["instructor"], new_name)
        self.assertEqual(reverted["new_values"]["instructor"], old_name)
        # İki sətir eyni diff-lə düzülmür — istiqamət oxunaqlıdır.
        self.assertNotEqual(assigned["old_values"], reverted["old_values"])
        self.assertNotEqual(assigned["resource_repr"], reverted["resource_repr"])
        self.assertTrue(reverted["resource_repr"].endswith(f"{new_name} \u2192 {old_name}"))

    def test_record_snapshot_columns_stay_stable_in_both_rows(self):
        """``changes.from/to_instructor_id`` təhvil SƏTRİNİN sütunlarıdır — çevrilmir."""
        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv")
            rows = self._audit_rows()
        for row in rows:
            self.assertEqual(row["changes"]["from_instructor_id"], str(self.old_teacher.pk))
            self.assertEqual(row["changes"]["to_instructor_id"], str(self.new_teacher.pk))


class BlockedResponseI18nTest(HandoverBase):
    """«blocked» POST cavabı AKTİV dildə qayıtmalıdır (əvvəl həmişə AZ idi)."""

    def _post_blocked_reassign(self, lang):
        from django.utils import translation

        client = self._login(self.rim)
        with translation.override(lang):
            return client.post(
                reverse("accounts:handover_action"),
                data={
                    "action": "reassign",
                    "reason": "Kadr dəyişikliyi",
                    "items": [
                        {"offering_id": str(self.offering_past.id), "new_instructor_id": str(self.new_teacher.pk)}
                    ],
                },
                content_type="application/json",
                HTTP_ACCEPT_LANGUAGE=lang,
            )

    def test_blocked_reassign_message_follows_the_active_language(self):
        messages = {}
        for lang in ("az", "en", "ru", "tr"):
            response = self._post_blocked_reassign(lang)
            self.assertEqual(response.status_code, 409, lang)
            payload = response.json()
            self.assertEqual(payload["error"], "blocked")
            self.assertEqual(payload["codes"], ["past_period"])
            messages[lang] = payload["message"]
        self.assertEqual(len(set(messages.values())), 4, messages)
        self.assertIn("semester", messages["en"].lower())
        self.assertNotEqual(messages["ru"], messages["az"])

    def test_blocked_revert_message_uses_the_revert_wording(self):
        from django.utils import translation

        with bypass_rls():
            record_id = self._reassign()["handover_ids"][0]
            AcademicPeriod.objects.filter(pk=self.period.pk).update(
                is_current=False, end_date=datetime.date.today() - datetime.timedelta(days=1)
            )
        client = self._login(self.rim)
        payloads = {}
        for lang in ("az", "en", "ru", "tr"):
            with translation.override(lang):
                response = client.post(
                    reverse("accounts:handover_action"),
                    data={"action": "revert", "handover_id": record_id, "reason": "Geri qaytar"},
                    content_type="application/json",
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
            self.assertEqual(response.status_code, 409, lang)
            payloads[lang] = response.json()
        self.assertEqual(len(set(row["message"] for row in payloads.values())), 4, payloads)
        # Geri qaytarma istiqaməti öz mətnini alır (təhvil mətni ilə eyni deyil).
        self.assertNotEqual(payloads["az"]["message"], self._post_blocked_reassign("az").json()["message"])

    def test_permission_denied_message_is_translated_not_service_azerbaijani(self):
        from django.utils import translation

        client = self._login(self.old_teacher)
        with translation.override("ru"):
            response = client.post(
                reverse("accounts:handover_action"),
                data={"action": "reassign", "reason": "Səbəb", "offering_id": str(self.offering_a.id)},
                content_type="application/json",
                HTTP_ACCEPT_LANGUAGE="ru",
            )
        self.assertEqual(response.status_code, 403)
        message = response.json()["message"]
        self.assertNotIn("icazəniz", message)
        self.assertTrue(any("\u0410" <= ch <= "\u044f" for ch in message), message)

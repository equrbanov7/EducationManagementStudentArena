"""Tələbə İDARƏETMƏ səthi — kart, köçürmə ön baxışı, köçürmə, akademik status.

Nə kilidlənir:

1. **Fail-closed əhatə.** ``people.manage_academic`` açarı OLMAYAN aktor üçün
   siyahı BOŞ, endpoint 403/404. Dekan öz fakültəsindən kənar tələbəni nə görür,
   nə köçürür; HƏDƏF qrup da onun sahəsində olmalıdır (əks halda tələbəni öz
   fakültəsindən «ata» bilərdi).
2. **Ön baxış rəqəmləri DOĞRUDUR.** Sahibin tələbi: «semestr ortasında köçürmə
   sürpriz olmasın». Test ön baxışın vəd etdiyi rəqəmlərin (qayıb saatı, jurnal
   işarəsi, buraxılış statusu, hədəf qrupda olmayan fənn) köçürmədən SONRAKI
   həqiqətlə üst-üstə düşdüyünü yoxlayır.
3. **Mexanizm TƏKRAR YAZILMIR.** Köçürmə rəsmi iki fazalı sübut axınından keçir:
   köhnə qeydiyyat ``dropped`` + ``superseded_by``, yenisi hədəf qrupda.
4. **Sorğu BÜDCƏSİ.** Kartın sorğu sayı yazılış sayı ilə ARTMIR (N+1 yoxdur).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.services import people
from apps.accounts.services.rim.policy import RimAccessError
from apps.audit.models import AuditLog
from apps.organizations.models import Membership
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    Lesson,
    LessonMark,
    StudentAcademicRecord,
    Subject,
)
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .people_fixture import PeopleFixture, make_role, make_user

User = get_user_model()

MANAGE = "people.manage_academic"
READ = ["people.view_students", "people.view_teachers"]


def _request(user, organization):
    request = RequestFactory().get("/accounts/profile/")
    request.user = user
    request.organization = organization
    return request


class AcademicFixture(PeopleFixture):
    """Kataloq fixture-u + köçürmə üçün lazım olan İKİNCİ qrup və jurnal izləri.

    Baza fixture-unda hər fakültədə bir qrup var; köçürmə üçün eyni fakültədə
    ikinci hədəf qrup, tələbənin qayıb saatı və jurnal işarələri lazımdır.
    """

    def __init__(self):
        super().__init__()
        with bypass_rls():
            self._build_academic()

    def _build_academic(self):
        # Eyni ixtisas altında ikinci qrup — koordinator əhatəsində qalır.
        self.group_a2 = self._unit("Qrup A1-2", "qrup-a1-2", OrgUnitType.GROUP, self.specialty_a1)
        # BAŞQA ixtisas altında qrup — koordinator üçün sahədən KƏNAR hədəf.
        self.specialty_a2 = self._unit("İxtisas A2", "ixt-a2", OrgUnitType.SPECIALTY, self.kafedra_a1)
        self.group_a3 = self._unit("Qrup A2-1", "qrup-a2-1", OrgUnitType.GROUP, self.specialty_a2)

        self.role_coordinator = make_role(
            self.org,
            "program_coordinator",
            level=60,
            scope_type=RoleScopeType.UNIT,
            permissions=[*READ, MANAGE],
        )
        self.role_dean_manage = make_role(
            self.org,
            "dean_manage",
            level=80,
            scope_type=RoleScopeType.UNIT,
            permissions=[*READ, MANAGE, "people.manage_status"],
        )

        self.coordinator = make_user("ppl_coord", first="Kənan", last="Koordinatorov")
        self._member(self.coordinator, self.role_coordinator, self.specialty_a1)

        self.dean_m = make_user("ppl_dean_m", first="Mətanət", last="Dekanova")
        self._member(self.dean_m, self.role_dean_manage, self.faculty_a)

        self.dean_m_b = make_user("ppl_dean_mb", first="Bilal", last="Bəylərov")
        self._member(self.dean_m_b, self.role_dean_manage, self.faculty_b)

        # Tarix fənni: köhnə qrupda AÇILIŞI var, hədəf qrupda YOXDUR → köçürmə
        # onu avtomatik yaradacaq; ön baxış bunu əvvəlcədən xəbər verməlidir.
        self.subject_history = Subject.objects.create(organization=self.org, code="TAR101", name="Tarix")

        self.offering_math_a1 = self.offering_a  # MAT101 · Qrup A1-1 (fixture-dan)
        CourseOffering.objects.filter(pk=self.offering_math_a1.pk).update(lesson_hours=30)
        self.offering_math_a1.refresh_from_db()

        self.offering_hist_a1 = CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject_history,
            period=self.period,
            group=self.group_a1,
            instructor=self.teacher_a,
            lesson_hours=30,
        )
        # Hədəf qrupda YALNIZ riyaziyyat açılışı var.
        self.offering_math_a2 = CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            group=self.group_a2,
            instructor=self.teacher_a,
            lesson_hours=30,
        )

        self.record_a = StudentAcademicRecord.objects.get(student=self.student_a)

        self.enr_math = Enrollment.objects.get(student=self.student_a, offering=self.offering_math_a1)
        Enrollment.objects.filter(pk=self.enr_math.pk).update(absence_hours=10)
        self.enr_math.refresh_from_db()
        self.enr_hist = Enrollment.objects.create(
            organization=self.org,
            student=self.student_a,
            offering=self.offering_hist_a1,
            absence_hours=2,
        )

        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering_math_a1,
            date=self.period.start_date,
            hours=2,
        )
        LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=self.enr_math,
            status="absent",
        )

    def _member(self, user, role, unit):
        Membership.objects.get_or_create(
            organization=self.org,
            user=user,
            role=role,
            scope_unit=unit,
            defaults={"is_active": True},
        )


class AcademicScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = AcademicFixture()

    def _actor(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def test_actor_without_permission_gets_empty_queryset(self):
        """Müəllim səthi ÜMUMİYYƏTLƏ görmür — bayraq da, siyahı da boşdur."""
        actor = self._actor(self.fx.teacher_a)
        self.assertFalse(actor.can_manage_academic)
        with bypass_rls():
            self.assertEqual(people.scoped_records_qs(actor).count(), 0)
            self.assertEqual(people.scoped_groups_qs(actor).count(), 0)

    def test_reader_without_manage_key_cannot_manage(self):
        """Kataloqu GÖRMƏK idarə etmək demək deyil (iki ayrı açar)."""
        actor = self._actor(self.fx.dean_a)  # yalnız people.manage_status
        self.assertFalse(actor.can_manage_academic)
        with bypass_rls():
            self.assertEqual(people.scoped_records_qs(actor).count(), 0)

    def test_dean_sees_only_own_faculty_records(self):
        actor = self._actor(self.fx.dean_m)
        with bypass_rls():
            students = {record.student_id for record in people.scoped_records_qs(actor)}
        self.assertIn(self.fx.student_a.pk, students)
        self.assertNotIn(self.fx.student_b.pk, students)

    def test_coordinator_scope_is_limited_to_own_specialty(self):
        """Koordinator öz ixtisasının qruplarını görür, qonşu ixtisasınkını YOX."""
        actor = self._actor(self.fx.coordinator)
        with bypass_rls():
            names = set(people.scoped_groups_qs(actor).values_list("name", flat=True))
        self.assertEqual(names, {"Qrup A1-1", "Qrup A1-2"})

    def test_unscoped_membership_yields_nothing(self):
        """`scope_unit` təyin edilməyib → fail-closed (heç nə)."""
        with bypass_rls():
            user = make_user("ppl_coord_x", first="Sahəsiz", last="Koordinator")
            Membership.objects.create(
                organization=self.fx.org,
                user=user,
                role=self.fx.role_coordinator,
                scope_unit=None,
                is_active=True,
            )
        actor = self._actor(user)
        with bypass_rls():
            self.assertEqual(people.scoped_records_qs(actor).count(), 0)
            self.assertEqual(people.scoped_groups_qs(actor).count(), 0)


class StudentCardTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = AcademicFixture()

    def _actor(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def test_card_shows_official_program_label_not_internal_code(self):
        with bypass_rls():
            card = people.build_student_card(actor=self._actor(self.fx.dean_m), user_id=self.fx.student_a.pk)
        record = card["records"][0]
        self.assertTrue(card["can_manage"])
        self.assertEqual(record["group_name"], "Qrup A1-1")
        self.assertEqual(record["faculty_name"], "Fakültə A")
        self.assertEqual(record["program_label"], self.fx.program_a.name)
        self.assertNotIn("MYEDU", record["program_label"])

    def _card_record_with_codes(self, official, legacy):
        Program = self.fx.program_a.__class__
        with bypass_rls():
            Program.objects.filter(pk=self.fx.program_a.pk).update(official_code=official, legacy_official_code=legacy)
            card = people.build_student_card(actor=self._actor(self.fx.dean_m), user_id=self.fx.student_a.pk)
        return card["records"][0]

    def test_card_never_prints_the_program_code_twice(self):
        """REQRESSİYA: `program_label` + `program_code` BİRLİKDƏ render olunur.

        `people_academic.js` `program_code`-u `program_label`-in İÇİNƏ nişan kimi
        əlavə edir. Etiket `display_label` («Ad · şifr») olsaydı, cari şifr eyni
        sətirdə İKİ DƏFƏ çıxardı: «Kompüter mühəndisliyi · 6006022 [6006022 ·
        köhnə 050631]». Doğru bölgü — ad ŞİFRSİZ, şifr yalnız nişanda
        (`context_builder/_helpers.py` ilə eyni naxış).
        """
        record = self._card_record_with_codes("6006022", "050631")
        self.assertEqual(record["program_label"], "Proqram A")
        self.assertNotIn("6006022", record["program_label"])
        self.assertIn("6006022", record["program_code"])
        self.assertIn("050631", record["program_code"])
        # JS-in qurduğu birləşmiş sətirdə hər şifr TƏK dəfə görünür.
        rendered = record["program_label"] + " " + record["program_code"]
        self.assertEqual(rendered.count("6006022"), 1, rendered)
        self.assertEqual(rendered.count("050631"), 1, rendered)

    def test_card_legacy_only_program_code_is_not_a_broken_badge(self):
        """Yalnız-köhnə-şifrli ixtisas: nişan ayırıcısız «050401» təkrarı olmasın."""
        record = self._card_record_with_codes("", "050401")
        self.assertEqual(record["program_label"], "Proqram A")
        self.assertEqual(record["program_code"], "050401")
        rendered = record["program_label"] + " " + record["program_code"]
        self.assertEqual(rendered.count("050401"), 1, rendered)

    def test_card_program_code_is_empty_when_the_program_has_no_code(self):
        """Şifrsiz ixtisasda nişan BOŞ qalır — asılı ayırıcı və uydurma yoxdur."""
        record = self._card_record_with_codes("", "")
        self.assertEqual(record["program_label"], "Proqram A")
        self.assertEqual(record["program_code"], "")

    def test_detail_academic_row_splits_the_name_from_the_code(self):
        """`detail.py` da EYNİ bölgüyə tabedir — ilk render şifri təkrarlamasın.

        Bu səthin hələ istehlakçısı yoxdur, amma `academic.py` ilə eyni açar
        cütünü (`program` + `program_code`) verir: birləşmiş `display_label`
        qalsaydı ilk UI onu qoşan kimi şifr iki dəfə çıxardı.
        """
        Program = self.fx.program_a.__class__
        with bypass_rls():
            Program.objects.filter(pk=self.fx.program_a.pk).update(
                official_code="6006022", legacy_official_code="050631"
            )
            detail = people.build_detail(actor=self._actor(self.fx.dean_m), user_id=self.fx.student_a.pk)
        row = detail["person"]["academic"][0]

        self.assertEqual(row["program"], "Proqram A")
        self.assertNotIn("6006022", row["program"])
        self.assertEqual(
            row["program_code"], self.fx.program_a.__class__.objects.get(pk=self.fx.program_a.pk).official_code_pair
        )
        rendered = row["program"] + " " + row["program_code"]
        self.assertEqual(rendered.count("6006022"), 1, rendered)
        self.assertEqual(rendered.count("050631"), 1, rendered)

    def test_card_lists_current_enrollments_with_absence(self):
        with bypass_rls():
            card = people.build_student_card(actor=self._actor(self.fx.dean_m), user_id=self.fx.student_a.pk)
        rows = {row["subject_code"]: row for row in card["records"][0]["enrollments"]}
        self.assertEqual(set(rows), {"MAT101", "TAR101"})
        self.assertEqual(rows["MAT101"]["absence_hours"], 10)
        self.assertFalse(rows["MAT101"]["is_guest"])

    def test_card_marks_guest_enrollment_from_another_group(self):
        """Alt qrupdan əlavə olunmuş sətir kartda AYRICA işarələnir."""
        with bypass_rls():
            Enrollment.objects.create(
                organization=self.fx.org,
                student=self.fx.student_a,
                offering=self.fx.offering_math_a2,
                source_group=self.fx.group_a1,
            )
            card = people.build_student_card(actor=self._actor(self.fx.dean_m), user_id=self.fx.student_a.pk)
        guests = [row for row in card["records"][0]["enrollments"] if row["is_guest"]]
        self.assertEqual(len(guests), 1)
        self.assertEqual(guests[0]["source_group_name"], "Qrup A1-1")

    def test_card_of_out_of_scope_student_is_404(self):
        actor = self._actor(self.fx.dean_m)
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.build_student_card(actor=actor, user_id=self.fx.student_b.pk)
        self.assertEqual(ctx.exception.status, 404)

    def test_card_of_a_teacher_is_404(self):
        actor = self._actor(self.fx.rector)
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.build_student_card(actor=actor, user_id=self.fx.teacher_a.pk)
        self.assertEqual(ctx.exception.status, 404)

    def test_card_query_count_does_not_grow_with_enrollments(self):
        """Yazılış sayı artdıqca sorğu sayı SABİT qalmalıdır (N+1 qadağası)."""
        actor = self._actor(self.fx.dean_m)
        with bypass_rls():
            people.build_student_card(actor=actor, user_id=self.fx.student_a.pk)
            with CaptureQueriesContext(connection) as small:
                small_card = people.build_student_card(actor=actor, user_id=self.fx.student_a.pk)
            for index in range(6):
                subject = Subject.objects.create(organization=self.fx.org, code=f"BULK{index}", name=f"Fənn {index}")
                offering = CourseOffering.objects.create(
                    organization=self.fx.org,
                    subject=subject,
                    period=self.fx.period,
                    group=self.fx.group_a1,
                    instructor=self.fx.teacher_a,
                    lesson_hours=30,
                )
                Enrollment.objects.create(organization=self.fx.org, student=self.fx.student_a, offering=offering)
            with CaptureQueriesContext(connection) as large:
                large_card = people.build_student_card(actor=actor, user_id=self.fx.student_a.pk)

        self.assertGreater(
            len(large_card["records"][0]["enrollments"]),
            len(small_card["records"][0]["enrollments"]),
        )
        self.assertEqual(
            len(large.captured_queries),
            len(small.captured_queries),
            "Tələbə kartında N+1: yazılış sayı artdıqca sorğu sayı da artdı.\n"
            + "\n".join(query["sql"][:160] for query in large.captured_queries),
        )


class TransferPreviewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = AcademicFixture()

    def _actor(self, user=None):
        return people.resolve_actor(_request(user or self.fx.dean_m, self.fx.org))

    def _preview(self, group, user=None):
        with bypass_rls():
            return people.preview_group_transfer(
                actor=self._actor(user),
                record_id=str(self.fx.record_a.pk),
                new_group_id=str(group.pk),
            )

    def test_preview_reports_what_will_be_hidden(self):
        preview = self._preview(self.fx.group_a2)
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["from_group"]["name"], "Qrup A1-1")
        self.assertEqual(preview["to_group"]["name"], "Qrup A1-2")
        totals = preview["totals"]
        self.assertEqual(totals["subjects"], 2)  # MAT101 + TAR101
        self.assertEqual(totals["absence_hours"], 12)  # 10 + 2
        self.assertEqual(totals["marks"], 1)  # bir jurnal işarəsi
        # Tarix fənninin hədəf qrupda açılışı YOXDUR → köçürmə onu yaradacaq.
        self.assertEqual(totals["missing_in_target"], 1)
        self.assertIn("attendance_resets", preview["warnings"])
        self.assertIn("offerings_created", preview["warnings"])

    def test_preview_flags_barred_student_losing_the_bar(self):
        """Qayıb limitini keçmiş tələbə köçürmə ilə «təmiz» başlayır — xəbərdarlıq."""
        with bypass_rls():
            Enrollment.objects.filter(pk=self.fx.enr_math.pk).update(absence_hours=25)
        preview = self._preview(self.fx.group_a2)
        self.assertEqual(preview["totals"]["barred_now"], 1)
        self.assertIn("barred_cleared", preview["warnings"])

    def test_preview_blocks_same_group(self):
        preview = self._preview(self.fx.group_a1)
        self.assertFalse(preview["ok"])
        self.assertIn("same_group", preview["blocking"])

    def test_preview_blocks_target_outside_scope(self):
        """Koordinator qonşu ixtisasın qrupunu hədəf seçə bilmir."""
        preview = self._preview(self.fx.group_a3, user=self.fx.coordinator)
        self.assertFalse(preview["ok"])
        self.assertIn("target_group_outside_scope", preview["blocking"])

    def test_preview_of_out_of_scope_record_is_404(self):
        record_b = StudentAcademicRecord.objects.get(student=self.fx.student_b)
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.preview_group_transfer(
                actor=self._actor(self.fx.dean_m),
                record_id=str(record_b.pk),
                new_group_id=str(self.fx.group_a2.pk),
            )
        self.assertEqual(ctx.exception.status, 404)


class TransferActionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = AcademicFixture()

    def _actor(self, user=None):
        return people.resolve_actor(_request(user or self.fx.dean_m, self.fx.org))

    def test_transfer_uses_the_official_evidence_flow(self):
        with bypass_rls():
            preview = people.preview_group_transfer(
                actor=self._actor(),
                record_id=str(self.fx.record_a.pk),
                new_group_id=str(self.fx.group_a2.pk),
            )
            result = people.transfer_group(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                new_group_id=str(self.fx.group_a2.pk),
                reason="Dekanlıq sərəncamı №12",
            )
            self.fx.record_a.refresh_from_db()
            old = Enrollment.objects.get(pk=self.fx.enr_math.pk)
            successors = Enrollment.objects.filter(
                student=self.fx.student_a,
                offering__group=self.fx.group_a2,
                status=Enrollment.Status.ENROLLED,
            )

        # Ön baxış NƏ VƏD ETDİSƏ, əməl onu etdi.
        self.assertEqual(result["moved"], preview["totals"]["subjects"])
        self.assertEqual(result["created"], preview["totals"]["subjects"])
        self.assertEqual(self.fx.record_a.group_id, self.fx.group_a2.pk)
        # Köhnə sətir SİLİNMİR — tarixçəyə keçir və varisə bağlanır.
        self.assertEqual(old.status, Enrollment.Status.DROPPED)
        self.assertIsNotNone(old.superseded_by_id)
        self.assertEqual(successors.count(), 2)
        # Yeni sətir TƏMİZ başlayır (ön baxışın xəbərdarlığı doğru idi).
        self.assertEqual({row.absence_hours for row in successors}, {0})

    def test_transfer_requires_a_reason(self):
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.transfer_group(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                new_group_id=str(self.fx.group_a2.pk),
                reason="  ",
            )
        self.assertEqual(ctx.exception.reason_code, "reason_required")

    def test_transfer_is_audited_with_preview_numbers(self):
        with bypass_rls():
            people.transfer_group(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                new_group_id=str(self.fx.group_a2.pk),
                reason="Qrup birləşməsi",
            )
            entry = AuditLog.objects.filter(resource_type="accounts.people.academic").order_by("-created_at").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user_id, self.fx.dean_m.pk)
        self.assertEqual(entry.changes["action"], "people.group_transferred")
        self.assertEqual(entry.old_values["group"], "Qrup A1-1")
        self.assertEqual(entry.new_values["group"], "Qrup A1-2")
        self.assertIn("preview_totals", entry.changes)

    def test_transfer_to_group_outside_scope_is_blocked(self):
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.transfer_group(
                self._actor(self.fx.coordinator),
                record_id=str(self.fx.record_a.pk),
                new_group_id=str(self.fx.group_a3.pk),
                reason="Sahədən kənar cəhd",
            )
        self.assertEqual(ctx.exception.status, 409)

    def test_transfer_of_another_faculty_student_is_404(self):
        record_b = StudentAcademicRecord.objects.get(student=self.fx.student_b)
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.transfer_group(
                self._actor(self.fx.dean_m),
                record_id=str(record_b.pk),
                new_group_id=str(self.fx.group_a2.pk),
                reason="Başqa fakültə",
            )
        self.assertEqual(ctx.exception.status, 404)

    def test_transfer_without_permission_is_denied(self):
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.transfer_group(
                self._actor(self.fx.dean_a),  # manage_status var, manage_academic YOX
                record_id=str(self.fx.record_a.pk),
                new_group_id=str(self.fx.group_a2.pk),
                reason="İcazəsiz cəhd",
            )
        self.assertEqual(ctx.exception.reason_code, "permission_denied")


class AcademicStatusTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = AcademicFixture()

    def _actor(self, user=None):
        return people.resolve_actor(_request(user or self.fx.dean_m, self.fx.org))

    def test_expelling_deactivates_the_record_but_keeps_history(self):
        with bypass_rls():
            enrollments_before = Enrollment.objects.filter(student=self.fx.student_a).count()
            result = people.set_academic_status(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                status="expelled",
                reason="Təhsil haqqı ödənilmədi",
            )
            self.fx.record_a.refresh_from_db()
            enrollments_after = Enrollment.objects.filter(student=self.fx.student_a).count()

        self.assertEqual(result["previous"], "enrolled")
        self.assertEqual(self.fx.record_a.status, "expelled")
        self.assertFalse(self.fx.record_a.is_active)
        # SƏRT SİLİNMƏ YOXDUR — qeydiyyatlar olduğu kimi qalır.
        self.assertEqual(enrollments_after, enrollments_before)

    def test_academic_leave_requires_a_reason(self):
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.set_academic_status(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                status="academic_leave",
                reason="",
            )
        self.assertEqual(ctx.exception.reason_code, "reason_required")

    def test_same_status_is_rejected(self):
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.set_academic_status(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                status="enrolled",
            )
        self.assertEqual(ctx.exception.status, 409)

    def test_unknown_status_is_rejected(self):
        with bypass_rls(), self.assertRaises(RimAccessError) as ctx:
            people.set_academic_status(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                status="dismissed",
                reason="Naməlum",
            )
        self.assertEqual(ctx.exception.status, 400)

    def test_status_change_is_audited(self):
        with bypass_rls():
            people.set_academic_status(
                self._actor(),
                record_id=str(self.fx.record_a.pk),
                status="graduated",
                reason="Məzun oldu",
            )
            entry = AuditLog.objects.filter(resource_type="accounts.people.academic").order_by("-created_at").first()
        self.assertEqual(entry.changes["action"], "people.academic_status_changed")
        self.assertEqual(entry.new_values["status"], "graduated")


class AcademicEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = AcademicFixture()

    def setUp(self):
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization_id"] = str(self.fx.org.pk)
        session.save()

    def test_card_endpoint_returns_records(self):
        self._login(self.fx.dean_m)
        with bypass_rls():
            response = self.client.get(
                reverse("accounts:people_student_card", kwargs={"user_id": self.fx.student_a.pk})
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["can_manage"])
        self.assertEqual(payload["records"][0]["group_name"], "Qrup A1-1")

    def test_group_search_is_scoped_and_paginated(self):
        self._login(self.fx.coordinator)
        with bypass_rls():
            response = self.client.get(
                reverse("accounts:people_academic_groups"),
                {"q": "Qrup", "exclude": str(self.fx.group_a1.pk), "limit": "1"},
            )
        payload = response.json()
        self.assertTrue(payload["has_access"])
        self.assertEqual([row["text"] for row in payload["results"]], ["Qrup A1-2"])
        self.assertFalse(payload["has_more"])

    def test_preview_endpoint_denied_without_permission(self):
        self._login(self.fx.dean_a)  # manage_academic YOX
        with bypass_rls():
            response = self.client.get(
                reverse("accounts:people_transfer_preview", kwargs={"record_id": str(self.fx.record_a.pk)}),
                {"group": str(self.fx.group_a2.pk)},
            )
        self.assertEqual(response.status_code, 403)

    def test_card_endpoint_denied_for_teacher(self):
        self._login(self.fx.teacher_a)
        with bypass_rls():
            response = self.client.get(
                reverse("accounts:people_student_card", kwargs={"user_id": self.fx.student_a.pk})
            )
        self.assertIn(response.status_code, (403, 404))

    def test_action_endpoint_transfers_and_returns_groups(self):
        self._login(self.fx.dean_m)
        with bypass_rls():
            response = self.client.post(
                reverse("accounts:people_action"),
                data={
                    "action": "transfer_group",
                    "record_id": str(self.fx.record_a.pk),
                    "group_id": str(self.fx.group_a2.pk),
                    "reason": "Dekanlıq sərəncamı",
                },
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["to_group"]["name"], "Qrup A1-2")

    def test_action_endpoint_rejects_transfer_without_permission(self):
        self._login(self.fx.dean_a)
        with bypass_rls():
            response = self.client.post(
                reverse("accounts:people_action"),
                data={
                    "action": "transfer_group",
                    "record_id": str(self.fx.record_a.pk),
                    "group_id": str(self.fx.group_a2.pk),
                    "reason": "İcazəsiz",
                },
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 403)


class SectionContractTest(TestCase):
    """Şablon müqaviləsi: bayraq və URL-lər context-də var və DOĞRU qapılıdır."""

    @classmethod
    def setUpTestData(cls):
        cls.fx = AcademicFixture()

    def _section(self, user, kind):
        from apps.accounts.views.people.section import build_people_section

        request = _request(user, self.fx.org)
        with bypass_rls():
            return build_people_section(request, kind)["people_section"]

    def test_students_section_exposes_management_urls(self):
        section = self._section(self.fx.dean_m, "students")
        self.assertTrue(section["can_manage_academic"])
        self.assertIn("card_url_template", section)
        self.assertIn("groups_url", section)
        self.assertIn("preview_url_template", section)
        self.assertEqual(
            {option["key"] for option in section["academic_status_options"]},
            {"enrolled", "academic_leave", "expelled", "graduated"},
        )

    def test_teachers_section_never_offers_student_management(self):
        section = self._section(self.fx.dean_m, "teachers")
        self.assertFalse(section["can_manage_academic"])

    def test_actor_without_key_gets_no_management_flag(self):
        section = self._section(self.fx.dean_a, "students")
        self.assertFalse(section["can_manage_academic"])


class RolePermissionTemplateTest(TestCase):
    """Şablonlar: koordinator və dekan açarı DAŞIYIR, müəllim DAŞIMIR."""

    def test_default_templates_grant_manage_academic(self):
        from apps.organizations.default_roles_university import UNIVERSITY_ROLES

        by_name = {template["name"]: template.get("permissions", []) for template in UNIVERSITY_ROLES}
        self.assertIn(MANAGE, by_name["program_coordinator"])
        self.assertIn(MANAGE, by_name["dean"])
        self.assertNotIn(MANAGE, by_name["teacher"])

    def test_sync_command_plans_the_new_key_for_existing_orgs(self):
        """Mövcud universitetdə açar şablondan gəlmir — sinxronizasiya lazımdır."""
        from apps.organizations.management.commands.sync_people_permissions import (
            people_permissions_by_role,
        )

        wanted = people_permissions_by_role()
        self.assertIn(MANAGE, wanted["program_coordinator"])
        self.assertIn(MANAGE, wanted["dean"])

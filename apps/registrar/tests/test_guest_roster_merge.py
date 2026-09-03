"""«Alt qrup birləşməsi» — öz jurnalından azad et + hədəf jurnala köçür.

Sahibin əsas ssenarisi: «tarix fənni üzrə ALT QRUPDAN hansısa tələbəni əlavə
etmək olsun». Mandat fənlərdə alt qrupun ÖZ jurnalı onsuz da var (services.
enroll_mandatory_subjects hər qrup üçün açılış yaradır), ona görə sadə əlavə
dublikat qapısına dəyir — bu fayl həmin dalanın nəzarətli çıxışını bağlayır.

Yoxlanan invariantlar:

* münaqişə + bayraqsız cəhd → xəta MƏTNİ nə etməli olduğunu deyir (dalan yox);
* birləşmə: mənbə qeydiyyat ``dropped`` + ``superseded_by`` → hədəf sətir;
* KÖHNƏ İŞ İTMİR — bal/davamiyyət sətirləri qalır, qayıb saatı hədəf jurnalın
  buraxılış həddinə köçürülür, sətirdə «əvvəlki jurnal» xülasəsi görünür;
* səbəb məcburidir, audit tamdır, geri götürmə mənbəni BƏRPA edir;
* önbaxış (təsdiqdən əvvəl nəticə) HTTP səthində;
* qüsur (a): mutasiya da ``status=ENROLLED`` süzür (lookup ilə eyni tərif);
* qüsur (b): rəsmi köçürmədən sonra «alt qrup» çipi SUSUR və qonaq-çıxarma
  yolu bağlanır.
"""

import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.registrar import gradebook, guest_merge, guest_roster, transfer
from apps.registrar.models import (
    AcademicStatus,
    AttendanceStatus,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonKind,
    LessonMark,
    StudentAcademicRecord,
)
from core.rls import bypass_rls

from .test_guest_roster import _GuestRosterBase

REASON = "Dekanlıq sərəncamı №77 — alt qrup birləşməsi"


class _MergeBase(_GuestRosterBase):
    """Alt qrupun ÖZ Tarix jurnalında real iz (dərs + qayıb + bal) yaradır."""

    def _source_enrollment(self):
        return Enrollment.objects.get(student=self.guest, offering=self.other_offering)

    def _seed_source_work(self, *, absences=2, scored=1):
        """Mənbə jurnalda dərslər + işarələr — «itə biləcək iş» məhz budur."""
        with bypass_rls():
            enrollment = self._source_enrollment()
            for index in range(absences + scored):
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=self.other_offering,
                    date=datetime.date(2025, 10, 1) + datetime.timedelta(days=index),
                    kind=LessonKind.SEMINAR,
                    hours=2,
                )
                absent = index < absences
                LessonMark.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status=AttendanceStatus.ABSENT if absent else AttendanceStatus.PRESENT,
                    score=None if absent else 8,
                )
            gradebook.recompute_absence_hours(enrollment=enrollment)
            return enrollment


class MergeGateTest(_MergeBase):
    """Bayraqsız cəhd DALAN olmamalıdır — xəta nə etməli olduğunu deməlidir."""

    def test_conflict_without_release_explains_the_way_out(self):
        with bypass_rls():
            with self.assertRaises(ValidationError) as ctx:
                guest_roster.add_guest_student(offering=self.offering, student=self.guest, by_user=self.coordinator)
        message = "; ".join(ctx.exception.messages)
        self.assertIn("azad et", message)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student=self.guest).exists())

    def test_reason_is_mandatory_for_merge(self):
        with bypass_rls():
            with self.assertRaises(ValidationError):
                guest_roster.add_guest_student(
                    offering=self.offering,
                    student=self.guest,
                    by_user=self.coordinator,
                    release_source=True,
                    reason="  ",
                )
            self.assertEqual(self._source_enrollment().status, Enrollment.Status.ENROLLED)

    def test_final_grade_in_source_blocks_the_merge(self):
        with bypass_rls():
            FinalGrade.objects.create(organization=self.org, enrollment=self._source_enrollment(), exam_score=40)
            with self.assertRaises(ValidationError) as ctx:
                guest_roster.add_guest_student(
                    offering=self.offering,
                    student=self.guest,
                    by_user=self.coordinator,
                    release_source=True,
                    reason=REASON,
                )
        self.assertIn("yekun qiyməti", "; ".join(ctx.exception.messages))


class MergeServiceTest(_MergeBase):
    def test_merge_supersedes_source_and_adds_guest_row(self):
        with bypass_rls():
            source = self._seed_source_work()
            target = guest_roster.add_guest_student(
                offering=self.offering,
                student=self.guest,
                by_user=self.coordinator,
                source_group=self.group2,
                reason=REASON,
                release_source=True,
            )
            source.refresh_from_db()
        self.assertEqual(target.offering_id, self.offering.id)
        self.assertEqual(target.source_group_id, self.group2.id)
        self.assertEqual(source.status, Enrollment.Status.DROPPED)
        self.assertEqual(source.superseded_by_id, target.pk)

    def test_old_work_is_preserved_and_carried(self):
        """Köhnə iz SİLİNMİR; qayıb saatı hədəf jurnalın həddinə köçürülür."""
        with bypass_rls():
            source = self._seed_source_work(absences=3, scored=2)
            source_hours = source.absence_hours
            target = guest_roster.add_guest_student(
                offering=self.offering,
                student=self.guest,
                by_user=self.coordinator,
                source_group=self.group2,
                reason=REASON,
                release_source=True,
            )
            target.refresh_from_db()
            journal = gradebook.get_offering_journal(offering=self.offering)
            preserved = LessonMark.objects.filter(enrollment=source).count()
        self.assertEqual(source_hours, 6)  # 3 × 2 saat
        self.assertEqual(preserved, 5)  # heç bir işarə silinmir
        self.assertEqual(target.absence_hours, 6)  # denormallaşmış sayğac köçür
        row = {r["student"].id: r for r in journal["rows"]}[self.guest.id]
        self.assertTrue(row["is_guest"])
        self.assertEqual(row["own_absence_hours"], 0)  # hədəf jurnalda hələ dərs yoxdur
        self.assertEqual(row["absence_hours"], 6)  # amma hədd sayğacı sıfırlanmır
        self.assertEqual(row["carry_over"]["absence_count"], 3)
        self.assertEqual(row["carry_over"]["marks"], 5)
        self.assertEqual(row["carry_over"]["groups"], ["G2"])

    def test_recompute_keeps_the_carried_hours(self):
        """Hədəf jurnalda yazı olanda köçürülən saat SİLİNMİR (recompute üstündən yazmır)."""
        with bypass_rls():
            self._seed_source_work(absences=2, scored=0)
            target = guest_roster.add_guest_student(
                offering=self.offering,
                student=self.guest,
                by_user=self.coordinator,
                source_group=self.group2,
                reason=REASON,
                release_source=True,
            )
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=datetime.date(2025, 11, 3),
                kind=LessonKind.SEMINAR,
                hours=2,
            )
            LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=target, status=AttendanceStatus.ABSENT
            )
            hours = gradebook.recompute_absence_hours(enrollment=target)
        self.assertEqual(hours, 6)  # 4 köçürülən + 2 yeni

    def test_merge_is_revertible(self):
        with bypass_rls():
            source = self._seed_source_work()
            target = guest_roster.add_guest_student(
                offering=self.offering,
                student=self.guest,
                by_user=self.coordinator,
                source_group=self.group2,
                reason=REASON,
                release_source=True,
            )
            guest_roster.remove_guest_student(
                offering=self.offering, enrollment=target, by_user=self.coordinator, reason="sərəncam ləğv edildi"
            )
            source.refresh_from_db()
            target.refresh_from_db()
        self.assertEqual(target.status, Enrollment.Status.DROPPED)
        self.assertEqual(source.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(source.superseded_by_id)

    def test_merge_is_audited(self):
        from apps.audit.models import AuditLog

        with bypass_rls():
            self._seed_source_work()
            guest_roster.add_guest_student(
                offering=self.offering,
                student=self.guest,
                by_user=self.coordinator,
                source_group=self.group2,
                reason=REASON,
                release_source=True,
            )
            entry = AuditLog.objects.filter(resource_type="registrar.journal_guest_merge").order_by("-created_at")[0]
        self.assertEqual(entry.changes["verb"], "release")
        self.assertEqual(entry.changes["source_group"], "G2")
        self.assertEqual(entry.reason, REASON)
        # Nəyin qorunduğu audit izində rəqəmlə qalır.
        self.assertEqual(entry.changes["preserved"]["absence_hours"], "4")


class MergeHttpTest(_MergeBase):
    def test_preview_reports_conflict_with_numbers(self):
        self._seed_source_work(absences=2, scored=1)
        client = self._client(self.coordinator)
        response = client.get(
            reverse("registrar:journal_guest_add_preview", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["conflict"])
        self.assertTrue(body["release_required"])
        self.assertEqual(body["blocked"], "")
        source = body["sources"][0]
        self.assertEqual(source["group"], "G2")
        self.assertEqual(source["marks"], 3)
        self.assertEqual(source["absence_count"], 2)
        self.assertEqual(source["absence_hours"], 4)

    def test_preview_has_no_conflict_when_source_journal_is_absent(self):
        self._drop_own_history(self.guest)
        client = self._client(self.coordinator)
        body = client.get(
            reverse("registrar:journal_guest_add_preview", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        ).json()
        self.assertFalse(body["conflict"])

    def test_add_over_http_requires_the_release_flag(self):
        client = self._client(self.coordinator)
        url = reverse("registrar:journal_guest_add", args=[self.offering.id])
        payload = {"group": str(self.group2.id), "student": str(self.guest.id), "reason": REASON}
        refused = client.post(url, payload)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("azad et", refused.json()["error"])

        payload["release_source"] = "on"
        accepted = client.post(url, payload)
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(accepted.json()["released"])
        with bypass_rls():
            self.assertEqual(self._source_enrollment().status, Enrollment.Status.DROPPED)

    def test_grid_shows_the_carry_over_chip_after_a_merge(self):
        """Köçürülən iş SƏHİFƏDƏ görünməlidir — «görünməz iş» qərarın şərtidir."""
        self._seed_source_work(absences=2, scored=1)
        client = self._client(self.coordinator)
        client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {
                "group": str(self.group2.id),
                "student": str(self.guest.id),
                "reason": REASON,
                "release_source": "on",
            },
        )
        page = client.get(reverse("registrar:journal_detail", args=[self.offering.id])).content.decode()
        self.assertIn("jgs-carry", page)
        self.assertIn("Əvvəlki jurnaldan", page)

    def test_modal_exposes_the_merge_surface(self):
        client = self._client(self.coordinator)
        page = client.get(reverse("registrar:journal_detail", args=[self.offering.id])).content.decode()
        self.assertIn("data-jgs-merge", page)
        self.assertIn("data-jgs-release", page)
        self.assertIn("data-preview-url", page)


class StatusMismatchTest(_MergeBase):
    """Qüsur (a): namizəd siyahısı ilə mutasiyanın «uyğun tələbə» tərifi eyni olmalıdır."""

    def _expel(self, student):
        with bypass_rls():
            StudentAcademicRecord.objects.filter(organization=self.org, student=student).update(
                status=AcademicStatus.EXPELLED
            )

    def test_expelled_but_active_record_is_rejected_by_service(self):
        self._drop_own_history(self.guest)
        self._expel(self.guest)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                guest_roster.add_guest_student(
                    offering=self.offering, student=self.guest, by_user=self.coordinator, source_group=self.group2
                )
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student=self.guest).exists())

    def test_expelled_but_active_record_is_rejected_over_http(self):
        self._drop_own_history(self.guest)
        self._expel(self.guest)
        client = self._client(self.coordinator)
        response = client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"group": str(self.group2.id), "student": str(self.guest.id)},
        )
        self.assertEqual(response.status_code, 404)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student=self.guest).exists())

    def test_candidate_list_and_mutation_agree(self):
        """Siyahıda görünməyən tələbə POST ilə də keçməməlidir (eyni süzgəc)."""
        self._drop_own_history(self.guest)
        self._expel(self.guest)
        with bypass_rls():
            visible = [r.student_id for r in guest_roster.candidate_records(offering=self.offering, group=self.group2)]
        self.assertNotIn(self.guest.id, visible)


class ProvenanceAfterTransferTest(_MergeBase):
    """Qüsur (b): rəsmi köçürmədən sonra «alt qrup» çipi YALAN danışmamalıdır."""

    def _guest_row(self):
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self.offering)
        return {row["student"].id: row for row in journal["rows"]}.get(self.guest.id)

    def _add_guest(self):
        with bypass_rls():
            return guest_roster.add_guest_student(
                offering=self.offering,
                student=self.guest,
                by_user=self.coordinator,
                source_group=self.group2,
                reason=REASON,
                release_source=True,
            )

    def test_chip_is_shown_while_the_student_belongs_elsewhere(self):
        self._add_guest()
        self.assertTrue(self._guest_row()["is_guest"])

    def test_chip_goes_silent_after_the_official_transfer(self):
        enrollment = self._add_guest()
        with bypass_rls():
            record = StudentAcademicRecord.objects.get(organization=self.org, student=self.guest)
            transfer.transfer_student_group(
                record=record,
                new_group=self.group1,
                period=self.period,
                by_user=self.coordinator,
                reason="rəsmi köçürmə",
            )
            enrollment.refresh_from_db()
        # Provenans TARİXİ faktdır — 0056 trigger-i onu silməyə imkan vermir…
        self.assertEqual(enrollment.source_group_id, self.group2.id)
        # …amma çip CARİ iddiadır və artıq susmalıdır.
        self.assertFalse(self._guest_row()["is_guest"])

    def test_transferred_student_cannot_be_removed_through_the_guest_path(self):
        enrollment = self._add_guest()
        with bypass_rls():
            record = StudentAcademicRecord.objects.get(organization=self.org, student=self.guest)
            transfer.transfer_student_group(
                record=record,
                new_group=self.group1,
                period=self.period,
                by_user=self.coordinator,
                reason="rəsmi köçürmə",
            )
            with self.assertRaises(ValidationError) as ctx:
                guest_roster.remove_guest_student(
                    offering=self.offering, enrollment=enrollment, by_user=self.coordinator
                )
            enrollment.refresh_from_db()
        self.assertIn("rəsmi qrup köçürməsi", "; ".join(ctx.exception.messages))
        self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)


class CarryOverHelperTest(_MergeBase):
    def test_carry_map_is_empty_without_a_merge(self):
        self._drop_own_history(self.guest)
        with bypass_rls():
            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=self.guest, by_user=self.coordinator, source_group=self.group2
            )
            self.assertEqual(guest_merge.carry_over_map([enrollment.pk]), {})
            self.assertEqual(guest_merge.carried_absence_hours(enrollment), 0)

    def test_regular_row_never_queries_carry(self):
        with bypass_rls():
            host_enrollment = self.host.enrollments.get(offering=self.offering)
            self.assertEqual(guest_merge.carried_absence_hours(host_enrollment), 0)

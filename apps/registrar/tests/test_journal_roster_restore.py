"""«Tələbəni bərpa et» — səhvən çıxarılmış tələbənin jurnala qaytarılması (sahib 2026-11-15).

Sahib: «kimsə səhvən jurnaldan uzaqlaşdırılıb, sonra necə bərpa edim bilmirəm».

Kilidlənən qaydalar:

* çıxar → siyahıda görünür (kim, nə vaxt, səbəb) → «Bərpa et» → tələbə qriddə yenidəndir, qeydiyyat EYNİDİR
  (yeni sətir yaradılmır), xanaları (bal / davamiyyət) yerindədir; tarixçəyə ``roster-restore`` düşür;
* «Fəndən azad», «Jurnal təmizliyi» (dondurma — yalnız RİM) və alt qrup «Çıxar»-ı üçün eyni düymə;
* tələbə həmin fənn üzrə başqa jurnalda aktivdirsə aydın xəta (qrupun adı ilə), heç nə yazılmır;
* bağlı jurnalda düymə səbəblə deaktiv, POST 409; açarsız aktor 403, əhatədən kənar 404;
* akademik statusa görə dondurulmuş sətir siyahıda səbəblə görünür, bərpa olunmur (qrup reyestrinin işidir).
"""

import datetime
import json

from django.test import override_settings
from django.urls import reverse

from apps.registrar import gradebook, journal_history, journal_hygiene_actions, journal_roster_restore
from apps.registrar.models import (
    AssessmentScheme,
    AttendanceStatus,
    CourseOffering,
    Enrollment,
    HygieneCategory,
    JournalHygieneDecision,
    Lesson,
    LessonKind,
    LessonMark,
)
from apps.registrar.tests.test_guest_roster import _doc, _GuestRosterBase
from apps.registrar.tests.test_subject_exempt import _ExemptBase
from core.rls import bypass_rls

LIST = "registrar:journal_roster_restore_list"
APPLY = "registrar:journal_roster_restore_apply"


class _RestoreMixin:
    def _rows(self, user):
        response = self._client(user).get(reverse(LIST, args=[self.offering.id]))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["rows"]

    def _restore(self, user, enrollment, note=""):
        return self._client(user).post(
            reverse(APPLY, args=[self.offering.id]),
            data=json.dumps({"enrollment": str(enrollment.pk), "note": note}),
            content_type="application/json",
        )

    def _journal_ids(self):
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self.offering)
        return [row["student"].id for row in journal["rows"]]

    def _mark(self, enrollment):
        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=datetime.date(2025, 10, 1),
                kind=LessonKind.SEMINAR,
                hours=2,
            )
            return LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=enrollment,
                status=AttendanceStatus.PRESENT,
                score=8,
            )


@override_settings(LANGUAGE_CODE="az")
class ExemptRestoreTest(_RestoreMixin, _ExemptBase):
    def test_removed_student_is_listed_and_restored_with_cells(self):
        mark = self._mark(self.enrollment)
        removed = self._exempt(removal_reason="added_by_mistake", reason="Səhv sətir")
        self.assertEqual(removed.status_code, 200, removed.content)
        self.assertNotIn(self.student.id, self._journal_ids())

        page = self._client(self.coordinator).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertContains(page, "data-jrs-open")
        self.assertContains(page, "data-jrs-modal")
        self.assertContains(page, "journal_roster_restore.js")

        (row,) = self._rows(self.coordinator)
        self.assertEqual(row["enrollment"], str(self.enrollment.pk))
        self.assertEqual(row["kind"], journal_roster_restore.KIND_EXEMPT)
        self.assertTrue(row["restorable"], row)
        self.assertEqual(row["reason"], "Səhv əlavə olunub")
        self.assertEqual(row["note"], "Səhv sətir")
        self.assertEqual(row["group"], "SE-1")
        self.assertTrue(row["by"])

        response = self._restore(self.coordinator, self.enrollment, note="səhvən çıxarılmışdı")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(self.student.id, self._journal_ids())
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.enrollment.pk).status, Enrollment.Status.ENROLLED)
            self.assertEqual(
                Enrollment.objects.filter(student=self.student, offering=self.offering).count(), 1
            )  # yeni sətir yaradılmayıb
            self.assertTrue(LessonMark.objects.filter(pk=mark.pk, enrollment=self.enrollment, score=8).exists())
            decision = JournalHygieneDecision.objects.get(enrollment=self.enrollment)
            history = journal_history.history_page(offering=self.offering)
        self.assertIsNotNone(decision.reverted_at)
        self.assertEqual(history["entries"][0]["kind"], "roster-restore")
        self.assertEqual(self._rows(self.coordinator), [])

    def test_active_elsewhere_is_a_clear_error(self):
        self._exempt(removal_reason="group_transfer")
        with bypass_rls():
            other_group = self.group.__class__.objects.create(
                organization=self.org, name="SE-2", slug="se-g2", unit_type=self.group.unit_type, parent=self.faculty
            )
            other = CourseOffering.objects.create(
                organization=self.org, subject=self.physics, period=self.period, group=other_group
            )
            Enrollment.objects.create(organization=self.org, student=self.student, offering=other)
        (row,) = self._rows(self.coordinator)
        self.assertFalse(row["restorable"])
        self.assertIn("SE-2", row["message"])

        response = self._restore(self.coordinator, self.enrollment)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "active_elsewhere")
        self.assertIn("SE-2", response.json()["message"])
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.DROPPED)

    def test_closed_journal_blocks_restore(self):
        self._exempt(removal_reason="suspension")
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            AssessmentScheme.objects.filter(pk=scheme.pk).update(is_published=True, approval_status="approved")
        page = self._client(self.coordinator).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertContains(page, "data-jrs-blocked-btn")
        (row,) = self._rows(self.coordinator)
        self.assertFalse(row["restorable"])
        response = self._restore(self.coordinator, self.enrollment)
        self.assertEqual((response.status_code, response.json()["error"]), (409, "roster_closed"))
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.DROPPED)

    def test_permissions(self):
        self._exempt(removal_reason="suspension")
        teacher = self._client(self.teacher).get(reverse(LIST, args=[self.offering.id]))
        self.assertEqual(teacher.status_code, 403)
        self.assertEqual(self._restore(self.teacher, self.enrollment).status_code, 403)
        self.assertEqual(self._restore(self.outsider, self.enrollment).status_code, 404)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.DROPPED)
        page = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertNotContains(page, "data-jrs-open")

    def test_no_button_without_removed_students(self):
        page = self._client(self.coordinator).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertNotContains(page, "data-jrs-open")
        self.assertNotContains(page, "journal_roster_restore.js")

    def test_hygiene_freeze_is_restored_only_by_rim(self):
        with bypass_rls():
            journal_hygiene_actions.record_decisions(
                organization=self.org,
                category=HygieneCategory.LEFT_STUDENT.value,
                rows=[
                    {
                        "id": str(self.enrollment.pk),
                        "status": Enrollment.Status.ENROLLED,
                        "reason": "expelled",
                        "evidence": {"enrollment": str(self.enrollment.pk)},
                    }
                ],
                to_status=Enrollment.Status.SUSPENDED,
                reason="Rektorun əmri ilə jurnallar təmizlənir (test).",
                actor=self.rim,
            )
        (row,) = self._rows(self.coordinator)
        self.assertEqual((row["kind"], row["status"]), (journal_roster_restore.KIND_HYGIENE, "suspended"))
        self.assertFalse(row["restorable"])
        self.assertEqual(self._restore(self.coordinator, self.enrollment).status_code, 403)

        (rim_row,) = self._rows(self.rim)
        self.assertTrue(rim_row["restorable"], rim_row)
        self.assertIn("Ayrılmış tələbə", rim_row["reason"])
        response = self._restore(self.rim, self.enrollment)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)
        with bypass_rls():
            history = journal_history.history_page(offering=self.offering)
        entry = history["entries"][0]
        self.assertEqual(entry["kind"], "roster-restore")
        self.assertEqual(entry["rows"][0]["item"], "Jurnal təmizliyi")

    def test_academic_suspension_is_listed_but_not_restorable(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enrollment.pk).update(status=Enrollment.Status.SUSPENDED)
        (row,) = self._rows(self.rim)
        self.assertEqual(row["kind"], "")
        self.assertFalse(row["restorable"])
        self.assertIn("qrup reyestrində", row["message"])
        response = self._restore(self.rim, self.enrollment)
        self.assertEqual((response.status_code, response.json()["error"]), (409, "not_restorable"))
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.SUSPENDED)


@override_settings(LANGUAGE_CODE="az")
class GuestRestoreTest(_RestoreMixin, _GuestRosterBase):
    def _add_and_remove(self):
        client = self._client(self.coordinator)
        self._drop_own_history(self.guest)
        added = client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"document": _doc(), "group": str(self.group2.id), "student": str(self.guest.id), "reason": "alt qrup"},
        )
        self.assertEqual(added.status_code, 200, added.content)
        with bypass_rls():
            enrollment = Enrollment.objects.get(pk=added.json()["enrollment_id"])
        mark = self._mark(enrollment)
        removed = client.post(
            reverse("registrar:journal_guest_remove", args=[self.offering.id]),
            {"enrollment": str(enrollment.pk), "removal_reason": "added_by_mistake"},
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        return enrollment, mark

    def test_guest_removal_is_restored_on_the_same_row(self):
        enrollment, mark = self._add_and_remove()
        self.assertNotIn(self.guest.id, self._journal_ids())
        (row,) = [item for item in self._rows(self.coordinator) if item["enrollment"] == str(enrollment.pk)]
        self.assertEqual(row["kind"], journal_roster_restore.KIND_GUEST)
        self.assertTrue(row["restorable"], row)
        self.assertEqual(row["reason"], "Səhv əlavə olunub")

        response = self._restore(self.coordinator, enrollment)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(self.guest.id, self._journal_ids())
        with bypass_rls():
            restored = Enrollment.objects.get(pk=enrollment.pk)
            self.assertEqual(restored.status, Enrollment.Status.ENROLLED)
            self.assertEqual(restored.source_group_id, self.group2.id)
            self.assertEqual(Enrollment.objects.filter(student=self.guest, offering=self.offering).count(), 1)
            self.assertTrue(LessonMark.objects.filter(pk=mark.pk, enrollment=enrollment).exists())
            history = journal_history.history_page(offering=self.offering)
        self.assertEqual(history["entries"][0]["kind"], "roster-restore")

    def test_guest_active_in_own_journal_gets_a_hint(self):
        enrollment, _mark = self._add_and_remove()
        with bypass_rls():
            Enrollment.objects.filter(student=self.guest, offering=self.other_offering).update(
                status=Enrollment.Status.ENROLLED
            )
        response = self._restore(self.coordinator, enrollment)
        self.assertEqual((response.status_code, response.json()["error"]), (409, "active_elsewhere"))
        self.assertIn("öz jurnalından azad et", response.json()["message"])
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=enrollment.pk).status, Enrollment.Status.DROPPED)

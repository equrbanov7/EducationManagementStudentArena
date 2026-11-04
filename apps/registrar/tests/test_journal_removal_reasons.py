"""Jurnaldan çıxarılmanın SƏBƏBİ + RİM-in mərkəzi «Jurnaldan çıxarılmalar» siyahısı (sahib 2026-11-04).

Sahib: «Jurnalda hansısa tələbəni çıxardarkən səbəb seçmə olsun select option ilə … Daha sonra mən harada isə
onda baxa bilim o tip hadisələrə — nəyə görə olub.»

Kilidlənən qaydalar:

* «Fəndən azad et» və alt qrup «Çıxar» səbəbsiz qəbul olunmur (400, tələbə jurnalda qalır); naməlum səbəb
  rədd edilir; «Digər» qeydsiz olmur;
* səbəb + qeyd ``JournalRemoval``-a (append-only) yazılır və jurnalın «Dəyişiklik tarixçəsi»ndə görünür
  (``roster-removal`` / «Bərpa et»dən sonra ``roster-restore``); «Azad edilənlər» siyahısında səbəb nişanı var;
* xarici nəticənin tanınması ilə azadlıq avtomatik «Kredit tanınması / köçürmə» səbəbi alır;
* mərkəzi siyahı yalnız RİM rəhbəri / superadmin üçündür (müəllim panel / ixrac görmür — 403); süzgəclər
  (səbəb, tarix, fakültə, kafedra, müəllim, tələbə) işləyir; Excel ixracı audit olunur.
"""

import datetime

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import OrgUnit
from apps.registrar import journal_history, journal_removal, journal_removal_read, subject_exempt
from apps.registrar.models import Enrollment, JournalHygieneDecision, JournalRemoval
from apps.registrar.tests.test_guest_roster import _doc, _GuestRosterBase
from apps.registrar.tests.test_subject_exempt import _ExemptBase
from core.constants import OrgUnitType
from core.rls import bypass_rls

SECTION = "journal-removals"


def _removals(**filters):
    with bypass_rls():
        return list(JournalRemoval.objects.filter(**filters))


class SubjectExemptReasonTest(_ExemptBase):
    def test_reason_is_required(self):
        response = self._exempt(removal_reason="")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "reason_required")
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)
        self.assertEqual(_removals(), [])

    def test_unknown_reason_is_refused(self):
        response = self._exempt(removal_reason="because")
        self.assertEqual((response.status_code, response.json()["error"]), (400, "reason_invalid"))
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)

    def test_other_needs_a_note(self):
        response = self._exempt(removal_reason="other", reason="   ")
        self.assertEqual((response.status_code, response.json()["error"]), (400, "note_required"))
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)
        ok = self._exempt(removal_reason="other", reason="Rektorun şifahi göstərişi")
        self.assertEqual(ok.status_code, 200, ok.content)
        (row,) = _removals()
        self.assertEqual((row.reason, row.note), ("other", "Rektorun şifahi göstərişi"))

    def test_reason_is_stored_and_shown_in_history_and_list(self):
        response = self._exempt(removal_reason="subject_substitution", reason="Sənəd №45 — Fizika II ilə əvəz")
        self.assertEqual(response.status_code, 200, response.content)
        (row,) = _removals()
        with bypass_rls():
            decision = JournalHygieneDecision.objects.get(enrollment=self.enrollment)
        self.assertEqual(row.action, "subject_exempt")
        self.assertEqual(row.reason, "subject_substitution")
        self.assertEqual(row.note, "Sənəd №45 — Fizika II ilə əvəz")
        self.assertEqual(row.actor_id, self.coordinator.id)
        self.assertEqual(row.hygiene_decision_id, decision.pk)
        self.assertIn("Sənəd №45", decision.reason)

        history = self._client(self.teacher).get(reverse("registrar:journal_history", args=[self.offering.id]))
        self.assertEqual(history.status_code, 200)
        entry = history.json()["entries"][0]
        self.assertEqual((entry["kind"], entry["group"]), ("roster-removal", "roster"))
        self.assertIn("Fənn əvəzlənməsi (sənəd təqdim edib)", entry["kind_label"])
        self.assertIn("Sənəd №45", entry["kind_label"])
        self.assertEqual(entry["rows"][0]["item"], "Fəndən azad")

        page = self._client(self.coordinator).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(page.context["exempt_rows"][0]["removal_label"], "Fənn əvəzlənməsi (sənəd təqdim edib)")
        self.assertContains(page, "data-jrr-reason")
        self.assertContains(page, "journal_removal_reason.js")

    def test_restore_is_visible_in_history_and_central_state(self):
        self._exempt(removal_reason="suspension")
        with bypass_rls():
            decision = JournalHygieneDecision.objects.get(enrollment=self.enrollment)
        restored = self._post(
            self.coordinator, "registrar:journal_subject_exempt_restore", {"decision": str(decision.pk)}
        )
        self.assertEqual(restored.status_code, 200, restored.content)
        with bypass_rls():
            page = journal_history.history_page(offering=self.offering)
            listed = journal_removal_read.page(self.org, journal_removal_read.parse_filters({}))
        self.assertEqual([entry["kind"] for entry in page["entries"]], ["roster-restore", "roster-removal"])
        self.assertEqual(listed["rows"][0]["state"], "restored")

    def test_recognition_exemption_gets_credit_recognition_reason(self):
        with bypass_rls():
            subject_exempt.exempt_student(
                offering=self.offering,
                enrollment_id=self.enrollment.pk,
                actor=self.rim,
                reason="Xarici nəticə tanınıb: Erasmus+",
                reason_code=subject_exempt.RECOGNITION_REASON_CODE,
            )
        (row,) = _removals()
        self.assertEqual((row.action, row.reason), ("subject_exempt", "credit_recognition"))
        self.assertIn("Erasmus+", row.note)

    def test_records_are_append_only(self):
        self._exempt(removal_reason="added_by_mistake")
        (row,) = _removals()
        with self.assertRaises(ValidationError):
            row.save()
        with self.assertRaises(ValidationError):
            row.delete()
        with bypass_rls():
            with self.assertRaises(DatabaseError), transaction.atomic():
                JournalRemoval.objects.filter(pk=row.pk).update(note="dəyişdi")
            with self.assertRaises(DatabaseError), transaction.atomic():
                JournalRemoval.objects.filter(pk=row.pk).delete()

    def test_clean_rules(self):
        self.assertEqual(journal_removal.clean("suspension", "  a   b "), {"reason": "suspension", "note": "a b"})
        for reason, note, code in (
            ("", "", "reason_required"),
            ("x", "", "reason_invalid"),
            ("other", "", "note_required"),
        ):
            with self.subTest(reason=reason):
                with self.assertRaises(journal_removal.RemovalReasonError) as ctx:
                    journal_removal.clean(reason, note)
                self.assertEqual(ctx.exception.code, code)


class GuestRemoveReasonTest(_GuestRosterBase):
    def _add_guest(self, client):
        self._drop_own_history(self.guest)
        added = client.post(
            reverse("registrar:journal_guest_add", args=[self.offering.id]),
            {"document": _doc(), "group": str(self.group2.id), "student": str(self.guest.id), "reason": "alt qrup"},
        )
        self.assertEqual(added.status_code, 200, added.content)
        return added.json()["enrollment_id"]

    def test_remove_requires_reason_and_stores_it(self):
        client = self._client(self.coordinator)
        enrollment_id = self._add_guest(client)
        url = reverse("registrar:journal_guest_remove", args=[self.offering.id])

        missing = client.post(url, {"enrollment": enrollment_id})
        self.assertEqual(missing.status_code, 400)
        other = client.post(url, {"enrollment": enrollment_id, "removal_reason": "other"})
        self.assertEqual(other.status_code, 400)
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=enrollment_id).status, Enrollment.Status.ENROLLED)

        removed = client.post(
            url, {"enrollment": enrollment_id, "removal_reason": "group_transfer", "removal_note": "G3-ə keçdi"}
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        (row,) = _removals()
        self.assertEqual((row.action, row.reason, row.note), ("guest_remove", "group_transfer", "G3-ə keçdi"))
        self.assertIsNone(row.hygiene_decision_id)
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=enrollment_id).status, Enrollment.Status.DROPPED)
            page = journal_history.history_page(offering=self.offering)
        self.assertEqual(page["entries"][0]["kind"], "roster-removal")
        self.assertIn("G3-ə keçdi", page["entries"][0]["kind_label"])

    def test_journal_page_renders_reason_panel(self):
        client = self._client(self.coordinator)
        self._add_guest(client)
        page = client.get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertContains(page, "data-jgs-remove-panel")
        self.assertContains(page, 'id="jgs-removal-reason"')


@override_settings(UNIVERSITY_MODE=True)
class JournalRemovalsSectionTest(_ExemptBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Fizika kafedrası", slug="se-chair", unit_type=OrgUnitType.CHAIR
            )
            cls.physics.chair_unit = cls.chair
            cls.physics.save(update_fields=["chair_unit"])
            cls.other_chair = OrgUnit.objects.create(
                organization=cls.org, name="Kimya kafedrası", slug="se-chair2", unit_type=OrgUnitType.CHAIR
            )

    def setUp(self):
        super().setUp()
        response = self._exempt(removal_reason="subject_substitution", reason="Sənəd №7")
        self.assertEqual(response.status_code, 200, response.content)

    def _page(self, **params):
        with bypass_rls():
            return journal_removal_read.page(self.org, journal_removal_read.parse_filters(params))

    def test_visible_for_rim_head_with_rows(self):
        client = self._client(self.rim)
        page = client.get(reverse("accounts:profile"), {"section": SECTION})
        self.assertContains(page, f'data-profile-section-panel="{SECTION}"')
        self.assertContains(page, f'data-section="{SECTION}"')
        fragment = client.get(reverse("accounts:profile_section_fragment", args=[SECTION]))
        self.assertEqual(fragment.status_code, 200)
        html = fragment.json()["html"]
        self.assertIn("data-jrm-root", html)
        self.assertIn("Sənəd №7", html)
        self.assertIn("Fənn əvəzlənməsi (sənəd təqdim edib)", html)
        self.assertIn(reverse("accounts:journal_removals_export"), html)

    def test_hidden_and_refused_for_teacher(self):
        client = self._client(self.teacher)
        page = client.get(reverse("accounts:profile"), {"section": SECTION})
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, f'data-profile-section-panel="{SECTION}"')
        self.assertNotContains(page, f'data-section="{SECTION}"')
        self.assertNotContains(page, "Sənəd №7")
        export = client.get(reverse("accounts:journal_removals_export"))
        self.assertEqual(export.status_code, 403)

    def test_export_is_xlsx_and_audited(self):
        response = self._client(self.rim).get(
            reverse("accounts:journal_removals_export"), {"jr_reason": "subject_substitution"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertTrue(response.content.startswith(b"PK"))
        with bypass_rls():
            self.assertTrue(AuditLog.objects.filter(resource_type="accounts.journal_removals", user=self.rim).exists())

    def test_filters(self):
        today = timezone.localdate()
        self.assertEqual(self._page()["total"], 1)
        self.assertEqual(self._page(jr_reason="subject_substitution")["total"], 1)
        self.assertEqual(self._page(jr_reason="suspension")["total"], 0)
        self.assertEqual(self._page(jr_reason="bogus")["total"], 1)  # naməlum dəyər — süzgəcsiz
        self.assertEqual(self._page(jr_action="guest_remove")["total"], 0)
        self.assertEqual(self._page(jr_from=today.isoformat(), jr_to=today.isoformat())["total"], 1)
        self.assertEqual(self._page(jr_from=(today + datetime.timedelta(days=1)).isoformat())["total"], 0)
        self.assertEqual(self._page(jr_to=(today - datetime.timedelta(days=1)).isoformat())["total"], 0)
        self.assertEqual(self._page(jr_faculty=str(self.faculty.pk))["total"], 1)
        self.assertEqual(self._page(jr_faculty=str(self.far_faculty.pk))["total"], 0)
        self.assertEqual(self._page(jr_chair=str(self.chair.pk))["total"], 1)
        self.assertEqual(self._page(jr_chair=str(self.other_chair.pk))["total"], 0)
        self.assertEqual(self._page(jr_teacher="se_teacher")["total"], 1)
        self.assertEqual(self._page(jr_teacher="başqa")["total"], 0)
        self.assertEqual(self._page(jr_q="se_stu")["total"], 1)
        self.assertEqual(self._page(jr_q="se_mate")["total"], 0)
        row = self._page()["rows"][0]
        self.assertEqual(
            (row["reason"], row["state"], row["subject_code"]), ("subject_substitution", "active", "FIZ101")
        )

    def test_reason_counts_ignore_reason_filter(self):
        with bypass_rls():
            counts = journal_removal_read.reason_counts(
                self.org, journal_removal_read.parse_filters({"jr_reason": "suspension"})
            )
        by_value = {item["value"]: item["count"] for item in counts}
        self.assertEqual(by_value["subject_substitution"], 1)
        self.assertEqual(by_value["suspension"], 0)

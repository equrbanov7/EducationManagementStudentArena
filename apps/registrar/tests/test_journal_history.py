"""«Dəyişiklik tarixçəsi» paneli (UNEC müqayisəsi P1-3, 2026-09-25) — JSON endpoint + səhifə qoşulması."""

import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import grade_audit, gradebook, journal_history, services
from apps.registrar.models import Enrollment, LessonKind, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalHistoryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jh_owner", "jh_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JH Univ",
                slug="jh-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="jh-g1", unit_type=OrgUnitType.GROUP
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
            cls.other_subject = Subject.objects.create(organization=cls.org, code="CS102", name="Alqoritmlər")
            cls.teacher = User.objects.create_user(
                "jh_teacher", "jh_teacher@qku.edu.az", "pw", first_name="Aygün", last_name="Məmmədova"
            )
            cls.other_teacher = User.objects.create_user("jh_other", "jh_other@qku.edu.az", "pw")
            cls.student = User.objects.create_user(
                "jh_student", "jh_student@qku.edu.az", "pw", first_name="Əli", last_name="İsmayılov"
            )
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
            cls.other_offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.other_subject, period=cls.period, group=cls.group
            )
            cls.other_offering.instructor = cls.teacher
            cls.other_offering.save(update_fields=["instructor"])
            cls.enrollment = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.offering)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _url(self, offering=None, **params):
        url = reverse("registrar:journal_history", args=[(offering or self.offering).id])
        if params:
            url += "?" + "&".join(f"{key}={value}" for key, value in params.items())
        return url

    def _log(self, *, item="2024-10-01 · Seminar", old="—", new="iə 8", offering=None, student=None, kind="mark"):
        with bypass_rls():
            grade_audit.log_grade_changes(
                offering=offering or self.offering,
                by_user=self.teacher,
                kind=kind,
                changes=[{"student": student or "İsmayılov Əli", "item": item, "old": old, "new": new}],
            )

    # ── Məzmun ───────────────────────────────────────────────────────────────

    def test_teacher_sees_real_saves_newest_first(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
            )
            for score in (8, 9):
                gradebook.save_marks(
                    enforce_day=False,
                    offering=self.offering,
                    entries=[
                        {
                            "lesson_id": lesson.id,
                            "enrollment_id": self.enrollment.id,
                            "status": "present",
                            "score": score,
                        }
                    ],
                    by_user=self.teacher,
                )
        resp = self._client(self.teacher).get(self._url())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["entries"]), 2)
        newest, oldest = data["entries"]
        self.assertEqual(newest["rows"][0]["old"], "iə 8")
        self.assertEqual(newest["rows"][0]["new"], "iə 9")
        self.assertEqual(oldest["rows"][0]["old"], "—")
        row = newest["rows"][0]
        self.assertEqual(row["student"], "Əli İsmayılov")
        self.assertEqual(row["date"], "2024-10-01")
        self.assertFalse(row["lesson_level"])
        self.assertEqual(newest["user"], "Aygün Məmmədova")
        self.assertEqual(newest["group"], "mark")
        self.assertEqual(newest["count"], 1)
        self.assertTrue(newest["kind_label"])
        self.assertRegex(newest["time"], r"^\d{2}:\d{2}$")
        # Süzgəc seçimləri — açılışın dərs tarixləri (yalnız ilk, süzgəcsiz səhifədə).
        self.assertEqual(data["dates"][0]["value"], "2024-10-01")
        self.assertEqual(data["total"], 2)

    def test_pagination_after_twenty_entries(self):
        for index in range(25):
            self._log(new=f"iə {index % 10}")
        client = self._client(self.teacher)
        first = client.get(self._url()).json()
        self.assertEqual(len(first["entries"]), journal_history.PAGE_SIZE)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["total"], 25)
        self.assertEqual(first["next_offset"], 20)
        second = client.get(self._url(offset=first["next_offset"])).json()
        self.assertEqual(len(second["entries"]), 5)
        self.assertFalse(second["has_more"])
        self.assertNotIn("total", second)
        ids = [entry["id"] for entry in first["entries"] + second["entries"]]
        self.assertEqual(len(ids), len(set(ids)), "səhifələr üst-üstə düşməməlidir")

    def test_limit_is_clamped(self):
        for _ in range(3):
            self._log()
        data = self._client(self.teacher).get(self._url(limit=5000, offset="abc")).json()
        self.assertEqual(len(data["entries"]), 3)
        self.assertEqual(data["offset"], 0)

    def test_other_offering_entries_stay_out(self):
        self._log(offering=self.other_offering, new="başqa fənn")
        self._log(new="bu fənn")
        data = self._client(self.teacher).get(self._url()).json()
        self.assertEqual([entry["rows"][0]["new"] for entry in data["entries"]], ["bu fənn"])

    def test_impersonation_stamp_is_metadata_not_a_row(self):
        from core.audit import IMPERSONATION_KEY

        with bypass_rls():
            grade_audit.log_grade_changes(
                offering=self.offering,
                by_user=self.teacher,
                kind="mark",
                changes=[
                    {"student": "İsmayılov Əli", "item": "2024-10-01 · Seminar", "old": "—", "new": "qb"},
                    {IMPERSONATION_KEY: {"id": "1", "username": "rim.rehber", "mode": "full"}},
                ],
            )
        entry = self._client(self.teacher).get(self._url()).json()["entries"][0]
        self.assertEqual(entry["count"], 1)
        self.assertEqual(len(entry["rows"]), 1)
        self.assertEqual(entry["impersonated_by"], "rim.rehber")

    def test_enrollment_labels_resolve_to_student_names(self):
        self._log(student=f"enrollment:{self.enrollment.id}", item="Sərbəst iş · Mövzu 1", old="1", new="0")
        self._log(student="enrollment:not-a-uuid", item="Kurs işi")
        entries = self._client(self.teacher).get(self._url()).json()["entries"]
        students = {entry["rows"][0]["student"] for entry in entries}
        self.assertIn("Əli İsmayılov", students)
        self.assertIn("enrollment:not-a-uuid", students)  # pozuq etiket 500 vermir, olduğu kimi qalır

    def test_lesson_level_rows_are_flagged(self):
        # Dərs düzəlişində «student» sahəsi dərsin özüdür, «item» isə sahənin adı.
        self._log(student="2024-10-02 · Mühazirə", item="Mövzu", old="A", new="B", kind="lesson-correction")
        self._log(student="—", item="2024-10-03 · Seminar", old="dərs sütunu", new="silindi")
        entries = self._client(self.teacher).get(self._url()).json()["entries"]
        by_new = {entry["rows"][0]["new"]: entry for entry in entries}
        correction = by_new["B"]
        self.assertTrue(correction["rows"][0]["lesson_level"])
        self.assertEqual(correction["rows"][0]["date"], "2024-10-02")
        self.assertEqual(correction["group"], "correction")
        self.assertTrue(by_new["silindi"]["rows"][0]["lesson_level"])

    def test_date_filter_runs_on_the_server(self):
        self._log(item="2024-10-01 · Seminar", new="birinci")
        self._log(item="2024-10-08 · Seminar", new="ikinci")
        client = self._client(self.teacher)
        data = client.get(self._url(date="2024-10-01")).json()
        self.assertEqual([entry["rows"][0]["new"] for entry in data["entries"]], ["birinci"])
        self.assertEqual(data["date"], "2024-10-01")
        self.assertNotIn("dates", data)
        # Yararsız tarix → süzgəcsiz (səssiz), 500 deyil.
        loose = client.get(self._url(date="31-31-2024")).json()
        self.assertEqual(len(loose["entries"]), 2)

    def test_query_count_is_flat(self):
        client = self._client(self.teacher)
        for _ in range(3):
            self._log()
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(client.get(self._url()).status_code, 200)
        for _ in range(17):
            self._log(student=f"enrollment:{self.enrollment.id}")
        with CaptureQueriesContext(connection) as large:
            self.assertEqual(client.get(self._url()).status_code, 200)
        # Böyük səhifədə +1: «daha çox» varmı → ümumi say, +1: enrollment etiketlərinin həlli.
        self.assertLessEqual(len(large.captured_queries), len(small.captured_queries) + 2)

    # ── Giriş ────────────────────────────────────────────────────────────────

    def test_student_never_sees_history(self):
        self._log()
        resp = self._client(self.student).get(self._url())
        self.assertEqual(resp.status_code, 404)

    def test_other_teacher_is_refused(self):
        self._log()
        resp = self._client(self.other_teacher).get(self._url())
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_is_redirected_to_login(self):
        resp = Client().get(self._url())
        self.assertEqual(resp.status_code, 302)

    def test_post_is_not_allowed(self):
        resp = self._client(self.teacher).post(self._url())
        self.assertEqual(resp.status_code, 405)

    # ── Jurnal səhifəsi ──────────────────────────────────────────────────────

    def test_journal_page_has_button_and_drawer_without_audit_query(self):
        self._log()
        client = self._client(self.teacher)
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-jhist-open")
        self.assertContains(resp, 'data-url="%s"' % reverse("registrar:journal_history", args=[self.offering.id]))
        self.assertContains(resp, "registrar/js/journal_history.js")
        self.assertNotIn("grade_history", resp.context)
        # Tarixçə panel açılanda oxunur — səhifə yüklənəndə audit cədvəlinə sorğu yoxdur.
        audit_reads = [q["sql"] for q in ctx.captured_queries if "audit_auditlog" in q["sql"] and "SELECT" in q["sql"]]
        self.assertEqual(audit_reads, [])

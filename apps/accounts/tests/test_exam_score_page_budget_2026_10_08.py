"""Tutum testi 2026-10-08 — «İmtahan balı» səhifəsinin (kollokvium/final balı) sorğu büdcəsi.

Yük testi (10 app × 1 CPU, 300 müəllim): «jf exam-score page» p50 3.8 s, «after save»
p50 3.8 s, «save» p50 1.2 s, app CPU 100 %. Kök səbəblər və qıfıllanan müqavilə:

* **GET** — sorğu sayı qrupun ölçüsündən asılı deyil (5 və 30 tələbə, həm boş siyahı,
  həm yadda saxlamadan sonrakı tarixçəli siyahı); S1..S10 xanalarının select-ində YALNIZ
  «—» + seçilmiş dəyər render olunur (`data-max=""` — 0..max variantlarını JS qurur);
  müəllim seçiciləri təşkilatın bütün üzvlüklərini oxumur (rol-əvvəl sorğu);
* **POST** — toplu yazı: sorğu sayı yazılan sətirlərin sayından asılı deyil;
* **Dərin keçid** — ``?ese_offering=`` (``ese_group`` olmadan; yük testinin və jurnal
  keçidinin URL-i) həmin açılışı açır, siyahının birinci qrupunu yox.
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

SMALL, BIG = 5, 30


@override_settings(UNIVERSITY_MODE=True)
class ExamScorePageBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("espb_owner", "espb_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ESPB Univ",
                slug="espb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
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
            program = Program.objects.create(organization=cls.org, code="ESPB", name="P", absence_limit_percent=25)
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2024)
            subject = Subject.objects.create(organization=cls.org, code="ESPB1", name="Fənn")
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=curriculum, subject=subject, semester_number=1
            )
            cls.center = User.objects.create_user("espb_center", "espb_center@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.center,
                organization=cls.org,
                role=cls.org.roles.get(name="exam_center_head"),
                is_primary=True,
                is_active=True,
            )
            teacher_role = cls.org.roles.get(name="teacher")
            student_role = cls.org.roles.get(name="student")
            cls.offerings = {}
            for size in (SMALL, BIG):
                group = OrgUnit.objects.create(
                    organization=cls.org, name=f"ESPB-{size:02d}", slug=f"espb-g{size}", unit_type=OrgUnitType.GROUP
                )
                for index in range(size):
                    student = User.objects.create_user(
                        f"espb_{size}_{index:02d}",
                        f"espb_{size}_{index:02d}@qku.edu.az",
                        "pw",
                        last_name=f"S{index:02d}",
                    )
                    Membership.objects.create(
                        user=student, organization=cls.org, role=student_role, is_primary=True, is_active=True
                    )
                    record = StudentAcademicRecord.objects.create(
                        organization=cls.org,
                        student=student,
                        program=program,
                        curriculum=curriculum,
                        group=group,
                        admission_year=2024,
                    )
                    services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
                teacher = User.objects.create_user(f"espb_t{size}", f"espb_t{size}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=teacher, organization=cls.org, role=teacher_role, is_primary=True, is_active=True
                )
                offering = CourseOffering.objects.get(organization=cls.org, period=cls.period, group=group)
                offering.instructor = teacher
                offering.lesson_hours = 60
                offering.save(update_fields=["instructor", "lesson_hours"])
                cls.offerings[size] = (group, offering)

    def _client(self):
        client = Client()
        client.force_login(self.center)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _page_params(self, size):
        group, offering = self.offerings[size]
        return {"section": "exam-score-entry", "ese_group": str(group.id), "ese_offering": str(offering.id)}

    def _get(self, client, size):
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(reverse("accounts:profile"), self._page_params(size))
        self.assertEqual(resp.status_code, 200)
        return len(ctx.captured_queries), resp.content.decode()

    def _enrollment_ids(self, size):
        with bypass_rls():
            return [str(pk) for pk in self.offerings[size][1].enrollments.order_by("id").values_list("id", flat=True)]

    def _post(self, client, size, enrollment_ids, **extra):
        group, offering = self.offerings[size]
        data = {
            "action": "save_scores",
            "offering_id": str(offering.id),
            "next": reverse("accounts:profile") + "?section=exam-score-entry",
            "exam_kind": "written",
            "question_count": "5",
            **{f"q__{eid}__1": "7" for eid in enrollment_ids},
            **{f"q__{eid}__2": "5" for eid in enrollment_ids},
            **{f"score__{eid}": "" for eid in enrollment_ids},
            **extra,
        }
        with CaptureQueriesContext(connection) as ctx:
            resp = client.post(reverse("accounts:exam_score_entry"), data)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("ese_saved=1", resp["Location"])
        return len(ctx.captured_queries)

    def test_get_and_post_budgets_do_not_depend_on_group_size(self):
        client = self._client()
        # İsitmə: hər iki açılışın sxemi / keşlər (ölçülər eyni vəziyyətdən başlasın).
        for size in (SMALL, BIG):
            self._get(client, size)
            self._post(client, size, self._enrollment_ids(size)[:1])

        small_get, _ = self._get(client, SMALL)
        big_get, html = self._get(client, BIG)
        self.assertEqual(big_get, small_get, f"GET: {SMALL} tələbə → {small_get}, {BIG} → {big_get}")

        small_post = self._post(client, SMALL, self._enrollment_ids(SMALL)[1:])
        big_post = self._post(client, BIG, self._enrollment_ids(BIG)[1:])
        self.assertEqual(big_post, small_post, f"POST: {SMALL - 1} sətir → {small_post}, {BIG - 1} → {big_post}")
        # Kəskin deqradasiya tavanı (əvvəl 25 sətirlik POST ≈ 1 190 sorğu idi).
        self.assertLessEqual(big_post, 60)

        small_after, _ = self._get(client, SMALL)
        big_after, html = self._get(client, BIG)
        self.assertEqual(big_after, small_after, f"after save: {SMALL} → {small_after}, {BIG} → {big_after}")

        # Yadda saxlanmış sual balı hazır toggle-da və select-in YEGANƏ dolu variantıdır.
        enrollment_id = self._enrollment_ids(BIG)[3]
        cell = re.search(rf'<select[^>]*name="q__{enrollment_id}__1"[^>]*>(.*?)</select>', html, re.S)
        self.assertIsNotNone(cell)
        self.assertEqual(cell.group(1), '<option value="">—</option><option value="7" selected>7</option>')
        self.assertIn(f'name="q__{enrollment_id}__1" aria-label="S1 — ', html)
        tbody = html[html.index("<tbody>") : html.index("</tbody>")]
        self.assertEqual(tbody.count("<option"), BIG * 10 + BIG * 2)  # «—» hər xanada + 2 dolu sual
        self.assertIn('data-ese-qcell="6" hidden', tbody)
        self.assertIn('data-max=""', tbody)

    def test_offering_deep_link_selects_its_group(self):
        """``?ese_offering=`` (qrupsuz — jurnal / yük testi keçidi) həmin açılışı açır, birinci qrupu yox."""
        client = self._client()
        group, offering = self.offerings[BIG]
        for mode in ("group", "subject"):
            resp = client.get(
                reverse("accounts:profile"),
                {"section": "exam-score-entry", "ese_mode": mode, "ese_offering": str(offering.id)},
            )
            self.assertContains(resp, f'name="offering_id" value="{offering.id}"')
        resp = client.get(
            reverse("accounts:profile"), {"section": "exam-score-entry", "ese_offering": str(offering.id)}
        )
        self.assertContains(resp, f"ese_group={group.id}")
        # Açıq ``ese_group`` üstündür; yanlış / yad açılış id-si defolta düşür (500 yox).
        small_group, small_offering = self.offerings[SMALL]
        resp = client.get(
            reverse("accounts:profile"),
            {"section": "exam-score-entry", "ese_group": str(small_group.id), "ese_offering": str(offering.id)},
        )
        self.assertContains(resp, f'name="offering_id" value="{small_offering.id}"')
        for bogus in ("not-a-uuid", "00000000-0000-0000-0000-000000000000"):
            resp = client.get(reverse("accounts:profile"), {"section": "exam-score-entry", "ese_offering": bogus})
            self.assertEqual(resp.status_code, 200)

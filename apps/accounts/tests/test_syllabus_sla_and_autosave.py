"""Siyahı ekranının SLA KPI-ı və autosave-in 409 konflikt cavabı.

* **18-ci ekran** (`docs/design/handoff_full/README.md` §5) KPI zolağında
  «SLA-nı keçib» kartı olmalıdır və hədd SİYASƏTDƏN gəlməlidir
  (``syllabus.sla_days``, default 5 — README §10.4), kodda hardcode YOX.
* **§8/10:** autosave konfliktində istifadəçi dəyişikliyi SƏSSİZCƏ İTMİR —
  server 409 + serverdəki ``revision`` qaytarır, redaktor isə müqayisə
  dialoqunu açır.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.syllabus import services
from apps.syllabus.constants import SectionKey
from apps.syllabus.models import SyllabusVersion
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)

User = get_user_model()

PASSWORD = "StrongPass123!"
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("syl-sla")
        cls.teacher = User.objects.create_user("syl_sla_teacher", "syl_sla_teacher@x.test", PASSWORD)
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS, level=60)
        cls.stack = make_academic_stack(cls.org, code="SLA101")
        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)
        actor = services.resolve_actor(cls.teacher, cls.org)
        cls.syllabus, cls.version = services.create_draft(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            actor=actor,
            offering=cls.offering,
            program=cls.stack["program"],
            chair_unit=cls.stack["chair"],
            author=cls.teacher,
            plan_hours=dict(PLAN_HOURS),
        )
        for section_id, data in complete_section_data().items():
            if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
                continue
            services.save_section(version=cls.version, section_id=section_id, data=data, actor=actor)

    def _client(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class SyllabusListSlaKpiTest(_Base):
    def _section(self, **params):
        from apps.accounts.views.syllabus.section import build_syllabus_list_section

        request = self._request(params)
        return build_syllabus_list_section(request, organization=self.org)["syllabus_list_section"]

    def _request(self, params):
        from django.test import RequestFactory

        request = RequestFactory().get("/accounts/profile/", params)
        request.user = self.teacher
        request.org_permissions = list(TEACHER_PERMS)
        request.organization = self.org
        return request

    def _submit_and_backdate(self, days: int):
        actor = services.resolve_actor(self.teacher, self.org)
        version = services.submit(version=self.version, actor=actor)
        stamp = timezone.now() - timezone.timedelta(days=days)
        SyllabusVersion.objects.filter(pk=version.pk).update(submitted_at=stamp)
        return version

    def test_the_kpi_row_carries_the_sla_card_with_the_policy_threshold(self):
        keys = [card["key"] for card in self._section()["kpis"]]
        self.assertIn("sla", keys)
        card = next(card for card in self._section()["kpis"] if card["key"] == "sla")
        # Qeyd mətni həddi GÖSTƏRİR — rəqəm siyasətdən gəlir (default 5).
        self.assertIn("5", str(card["note"]))

    def test_a_submission_older_than_the_sla_is_counted(self):
        self._submit_and_backdate(9)
        card = next(card for card in self._section()["kpis"] if card["key"] == "sla")
        self.assertEqual(card["value"], 1)

    def test_a_fresh_submission_is_not_counted(self):
        self._submit_and_backdate(1)
        card = next(card for card in self._section()["kpis"] if card["key"] == "sla")
        self.assertEqual(card["value"], 0)

    def test_the_organization_policy_moves_the_threshold(self):
        self._submit_and_backdate(4)
        self.assertEqual(next(c for c in self._section()["kpis"] if c["key"] == "sla")["value"], 0)
        self.org.settings = {"syllabus": {"sla_days": 2}}
        self.org.save(update_fields=["settings"])
        card = next(card for card in self._section()["kpis"] if card["key"] == "sla")
        self.assertEqual(card["value"], 1)
        self.assertIn("2", str(card["note"]))

    def test_the_sla_filter_narrows_the_table_to_the_overdue_rows(self):
        self._submit_and_backdate(9)
        section = self._section(status="sla")
        self.assertEqual(len(section["rows"]), 1)
        self.assertEqual(section["rows"][0]["id"], str(self.syllabus.pk))


class SyllabusAutosaveConflictTest(_Base):
    def _save(self, client, *, revision, text="Yeni məqsəd mətni"):
        return client.post(
            reverse("accounts:syllabus_section_save", kwargs={"version_id": str(self.version.pk)}),
            data=json.dumps(
                {
                    "section": SectionKey.DESC.value,
                    "revision": revision,
                    "data": {"description": "T" * 130, "goal": text + "M" * 70},
                }
            ),
            content_type="application/json",
        )

    def _revision(self) -> int:
        return self.version.sections.get(section_id=SectionKey.DESC.value).revision

    def test_a_stale_revision_returns_409_with_the_server_revision(self):
        client = self._client()
        stale = self._revision() - 1

        response = self._save(client, revision=stale)

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "section.conflict")
        # Redaktor müqayisə dialoqunu məhz bu rəqəmlə açır.
        self.assertEqual(payload["revision"], self._revision())
        self.assertTrue(payload["error"])

    def test_the_current_revision_saves_and_bumps_the_counter(self):
        client = self._client()
        before = self._revision()

        response = self._save(client, revision=before)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["revision"], before + 1)

    def test_an_assessment_split_outside_the_policy_is_refused_by_the_endpoint(self):
        client = self._client()
        response = client.post(
            reverse("accounts:syllabus_section_save", kwargs={"version_id": str(self.version.pk)}),
            data=json.dumps({"section": SectionKey.ASSESS.value, "data": {"midterm": 80, "project": 80}}),
            content_type="application/json",
        )
        # Validasiya xətası kliyent xətasıdır (QA 2026-09-05 SYLLABUS-06): 400, icazə 403 deyil.
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "assess.split_mismatch")


class SyllabusInputGuardTest(_Base):
    """QA 2026-09-05 SYLLABUS-01/02: dublikat yaratma 500 (IntegrityError), ixtiyari JSON forması
    autosave-də qəbul olunub redaktoru 500 ilə kilidləyirdi."""

    def test_second_create_for_the_same_offering_returns_409_not_500(self):
        client = self._client()
        response = client.post(
            reverse("accounts:syllabus_action"),
            data=json.dumps({"action": "create", "offering": str(self.offering.pk)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["code"], "syllabus.exists")
        self.assertEqual(payload["syllabus"], str(self.syllabus.pk))

    def test_invalid_week_row_shape_is_refused_with_400(self):
        client = self._client()
        revision = self.version.sections.get(section_id=SectionKey.WEEK.value).revision
        response = client.post(
            reverse("accounts:syllabus_section_save", kwargs={"version_id": str(self.version.pk)}),
            data=json.dumps(
                {
                    "section": SectionKey.WEEK.value,
                    "revision": revision,
                    "data": {"rows": [1, None, {"topic": {"a": 1}}]},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["code"], "section.invalid_shape")
        self.assertEqual(payload["field"], "rows[0]")
        # Redaktor bundan sonra da açılır (məzmun toxunulmaz qalıb).
        editor = client.get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "syllabus-editor"})
            + f"?version={self.version.pk}",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(editor.status_code, 200)

    def test_oversized_description_is_refused_with_400(self):
        client = self._client()
        revision = self.version.sections.get(section_id=SectionKey.DESC.value).revision
        response = client.post(
            reverse("accounts:syllabus_section_save", kwargs={"version_id": str(self.version.pk)}),
            data=json.dumps(
                {"section": SectionKey.DESC.value, "revision": revision, "data": {"description": "B" * 30000}}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "section.too_long")

"""Sahib 2026-10-25: «Bu tip məsələləri tənzimləmək olsun» — kafedra plan saatını (BİR qrup üçün) əl ilə düzəldir.

* kafedra müdiri (``syllabus.approve``, kafedra əhatəsi) düzəldir — dosyenin düzəlişi + açıq qaralama (tamamlanma
  ilə) + təsdiqlənmiş versiyanın YALNIZ plan sahəsi; həftəlik bölgüyə toxunulmur; audit yazılır;
* başqa kafedranın müdiri və müəllim (müəllif) düzəldə bilmir — 403;
* düzəliş rəsmi saatdır: müəllimin «plan_hours» əməli 409, redaktor müəllifin qaralamasını ona uyğunlaşdırır;
* «Avtomatik hesaba qayıt» düzəlişi silir və versiyaları hesablanmış saata qaytarır;
* forma yalnız icazəlinin redaktorunda görünür.
"""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import OrgUnit
from apps.syllabus import services
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from core.constants import OrgUnitType, RoleScopeType

User = get_user_model()

AUTO = {"lecture": 45, "seminar": 60}  # yükün cəmi kimi yazılmış (105)
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
_PATCH = "apps.registrar.public.plan_hours_for_offering"


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


class PlanOverrideTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("syl-override")
        faculty = OrgUnit.objects.create(
            organization=cls.org, name="Fakültə", slug="syl-ovr-fac", unit_type=OrgUnitType.FACULTY
        )
        cls.stack = make_academic_stack(cls.org, code="OVR101")
        other = make_academic_stack(cls.org, code="OVR202")
        for chair in (cls.stack["chair"], other["chair"]):
            chair.parent = faculty
            chair.save()
        cls.teacher = User.objects.create_user("ovr_teacher", "ovr_teacher@x.test", "StrongPass123!")
        cls.chair = User.objects.create_user("ovr_chair", "ovr_chair@x.test", "StrongPass123!")
        cls.stranger = User.objects.create_user("ovr_chair_b", "ovr_chair_b@x.test", "StrongPass123!")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS, level=60)
        activate_member(
            cls.org,
            cls.chair,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        activate_member(
            cls.org,
            cls.stranger,
            "chair_head_b",
            permissions=CHAIR_PERMS,
            scope_unit=other["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        offering = make_offering(cls.org, cls.stack, cls.teacher)
        actor = services.resolve_actor(cls.teacher, cls.org)
        cls.syllabus, cls.version = services.create_draft(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            actor=actor,
            offering=offering,
            program=cls.stack["program"],
            chair_unit=cls.stack["chair"],
            author=cls.teacher,
            plan_hours=AUTO,
        )

    def _post(self, user, **payload):
        return _client(user, self.org).post(
            reverse("accounts:syllabus_plan_hours_override", args=[self.version.pk]),
            json.dumps(payload),
            content_type="application/json",
        )

    def _editor(self, user) -> str:
        response = _client(user, self.org).get(
            reverse("accounts:profile"), {"section": "syllabus-editor", "version": str(self.version.pk)}
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    @mock.patch(_PATCH, return_value=AUTO)
    def test_chair_sets_override_on_draft_and_approved(self, _plan):
        week = SyllabusSection.objects.get(version=self.version, section_id="week")
        week.data = {"rows": [{"topic": "Giriş", "lecture": 2, "seminar": 2}]}
        week.save(update_fields=["data"])
        approved = SyllabusVersion.objects.create(
            organization=self.org,
            syllabus=self.syllabus,
            major=1,
            minor=9,
            status="approved",
            approval_source="migration",
            locked_at=timezone.now(),
            plan_hours=AUTO,
        )
        response = self._post(self.chair, lecture=45, seminar=30)
        self.assertEqual(response.status_code, 200, response.content)
        self.syllabus.refresh_from_db()
        self.version.refresh_from_db()
        approved.refresh_from_db()
        week.refresh_from_db()
        self.assertEqual(self.syllabus.plan_hours_override, {"lecture": 45, "seminar": 30})
        self.assertEqual(self.version.plan_hours, {"lecture": 45, "seminar": 30})
        self.assertEqual(approved.plan_hours, {"lecture": 45, "seminar": 30})
        self.assertEqual(approved.status, "approved")
        self.assertEqual(week.data["rows"], [{"topic": "Giriş", "lecture": 2, "seminar": 2}])
        self.assertTrue(AuditLog.objects.filter(resource_type="syllabus.plan_hours").exists())

    @mock.patch(_PATCH, return_value=AUTO)
    def test_teacher_and_other_chair_are_denied(self, _plan):
        self.assertEqual(self._post(self.teacher, lecture=45, seminar=30).status_code, 403)
        self.assertEqual(self._post(self.stranger, lecture=45, seminar=30).status_code, 403)
        self.syllabus.refresh_from_db()
        self.assertEqual(self.syllabus.plan_hours_override, {})

    @mock.patch(_PATCH, return_value=AUTO)
    def test_override_is_official_for_the_teacher(self, _plan):
        self._post(self.chair, lecture=45, seminar=30)
        response = _client(self.teacher, self.org).post(
            reverse("accounts:syllabus_action"),
            json.dumps({"action": "plan_hours", "version": str(self.version.pk), "lecture": 90}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        # Müəllifin redaktoru düzəlişi saxlayır (yük cəminə qaytarmır).
        self._editor(self.teacher)
        self.version.refresh_from_db()
        self.assertEqual(self.version.plan_hours, {"lecture": 45, "seminar": 30})

    @mock.patch(_PATCH, return_value={"lecture": 45, "seminar": 30})
    def test_reset_returns_to_automatic_hours(self, _plan):
        Syllabus.objects.filter(pk=self.syllabus.pk).update(plan_hours_override={"lecture": 30, "seminar": 15})
        response = self._post(self.chair, reset=True)
        self.assertEqual(response.status_code, 200, response.content)
        self.syllabus.refresh_from_db()
        self.version.refresh_from_db()
        self.assertEqual(self.syllabus.plan_hours_override, {})
        self.assertEqual(self.version.plan_hours, {"lecture": 45, "seminar": 30})

    @mock.patch(_PATCH, return_value=AUTO)
    def test_bad_payloads(self, _plan):
        self.assertEqual(self._post(self.chair).status_code, 400)
        self.assertEqual(self._post(self.chair, lecture=-5).status_code, 400)
        self.assertEqual(self._post(self.chair, lecture="x").status_code, 400)

    @mock.patch(_PATCH, return_value=AUTO)
    def test_form_visible_only_to_allowed(self, _plan):
        self.assertIn("syl-planhours--override", self._editor(self.chair))
        self.assertNotIn("syl-planhours--override", self._editor(self.teacher))

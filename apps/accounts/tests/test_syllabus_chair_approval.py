"""HTTP səthi — sillabusu TƏSDİQ EDƏN kafedra müdiridir (sahibin qərarı 2026-09-03).

`apps/syllabus/tests/test_chair_approval_authority.py` domen qatını kilidləyir;
burada eyni qayda **HTTP status kodları** səviyyəsində qorunur, çünki UI-nın
davranışı məhz oradan asılıdır:

* dekan qərar endpoint-ində **403** alır (409 «yenidən cəhd et» demək olardı);
* öz kafedrasının müdiri **200** alır və versiya təsdiqlənir;
* BAŞQA kafedranın müdiri əhatə qapısında **404** alır (mövcudluq sızmır);
* RİM (org-wide) override-i işləyir;
* dekanın gördüyü növbə YALNIZ OXUNUR — düymə yoxdur, səbəbi isə ekranda
  AÇIQ yazılır («Təsdiq kafedra müdirinin səlahiyyətindədir»).
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import OrgUnitType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]
DEAN_PERMS = ["syllabus.view", "syllabus.review"]

#: Ekranda görünməli olan açıq qeyd (sahibin sözləri ilə).
READ_ONLY_NOTE = "Təsdiq kafedra müdirinin səlahiyyətindədir"


def _submit(org, stack, teacher):
    actor = services.resolve_actor(teacher, org)
    offering = make_offering(org, stack, teacher)
    _syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        author=teacher,
        plan_hours=dict(PLAN_HOURS),
    )
    for section_id, data in complete_section_data().items():
        if section_id in {"prev", "send"}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    return services.submit(version=version, actor=actor)


class SyllabusChairApprovalHttpTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("syl-chair-http")
        cls.faculty = OrgUnit.objects.create(
            organization=cls.org,
            name="Fakültə",
            slug=f"{cls.org.slug}-faculty",
            unit_type=OrgUnitType.FACULTY,
        )
        cls.stack_a = make_academic_stack(cls.org, code="CHA101")
        cls.stack_b = make_academic_stack(cls.org, code="CHB202")
        for stack in (cls.stack_a, cls.stack_b):
            chair = stack["chair"]
            chair.parent = cls.faculty
            chair.save()

        cls.teacher = User.objects.create_user("cha_teacher", "cha_teacher@x.test", PASSWORD)
        cls.chair_a = User.objects.create_user("cha_chair_a", "cha_chair_a@x.test", PASSWORD)
        cls.chair_b = User.objects.create_user("cha_chair_b", "cha_chair_b@x.test", PASSWORD)
        cls.dean = User.objects.create_user("cha_dean", "cha_dean@x.test", PASSWORD)
        cls.rim = User.objects.create_user("cha_rim", "cha_rim@x.test", PASSWORD)

        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        activate_member(
            cls.org,
            cls.chair_a,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack_a["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        activate_member(
            cls.org,
            cls.chair_b,
            "chair_head_b",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack_b["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        activate_member(
            cls.org,
            cls.dean,
            "dean",
            permissions=DEAN_PERMS,
            scope_unit=cls.faculty,
            level=80,
            scope_type=RoleScopeType.UNIT,
        )
        activate_member(cls.org, cls.rim, "ikt_rehber", permissions=["syllabus.*"], level=88)

    def setUp(self):
        self.version = _submit(self.org, self.stack_a, self.teacher)

    def _client(self, user) -> Client:
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _decide(self, user, action, version=None, **extra):
        payload = {"action": action, **extra}
        return self._client(user).post(
            reverse("accounts:syllabus_decision", kwargs={"version_id": str((version or self.version).pk)}),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _html(self, user) -> str:
        response = self._client(user).get(reverse("accounts:profile"), {"section": "syllabus-review"})
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    # ── Dekan: oxuyur, qərar vermir ────────────────────────────────────────

    def test_dean_gets_403_on_every_decision(self):
        reason = "Qiymətləndirmə strukturu tələblərə uyğun deyil."
        cases = (("approve", {}), ("revise", {"reason": reason}), ("reject", {"reason": reason}))

        for action, extra in cases:
            with self.subTest(action=action):
                response = self._decide(self.dean, action, **extra)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "transition.permission_denied")

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, SyllabusStatus.SUBMITTED.value)

    def test_dean_queue_is_read_only_with_an_explicit_note(self):
        html = self._html(self.dean)

        self.assertIn(f'data-syl-open="{self.version.pk}"', html)  # növbəni GÖRÜR
        self.assertIn(READ_ONLY_NOTE, html)
        self.assertNotIn('data-syl-decide="approve"', html)
        self.assertNotIn('data-syl-decide="reject"', html)

    # ── Kafedra müdiri ─────────────────────────────────────────────────────

    def test_chair_head_of_the_owning_chair_approves(self):
        response = self._decide(self.chair_a, "approve")

        self.assertEqual(response.status_code, 200)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, SyllabusStatus.APPROVED.value)

    def test_chair_head_queue_still_shows_the_decision_buttons(self):
        html = self._html(self.chair_a)

        self.assertIn('data-syl-decide="approve"', html)
        self.assertNotIn(READ_ONLY_NOTE, html)

    def test_chair_head_of_another_chair_is_blocked_by_the_scope_gate(self):
        response = self._decide(self.chair_b, "approve")

        self.assertEqual(response.status_code, 404)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, SyllabusStatus.SUBMITTED.value)

    # ── Org-wide override ──────────────────────────────────────────────────

    def test_rim_override_still_works_and_is_audited(self):
        response = self._decide(self.rim, "approve")

        self.assertEqual(response.status_code, 200)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, SyllabusStatus.APPROVED.value)
        self.assertEqual(self.version.approved_by_id, self.rim.pk)

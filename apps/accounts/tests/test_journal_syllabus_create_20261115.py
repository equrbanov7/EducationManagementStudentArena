"""Sahib 2026-11-15: jurnalda sillabus yoxdursa «Sillabus yarat» klikdə dosyeni yaradıb redaktoru açır.

* ``syllabus_action`` ``create`` cavabı dosyenin id-sini (``syllabus``) qaytarır — JS redaktora bu id ilə keçir;
* superadmin başqa müəllimin jurnalı üçün də yarada bilər; adi kənar müəllim 404 alır (mövcudluq sızmır).
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.syllabus.models import Syllabus
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]


class JournalSyllabusCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("syl-jcreate")
        cls.teacher = User.objects.create_user("jcreate_teacher", "jcreate_teacher@x.test", "pw")
        cls.other = User.objects.create_user("jcreate_other", "jcreate_other@x.test", "pw")
        for user in (cls.teacher, cls.other):
            activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS, level=60)
        cls.admin = User.objects.create_superuser("jcreate_admin", "jcreate_admin@x.test", "pw")
        cls.stack = make_academic_stack(cls.org, code="JCR101")
        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)

    def post(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client.post(
            reverse("accounts:syllabus_action"),
            data=json.dumps({"action": "create", "offering": str(self.offering.pk)}),
            content_type="application/json",
        )

    def test_teacher_create_returns_syllabus_id(self):
        response = self.post(self.teacher)
        self.assertEqual(response.status_code, 200)
        syllabus = Syllabus.objects.get(offering=self.offering)
        self.assertEqual(response.json()["syllabus"], str(syllabus.pk))

    def test_superadmin_can_create_for_teachers_journal(self):
        response = self.post(self.admin)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(Syllabus.objects.filter(offering=self.offering).exists())

    def test_other_teacher_gets_404(self):
        response = self.post(self.other)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

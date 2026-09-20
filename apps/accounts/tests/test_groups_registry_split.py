"""Ekran 06 «Qruplar» — ana qrupu ALT QRUPLARA BÖLMƏ (sahib 2026-09-20).

* `action=split_group`: alt qruplar ana qrupun ixtisası altında yaranır, metadata
  (kurs, dil sektoru, qəbul ili) miras alınır, `settings.parent_group` ana qrupu
  göstərir; tələbələr RƏSMİ köçürmə xidməti ilə keçir (jurnal tarixçəsi qalır),
  seçilməyənlər ana qrupda qalır; hər alt qrup üçün audit sətri düşür.
* Validasiya: ≥2 alt qrup, adlar boş/təkrar olmasın, mövcud qrup adı ilə toqquşmasın,
  tələbə yalnız bir alt qrupda və yalnız bu qrupun aktiv tələbəsi olsun, səbəb ≥3.
* İcazə: `unit.group_manage` olmayan (adi müəllim) 403 alır.
* Reyestr fraqmenti «Alt qruplara böl» düyməsini və dialoqu render edir.
"""

import json

from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.group_split import parse_subgroups
from apps.organizations.models import OrgUnit
from apps.registrar.models import StudentAcademicRecord

from .test_group_students_drawer import _StudentsBase

REASON = "Laboratoriya dərsləri üçün alt qruplara bölünür."


class _SplitBase(_StudentsBase):
    def _split(self, role, payload):
        data = {"action": "split_group", "id": str(self.group.id), "reason": REASON}
        data.update(payload)
        return self._client(role).post(reverse("organizations:group_action", kwargs={"slug": self.org.slug}), data)

    def _payload(self, first, second, names=("QA-DS2 KE-24-1", "QA-DS2 KE-24-2")):
        return {
            "subgroups": json.dumps(
                [
                    {"name": names[0], "record_ids": [str(r.pk) for r in first]},
                    {"name": names[1], "record_ids": [str(r.pk) for r in second]},
                ]
            )
        }


class ParseSubgroupsTest(_SplitBase):
    def test_parses_and_normalises(self):
        parsed = parse_subgroups(
            json.dumps([{"name": "  A   1 ", "record_ids": ["x", " ", "y"]}, {"name": "B", "record_ids": []}])
        )
        self.assertEqual(parsed, [{"name": "A 1", "record_ids": ["x", "y"]}, {"name": "B", "record_ids": []}])

    def test_rejects_bad_shapes(self):
        for raw, code in (
            ("{", "subgroups_invalid"),
            (json.dumps([{"name": "A", "record_ids": []}]), "too_few"),
            (json.dumps([{"name": "", "record_ids": []}, {"name": "B", "record_ids": []}]), "name_required"),
            (json.dumps([{"name": "a", "record_ids": []}, {"name": "A", "record_ids": []}]), "name_duplicate"),
            (json.dumps([{"name": "A", "record_ids": ["1"]}, {"name": "B", "record_ids": ["1"]}]), "student_duplicate"),
            (json.dumps([{"name": str(i), "record_ids": []} for i in range(7)]), "too_many"),
        ):
            with self.assertRaises(ValueError) as ctx:
                parse_subgroups(raw)
            self.assertEqual(str(ctx.exception), code)


class SplitGroupActionTest(_SplitBase):
    def test_splits_into_two_subgroups_and_keeps_the_rest_in_the_parent(self):
        a, b, c = self.students
        response = self._split("teaching_office_head", self._payload([a], [b]))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["moved"], 2)
        self.assertEqual(payload["remaining"], 1)
        self.assertEqual([item["name"] for item in payload["created"]], ["QA-DS2 KE-24-1", "QA-DS2 KE-24-2"])

        sub1 = OrgUnit.objects.get(organization=self.org, name="QA-DS2 KE-24-1")
        sub2 = OrgUnit.objects.get(organization=self.org, name="QA-DS2 KE-24-2")
        self.assertEqual(sub1.parent_id, self.group.parent_id)
        self.assertEqual(sub1.settings["parent_group"], str(self.group.pk))
        self.assertEqual(sub1.settings["language_sector"], self.group.settings.get("language_sector", ""))
        self.assertEqual(StudentAcademicRecord.objects.get(pk=a.pk).group_id, sub1.pk)
        self.assertEqual(StudentAcademicRecord.objects.get(pk=b.pk).group_id, sub2.pk)
        self.assertEqual(StudentAcademicRecord.objects.get(pk=c.pk).group_id, self.group.pk)
        # Hər alt qrup üçün audit + ana qrup üçün yekun sətir.
        self.assertGreaterEqual(AuditLog.objects.filter(reason__contains="subgroup created by splitting").count(), 2)
        self.assertTrue(AuditLog.objects.filter(reason__contains="group split into subgroups").exists())

    def test_rejects_name_collision_and_foreign_students(self):
        a, b, _c = self.students
        response = self._split(
            "teaching_office_head", self._payload([a], [b], names=(self.group_b.name.lower(), "Yeni-2"))
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "name_taken")
        self.assertFalse(OrgUnit.objects.filter(name="Yeni-2").exists())

        foreign = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.users["teacher"],
            program=self.program,
            curriculum=self.plan,
            group=self.group_b,
            admission_year=2024,
        )
        response = self._split("teaching_office_head", self._payload([a], [foreign]))
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "student_outside_group")
        self.assertFalse(OrgUnit.objects.filter(name="QA-DS2 KE-24-1").exists())  # heç nə yaradılmadı

    def test_requires_reason_and_permission(self):
        a, b, _c = self.students
        response = self._split("teaching_office_head", {**self._payload([a], [b]), "reason": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "reason_required")
        response = self._split("teacher", self._payload([a], [b]))
        self.assertEqual(response.status_code, 403)

    def test_registry_fragment_renders_split_button_and_dialog(self):
        client = self._client("teaching_office_head")
        response = client.get(reverse("accounts:profile") + "?section=groups-registry")
        html = response.content.decode()
        self.assertIn("data-tof-split-open", html)
        self.assertIn('id="tofGroupSplitDialog"', html)
        self.assertIn('name="subgroups"', html)

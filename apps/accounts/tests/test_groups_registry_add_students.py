"""Ekran 06 «Qruplar» — sahib istəkləri (2026-09-07).

* qrup adı / kodu UNİKALDIR (eyni adda/kodda ikinci qrup yaradılmır);
* «Tələbə əlavə et»: namizədlər YALNIZ qrupsuz qeydiyyatlı tələbələrdir, əlavə
  RƏSMİ köçürmə xidməti ilə (səbəb ≥20) aparılır;
* təhsil forması (əyani/qiyabi) qrupun metadatasında saxlanılır və filtrlənir;
* reyestr fraqmenti avto-filtr, Bootstrap select və əlavə dialoqu render edir.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import StudentAcademicRecord

from .test_group_students_drawer import _StudentsBase
from .test_teaching_office_stage2 import PASSWORD

User = get_user_model()

REASON = "Tələbə qəbul əmrinə əsasən qrupa daxil edilir — sərəncam №7/T, 2026."


class _AddStudentsBase(_StudentsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # QRUPSUZ tələbələr — «tələbə əlavə et» namizədləri.
        cls.free = []
        for index in range(2):
            user = User.objects.create_user(f"ds2_free{index}", f"ds2_free{index}@qku.edu.az", PASSWORD)
            user.first_name, user.last_name = f"Sərbəst{index}", f"Qrupsuz{index}"
            user.save(update_fields=["first_name", "last_name"])
            Membership.objects.create(
                user=user, organization=cls.org, role=cls.roles["teacher"], is_primary=True, is_active=True
            )
            cls.free.append(
                StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=cls.program,
                    curriculum=cls.plan,
                    group=None,
                    admission_year=2026,
                )
            )

    def _action(self, role, payload):
        return self._client(role).post(reverse("organizations:group_action", kwargs={"slug": self.org.slug}), payload)

    def _candidates_url(self, group=None):
        return reverse(
            "organizations:group_student_candidates",
            kwargs={"slug": self.org.slug, "unit_id": (group or self.group).id},
        )


class GroupUniquenessTest(_AddStudentsBase):
    def test_duplicate_name_is_rejected(self):
        response = self._action(
            "teaching_office_head",
            {"action": "save_group", "name": self.group.name.lower(), "specialty": str(self.specialty.id)},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "name_taken")
        self.assertEqual(response.json()["field"], "name")

    def test_duplicate_code_is_rejected(self):
        response = self._action(
            "teaching_office_head",
            {
                "action": "save_group",
                "name": "Tam yeni ad",
                "code": self.group_b.code.lower(),
                "specialty": str(self.specialty.id),
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "code_taken")

    def test_editing_keeps_own_name(self):
        response = self._action(
            "teaching_office_head",
            {
                "action": "save_group",
                "id": str(self.group.id),
                "name": self.group.name,
                "code": self.group.code,
                "specialty": str(self.specialty.id),
                "education_form": "part_time",
                "language_sector": "EN",
                "admission_year": "2026",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.settings["education_form"], "part_time")
        self.assertEqual(self.group.settings["language_sector"], "EN")

    def test_unknown_education_form_is_dropped(self):
        response = self._action(
            "teaching_office_head",
            {
                "action": "save_group",
                "name": "Forma sınağı",
                "specialty": str(self.specialty.id),
                "education_form": "hacked",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        unit = OrgUnit.objects.get(organization=self.org, name="Forma sınağı")
        self.assertEqual(unit.settings["education_form"], "")


class CandidatesEndpointTest(_AddStudentsBase):
    def test_lists_only_groupless_enrolled_students(self):
        response = self._client("teaching_office_head").get(self._candidates_url())
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        ids = {row["id"] for row in body["results"]}
        self.assertEqual(ids, {str(record.id) for record in self.free})
        # Qrupdakı tələbələr siyahıda YOXDUR.
        for record in self.students:
            self.assertNotIn(str(record.id), ids)
        self.assertFalse(body["has_more"])
        self.assertIn("@ds2_free0", body["results"][0]["text"] + body["results"][1]["text"])

    def test_search_by_name_and_pagination(self):
        response = self._client("teaching_office_head").get(self._candidates_url(), {"q": "Qrupsuz1"})
        rows = response.json()["results"]
        self.assertEqual([row["id"] for row in rows], [str(self.free[1].id)])

        paged = self._client("teaching_office_head").get(self._candidates_url(), {"limit": "1"}).json()
        self.assertEqual(len(paged["results"]), 1)
        self.assertTrue(paged["has_more"])

    def test_requires_manage_permission(self):
        self.assertEqual(self._client("dean").get(self._candidates_url()).status_code, 403)
        self.assertEqual(self._client("teacher").get(self._candidates_url()).status_code, 403)


class AddStudentsActionTest(_AddStudentsBase):
    def test_requires_students_but_not_reason(self):
        """Səbəb TƏLƏB OLUNMUR (sahib, 2026-09-08) — boş/qısa səbəblə də əlavə keçir,
        auditə standart qeyd düşür; tələbə seçilməyibsə yenə 400."""
        empty = self._action("teaching_office_head", {"action": "add_students", "id": str(self.group_b.id)})
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(empty.json()["error"], "students_required")

        short = self._action(
            "teaching_office_head",
            {
                "action": "add_students",
                "id": str(self.group_b.id),
                "record_ids": str(self.free[0].id),
                "reason": "qısa",
            },
        )
        self.assertEqual(short.status_code, 200, short.content)
        self.free[0].refresh_from_db()
        self.assertEqual(self.free[0].group_id, self.group_b.id)

    def test_adds_groupless_students_via_official_transfer(self):
        response = self._action(
            "teaching_office_head",
            {
                "action": "add_students",
                "id": str(self.group_b.id),
                "record_ids": ",".join(str(record.id) for record in self.free),
                "reason": REASON,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["added"], 2)
        for record in self.free:
            record.refresh_from_db()
            self.assertEqual(record.group_id, self.group_b.id)
            self.assertTrue(record.is_active)
        self.assertTrue(
            AuditLog.objects.filter(organization=self.org, reason__icontains="groups: students added").exists()
        )
        # Artıq qrupdadırlar — namizəd siyahısından düşürlər.
        left = self._client("teaching_office_head").get(self._candidates_url(self.group_b)).json()["results"]
        self.assertEqual(left, [])
        # Çekmecədə ixtisas şifri/adı ilə görünürlər.
        drawer = self._client("teaching_office_head").get(self._students_url(self.group_b)).json()
        self.assertEqual({row["username"] for row in drawer["rows"]}, {"ds2_free0", "ds2_free1"})
        self.assertIn("program_name", drawer["rows"][0])
        self.assertIn("program_code", drawer["rows"][0])

    def test_student_already_in_group_is_not_added(self):
        record = self.students[0]
        response = self._action(
            "teaching_office_head",
            {"action": "add_students", "id": str(self.group_b.id), "record_ids": str(record.id), "reason": REASON},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "no_candidates")
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.group.id)

    def test_dean_without_manage_is_forbidden(self):
        response = self._action(
            "dean",
            {
                "action": "add_students",
                "id": str(self.group_b.id),
                "record_ids": str(self.free[0].id),
                "reason": REASON,
            },
        )
        self.assertEqual(response.status_code, 403)


class RegistryFragmentTest(_AddStudentsBase):
    def test_fragment_renders_auto_filters_bootstrap_selects_and_add_dialog(self):
        response = self._fragment("teaching_office_head", "groups-registry")
        html = response.json()["html"]
        self.assertIn('data-ems-filters-auto="1"', html)
        self.assertNotIn("ems-filters__apply", html)
        self.assertIn('name="gr_form"', html)
        self.assertIn('name="gr_year"', html)
        self.assertIn("data-bootstrap-select", html)
        self.assertIn('data-live-search="true"', html)
        self.assertIn('id="tofGroupAddStudentsDialog"', html)
        self.assertIn("data-tof-add-students", html)
        self.assertIn('name="education_form"', html)
        self.assertIn('<option value="AZ">', html)
        section = response.context["groups_registry_section"]
        self.assertTrue(section["current_year"] >= 2026)
        self.assertEqual(section["default_education_form"], "full_time")
        row = next(r for r in section["rows"] if r["name"] == self.group.name)
        self.assertIn("candidates_url", row)
        self.assertEqual(row["candidates_url"], self._candidates_url())

    def test_education_form_filter(self):
        settings_blob = dict(self.group_b.settings)
        settings_blob["education_form"] = "part_time"
        OrgUnit.objects.filter(pk=self.group_b.pk).update(settings=settings_blob)

        response = self._fragment("teaching_office_head", "groups-registry", gr_form="part_time")
        names = {r["name"] for r in response.context["groups_registry_section"]["rows"]}
        self.assertEqual(names, {self.group_b.name})
        row = next(iter(response.context["groups_registry_section"]["rows"]))
        self.assertEqual(row["education_form_label"], "Qiyabi")

        by_year = self._fragment("teaching_office_head", "groups-registry", gr_year="2024")
        self.assertIn(self.group_b.name, {r["name"] for r in by_year.context["groups_registry_section"]["rows"]})

    def test_exam_cohort_link_is_gone(self):
        """Köhnə imtahan-kohortu «Qruplar» bölməsi silinib (sahib, 2026-09-08) —
        reyestr başlığında ona çarpaz keçid qalmamalıdır; «Dərs cədvəli» qalır."""
        response = self._fragment("teaching_office_head", "groups-registry")
        html = response.json()["html"]
        self.assertNotIn("İmtahan kohortları", html)
        self.assertNotIn('data-section="groups"', html)
        self.assertIn('data-section="schedule-manage"', html)

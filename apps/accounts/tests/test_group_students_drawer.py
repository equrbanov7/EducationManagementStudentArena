"""Ekran 06 «Qruplar» — tələbə çekmecəsi, «qrupdan çıxar» və rəsmi DOCX (2026-09-07).

* ``organizations:group_students`` — oxu (`unit.view`), əhatədən kənar 404,
  bayraqlar (`can_manage` / `can_move_students`);
* «qrupdan çıxar» = RƏSMİ köçürmə (`student_registry_action`, kind=group_transfer) —
  DB qapısı qrup dəyişikliyini yalnız köçürmə xidmətinə buraxır; əmr № + tarix +
  hədəf qrup + səbəb ≥20, köhnə qeydiyyat tarixçəyə keçir;
* ``registrar:group_individual_plan`` — DOCX rəsmi şablondan, yer tutucu qalmır,
  tələbə adı və fənn sətirləri sənəddədir, `?student=` tək tələbə verir;
* semestr açılışı: səhifələmə (`sm_page`) + «Necə işləyir» məzmunu.
"""

import io
import zipfile

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import CourseOffering, PlanStatus, StudentAcademicRecord
from core.constants import OrgUnitType

from .test_teaching_office_stage2 import PASSWORD, Stage2BaseTest

User = get_user_model()

REASON = "Tələbə öz ərizəsi ilə başqa qrupa keçir — dekanlıq sərəncamı №41."


class _StudentsBase(Stage2BaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.plan = cls._plan_for_class(status=PlanStatus.APPROVED)
        cls.row = cls._row_for_class(cls.plan, cls.subject, semester=1, credits=5)
        cls.row_b = cls._row_for_class(cls.plan, cls.subject_b, semester=2, credits=6)
        cls.students = []
        for index in range(3):
            user = User.objects.create_user(f"ds2_st{index}", f"ds2_st{index}@qku.edu.az", PASSWORD)
            user.first_name, user.last_name = f"Ad{index}", f"Soyad{index}"
            user.save(update_fields=["first_name", "last_name"])
            Membership.objects.create(
                user=user,
                organization=cls.org,
                role=cls.roles["teacher"],  # rol vacib deyil — qeyd əsasdır
                is_primary=True,
                is_active=True,
            )
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                program=cls.program,
                curriculum=cls.plan,
                group=cls.group,
                admission_year=2024,
            )
            cls.students.append(record)
        cls.offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.subject,
            period=cls.period,
            group=cls.group,
            instructor=cls.users["teacher"],
        )
        cls.far_group = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.GROUP, name="Uzaq qrup", slug="ds2-far", code="FAR"
        )
        cls.group_b = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name="QA-DS2 KE-24B",
            slug="ds2-qrup-b",
            code="KE-24B",
            settings={"language_sector": "AZ", "course_year": 1, "admission_year": 2024},
        )
        # Tədris şöbəsi rəhbəri tələbə hərəkəti də yazır (student.movement) — çekmecədəki
        # «dondur / uzaqlaşdır / qrupdan çıxar» düymələri bu açara bağlıdır.
        head = cls.roles["teaching_office_head"]
        head.permissions = list(head.permissions) + [
            "student.movement",
            "student.assign_group",
            "student.registry_view",
            "people.manage_academic",
        ]
        head.save(update_fields=["permissions"])
        # Qrup köçürməsi yalnız CARİ dövrdə aparılır.
        cls.period.is_current = True
        cls.period.save(update_fields=["is_current"])

    @classmethod
    def _plan_for_class(cls, **kwargs):
        from apps.registrar.models import Curriculum

        return Curriculum.objects.create(
            organization=cls.org, program=cls.program, admission_year=2024, name="QA plan", version=1, **kwargs
        )

    @classmethod
    def _row_for_class(cls, plan, subject, *, semester, credits):
        from apps.registrar.models import CurriculumSubject

        return CurriculumSubject.objects.create(
            organization=cls.org,
            curriculum=plan,
            subject=subject,
            semester_number=semester,
            credits=credits,
            total_hours=credits * 30,
            lecture_hours=30,
            seminar_hours=15,
            lab_hours=15,
            selfwork_hours=credits * 30 - 60,
            row_code=f"QA-{semester}",
        )

    def _students_url(self, group=None):
        return reverse(
            "organizations:group_students", kwargs={"slug": self.org.slug, "unit_id": (group or self.group).id}
        )


class GroupStudentsEndpointTest(_StudentsBase):
    def test_lists_active_students_with_flags(self):
        response = self._client("teaching_office_head").get(self._students_url())
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["group"]["name"], self.group.name)
        self.assertEqual({row["username"] for row in body["rows"]}, {"ds2_st0", "ds2_st1", "ds2_st2"})
        self.assertTrue(body["can_manage"])
        self.assertTrue(body["can_move_students"])
        row = body["rows"][0]
        self.assertEqual(row["status"], "enrolled")
        self.assertEqual(row["admission_year"], 2024)

    def test_dean_reads_but_cannot_manage(self):
        body = self._client("dean").get(self._students_url()).json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["can_manage"])
        self.assertFalse(body["can_move_students"])

    def test_group_outside_scope_is_404(self):
        response = self._client("dean").get(self._students_url(self.far_group))
        self.assertEqual(response.status_code, 404)

    def test_teacher_without_unit_view_is_403(self):
        response = self._client("teacher").get(self._students_url())
        self.assertEqual(response.status_code, 403)

    def test_registry_rows_carry_drawer_and_docx_urls(self):
        response = self._fragment("teaching_office_head", "groups-registry")
        row = next(r for r in response.context["groups_registry_section"]["rows"] if r["name"] == self.group.name)
        self.assertEqual(row["students_url"], self._students_url())
        self.assertIn("ferdi-plan.docx", row["plan_url"])
        html = response.json()["html"]  # fraqment API HTML-i JSON içində qaytarır
        self.assertIn("data-tof-students-open", html)
        self.assertIn('id="tofGroupStudentsDrawer"', html)
        self.assertIn('id="tofStudentTransferDialog"', html)
        self.assertIn('id="tofStudentFreezeDialog"', html)
        self.assertIn(f'<option value="{self.group_b.id}">', html)  # köçürmə hədəfi


class TransferStudentActionTest(_StudentsBase):
    """«Qrupdan çıxar» — rəsmi köçürmə (hərəkət əmri) ilə; qeydiyyat tarixçəsi qalır."""

    def _post(self, role, payload):
        return self._client(role).post(reverse("accounts:student_registry_action"), payload)

    def _payload(self, record, **extra):
        payload = {
            "record_id": str(record.id),
            "kind": "group_transfer",
            "target_group": str(self.group_b.id),
            "order_number": "12/T",
            "order_date": "2026-09-07",
            "reason": REASON,
        }
        payload.update(extra)
        return payload

    def test_short_reason_is_rejected(self):
        record = self.students[0]
        response = self._post("teaching_office_head", self._payload(record, reason="qısa"))
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(response.json()["ok"])
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.group.id)

    def test_transfer_moves_student_and_keeps_history(self):
        record = self.students[1]
        response = self._post("teaching_office_head", self._payload(record))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.group_b.id)
        self.assertEqual(record.status, "enrolled")
        self.assertTrue(StudentAcademicRecord.objects.filter(pk=record.pk, is_active=True).exists())
        # Köhnə qrupun çekmecəsində yoxdur, yeni qrupunkində var.
        old_rows = self._client("teaching_office_head").get(self._students_url()).json()["rows"]
        new_rows = self._client("teaching_office_head").get(self._students_url(self.group_b)).json()["rows"]
        self.assertNotIn(record.student.username, {row["username"] for row in old_rows})
        self.assertIn(record.student.username, {row["username"] for row in new_rows})
        self.assertTrue(
            AuditLog.objects.filter(organization=self.org, user=self.users["teaching_office_head"]).exists()
        )

    def test_dean_without_movement_permission_is_refused(self):
        record = self.students[2]
        response = self._post("dean", self._payload(record))
        self.assertEqual(response.status_code, 403)
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.group.id)


class IndividualPlanDocxTest(_StudentsBase):
    def _docx_text(self, payload: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return archive.read("word/document.xml").decode("utf-8")

    def test_group_document_has_one_page_per_student(self):
        url = reverse("registrar:group_individual_plan", kwargs={"group_id": self.group.id})
        response = self._client("teaching_office_head").get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("wordprocessingml", response["Content-Type"])
        self.assertEqual(response["X-Students"], "3")
        xml = self._docx_text(response.content)
        for record in self.students:
            self.assertIn(record.student.get_full_name(), xml)
        self.assertNotIn("{{", xml)  # heç bir yer tutucu qalmır
        self.assertEqual(xml.count('<w:br w:type="page"/>'), 2)  # 3 tələbə → 2 səhifə keçidi
        self.assertIn("QA-DS2 Alqoritmlər", xml)  # 1-ci semestr fənni
        self.assertIn("QA-DS2 Diskret riyaziyyat", xml)  # 2-ci semestr fənni
        self.assertIn("QA-1", xml)  # fənnin kodu = plan şifri (row_code)
        self.assertNotIn("QA-DS2-SBJ", xml)  # daxili subject.code sızmır
        self.assertIn("Payız semestri (P-1)", xml)
        self.assertIn("Yaz semestri (Y-2)", xml)
        self.assertIn(self.users["teacher"].username, xml)  # açılışın müəllimi
        self.assertIn("Kompüter elmləri", xml)  # ixtisas
        self.assertIn("Mühəndislik", xml)  # fakültə

    def test_single_student_document(self):
        record = self.students[0]
        url = reverse("registrar:group_individual_plan", kwargs={"group_id": self.group.id})
        response = self._client("dean").get(url, {"student": str(record.id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Students"], "1")
        xml = self._docx_text(response.content)
        self.assertIn(record.student.get_full_name(), xml)
        self.assertNotIn(self.students[1].student.get_full_name(), xml)
        self.assertNotIn('<w:br w:type="page"/>', xml)

    def test_outside_scope_or_no_permission_is_404(self):
        url = reverse("registrar:group_individual_plan", kwargs={"group_id": self.far_group.id})
        self.assertEqual(self._client("dean").get(url).status_code, 404)
        url = reverse("registrar:group_individual_plan", kwargs={"group_id": self.group.id})
        self.assertEqual(self._client("teacher").get(url).status_code, 404)


class SemesterOpeningPaginationTest(_StudentsBase):
    def test_section_paginates_and_explains(self):
        response = self._fragment("teaching_office_head", "semester-opening", sm_period=str(self.period.id))
        self.assertEqual(response.status_code, 200)
        section = response.context["semester_opening_section"]
        self.assertEqual(section["page_obj"].paginator.count, 1)
        self.assertEqual(len(section["howto"]), 5)
        self.assertIn(section["howto"][0]["state"], ("done", "current", "todo", "error"))
        html = response.json()["html"]
        self.assertIn("tof-howto", html)
        self.assertIn("Necə işləyir", html)
        self.assertIn("tof-table-title", html)

"""«Tələbəni qrupa əlavə et» — başqa qrupdakı tələbə (sahib 2026-11-18).

Sahib: «axtardıqca bütün tələbələr görünsün; başqa qrupdadırsa göstərin — ya əlavə olaraq (əcnəbi tələbə 2 qrupda
ola bilər, əsas qrupuna dəymirik), ya da məcburi keçid». Yoxlanır:

* axtarış yazılanda başqa qrupdakı tələbə «x:» önəkli id və «başqa qrupdadır» qeydi ilə gəlir (boş axtarışda yox);
* rejim seçilməyibsə 400 ``other_mode_required``; ``transfer`` — rəsmi köçürmə;
* ``extra`` — öz qrupu QALIR, qrupun cari jurnalına mənbə qrupla qeydiyyat + yerləşdirmə tarixçəsi; çekmecədə
  «Əlavə üzvlər» (``extra_rows``); qrupun jurnalı yoxdursa aydın 400.
"""

from apps.registrar.models import CourseOffering, Enrollment, SubgroupPlacementEvent

from .test_groups_registry_add_students import _AddStudentsBase


class OtherGroupCandidatesTest(_AddStudentsBase):
    def test_search_shows_students_of_other_groups_with_prefix(self):
        record = self.students[0]
        rows = (
            self._client("teaching_office_head")
            .get(self._candidates_url(self.group_b), {"q": "Soyad0"})
            .json()["results"]
        )
        self.assertEqual([row["id"] for row in rows], ["x:" + str(record.id)])
        self.assertIn(self.group.name, rows[0]["text"])

    def test_empty_search_keeps_only_groupless(self):
        rows = self._client("teaching_office_head").get(self._candidates_url(self.group_b)).json()["results"]
        self.assertEqual({row["id"] for row in rows}, {str(record.id) for record in self.free})

    def test_own_group_members_are_not_candidates(self):
        rows = (
            self._client("teaching_office_head")
            .get(self._candidates_url(self.group), {"q": "Soyad0"})
            .json()["results"]
        )
        self.assertEqual(rows, [])


class OtherGroupAddTest(_AddStudentsBase):
    def _add(self, record, **extra):
        payload = {"action": "add_students", "id": str(self.group_b.id), "record_ids": "x:" + str(record.id)}
        payload.update(extra)
        return self._action("teaching_office_head", payload)

    def test_transfer_mode_moves_student(self):
        record = self.students[0]
        response = self._add(record, other_mode="transfer")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["transferred"], 1)
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.group_b.id)

    def test_extra_mode_keeps_home_group_and_enrolls_in_group_journals(self):
        offering = CourseOffering.objects.create(
            organization=self.org, subject=self.subject_b, period=self.period, group=self.group_b
        )
        record = self.students[0]
        response = self._add(record, other_mode="extra")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["extra"], 1, body)
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.group.id)  # öz qrupu dəyişmir
        enrollment = Enrollment.objects.get(student=record.student, offering=offering)
        self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)
        self.assertEqual(enrollment.source_group_id, self.group.id)
        self.assertTrue(SubgroupPlacementEvent.objects.filter(enrollment=enrollment).exists())
        drawer = self._client("teaching_office_head").get(self._students_url(self.group_b)).json()
        self.assertEqual([row["username"] for row in drawer["extra_rows"]], [record.student.username])
        self.assertEqual(drawer["extra_rows"][0]["group_name"], self.group.name)
        self.assertEqual(drawer["rows"], [])

    def test_extra_mode_without_group_journals_is_rejected(self):
        record = self.students[0]
        response = self._add(record, other_mode="extra")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn("jurnalı yoxdur", response.json()["message"])
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.group.id)

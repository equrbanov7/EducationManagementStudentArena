"""``legacy_journal_teachers_extract`` xidməti: köhnə jurnal → (fənn UUID, qrup UUID-ləri, istifadəçi id, növlər).

Faylda AD YOXDUR; saxta / «sonra sil» jurnal atılır; alt qrup ana qrupu da gətirir; tapılmayan müəllim üçün hesab
YARADILMIR (``teacher_id=None``)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.legacy_import.services.delta.journal_teachers import FORMAT, current_semester, extract
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import Subject
from core.constants import OrgUnitType

User = get_user_model()


class _Cursor:
    """MariaDB kursoru əvəzi: SQL-dəki cədvəl adına görə hazır sətirlər qaytarır."""

    def __init__(self, tables: dict):
        self.tables = tables
        self.description = ()
        self._rows: list = []

    def execute(self, sql, params=()):
        rows = next((found for marker, found in self.tables.items() if marker in sql), [])
        names = list(rows[0]) if rows else ["id"]
        self.description = [(name,) for name in names]
        self._rows = [tuple(row[name] for name in names) for row in rows]

    def fetchall(self):
        return self._rows


class JournalTeachersExtractTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("jt_owner", "jt@x.test", "pw")
        self.org = Organization.objects.create(name="JT", slug="jt-org", owner=owner, status="active", is_active=True)
        self.chair = OrgUnit.objects.create(
            organization=self.org, name="JT kafedra", slug="jt-chair", unit_type=OrgUnitType.CHAIR
        )
        self.group = OrgUnit.objects.create(
            organization=self.org, name="236 BİO", slug="jt-group", unit_type=OrgUnitType.GROUP
        )
        self.subgroup = OrgUnit.objects.create(
            organization=self.org, name="236 BİO-1", slug="jt-sub", unit_type=OrgUnitType.GROUP, parent=self.group
        )
        self.subject = Subject.objects.create(organization=self.org, code="JT1", name="Sitologiya")
        self.teacher = User.objects.create_user("jt_t", "t@x.test", "pw", first_name="Natəvan", last_name="Kərəmova")
        role = Role.objects.create(organization=self.org, name="teacher", display_name="Teacher", is_active=True)
        Membership.objects.create(organization=self.org, user=self.teacher, role=role, scope_unit=self.chair)

    def _cursor(self):
        return _Cursor(
            {
                "semestr_jurnal": [{"id": 14, "name": "2026/2027 Payız"}],
                "journals_dates_added_by_teacher": [{"journal_id": 1, "n": 8}],
                ".journals ": [
                    {"id": 1, "lesson_id": 50, "teacher_id": 7, "groups_id": '["90"]', "sem_muh": '["0","1"]',
                     "active": 1, "fake": 0, "sonra_sil": 0},
                    {"id": 2, "lesson_id": 50, "teacher_id": 8, "groups_id": '["91"]', "sem_muh": '["2"]',
                     "active": 1, "fake": 0, "sonra_sil": 0},
                    {"id": 3, "lesson_id": 50, "teacher_id": 7, "groups_id": '["90"]', "sem_muh": '["1"]',
                     "active": 1, "fake": 1, "sonra_sil": 0},
                ],  # fmt: skip
                "`lessons`": [{"id": 50, "name": "Sitologiya"}],
                "`groups`": [{"id": 90, "name": "236 BİO"}, {"id": 91, "name": "236 BİO-1"}],
                "`workers`": [
                    {"id": 7, "first_name": "Natəvan", "last_name": "Kərəmova", "father_name": "", "department_id": 0},
                    {"id": 8, "first_name": "Naməlum", "last_name": "Şəxs", "father_name": "", "department_id": 0},
                ],
            }
        )

    def test_extract_maps_to_target_keys_without_names(self):
        self.assertEqual(current_semester(self._cursor(), "myedu_new")["id"], 14)
        data = extract(self._cursor(), source="myedu_new", semester=14, organization=self.org)
        self.assertEqual(data["format"], FORMAT)
        self.assertEqual(data["stats"]["skipped_fake"], 1)
        by_id = {journal["legacy_id"]: journal for journal in data["journals"]}
        self.assertEqual(set(by_id), {1, 2})
        first = by_id[1]
        self.assertEqual(first["subject_id"], str(self.subject.pk))
        self.assertEqual(first["group_ids"], [str(self.group.pk)])
        self.assertEqual(first["teacher_id"], self.teacher.pk)
        self.assertEqual(first["kinds"], ["lecture", "seminar"])
        self.assertEqual(first["dates"], 8)
        second = by_id[2]
        self.assertEqual(set(second["group_ids"]), {str(self.group.pk), str(self.subgroup.pk)})  # ana qrup da
        self.assertIsNone(second["teacher_id"])  # tapılmadı — hesab YARADILMIR
        self.assertFalse(User.objects.filter(last_name="Şəxs").exists())
        self.assertNotIn("Kərəmova", repr(data))

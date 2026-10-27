"""``syllabi_backfill`` (sahib 2026-10-27): cari semestr jurnalı olan müəllimin köhnə sillabusu — baza dosye kimi.

Yoxlanılır: dry-run heç nə yazmır; mövcud sillabusa (müəllif və ya açılış müəllimi kimi) toxunulmur; hesab
yaradılmır; birləşmiş jurnal (açılışın müəllimi ≠ köhnə müəllif) — köhnə müəllif öz baza dosyesini alır və jurnal
onu ``syllabus_for_offering``-in 3-cü pilləsi ilə tapır; ikinci qaçış 0 yazı; paket adi fazalarla RƏDD olunur.
"""

import datetime as dt
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.legacy_import.services.delta.apply import BATCH_RESOURCE, execute
from apps.legacy_import.services.delta.syllabi_backfill import TeacherSyllabiPhaseMismatch, choose_source
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.services.drafts import import_migrated_version
from apps.syllabus.services.offerings import syllabus_for_offering_obj
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()
UNTIL = dt.date(2026, 10, 27)
PHASES = ("syllabi_backfill",)


def _worker(pk, first, last):
    return {
        "id": pk,
        "first_name": first,
        "last_name": last,
        "father_name": "",
        "department_id": 3,
        "teacher_type": 1,
        "inzibati": 0,
        "kollec_or_uni": "University",
    }


def _journal(pk, lesson_id, teacher_id, sillabus_id=None, *, fake=0):
    return {
        "id": pk,
        "uniqid": f"uq{pk}",
        "lesson_id": lesson_id,
        "teacher_id": teacher_id,
        "groups_id": "[]",
        "students_id": "[]",
        "semestr": 14,
        "fake": fake,
        "sonra_sil": 0,
        "active": 1,
        "fenn_saati": 45,
        "kredit": 5,
        "sillabus_id": sillabus_id,
    }


def _syllabus(pk, lesson_id, teacher_id, topic, *, active=1, empty=False):
    row = {"id": pk * 10, "uniqid": f"syl{pk}", "movzu": topic, "muh_saat": "2", "sem_saat": "2"}
    row.update(praktiki_saat="", lab_saat="", qeyd="")
    week = [] if empty else [row]
    return {
        "id": pk,
        "uniqid": f"syl{pk}",
        "lesson_id": lesson_id,
        "teacher_id": teacher_id,
        "ders_saati": 45,
        "language": "az",
        "active": active,
        "is_new": False,
        "is_changed": False,
        "week": week,
        "sections": {} if empty else {"sillabus_tesviri_ve_meqsedi": [[pk, f"Təsvir {pk}"]]},
    }


def _bundle():
    return {
        "snapshot": {
            "sha256": "0" * 64,
            "full_semesters": [],
            "phases": list(PHASES),
            "teacher_syllabi": {"semester": 14, "pairs": 6},
        },
        "periods": [{"id": 14, "name": "2026/2027 Payız", "type": "autumn", "is_current": 1}],
        "departments": [],
        "specialities": [],
        "groups": [],
        "subjects": [
            {"id": 5, "name": "Riyaziyyat", "lesson_code": "", "department_id": 3, "type": ""},
            {"id": 6, "name": "Fizika", "lesson_code": "", "department_id": 3, "type": ""},
            {"id": 7, "name": "Kimya", "lesson_code": "", "department_id": 3, "type": ""},
        ],
        "workers": [_worker(77, "Birinci", "Müəllim"), _worker(88, "İkinci", "Müəllim"), _worker(99, "Zz", "Qq")],
        "students": [],
        "expelled_students": [],
        "journals": [
            _journal(11, 5, 77, 500),  # birləşmiş jurnal: açılış B-nindir, köhnə müəllif A
            _journal(12, 6, 77),  # jurnalın sillabusu yoxdur → müəllim + fənnin ən yenisi
            _journal(13, 5, 88, 510),  # B-nin artıq sillabusu var → toxunulmur
            _journal(14, 5, 99, 500),  # müəllim tapılmır → hesab YARADILMIR
            _journal(15, 7, 77),  # fənn kataloqda yoxdur
            _journal(16, 6, 88),  # yalnız boş sillabus
            _journal(17, 6, 99, fake=1),  # saxta jurnal atılır
        ],
        "lesson_dates": [],
        "points": [],
        "excuse_windows": [],
        "lesson_topics": [],
        "syllabi": [
            _syllabus(500, 5, 77, "Giri&ccedil;"),
            _syllabus(510, 5, 88, "B mövzu"),
            _syllabus(600, 6, 77, "Köhnə mövzu"),
            _syllabus(601, 6, 77, "Yeni mövzu"),
            _syllabus(602, 6, 77, "", empty=True),
            _syllabus(603, 6, 77, "Passiv mövzu", active=0),
            _syllabus(650, 6, 88, "", empty=True),
        ],
    }


class SyllabiBackfillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("sb_actor", "sb-actor@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SB Univ",
                slug="sb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(organization=cls.org, name="Fakültə", slug="sb-fac", unit_type="faculty")
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="sb-chair", unit_type="chair", parent=faculty
            )
            cls.g1 = OrgUnit.objects.create(organization=cls.org, name="101 A", slug="sb-g1", unit_type="group")
            cls.g2 = OrgUnit.objects.create(organization=cls.org, name="102 A", slug="sb-g2", unit_type="group")
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2026, 9, 15),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            cls.math = Subject.objects.create(
                organization=cls.org, code="QKU-5", name="Riyaziyyat", chair_unit=cls.chair
            )
            cls.physics = Subject.objects.create(
                organization=cls.org, code="QKU-6", name="Fizika", chair_unit=cls.chair
            )
            teacher_role = cls.org.roles.get(name="teacher")
            cls.a = User.objects.create_user("sb.a", "sb-a@example.test", "x", first_name="Birinci", last_name="A")
            cls.b = User.objects.create_user("sb.b", "sb-b@example.test", "x", first_name="İkinci", last_name="B")
            for user in (cls.a, cls.b):
                Membership.objects.create(
                    user=user, organization=cls.org, role=teacher_role, scope_unit=cls.chair, is_active=True
                )
            # Birləşmiş jurnal: hər iki köhnə jurnal B-nin açılışına düşüb, sillabusu B-nindir.
            cls.offering_b = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.math,
                period=cls.period,
                group=cls.g1,
                instructor=cls.b,
                lesson_hours=45,
            )
            cls.syllabus_b, cls.version_b = import_migrated_version(
                organization=cls.org,
                subject=cls.math,
                approved_at=None,
                period=cls.period,
                offering=cls.offering_b,
                chair_unit=cls.chair,
                author=cls.b,
            )
            # A-nın öz (sillabussuz) açılışı — baza dosyeni 3-cü pillə ilə tapmalıdır.
            cls.offering_a = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.math,
                period=cls.period,
                group=cls.g2,
                instructor=cls.a,
                lesson_hours=45,
            )

    def _run(self, *, apply, bundle=None, phases=PHASES):
        ledger = {"worker": {"77": str(self.a.pk), "88": str(self.b.pk)}}

        def fake(_organization, entity_type, legacy_pks=None):
            found = ledger.get(entity_type, {})
            if legacy_pks is None:
                return dict(found)
            keys = {str(key) for key in legacy_pks}
            return {key: value for key, value in found.items() if key in keys}

        with mock.patch("apps.legacy_import.services.delta.people.ledger_map", fake), bypass_rls():
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=bundle or _bundle(),
                apply=apply,
                until=UNTIL,
                tag="sb-test",
                phases=phases,
            )

    @staticmethod
    def _counts(run):
        return {
            key.split(".", 1)[1]: value for key, value in run.counters.items() if key.startswith("syllabi_backfill.")
        }

    def test_dry_run_counts_and_writes_nothing(self):
        users = User.objects.count()
        with bypass_rls():
            before = Syllabus.objects.filter(organization=self.org).count()
        run = self._run(apply=False)
        counts = self._counts(run)
        self.assertEqual(counts["pairs"], 6)
        self.assertEqual(counts["created"], 2)
        self.assertEqual(counts["skipped_existing"], 1)
        self.assertEqual(counts["teacher_unresolved"], 1)
        self.assertEqual(counts["subject_unresolved"], 1)
        self.assertEqual(counts["empty"], 1)
        self.assertEqual(counts["skipped_inactive_base"], 0)
        with bypass_rls():
            self.assertEqual(Syllabus.objects.filter(organization=self.org).count(), before)
            self.assertFalse(AuditLog.objects.filter(resource_type=BATCH_RESOURCE).exists())
        self.assertEqual(User.objects.count(), users)

    def test_apply_creates_base_for_legacy_author_and_is_idempotent(self):
        users = User.objects.count()
        version_b = SyllabusVersion.objects.get(pk=self.version_b.pk)
        run = self._run(apply=True)
        self.assertEqual(self._counts(run)["created"], 2)
        self.assertEqual(User.objects.count(), users, "tapılmayan müəllimə hesab yaradılmır")
        with bypass_rls():
            base_math = Syllabus.objects.get(
                organization=self.org, subject=self.math, author=self.a, offering__isnull=True, period__isnull=True
            )
            approved = base_math.approved_version
            self.assertEqual((approved.status, approved.approval_source), ("approved", "migration"))
            self.assertEqual(base_math.chair_unit, self.chair)
            week = SyllabusSection.objects.get(version=approved, section_id="week").data
            self.assertIn("Giriç", str(week), "jurnalın öz sillabusu, HTML entity açılıb")
            base_physics = Syllabus.objects.get(organization=self.org, subject=self.physics, author=self.a)
            week = str(SyllabusSection.objects.get(version=base_physics.approved_version, section_id="week").data)
            self.assertIn("Yeni mövzu", week, "müəllim + fənnin ən yeni aktiv, boş olmayan sillabusu")
            self.assertNotIn("Köhnə mövzu", week)
            # B-nin mövcud sillabusuna toxunulmayıb; B-yə ikinci dosye yaranmayıb.
            self.assertEqual(Syllabus.objects.filter(organization=self.org, author=self.b).count(), 1)
            self.assertEqual(SyllabusVersion.objects.filter(syllabus=self.syllabus_b).count(), 1)
            fresh_b = SyllabusVersion.objects.get(pk=self.version_b.pk)
            self.assertEqual(fresh_b.updated_at, version_b.updated_at)
            # Jurnal həlli: A-nın açılışı baza dosyeni (3-cü pillə), B-nin açılışı öz dosyesini tapır.
            self.assertEqual(syllabus_for_offering_obj(CourseOffering.objects.get(pk=self.offering_a.pk)), base_math)
            self.assertEqual(
                syllabus_for_offering_obj(CourseOffering.objects.get(pk=self.offering_b.pk)), self.syllabus_b
            )
            self.assertTrue(AuditLog.objects.filter(resource_type=BATCH_RESOURCE, resource_id="sb-test").exists())
            total = Syllabus.objects.filter(organization=self.org).count()
        again = self._counts(self._run(apply=True))
        self.assertEqual(again["created"], 0)
        self.assertEqual(again["skipped_existing"], 3)
        with bypass_rls():
            self.assertEqual(Syllabus.objects.filter(organization=self.org).count(), total)

    def test_existing_syllabus_as_offering_instructor_is_respected(self):
        """A-nın açılışına bağlı (başqasının yazdığı) sillabus da «var» sayılır — baza yaranmır."""
        with bypass_rls():
            import_migrated_version(
                organization=self.org,
                subject=self.math,
                approved_at=None,
                period=self.period,
                offering=self.offering_a,
                chair_unit=self.chair,
                author=self.b,
            )
        counts = self._counts(self._run(apply=True))
        self.assertEqual(counts["skipped_existing"], 2)
        self.assertEqual(counts["created"], 1)  # yalnız Fizika
        with bypass_rls():
            self.assertFalse(Syllabus.objects.filter(organization=self.org, subject=self.math, author=self.a).exists())

    def test_inactive_base_is_not_touched(self):
        with bypass_rls():
            dormant, _version = import_migrated_version(
                organization=self.org, subject=self.physics, approved_at=None, chair_unit=self.chair, author=self.a
            )
            Syllabus.objects.filter(pk=dormant.pk).update(is_active=False)
        counts = self._counts(self._run(apply=True))
        self.assertEqual(counts["skipped_inactive_base"], 1)
        with bypass_rls():
            self.assertEqual(SyllabusVersion.objects.filter(syllabus=dormant).count(), 1)

    def test_bundle_rejects_regular_phases(self):
        with self.assertRaises(TeacherSyllabiPhaseMismatch):
            self._run(apply=False, phases=("offerings", "syllabi_backfill"))

    def test_choose_source_prefers_journal_then_newest(self):
        bundle = _bundle()
        by_id = {row["id"]: row for row in bundle["syllabi"]}
        by_teacher = {}
        for row in bundle["syllabi"]:
            by_teacher.setdefault(row["teacher_id"], []).append(row)
        run = mock.Mock(legacy_subjects={row["id"]: row for row in bundle["subjects"]})
        own, reason = choose_source(run, [bundle["journals"][0]], 77, 5, by_id, by_teacher)
        self.assertEqual((own["id"], reason), (500, "journal"))
        newest, reason = choose_source(run, [bundle["journals"][1]], 77, 6, by_id, by_teacher)
        self.assertEqual((newest["id"], reason), (601, "teacher_subject"))
        self.assertEqual(choose_source(run, [bundle["journals"][5]], 88, 6, by_id, by_teacher), (None, "empty"))
        self.assertEqual(choose_source(run, [bundle["journals"][4]], 77, 7, by_id, by_teacher), (None, "no_syllabus"))


class _FakeExtractor:
    """``DeltaExtractor``-in ``build_teacher_syllabi_bundle``-in istifadə etdiyi səthi (MariaDB-siz)."""

    src = "`src`"
    chunk = 2

    def __init__(self):
        self.full_semesters = []
        lessons = ((5, "Riyaziyyat"), (6, "Fizika"), (8, "Riyaziyyat"))
        self.tables = {
            "lessons": {pk: {"id": pk, "name": name, "department_id": 3} for pk, name in lessons},
            "workers": {77: {"id": 77, "department_id": 3}, 88: {"id": 88, "department_id": 3}},
            "departments": {3: {"id": 3}},
            "groups": {900: {"id": 900, "name": "101A"}},
        }
        self.sillabus = [(500, 5, 77), (501, 8, 77), (502, 6, 77), (503, 6, 88), (504, 9, 99)]

    def journals(self):
        assert self.full_semesters == [14]
        return [
            {**_journal(11, 5, 77, 500), "students_id": '["1"]', "groups_id": '["900"]'},
            _journal(12, 5, 88, 504),
            _journal(13, 6, 99, fake=1),
        ]

    def _rows(self, sql, params=()):
        if "FROM `src`.sillabus" in sql:
            return [
                {"id": pk, "lesson_id": lesson, "teacher_id": teacher}
                for pk, lesson, teacher in self.sillabus
                if teacher in params
            ]
        if "semestr_jurnal" in sql:
            return [{"id": 14, "name": "2026/2027 Payız", "type": "autumn", "is_current": 1}]
        raise AssertionError(sql)

    def _by_ids(self, table, columns, ids):
        return [self.tables[table][pk] for pk in sorted(ids) if pk in self.tables[table]]

    def syllabi(self, ids):
        return [
            {"id": pk, "lesson_id": lesson, "teacher_id": teacher} for pk, lesson, teacher in self.sillabus if pk in ids
        ]


def test_teacher_syllabi_bundle_shape(tmp_path):
    import pytest

    from apps.legacy_import.services.delta.bundle import read_bundle, write_bundle
    from apps.legacy_import.services.delta.syllabi_backfill import check_phases
    from apps.legacy_import.services.delta.teacher_syllabi_extract import build_teacher_syllabi_bundle

    bundle = build_teacher_syllabi_bundle(_FakeExtractor(), snapshot={"source_schema": "src"}, semester=14)
    assert bundle["snapshot"]["phases"] == ["syllabi_backfill"]
    assert bundle["snapshot"]["teacher_syllabi"]["pairs"] == 2
    assert {row["id"] for row in bundle["journals"]} == {11, 12}, "saxta jurnal atılır"
    assert all(row["students_id"] == "[]" for row in bundle["journals"])
    # Sahib 2026-10-27 (syllabi_share): qrup siyahısı və qrup sətirləri paketdə QALIR.
    assert {row["id"]: row["groups_id"] for row in bundle["journals"]}[11] == '["900"]'
    assert bundle["groups"] == [{"id": 900, "name": "101A"}]
    # 77: Riyaziyyat (5) + eyni adlı dublikat (8); Fizika (502) cütə düşmür. 88: jurnalın öz sillabusu (504).
    assert {row["id"] for row in bundle["syllabi"]} == {500, 501, 504}
    assert bundle["students"] == [] and bundle["points"] == []
    path = tmp_path / "b.json.gz"
    write_bundle(str(path), bundle)
    assert read_bundle(str(path))["snapshot"]["teacher_syllabi"]["semester"] == 14
    check_phases(bundle, ("syllabi_backfill",))
    check_phases(bundle, ("syllabi_share",))
    with pytest.raises(TeacherSyllabiPhaseMismatch):
        check_phases(bundle, ("syllabi", "syllabi_backfill"))

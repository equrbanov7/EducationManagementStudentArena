"""«Bir sillabus — bir neçə jurnal» (sahib 2026-10-27): ``syllabi_share`` fazası, ``syllabi`` fazasının tək idxalı və
``share_legacy_syllabi`` təmir əmri.

Ssenari: köhnə A müəllimi (legacy 77) bir sillabusu (500) iki jurnalda üç qrup üçün işlədib (11: 101 A + 102 A,
12: 103 A); B müəllimi (88) həmin sillabusu öz jurnalında (13: 104 A). Yeni sistemdə 101 A-nın açılışına sillabus
köçüb (lövbər), 102 A / 103 A «sillabus yoxdur».

Yoxlanılır: 102 A və 103 A lövbərə SURƏTSİZ bağlanır (jurnal, tələbə, həftəlik plan eyni dosyeni görür); B-nin
qrupu (başqa müəllim) toxunulmur; öz dosyesi olan qrup üstünə yazılmır; dry-run heç nə yazmır; ikinci qaçış 0;
``--teacher`` süzgəci; yeni ``syllabi`` idxalı eyni sillabusu bir dəfə yaradıb qalanlarını paylaşır.
"""

import datetime as dt
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.legacy_import.services.delta.apply import DeltaRun, execute
from apps.legacy_import.services.delta.journals import JournalSlices
from apps.legacy_import.services.delta.syllabi import document_for, import_syllabi
from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.syllabus.models import ShareSource, Syllabus, SyllabusShare
from apps.syllabus.services.drafts import import_migrated_version
from apps.syllabus.services.offerings import syllabus_for_offering_obj
from apps.syllabus.services.student_lookup import student_syllabus_map
from apps.syllabus.services.week_rows import approved_week_rows_for_offerings
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()
UNTIL = dt.date(2026, 10, 27)
PHASE = "syllabi_share"


def _journal(pk, teacher_id, groups, sillabus_id=500, lesson_id=5):
    return {
        "id": pk,
        "uniqid": f"uq{pk}",
        "lesson_id": lesson_id,
        "teacher_id": teacher_id,
        "groups_id": "[" + ", ".join(f'"{group}"' for group in groups) + "]",
        "students_id": "[]",
        "semestr": 14,
        "fake": 0,
        "sonra_sil": 0,
        "active": 1,
        "fenn_saati": 45,
        "kredit": 5,
        "sillabus_id": sillabus_id,
    }


def _legacy_syllabus(pk=500, topic="Potok mövzusu"):
    return {
        "id": pk,
        "uniqid": f"syl{pk}",
        "lesson_id": 5,
        "teacher_id": 77,
        "ders_saati": 45,
        "language": "az",
        "active": 1,
        "is_new": False,
        "is_changed": False,
        "week": [
            {
                "id": pk * 10,
                "uniqid": f"w{pk}",
                "movzu": topic,
                "muh_saat": "2",
                "sem_saat": "2",
                "praktiki_saat": "",
                "lab_saat": "",
                "qeyd": "",
            }
        ],
        "sections": {"sillabus_tesviri_ve_meqsedi": [[pk, f"Təsvir {pk}"]]},
    }


def _bundle(journals=None):
    return {
        "snapshot": {"sha256": "0" * 64, "full_semesters": [], "phases": [PHASE]},
        "periods": [{"id": 14, "name": "2026/2027 Payız", "type": "autumn", "is_current": 1}],
        "departments": [],
        "specialities": [],
        "groups": [{"id": 900 + index, "name": f"10{index} A"} for index in range(1, 5)],
        "subjects": [{"id": 5, "name": "Riyaziyyat", "lesson_code": "", "department_id": 3, "type": ""}],
        "workers": [],
        "students": [],
        "expelled_students": [],
        "journals": journals or [_journal(11, 77, [901, 902]), _journal(12, 77, [903]), _journal(13, 88, [904])],
        "lesson_dates": [],
        "points": [],
        "excuse_windows": [],
        "lesson_topics": [],
        "syllabi": [_legacy_syllabus()],
    }


class _World(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("ss_actor", "ss-actor@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SS Univ",
                slug="ss-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(organization=cls.org, name="Fakültə", slug="ss-fac", unit_type="faculty")
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="ss-chair", unit_type="chair", parent=faculty
            )
            cls.groups = {
                index: OrgUnit.objects.create(
                    organization=cls.org, name=f"10{index} A", slug=f"ss-g{index}", unit_type="group"
                )
                for index in range(1, 5)
            }
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
            role = cls.org.roles.get(name="teacher")
            cls.a = User.objects.create_user("ss.a", "ss-a@example.test", "x", first_name="Birinci", last_name="A")
            cls.b = User.objects.create_user("ss.b", "ss-b@example.test", "x", first_name="İkinci", last_name="B")
            for user in (cls.a, cls.b):
                Membership.objects.create(
                    user=user, organization=cls.org, role=role, scope_unit=cls.chair, is_active=True
                )
            cls.offerings = {
                index: CourseOffering.objects.create(
                    organization=cls.org,
                    subject=cls.math,
                    period=cls.period,
                    group=cls.groups[index],
                    instructor=cls.a if index < 4 else cls.b,
                    lesson_hours=45,
                )
                for index in range(1, 5)
            }
            # Lövbər: köhnə sillabus 101 A-nın açılışına köçüb (delta ``syllabi`` fazası ilə eyni çevirici).
            section_data, _codes = build_section_data(document_for(_legacy_syllabus()))
            cls.anchor, _version = import_migrated_version(
                organization=cls.org,
                subject=cls.math,
                approved_at=None,
                period=cls.period,
                offering=cls.offerings[1],
                chair_unit=cls.chair,
                author=cls.a,
                section_data=section_data,
            )

    def _run(self, *, apply, bundle=None, teacher_id=None):
        with bypass_rls():
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=bundle or _bundle(),
                apply=apply,
                until=UNTIL,
                tag="ss-test",
                phases=(PHASE,),
                setup=lambda run: setattr(run, "share_teacher_id", teacher_id),
            )

    @staticmethod
    def _counts(run):
        prefix = f"{PHASE}."
        return {key[len(prefix) :]: value for key, value in run.counters.items() if key.startswith(prefix)}

    def _offering(self, index):
        return CourseOffering.objects.get(pk=self.offerings[index].pk)


class SyllabiShareTests(_World):
    def test_dry_run_counts_and_writes_nothing(self):
        counts = self._counts(self._run(apply=False))
        self.assertEqual(counts["linked"], 2)
        self.assertEqual(counts["anchored"], 1)
        self.assertEqual(counts["multi_group"], 1, "B-nin tək qrupu paylaşım dəsti deyil")
        with bypass_rls():
            self.assertFalse(SyllabusShare.objects.exists())

    def test_apply_links_other_groups_to_one_syllabus_and_is_idempotent(self):
        counts = self._counts(self._run(apply=True))
        self.assertEqual(counts["linked"], 2)
        with bypass_rls():
            shares = SyllabusShare.objects.filter(syllabus=self.anchor)
            self.assertEqual(
                set(shares.values_list("offering_id", flat=True)), {self.offerings[2].pk, self.offerings[3].pk}
            )
            self.assertEqual(set(shares.values_list("source", flat=True)), {ShareSource.LEGACY.value})
            self.assertEqual(Syllabus.objects.filter(organization=self.org).count(), 1, "surət yaranmır")
            offerings = [self._offering(index) for index in range(1, 5)]
            for offering in offerings[:3]:
                self.assertEqual(syllabus_for_offering_obj(offering), self.anchor)
            self.assertIsNone(syllabus_for_offering_obj(offerings[3]), "başqa müəllimin qrupu toxunulmur")
            student = student_syllabus_map(self.org, offerings)
            self.assertEqual({student[offering.pk] for offering in offerings[:3]}, {self.anchor.pk})
            weeks = approved_week_rows_for_offerings(offerings)
            self.assertIn("Potok mövzusu", str(weeks[self.offerings[3].pk]))
        again = self._counts(self._run(apply=True))
        self.assertEqual((again["linked"], again["covered"]), (0, 2))
        with bypass_rls():
            self.assertEqual(SyllabusShare.objects.count(), 2)

    def test_group_with_own_syllabus_is_not_overwritten(self):
        with bypass_rls():
            own, _version = import_migrated_version(
                organization=self.org,
                subject=self.math,
                approved_at=None,
                period=self.period,
                offering=self.offerings[2],
                chair_unit=self.chair,
                author=self.a,
            )
        counts = self._counts(self._run(apply=True))
        self.assertEqual((counts["linked"], counts["own_copy"]), (1, 1))
        with bypass_rls():
            self.assertEqual(syllabus_for_offering_obj(self._offering(2)), own)
            self.assertFalse(SyllabusShare.objects.filter(offering=self.offerings[2]).exists())

    def test_different_content_is_not_an_anchor(self):
        bundle = _bundle()
        bundle["syllabi"] = [_legacy_syllabus(topic="Başqa mövzu")]
        counts = self._counts(self._run(apply=True, bundle=bundle))
        self.assertEqual((counts["linked"], counts["no_anchor"]), (0, 1))

    def test_teacher_filter(self):
        counts = self._counts(self._run(apply=False, teacher_id=self.b.pk))
        self.assertEqual((counts["linked"], counts["teacher_filtered"]), (0, 1))
        counts = self._counts(self._run(apply=False, teacher_id=self.a.pk))
        self.assertEqual(counts["linked"], 2)

    def test_share_stops_applying_when_the_journal_changes_teacher(self):
        self._run(apply=True)
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.offerings[3].pk).update(instructor=self.b)
            self.assertIsNone(syllabus_for_offering_obj(self._offering(3)))
            self.assertNotIn(self.offerings[3].pk, student_syllabus_map(self.org, [self._offering(3)]))

    def test_command_prints_counts_only(self):
        import tempfile

        from apps.legacy_import.services.delta.bundle import write_bundle

        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/delta.json.gz"
            write_bundle(path, _bundle())
            out = io.StringIO()
            with (
                mock.patch("apps.legacy_import.management.commands.share_legacy_syllabi.assert_writable_target"),
                bypass_rls(),
            ):
                call_command(
                    "share_legacy_syllabi", "--bundle", path, "--organization", self.org.slug, "--apply", stdout=out
                )
            line = out.getvalue().strip()
            self.assertTrue(line.startswith("syllabi_share: mode=apply "), line)
            self.assertIn(" linked=2 ", line)
            self.assertNotIn("Riyaziyyat", line)
            with self.assertRaises(CommandError):
                call_command(
                    "share_legacy_syllabi", "--bundle", path, "--organization", self.org.slug, "--teacher", "yoxdur"
                )
            empty = _bundle()
            empty["groups"] = []
            write_bundle(path, empty)
            with self.assertRaisesMessage(CommandError, "syllabi_share_bundle_without_groups"):
                call_command("share_legacy_syllabi", "--bundle", path, "--organization", self.org.slug)


class SyllabiPhaseSingleImportTests(_World):
    """Yeni ``syllabi`` idxalı: eyni köhnə sillabus eyni müəllimin qruplarına BİR dəfə köçür, qalanları paylaşılır."""

    def test_import_creates_one_syllabus_and_shares_the_rest(self):
        with bypass_rls():
            Syllabus.objects.filter(pk=self.anchor.pk).delete()
            run = DeltaRun(organization=self.org, actor=self.actor, bundle=_bundle(), tag="ss-imp", until=UNTIL)
            first, second = JournalSlices(_journal(11, 77, [901, 902])), JournalSlices(_journal(13, 88, [904]))
            first.offerings = [self._offering(1), self._offering(2), self._offering(3)]
            second.offerings = [self._offering(4)]
            for entry in (first, second):
                entry.writable = {offering.pk for offering in entry.offerings}
            import_syllabi(run, {"uq11": first, "uq13": second})
            self.assertEqual(run.counters["syllabus.offering_imported"], 2, "A üçün bir, B üçün bir")
            self.assertEqual(run.counters["syllabus.offering_shared_linked"], 2)
            own_a = Syllabus.objects.get(organization=self.org, offering=self.offerings[1])
            for index in (2, 3):
                self.assertEqual(syllabus_for_offering_obj(self._offering(index)), own_a)
            self.assertTrue(Syllabus.objects.filter(offering=self.offerings[4], author=self.b).exists())
            # İdempotent: ikinci qaçış heç nə yaratmır.
            import_syllabi(run, {"uq11": first, "uq13": second})
            self.assertEqual(run.counters["syllabus.offering_imported"], 2)
            self.assertEqual(run.counters["syllabus.offering_has_syllabus"], 4)


def test_prod_data_ops_wires_the_command_without_new_inputs():
    import re
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
    text = path.read_text(encoding="utf-8")
    assert "          - share_legacy_syllabi\n" in text
    assert text.count("            share_legacy_syllabi)\n") == 2  # şifrəli paket + icra bloku
    pattern = "^syllabi_share: [a-z_]+=[0-9a-z_]+( [a-z_]+=[0-9a-z_]+)*$"
    assert pattern in text
    assert "/tmp/legacy_share_*.json.gz" in text
    inputs = yaml.safe_load(text)[True]["workflow_dispatch"]["inputs"]
    assert len(inputs) <= 25
    sample = "syllabi_share: mode=dry_run legacy_syllabi=3 linked=2 teacher_filtered=0"
    assert re.match(pattern, sample)

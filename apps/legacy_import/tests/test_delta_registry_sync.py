"""DELTA ``registry_sync`` fazası — aktiv reyestrin köhnə sistemlə rəsmi əmrlərlə nizamlanması (sintetik data).

Yoxlanılır: cutover-dən sonra köhnə sistemdə dəyişən qrup → rəsmi ``group_transfer``; azad edilmə → ``expulsion``
(köhnə əmr nömrəsi ilə); yeni sistemdə əl ilə dəyişiklik, dəyişməmiş köhnə qrup, alt qrup ↔ ana qrup və başqa
ixtisas — toxunulmur; dry-run heç nə yazmır; ikinci qaçış 0 yazı; faza default fazalara DAXİL DEYİL.
"""

import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.legacy_import.services.delta.apply import DEFAULT_PHASES, PHASES, execute
from apps.legacy_import.services.delta.registry_sync import SYNC_REASON
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord, StudentMovement
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()


def _group(pk, name, speciality=5):
    return {
        "id": pk,
        "name": name,
        "speciality_id": speciality,
        "department_id": 3,
        "start_year": 2025,
        "eyani_qiyabi": "Əyani",
        "bak_or_mag": "bak",
        "sector": "az",
        "kollec_or_uni": "University",
        "is_new": False,
    }


def _student(pk, fin, group_id, *, azad=0, baseline=None, is_new=False, **extra):
    row = {
        "id": pk,
        "first_name": f"Ad{pk}",
        "last_name": f"Soyad{pk}",
        "father_name": "",
        "fincode": fin,
        "sex": 1,
        "gender": None,
        "birthday": "",
        "group_id": group_id,
        "speciality_id": 5,
        "entry_year": "2025",
        "azadedildi": azad,
        "is_new": is_new,
        **extra,
    }
    if baseline is not None:
        row["baseline"] = baseline
    return row


def _bundle():
    return {
        "snapshot": {"phases": ["registry_sync"], "full_semesters": [14]},
        "periods": [],
        "groups": [_group(900, "201 A"), _group(901, "201 A1"), _group(902, "201 B"), _group(903, "201 X", 6)],
        "subjects": [],
        "workers": [],
        "students": [
            # köçürmə: köhnə sistemdə 900 → 902 (cutover-dən sonra)
            _student(1, "FIN0001", 902, baseline={"group_id": 900, "azadedildi": 0}),
            # azad edilib (cutover-dən sonra), əmr köhnə sistemdən
            _student(
                2,
                "FIN0002",
                900,
                azad=1,
                baseline={"group_id": 900, "azadedildi": 0},
                order_no="77",
                order_date="2026-10-02 00:00:00",
            ),
            # köhnə sistemdə dəyişib, amma yeni sistemdə əl ilə köçürmə izi var → toxunulmur
            _student(3, "FIN0003", 902, baseline={"group_id": 900, "azadedildi": 0}),
            # köhnə sistemdə dəyişməyib, yeni sistemdə başqa qrupdadır → yeni sistem qalibdir
            _student(4, "FIN0004", 900),
            # yeni tələbə alt qrupda («201 A1»), yeni sistemdə ana qrupda → köçürmə deyil
            _student(5, "FIN0005", 901, is_new=True),
            # başqa ixtisasın qrupuna → proqram qərarıdır, toxunulmur
            _student(7, "FIN0007", 903, is_new=True),
        ],
        "expelled_students": [
            _student(6, "FIN0006", 900, azad=1, order_no="", order_date=None),
            _student(8, "FIN0001", 900, azad=1),  # əsas bölmədə olan adamın köhnə sətri — toxunulmur
        ],
    }


class RegistrySyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("sync_actor", "sync-actor@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Sync Univ",
                slug="sync-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(organization=cls.org, name="Fakültə", slug="s-fac", unit_type="faculty")
            specialty = OrgUnit.objects.create(
                organization=cls.org, name="İxtisas", slug="s-spec", unit_type="specialty", parent=faculty
            )
            other = OrgUnit.objects.create(
                organization=cls.org, name="Başqa ixtisas", slug="s-spec2", unit_type="specialty", parent=faculty
            )

            def group(name, slug, parent=specialty, **settings):
                return OrgUnit.objects.create(
                    organization=cls.org, name=name, slug=slug, unit_type="group", parent=parent, settings=settings
                )

            cls.g_a = group("201 A", "myedu-grp-900")
            cls.g_a1 = group("201 A1", "myedu-grp-901", parent_group=str(cls.g_a.pk))
            cls.g_b = group("201 B", "myedu-grp-902")
            cls.g_x = group("201 X", "myedu-grp-903", parent=other)
            program = Program.objects.create(organization=cls.org, code="SYN", name="Proqram", specialty_unit=specialty)
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2025)
            AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2026, 9, 15),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            role = cls.org.roles.get(name="student")
            cls.records = {}
            for number, home in ((1, cls.g_a), (2, cls.g_a), (3, cls.g_a), (4, cls.g_b), (5, cls.g_a), (6, cls.g_a)):
                user = User.objects.create_user(f"sync.s{number}", f"s{number}@example.test", "x")
                UserProfile.objects.filter(user=user).update(fin=f"FIN000{number}")
                Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
                cls.records[number] = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=program,
                    curriculum=curriculum,
                    group=home,
                    admission_year=2025,
                    status="enrolled",
                    is_active=True,
                )
            user = User.objects.create_user("sync.s7", "s7@example.test", "x")
            UserProfile.objects.filter(user=user).update(fin="FIN0007")
            Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
            cls.records[7] = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                program=program,
                curriculum=curriculum,
                group=cls.g_a,
                admission_year=2025,
                status="enrolled",
                is_active=True,
            )
            # Yeni sistemdə RİM-in əl ilə etdiyi köçürmə izi (cutover-dən sonra).
            AuditLog.objects.create(
                organization=cls.org,
                action="update",
                resource_type="registrar.group_transfer",
                resource_id=str(cls.records[3].pk),
                reason="RİM əmri",
            )

    def _run(self, *, apply, phases=("registry_sync",)):
        with bypass_rls():
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=_bundle(),
                apply=apply,
                until=dt.date(2026, 10, 21),
                tag="sync-test",
                phases=phases,
            )

    def _state(self, number):
        with bypass_rls():
            record = StudentAcademicRecord.objects.get(pk=self.records[number].pk)
        return record.group_id, record.status

    def test_phase_is_opt_in(self):
        self.assertIn("registry_sync", PHASES)
        self.assertNotIn("registry_sync", DEFAULT_PHASES)

    def test_dry_run_writes_nothing(self):
        run = self._run(apply=False)
        self.assertEqual(run.counters["registry.group.transfer.moved"], 1)
        self.assertEqual(run.counters["written.student_movements"], 3)
        self.assertEqual(self._state(1), (self.g_a.pk, "enrolled"))
        with bypass_rls():
            self.assertFalse(StudentMovement.objects.filter(organization=self.org).exists())

    def test_apply_uses_official_movements_and_second_run_is_noop(self):
        run = self._run(apply=True)
        counters = run.counters
        self.assertEqual(counters["registry.group.transfer.moved"], 1)
        self.assertEqual(counters["registry.expel.in_snapshot"], 1)
        self.assertEqual(counters["registry.expel.not_in_snapshot"], 1)
        self.assertEqual(counters["registry.expelled_readmitted"], 1)
        self.assertEqual(counters["registry.group.system_changed"], 1)
        self.assertEqual(counters["registry.group.legacy_unchanged_system_wins"], 1)
        self.assertEqual(counters["registry.group.subgroup_parent"], 1)
        self.assertEqual(counters["registry.group.other_speciality"], 1)
        self.assertEqual((counters["registry.active_before"], counters["registry.active_after"]), (7, 5))

        self.assertEqual(self._state(1), (self.g_b.pk, "enrolled"))
        self.assertEqual(self._state(2), (self.g_a.pk, "expelled"))
        self.assertEqual(self._state(3), (self.g_a.pk, "enrolled"))
        self.assertEqual(self._state(4), (self.g_b.pk, "enrolled"))
        self.assertEqual(self._state(5), (self.g_a.pk, "enrolled"))
        self.assertEqual(self._state(6), (self.g_a.pk, "expelled"))
        self.assertEqual(self._state(7), (self.g_a.pk, "enrolled"))
        with bypass_rls():
            transfer = StudentMovement.objects.get(record=self.records[1])
            self.assertEqual((transfer.kind, transfer.order_number), ("group_transfer", "KS-SINX-20261021"))
            self.assertTrue(transfer.reason.startswith(SYNC_REASON))
            expel = StudentMovement.objects.get(record=self.records[2])
            self.assertEqual(
                (expel.kind, expel.order_number, expel.order_date), ("expulsion", "77", dt.date(2026, 10, 2))
            )
            fallback = StudentMovement.objects.get(record=self.records[6])
            self.assertEqual(fallback.order_number, "KS-SINX-20261021")
            self.assertEqual(
                UserProfile.objects.get(user=self.records[2].student).access_state, UserProfile.AccessState.ARCHIVED
            )

        again = self._run(apply=True)
        self.assertEqual(again.counters["written.student_movements"], 0)
        self.assertEqual(again.counters["registry.group.same"], 1)
        self.assertEqual(again.counters["registry.already_closed"], 2)
        with bypass_rls():
            self.assertEqual(StudentMovement.objects.filter(organization=self.org).count(), 3)

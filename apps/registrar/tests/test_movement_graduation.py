"""«Məzun etmə» hərəkəti (sahib 2026-10-25) — status, qeydiyyat, giriş və bərpa (undo).

* ``graduation`` yalnız ``enrolled``-dən; nəticə ``graduated``, ``is_active=False``;
* cari dövrün açıq qeydiyyatı dondurulur (xaric etmə kimi), keçmiş tarixçə toxunulmur;
* hesabın girişi bağlanır — amma eyni adamın BAŞQA aktiv qeydi varsa nə giriş, nə qeydiyyat toxunulur;
* «Bərpa» əmri məzunu geri qaytarır (status + dondurulmuş qeydiyyatlar).
"""

from apps.accounts.models import UserProfile
from apps.registrar import movements
from apps.registrar.models import AcademicStatus, Curriculum, Enrollment, MovementKind, Program, StudentAcademicRecord
from core.rls import bypass_rls
from core.ui import status_catalog

from .test_audit_2026_09_28_b2_lifecycle import _LifecycleBase


class GraduationMovementTest(_LifecycleBase):
    def _profile(self):
        return UserProfile.objects.filter(user=self.student).first()

    def test_kind_is_in_catalog_and_rules(self):
        self.assertIn("graduation", status_catalog.keys("student_movement"))
        rule = movements.RULES[MovementKind.GRADUATION]
        self.assertEqual(rule.from_statuses, (AcademicStatus.ENROLLED,))
        self.assertEqual(rule.to_status, AcademicStatus.GRADUATED)
        self.assertIn(AcademicStatus.GRADUATED, movements.RULES[MovementKind.REINSTATEMENT].from_statuses)

    def test_graduation_closes_record_enrollments_and_access(self):
        movement = self._move("graduation")
        self.record.refresh_from_db()
        self.assertEqual((self.record.status, self.record.is_active), (AcademicStatus.GRADUATED, False))
        self.assertEqual((movement.from_status, movement.to_status), ("enrolled", "graduated"))
        self.assertEqual(self._status(self.current), Enrollment.Status.SUSPENDED)
        self.assertEqual(self._status(self.history), Enrollment.Status.COMPLETED)
        profile = self._profile()
        if profile is not None:
            self.assertEqual(profile.access_state, UserProfile.AccessState.ARCHIVED)

    def test_reinstatement_undoes_graduation(self):
        self._move("graduation")
        self._move("reinstatement", new_group=self.group1)
        self.record.refresh_from_db()
        self.assertEqual((self.record.status, self.record.is_active), (AcademicStatus.ENROLLED, True))
        self.assertEqual(self._status(self.current), Enrollment.Status.ENROLLED)

    def test_graduation_requires_enrolled_status(self):
        self._move("expulsion")
        with self.assertRaises(movements.MovementError) as caught:
            self._move("graduation")
        self.assertEqual(caught.exception.code, "illegal_transition")

    def test_other_active_record_keeps_access_and_enrollments(self):
        with bypass_rls():
            master = Program.objects.create(
                organization=self.org, code="B2MS", name="Magistr", degree_level="master", ects_total=120
            )
            curriculum = Curriculum.objects.create(organization=self.org, program=master, admission_year=2024)
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=master,
                curriculum=curriculum,
                group=self.group2,
                admission_year=2024,
            )
            UserProfile.objects.filter(user=self.student).update(access_state=UserProfile.AccessState.ACTIVE)
        self._move("graduation")
        self.assertEqual(self._status(self.current), Enrollment.Status.ENROLLED)
        profile = self._profile()
        if profile is not None:
            self.assertEqual(profile.access_state, UserProfile.AccessState.ACTIVE)

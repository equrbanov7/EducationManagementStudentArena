"""Dərs yükü payı alt qrup (Lab-1 / Lab-2) səviyyəsində (sahib 2026-11-09): ``sections`` → payın tələbə siyahısı
yalnız həmin lab qrupu; bölmə götürüləndə siyahı boşalır; əl ilə məhdudlaşdırılmış pay qorunur."""

from __future__ import annotations

from apps.registrar.journal_workload_shares import SECTIONS_BATCH, sync_workload_journal_shares
from apps.registrar.models import Enrollment, JournalShare, JournalShareSource
from core.rls import bypass_rls

from .test_journal_shares_2026_10_26 import _add_teacher, _ShareBase


class SectionSharesTest(_ShareBase):
    def _plan(self, teachers, sections):
        key = (self.offering.subject_id, self.offering.period_id, self.offering.group_id)
        return {key: {"owner_id": self.teacher.pk, "teachers": teachers, "sections": sections, "ambiguous": False}}

    def _sync(self, plans):
        with bypass_rls():
            return sync_workload_journal_shares(
                organization_id=self.org.pk, offering_ids=[self.offering.pk], plans=plans, by_user=self.owner
            )

    def test_sections_scope_the_share_to_the_lab_group(self):
        with bypass_rls():
            lab2 = _add_teacher(type(self), "jsx_lab2")
            Enrollment.objects.filter(pk=self.e1.pk).update(lab_group=1)
            Enrollment.objects.filter(pk=self.e2.pk).update(lab_group=2)
        counts = self._sync(
            self._plan(
                {self.teacher.pk: {"lecture", "lab"}, lab2.pk: {"lab"}},
                {self.teacher.pk: {"lab": [1]}, lab2.pk: {"lab": [2]}},
            )
        )
        self.assertEqual(counts["created"], 2)
        with bypass_rls():
            owner = JournalShare.objects.get(offering=self.offering, teacher=self.teacher, is_active=True)
            other = JournalShare.objects.get(offering=self.offering, teacher=lab2, is_active=True)
            self.assertEqual(
                (owner.kinds, set(owner.enrollments.values_list("pk", flat=True)), owner.batch),
                (["lab", "lecture"], {self.e1.pk}, SECTIONS_BATCH),
            )
            self.assertEqual(
                (other.kinds, set(other.enrollments.values_list("pk", flat=True)), other.batch),
                (["lab"], {self.e2.pk}, SECTIONS_BATCH),
            )
            self.assertEqual(other.source, JournalShareSource.WORKLOAD)
        # Bölmə götürülür: siyahı boşalır, işarə silinir; ikinci müəllim yükdən çıxır: pay deaktiv.
        counts = self._sync(self._plan({self.teacher.pk: {"lecture", "lab"}, lab2.pk: {"lab"}}, {}))
        with bypass_rls():
            owner.refresh_from_db()
            other.refresh_from_db()
            self.assertEqual((owner.enrollments.count(), owner.batch), (0, ""))
            self.assertEqual((other.enrollments.count(), other.batch), (0, ""))
        # Tək sahib qalır — ayrıca paya ehtiyac yoxdur: hər iki pay deaktiv (mövcud qayda).
        counts = self._sync(self._plan({self.teacher.pk: {"lecture", "lab"}}, {}))
        with bypass_rls():
            other.refresh_from_db()
            owner.refresh_from_db()
        self.assertEqual((other.is_active, owner.is_active, counts["deactivated"]), (False, False, 2))

    def test_manually_limited_share_is_preserved(self):
        with bypass_rls():
            lab2 = _add_teacher(type(self), "jsx_lab3")
        manual = self._share(lab2, kinds=["lab"], enrollments=[self.e2], source=JournalShareSource.WORKLOAD)
        counts = self._sync(self._plan({self.teacher.pk: {"lecture", "lab"}, lab2.pk: {"lab"}}, {}))
        self.assertGreaterEqual(counts["preserved"], 1)
        with bypass_rls():
            manual.refresh_from_db()
            self.assertEqual((manual.batch, set(manual.enrollments.values_list("pk", flat=True))), ("", {self.e2.pk}))

"""«Bölgü sehrbazı»nın jurnal tərəfi (sahib 2026-11-26) — ``apps.registrar.public`` fasadı.

Nəyi qoruyur
------------
* ``split_wizard_apply_sections``: seminar alt qrupları + lab qrupları bir çağırışda (1..N nömrə, ad, mənbə alt qrup),
  tələbələr yerləşir; təkrar çağırış heç nə yazmır; ``None`` növə toxunulmur; say ≤ 1 — bölmələr silinir;
* rədlər: yerləşdirilməmiş tələbə, iç-içə rejimdə qarışıq lab qrupu, dərsi olan bölmənin silinməsi, eyni ad,
  səlahiyyətsiz aktor (403), keçmiş dövr (409) — heç biri heç nə yazmır;
* ``split_wizard_journal_state``: siyahı, bölmələr, bağlı dərs sayı, aktorun səlahiyyəti.
"""

from __future__ import annotations

from apps.organizations.models import AcademicPeriod
from apps.registrar.models import Enrollment, LabGroup, LessonKind, SeminarGroup
from apps.registrar.public import (
    SplitWizardSectionError,
    split_wizard_apply_sections,
    split_wizard_journal_state,
)
from core.rls import bypass_rls

from .test_lab_groups_manage_2026_11_06 import LabManageBase


class SplitWizardSectionsTest(LabManageBase):
    PREFIX = "swsec"

    @property
    def key(self):
        return (self.offering.subject_id, self.offering.period_id, self.offering.group_id)

    def roster(self):
        with bypass_rls():
            return list(
                Enrollment.objects.filter(offering=self.offering, status=Enrollment.Status.ENROLLED).order_by("pk")
            )

    def apply(self, user=None, **kwargs):
        return split_wizard_apply_sections(organization=self.org, user=user or self.chair_head, key=self.key, **kwargs)

    def two_by_two(self):
        ids = [str(row.pk) for row in self.roster()]
        half = len(ids) // 2
        return {
            "seminar": {
                "count": 2,
                "names": ["A1", "A2"],
                "placement": {pk: 1 if i < half else 2 for i, pk in enumerate(ids)},
            },
            "lab": {
                "count": 4,
                "nested": True,
                "names": ["A1 · Lab-1", "A1 · Lab-2", "A2 · Lab-1", "A2 · Lab-2"],
                "placement": {pk: (1 if i < half else 3) + (i % 2) for i, pk in enumerate(ids)},
            },
        }

    def state(self):
        with bypass_rls():
            return dict(SeminarGroup.objects.filter(offering=self.offering).values_list("number", "name")), dict(
                LabGroup.objects.filter(offering=self.offering).values_list("number", "name")
            )

    def test_two_by_two_is_created_and_resave_is_a_no_op(self):
        result = self.apply(**self.two_by_two())
        self.assertTrue(result["changed"])
        seminars, labs = self.state()
        self.assertEqual(seminars, {1: "A1", 2: "A2"})
        self.assertEqual(sorted(labs), [1, 2, 3, 4])
        for row in self.roster():
            self.assertEqual((row.lab_group - 1) // 2 + 1, row.seminar_group, "lab qrupu öz seminar alt qrupundadır")
        again = self.apply(**self.two_by_two())
        self.assertEqual(again, {"changed": False, "students": 0, "sections": 0})

        state = split_wizard_journal_state(organization=self.org, user=self.chair_head, keys={self.key})[self.key]
        self.assertTrue(state["can_manage"])
        self.assertEqual([s["label"] for s in state["seminar"]], ["A1", "A2"])
        self.assertEqual(len(state["students"]), len(self.roster()))

    def test_none_kind_is_untouched_and_count_one_clears(self):
        self.apply(**self.two_by_two())
        self.apply(seminar={"count": 0}, lab=None)
        seminars, labs = self.state()
        self.assertEqual((seminars, sorted(labs)), ({}, [1, 2, 3, 4]))
        self.assertTrue(all(row.seminar_group is None and row.lab_group for row in self.roster()))

    def test_rejections_write_nothing(self):
        payload = self.two_by_two()
        bad = dict(payload, seminar=dict(payload["seminar"], placement={}))
        with self.assertRaises(SplitWizardSectionError) as ctx:
            self.apply(**bad)
        self.assertEqual(ctx.exception.code, "unplaced")
        mixed = dict(payload, lab=dict(payload["lab"], placement={pk: 1 for pk in payload["lab"]["placement"]}))
        with self.assertRaises(SplitWizardSectionError) as ctx:
            self.apply(**mixed)
        self.assertEqual(ctx.exception.code, "lab_mixed")
        twins = dict(payload, seminar=dict(payload["seminar"], names=["Eyni", "eyni"]))
        with self.assertRaises(SplitWizardSectionError) as ctx:
            self.apply(**twins)
        self.assertEqual(ctx.exception.code, "duplicate_name")
        with self.assertRaises(SplitWizardSectionError) as ctx:
            self.apply(user=self.other_teacher, **payload)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("forbidden", 403))
        self.assertEqual(self.state(), ({}, {}))

    def test_section_with_lessons_cannot_be_removed(self):
        self.apply(**self.two_by_two())
        self.lesson(lab_group=4)
        payload = self.two_by_two()
        payload["lab"] = {
            "count": 2,
            "nested": False,
            "names": ["", ""],
            "placement": {pk: 1 + i % 2 for i, pk in enumerate(payload["lab"]["placement"])},
        }
        with self.assertRaises(SplitWizardSectionError) as ctx:
            self.apply(**payload)
        self.assertEqual(ctx.exception.code, "has_lessons")
        self.assertEqual(sorted(self.state()[1]), [1, 2, 3, 4])

    def test_seminar_lesson_counts_are_reported(self):
        self.apply(**self.two_by_two())
        self.lesson(kind=LessonKind.SEMINAR, lab_group=None)
        with bypass_rls():
            from apps.registrar.models import Lesson

            Lesson.objects.filter(offering=self.offering, kind=LessonKind.SEMINAR).update(seminar_group=2)
        state = split_wizard_journal_state(organization=self.org, user=self.chair_head, keys={self.key})[self.key]
        self.assertEqual([s["lessons"] for s in state["seminar"]], [0, 1])

    def test_past_period_is_blocked(self):
        with bypass_rls():
            AcademicPeriod.objects.filter(pk=self.offering.period_id).update(is_current=False)
        with self.assertRaises(SplitWizardSectionError) as ctx:
            self.apply(**self.two_by_two())
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("blocked", 409))
        self.assertEqual(self.state(), ({}, {}))

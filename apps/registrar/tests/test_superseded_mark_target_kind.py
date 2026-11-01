"""Transfer targets must preserve the source teaching component."""

from datetime import time
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.registrar.superseded_marks import _pick_target


class SupersededMarkTargetKindTests(SimpleTestCase):
    def lesson(self, kind, hour=10):
        return SimpleNamespace(kind=kind, start_time=time(hour))

    def test_same_time_other_kind_is_never_a_target(self):
        source = self.lesson("seminar")
        self.assertEqual(_pick_target([self.lesson("lecture")], source), (None, "no_target_lesson"))

    def test_same_time_correct_kind_wins_over_other_component(self):
        source = self.lesson("seminar")
        target = self.lesson("seminar")
        self.assertEqual(_pick_target([self.lesson("lecture"), target], source), (target, ""))

    def test_other_component_at_same_time_cannot_override_unique_same_kind(self):
        source = self.lesson("seminar")
        target = self.lesson("seminar", 12)
        self.assertEqual(_pick_target([self.lesson("lecture"), target], source), (target, ""))

    def test_duplicate_same_component_and_time_stays_ambiguous(self):
        source = self.lesson("seminar")
        self.assertEqual(
            _pick_target([self.lesson("seminar"), self.lesson("seminar")], source),
            (None, "ambiguous_target_lesson"),
        )

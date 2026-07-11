"""EXAM-P1-20 — imtahan biznes SLI metriklərinin təhlükəsiz olması.

record_* köməkçiləri heç bir halda (prometheus olsun/olmasın) exception
atmamalıdır — metrik yazısı biznes axınını pozmamalıdır.
"""

from django.test import SimpleTestCase

from apps.exams import metrics


class BusinessMetricsSafetyTests(SimpleTestCase):
    def test_all_record_helpers_are_safe(self):
        # Heç biri exception atmamalıdır.
        metrics.record_attempt_started("test")
        metrics.record_attempt_submitted("test", "submitted")
        metrics.record_autosave("ok")
        metrics.record_result_published("published")
        metrics.record_pin_attempt("success")
        metrics.record_pin_attempt("failure")
        metrics.record_supervision_incident("tab_switched")

    def test_handles_none_labels_gracefully(self):
        metrics.record_attempt_started(None)
        metrics.record_supervision_incident(None)

    def test_counter_helpers_really_increment_registered_counters(self):
        if not metrics._ENABLED:
            self.skipTest("prometheus_client quraşdırılmayıb")

        started = metrics.exam_attempt_started_total.labels(exam_type="counter_probe")
        submitted = metrics.exam_attempt_submitted_total.labels(exam_type="counter_probe", outcome="submitted")
        autosave = metrics.exam_autosave_total.labels(result="counter_probe")
        before = (started._value.get(), submitted._value.get(), autosave._value.get())

        metrics.record_attempt_started("counter_probe")
        metrics.record_attempt_submitted("counter_probe", "submitted")
        metrics.record_autosave("counter_probe")

        after = (started._value.get(), submitted._value.get(), autosave._value.get())
        self.assertEqual(after, tuple(value + 1 for value in before))

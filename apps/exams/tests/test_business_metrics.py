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

"""«Mənim dərs yüküm» etiketləri aktiv dilə uyğun olmalıdır (QA-1 F3, 2026-10-17).

Bug: ``queries._ACTIVITY_LABELS`` / ``_SEASON_LABELS`` və ``my_workload_lines._FORM_LABELS`` / ``_LEVEL_LABELS``
import anında ``str()`` ilə qiymətləndirilirdi — proses ilk dildə (az) donurdu, en/ru/de səhifədə AZ etiketlər qalırdı.
İndi lüğətlər LAZY qalır, mətnə çevirmə çağırış anındadır. Test kataloqdan asılı deyil: lazylığı və çağırış anında
qiymətləndirməni yoxlayır.
"""

from unittest import mock

from django.test import SimpleTestCase
from django.utils.functional import Promise, lazy

from apps.workload.services import my_workload_lines, queries


class WorkloadLabelsAreLazyTest(SimpleTestCase):
    def test_label_maps_hold_lazy_objects(self):
        for mapping in (
            queries._ACTIVITY_LABELS,
            queries._SEASON_LABELS,
            my_workload_lines._FORM_LABELS,
            my_workload_lines._LEVEL_LABELS,
        ):
            self.assertTrue(mapping)
            for label in mapping.values():
                self.assertIsInstance(label, Promise)

    def test_label_is_translated_at_call_time_not_import_time(self):
        calls = []
        current = {"text": "az"}
        lazy_label = lazy(lambda: calls.append(1) or current["text"], str)()
        with mock.patch.dict(queries._ACTIVITY_LABELS, {"lecture": lazy_label}):
            self.assertEqual(calls, [])
            self.assertEqual(queries._label(queries._ACTIVITY_LABELS, "lecture"), "az")
            current["text"] = "en"  # dil dəyişdi → eyni lüğət yeni mətn verməlidir
            self.assertEqual(queries._label(queries._ACTIVITY_LABELS, "lecture"), "en")
            self.assertEqual(len(calls), 2)

    def test_unknown_value_is_returned_as_is(self):
        self.assertEqual(queries._label(queries._SEASON_LABELS, "nonsense"), "nonsense")
        self.assertEqual(my_workload_lines._label(my_workload_lines._FORM_LABELS, ""), "")

    def test_grouped_lines_use_call_time_labels(self):
        calls = []
        lazy_label = lazy(lambda: calls.append(1) or "Əyani-X", str)()
        with mock.patch.dict(my_workload_lines._FORM_LABELS, {"eyani": lazy_label}):
            rows = [
                {
                    "row_id": "r1",
                    "task_id": "t1",
                    "education_form": "eyani",
                    "degree_level": "bachelor",
                    "activity": "lecture",
                    "activity_label": "Mühazirə",
                    "hours": 15,
                    "id": "a1",
                }
            ]
            lines = my_workload_lines.group_workload_lines(rows)
        self.assertEqual(lines[0]["education_form_label"], "Əyani-X")
        self.assertEqual(len(calls), 1)

"""``week`` saat qaydası — plan bölgüsü olmayanda ziddiyyət yaratmamalıdır.

Qüsurun tarixçəsi: ``_check_week`` eyni anda iki şey tələb edirdi —
(a) hər növün saat CƏMİ ``plan_hours[növ]``-ə bərabər olsun, (b) dolu hər
mövzuda ən azı 1 saat olsun.  ``plan_hours`` boş olanda (a) «cəmi 0 olsun»
deməkdir, (b) isə «0-dan böyük olsun» — yəni bölmə HEÇ VAXT bağlanmırdı.

Nəticəsi: müəllimin sıfırdan yaratdığı hər sillabus 88%-də ilişirdi və
təsdiqə göndərilə bilmirdi (``api.py::_do_create`` ``plan_hours={}`` ötürür,
çünki ``CourseOffering`` yalnız ``lesson_hours`` cəmini daşıyır).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.syllabus.completion import evaluate


def _week_rows(n=14, lecture=2):
    return [{"topic": f"Mövzu {i + 1}", "outcome": "TN1", "lecture": lecture, "seminar": 0, "lab": 0} for i in range(n)]


def _data(rows=None):
    return {
        "desc": {"description": "x" * 60, "goal": "y" * 40},
        "out": {"outcomes": ["Nəticə bir", "Nəticə iki", "Nəticə üç"]},
        "week": {"rows": rows if rows is not None else _week_rows()},
        "method": {"methods": ["mühazirə"], "note": ""},
        "assess": {},
        "self": {"option": "2x5", "topics": [{"title": f"S{i}"} for i in range(2)]},
        "lit": {"primary": ["Kitab A"], "secondary": []},
    }


def _week_codes(report):
    return sorted(issue.code for issue in report.issues if issue.section == "week")


class WeekHoursWithoutPlanTest(SimpleTestCase):
    def test_an_empty_plan_does_not_make_the_week_section_impossible(self):
        """Plan bölgüsü YOXDURSA saat balansı yoxlanılmır — bölmə bağlana bilər."""
        self.assertEqual(_week_codes(evaluate(_data(), {})), [])

    def test_a_missing_plan_is_treated_the_same_as_an_empty_one(self):
        self.assertEqual(_week_codes(evaluate(_data(), None)), [])

    def test_a_plan_that_matches_still_passes(self):
        self.assertEqual(_week_codes(evaluate(_data(), {"lecture": 28})), [])

    def test_a_plan_that_does_not_match_STILL_FAILS(self):
        """Ən vacib mühafizəçi: plan VARSA qayda hələ də dişləyir."""
        self.assertIn("week.hours_mismatch", _week_codes(evaluate(_data(), {"lecture": 99})))

    def test_only_the_kinds_named_by_the_plan_are_constrained(self):
        """Plan yalnız `lecture` deyirsə, `seminar`/`lab` sərbəst qalır."""
        rows = _week_rows()
        rows[0]["seminar"] = 5  # planda seminar yoxdur → problem olmamalıdır
        self.assertEqual(_week_codes(evaluate(_data(rows), {"lecture": 28})), [])

    def test_a_filled_topic_without_hours_is_still_rejected(self):
        """Digər qayda toxunulmamış qalmalıdır."""
        rows = _week_rows()
        rows[3]["lecture"] = 0
        self.assertIn("week.topic_without_hours", _week_codes(evaluate(_data(rows), {})))

"""Dərs yükü giriş qapıları — QA 2026-09-05 WORKLOAD-SCHEDULE-01/02 reqressiya qapısı."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.workload.constants import Season
from apps.workload.services import WorkloadDenied, resolve_actor, save_row
from apps.workload.services.people import parse_uuid, resolve_chair
from apps.workload.services.tasks import normalize_academic_year

from .factories import activate_member, make_org, make_structure, make_task

User = get_user_model()


class AcademicYearGuardTest(SimpleTestCase):
    def test_valid_forms_normalise(self):
        self.assertEqual(normalize_academic_year("2026/2027"), "2026/2027")
        self.assertEqual(normalize_academic_year("2026-2027"), "2026/2027")

    def test_garbage_and_out_of_range_years_are_rejected(self):
        # `format_year` ilk 4 rəqəmli ili götürüb Y/Y+1 qurur ("2026/2029" → "2026/2027" — qəsdli);
        # burada yalnız il TAPILMAYAN və ya diapazondan kənar dəyərlər rədd edilir.
        for raw in ("abc", "", "1800/1801", "iki min", "9999"):
            self.assertEqual(normalize_academic_year(raw), "", raw)


class ChairIdGuardTest(SimpleTestCase):
    def test_non_uuid_chair_is_denied_not_500(self):
        self.assertIsNone(parse_uuid("x"))
        self.assertIsNone(parse_uuid(""))
        with self.assertRaises(WorkloadDenied):
            resolve_chair(None, "x")


class CurrentAcademicYearSourceTest(TestCase):
    """Cari tədris ili tək mənbədən gəlir — QA 2026-09-05 UX-09."""

    def test_period_wins_over_a_newer_task_year(self):
        from apps.workload.center_registry import current_academic_year
        from apps.workload.models import TeachingTask

        from .factories import make_org, make_structure, make_task

        org = make_org("yearsrc")
        stack = make_structure(org, code="YS")
        task = make_task(org, stack["chair"])
        TeachingTask.objects.filter(pk=task.pk).update(academic_year="2030/2031")
        # `is_current` dövr yoxdur; ən son BAŞLAYAN dövr qazanmalıdır (tapşırıq ili yox).
        AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
        AcademicPeriod.objects.filter(organization=org).update(is_current=False)
        self.assertEqual(
            current_academic_year(org),
            AcademicPeriod.objects.filter(organization=org)
            .order_by("-start_date")
            .values_list("academic_year", flat=True)
            .first(),
        )


class SaveRowValidationTest(TestCase):
    """``save_row`` sətir yoxlamaları — QA 2026-09-05 P3-20/P3-22 reqressiya qapısı."""

    def setUp(self):
        self.org = make_org("rowval")
        self.stack = make_structure(self.org, code="RV")
        self.office = User.objects.create_user("rowval_office", "rowval_office@x.test", "pw")
        activate_member(
            self.org,
            self.office,
            "teaching_office_head",
            permissions=["workload.view", "workload.manage"],
            level=85,
        )
        self.task = make_task(self.org, self.stack["chair"], created_by=self.office)
        self.actor = resolve_actor(self.office, self.org)

    def test_total_hours_error_names_the_right_field(self):
        # QA 2026-09-05 (P3-20): mənfi/ondalıq `total_hours` xətası
        # «student_count» sahəsini göstərirdi — `_coerce` çağırışı yanlış
        # sahə adı ötürürdü.
        with self.assertRaises(WorkloadDenied) as ctx:
            save_row(task=self.task, actor=self.actor, data={"subject_text": "Fənn", "total_hours": -5})
        self.assertEqual(ctx.exception.code, "workload.negative_number")
        self.assertIn("total_hours", ctx.exception.message)
        self.assertNotIn("student_count", ctx.exception.message)

    def test_json_bool_hours_is_rejected_not_coerced(self):
        # QA 2026-09-05 (P3-22): JSON `true` `int(value)`-də səssizcə 1 olurdu
        # (`bool` `int`-in alt-sinifidir).
        with self.assertRaises(WorkloadDenied) as ctx:
            save_row(task=self.task, actor=self.actor, data={"subject_text": "Fənn", "lecture_total": True})
        self.assertEqual(ctx.exception.code, "workload.invalid_number")

    def test_json_float_hours_is_rejected_not_truncated(self):
        # QA 2026-09-05 (P3-22): 12.5 → 12 səssiz kəsilirdi.
        with self.assertRaises(WorkloadDenied) as ctx:
            save_row(task=self.task, actor=self.actor, data={"subject_text": "Fənn", "lecture_total": 12.5})
        self.assertEqual(ctx.exception.code, "workload.invalid_number")

    def test_whole_number_float_hours_is_still_accepted(self):
        # 12.0 məlumat itirmir — rədd yox, normal int-ə çevrilir.
        row = save_row(task=self.task, actor=self.actor, data={"subject_text": "Fənn", "lecture_total": 12.0})
        self.assertEqual(row.lecture_total, 12)

    def test_season_is_derived_from_the_chosen_period_when_not_given(self):
        # QA 2026-09-05 (P3-20 / WORKLOAD-SCHEDULE-07): «Yay» dövrü seçiləndə
        # `season` göndərilməyibsə sətir defolt «fall»da donub qalırdı.
        AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
        summer_period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Yay",
            period_type="semester",
            academic_year="2026/2027",
            start_date="2027-07-01",
            end_date="2027-08-15",
        )
        row = save_row(
            task=self.task,
            actor=self.actor,
            data={"subject_text": "Yay fənni", "period_id": str(summer_period.pk)},
        )
        self.assertEqual(row.season, Season.SUMMER)

    def test_explicit_season_is_not_overridden_by_the_period(self):
        AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
        summer_period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Yay",
            period_type="semester",
            academic_year="2026/2027",
            start_date="2027-07-01",
            end_date="2027-08-15",
        )
        row = save_row(
            task=self.task,
            actor=self.actor,
            data={
                "subject_text": "Yay fənni (əl ilə yaz)",
                "period_id": str(summer_period.pk),
                "season": "spring",
            },
        )
        self.assertEqual(row.season, Season.SPRING)

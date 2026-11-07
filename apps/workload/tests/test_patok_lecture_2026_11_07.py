"""Sahib 2026-11-07: patok mühazirəsi ikinci/üçüncü qrupda da görünsün, yük ikiqat sayılmasın.

* tərəfdaş sətir (``lecture_plan > 0``, ``lecture_total = 0``) «Mühazirə» süzgəcində çıxır və kartında aparıcı
  sətrin müəllimi + qrupları ilə mühazirə xətti var; bölgü / yük dəyişmir;
* mühazirəçi: tərəfdaşda da bölgüsü olan aparıcı müəllim; yoxdursa tək aparıcı müəllim; ikisi də deyilsə boş;
* müəllimin jurnal xəritəsində öz bölgüsü olan tərəfdaş qrupa «lecture» növü düşür (bölgüsü yoxdursa jurnal
  onun deyil — düşmür).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.workload.constants import RowKind, TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.public import teacher_journal_assignments
from apps.workload.services.assignments import balance_for_rows
from apps.workload.services.patok import partner_lectures
from apps.workload.services.queries import rows_page
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.constants import OrgUnitType

User = get_user_model()


class PatokLectureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("patok-lecture")
        cls.stack = make_structure(cls.org, code="PT")
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.AMENDED)
        cls.lecturer, cls.colleague, cls.other = (
            User.objects.create_user(name) for name in ("pt-lec", "pt-sem", "pt-oth")
        )
        for user in (cls.lecturer, cls.colleague, cls.other):
            activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS)
        cls.lead = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=30)
        OrgUnit.objects.filter(pk=cls.stack["group"].pk).update(name="236 K")
        cls.partner = cls._row("236 KE", lecture_total=0, seminar=15)
        cls.third = cls._row("236 KE ing", lecture_total=0, seminar=15)
        cls._assign(cls.lead, cls.lecturer, "lecture", 30)
        cls._assign(cls.lead, cls.lecturer, "seminar", 30)
        cls._assign(cls.partner, cls.lecturer, "seminar", 15)
        cls._assign(cls.third, cls.colleague, "seminar", 15)

    @classmethod
    def _row(cls, name, *, lecture_total, seminar):
        group = OrgUnit.objects.create(
            organization=cls.org,
            name=name,
            slug=f"pt-{name.lower().replace(' ', '-')}",
            unit_type=OrgUnitType.GROUP,
            parent=cls.stack["specialty"],
        )
        row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=seminar)
        type(row).objects.filter(pk=row.pk).update(lecture_total=lecture_total, total_hours=lecture_total + seminar)
        row.refresh_from_db()
        row.groups.set([group])
        return row

    @classmethod
    def _assign(cls, row, teacher, activity, hours):
        TeacherAssignment.objects.create(organization=cls.org, row=row, teacher=teacher, activity=activity, hours=hours)

    def test_partner_shows_the_lead_lecture_without_adding_load(self):
        page = rows_page(self.task, activity="lecture", limit=50)
        by_id = {row["id"]: row for row in page["rows"]}
        self.assertEqual(set(by_id), {str(self.lead.pk), str(self.partner.pk), str(self.third.pk)})
        self.assertIsNone(by_id[str(self.lead.pk)]["patok_lecture"])
        self.assertEqual(
            by_id[str(self.partner.pk)]["patok_lecture"],
            {"hours": 30, "teacher_id": str(self.lecturer.pk), "teacher_name": "pt-lec", "groups": "236 K"},
        )
        # Tərəfdaşda mühazirəçinin bölgüsü yoxdur, amma aparıcıda tək müəllim var.
        self.assertEqual(by_id[str(self.third.pk)]["patok_lecture"]["teacher_id"], str(self.lecturer.pk))
        balance = balance_for_rows([self.partner])[str(self.partner.pk)]["activities"]
        self.assertNotIn("lecture", balance)
        self.assertEqual(
            sum(
                TeacherAssignment.objects.filter(teacher=self.lecturer, activity="lecture").values_list(
                    "hours", flat=True
                )
            ),
            30,
        )

    def test_two_lecturers_resolve_by_the_partner_assignment_or_stay_blank(self):
        rival = self._row("236 BİO", lecture_total=30, seminar=15)
        type(rival).objects.filter(pk=rival.pk).update(lecture_total=30)
        self._assign(rival, self.other, "lecture", 30)
        found = partner_lectures([self.partner, self.third])
        self.assertEqual(found[self.partner.pk]["teacher_id"], str(self.lecturer.pk))  # öz bölgüsü var
        self.assertEqual(found[self.third.pk]["teacher_id"], "")  # iki aparıcı, heç biri tərəfdaşda yox
        self.assertEqual(found[self.third.pk]["groups"], "")

    def test_lecturer_journal_map_gets_lecture_for_every_patok_group(self):
        assignments = teacher_journal_assignments(organization=self.org, teacher_id=self.lecturer.pk)
        subject, period = self.stack["subject"].pk, self.stack["period"].pk
        partner_group = self.partner.groups.get().pk
        third_group = self.third.groups.get().pk
        self.assertEqual(assignments[(subject, period, partner_group)], {"seminar", "lecture"})
        self.assertNotIn((subject, period, third_group), assignments)
        colleague = teacher_journal_assignments(organization=self.org, teacher_id=self.colleague.pk)
        self.assertEqual(colleague[(subject, period, third_group)], {"seminar"})

    def test_non_partner_rows_are_untouched(self):
        type(self.partner).objects.filter(pk=self.partner.pk).update(row_kind=RowKind.INTENSIVE)
        self.partner.refresh_from_db()
        self.assertEqual(partner_lectures([self.partner, self.lead]), {})

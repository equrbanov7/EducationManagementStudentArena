"""Sahib 2026-11-08: patok tərəfdaşı → aparıcı sətir AÇIQ bağı (``TeachingTaskRow.patok_lead``).

* A mühazirə (aparıcı sətir), B seminar, C lab (tərəfdaş sətir): mühazirəçi A-dır, B/C heç vaxt mühazirəçi deyil;
  «Mühazirə» süzgəci müəllimə görə fəaliyyət üzrə işləyir; A tərəfdaş qrupun jurnalını «lecture» kimi görür; yük dəyişmir;
* eyni fənndə iki mühazirəçi (536 MRK Həbibov / 536 MU-ML-İ Balayev, seminar Orucova): bağsız — müəyyən deyil
  (evristika dəyişmir), bağla — Balayev; bağ etibarsız olanda evristikaya qayıdır;
* ``/ders-yuku/setir/yadda-saxla/`` ``patok_lead_id``-ni yoxlayıb yazır / açır;
* ``link_patok_leads_20261108`` əmri: tək namizəd → bağ, çox namizəd → ``ambiguous_row=<id>``, ``--pairs``.
"""

from __future__ import annotations

import json
import re
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.registrar.models import Subject
from apps.workload.constants import Season, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.public import teacher_journal_assignments
from apps.workload.services.assignments import balance_for_rows
from apps.workload.services.patok import partner_lectures
from apps.workload.services.queries import rows_page
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]
WORKFLOW = Path(settings.BASE_DIR) / ".github" / "workflows" / "prod-data-ops.yml"


class _PatokMixin:
    code = "PL"

    @classmethod
    def _setup_org(cls, status=TaskStatus.AMENDED):
        cls.org = make_org(f"patok-link-{cls.code.lower()}")
        cls.stack = make_structure(cls.org, code=cls.code)
        cls.task = make_task(cls.org, cls.stack["chair"], status=status)

    @classmethod
    def _teacher(cls, name):
        user = User.objects.create_user(f"{cls.code.lower()}-{name}")
        activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS)
        return user

    @classmethod
    def _group(cls, name):
        return OrgUnit.objects.create(
            organization=cls.org,
            name=name,
            slug=f"{cls.code.lower()}-{name.lower().replace(' ', '-')}",
            unit_type=OrgUnitType.GROUP,
            parent=cls.stack["specialty"],
        )

    @classmethod
    def _row(cls, group, *, lecture_total, lecture_plan=30, seminar=30, lab=0, subject=None, task=None):
        task = task or cls.task
        row = TeachingTaskRow.objects.create(
            organization=cls.org,
            task=task,
            season=Season.FALL,
            period=cls.stack["period"],
            subject=subject or cls.stack["subject"],
            specialty=cls.stack["specialty"],
            faculty=cls.stack["faculty"],
            lecture_plan=lecture_plan,
            lecture_total=lecture_total,
            seminar_plan=seminar,
            seminar_total=seminar,
            lab_plan=lab,
            lab_total=lab,
            total_hours=lecture_total + seminar + lab,
        )
        row.groups.set([group])
        return row

    @classmethod
    def _assign(cls, row, teacher, activity, hours):
        TeacherAssignment.objects.create(organization=cls.org, row=row, teacher=teacher, activity=activity, hours=hours)

    def _ids(self, **filters):
        return {row["id"] for row in rows_page(self.task, limit=50, **filters)["rows"]}


class LectureSeminarLabSplitTests(_PatokMixin, TestCase):
    """A — mühazirə (aparıcıda), B — tərəfdaşın seminarı, C — tərəfdaşın labı."""

    code = "PLA"

    @classmethod
    def setUpTestData(cls):
        cls._setup_org()
        cls.a, cls.b, cls.c = (cls._teacher(name) for name in ("a", "b", "c"))
        cls.lead = cls._row(cls._group("536 MRK"), lecture_total=30)
        cls.partner = cls._row(cls._group("536 MU"), lecture_total=0, seminar=15, lab=15)
        cls._assign(cls.lead, cls.a, "lecture", 30)
        cls._assign(cls.lead, cls.a, "seminar", 30)
        cls._assign(cls.partner, cls.b, "seminar", 15)
        cls._assign(cls.partner, cls.c, "lab", 15)
        TeachingTaskRow.objects.filter(pk=cls.partner.pk).update(patok_lead=cls.lead)
        cls.partner.refresh_from_db()

    def test_partner_card_names_the_lead_lecturer(self):
        found = partner_lectures([self.partner])[self.partner.pk]
        self.assertEqual(
            found,
            {
                "hours": 30,
                "teacher_id": str(self.a.pk),
                "teacher_name": self.a.username,
                "groups": "536 MRK",
                "lead_id": str(self.lead.pk),
                "linked": True,
            },
        )
        by_id = {row["id"]: row for row in rows_page(self.task, activity="lecture", limit=50)["rows"]}
        self.assertEqual(by_id[str(self.partner.pk)]["patok_lecture"]["teacher_id"], str(self.a.pk))
        self.assertEqual(by_id[str(self.partner.pk)]["patok_lead_id"], str(self.lead.pk))

    def test_lecture_filter_is_per_activity(self):
        lead, partner = str(self.lead.pk), str(self.partner.pk)
        self.assertEqual(self._ids(teacher=str(self.a.pk), activity="lecture"), {lead, partner})
        self.assertEqual(self._ids(teacher=str(self.b.pk), activity="lecture"), set())
        self.assertEqual(self._ids(teacher=str(self.c.pk), activity="lecture"), set())
        self.assertEqual(self._ids(teacher=str(self.b.pk), activity="seminar"), {partner})
        self.assertEqual(self._ids(teacher=str(self.c.pk), activity="lab"), {partner})
        self.assertEqual(self._ids(teacher=str(self.a.pk), activity="seminar"), {lead})
        # Fəaliyyətsiz: müəllimin bölgüsü olan sətirlər + mühazirəsini apardığı patok tərəfdaşı.
        self.assertEqual(self._ids(teacher=str(self.a.pk)), {lead, partner})
        self.assertEqual(self._ids(teacher=str(self.b.pk)), {partner})

    def test_journal_map_per_activity(self):
        subject, period = self.stack["subject"].pk, self.stack["period"].pk
        partner_group = self.partner.groups.get().pk
        lead_group = self.lead.groups.get().pk
        a_map = teacher_journal_assignments(organization=self.org, teacher_id=self.a.pk)
        self.assertEqual(a_map[(subject, period, partner_group)], {"lecture"})
        self.assertEqual(a_map[(subject, period, lead_group)], {"lecture", "seminar"})
        b_map = teacher_journal_assignments(organization=self.org, teacher_id=self.b.pk)
        self.assertEqual(b_map, {(subject, period, partner_group): {"seminar"}})
        c_map = teacher_journal_assignments(organization=self.org, teacher_id=self.c.pk)
        self.assertEqual(c_map, {(subject, period, partner_group): {"lab"}})

    def test_teacher_totals_unchanged(self):
        self.assertNotIn("lecture", balance_for_rows([self.partner])[str(self.partner.pk)]["activities"])
        lecture = TeacherAssignment.objects.filter(teacher=self.a, activity="lecture").values_list("hours", flat=True)
        self.assertEqual(sum(lecture), 30)
        self.assertFalse(TeacherAssignment.objects.filter(row=self.partner, activity="lecture").exists())


class TwoLecturersSameSubjectTests(_PatokMixin, TestCase):
    """536: Həbibov (MRK) və Balayev (MU) eyni fənnə mühazirə deyir, Orucova — tərəfdaşın seminarı."""

    code = "PLB"

    @classmethod
    def setUpTestData(cls):
        cls._setup_org()
        cls.habibov, cls.balayev, cls.orucova = (cls._teacher(name) for name in ("hab", "bal", "oru"))
        cls.lead_mrk = cls._row(cls._group("536 MRK"), lecture_total=30)
        cls.lead_mu = cls._row(cls._group("536 MU"), lecture_total=30)
        cls.partner = cls._row(cls._group("536 İ"), lecture_total=0, seminar=30)
        cls._assign(cls.lead_mrk, cls.habibov, "lecture", 30)
        cls._assign(cls.lead_mu, cls.balayev, "lecture", 30)
        cls._assign(cls.partner, cls.orucova, "seminar", 30)

    def _link(self, lead):
        TeachingTaskRow.objects.filter(pk=self.partner.pk).update(patok_lead=lead)
        self.partner.refresh_from_db()

    def test_without_link_stays_blank(self):
        found = partner_lectures([self.partner])[self.partner.pk]
        self.assertEqual((found["teacher_id"], found["groups"], found["linked"]), ("", "", False))
        subject, period = self.stack["subject"].pk, self.stack["period"].pk
        group = self.partner.groups.get().pk
        for teacher in (self.habibov, self.balayev):
            mapping = teacher_journal_assignments(organization=self.org, teacher_id=teacher.pk)
            self.assertNotIn((subject, period, group), mapping)

    def test_explicit_link_resolves_the_lecturer(self):
        self._link(self.lead_mu)
        found = partner_lectures([self.partner])[self.partner.pk]
        self.assertEqual(
            (found["teacher_id"], found["groups"], found["linked"]), (str(self.balayev.pk), "536 MU", True)
        )
        subject, period = self.stack["subject"].pk, self.stack["period"].pk
        group = self.partner.groups.get().pk
        balayev = teacher_journal_assignments(organization=self.org, teacher_id=self.balayev.pk)
        self.assertEqual(balayev[(subject, period, group)], {"lecture"})
        habibov = teacher_journal_assignments(organization=self.org, teacher_id=self.habibov.pk)
        self.assertNotIn((subject, period, group), habibov)
        orucova = teacher_journal_assignments(organization=self.org, teacher_id=self.orucova.pk)
        self.assertEqual(orucova[(subject, period, group)], {"seminar"})
        partner = str(self.partner.pk)
        self.assertIn(partner, self._ids(teacher=str(self.balayev.pk), activity="lecture"))
        self.assertNotIn(partner, self._ids(teacher=str(self.habibov.pk), activity="lecture"))
        self.assertNotIn(partner, self._ids(teacher=str(self.orucova.pk), activity="lecture"))

    def test_link_beats_heuristic_local_assignment(self):
        # Həbibov tərəfdaşda seminar da deyir — evristika onu seçərdi; açıq bağ Balayevdir.
        TeacherAssignment.objects.filter(row=self.partner, teacher=self.orucova).update(hours=29)
        self._assign(self.partner, self.habibov, "seminar", 1)
        self.assertEqual(partner_lectures([self.partner])[self.partner.pk]["teacher_id"], str(self.habibov.pk))
        self._link(self.lead_mu)
        self.assertEqual(partner_lectures([self.partner])[self.partner.pk]["teacher_id"], str(self.balayev.pk))
        subject, period = self.stack["subject"].pk, self.stack["period"].pk
        habibov = teacher_journal_assignments(organization=self.org, teacher_id=self.habibov.pk)
        self.assertEqual(habibov[(subject, period, self.partner.groups.get().pk)], {"seminar"})

    def test_stale_link_falls_back_to_heuristic(self):
        self._link(self.lead_mu)
        TeachingTaskRow.objects.filter(pk=self.lead_mrk.pk).update(lecture_total=0)  # MRK artıq aparıcı deyil
        TeachingTaskRow.objects.filter(pk=self.lead_mu.pk).update(lecture_total=0)  # bağ etibarsız
        self.partner.refresh_from_db()
        found = partner_lectures([self.partner])[self.partner.pk]
        self.assertEqual((found["teacher_id"], found["linked"]), ("", False))
        subject, period = self.stack["subject"].pk, self.stack["period"].pk
        balayev = teacher_journal_assignments(organization=self.org, teacher_id=self.balayev.pk)
        self.assertNotIn((subject, period, self.partner.groups.get().pk), balayev)


class RowSaveEndpointTests(_PatokMixin, TestCase):
    code = "PLC"

    @classmethod
    def setUpTestData(cls):
        cls._setup_org(status=TaskStatus.DRAFT)
        cls.head = User.objects.create_user("plc-head")
        activate_member(
            cls.org,
            cls.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        cls.lead = cls._row(cls._group("PLC 1"), lecture_total=30)
        cls.other_lead = cls._row(cls._group("PLC 2"), lecture_total=30)
        cls.partner = cls._row(cls._group("PLC 3"), lecture_total=0)
        cls.other_partner = cls._row(cls._group("PLC 4"), lecture_total=0)
        other_subject = Subject.objects.create(organization=cls.org, code="PLC102", name="Fizika", ects=5)
        cls.foreign_subject = cls._row(cls._group("PLC 5"), lecture_total=30, subject=other_subject)

    def setUp(self):
        self.client.force_login(self.head)

    def _save(self, row, **extra):
        payload = {"task_id": str(self.task.pk), "row_id": str(row.pk), **extra}
        return self.client.post(reverse("workload:row_save"), data=json.dumps(payload), content_type="application/json")

    def _error(self, row, lead_id):
        response = self._save(row, patok_lead_id=lead_id)
        self.assertEqual(response.status_code, 400, response.content)
        return response.json()["error"]

    def test_set_keep_and_clear(self):
        response = self._save(self.partner, patok_lead_id=str(self.lead.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.partner.refresh_from_db()
        self.assertEqual(self.partner.patok_lead_id, self.lead.pk)
        self.assertEqual(self._save(self.partner, seminar_total=30).status_code, 200)  # açar yoxdur — bağ qalır
        self.partner.refresh_from_db()
        self.assertEqual(self.partner.patok_lead_id, self.lead.pk)
        self.assertEqual(self._save(self.partner, patok_lead_id="").status_code, 200)
        self.partner.refresh_from_db()
        self.assertIsNone(self.partner.patok_lead_id)

    def test_rejections(self):
        self.assertEqual(self._error(self.partner, str(self.partner.pk)), "workload.patok_lead_self")
        self.assertEqual(self._error(self.partner, "not-a-uuid"), "workload.patok_lead_not_found")
        self.assertEqual(self._error(self.partner, str(self.foreign_subject.pk)), "workload.patok_lead_mismatch")
        self.assertEqual(self._error(self.partner, str(self.other_partner.pk)), "workload.patok_lead_no_lecture")
        self.assertEqual(self._error(self.other_lead, str(self.lead.pk)), "workload.patok_not_partner")
        other_task = make_task(self.org, self._group("PLC kafedra 2"), status=TaskStatus.DRAFT)
        foreign_task_lead = self._row(self._group("PLC 6"), lecture_total=30, task=other_task)
        self.assertEqual(self._error(self.partner, str(foreign_task_lead.pk)), "workload.patok_lead_mismatch")
        TeachingTaskRow.objects.filter(pk=self.other_lead.pk).update(patok_lead=self.lead)  # köhnəlmiş bağ
        self.assertEqual(self._error(self.partner, str(self.other_lead.pk)), "workload.patok_lead_is_partner")
        TeachingTaskRow.objects.filter(pk=self.other_partner.pk).update(patok_lead=self.partner)
        self.assertEqual(self._error(self.partner, str(self.lead.pk)), "workload.patok_row_is_lead")
        self.partner.refresh_from_db()
        self.assertIsNone(self.partner.patok_lead_id)

    def test_lecture_hours_on_partner_drop_the_link(self):
        self.assertEqual(self._save(self.partner, patok_lead_id=str(self.lead.pk)).status_code, 200)
        self.assertEqual(self._save(self.partner, lecture_total=30).status_code, 200)
        self.partner.refresh_from_db()
        self.assertIsNone(self.partner.patok_lead_id)


class LinkPatokLeadsCommandTests(_PatokMixin, TestCase):
    code = "PLD"

    @classmethod
    def setUpTestData(cls):
        cls._setup_org()
        cls.admin = User.objects.create_superuser("pld-admin", "pld-admin@x.test", "pw")
        physics = Subject.objects.create(organization=cls.org, code="PLD102", name="Fizika", ects=5)
        algebra = Subject.objects.create(organization=cls.org, code="PLD103", name="Cəbr", ects=5)
        cls.single_lead = cls._row(cls._group("PLD 1"), lecture_total=30)
        cls.single = cls._row(cls._group("PLD 2"), lecture_total=0)
        cls.lead_a = cls._row(cls._group("PLD 3"), lecture_total=30, subject=physics)
        cls.lead_b = cls._row(cls._group("PLD 4"), lecture_total=30, subject=physics)
        cls.ambiguous = cls._row(cls._group("PLD 5"), lecture_total=0, subject=physics)
        cls.orphan = cls._row(cls._group("PLD 6"), lecture_total=0, subject=algebra)

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "link_patok_leads_20261108", "--org", self.org.slug, "--actor", self.admin.username, *extra, stdout=out
        )
        return out.getvalue().splitlines()

    @staticmethod
    def _counts(lines):
        return dict(item.split("=", 1) for line in lines for item in line.split()[1:])

    def _lead(self, row):
        row.refresh_from_db()
        return row.patok_lead_id

    def test_dry_run_then_apply(self):
        lines = self._call()
        counts = self._counts(lines[:2])
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual(counts["year"], "2026-2027")
        self.assertEqual(
            {key: counts[key] for key in ("partners", "linked", "ambiguous", "no_lead")},
            {"partners": "3", "linked": "1", "ambiguous": "1", "no_lead": "1"},
        )
        self.assertEqual(lines[2], f"patok_links: ambiguous_row={self.ambiguous.pk}")
        self.assertIsNone(self._lead(self.single))  # dry-run geri qaytarıldı
        self._call("--apply")
        self.assertEqual(self._lead(self.single), self.single_lead.pk)
        self.assertIsNone(self._lead(self.ambiguous))
        counts = self._counts(self._call("--apply", f"--pairs={self.ambiguous.pk}:{self.lead_b.pk}")[:2])
        self.assertEqual((counts["pair_linked"], counts["partners"], counts["ambiguous"]), ("1", "1", "0"))
        self.assertEqual(self._lead(self.ambiguous), self.lead_b.pk)
        counts = self._counts(self._call("--apply")[:2])
        self.assertEqual((counts["linked"], counts["partners"]), ("0", "1"))  # idempotent: yalnız «orphan» qalır

    def test_bad_pairs_abort_everything(self):
        with self.assertRaisesMessage(CommandError, "patok_links_patok_lead_mismatch"):
            self._call("--apply", f"--pairs={self.ambiguous.pk}:{self.single_lead.pk}")
        self.assertIsNone(self._lead(self.single))
        with self.assertRaisesMessage(CommandError, "patok_links_pairs_format"):
            self._call("--pairs=abc")
        with self.assertRaisesMessage(CommandError, "actor_must_be_active_superuser"):
            call_command("link_patok_leads_20261108", "--org", self.org.slug, "--actor", "nobody", stdout=StringIO())

    def test_output_matches_workflow_grep_and_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - link_patok_leads_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "link_patok_leads_20261108" ]', text)
        self.assertIn("            link_patok_leads_20261108)\n", text)
        pattern = re.search(r"grep -E '(\^\([^']*\|patok_links\|[^']*)'", text).group(1)
        for line in self._call():
            self.assertRegex(line, pattern)

"""«Bir fənn = bir kart» (sahib 2026-11-09): eyni fənn + semestr + kredit sətirləri bir kartda.

536 ailəsi modeli: MU (Balayev mühazirə, Orucova seminar), Bİ (Həbibov), «MRK / DBİ» (Bİ axınının tərəfdaşı,
seminar qrup-qrup: Həbibov MRK — struktur bağ, Orucova DBİ — qrup qeydi), «İ / ML» (MU axınının tərəfdaşı, Orucova
seminarı qrupsuz). Eyni fənnin 4 kreditlik sətri və Fizika ayrı kartlardır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.registrar.models import Subject
from apps.workload.constants import Season, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services.queries import rows_page
from apps.workload.services.subject_cards import cards_page, family_key
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_structure, make_task

User = get_user_model()
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class CardsBase(TestCase):
    code = "SC"
    status = TaskStatus.AMENDED

    @classmethod
    def setUpTestData(cls):
        cls.org = make_org(f"cards-{cls.code.lower()}")
        cls.stack = make_structure(cls.org, code=cls.code)
        cls.task = make_task(cls.org, cls.stack["chair"], status=cls.status)
        cls.head = User.objects.create_user(f"{cls.code.lower()}-head")
        activate_member(
            cls.org,
            cls.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        cls.balayev, cls.habibov, cls.orucova = (cls._teacher(name) for name in ("balayev", "habibov", "orucova"))
        cls.g_mu, cls.g_bi, cls.g_mrk, cls.g_dbi, cls.g_i, cls.g_ml = (
            cls._group(name) for name in ("536 MU", "536 Bİ", "536 MRK", "536 DBİ", "536 İ", "536 ML")
        )
        cls.row_mu = cls._row([cls.g_mu], lecture_total=45)
        cls.row_bi = cls._row([cls.g_bi], lecture_total=45)
        cls.row_mrk_dbi = cls._row([cls.g_mrk, cls.g_dbi], lecture_total=0, seminar_total=90, subgroup_count=2)
        cls.row_i_ml = cls._row([cls.g_i, cls.g_ml], lecture_total=0, seminar_total=90, subgroup_count=2)
        TeachingTaskRow.objects.filter(pk=cls.row_mrk_dbi.pk).update(patok_lead=cls.row_bi)
        TeachingTaskRow.objects.filter(pk=cls.row_i_ml.pk).update(patok_lead=cls.row_mu)
        cls._assign(cls.row_mu, cls.balayev, "lecture", 45)
        cls._assign(cls.row_mu, cls.orucova, "seminar", 45)
        cls._assign(cls.row_bi, cls.habibov, "lecture", 45)
        cls._assign(cls.row_bi, cls.habibov, "seminar", 45)
        cls._assign(cls.row_mrk_dbi, cls.habibov, "seminar", 45, group=cls.g_mrk)
        cls._assign(cls.row_mrk_dbi, cls.orucova, "seminar", 45, groups_note=cls.g_dbi.name)  # qrup qeydi
        cls._assign(cls.row_i_ml, cls.orucova, "seminar", 90)
        cls.row_credits4 = cls._row(
            [cls.g_mu], lecture_total=30, lecture_plan=30, seminar_total=30, credits="4", credits_value=4
        )
        cls.physics = Subject.objects.create(organization=cls.org, code=f"{cls.code}202", name="Fizika", ects=5)
        cls.row_physics = cls._row([cls.g_bi], lecture_total=30, lecture_plan=30, subject=cls.physics)
        for row in (cls.row_mrk_dbi, cls.row_i_ml):
            row.refresh_from_db()

    @classmethod
    def _teacher(cls, name):
        user = User.objects.create_user(f"{cls.code.lower()}-{name}", first_name=name.title(), last_name="T")
        activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS)
        return user

    @classmethod
    def _group(cls, name):
        return OrgUnit.objects.create(
            organization=cls.org,
            name=f"{cls.code} {name}",
            slug=f"{cls.code.lower()}-{name.lower().replace(' ', '-')}",
            unit_type=OrgUnitType.GROUP,
            parent=cls.stack["specialty"],
        )

    @classmethod
    def _row(cls, groups, *, lecture_total, lecture_plan=45, seminar_total=45, seminar_plan=45, subject=None, **extra):
        fields = {
            "organization": cls.org,
            "task": cls.task,
            "season": Season.FALL,
            "period": cls.stack["period"],
            "subject": subject or cls.stack["subject"],
            "specialty": cls.stack["specialty"],
            "faculty": cls.stack["faculty"],
            "lecture_plan": lecture_plan,
            "lecture_total": lecture_total,
            "seminar_plan": seminar_plan,
            "seminar_total": seminar_total,
            "union_count": 1,
            "subgroup_count": 1,
            "credits": "8",
            "credits_value": 8,
        }
        fields.update(extra)
        fields["total_hours"] = fields["lecture_total"] + fields["seminar_total"]
        row = TeachingTaskRow.objects.create(**fields)
        row.groups.set(groups)
        return row

    @classmethod
    def _assign(cls, row, teacher, activity, hours, *, group=None, groups_note=""):
        return TeacherAssignment.objects.create(
            organization=cls.org,
            row=row,
            teacher=teacher,
            activity=activity,
            hours=hours,
            group=group,
            groups_note=groups_note,
        )

    def _cards(self, **kwargs):
        kwargs.setdefault("limit", 20)
        return cards_page(self.task, **kwargs)

    def _algebra(self):
        return next(card for card in self._cards()["cards"] if card["row_ids"][0] == str(self.row_mu.pk))


class FamilyCardTests(CardsBase):
    def test_same_subject_period_and_credits_form_one_card(self):
        page = self._cards()
        self.assertEqual(page["total"], 3)
        self.assertEqual([card["subject"] for card in page["cards"]], ["Alqoritmlər", "Alqoritmlər", "Fizika"])
        card = page["cards"][0]
        names = [group["name"] for group in card["groups"]]
        self.assertEqual(
            set(names), {f"SC {name}" for name in ("536 MU", "536 Bİ", "536 MRK", "536 DBİ", "536 İ", "536 ML")}
        )
        self.assertEqual(names[:2], ["SC 536 MU", "SC 536 Bİ"])  # sətir sırası, sətir daxilində qrup adı
        self.assertEqual(
            set(card["row_ids"]), {str(r.pk) for r in (self.row_mu, self.row_bi, self.row_mrk_dbi, self.row_i_ml)}
        )
        self.assertEqual((card["credits"], card["total_hours"]), ("8", 45 + 45 + 45 + 45 + 90 + 90))
        self.assertEqual(page["cards"][1]["credits"], "4")
        self.assertEqual(len(page["rows"]), 6)  # düz siyahı — redaktə modalı üçün

    def test_credit_key_falls_back_to_text(self):
        row = TeachingTaskRow(
            task=self.task,
            subject=self.stack["subject"],
            period=self.stack["period"],
            season=Season.FALL,
            credits="8",
            credits_value=0,
        )
        self.assertEqual(family_key(row), family_key(self.row_mu))

    def test_lecture_streams_follow_the_lead_links(self):
        lecture = self._algebra()["lecture"]
        by_lead = {stream["lead_row_id"]: stream for stream in lecture["streams"]}
        self.assertEqual(set(by_lead), {str(self.row_mu.pk), str(self.row_bi.pk)})
        mu = by_lead[str(self.row_mu.pk)]
        self.assertEqual(set(mu["row_ids"]), {str(self.row_mu.pk), str(self.row_i_ml.pk)})
        self.assertEqual({g["name"] for g in mu["groups"]}, {"SC 536 MU", "SC 536 İ", "SC 536 ML"})
        self.assertEqual([e["teacher_name"] for e in mu["entries"]], [self.balayev.get_full_name()])
        self.assertEqual((mu["hours"], mu["is_complete"], mu["orphan"]), (45, True, False))
        bi = by_lead[str(self.row_bi.pk)]
        self.assertEqual(set(bi["row_ids"]), {str(self.row_bi.pk), str(self.row_mrk_dbi.pk)})
        self.assertEqual(lecture["load_hours"], 90)  # hər axın bir dəfə
        self.assertEqual(self._algebra()["warnings"], [])

    def test_unlinked_partner_is_an_orphan_stream_with_warning(self):
        extra = self._row([self._group("536 TB")], lecture_total=0)  # iki aparıcı var — evristika müəyyən etmir
        card = self._algebra()
        orphan = next(s for s in card["lecture"]["streams"] if s["lead_row_id"] == str(extra.pk))
        self.assertEqual((orphan["orphan"], orphan["warning"], orphan["hours"]), (True, "no_lead", 45))
        self.assertIn("patok_unlinked", card["warnings"])
        self.assertEqual(card["lecture"]["load_hours"], 90)

    def test_seminar_lines_per_group(self):
        seminar = self._algebra()["seminar"]
        lines = {(line["label"], line.get("shared", False)): line for line in seminar["lines"]}
        orucova, habibov = self.orucova.get_full_name(), self.habibov.get_full_name()
        self.assertEqual([e["teacher_name"] for e in lines[("SC 536 MU", False)]["entries"]], [orucova])
        self.assertEqual([e["teacher_name"] for e in lines[("SC 536 Bİ", False)]["entries"]], [habibov])
        self.assertEqual([e["teacher_name"] for e in lines[("SC 536 MRK", False)]["entries"]], [habibov])  # FK
        self.assertEqual([e["teacher_name"] for e in lines[("SC 536 DBİ", False)]["entries"]], [orucova])  # qeyd
        self.assertEqual(lines[("SC 536 İ", False)]["entries"], [])
        shared = next(line for line in seminar["lines"] if line.get("shared"))
        self.assertEqual([(e["teacher_name"], e["hours"]) for e in shared["entries"]], [(orucova, 90)])
        self.assertEqual((shared["plan"], shared["total"], shared["remaining"]), (45, 90, 0))
        self.assertEqual(seminar["plan"], 45)

    def test_pagination_is_per_family_and_focus_extends(self):
        first = self._cards(limit=1)
        self.assertEqual(
            (len(first["cards"]), first["total"], first["next_offset"], first["has_more"]), (1, 3, 1, True)
        )
        self.assertEqual(len(first["rows"]), 4)
        second = self._cards(limit=1, offset=1)
        self.assertEqual(second["cards"][0]["credits"], "4")
        focused = self._cards(limit=1, focus_row=self.row_physics.pk)
        self.assertEqual(len(focused["cards"]), 3)
        self.assertFalse(focused["has_more"])

    def test_rows_page_view_cards_and_query_budget(self):
        with CaptureQueriesContext(connection) as one:
            rows_page(self.task, limit=1, view="cards")
        with CaptureQueriesContext(connection) as all_cards:
            page = rows_page(self.task, limit=20, view="cards")
        self.assertIn("cards", page)
        self.assertEqual(len(all_cards), len(one))

    def test_rows_endpoint_returns_cards(self):
        self.client.force_login(self.head)
        response = self.client.get(
            reverse("workload:rows"),
            {"chair": str(self.stack["chair"].pk), "year": self.task.academic_year, "limit": "30", "view": "cards"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["total"], 3)
        self.assertEqual(len(payload["cards"]), 3)
        self.assertEqual(payload["cards"][0]["lecture"]["load_hours"], 90)
        plain = self.client.get(
            reverse("workload:rows"),
            {"chair": str(self.stack["chair"].pk), "year": self.task.academic_year, "limit": "30"},
        ).json()
        self.assertNotIn("cards", plain)
        self.assertEqual(plain["total"], 6)

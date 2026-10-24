"""Sahib 2026-10-25: «ştat olaraq bir kafedrada, saat hesabı olaraq başqa kafedrada fənn götürüb».

Model: müəllimin ŞTAT kafedrası (``people.home_chair_rank``) dəyişmir; yük sətri FƏNNİN kafedrasının tapşırığındadır,
müəllim orada ƏLAVƏ (``is_primary=False``) müəllim üzvlüyü ilə durur (``join_chair_as_teacher``).

* (a) yükü verən kafedranın müdiri kənar müəllimi seçicidə görür və təyin edir — ştat kafedrası dəyişmir;
* (b) «Mənim dərs yüküm» bütün kafedraların sətirlərini kafedra adı ilə verir;
* (c) kafedra profili: kənar müəllim ayrıca, ştat/norma cəmlərinə düşmür; öz müəllimin «başqa kafedrada» saatı;
* (e) «Dərs yükü faylı» başqa kafedranın fənnini bu kafedraya YAZMIR (önizləmədə səbəb ilə);
* yoxlama əmri — saylar, ``--apply`` yalnız çatışmayan kənar üzvlüyü əlavə edir (idempotent).
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from openpyxl import Workbook

from apps.organizations.models import Membership, OrgUnit, Role
from apps.registrar.models import Subject
from apps.workload.constants import Activity, Season, TaskStatus
from apps.workload.load_actions import LOAD_SESSION_KEY
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.public import chair_staff_load
from apps.workload.services import assign_teacher, resolve_actor, teacher_pool, teacher_workload_rows
from apps.workload.services.my_workload_lines import group_workload_lines
from apps.workload.services.people import home_chair_rank, home_chairs
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]
OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit", "workload.load_import"]


def _row(name, unit_type, *, primary=False, role="teacher", day=1):
    return {
        "scope_unit__unit_type": unit_type,
        "is_primary": primary,
        "role__name": role,
        "role__level": 50,
        "created_at": datetime(2026, 9, day, tzinfo=timezone.utc),
        "name": name,
    }


class HomeChairRankTests(SimpleTestCase):
    def _home(self, *rows):
        return min(rows, key=home_chair_rank)["name"]

    def test_extra_membership_never_becomes_home_chair(self):
        # Əsas kafedra müdiri (chair_head) başqa kafedrada saathesabı müəllimdir → ştat öz kafedrasıdır.
        self.assertEqual(
            self._home(_row("A", "chair", primary=True, role="chair_head"), _row("B", "chair", day=20)), "A"
        )
        # Hər ikisi əsas deyil → köhnə (ştat) üzvlük; əlavə üzvlük həmişə sonra yaranır.
        self.assertEqual(self._home(_row("B", "chair", day=20), _row("A", "chair", day=2)), "A")
        # Kafedrasız əsas üzvlük (vahidsiz müəllim) — kafedra yalnız əlavə üzvlükdən məlumdur.
        self.assertEqual(self._home(_row("-", None, primary=True), _row("B", "chair", day=20)), "B")


class CrossChairServiceTests(TestCase):
    def setUp(self):
        self.org = make_org("wl-cross")
        self.home = make_structure(self.org, code="HOM")
        self.host = make_structure(self.org, code="HST")
        self.head = User.objects.create_user("cross_head", "ch@x.test", "pw")
        activate_member(
            self.org, self.head, "chair_head", permissions=CHAIR_PERMS, scope_unit=self.host["chair"], level=70,
            scope_type=RoleScopeType.UNIT,
        )  # fmt: skip
        self.teacher = User.objects.create_user("cross_t", "ct@x.test", "pw", first_name="Elçin", last_name="Abasov")
        activate_member(
            self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.home["chair"],
            scope_type=RoleScopeType.COURSE,
        )  # fmt: skip
        Membership.objects.filter(user=self.teacher).update(is_primary=True)
        self.actor = resolve_actor(self.head, self.org)
        self.task = make_task(self.org, self.host["chair"], status=TaskStatus.APPROVED, created_by=self.head)
        self.row = make_row(self.task, self.host, lecture_total=30, seminar_total=15)

    def test_picker_lists_outside_teacher_with_home_chair(self):
        self.assertNotIn(str(self.teacher.pk), {item["id"] for item in teacher_pool(self.org, self.host["chair"])})
        pool = teacher_pool(self.org, self.host["chair"], include_outside=True)
        item = next(item for item in pool if item["id"] == str(self.teacher.pk))
        self.assertTrue(item["is_outside"])
        self.assertEqual(item["home_chair"], "HOM-kafedra")

    def test_assign_outside_teacher_adds_extra_membership_home_unchanged(self):
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.LECTURE, teacher_id=self.teacher.pk, hours=30)
        extra = Membership.objects.get(user=self.teacher, scope_unit=self.host["chair"])
        self.assertFalse(extra.is_primary)
        self.assertTrue(extra.is_active)
        self.assertEqual(home_chairs(self.org, [self.teacher.pk])[self.teacher.pk]["id"], str(self.home["chair"].pk))
        self.assertTrue(
            Membership.objects.filter(user=self.teacher, scope_unit=self.home["chair"], is_primary=True).exists()
        )

    def _distribute(self):
        home_task = make_task(self.org, self.home["chair"], status=TaskStatus.DISTRIBUTED)
        home_row = make_row(home_task, self.home, lecture_total=40, seminar_total=20)
        TeacherAssignment.objects.create(
            organization=self.org, row=home_row, teacher=self.teacher, activity=Activity.LECTURE, hours=40
        )
        TeacherAssignment.objects.create(
            organization=self.org, row=home_row, teacher=self.teacher, activity=Activity.SEMINAR, hours=20
        )
        assign_teacher(row=self.row, actor=self.actor, activity=Activity.LECTURE, teacher_id=self.teacher.pk, hours=30)
        TeachingTask.objects.filter(pk=self.task.pk).update(status=TaskStatus.DISTRIBUTED)

    def test_my_workload_has_lines_from_both_chairs_with_chair_name(self):
        self._distribute()
        rows = teacher_workload_rows(organization=self.org, teacher=self.teacher, academic_year=YEAR)
        lines = group_workload_lines(rows)
        self.assertEqual({line["chair_name"] for line in lines}, {"HOM-kafedra", "HST-kafedra"})
        self.assertEqual(sum(line["hours"] for line in lines), 90)

    def test_chair_profile_load_separates_outside_and_other_chair_hours(self):
        self._distribute()
        host = chair_staff_load(
            organization=self.org, teacher_ids=[self.teacher.pk], academic_year=YEAR, chair_id=self.host["chair"].pk
        )
        summary = host["by_teacher"][self.teacher.pk]
        self.assertTrue(summary["is_outside"])
        self.assertEqual((summary["chair_hours"], summary["home_chair_name"]), (30, "HOM-kafedra"))
        self.assertEqual((host["totals"]["teachers"], host["totals"]["hours"]), (0, 0))  # ştat/norma cəmində yox

        home = chair_staff_load(
            organization=self.org, teacher_ids=[self.teacher.pk], academic_year=YEAR, chair_id=self.home["chair"].pk
        )
        summary = home["by_teacher"][self.teacher.pk]
        self.assertFalse(summary["is_outside"])
        self.assertEqual((summary["total_hours"], summary["other_chair_hours"]), (90, 30))
        self.assertEqual(summary["other_chairs"], [{"name": "HST-kafedra", "hours": 30}])
        self.assertEqual(home["totals"]["hours"], 90)


def _xlsx(rows) -> bytes:
    from apps.workload.services.load_upload_parsing import TEMPLATE_HEADERS

    book = Workbook()
    sheet = book.active
    sheet.title = "Dərs yükü"
    sheet.append(list(TEMPLATE_HEADERS))
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class LoadUploadOtherChairTests(TestCase):
    """«Ümumi iqtisadiyyat» faylında İT kafedrasının fənləri — bu kafedraya yazılmır, önizləmədə səbəb görünür."""

    def setUp(self):
        self.org = make_org("qku-cross-load")
        faculty = OrgUnit.objects.create(
            organization=self.org, name="İqtisadiyyat məktəbi", unit_type=OrgUnitType.FACULTY
        )
        self.chair = OrgUnit.objects.create(
            organization=self.org, name="Ümumi iqtisadiyyat kafedrası", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        self.it = OrgUnit.objects.create(
            organization=self.org, name="İnformasiya texnologiyaları kafedrası", unit_type=OrgUnitType.CHAIR,
            parent=faculty,
        )  # fmt: skip
        specialty = OrgUnit.objects.create(
            organization=self.org, name="İdarəetmə", slug="ide", unit_type=OrgUnitType.SPECIALTY, parent=faculty
        )
        self.group = OrgUnit.objects.create(
            organization=self.org, name="631 K", unit_type=OrgUnitType.GROUP, parent=specialty
        )
        Subject.objects.create(organization=self.org, code="QKU-1", name="Biznes riyaziyyatı", ects=5)
        rds = Subject.objects.create(organization=self.org, code="QKU-2", name="Rəqəmsal sistemlər", ects=5)
        Subject.objects.create(
            organization=self.org, code="QKU-3", name="Kompüter modelləşdirilməsi", ects=5, chair_unit=self.it
        )
        it_task = TeachingTask.objects.create(
            organization=self.org, chair=self.it, academic_year=YEAR, status=TaskStatus.DISTRIBUTED
        )
        it_row = TeachingTaskRow.objects.create(
            organization=self.org, task=it_task, season=Season.FALL, subject=rds, subject_text="Rəqəmsal sistemlər",
            groups_text="631 K", lecture_plan=30, lecture_total=30, total_hours=30, union_count=1, subgroup_count=1,
        )  # fmt: skip
        it_row.groups.set([self.group])
        self.office = User.objects.create_user("tedris.cross", "tc@x.test", "pw")
        activate_member(self.org, self.office, "teaching_office_head", permissions=OFFICE_PERMS, level=70)
        self.teacher = User.objects.create_user("elcin.cross", "e@x.test", "pw", first_name="Elçin", last_name="Abasov")
        activate_member(
            self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.chair,
            scope_type=RoleScopeType.COURSE,
        )  # fmt: skip

    def test_other_chair_lines_are_not_written_here(self):
        rows = [
            ["Abasov Elçin", "631 K", "Biznes riyaziyyatı", 5, 20, "", 40, 20, "", "", "", ""],
            ["", "631 K", "Rəqəmsal sistemlər", 5, 20, "", 30, "", "", "", "", ""],
            ["Naməlum Müəllim Xyz", "631 K", "Kompüter modelləşdirilməsi", 5, 20, "", 30, "", "", "", "", ""],
        ]
        self.client.force_login(self.office)
        upload = SimpleUploadedFile("yuk.xlsx", _xlsx(rows))
        response = self.client.post(
            reverse("workload:action"),
            {"action": "load_upload", "chair": str(self.chair.pk), "academic_year": YEAR, "file": upload},
        )
        self.assertEqual(response.status_code, 200, response.content)
        counters = response.json()["counters"]
        self.assertEqual(
            (counters.get("row_created"), counters.get("other_chair_row"), counters.get("other_chair_subject")),
            (1, 1, 1),
        )
        lines = {line["subject"]: line for line in self.client.session[LOAD_SESSION_KEY]["report"]["lines"]}
        self.assertEqual(lines["Rəqəmsal sistemlər"]["row"], "other_chair_row:İnformasiya texnologiyaları kafedrası")
        self.assertEqual(lines["Kompüter modelləşdirilməsi"]["teacher_status"], "other_chair")

        self.client.post(reverse("workload:action"), {"action": "load_apply"})
        task = TeachingTask.objects.get(organization=self.org, chair=self.chair, academic_year=YEAR)
        self.assertEqual(
            list(TeachingTaskRow.objects.filter(task=task).values_list("subject__name", flat=True)),
            ["Biznes riyaziyyatı"],
        )
        self.assertFalse(User.objects.filter(last_name="Naməlum").exists())  # ötürülən sətrin müəllimi açılmır
        self.assertFalse(Membership.objects.filter(user=self.teacher, scope_unit=self.it).exists())

        html = self.client.get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "workload-center"}), {"wc_view": "load"}
        ).json()["html"]
        self.assertIn("Fənn başqa kafedraya aiddir: İnformasiya texnologiyaları kafedrası", html)


class AuditCommandTests(TestCase):
    def setUp(self):
        self.org = make_org("wl-cross-audit")
        self.home = make_structure(self.org, code="AUH")
        self.host = make_structure(self.org, code="AUX")
        self.admin = User.objects.create_superuser("cross_admin", "ca@x.test", "pw")
        self.teacher = User.objects.create_user("cross_audit_t", "cat@x.test", "pw")
        activate_member(
            self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.home["chair"],
            scope_type=RoleScopeType.COURSE,
        )  # fmt: skip
        task = make_task(self.org, self.host["chair"], status=TaskStatus.DISTRIBUTED)
        row = make_row(task, self.host)
        # Köhnə idxal yolu: bölgü var, kafedrada üzvlük yoxdur (jurnal əhatəsi üçün lazımdır).
        TeacherAssignment.objects.create(
            organization=self.org, row=row, teacher=self.teacher, activity=Activity.LECTURE, hours=30
        )

    def _run(self, *extra) -> str:
        out = io.StringIO()
        call_command(
            "audit_cross_chair_loads", "--org", self.org.slug, "--year", YEAR, "--actor", "cross_admin", *extra,
            stdout=out,
        )  # fmt: skip
        return out.getvalue()

    def test_dry_run_counts_then_apply_joins_once(self):
        output = self._run()
        self.assertIn("mode=dry_run", output)
        self.assertIn("cross_teachers=1", output)
        self.assertIn("cross_hours=30", output)
        self.assertIn("missing_membership=1", output)
        self.assertFalse(Membership.objects.filter(user=self.teacher, scope_unit=self.host["chair"]).exists())
        self.assertIn("membership_added=1", self._run("--apply"))
        extra = Membership.objects.get(user=self.teacher, scope_unit=self.host["chair"])
        self.assertFalse(extra.is_primary)
        self.assertEqual(extra.role, Role.objects.get(organization=self.org, name="teacher"))
        self.assertIn("missing_membership=0 membership_added=0", self._run("--apply"))

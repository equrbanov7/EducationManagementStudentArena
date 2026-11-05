"""Broad list filtered by teacher == that teacher's own list (owner report 2026-11-04).

«View-as ilə müəllimin kabinetində jurnallarını tam görürəm, öz kabinetimdə müəllimi axtaranda
tamam fərqli jurnallar çıxır.» The broad ``?teacher=`` filter used to be a bare ownership match
over the whole organization, while the teacher's own list is the workload projection with a
current / history split. Both now run the same authority.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar.journal_teacher_filters import teachers_for
from apps.registrar.models import CourseOffering, JournalShare, Lesson, TeachingHandover
from apps.registrar.page_contexts import journal_list_context
from apps.workload.constants import TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class JournalListTeacherParityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("jl-parity")
        cls.admin = User.objects.create_user("jl-parity-admin", is_superuser=True)
        cls.teacher = User.objects.create_user("jl-parity-teacher", first_name="Paritet", last_name="Müəllim")
        cls.other = User.objects.create_user("jl-parity-other")
        for user in (cls.teacher, cls.other):
            activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS)
        cls.stack = make_structure(cls.org, code="JP")
        task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.AMENDED)
        cls.row = make_row(task, cls.stack, lecture_total=30, seminar_total=30)
        for kind in ("lecture", "seminar"):
            TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=cls.teacher, activity=kind, hours=30
            )
        # (a) own instructor journal inside positive workload → current.
        cls.own = cls.offering(cls.stack, instructor=cls.teacher)
        # (b) split journal: another owner, active seminar share on a registered child group → current.
        parent = cls.stack["group"]
        child = OrgUnit.objects.create(
            organization=cls.org,
            name="JP-236-1",
            slug="jl-parity-child",
            unit_type="group",
            parent=parent.parent,
            settings={"parent_group": str(parent.pk)},
        )
        cls.shared = cls.offering({**cls.stack, "group": child}, instructor=cls.other)
        JournalShare.objects.create(organization=cls.org, offering=cls.shared, teacher=cls.teacher, kinds=["seminar"])
        # (d) workload row on group X, journal on its verified alias Y (233KE ≡ 233 KE az) → current.
        cls.alias_stack = make_structure(cls.org, code="JPA")
        alias_task = make_task(cls.org, cls.alias_stack["chair"], status=TaskStatus.AMENDED)
        alias_row = make_row(alias_task, cls.alias_stack)
        TeacherAssignment.objects.create(
            organization=cls.org, row=alias_row, teacher=cls.teacher, activity="lecture", hours=30
        )
        cls.alias_group = make_structure(cls.org, code="JPY")["group"]
        cls.aliased = cls.offering({**cls.alias_stack, "group": cls.alias_group}, instructor=cls.teacher)
        # (e) history: real lessons taught in someone else's journal; handed-over observer journal.
        cls.taught = cls.offering(make_structure(cls.org, code="JPT"), instructor=cls.other)
        Lesson.objects.create(
            organization=cls.org,
            offering=cls.taught,
            date=timezone.localdate(),
            kind="seminar",
            hours=2,
            instructor=cls.teacher,
        )
        cls.observed = cls.offering(make_structure(cls.org, code="JPO"), instructor=cls.other)
        TeachingHandover.objects.create(
            organization=cls.org,
            offering=cls.observed,
            from_instructor=cls.teacher,
            to_instructor=cls.other,
            performed_by=cls.org.owner,
        )
        # Noise the old ownership filter showed: owner without any workload / records.
        cls.stale = cls.offering(make_structure(cls.org, code="JPS"), instructor=cls.teacher)
        # (c) canonical handover of a populated legacy journal (no official workload row) → current.
        # Created last: a newer `is_current` period demotes the previous one (handover needs a current one).
        handed = make_structure(cls.org, code="JPH")
        cls.handed = cls.offering(handed, instructor=cls.teacher)
        TeachingHandover.objects.create(
            organization=cls.org,
            offering=cls.handed,
            from_instructor=cls.other,
            to_instructor=cls.teacher,
            performed_by=cls.org.owner,
        )
        Lesson.objects.create(
            organization=cls.org,
            offering=cls.handed,
            date=timezone.localdate(),
            kind="seminar",
            hours=2,
            instructor=cls.other,
            created_by=cls.other,
        )

    @classmethod
    def offering(cls, stack, *, instructor):
        return CourseOffering.objects.create(
            organization=cls.org,
            subject=stack["subject"],
            group=stack["group"],
            period=stack["period"],
            instructor=instructor,
        )

    def setUp(self):
        alias = {self.alias_group.pk: self.alias_stack["group"]}
        for target in (
            "apps.workload.services.journal_assignments.canonical_aliases",
            "apps.registrar.teacher_journal_list.canonical_aliases",
        ):
            patcher = patch(target, return_value=alias)
            patcher.start()
            self.addCleanup(patcher.stop)

    def context(self, user, **params):
        request = RequestFactory().get("/jurnal/", params)
        request.user = user
        request.organization = self.org
        return journal_list_context(user, request)

    def rows(self, data):
        return sorted((o.pk, getattr(o, "journal_entry_kind", "")) for o in data["offerings"])

    def assert_parity(self, **params):
        own = self.context(self.teacher, **params)
        broad = self.context(self.admin, teacher=self.teacher.pk, **params)
        self.assertTrue(broad["journal_is_broad"])
        self.assertTrue(broad["journal_teacher_mirrored"])
        self.assertEqual(self.rows(broad), self.rows(own))
        self.assertEqual(broad["journal_teaching_view"], own["journal_teaching_view"])
        self.assertEqual(
            [(o.pk, o.slot_kinds, o.journal_is_current_load) for o in broad["offerings"]],
            [(o.pk, o.slot_kinds, o.journal_is_current_load) for o in own["offerings"]],
        )
        return own, broad

    def test_current_tab_matches_teacher_own_list(self):
        own, broad = self.assert_parity(year="")
        names = {self.own.pk: "own", self.shared.pk: "shared", self.handed.pk: "handed", self.aliased.pk: "aliased"}
        self.assertEqual({names.get(o.pk, o.pk) for o in own["offerings"]}, set(names.values()))
        self.assertEqual(own["journal_teaching_view"], "current")
        self.assertNotIn(self.stale.pk, {o.pk for o in broad["offerings"]})

    def test_history_tab_matches_teacher_own_list(self):
        own, broad = self.assert_parity(year="", teaching="history")
        self.assertEqual({o.pk for o in own["offerings"]}, {self.taught.pk, self.observed.pk})
        self.assertEqual(broad["journal_teaching_view"], "history")
        # The own-history route answers only request.user; the admin keeps the canonical journal link.
        self.assertTrue(any(o.journal_own_history_link for o in own["offerings"]))
        self.assertFalse(any(o.journal_own_history_link for o in broad["offerings"]))

    def test_default_semester_autoselect_and_kind_filter_match(self):
        own, broad = self.assert_parity()
        self.assertEqual(broad["journal_selected_year"], own["journal_selected_year"])
        self.assertEqual(broad["journal_selected_season"], own["journal_selected_season"])
        for kind in ("lecture", "seminar", "lab"):
            self.assert_parity(year="", kind=kind)
            self.assert_parity(year="", kind=kind, teaching="history")

    def test_view_selector_renders_for_mirrored_teacher_only(self):
        request = RequestFactory().get("/jurnal/")
        request.user = self.admin
        mirrored = self.context(self.admin, teacher=self.teacher.pk, teaching="history", year="")
        html = render_to_string("registrar/partials/_journal_teacher_view.html", mirrored, request=request)
        self.assertIn('name="teaching"', html)
        self.assertNotIn("qeydlərim", html)
        plain = self.context(self.admin, year="")
        html = render_to_string("registrar/partials/_journal_teacher_view.html", plain, request=request)
        self.assertNotIn('name="teaching"', html)

    def test_teacher_without_own_list_authority_keeps_ownership_filter(self):
        outsider = User.objects.create_user("jl-parity-outsider")
        offering = self.offering(make_structure(self.org, code="JPX"), instructor=self.other)
        CourseOffering.objects.filter(pk=offering.pk).update(instructor=None)
        JournalShare.objects.create(organization=self.org, offering=offering, teacher=outsider)
        data = self.context(self.admin, teacher=outsider.pk, year="")
        self.assertFalse(data["journal_teacher_mirrored"])
        self.assertEqual([o.pk for o in data["offerings"]], [offering.pk])
        self.assertEqual(self.context(self.admin, teacher="abc", year="")["offerings"], [])

    def test_history_only_teacher_is_a_picker_candidate(self):
        author = User.objects.create_user("jl-parity-author")
        activate_member(self.org, author, "teacher", permissions=TEACHER_PERMS)
        Lesson.objects.create(organization=self.org, offering=self.stale, date=timezone.localdate(), instructor=author)
        candidates = set(
            teachers_for(CourseOffering.objects.filter(organization=self.org)).values_list("pk", flat=True)
        )
        self.assertTrue({author.pk, self.teacher.pk, self.other.pk} <= candidates)

    def test_my_journals_button_shows_own_list_to_broad_viewer(self):
        """Sahib 2026-11-05: çox jurnal görən hər kəs «Mənim jurnallarım» ilə yalnız öz siyahısını görür."""
        own = {tab: self.rows(self.context(self.teacher, year="", teaching=tab)) for tab in ("current", "history")}
        User.objects.filter(pk=self.teacher.pk).update(is_superuser=True)
        broad_user = User.objects.get(pk=self.teacher.pk)
        data = self.context(broad_user, year="")
        self.assertTrue(data["journal_is_broad"])
        self.assertEqual(data["journal_my_teacher_id"], str(broad_user.pk))
        self.assertEqual(data["journal_selected_teacher"], "")
        request = RequestFactory().get("/jurnal/")
        request.user = broad_user
        html = render_to_string("registrar/partials/_journal_list_content.html", data, request=request)
        self.assertIn(f"?teacher={broad_user.pk}", html)
        for tab, rows in own.items():
            mine = self.context(broad_user, teacher=broad_user.pk, year="", teaching=tab)
            self.assertEqual(mine["journal_selected_teacher"], mine["journal_my_teacher_id"])
            self.assertTrue(mine["journal_teacher_mirrored"])
            self.assertEqual([pk for pk, _kind in self.rows(mine)], [pk for pk, _kind in rows])
        # Öz jurnalı olmayan geniş aktor da düyməni görür (boş siyahı ilə).
        self.assertEqual(self.context(self.admin, year="")["journal_my_teacher_id"], str(self.admin.pk))

    def test_broad_row_shows_current_split_like_teacher_sees_it(self):
        """Sahib 2026-11-05: geniş siyahıda bölünmüş jurnal sahibin adı ilə deyil, cari bölgü ilə görünür."""
        data = self.context(self.admin, year="", q=self.shared.subject.name)
        row = next(o for o in data["offerings"] if o.pk == self.shared.pk)
        teachers = {t["name"]: t["kinds"] for t in row.load_teachers}
        self.assertIn("Seminar", teachers[self.teacher.get_full_name()])
        owner = teachers[self.other.get_full_name() or self.other.username]
        self.assertNotIn("Seminar", owner)
        request = RequestFactory().get("/jurnal/")
        request.user = self.admin
        html = render_to_string("registrar/partials/_journal_list_content.html", data, request=request)
        self.assertIn(self.teacher.get_full_name(), html)
        # Müəllimin öz (mirror) görünüşündə bu sahə hesablanmır — orada sətir müəllimin öz növlərini göstərir.
        mirrored = self.context(self.admin, teacher=self.teacher.pk, year="")
        self.assertFalse(any(getattr(o, "load_teachers", None) for o in mirrored["offerings"]))

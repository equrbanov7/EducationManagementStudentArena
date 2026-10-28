"""«Praktiki məşğələ» — seminarın YALNIZ görünüş adı (sahib 2026-10-28).

Saxlanan növ ``seminar`` qalır; ``CourseOffering.seminar_is_practical`` olan açılışda insana göstərilən etiket
«Praktiki məşğələ»dir (jurnal sütunu / modal / pillələr, cədvəl, «Keçilmiş dərslər», tələbə tarixçəsi). Bayraq:
kafedra müdiri / RİM jurnaldan, RİM kataloq formasından; ilkin dəyər ``set_practical_offerings`` (plan faylı).
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import tempfile
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from apps.audit.models import AuditLog
from apps.legacy_import.services.practical_flag_plan import practical_plan
from apps.organizations.models import Membership
from apps.registrar import practical_label, practical_toggle
from apps.registrar.forms import OfferingForm
from apps.registrar.lessons_log import build_rows
from apps.registrar.models import CourseOffering, Lesson, LessonMark, ScheduleSlot
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
D = datetime.date


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("practical_flag: ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len("practical_flag: ") :].split())
    return out


class PracticalBase(SubgroupFixture, TestCase):
    PREFIX = "prac"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])
            cls.offering = cls.history_g1
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.seminar = Lesson.objects.create(
                organization=cls.org, offering=cls.offering, date=D(2025, 10, 7), kind="seminar"
            )
            cls.lecture = Lesson.objects.create(
                organization=cls.org, offering=cls.offering, date=D(2025, 10, 8), kind="lecture"
            )
            cls.chair_head = cls._member(f"{cls.PREFIX}_head", cls.org.roles.get(name="chair_head"), cls.chair)
            cls.far_head = cls._member(f"{cls.PREFIX}_farhead", cls.org.roles.get(name="chair_head"), cls.far_faculty)

    def flag(self, value=True):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.offering.pk).update(seminar_is_practical=value)


class LabelTest(PracticalBase):
    def test_stored_kind_stays_seminar_label_changes(self):
        with translation.override("az"):
            with bypass_rls():
                self.assertEqual(Lesson.objects.get(pk=self.seminar.pk).get_kind_display(), "Seminar")
                self.flag()
                lesson = Lesson.objects.get(pk=self.seminar.pk)
                self.assertEqual(lesson.kind, "seminar")
                self.assertEqual(lesson.get_kind_display(), "Praktiki məşğələ")
                self.assertEqual(Lesson.objects.get(pk=self.lecture.pk).get_kind_display(), "Mühazirə")
                slot = self.slot(self.offering)
                ScheduleSlot.objects.filter(pk=slot.pk).update(kind="seminar")
                self.assertEqual(ScheduleSlot.objects.get(pk=slot.pk).get_kind_display(), "Praktiki məşğələ")
        with translation.override("en"):
            with bypass_rls():
                self.assertEqual(Lesson.objects.get(pk=self.seminar.pk).get_kind_display(), "Practical session")

    def test_cached_offering_needs_no_query(self):
        self.flag()
        with bypass_rls():
            offering = CourseOffering.objects.get(pk=self.offering.pk)
            lessons = list(offering.lessons.all())
            marks = list(LessonMark.objects.select_related("lesson__offering").filter(lesson__offering=offering))
            with CaptureQueriesContext(connection) as ctx:
                labels = {lesson.get_kind_display() for lesson in lessons}
                for mark in marks:
                    mark.lesson.get_kind_display()
        self.assertEqual(len(ctx.captured_queries), 0)
        self.assertIn(str(practical_label.PRACTICAL_LABEL), labels)

    def test_kind_choices_follow_flag(self):
        with translation.override("az"), bypass_rls():
            plain = dict(practical_label.kind_choices(CourseOffering.objects.get(pk=self.offering.pk)))
            self.flag()
            practical = dict(practical_label.kind_choices(CourseOffering.objects.get(pk=self.offering.pk)))
        self.assertEqual(plain["seminar"], "Seminar")
        self.assertEqual(practical["seminar"], "Praktiki məşğələ")
        self.assertEqual(list(practical), ["lecture", "seminar", "lab"])

    def test_lessons_log_rows(self):
        self.flag()
        with translation.override("az"), bypass_rls():
            rows = build_rows(Lesson.objects.filter(offering=self.offering))
        self.assertEqual({row["kind"]: row["kind_label"] for row in rows}["seminar"], "Praktiki məşğələ")

    def test_offering_form_has_field(self):
        self.assertIn("seminar_is_practical", OfferingForm.Meta.fields)


class JournalPageTest(PracticalBase):
    def test_teacher_sees_label_but_not_toggle(self):
        self.flag()
        response = self.client_for(self.teacher).get(
            reverse("registrar:journal_detail", args=[self.offering.pk]), {"kind": "seminar"}, HTTP_ACCEPT_LANGUAGE="az"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["practical_toggle"])
        self.assertIn(("seminar", "Praktiki məşğələ"), [tuple(row) for row in response.context["lesson_kinds"]])
        self.assertContains(response, 'title="Praktiki məşğələ')
        self.assertNotContains(response, "jd2-practical__btn")

    def test_permissions(self):
        with bypass_rls():
            offering = CourseOffering.objects.select_related("organization").get(pk=self.offering.pk)
        self.assertTrue(practical_toggle.can_toggle(self.owner, offering))
        self.assertTrue(practical_toggle.can_toggle(self.chair_head, offering))
        self.assertFalse(practical_toggle.can_toggle(self.far_head, offering))
        self.assertFalse(practical_toggle.can_toggle(self.teacher, offering))

    def test_permission_revocation_and_custom_role(self):
        with bypass_rls():
            role = self.org.roles.get(name="chair_head")
            role.permissions = [key for key in role.permissions if key != "workload.distribute"]
            role.save(update_fields=["permissions"])
            offering = CourseOffering.objects.select_related("organization").get(pk=self.offering.pk)
            self.assertFalse(practical_toggle.can_toggle(self.chair_head, offering))
            role.name = "custom_practical_editor"
            role.permissions = ["workload.distribute"]
            role.save(update_fields=["name", "permissions"])
            fresh = type(self.chair_head).objects.get(pk=self.chair_head.pk)
            self.assertTrue(practical_toggle.can_toggle(fresh, offering))

    def test_chair_head_toggles_with_audit(self):
        url = reverse("registrar:journal_practical_toggle", args=[self.offering.pk])
        client = self.client_for(self.chair_head)
        self.assertEqual(client.get(url).status_code, 405)
        response = client.post(url, {"on": "1"})
        self.assertRedirects(
            response, reverse("registrar:journal_detail", args=[self.offering.pk]), fetch_redirect_response=False
        )
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).seminar_is_practical)
            self.assertTrue(
                AuditLog.objects.filter(object_id=str(self.offering.pk), new_values__seminar_is_practical=True).exists()
            )
        client.post(url, {"on": "0"})
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.offering.pk).seminar_is_practical)

    def test_teacher_cannot_toggle(self):
        url = reverse("registrar:journal_practical_toggle", args=[self.offering.pk])
        self.assertEqual(self.client_for(self.teacher).post(url, {"on": "1"}).status_code, 404)
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.offering.pk).seminar_is_practical)

    def test_superuser_sees_toggle(self):
        response = self.client_for(self.owner).get(reverse("registrar:journal_detail", args=[self.offering.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["practical_toggle"]["on"], False)
        self.assertContains(response, "jd2-practical__btn")
        self.assertContains(response, "registrar/css/journal_practical.css")


class SetPracticalOfferingsTest(PracticalBase):
    def _call(self, plan, *extra):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(plan, handle)
        out = StringIO()
        call_command(
            "set_practical_offerings",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            "--file",
            handle.name,
            *extra,
            stdout=out,
        )
        return out.getvalue()

    def test_dry_run_apply_idempotent_fill_only(self):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.own_math.pk).update(is_active=False)
            CourseOffering.objects.filter(pk=self.physics_g1.pk).update(seminar_is_practical=True)
        plan = {
            "format": "practical-offerings/1",
            "offerings": [
                str(self.offering.pk),
                str(self.own_math.pk),
                str(self.physics_g1.pk),
                "00000000-0000-0000-0000-000000000000",
            ],
        }
        dry = _counts(self._call(plan))
        self.assertEqual(
            (dry["offerings_set"], dry["offerings_inactive"], dry["offerings_already_set"], dry["offerings_missing"]),
            ("1", "1", "1", "1"),
        )
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.offering.pk).seminar_is_practical, "dry-run yazmır")
        text = self._call(plan, "--apply")
        self.assertEqual(_counts(text)["offerings_set"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).seminar_is_practical)
            self.assertFalse(CourseOffering.objects.get(pk=self.own_math.pk).seminar_is_practical)
            self.assertEqual(Lesson.objects.get(pk=self.seminar.pk).kind, "seminar")
            self.assertTrue(AuditLog.objects.filter(new_values__offering_ids=[str(self.offering.pk)]).exists())
        self.assertEqual(_counts(self._call(plan))["offerings_set"], "0")
        # Fill-only: plandan kənar bayraq söndürülmür.
        self._call({"format": "practical-offerings/1", "offerings": []}, "--apply")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.physics_g1.pk).seminar_is_practical)

    def test_bad_format(self):
        with self.assertRaises(CommandError):
            self._call({"format": "legacy-lesson-kinds/1", "lessons": []})


class PlanRuleTest(TestCase):
    """``practical_plan`` — kod 3 jurnalının açılışları; adi seminar jurnalı ilə bölüşülən açılış atlanır."""

    def test_rule(self):
        def entry(active, *offerings):
            return SimpleNamespace(journal={"active": active}, offerings=[SimpleNamespace(pk=pk) for pk in offerings])

        builder = SimpleNamespace(
            counts={},
            cells=[
                {"journal_uniqid": "P1", "lab": 0, "sem_muh": 3},
                {"journal_uniqid": "P1", "lab": 0, "sem_muh": 0},
                {"journal_uniqid": "P2", "lab": 0, "sem_muh": "3"},
                {"journal_uniqid": "OLD", "lab": 0, "sem_muh": 3},
                {"journal_uniqid": "S", "lab": 0, "sem_muh": 0},
                {"journal_uniqid": "L", "lab": 1, "sem_muh": 3},
            ],
            slices={
                "P1": entry(1, "a", "b"),
                "P2": entry(1, "c"),
                "OLD": entry(0, "d"),
                "S": entry(1, "c"),
                "L": entry(1, "e"),
            },
        )
        from collections import Counter

        builder.counts = Counter()
        plan = practical_plan(builder)
        self.assertEqual(plan, {"format": "practical-offerings/1", "offerings": ["a", "b"]})
        self.assertEqual(builder.counts["offerings_skipped_shared_with_seminar_journal"], 1)
        self.assertEqual(builder.counts["practical_journals_inactive"], 1)
        self.assertEqual(builder.counts["practical_journals"], 2)


class WorkflowTest(TestCase):
    def test_prod_data_ops_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - set_practical_offerings\n", text)
        self.assertIn("'^practical-flag-[0-9a-z-]+$'", text)
        self.assertIn('--file "/tmp/practical_flag_${GITHUB_RUN_ID}.json"', text)
        self.assertIn("/tmp/practical_flag_*.json", text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        for line in (
            "practical_flag: mode=dry_run",
            "practical_flag: offerings_already_set=0 offerings_in_file=214 offerings_inactive=0 offerings_set=214",
        ):
            self.assertRegex(line, pattern)
        self.assertNotRegex("practical_flag: subject=Dizayn əsasları", pattern)
        self.assertEqual(text.count("            set_practical_offerings)\n"), 2)


class MembershipSanityTest(PracticalBase):
    def test_chair_head_membership_scoped_to_chair(self):
        with bypass_rls():
            self.assertTrue(
                Membership.objects.filter(user=self.chair_head, role__name="chair_head", scope_unit=self.chair).exists()
            )

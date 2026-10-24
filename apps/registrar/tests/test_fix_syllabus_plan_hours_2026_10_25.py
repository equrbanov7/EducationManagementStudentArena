"""``fix_syllabus_plan_hours`` — mövcud sillabusların plan saatı bir qrupun saatına (sahib 2026-10-25).

Quru icra heç nə yazmır; ``--apply`` qaralamanı (105 → 75) və saatı SƏHV olan təsdiqlənmiş versiyanı düzəldir,
plan saatı BOŞ olan təsdiqlənmiş versiyaya yalnız ``--fill-empty`` ilə toxunur; həftəlik bölgü dəyişmir; təkrar
icra 0 yazır; kafedranın düzəlişi (``plan_hours_override``) avtomatik hesabdan üstündür.
"""

import pathlib
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.syllabus import services
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
_PATCH = "apps.registrar.management.commands.fix_syllabus_plan_hours.plan_hours_for_offering"
GROUP_HOURS = {"lecture": 45, "seminar": 30}


class FixSyllabusPlanHoursTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("syl-fix-hours")
        cls.teacher = User.objects.create_user("fix_teacher", "fix_teacher@x.test", "StrongPass123!")
        activate_member(
            cls.org, cls.teacher, "teacher", permissions=["syllabus.view", "syllabus.edit", "grade.input"], level=60
        )
        actor = services.resolve_actor(cls.teacher, cls.org)
        cls.items = []
        for code in ("FIX101", "FIX202", "FIX303"):
            stack = make_academic_stack(cls.org, code=code)
            syllabus, version = services.create_draft(
                organization=cls.org,
                subject=stack["subject"],
                period=stack["period"],
                actor=actor,
                offering=make_offering(cls.org, stack, cls.teacher),
                program=stack["program"],
                chair_unit=stack["chair"],
                author=cls.teacher,
                plan_hours={"lecture": 45, "seminar": 60},
            )
            cls.items.append((syllabus, version))
        cls.draft = cls.items[0][1]
        # Saatı səhv yazılmış təsdiqlənmiş versiya (köçürülmüş) və plan saatı boş olan təsdiqlənmiş versiya.
        cls.approved_wrong = cls._approved(cls.items[1][0], {"lecture": 45, "seminar": 60})
        cls.approved_empty = cls._approved(cls.items[2][0], {})

    @classmethod
    def _approved(cls, syllabus, hours):
        return SyllabusVersion.objects.create(
            organization=cls.org,
            syllabus=syllabus,
            major=1,
            minor=5,
            status="approved",
            approval_source="migration",
            locked_at=timezone.now(),
            plan_hours=hours,
        )

    def _run(self, *args) -> str:
        out = StringIO()
        call_command("fix_syllabus_plan_hours", *args, stdout=out)
        return out.getvalue()

    def _hours(self, version):
        version.refresh_from_db()
        return version.plan_hours

    @mock.patch(_PATCH, return_value=GROUP_HOURS)
    def test_dry_run_writes_nothing(self, _plan):
        output = self._run()
        self.assertIn("QURU İCRA", output)
        self.assertEqual(self._hours(self.draft), {"lecture": 45, "seminar": 60})
        self.assertEqual(self._hours(self.approved_wrong), {"lecture": 45, "seminar": 60})

    @mock.patch(_PATCH, return_value=GROUP_HOURS)
    def test_apply_fixes_draft_and_wrong_approved_keeps_week_rows(self, _plan):
        week = SyllabusSection.objects.get(version=self.draft, section_id="week")
        week.data = {"rows": [{"topic": "A", "lecture": 2, "seminar": 2}]}
        week.save(update_fields=["data"])
        self._run("--apply")
        self.assertEqual(self._hours(self.draft), GROUP_HOURS)
        self.assertEqual(self._hours(self.approved_wrong), GROUP_HOURS)
        self.assertEqual(self._hours(self.approved_empty), {})
        week.refresh_from_db()
        self.assertEqual(week.data["rows"], [{"topic": "A", "lecture": 2, "seminar": 2}])
        self.assertIn("✅ 0", self._run("--apply"))  # idempotent

    @mock.patch(_PATCH, return_value=GROUP_HOURS)
    def test_fill_empty_and_override_priority(self, _plan):
        Syllabus.objects.filter(pk=self.items[2][0].pk).update(plan_hours_override={"lecture": 30, "seminar": 45})
        self._run("--fill-empty", "--apply")
        self.assertEqual(self._hours(self.approved_empty), {"lecture": 30, "seminar": 45})
        self.assertEqual(self._hours(self.items[2][1]), {"lecture": 30, "seminar": 45})


class ProdDataOpsWhitelistTests(SimpleTestCase):
    def test_command_is_whitelisted_with_fixed_args(self):
        text = (pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("          - fix_syllabus_plan_hours\n", text)
        branch = text[text.index("            fix_syllabus_plan_hours)") :]
        branch = branch[: branch.index(";;")]
        self.assertIn('args=(--org "$ORG")', branch)
        self.assertIn("args+=(--fill-empty)", branch)

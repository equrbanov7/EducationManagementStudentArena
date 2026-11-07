"""share_mexanika_syllabi_20261107: dry-run / apply / idempotence / guarded stray draft / undo + prod-data-ops wiring."""

import datetime as dt
import io
import os
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

import yaml

from apps.accounts.models import UserProfile
from apps.legacy_import.services import mexanika_syllabi_20261107 as service
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.models import Syllabus, SyllabusShare, SyllabusVersion
from apps.syllabus.public import import_migrated_version
from core.rls import bypass_rls

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/prod-data-ops.yml"
COMMAND = "share_mexanika_syllabi_20261107"


def _run(*args):
    out = io.StringIO()
    call_command(COMMAND, "--actor", "mxsyl_admin", *args, stdout=out)
    return out.getvalue()


class MexanikaSyllabiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.actor = User.objects.create_superuser("mxsyl_admin", "admin@example.test", "test")
        with bypass_rls():
            cls.org = Organization.objects.create(
                id=ORG, name="QKU", slug="qku", org_type="university", owner=cls.actor, status="active"
            )
            cls.teacher = User.objects.create_user(username="mxsyl.teacher", first_name="Müəllim")
            UserProfile.objects.filter(user=cls.teacher).update(organization=cls.org)
            Membership.objects.create(user=cls.teacher, organization=cls.org, role=cls.org.roles.get(name="teacher"))
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type="semester",
                start_date=dt.date(2026, 9, 1),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            subject = Subject.objects.create(organization=cls.org, code="QKU-9901", name="Robotexnika")
            offerings = []
            for name in ("233 K az", "2232 K", "233 EKO az"):
                group = OrgUnit.objects.create(
                    organization=cls.org, name=name, slug=f"mx-{len(offerings)}", unit_type="group"
                )
                offerings.append(
                    CourseOffering.objects.create(
                        organization=cls.org,
                        subject=subject,
                        period=period,
                        group=group,
                        instructor=cls.teacher,
                        lesson_hours=45,
                    )
                )
            cls.main, cls.stray_offering, cls.other = offerings
            common = dict(organization=cls.org, subject=subject, period=period, author=cls.teacher)
            cls.source, _ = import_migrated_version(
                offering=cls.main, approved_at=timezone.now(), section_data={}, **common
            )
            cls.stray, cls.stray_version = import_migrated_version(
                offering=cls.stray_offering, approved_at=timezone.now(), section_data={}, **common
            )
            # «Kopyala» ilə açılmış, təqdim edilməmiş qaralama.
            SyllabusVersion.objects.filter(pk=cls.stray_version.pk).update(
                status=SyllabusStatus.DRAFT, approved_at=None, submitted_at=None
            )
            Syllabus.objects.filter(pk=cls.stray.pk).update(approved_version=None)
        cls.patches = (
            patch.object(
                service, "STRAY_DRAFT", (str(cls.stray.pk), str(cls.stray_version.pk), str(cls.stray_offering.pk))
            ),
            patch.object(
                service,
                "LINKS",
                (
                    ("stray", str(cls.source.pk), str(cls.stray_offering.pk)),
                    ("eko", str(cls.source.pk), str(cls.other.pk)),
                ),
            ),
        )

    def setUp(self):
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_dry_run_apply_idempotent_and_undo(self):
        dry = _run()
        self.assertIn("mode=dry_run", dry)
        self.assertIn("linked=2", dry)
        self.assertIn("stray_draft_retired=1", dry)
        self.assertFalse(SyllabusShare.objects.exists())
        self.assertTrue(Syllabus.objects.get(pk=self.stray.pk).is_active)

        applied = _run("--apply")
        batch = re.search(r"batch=(mxsyl-\S+)", applied).group(1)
        self.assertEqual(SyllabusShare.objects.filter(syllabus=self.source).count(), 2)
        self.assertFalse(Syllabus.objects.get(pk=self.stray.pk).is_active)

        again = _run("--apply")
        self.assertIn("already=2", again)
        self.assertIn("stray_draft_already_inactive=1", again)
        self.assertNotIn("batch=", again)

        undone = _run("--apply", "--undo", batch)
        self.assertIn("shares_removed=2", undone)
        self.assertIn("stray_draft_restored=1", undone)
        self.assertFalse(SyllabusShare.objects.exists())
        self.assertTrue(Syllabus.objects.get(pk=self.stray.pk).is_active)
        self.assertIn("already_undone=1", _run("--apply", "--undo", batch))

    def test_touched_draft_is_not_retired(self):
        Syllabus.objects.filter(pk=self.stray.pk).update(offering=self.other)
        out = _run("--apply")
        self.assertIn("skipped_stray_draft_changed=1", out)
        self.assertTrue(Syllabus.objects.get(pk=self.stray.pk).is_active)

    def test_rejects_bad_undo_and_non_superuser(self):
        with self.assertRaises(CommandError):
            _run("--undo", "mxsyl-bad")
        get_user_model().objects.filter(username="mxsyl_admin").update(is_superuser=False)
        with self.assertRaises(CommandError):
            _run()


def _bash(block, **env):
    script = (
        'set -euo pipefail\nmatch() { printf \'%s\' "$1" | grep -Eq -- "$2"; }\n'
        "superadmin_actor() { printf 'fixture-actor'; }\n" + block + '\nprintf "ARG:%s\\n" "${args[@]}"\n'
    )
    base = {"BATCH": "", "APPLY": "false", "ORG": "qku"}
    return subprocess.run(["bash", "-c", script], env={**os.environ, **base, **env}, capture_output=True, text=True)


class MexanikaSyllabiWorkflowTests(SimpleTestCase):
    def test_whitelisted_with_case_filter_and_guarded_undo(self):
        text = WORKFLOW.read_text()
        options = yaml.safe_load(text)[True]["workflow_dispatch"]["inputs"]["command"]["options"]
        self.assertEqual(options.count(COMMAND), 1)
        self.assertIn(f'elif [ "$COMMAND" = "{COMMAND}" ]; then', text)
        block = re.search(rf"            {COMMAND}\)\n(.*?)              ;;", text, re.S).group(1)
        result = _bash(block)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith("ARG:--org\nARG:qku\nARG:--actor\nARG:fixture-actor\n"))
        result = _bash(block, BATCH="mxsyl-20261107-120000-abcd", APPLY="true")
        self.assertIn("ARG:--undo\nARG:mxsyl-20261107-120000-abcd", result.stdout)
        self.assertNotEqual(_bash(block, BATCH="mxsyl-20261107-120000-abcd").returncode, 0)
        pattern = re.search(r"grep -E '(\^mexanika_syllabi:[^']+)'", text).group(1)
        self.assertRegex("mexanika_syllabi: mode=apply linked=4 stray_draft_retired=1", pattern)
        self.assertRegex("mexanika_syllabi: entry=rust_2232k result=linked", pattern)
        self.assertNotRegex("mexanika_syllabi: teacher=Real Person", pattern)

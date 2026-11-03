"""Sahib 2026-11-04: ``merge_subjects`` PLAN rejimi (çoxlu cüt, bir backup, cüt başına tranzaksiya), SAYT kodları
(saxlanılan YALNIZ QKU, SAYT mənbə), ``recode_site_subjects`` (qalan SAYT → növbəti QKU-N, undo) və workflow girişləri.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Subject
from apps.registrar.subject_merge import AUDIT_RESOURCE
from apps.registrar.subject_merge_plan import parse_plan
from core.rls import bypass_rls

from .subject_merge_fixture import SubjectMergeBase

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
REASON = "Dublikat fənn kartları — sahibin 2026-11-04 təsdiqi (plan rejimi)"


def _run(*args):
    out = StringIO()
    call_command(*args, stdout=out)
    return out.getvalue()


class MergePlanTest(SubjectMergeBase):
    def setUp(self):
        with bypass_rls():
            self.keep_a = Subject.objects.create(organization=self.org, code="QKU-101", name="Alfa", ects=5)
            self.site_a = Subject.objects.create(organization=self.org, code="SAYT-0101", name="Alfa ", ects=5)
            self.keep_b = Subject.objects.create(organization=self.org, code="QKU-102", name="Beta", ects=5)
            self.src_b = Subject.objects.create(organization=self.org, code="QKU-202", name="Beta", ects=5)
            self.keep_c = Subject.objects.create(organization=self.org, code="QKU-103", name="Qamma", ects=5)
            self.src_c1 = Subject.objects.create(organization=self.org, code="QKU-203", name="Qamma", ects=5)
            self.src_c2 = Subject.objects.create(organization=self.org, code="SAYT-0103", name="Qamma", ects=5)
        self.moved_a = self.offering(self.site_a, self.group1)
        self.offering(self.keep_b, self.group1)  # B: eyni qrupda iki AKTİV açılış → toqquşma
        self.blocked_b = self.offering(self.src_b, self.group1)
        self.moved_c = self.offering(self.src_c2, self.group2)
        self.plan = "QKU-101:SAYT-0101; QKU-102:QKU-202 ;QKU-103:QKU-203,SAYT-0103"

    def test_dry_run_reports_each_pair_and_writes_nothing(self):
        text = _run("merge_subjects", "--org", self.org.slug, "--plan", self.plan)
        self.assertIn("[1/3] QKU-101 ← SAYT-0101: OK (dry-run)", text)
        self.assertIn("[2/3] QKU-102 ← QKU-202: ATLANDI — 1 toqquşma", text)
        self.assertIn("TOQQUŞMA:", text)
        self.assertIn("merge_plan: mode=dry_run pairs=3 ok=2 conflict=1 error=0", text)
        self.assertFalse(Subject.objects.get(pk=self.site_a.pk).is_archived)

    def test_apply_merges_good_pairs_and_skips_the_conflicting_one(self):
        text = _run("merge_subjects", "--org", self.org.slug, "--plan", self.plan, "--apply", "--reason", REASON)
        self.assertIn("merge_plan: mode=apply pairs=3 ok=2 conflict=1 error=0", text)
        audit_ids = re.findall(r"audit=([0-9a-f-]{36})", text)
        self.assertEqual(len(audit_ids), 2)
        self.assertEqual(AuditLog.objects.filter(resource_type=AUDIT_RESOURCE).count(), 2)
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=self.moved_a.pk).subject_id, self.keep_a.pk)
            self.assertEqual(CourseOffering.objects.get(pk=self.moved_c.pk).subject_id, self.keep_c.pk)
            self.assertEqual(CourseOffering.objects.get(pk=self.blocked_b.pk).subject_id, self.src_b.pk)
        archived = set(Subject.objects.filter(is_archived=True).values_list("code", flat=True))
        self.assertEqual(archived, {"SAYT-0101", "QKU-203", "SAYT-0103"})
        # hər cüt ayrıca geri qaytarılır
        _run("undo_subject_merge", "--audit-id", audit_ids[0], "--apply", "--reason", REASON)
        self.assertFalse(Subject.objects.get(pk=self.site_a.pk).is_archived)
        self.assertTrue(Subject.objects.get(pk=self.src_c2.pk).is_archived)

    def test_plan_validation(self):
        for bad in (
            "SAYT-0101:QKU-101",  # saxlanılan SAYT ola bilməz
            "QKU-101:SAYT-0101;QKU-101:QKU-202",  # kod iki dəfə
            "QKU-101:SAYT-0101;SAYT-0101:QKU-202",  # zəncir
            "QKU-101",
            "QKU-101:MYEDU-5",
            "",
        ):
            with self.subTest(plan=bad), self.assertRaises(CommandError):
                parse_plan(bad)
        self.assertEqual(parse_plan(" QKU-1 : SAYT-2 , QKU-3 "), [("QKU-1", ["SAYT-2", "QKU-3"])])
        with self.assertRaises(CommandError):
            _run("merge_subjects", "--org", self.org.slug, "--plan", self.plan, "--target", "QKU-101")


class RecodeSiteSubjectsTest(SubjectMergeBase):
    def setUp(self):
        with bypass_rls():
            Subject.objects.create(organization=self.org, code="QKU-50", name="Mövcud fənn")
            Subject.objects.create(organization=self.org, code="QKU-7", name="Vo İP sistemləri (QKU)")
            self.unique = Subject.objects.create(organization=self.org, code="SAYT-0001", name="Unikal fənn")
            self.second = Subject.objects.create(organization=self.org, code="SAYT-0010", name="İkinci fənn")
            self.dup = Subject.objects.create(organization=self.org, code="SAYT-0002", name="Mövcud  FƏNN")
            self.archived = Subject.objects.create(
                organization=self.org, code="SAYT-0003", name="Arxiv", is_archived=True, is_active=False
            )
            self.excluded = Subject.objects.create(organization=self.org, code="SAYT-0004", name="Gözləyən")
        self.offering_row = self.offering(self.unique, self.group1)

    def test_dry_run_apply_and_undo(self):
        dry = _run("recode_site_subjects", "--org", self.org.slug, "--exclude", "SAYT-0004")
        self.assertIn("SAYT-0001 → QKU-51", dry)
        self.assertIn("SAYT-0010 → QKU-52", dry)
        self.assertIn("SAYT-0002: QKU dublikatı var", dry)
        self.assertIn("site_recode: mode=dry_run batch=none", dry)
        self.assertIn("has_qku_duplicate=1", dry)
        self.assertIn("archived_skipped=1", dry)
        self.assertIn("excluded=1", dry)
        self.assertEqual(Subject.objects.get(pk=self.unique.pk).code, "SAYT-0001")

        text = _run("recode_site_subjects", "--org", self.org.slug, "--exclude", "SAYT-0004", "--apply")
        batch = re.search(r"batch=(sitecode-\S+)", text).group(1)
        self.unique.refresh_from_db()
        self.assertEqual(self.unique.code, "QKU-51")
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=self.offering_row.pk).subject_id, self.unique.pk)
        for row, code in ((self.dup, "SAYT-0002"), (self.archived, "SAYT-0003"), (self.excluded, "SAYT-0004")):
            row.refresh_from_db()
            self.assertEqual(row.code, code)
        again = _run("recode_site_subjects", "--org", self.org.slug, "--exclude", "SAYT-0004")
        self.assertIn("recoded=0", again)

        _run("recode_site_subjects", "--org", self.org.slug, "--undo", batch, "--apply")
        self.unique.refresh_from_db()
        self.assertEqual(self.unique.code, "SAYT-0001")
        with self.assertRaises(CommandError):
            _run("recode_site_subjects", "--org", self.org.slug, "--undo", batch, "--apply")

    def test_bad_exclude_is_rejected(self):
        with self.assertRaises(CommandError):
            _run("recode_site_subjects", "--org", self.org.slug, "--exclude", "QKU-1")


class PlanAndRecodeWorkflowTest(TestCase):
    def _block(self, name):
        text = WORKFLOW.read_text(encoding="utf-8")
        return re.findall(rf"            {name}\)\n(.*?)\n              ;;\n", text, re.S)[0]

    def _run(self, name, **env):
        script = (
            "set -euo pipefail\n"
            "match() { case \"$1\" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; "
            'printf \'%s\' "$1" | grep -Eq -- "$2"; }\n' + self._block(name) + '\nprintf "ARG:%s\\n" "${args[@]}"\n'
        )
        base = {"ORG": "qku", "APPLY": "false", "BATCH": "", "TEACHER": "", "CREATE_MISSING": "false"}
        return subprocess.run(
            ["bash", "-c", script], env={**os.environ, **base, **env}, capture_output=True, text=True, check=False
        )

    def test_merge_subjects_accepts_sayt_sources_and_plan(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - recode_site_subjects\n", text)
        single = self._run("merge_subjects", TEACHER="QKU-934", BATCH="SAYT-0004")
        self.assertEqual(single.returncode, 0, single.stderr)
        self.assertIn("ARG:--source=SAYT-0004", single.stdout)
        self.assertNotEqual(self._run("merge_subjects", TEACHER="SAYT-0004", BATCH="QKU-934").returncode, 0)
        plan = ";".join(f"QKU-{n}:SAYT-{n:04d}" for n in range(1, 96)) + ";QKU-500:QKU-501,QKU-502"
        ok = self._run("merge_subjects", BATCH=plan)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn(f"ARG:--plan={plan}", ok.stdout)
        for env in (
            {"BATCH": plan, "TEACHER": "QKU-1"},
            {"BATCH": "SAYT-1:QKU-2"},
            {"BATCH": "QKU-1:SAYT-2;;QKU-3:QKU-4"},
            {"BATCH": "QKU-1:SAYT-2\nQKU-3:QKU-4"},
        ):
            self.assertNotEqual(self._run("merge_subjects", **env).returncode, 0, env)

    def test_recode_arguments(self):
        self.assertEqual(self._run("recode_site_subjects").stdout, "ARG:--org\nARG:qku\n")
        undo = self._run("recode_site_subjects", BATCH="sitecode-20261104-120000-ab12", APPLY="true")
        self.assertIn("ARG:--undo=sitecode-20261104-120000-ab12\nARG:--apply", undo.stdout)
        exclude = self._run("recode_site_subjects", BATCH="SAYT-0012,SAYT-0013")
        self.assertIn("ARG:--exclude=SAYT-0012,SAYT-0013", exclude.stdout)
        self.assertNotEqual(self._run("recode_site_subjects", BATCH="QKU-1").returncode, 0)

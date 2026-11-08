"""Sahib 2026-11-07: 1-ci kurslar — köhnə sistemin Lab-1 / Lab-2 bölgüsü və ADİAK alt qrup payları.

* plan faylı: hər jurnalda siyahılar kəsişmir, ölçülər köhnə sistemin siyahılarındandır, yalnız id var;
* ``apply_first_year_splits_20261107``: defolt dry-run, ``--apply``, idempotent; lab qrupu başqa dəyərin üzərinə
  yazılmır; köçürülmüş lab dərsi xanalarının qrupuna bağlanır; ADİAK-da ikinci müəllimin payı yalnız öz alt qrupunu,
  sahibin («köhnə sistem» mənbəli) payı öz alt qrupunu daşıyır; sahib dəyişibsə və ya siyahı uyğun gəlmirsə atlanır;
  stdout-da yalnız saylar; prod-data-ops-a qoşulub.
"""

from __future__ import annotations

import io
import json
import re
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.registrar import first_year_splits_2026_11_07 as splits
from apps.registrar import journal_shares
from apps.registrar.models import Enrollment, JournalShare, JournalShareSource, Lesson, LessonMark
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, User, _LabWorld
from core.rls import bypass_rls

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class FirstYearSplitsPlanTest(SimpleTestCase):
    def test_plan_lists_are_disjoint_ids_of_the_legacy_sizes(self):
        data = json.loads(splits.PLAN_PATH.read_text(encoding="utf-8"))
        sizes = {key: tuple(len(spec["groups"][g]) for g in ("1", "2")) for key, spec in data["lab"].items()}
        self.assertEqual(
            sizes,
            {
                "phys_bio": (15, 15),
                "phys_sbio": (23, 18),
                "phys_k": (15, 16),
                "phys_ke": (20, 20),
                "phys_em": (19, 19),
                "chem_m": (20, 20),
            },
        )
        shares = {key: (len(spec["owner_rows"]), len(spec["other_rows"])) for key, spec in data["shares"].items()}
        self.assertEqual(
            shares,
            {
                "adiak_sbio": (18, 19),
                "adiak_m": (19, 17),
                "adiak_em": (18, 19),
                "adiak_ke": (20, 20),
                "adiak_it": (20, 19),
            },
        )
        for spec in data["lab"].values():
            one, two = (set(spec["groups"][g]) for g in ("1", "2"))
            self.assertFalse(one & two)
            self.assertTrue(all(UUID.match(pk) for pk in one | two))
        for spec in data["shares"].values():
            self.assertFalse(set(spec["owner_rows"]) & set(spec["other_rows"]))
            self.assertTrue(all(UUID.match(pk) for pk in spec["owner_rows"] + spec["other_rows"]))


class ApplyFirstYearSplitsCommandTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            Enrollment.objects.filter(offering=self.offering).update(lab_group=None)
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.colleague = User.objects.create_user("lab_colleague", "lab_colleague@x.test", "pw")
        self._member(self.colleague, "teacher", ["grade.input"])
        offering = str(self.offering.pk)
        self.plan = {
            "lab": {
                "phys_k": {
                    "offering": offering,
                    "groups": {"1": [str(self.e1.pk), "00000000-0000-0000-0000-000000000001"], "2": [str(self.e2.pk)]},
                }
            },
            "shares": {
                "adiak_ke": {
                    "offering": offering,
                    "owner": self.teacher.pk,
                    "owner_rows": [str(self.e1.pk)],
                    "other_rows": [str(self.e2.pk)],
                }
            },
        }
        patch = mock.patch.object(splits, "plan", lambda: self.plan)
        patch.start()
        self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "apply_first_year_splits_20261107",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^lab_groups: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("lab_groups: ") :].split())
        return counts

    def _other_share(self):
        with bypass_rls():
            return JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.colleague, kinds=["seminar"]
            )

    def test_dry_run_apply_idempotent(self):
        legacy_lab = self._lesson()
        other = self._other_share()
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=legacy_lab, enrollment=self.e1, status="present")
        dry = self._call()
        self.assertEqual(
            {k: dry.get(k) for k in ("phys_k_lab_first", "phys_k_lab_second", "phys_k_not_enrolled")},
            {"phys_k_lab_first": "1", "phys_k_lab_second": "1", "phys_k_not_enrolled": "1"},
        )
        self.assertEqual(
            (dry["adiak_ke_owner_share_created"], dry["adiak_ke_owner_split"], dry["adiak_ke_other_split"]),
            ("1", "1", "1"),
        )
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, lab_group__isnull=False).exists())
            self.assertFalse(JournalShare.objects.filter(offering=self.offering, teacher=self.teacher).exists())
        self._call("--apply")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.e1.pk).lab_group, 1)
            self.assertEqual(Enrollment.objects.get(pk=self.e2.pk).lab_group, 2)
            self.assertEqual(Lesson.objects.get(pk=legacy_lab.pk).lab_group, 1)
            own = JournalShare.objects.get(offering=self.offering, teacher=self.teacher, is_active=True)
            self.assertEqual(own.source, JournalShareSource.LEGACY)
            self.assertEqual(set(own.enrollments.all()), {self.e1})
            self.assertEqual(set(JournalShare.objects.get(pk=other.pk).enrollments.all()), {self.e2})
            colleague_scope = journal_shares.journal_scope(self.colleague, self._fresh())
            owner_scope = journal_shares.journal_scope(self.teacher, self._fresh())
        self.assertEqual(colleague_scope.enrollment_ids, frozenset({str(self.e2.pk)}))
        self.assertEqual(owner_scope.enrollment_ids, frozenset({str(self.e1.pk), str(self.e0.pk)}))
        again = self._call("--apply")
        self.assertEqual((again["phys_k_already"], again["phys_k_lesson_already"]), ("2", "1"))
        self.assertEqual((again["adiak_ke_owner_already"], again["adiak_ke_other_already"]), ("1", "1"))
        self.assertNotIn("phys_k_lab_first", again)

    def test_never_overwrites_another_lab_group(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.e1.pk).update(lab_group=2)
        self.assertEqual(self._call("--apply")["phys_k_conflict"], "1")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.e1.pk).lab_group, 2)

    def test_share_guards(self):
        self.assertEqual(self._call("--apply")["adiak_ke_other_share_ambiguous_skipped"], "1")
        self._other_share()
        self.plan["shares"]["adiak_ke"]["owner"] = self.colleague.pk
        self.assertEqual(self._call("--apply")["adiak_ke_owner_changed_skipped"], "1")
        self.plan["shares"]["adiak_ke"]["owner"] = self.teacher.pk
        self.plan["shares"]["adiak_ke"]["other_rows"] = ["00000000-0000-0000-0000-000000000002"]
        self.assertEqual(self._call("--apply")["adiak_ke_roster_changed_skipped"], "1")
        with bypass_rls():
            self.assertFalse(JournalShare.objects.filter(offering=self.offering, teacher=self.teacher).exists())

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - apply_first_year_splits_20261107\n", text)
        self.assertIn('[ "$COMMAND" = "apply_first_year_splits_20261107" ]', text)
        self.assertIn("|apply_first_year_splits_20261107|", text)

"""Keçilmiş dərsin müəllimi bərpası (sahib 2026-11-13) — ``restore_lesson_authors_20261113``.

Ssenari (Enzimologiya 234 BİO az kimi): açılış A-nındır; köhnə sistemdə mühazirə jurnalı A-da, seminar jurnalı
B-də idi. Delta dərsləri BOŞ ``instructor`` ilə yaradıb — hamısı A-ya düşürdü. Bərpadan sonra mühazirə → A,
seminar → B; dolu müəllim saxlanır; iki iddialı slot yalnız TƏK sahib / pay müəllimi ilə həll olunur; yeni
sistemdə yaradılmış boş dərs cari sahibə gedir (dərsdən sonra təhvil yoxdursa); ``--undo`` yalnız bu əmrin
yazdığını və hələ də eyni müəllimdə olanı boşaldır.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.audit.models import AuditLog
from apps.legacy_import.management.commands import restore_lesson_authors_20261113 as command
from apps.legacy_import.services import lesson_authors_2026_11_13 as service
from apps.organizations.models import OrgUnit
from apps.registrar import lessons_log
from apps.registrar.models import CourseOffering, JournalShare, Lesson, LessonKind, Subject, TeachingHandover
from apps.registrar.tests.test_teaching_handover import HandoverBase
from core.constants import OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

LEGACY_GROUP = 642
LEGACY_SUBJECT = 1206
WORKER_A, WORKER_B, WORKER_C, WORKER_D = 167, 933, 555, 777
LECTURE_SLOTS = ["2024-10-01 10:10", "2024-10-08 10:10"]
SEMINAR_SLOTS = ["2024-10-02 11:50", "2024-10-09 11:50"]


def _journal(legacy_id, teacher, slots, *, subject=None, user=None):
    return {
        "legacy_id": legacy_id,
        "teacher": teacher,
        "user": user,
        "subject": subject or {"id": LEGACY_SUBJECT, "name": "Enzimologiya"},
        "groups": [{"id": LEGACY_GROUP, "name": "GA"}],
        "slots": list(slots),
    }


def _parse(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("twin_merge: "):
            out.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
    return out


class _Base(HandoverBase):
    """``HandoverBase`` + delta açarları (qrup slug-ı ``myedu-grp-642``, fənn kodu ``QKU-1206``)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            OrgUnit.objects.filter(pk=cls.group_a.pk).update(slug=f"myedu-grp-{LEGACY_GROUP}")
            Subject.objects.filter(pk=cls.offering_a.subject_id).update(
                code=f"QKU-{LEGACY_SUBJECT}", name="Enzimologiya"
            )
            cls.admin = User.objects.create_user("la_admin", "la_admin@qku.edu.az", "pw")
            cls.admin.is_superuser = True
            cls.admin.save(update_fields=["is_superuser"])
        cls.teacher_a, cls.teacher_b = cls.old_teacher, cls.other_teacher

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="lesson_authors_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        with bypass_rls():
            self.share_b = JournalShare.objects.create(
                organization=self.org,
                offering=self.offering_a,
                teacher=self.teacher_b,
                source="workload",
                kinds=["seminar"],
            )
            self.lectures = [self._lesson(slot, LessonKind.LECTURE) for slot in LECTURE_SLOTS]
            self.seminars = [self._lesson(slot, LessonKind.SEMINAR) for slot in SEMINAR_SLOTS]
        self.workers = {
            str(WORKER_A): str(self.teacher_a.pk),
            str(WORKER_B): str(self.teacher_b.pk),
            str(WORKER_C): str(self.new_teacher.pk),
            str(WORKER_D): str(self.dean.pk),
        }

    def _lesson(self, slot, kind, *, offering=None, **extra):
        day, clock = slot.split(" ")
        return Lesson.objects.create(
            organization=self.org,
            offering=offering or self.offering_a,
            date=datetime.date.fromisoformat(day),
            start_time=datetime.time.fromisoformat(clock),
            kind=kind,
            hours=2,
            **extra,
        )

    def _evidence(self, journals=None, *, period=None, name="evidence.json", **extra):
        data = {
            "format": service.FORMAT,
            "semester": 14,
            "period": period or {"name": "Payız", "academic_year": "2024/2025"},
            "cutoff": "2024-12-31",
            "journals": (
                journals
                if journals is not None
                else [_journal(1, WORKER_A, LECTURE_SLOTS), _journal(2, WORKER_B, SEMINAR_SLOTS)]
            ),
        }
        data.update(extra)
        path = f"{self.tmp}/{name}"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        return path

    def _run(self, path=None, *, apply=False, undo=False, actor=None):
        out = StringIO()
        args = ["restore_lesson_authors_20261113", "--org", self.org.slug, "--actor", actor or self.admin.username]
        if path:
            args += ["--file", path]
        if apply:
            args.append("--apply")
        if undo:
            args.append("--undo")
        with mock.patch.object(service, "ledger_map", return_value=self.workers):
            call_command(*args, stdout=out)
        return out.getvalue()

    def _owners(self, lessons):
        with bypass_rls():
            return [Lesson.objects.get(pk=lesson.pk).instructor_id for lesson in lessons]


class ApplyTest(_Base):
    def test_lectures_go_to_owner_and_seminars_to_the_seminar_teacher(self):
        counts = _parse(self._run(self._evidence(), apply=True))
        self.assertEqual(self._owners(self.lectures), [self.teacher_a.pk] * 2)
        self.assertEqual(self._owners(self.seminars), [self.teacher_b.pk] * 2)
        self.assertEqual(counts["lessons_stamped"], "4")
        self.assertEqual(counts["lessons_to_non_owner"], "2")
        self.assertEqual(counts["slot_matched"], "4")
        with bypass_rls():
            audit = AuditLog.objects.get(organization=self.org, resource_type=service.RESOURCE)
            self.assertEqual(audit.resource_id, str(self.offering_a.pk))
            self.assertEqual(
                audit.new_values["lessons"],
                {str(lesson.pk): self.teacher_a.pk for lesson in self.lectures}
                | {str(lesson.pk): self.teacher_b.pk for lesson in self.seminars},
            )
            mine_b = set(
                lessons_log.scoped_lessons(self.teacher_b, self.org, supervisor=False).values_list("pk", flat=True)
            )
            mine_a = set(
                lessons_log.scoped_lessons(self.teacher_a, self.org, supervisor=False).values_list("pk", flat=True)
            )
        self.assertEqual(mine_b, {lesson.pk for lesson in self.seminars})
        self.assertTrue({lesson.pk for lesson in self.lectures} <= mine_a)
        self.assertFalse({lesson.pk for lesson in self.seminars} & mine_a)

    def test_dry_run_writes_nothing(self):
        output = self._run(self._evidence())
        counts = _parse(output)
        self.assertIn("twin_merge: mode=dry_run", output)
        self.assertEqual(counts["lesson_legacy_planned"], "4")
        self.assertEqual(self._owners(self.lectures + self.seminars), [None] * 4)
        with bypass_rls():
            self.assertFalse(AuditLog.objects.filter(resource_type=service.RESOURCE).exists())

    def test_rerun_is_idempotent(self):
        path = self._evidence()
        self._run(path, apply=True)
        counts = _parse(self._run(path, apply=True))
        self.assertEqual(counts.get("lessons_stamped", "0"), "0")
        self.assertEqual(counts["lesson_already"], "4")
        with bypass_rls():
            self.assertEqual(AuditLog.objects.filter(resource_type=service.RESOURCE).count(), 1)

    def test_filled_instructor_is_kept(self):
        with bypass_rls():
            Lesson.objects.filter(pk=self.seminars[0].pk).update(instructor=self.dean)
        counts = _parse(self._run(self._evidence(), apply=True))
        self.assertEqual(counts["lesson_differs_kept"], "1")
        self.assertEqual(self._owners(self.seminars), [self.dean.pk, self.teacher_b.pk])

    def test_other_subject_at_the_same_slot_is_not_claimed(self):
        with bypass_rls():
            other = self._make_offering("CHEM1", self.group_a, "la_student_chem", 2024, self.period)
            stranger = self._lesson(LECTURE_SLOTS[0], LessonKind.LECTURE, offering=other)
        self._run(self._evidence(), apply=True)
        self.assertEqual(self._owners([stranger]), [None])
        self.assertEqual(self._owners(self.lectures), [self.teacher_a.pk] * 2)

    def test_lesson_after_cutoff_is_left_alone(self):
        with bypass_rls():
            late = self._lesson("2025-01-10 10:10", LessonKind.LECTURE)
        self._run(self._evidence([_journal(1, WORKER_A, ["2025-01-10 10:10"])]), apply=True)
        self.assertEqual(self._owners([late]), [None])

    def test_unknown_teacher_is_counted_and_skipped(self):
        counts = _parse(self._run(self._evidence([_journal(1, 99999, LECTURE_SLOTS)]), apply=True))
        self.assertEqual(counts["journal_teacher_unresolved"], "1")
        self.assertEqual(counts["slot_teacher_unresolved"], "2")
        self.assertEqual(self._owners(self.lectures), [None, None])

    def test_file_user_resolves_a_journal_without_ledger(self):
        journals = [_journal(1, 4242, LECTURE_SLOTS, user=self.teacher_a.pk)]  # 4242 ledger-də yoxdur
        counts = _parse(self._run(self._evidence(journals), apply=True))
        self.assertNotIn("journal_teacher_unresolved", counts)
        self.assertEqual(self._owners(self.lectures), [self.teacher_a.pk] * 2)

    def test_ledger_wins_over_file_user(self):
        journals = [_journal(1, WORKER_A, LECTURE_SLOTS, user=self.dean.pk)]
        self._run(self._evidence(journals), apply=True)
        self.assertEqual(self._owners(self.lectures), [self.teacher_a.pk] * 2)

    def test_inactive_file_user_is_unresolved(self):
        with bypass_rls():
            User.objects.filter(pk=self.dean.pk).update(is_active=False)
        journals = [_journal(1, 4242, LECTURE_SLOTS, user=self.dean.pk)]
        counts = _parse(self._run(self._evidence(journals), apply=True))
        self.assertEqual(counts["journal_teacher_unresolved"], "1")
        self.assertEqual(self._owners(self.lectures), [None, None])

    def test_inactive_ledger_teacher_is_unresolved(self):
        with bypass_rls():
            User.objects.filter(pk=self.teacher_b.pk).update(is_active=False)
        counts = _parse(self._run(self._evidence([_journal(2, WORKER_B, SEMINAR_SLOTS)]), apply=True))
        self.assertEqual(counts["journal_teacher_unresolved"], "1")
        self.assertEqual(self._owners(self.seminars), [None, None])

    def test_unresolved_period_stops(self):
        counts = _parse(self._run(self._evidence(period={"name": "Yaz", "academic_year": "2030/2031"}), apply=True))
        self.assertEqual(counts["period_unresolved"], "1")
        self.assertEqual(self._owners(self.lectures + self.seminars), [None] * 4)


class ConflictTest(_Base):
    def test_two_claims_one_holder_is_resolved(self):
        journals = [
            _journal(1, WORKER_A, LECTURE_SLOTS),
            _journal(3, WORKER_C, LECTURE_SLOTS[:1]),  # pay / sahib deyil
        ]
        counts = _parse(self._run(self._evidence(journals), apply=True))
        self.assertEqual(counts["lesson_conflict_resolved_by_holder"], "1")
        self.assertEqual(self._owners(self.lectures), [self.teacher_a.pk] * 2)

    def test_two_holders_claim_the_same_slot(self):
        journals = [
            _journal(1, WORKER_A, LECTURE_SLOTS),
            _journal(4, WORKER_B, LECTURE_SLOTS[1:]),  # B də pay müəllimidir
        ]
        counts = _parse(self._run(self._evidence(journals), apply=True))
        self.assertEqual(counts["lesson_conflict"], "1")
        self.assertEqual(self._owners(self.lectures), [self.teacher_a.pk, None])

    def test_two_strangers_claim_the_same_slot(self):
        with bypass_rls():
            extra = self._lesson("2024-10-15 09:00", LessonKind.LECTURE)
        journals = [_journal(5, WORKER_C, ["2024-10-15 09:00"]), _journal(6, WORKER_D, ["2024-10-15 09:00"])]
        counts = _parse(self._run(self._evidence(journals), apply=True))
        self.assertEqual(counts["lesson_conflict"], "1")
        self.assertEqual(self._owners([extra]), [None])

    def test_subgroup_journal_beats_the_parent_group_journal(self):
        """Ana qrupun jurnalı (X) alt qrupun dərsinə də iddia edir — alt qrupun öz jurnalı (Y) qalib gəlir."""
        with bypass_rls():
            subgroup = OrgUnit.objects.create(
                organization=self.org,
                name="GA (1)",
                slug=f"myedu-grp-{LEGACY_GROUP + 1}",
                unit_type=OrgUnitType.GROUP,
                parent=OrgUnit.objects.get(pk=self.group_a.pk),
            )
            sub_offering = CourseOffering.objects.create(
                organization=self.org,
                subject_id=self.offering_a.subject_id,
                period=self.period,
                group=subgroup,
                instructor=self.teacher_a,
            )
            sub_lesson = self._lesson(LECTURE_SLOTS[0], LessonKind.LECTURE, offering=sub_offering)
        sub_journal = _journal(7, WORKER_C, LECTURE_SLOTS[:1])
        sub_journal["groups"] = [{"id": LEGACY_GROUP + 1, "name": "GA (1)"}]
        counts = _parse(self._run(self._evidence([_journal(1, WORKER_A, LECTURE_SLOTS), sub_journal]), apply=True))
        self.assertEqual(counts["lesson_conflict_resolved_by_group"], "1")
        self.assertEqual(self._owners([sub_lesson]), [self.new_teacher.pk])
        self.assertEqual(self._owners(self.lectures), [self.teacher_a.pk] * 2)


class NewSystemLessonTest(_Base):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.typed = self._lesson("2024-11-01 13:30", LessonKind.LECTURE, created_by=self.teacher_a)

    def test_new_lesson_goes_to_current_owner(self):
        counts = _parse(self._run(self._evidence([]), apply=True))
        self.assertEqual(counts["lesson_new_planned"], "1")
        self.assertEqual(self._owners([self.typed]), [self.teacher_a.pk])
        self.assertEqual(self._owners(self.lectures), [None, None])  # sübutsuz köhnə dərs boş qalır

    def test_handover_after_the_lesson_leaves_it_untouched(self):
        with bypass_rls():
            TeachingHandover.objects.create(
                organization=self.org,
                offering=self.offering_a,
                from_instructor=self.new_teacher,
                to_instructor=self.teacher_a,
                reason="Sınaq",
            )
        counts = _parse(self._run(self._evidence([]), apply=True))
        self.assertEqual(counts["new_after_handover"], "1")
        self.assertEqual(self._owners([self.typed]), [None])

    def test_reverted_handover_does_not_block(self):
        with bypass_rls():
            TeachingHandover.objects.create(
                organization=self.org,
                offering=self.offering_a,
                from_instructor=self.new_teacher,
                to_instructor=self.teacher_a,
                reason="Sınaq",
                reverted_at=datetime.datetime.now(datetime.timezone.utc),
            )
        self._run(self._evidence([]), apply=True)
        self.assertEqual(self._owners([self.typed]), [self.teacher_a.pk])


class UndoTest(_Base):
    def test_undo_clears_only_lessons_still_on_the_stamped_teacher(self):
        path = self._evidence()
        self._run(path, apply=True)
        with bypass_rls():
            Lesson.objects.filter(pk=self.seminars[0].pk).update(instructor=self.dean)  # sonra əl ilə dəyişib
            kept = self._lesson("2024-10-20 10:10", LessonKind.LECTURE, instructor=self.teacher_a)
        dry = _parse(self._run(path, undo=True))
        self.assertEqual(dry["undo_lessons_cleared"], "3")
        self.assertEqual(self._owners(self.lectures), [self.teacher_a.pk] * 2)
        counts = _parse(self._run(path, apply=True, undo=True))
        self.assertEqual(counts["undo_lessons_cleared"], "3")
        self.assertEqual(counts["undo_offerings"], "1")
        self.assertEqual(self._owners(self.lectures), [None, None])
        self.assertEqual(self._owners(self.seminars), [self.dean.pk, None])
        self.assertEqual(self._owners([kept]), [self.teacher_a.pk])


class CommandContractTest(_Base):
    def test_output_is_only_count_lines(self):
        output = self._run(self._evidence(), apply=True)
        lines = [line for line in output.splitlines() if line.strip()]
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r"^twin_merge: ")
            self.assertRegex(line, r"^twin_merge:( [a-z_]+=[a-z0-9_]+)+$")

    def test_actor_must_be_active_superuser(self):
        for username in (self.rim.username, "nobody_here"):
            with self.subTest(username=username), self.assertRaises(CommandError) as error:
                self._run(self._evidence(), apply=True, actor=username)
            self.assertEqual(str(error.exception), "actor_must_be_active_superuser")
        with bypass_rls():
            User.objects.filter(pk=self.admin.pk).update(is_active=False)
        with self.assertRaises(CommandError) as error:
            self._run(self._evidence(), apply=True)
        self.assertEqual(str(error.exception), "actor_must_be_active_superuser")
        self.assertEqual(self._owners(self.lectures), [None, None])

    def test_unknown_org(self):
        with self.assertRaises(CommandError) as error, mock.patch.object(service, "ledger_map", return_value={}):
            call_command(
                "restore_lesson_authors_20261113",
                "--org",
                "no-such-org",
                "--actor",
                self.admin.username,
                stdout=StringIO(),
            )
        self.assertEqual(str(error.exception), "lesson_authors_organization_unknown")

    def test_failure_becomes_a_coded_command_error(self):
        path = self._evidence(format="something-else/9")
        with self.assertRaises(CommandError) as error:
            self._run(path, apply=True)
        self.assertEqual(str(error.exception), "lesson_authors_failed_valueerror_format_unknown")
        self.assertEqual(self._owners(self.lectures), [None, None])


class FailureCodeTest(SimpleTestCase):
    def test_slug_and_length(self):
        code = command.failure_code(ValueError("Bad «thing» 42"))
        self.assertRegex(code, r"^lesson_authors_failed_[a-z0-9_]+$")
        self.assertTrue(code.startswith("lesson_authors_failed_valueerror_bad_thing_42"))
        self.assertLessEqual(len(command.failure_code(ValueError("x" * 500))), 120)


class EvidenceFileTest(SimpleTestCase):
    """Repodakı real sübut faylı: format, Enzimologiya 234 BİO az nümunəsi, şəxsi məlumat yoxdur."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = service.load()

    def test_format_and_header(self):
        self.assertEqual(self.data["format"], service.FORMAT)
        self.assertEqual(set(self.data), {"format", "semester", "period", "cutoff", "journals"})
        self.assertEqual(set(self.data["period"]), {"name", "academic_year"})
        datetime.date.fromisoformat(self.data["cutoff"])

    def test_enzimologiya_journals(self):
        by_id = {entry["legacy_id"]: entry for entry in self.data["journals"]}
        for legacy_id, teacher in ((14340, 167), (15233, 933)):
            with self.subTest(journal=legacy_id):
                entry = by_id[legacy_id]
                self.assertEqual(entry["teacher"], teacher)
                self.assertIn({"id": 642, "name": "234 BİO az"}, entry["groups"])
                self.assertEqual(entry["subject"]["id"], by_id[14340]["subject"]["id"])
        self.assertEqual(len(by_id[15233]["slots"]), 5)

    def test_no_person_fields(self):
        slot = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        for entry in self.data["journals"]:
            self.assertEqual(set(entry), {"legacy_id", "teacher", "user", "subject", "groups", "slots"})
            self.assertIsInstance(entry["teacher"], int)
            self.assertTrue(entry["user"] is None or isinstance(entry["user"], int))
            self.assertEqual(set(entry["subject"]), {"id", "name"})
            for group in entry["groups"]:
                self.assertEqual(set(group), {"id", "name"})
            for text in entry["slots"]:
                self.assertRegex(text, slot)

    def test_unknown_format_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump({"format": "other/1"}, handle)
        self.addCleanup(lambda: __import__("os").unlink(handle.name))
        with self.assertRaises(ValueError):
            service.load(handle.name)

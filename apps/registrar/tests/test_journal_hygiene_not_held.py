"""«Jurnal təmizliyi» — KEÇİRİLMƏYƏN FƏNN (sahib 2026-10-11).

Kilidlənən qaydalar:

* bitmiş dövrdə ≥2 tələbəli açılışda HEÇ KİMİN imtahan («çıxış») balı yoxdursa — yalnız giriş balı və ya heç
  nə — açılış «keçirilməyib»: yeni sistem (``FinalGrade.exam_score``, təkrar imtahan, ``ExamScoreEntry``) və
  köhnə sistem (imtahan xanası, giriş/çıxış cəhdinin ÇIXIŞ balı, yekun cədvəli) eyni qaydaya tabedir;
* bir tələbənin imtahan balı (0 da), cari / gələcək dövr, tək tələbəli açılış → namizəd deyil;
* imtahan balı olmadan heç kim «keçdi» görünmür (kanonik qiymətləndirici ilə yoxlanır);
* güclü siqnal = qrupun digər fənlərinin ≥ yarısında imtahan var VƏ dərs / kollokvium izi yoxdur;
* tətbiq: bütöv açılış ``dropped`` + qərar jurnalı + audit, yarımçıq seçim rədd olunur, «Bərpa et» qaytarır;
  ``dropped`` sətir transkriptdən düşür; CLI açılış üzrə hesabat verir; sorğu sayı açılış sayından asılı deyil.
"""

from __future__ import annotations

import io
import json
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.registrar import analytics
from apps.registrar import journal_hygiene as hygiene
from apps.registrar import journal_hygiene_actions as actions
from apps.registrar import journal_hygiene_not_held as not_held
from apps.registrar import journal_hygiene_rows as rows_service
from apps.registrar import transcript
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    Enrollment,
    FinalGrade,
    JournalHygieneDecision,
    LegacyGradeEvidenceKind,
    LegacyGradeFact,
    LegacyGradeMappingStatus,
    ResitReason,
    ResitRecord,
    Subject,
)
from core.rls import bypass_rls

from .journal_hygiene_fixture import REASON, HygieneBase, User
from .test_journal_hygiene_detection import domain_queries

NOT_HELD_REASON = "Qrupda keçirilməyən fənn: heç kimin imtahan balı yoxdur (test qeydi)."
_HASH = "a" * 64


class NotHeldBase(HygieneBase):
    """Keçmiş dövrdə qrup JH-101: 3 «sessiya» fənni (imtahanlı) + keçirilməyən fənn (3 tələbə, yalnız giriş)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.students = [cls.make_student(f"jh_nh{index}") for index in range(3)]
            cls.session = []
            for index in range(3):
                subject = Subject.objects.create(organization=cls.org, code=f"JH-S{index}", name=f"Sessiya {index}")
                offering = cls._offering(subject, cls.past)
                rows = [cls.enroll(student, offering) for student in cls.students]
                FinalGrade.objects.create(organization=cls.org, enrollment=rows[0], exam_score=Decimal("31"))
                cls.session.append(offering)
            cls.ghost = cls._offering(cls.subject_c, cls.past)
            cls.ghost_rows = [cls.enroll(student, cls.ghost) for student in cls.students]
            for row in cls.ghost_rows:
                cls.entry(row, Decimal("10"))
                # Boş ``FinalGrade`` (imtahan balı yoxdur) imtahan sübutu DEYİL.
                FinalGrade.objects.create(organization=cls.org, enrollment=row)

    @classmethod
    def entry(cls, enrollment, score, *, kind=ComponentKind.GENERIC, name="Davamiyyət və sərbəst iş (arxiv)"):
        component, _ = AssessmentComponent.objects.get_or_create(
            organization=cls.org, offering=enrollment.offering, name=name, defaults={"kind": kind, "max_score": 20}
        )
        return ComponentScore.objects.create(
            organization=cls.org, component=component, enrollment=enrollment, score=score
        )

    @classmethod
    def fact(cls, enrollment, kind, *, source_pk, entry=None, exam=None, kesr=None, raw=""):
        return LegacyGradeFact.objects.create(
            organization=cls.org,
            enrollment=enrollment,
            source_system="myedudb",
            source_table="imthngrscxsblr" if kind == LegacyGradeEvidenceKind.EXAM_ENTRY_EXIT else "yekun",
            source_pk=source_pk,
            source_snapshot_sha256=_HASH,
            source_row_hash=_HASH,
            materialization_digest=_HASH,
            transform_version="legacy-grade-v1",
            evidence_kind=kind,
            mapping_status=LegacyGradeMappingStatus.LINKED,
            source_journal_ref="journal-nh",
            source_enrollment_ref=f"journal-nh:{source_pk}",
            entry_score_text="" if entry is None else str(entry),
            exam_score_text="" if exam is None else str(exam),
            raw_score_text=raw,
            entry_score=entry,
            exam_score=exam,
            legacy_kesr=kesr,
        )

    def scan_ids(self, **kwargs):
        with bypass_rls():
            return set(not_held.scan(self.org, **kwargs).offerings)

    def candidates(self, filters=None):
        with bypass_rls():
            return hygiene.candidates(self.org, hygiene.NOT_HELD, filters)


class NotHeldDetectionTest(NotHeldBase):
    def test_whole_group_without_exam_is_detected_as_strong(self):
        with bypass_rls():
            result = not_held.scan(self.org)
            self.assertEqual(set(result.offerings), {self.ghost.pk})
            info = result.offerings[self.ghost.pk]
            self.assertEqual((info["size"], info["siblings"], info["siblings_exam"]), (3, 3, 3))
            self.assertTrue(info["strong"])
            rows = rows_service.rows_for(self.candidates(), hygiene.NOT_HELD)
        self.assertEqual({row["id"] for row in rows}, {str(row.pk) for row in self.ghost_rows})
        row = rows[0]
        self.assertEqual(row["reason"], not_held.REASON_NOT_HELD)
        self.assertTrue(row["strong"])
        self.assertTrue(row["has_evidence"])
        self.assertEqual(row["group_size"], 3)
        self.assertEqual([tag["code"] for tag in row["tags"]], [not_held.TAG_ENTRY_ONLY])

    def test_nobody_passes_without_an_exam_score(self):
        with bypass_rls():
            rows = list(
                Enrollment.objects.filter(pk__in=[row.pk for row in self.ghost_rows]).select_related("offering")
            )
            maps = analytics.build_evaluation_maps(self.org, rows)
            results = [analytics.evaluate_enrollment(row, maps) for row in rows]
        self.assertFalse(any(result["passed"] for result in results))
        self.assertFalse(any(result["graded"] for result in results))

    def test_one_exam_score_means_the_subject_was_held(self):
        with bypass_rls():
            FinalGrade.objects.filter(enrollment=self.ghost_rows[1]).update(exam_score=Decimal("0"))
        self.assertEqual(self.scan_ids(), set())

    def test_resit_score_and_exam_entry_are_exam_evidence(self):
        with bypass_rls():
            ResitRecord.objects.create(
                organization=self.org, enrollment=self.ghost_rows[0], reason=ResitReason.TOTAL, resit_score=None
            )
        self.assertEqual(self.scan_ids(), {self.ghost.pk})  # boş təkrar-imtahan hüququ sübut deyil
        with bypass_rls():
            ResitRecord.objects.filter(enrollment=self.ghost_rows[0]).update(resit_score=Decimal("20"))
        self.assertEqual(self.scan_ids(), set())

    def test_exam_of_transfer_predecessor_counts(self):
        with bypass_rls():
            other = self._offering(self.subject_c, self.past, group=self.group2)
            old = self.enroll(self.make_student("jh_nh_moved"), other)
            FinalGrade.objects.create(organization=self.org, enrollment=old, exam_score=Decimal("40"))
            successor = self.enroll(old.student, self.ghost)
            Enrollment.objects.filter(pk=old.pk).update(status=Enrollment.Status.DROPPED, superseded_by=successor)
        self.assertEqual(self.scan_ids(), set())

    def test_current_and_future_periods_are_never_candidates(self):
        with bypass_rls():
            for period in (self.current, self.future):
                subject = Subject.objects.create(organization=self.org, code=f"JH-{period.name}", name=period.name)
                offering = self._offering(subject, period)
                for student in self.students:
                    self.entry(self.enroll(student, offering), Decimal("8"))
            ended_but_current = self._offering(self.subject_b, self.past, group=self.group2)
            for index in range(2):
                self.enroll(self.make_student(f"jh_nh_c{index}"), ended_but_current)
        self.assertEqual(self.scan_ids(), {self.ghost.pk, ended_but_current.pk})
        with bypass_rls():
            type(self.past).objects.filter(pk=self.past.pk).update(is_current=True)
        self.assertEqual(self.scan_ids(), set())  # «cari» işarəli dövr bitmiş sayılmır

    def test_single_student_offering_is_not_a_candidate(self):
        with bypass_rls():
            Enrollment.objects.filter(pk__in=[row.pk for row in self.ghost_rows[1:]]).update(
                status=Enrollment.Status.DROPPED
            )
        self.assertEqual(self.scan_ids(), set())

    def test_teaching_trace_or_missing_session_makes_it_review_only(self):
        with bypass_rls():
            self.entry(self.ghost_rows[0], Decimal("7"), kind=ComponentKind.KOLLOKVIUM, name="Kollokvium 1")
            result = not_held.scan(self.org)
        info = result.offerings[self.ghost.pk]
        self.assertTrue(info["taught"])
        self.assertFalse(info["strong"])
        with bypass_rls():
            ComponentScore.objects.filter(component__kind=ComponentKind.KOLLOKVIUM).delete()
            FinalGrade.objects.filter(enrollment__offering__in=self.session[:2]).update(exam_score=None)
            info = not_held.scan(self.org).offerings
        # İndi sessiya fənlərindən yalnız 1/3-ü imtahanlıdır → güclü deyil (2 sessiya fənni də namizəddir).
        self.assertFalse(info[self.ghost.pk]["strong"])
        self.assertEqual(set(info), {self.ghost.pk, self.session[0].pk, self.session[1].pk})

    def test_counts_and_filters(self):
        with bypass_rls():
            queryset = self.candidates()
            totals = hygiene.counts(queryset, hygiene.NOT_HELD)
            strong = self.candidates({"category": "strong"}).count()
            review = self.candidates({"category": "review"}).count()
            entry_only = self.candidates({"category": not_held.TAG_ENTRY_ONLY}).count()
        self.assertEqual((totals["total"], totals["offerings"], totals["offerings_strong"]), (3, 1, 1))
        self.assertEqual((strong, review, entry_only), (3, 0, 3))
        codes = [option["value"] for option in hygiene.category_options(hygiene.NOT_HELD)]
        self.assertIn(not_held.TAG_TAUGHT, codes)

    def test_query_count_is_flat(self):
        def run():
            with CaptureQueriesContext(connection) as ctx, bypass_rls():
                queryset = hygiene.candidates(self.org, hygiene.NOT_HELD)
                totals = hygiene.counts(queryset, hygiene.NOT_HELD)
                rows_service.page(queryset, hygiene.NOT_HELD, number=1, size=50, total=totals["total"])
            return domain_queries(ctx), totals["offerings"]

        small, offerings_small = run()
        with bypass_rls():
            for index in range(3):
                subject = Subject.objects.create(organization=self.org, code=f"JH-G{index}", name=f"Fantom {index}")
                offering = self._offering(subject, self.past)
                for student in self.students:
                    self.enroll(student, offering)
        large, offerings_large = run()
        self.assertEqual((offerings_small, offerings_large), (1, 4))
        self.assertEqual(len(small), len(large), large)


class LegacyNotHeldTest(NotHeldBase):
    """Köhnə sistem: yalnız giriş balı → keçirilməyib; imtahan / çıxış / yekun balı → keçirilib."""

    def test_entry_only_legacy_facts_do_not_count_as_exam(self):
        with bypass_rls():
            for index, row in enumerate(self.ghost_rows):
                self.fact(row, LegacyGradeEvidenceKind.OTHER, source_pk=100 + index, entry=Decimal("9"), raw="9")
                self.fact(row, LegacyGradeEvidenceKind.EXAM, source_pk=200 + index)  # boş imtahan xanası
        self.assertEqual(self.scan_ids(), {self.ghost.pk})

    def test_exit_score_of_entry_exit_attempt_is_exam_evidence(self):
        with bypass_rls():
            self.fact(
                self.ghost_rows[0],
                LegacyGradeEvidenceKind.EXAM_ENTRY_EXIT,
                source_pk=300,
                entry=Decimal("40"),
                exam=Decimal("18"),
            )
        self.assertEqual(self.scan_ids(), set())

    def test_marked_exam_cell_is_exam_evidence(self):
        with bypass_rls():
            self.fact(self.ghost_rows[0], LegacyGradeEvidenceKind.EXAM, source_pk=400, raw="l")
        self.assertEqual(self.scan_ids(), set())

    def test_passed_summary_is_exam_evidence_but_failed_entry_only_summary_is_not(self):
        with bypass_rls():
            self.fact(self.ghost_rows[1], LegacyGradeEvidenceKind.SUMMARY, source_pk=500, entry=Decimal("12"), kesr=1)
        self.assertEqual(self.scan_ids(), {self.ghost.pk})
        with bypass_rls():
            self.fact(self.ghost_rows[2], LegacyGradeEvidenceKind.SUMMARY, source_pk=401, entry=Decimal("45"), kesr=0)
        self.assertEqual(self.scan_ids(), set())


class NotHeldActionsTest(NotHeldBase):
    def _preview(self, ids):
        with bypass_rls():
            return actions.preview(
                organization=self.org,
                actor=self.owner,
                category=hygiene.NOT_HELD,
                enrollment_ids=[str(pk) for pk in ids],
                target=actions.TARGET_DROP,
            )

    def _apply(self, ids, digest):
        with bypass_rls():
            return actions.apply(
                organization=self.org,
                actor=self.owner,
                category=hygiene.NOT_HELD,
                enrollment_ids=[str(pk) for pk in ids],
                target=actions.TARGET_DROP,
                reason=NOT_HELD_REASON,
                expected_digest=digest,
            )

    def test_apply_drops_whole_offering_then_revert(self):
        ids = [row.pk for row in self.ghost_rows]
        data = self._preview(ids)
        self.assertTrue(data["can_apply"])
        self.assertEqual((data["rows"], data["journals"], data["partial_total"]), (3, 1, 0))
        result = self._apply(ids, data["digest"])
        self.assertEqual(result["changed"], 3)
        with bypass_rls():
            statuses = set(Enrollment.objects.filter(pk__in=ids).values_list("status", flat=True))
            decisions = list(JournalHygieneDecision.objects.filter(batch=result["batch"]))
            self.assertTrue(
                AuditLog.objects.filter(resource_type=actions.AUDIT_RESOURCE, resource_id=result["batch"]).exists()
            )
            self.assertEqual(self.scan_ids(), set())
            record = transcript.build_student_transcript(student=self.students[0], organization=self.org)
        self.assertEqual(statuses, {Enrollment.Status.DROPPED})
        self.assertEqual({item.category for item in decisions}, {hygiene.NOT_HELD})
        self.assertEqual({item.reason_code for item in decisions}, {not_held.REASON_NOT_HELD})
        subjects = {row["subject"].pk for sem in record["semesters"] for row in sem["rows"]}
        self.assertNotIn(self.subject_c.pk, subjects)  # transkriptdən düşüb
        self.assertEqual(len(subjects), 3)

        with bypass_rls():
            reverted = actions.revert(
                organization=self.org,
                actor=self.owner,
                decision_ids=[str(item.pk) for item in decisions],
                reason=REASON,
            )
        self.assertEqual(reverted["reverted"], 3)
        self.assertEqual(self.status_of(self.ghost_rows[0]), Enrollment.Status.ENROLLED)
        self.assertEqual(self.scan_ids(), {self.ghost.pk})

    def test_partial_selection_is_rejected(self):
        ids = [row.pk for row in self.ghost_rows[:2]]
        data = self._preview(ids)
        self.assertEqual(data["partial_total"], 1)
        self.assertFalse(data["can_apply"])
        with self.assertRaises(actions.HygieneError) as ctx:
            self._apply(ids, data["digest"])
        self.assertEqual(ctx.exception.code, "partial_offering")
        self.assertEqual(self.status_of(self.ghost_rows[0]), Enrollment.Status.ENROLLED)

    def test_exam_written_after_preview_is_drift(self):
        ids = [row.pk for row in self.ghost_rows]
        data = self._preview(ids)
        with bypass_rls():
            FinalGrade.objects.filter(enrollment=self.ghost_rows[2]).update(exam_score=Decimal("12"))
        with self.assertRaises(actions.HygieneError) as ctx:
            self._apply(ids, data["digest"])
        self.assertEqual(ctx.exception.code, "drift")
        self.assertFalse(JournalHygieneDecision.objects.exists())

    def test_whole_offering_ids_never_cuts_an_offering(self):
        pairs = [(1, "a"), (2, "a"), (3, "b"), (4, "b"), (5, "b")]
        self.assertEqual(not_held.whole_offering_ids(pairs, 4), ["1", "2"])
        self.assertEqual(not_held.whole_offering_ids(pairs, 5), ["1", "2", "3", "4", "5"])


class NotHeldCommandTest(NotHeldBase):
    def _call(self, *args):
        out = io.StringIO()
        call_command(
            "journal_hygiene_report", "--organization", self.org.slug, "--category", "not_held", *args, stdout=out
        )
        return out.getvalue()

    def test_dry_run_reports_per_offering(self):
        output = self._call()
        self.assertIn("KEÇİRİLMƏYƏN FƏNLƏR", output)
        self.assertIn(str(self.ghost.pk), output)
        self.assertIn("3 tələbə", output)
        self.assertIn("GÜCLÜ", output)
        self.assertIn("DRY-RUN", output)
        self.assertEqual(self.status_of(self.ghost_rows[0]), Enrollment.Status.ENROLLED)

    def test_apply_with_guard_flag(self):
        output = self._call("--code", "strong", "--apply", "--reason", NOT_HELD_REASON, "--i-know-this-is-production")
        self.assertIn("YAZILDI: 3", output)
        self.assertEqual(self.status_of(self.ghost_rows[1]), Enrollment.Status.DROPPED)
        with bypass_rls():
            self.assertEqual(JournalHygieneDecision.objects.filter(category=hygiene.NOT_HELD).count(), 3)


@override_settings(UNIVERSITY_MODE=True)
class NotHeldHttpTest(NotHeldBase):
    """Kabinet bölməsi: ``tab=not_held`` siyahısı, açılış sayları, «hamısını seç» və HTTP üzərindən tətbiq."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.superadmin = User.objects.create_superuser("jh_nh_su", "jh_nh_su@qku.edu.az", "pw")

    def _client(self):
        client = Client()
        client.force_login(self.superadmin)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_tab_counts_select_all_and_apply(self):
        client = self._client()
        url = reverse("accounts:journal_hygiene_rows")
        data = client.get(url, {"tab": "not_held"}).json()
        self.assertEqual((data["counts"]["total"], data["counts"]["offerings"]), (3, 1))
        self.assertEqual(data["results"][0]["group_size"], 3)
        ids = client.get(url, {"tab": "not_held", "select": "all"}).json()["ids"]
        self.assertEqual(set(ids), {str(row.pk) for row in self.ghost_rows})
        action = reverse("accounts:journal_hygiene_action")

        def post(payload):
            return client.post(action, data=json.dumps(payload), content_type="application/json")

        preview = post({"action": "preview", "tab": "not_held", "ids": ids, "target": "drop"}).json()
        self.assertTrue(preview["can_apply"])
        applied = post(
            {
                "action": "apply",
                "tab": "not_held",
                "ids": ids,
                "target": "drop",
                "reason": NOT_HELD_REASON,
                "digest": preview["digest"],
            }
        )
        self.assertEqual(applied.status_code, 200, applied.content)
        self.assertEqual(self.status_of(self.ghost_rows[0]), Enrollment.Status.DROPPED)
        history = client.get(url, {"tab": "history", "category": "not_held"}).json()
        self.assertEqual(history["total"], 3)

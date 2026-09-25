"""Giriş balı pariteti — BÜTÜN güzgülərin rəqəmlərini bir lüğətə yığan köməkçi (sorğu da sayır).

``test_entry_standard_parity`` bu lüğəti keçiddən ƏVVƏL (köhnə kod) çəkilmiş snapshot ilə və öz
aralarında müqayisə edir; eyni test köməkçinin sorğu saylarını da (``queries``) büdcə ilə yoxlayır.
Yalnız keçiddən əvvəl də mövcud olan API-lər çağırılır.
"""

from __future__ import annotations

from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from apps.registrar.models import Enrollment
from apps.registrar.tests.entry_standard_fixture import OFFERINGS, STUDENTS
from core.rls import bypass_rls


def _s(value):
    return None if value is None else str(value)


def _final(result) -> tuple:
    return (
        _s(result["entry_score"]),
        _s(result["total"]),
        bool(result["passed"]),
        bool(result["failed"]),
        bool(result["barred"]),
    )


def _count(func):
    with CaptureQueriesContext(connection) as ctx:
        value = func()
    return value, len(ctx.captured_queries)


class MirrorProbe:
    """``fx`` — :class:`EntryStandardFixture` test nümunəsi."""

    def __init__(self, fx):
        self.fx = fx
        self.numbers: dict = {}
        self.queries: dict = {}

    # ── köməkçilər ────────────────────────────────────────────────────────
    def _fresh_enrollments(self, key=None):
        qs = Enrollment.objects.filter(organization=self.fx.org).select_related("student")
        if key is not None:
            qs = qs.filter(offering=self.fx.offerings[key])
        return list(qs.order_by("offering__subject__code", "student__username"))

    def _put(self, name, key, value):
        self.numbers.setdefault(name, {})[key] = value

    def _request(self, user, **params):
        request = RequestFactory().get("/", params)
        request.user = user
        return request

    # ── güzgülər ──────────────────────────────────────────────────────────
    def collect(self) -> dict:
        with bypass_rls():
            self._gradebook_single()
            self._entry_batch()
            self._finals()
            self._offering_surfaces()
            self._student_surfaces()
            self._analytics()
            self._transcripts()
        return self.numbers

    def _gradebook_single(self):
        from apps.registrar import gradebook

        for enrollment in self._fresh_enrollments():
            scheme = gradebook.ensure_assessment_scheme(offering=enrollment.offering)
            self._put(
                "entry_single",
                self.fx.row_key(enrollment),
                _s(gradebook.entry_score_for(enrollment, scheme.entry_score_max)),
            )

    def _entry_batch(self):
        from apps.registrar import finals_batch, gradebook

        for key in OFFERINGS:
            enrollments = self._fresh_enrollments(key)
            batch = finals_batch.entry_batch(enrollments)
            for enrollment in enrollments:
                cap = gradebook.ensure_assessment_scheme(offering=enrollment.offering).entry_score_max
                value = gradebook.entry_score_for(enrollment, cap, **batch.entry_kwargs(enrollment))
                self._put("entry_batch", self.fx.row_key(enrollment), _s(value))

    def _finals(self):
        from apps.registrar import finals, finals_batch

        for enrollment in self._fresh_enrollments():
            self._put(
                "final_single", self.fx.row_key(enrollment), _final(finals.compute_final_result(enrollment=enrollment))
            )
        enrollments = self._fresh_enrollments()
        batch = finals_batch.build(enrollments)
        for enrollment in enrollments:
            result = finals.compute_final_result(enrollment=enrollment, batch=batch)
            self._put("final_batch", self.fx.row_key(enrollment), _final(result))

    def _offering_surfaces(self):
        from apps.registrar import finals, gradebook, journal_extras

        for key in OFFERINGS:
            rows, count = _count(
                lambda key=key: finals.get_offering_results(offering=self.fx.fresh_offering(key))["rows"]
            )
            self.queries[f"offering_results/{key}"] = count
            for row in rows:
                self._put("offering_results", self.fx.row_key(row["enrollment"]), _final(row["result"]))
            breakdown, count = _count(lambda key=key: journal_extras.get_final_breakdown(self.fx.fresh_offering(key)))
            self.queries[f"final_breakdown/{key}"] = count
            for row in breakdown["rows"]:
                self._put("final_breakdown", self.fx.row_key(row["enrollment"]), _s(row["entry"]))
            grid, count = _count(lambda key=key: gradebook.get_offering_journal(offering=self.fx.fresh_offering(key)))
            self.queries[f"journal_grid/{key}"] = count
            for row in grid["rows"]:
                self._put("journal_grid", self.fx.row_key(row["enrollment"]), _s(row["entry_score"]))

    def _student_surfaces(self):
        from apps.registrar import dashboard_data, exam_bridge, gradebook, page_contexts, public
        from apps.registrar.models import StudentAcademicRecord

        for username in STUDENTS:
            student = self.fx.records[username].student
            for period_key, period in self.fx.periods.items():
                record = StudentAcademicRecord.objects.get(pk=self.fx.records[username].pk)
                summary, count = _count(
                    lambda record=record, period=period: gradebook.get_student_journal_summary(
                        record=record, period=period, semester_number=1
                    )
                )
                self.queries[f"student_journal_summary/{period_key}/{username}"] = count
                for row in summary["subjects"]:
                    self._put(
                        "student_journal_summary", self.fx.row_key(row["enrollment"]), _s(row["journal"]["entry_score"])
                    )
                record = StudentAcademicRecord.objects.get(pk=self.fx.records[username].pk)
                dash, count = _count(
                    lambda record=record, period=period: dashboard_data.student_subjects(
                        organization=self.fx.org, record=record, period=period
                    )
                )
                self.queries[f"dashboard/{period_key}/{username}"] = count
                by_id = {e.id: e for e in self._fresh_enrollments()}
                for row in dash["rows"]:
                    self._put("dashboard", self.fx.row_key(by_id[row["enrollment_id"]]), _s(row["entry_score"]))
                record = StudentAcademicRecord.objects.get(pk=self.fx.records[username].pk)
                stats, count = _count(
                    lambda student=student, record=record, period=period: page_contexts._student_offering_stats(
                        student, self.fx.org, record, period
                    )
                )
                self.queries[f"schedule_stats/{period_key}/{username}"] = count
                for key, (_code, pkey) in OFFERINGS.items():
                    if pkey == period_key:
                        enrollment = self.fx.enrollments[key][username]
                        self._put(
                            "schedule_stats", f"{key}/{username}", _s(stats[enrollment.offering_id]["entry_score"])
                        )
            # «Fənlərim» (cari dövr = NEW)
            ctx, count = _count(
                lambda student=student: public.build_student_subjects_context(
                    self._request(student), organization=self.fx.org
                )
            )
            self.queries[f"student_subjects/{username}"] = count
            for row in ctx["student_subjects_section"]["subjects"]:
                journal = row.get("journal") or {}
                self._put(
                    "student_subjects_journal", self.fx.row_key(row["enrollment"]), _s(journal.get("entry_score"))
                )
                self._put("student_subjects_final", self.fx.row_key(row["enrollment"]), _final(row["final"]))
            # Tələbə jurnal detalı (hər açılış üçün)
            for key, (_code, period_key) in OFFERINGS.items():
                enrollment = self.fx.enrollments[key][username]
                request = self._request(student, subject=str(enrollment.id), period=str(self.fx.periods[period_key].id))
                ctx, count = _count(
                    lambda request=request: public.build_student_journal_context(request, organization=self.fx.org)
                )
                self.queries[f"student_journal_detail/{key}/{username}"] = count
                detail = ctx["journal_student_section"]["detail"]
                self._put("student_journal_detail", f"{key}/{username}", _s(detail["entry_score"]))
                summary = exam_bridge.exam_result_summary(
                    student=student, subject_id=enrollment.offering.subject_id, organization=self.fx.org
                )
                self._put(
                    "exam_result_summary", f"{key}/{username}", (_s(summary["entry_score"]), _s(summary["total"]))
                )

    def _analytics(self):
        from apps.accounts import academic_summary
        from apps.accounts.academic_records import _new_acc
        from apps.registrar import analytics

        enrollments = list(
            Enrollment.objects.filter(organization=self.fx.org).select_related(
                "offering", "offering__subject", "offering__period"
            )
        )
        maps, count = _count(lambda: analytics.build_evaluation_maps(self.fx.org, enrollments))
        self.queries["evaluation_maps"] = count
        for enrollment in enrollments:
            result = analytics.evaluate_enrollment(enrollment, maps)
            self._put(
                "analytics_eval",
                self.fx.row_key(enrollment),
                (_s(result["total"]), bool(result["passed"]), bool(result["failed"]), bool(result["barred"])),
            )
        # akademik-qeyd icmalının «id-kolleksiyalı» yolu (``academic_records._evaluate_all`` forması)
        from apps.registrar.models import CourseOffering

        flat = Enrollment.objects.filter(organization=self.fx.org).order_by()
        offerings = {
            o.id: o
            for o in CourseOffering.objects.filter(id__in=flat.values("offering_id"))
            .select_related("subject")
            .only("id", "lesson_hours", "subject__ects")
        }
        light = list(flat.only("id", "student_id", "offering_id", "absence_hours"))
        for enrollment in light:
            enrollment.offering = offerings[enrollment.offering_id]
        maps, count = _count(
            lambda: analytics.build_evaluation_maps_for(
                self.fx.org,
                enrollment_ids=flat.values("id"),
                offering_ids=flat.values("offering_id"),
                student_ids=flat.values("student_id"),
            )
        )
        self.queries["evaluation_maps_for"] = count
        for enrollment in light:
            result = analytics.evaluate_enrollment(enrollment, maps)
            self._put("analytics_eval_for", self.fx.row_key(enrollment), (_s(result["total"]), bool(result["passed"])))
        for period_key, period in self.fx.periods.items():
            data, count = _count(
                lambda period=period: analytics.build_period_analytics(organization=self.fx.org, period=period)
            )
            self.queries[f"period_analytics/{period_key}"] = count
            totals = data["totals"]
            self._put(
                "period_analytics",
                period_key,
                tuple(_s(totals[k]) for k in ("graded", "passed", "failed", "barred", "avg_total", "avg_gpa")),
            )
            qs = Enrollment.objects.filter(organization=self.fx.org, offering__period=period)
            acc = _new_acc()
            _value, count = _count(lambda qs=qs, acc=acc: academic_summary.accumulate_summary(self.fx.org, qs, acc))
            self.queries[f"academic_summary/{period_key}"] = count
            self._put("academic_summary", period_key, tuple(_s(acc[k]) for k in sorted(acc)))

    def _transcripts(self):
        from apps.registrar import transcript

        for username in STUDENTS:
            student = self.fx.records[username].student
            data, count = _count(
                lambda student=student: transcript.build_student_transcript(student=student, organization=self.fx.org)
            )
            self.queries[f"transcript/{username}"] = count
            for semester in data["semesters"]:
                for row in semester["rows"]:
                    self._put("transcript", self.fx.row_key(row["enrollment"]), _final(row["result"]))
            self._put("transcript_gpa", username, (_s(data["cumulative_gpa"]), _s(data["quality_points"])))
            credits, count = _count(
                lambda student=student: transcript.student_credit_totals(student=student, organization=self.fx.org)
            )
            self.queries[f"credit_totals/{username}"] = count
            self._put("credit_totals", username, (credits["earned"], credits["in_progress"]))

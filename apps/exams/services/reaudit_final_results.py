"""Fixed-tenant, bounded READ ONLY audit of native effective scores and journal targets."""

import logging
import time
from collections import Counter

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from core.rls import apply_rls_request_context

from .. import score_adjustments
from ..models import Exam, ExamAttempt
from . import journal_sync
from .journal_sync_scope import target_identity
from .manual_grading import grading_complete

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
MAX_ROWS = 1000000
MAX_ATTEMPTS = 20000
MAX_SECONDS = 420
MAX_QUERIES = 150000
MAX_CASES = 500


class AuditLimit(ValueError):
    pass


class Budget:
    def __init__(self):
        self.started = time.monotonic()
        self.queries = 0

    def check(self):
        if time.monotonic() - self.started > MAX_SECONDS or self.queries >= MAX_QUERIES:
            raise AuditLimit("final_audit_execution_budget")

    def __call__(self, execute, sql, params, many, context):
        self.check()
        self.queries += 1
        return execute(sql, params, many, context)


class QuietNativeLogs(logging.Filter):
    def filter(self, record):
        # Resolver warnings contain student identifiers. Audit emits only safe classes.
        return False


def _model(label):
    return apps.get_model(label)


def validate_actor(username):
    apply_rls_request_context(user_id=None, org_id=ORG, bypass=False, local=True)
    if not _model("organizations.Organization").objects.filter(pk=ORG, is_active=True, status="active").exists():
        raise ValueError("final_audit_fixed_organization")
    actor = (
        get_user_model()
        .objects.filter(
            Q(profile__organization_id=ORG)
            | Q(memberships__organization_id=ORG, memberships__is_active=True)
            | Q(owned_organizations__id=ORG),
            username=username,
            is_active=True,
            is_superuser=True,
        )
        .values_list("pk", flat=True)
        .first()
    )
    if actor is None:
        raise ValueError("final_audit_active_tenant_superuser")
    apply_rls_request_context(user_id=actor, org_id=ORG, bypass=False, local=True)
    if (
        not _model("organizations.AcademicPeriod")
        .objects.filter(pk=PERIOD, organization_id=ORG, is_current=True)
        .exists()
    ):
        raise ValueError("final_audit_current_period_changed")


def _attempts():
    # Include history in competition: an old explicitly-linked attempt and a new
    # current fallback are different cells. Filter resolved targets, never dates.
    return ExamAttempt.objects.filter(
        exam__organization_id=ORG,
        exam__is_deleted=False,
        exam__exam_type_extended__in=("final", "midterm"),
        is_trial=False,
        status__in=("submitted", "expired"),
    )


def preflight():
    # Count before native helpers can materialize related lists. Broad tenant
    # scopes intentionally include the historical fallback resolver's inputs.
    scopes = {
        "enrollments": ("registrar.Enrollment", {"organization_id": ORG}),
        "offerings": ("registrar.CourseOffering", {"organization_id": ORG}),
        "answers": ("exams.ExamAnswer", {"attempt__exam__organization_id": ORG}),
        "answered_options": ("exams.ExamQuestionOption", {"question__answers__attempt__exam__organization_id": ORG}),
        "appealed_options": ("exams.ExamQuestionOption", {"question__appeal_items__appeal__organization_id": ORG}),
        "appeal_items": ("appeals.AppealItem", {"appeal__organization_id": ORG}),
        "adjustments": ("appeals.ScoreAdjustment", {"attempt__exam__organization_id": ORG}),
        "key_credits": ("appeals.KeyCorrectionCredit", {"correction__organization_id": ORG}),
        "score_entries": ("registrar.ExamScoreEntry", {"organization_id": ORG}),
        "component_corrections": ("registrar.ComponentScoreCorrection", {"organization_id": ORG}),
        "retake_grants": ("registrar.ExamChanceGrant", {"organization_id": ORG}),
        "questions": ("exams.ExamQuestion", {"exam__organization_id": ORG}),
        "journal_links": ("exams.Exam_journal_offerings", {"exam__organization_id": ORG}),
        "appeals": ("appeals.Appeal", {"organization_id": ORG}),
        "final_rows": ("registrar.FinalGrade", {"organization_id": ORG}),
        "resit_rows": ("registrar.ResitRecord", {"organization_id": ORG}),
    }
    counts = {"finished_attempts": _attempts().count()}
    if counts["finished_attempts"] > MAX_ATTEMPTS:
        raise AuditLimit("final_audit_attempt_budget")
    for name, (label, filters) in scopes.items():
        counts[name] = _model(label).objects.filter(**filters).values("pk").distinct().count()
        if sum(counts.values()) > MAX_ROWS:
            raise AuditLimit("final_audit_row_budget")
    return counts


def attempt_percent(attempt):
    if attempt.supervision_status == "removed":
        return 0, {"expelled": True}
    if attempt.exam.exam_type == "test":
        effective = score_adjustments.effective_test_score(attempt)
        visible = score_adjustments.student_visible_effective_test_score(attempt)
        if effective is None or visible is None:
            return None, {"status": "unknown_effective_score_hook"}
        return effective["effective_percentage"], {
            "appeal_or_key_bonus_present": effective["bonus_points"] > 0,
            "student_visibility_pending": effective["effective_percentage"] != visible["effective_percentage"],
            "native_legacy_count_fallback": bool(effective["base"].used_legacy_fallback),
        }
    if attempt.exam.exam_type_extended == "midterm" and not grading_complete(attempt):
        return None, {"status": "grading_pending"}
    percent = journal_sync._attempt_percent(attempt)
    if percent is journal_sync.PERCENT_PENDING:
        return None, {"status": "grading_pending"}
    return percent, {} if percent is not None else {"status": "unknown_percent"}


def inspect_attempt(attempt, identity):
    from apps.registrar.public import inspect_reaudit_exam_target

    if identity is None:
        return {"status": "unknown_no_writable_target"}
    percent, score_flags = attempt_percent(attempt)
    if percent is None:
        enrollment = _model("registrar.Enrollment").objects.get(pk=identity[1], organization_id=ORG)
        return {
            "enrollment_id": str(enrollment.pk),
            "offering_id": str(enrollment.offering_id),
            "target_kind": identity[0],
            **score_flags,
        }
    return {
        **inspect_reaudit_exam_target(attempt=attempt, identity=identity, percent=percent, period_id=PERIOD),
        **score_flags,
    }


def collect():
    counts, cases = Counter(), []
    scope_counts = preflight()
    seen, current_compared, current_official = set(), set(), set()
    counts["attempts_total"] = scope_counts["finished_attempts"]

    def record(kind, row):
        counts[kind] += 1
        counts["cases_total"] += 1
        if len(cases) < MAX_CASES:
            cases.append({"case": kind, **row})

    links = Exam.journal_offerings.through.objects.filter(exam__organization_id=ORG)
    for link in links.select_related("exam", "courseoffering").order_by("pk").iterator(chunk_size=100):
        if str(link.courseoffering.period_id) != PERIOD:
            continue
        counts["current_journal_links"] += 1
        if link.exam.subject_id != link.courseoffering.subject_id or str(link.courseoffering.organization_id) != ORG:
            record(
                "mismatched_subject_or_tenant_link",
                {"exam_id": link.exam_id, "offering_id": str(link.courseoffering_id)},
            )
    attempts = _attempts().select_related("exam__organization", "user").prefetch_related("exam__journal_offerings")
    for attempt in attempts.order_by("-started_at", "-pk").iterator(chunk_size=50):
        counts["attempts_processed"] += 1
        row = {"attempt_id": attempt.pk, "exam_id": attempt.exam_id, "category": attempt.exam.exam_type_extended}
        if attempt.exam.subject_id is None:
            record("unlinked_subject", row)
            continue
        identity = target_identity(attempt)
        if (
            identity is not None
            and not _model("registrar.Enrollment")
            .objects.filter(pk=identity[1], organization_id=ORG, offering__period_id=PERIOD)
            .exists()
        ):
            counts["outside_current_period"] += 1
            continue
        key = (attempt.exam.exam_type_extended, identity)
        accepted = (
            _model("appeals.Appeal")
            .objects.filter(organization_id=ORG, attempt_id=attempt.pk, status__in=("accepted", "partially_accepted"))
            .order_by("pk")
        )
        accepted_count = accepted.count()
        if accepted_count:
            row["accepted_appeal_count"] = accepted_count
            row["accepted_appeal_ids"] = list(accepted.values_list("pk", flat=True)[:20])
            row["accepted_appeal_ids_truncated"] = accepted_count > 20
        if identity is not None and key in seen:
            counts["superseded_same_cell"] += 1
            if accepted_count:
                record("accepted_appeal_superseded_attempt", row)
            continue
        if identity is not None:
            seen.add(key)
        with transaction.atomic():
            result = inspect_attempt(attempt, identity)
        status = result["status"]
        if accepted_count:
            record("accepted_appeal_official_attempt", {**row, **result})
        counts[status] += 1
        if result.get("enrollment_id") and status != "outside_current_period":
            current_official.add((row["category"], result["target_kind"], result["enrollment_id"]))
        if status == "compared":
            current_compared.add((row["category"], result["target_kind"], result["enrollment_id"]))
            counts["compared_" + row["category"]] += 1
            counts["comparison_" + result["comparison"]] += 1
            for flag in (
                "stored_zero",
                "expected_zero",
                "stored_out_of_bounds",
                "appeal_or_key_bonus_present",
                "student_visibility_pending",
                "native_legacy_count_fallback",
            ):
                counts[flag] += bool(result.get(flag))
            if result["comparison"] != "equal" or result.get("stored_out_of_bounds"):
                record("journal_score_review", {**row, **result})
            if result.get("source_attempt_matches") is False:
                record("midterm_source_attempt_differs", {**row, **result})
        elif status != "outside_current_period":
            record("attempt_" + status, {**row, **result})
    current_filter = {"organization_id": ORG, "enrollment__offering__period_id": PERIOD}
    for label, field in (("registrar.FinalGrade", "exam_score"), ("registrar.ResitRecord", "resit_score")):
        query = _model(label).objects.filter(**current_filter)
        name = "current_final" if field == "exam_score" else "current_resit"
        counts[name + "_rows"] = query.count()
        counts[name + "_nonempty"] = query.filter(**{field + "__isnull": False}).count()
        counts[name + "_zero"] = query.filter(**{field: 0}).count()
        fields = ["pk", "enrollment_id"] + (["status"] if name == "current_resit" else [])
        for stored in (
            query.filter(**{field + "__isnull": False}).values(*fields).order_by("pk").iterator(chunk_size=100)
        ):
            eid = str(stored["enrollment_id"])
            safe = {"row_id": str(stored["pk"]), "enrollment_id": eid}
            if name == "current_resit" and stored["status"] != "completed":
                record("noncompleted_resit_stored_score_ignored_by_display", safe)
            stored_key = ("final", "enrollment" if name == "current_final" else "retake", eid)
            if stored_key not in current_official:
                record(name + "_without_selected_online_attempt", safe)
            elif stored_key not in current_compared:
                counts[name + "_not_numerically_compared"] += 1
    counts["accepted_appeals_current_exam_scope"] = (
        _model("appeals.Appeal")
        .objects.filter(
            organization_id=ORG,
            status__in=("accepted", "partially_accepted"),
            exam__journal_offerings__period_id=PERIOD,
        )
        .distinct()
        .count()
    )
    case_total = counts["cases_total"]
    return {
        "format": "reaudit-final-results/1",
        "complete": True,
        "read_only": True,
        "all_academic_results_verified": False,
        "coverage": "Completed nontrial final/midterm attempts: latest native target per category in fixed current period; stored current final/resit inventory. No academic-source authority determination.",
        "organization_id": ORG,
        "period_id": PERIOD,
        "captured_at": timezone.now().isoformat(),
        "scope_counts": scope_counts,
        "counts": dict(counts),
        "cases": cases,
        "cases_total": case_total,
        "cases_returned": len(cases),
        "cases_truncated": case_total > len(cases),
        "unknowns": [
            "Historical final results outside the fixed current period are not assessed.",
            "Paper/legacy-only final rows without a selected online attempt require source review.",
            "No grade changes are authorized by this report; mismatches are review candidates.",
            "Question 3600 answer-key authority and future correctness are a separate reviewed correction.",
        ],
    }


def audit(username):
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise ValueError("final_audit_fresh_postgresql_transaction")
    budget = Budget()
    quiet = QuietNativeLogs()
    loggers = [logging.getLogger(name) for name in ("apps.registrar.exam_bridge", "apps.exams.services.journal_sync")]
    for logger in loggers:
        logger.addFilter(quiet)
    try:
        # Fresh outer transaction is required before SET TRANSACTION. The
        # worker wrapper would add a savepoint with transaction pooling enabled.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '15s'")
                cursor.execute("SET LOCAL lock_timeout = '3s'")
            with connection.execute_wrapper(budget):
                validate_actor(username)
                result = collect()
                with connection.cursor() as cursor:
                    cursor.execute("SHOW transaction_read_only")
                    readonly = cursor.fetchone()[0]
                    cursor.execute("SHOW transaction_isolation")
                    isolation = cursor.fetchone()[0]
                if readonly != "on" or isolation != "repeatable read":
                    raise ValueError("final_audit_readonly_lost")
                result["transaction"] = {"read_only": readonly, "isolation": isolation}
                result["query_count"] = budget.queries
                budget.check()
                return result
    finally:
        for logger in loggers:
            logger.removeFilter(quiet)

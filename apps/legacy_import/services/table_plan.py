"""Deployable, immutable registry for the reviewed legacy source table plan."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

TABLE_PLAN_VERSION = "legacy-table-plan-v1"
SOURCE_SNAPSHOT_SHA256 = "177ef2269027395fd3a80fc1dd592aab565dda7cbca5f6f08785313881d68fe0"
EXPECTED_TABLE_COUNT = 81
EXPECTED_ROW_COUNT = 9_044_531
_EXPECTED_PLAN_FINGERPRINT = "3868ca938f1134e9ee666ab066f6ac03e673414984780c016f20b587ec05e0d1"
_SAFE_TABLE_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class LegacyTablePlanError(Exception):
    """Sanitized fixed-plan validation failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LegacyTableAction(str, Enum):
    """A closed action vocabulary; gated actions never authorize a write."""

    TRANSFORM_CANDIDATE = "transform_candidate"
    REVIEW_GATED = "review_gated"
    DESIGN_GATED = "design_gated"
    ARCHIVE_GATED = "archive_gated"
    SECURITY_GATED = "security_gated"
    UNKNOWN_GATED = "unknown_gated"
    EMPTY_GATED = "empty_gated"
    VALIDATE_ONLY = "validate_only"

    @property
    def is_fail_closed(self) -> bool:
        return True

    @property
    def authorizes_target_write(self) -> bool:
        """A source plan is evidence only; separate reviewed bindings authorize writes."""

        return False


@dataclass(frozen=True)
class LegacyTablePlanEntry:
    source_table: str
    expected_rows: int
    compatibility_pct: int
    status: str
    action: LegacyTableAction
    domain_key: str
    dependency_phase: int
    adapter_key: str | None

    @property
    def authorizes_target_write(self) -> bool:
        return False


@dataclass(frozen=True)
class LegacyTablePlan:
    version: str
    fingerprint: str
    source_snapshot_sha256: str
    expected_row_count: int
    entries: tuple[LegacyTablePlanEntry, ...]

    def entry_for(self, source_table: str) -> LegacyTablePlanEntry:
        if type(source_table) is not str or not _SAFE_TABLE_NAME.fullmatch(source_table):
            raise LegacyTablePlanError("legacy_table_plan_table_invalid")
        for entry in self.entries:
            if entry.source_table == source_table:
                return entry
        raise LegacyTablePlanError("legacy_table_plan_table_unregistered")


_PLAN_ROWS = (
    ("alerts_workers", 629, 50, "migrate-partial", "review_gated", "communications"),
    ("allowed_qb", 2964, 70, "migrate-partial+archive", "review_gated", "grading"),
    ("balvereqi_logs", 52386, 50, "migrate-partial+archive", "review_gated", "grading"),
    ("books", 0, 0, "empty-skip", "empty_gated", "library"),
    ("books_order", 0, 0, "empty-skip", "empty_gated", "library"),
    ("curricula", 126, 70, "migrate-partial", "review_gated", "academic_structure"),
    ("curricula_plan", 3424, 60, "migrate-partial+archive", "review_gated", "academic_structure"),
    ("curricula_plan_patok", 1, 40, "sparse-migrate-partial", "review_gated", "academic_structure"),
    ("curricula_tam", 170, 30, "archive-only", "archive_gated", "academic_structure"),
    ("curricula_tasks", 1, 20, "sparse-archive-only", "archive_gated", "academic_structure"),
    ("curricula_tasks_content", 5, 60, "sparse-migrate-partial", "review_gated", "academic_structure"),
    ("curricula_tasks_content_teachers", 0, 60, "empty-skip", "empty_gated", "academic_structure"),
    ("departments", 31, 80, "migrate", "transform_candidate", "academic_structure"),
    ("ders_cedveli", 433, 70, "migrate-partial", "review_gated", "academic_structure"),
    ("exam_answers", 1306373, 80, "migrate", "transform_candidate", "exams"),
    ("exam_list", 5848, 80, "migrate", "transform_candidate", "exams"),
    ("exam_question_topics", 853, 50, "migrate-partial", "review_gated", "exams"),
    ("exam_questions", 294702, 80, "migrate", "transform_candidate", "exams"),
    ("exam_students_start", 29263, 70, "migrate-partial", "review_gated", "exams"),
    ("ferdi_plan", 0, 20, "empty-skip", "empty_gated", "academic_structure"),
    ("groups", 766, 80, "migrate", "transform_candidate", "academic_structure"),
    ("holidays", 18, 0, "archive-only-gap", "archive_gated", "academic_structure"),
    ("imthngrscxsblr", 12544, 70, "migrate-partial", "review_gated", "grading"),
    ("journal_exam_joint", 5041, 40, "migrate-partial+archive", "review_gated", "grading"),
    ("journals", 13875, 70, "migrate-partial", "review_gated", "grading"),
    ("journals_dates", 44268, 70, "transform-deduplicate", "review_gated", "grading"),
    ("journals_dates_added_by_teacher", 379215, 80, "transform-deduplicate", "review_gated", "grading"),
    ("journals_dates_parsed", 34178, 80, "transform-deduplicate", "review_gated", "grading"),
    ("journals_dates_points", 5135289, 80, "migrate-critical", "review_gated", "grading"),
    ("journals_dates_points_archive", 776033, 40, "historical-archive", "archive_gated", "grading"),
    ("journals_dates_rooms", 291509, 60, "migrate-partial+archive", "review_gated", "grading"),
    ("journals_files", 23837, 70, "migrate-partial", "review_gated", "grading"),
    ("lessons", 2521, 90, "migrate", "transform_candidate", "academic_structure"),
    ("level_exams", 12, 70, "migrate-partial", "review_gated", "exams"),
    ("level_exams_questions", 496, 80, "migrate", "transform_candidate", "exams"),
    ("level_exams_topics", 113, 60, "migrate-partial", "review_gated", "exams"),
    ("level_results", 1598, 80, "migrate", "transform_candidate", "exams"),
    ("niq", 1, 0, "sparse-blank-archive", "archive_gated", "communications"),
    ("notifications", 15, 80, "migrate", "transform_candidate", "communications"),
    ("notifications_groups", 1, 50, "sparse-transform", "review_gated", "communications"),
    ("notifications_logs", 11, 80, "fold-into-parent", "review_gated", "communications"),
    ("ntg", 41, 0, "unknown-archive-only", "unknown_gated", "communications"),
    ("room_types", 4, 30, "lookup-archive", "archive_gated", "academic_structure"),
    ("rooms", 158, 60, "migrate-partial", "review_gated", "academic_structure"),
    ("semestr_jurnal", 13, 80, "migrate", "transform_candidate", "grading"),
    ("sillabus", 8248, 50, "migrate-partial+archive", "design_gated", "syllabus"),
    ("sillabus_certificates", 9846, 60, "migrate-partial-deduplicate", "design_gated", "syllabus"),
    ("sillabus_dersin_islenme_formasi", 8261, 30, "migrate-metadata+archive", "design_gated", "syllabus"),
    ("sillabus_derslikler", 16476, 60, "migrate-partial", "design_gated", "syllabus"),
    ("sillabus_eldeolunacaq_tecrubeler", 8261, 30, "migrate-metadata+archive", "design_gated", "syllabus"),
    ("sillabus_elmi_maraq", 10739, 60, "migrate-partial-deduplicate", "design_gated", "syllabus"),
    ("sillabus_imtahan_suallari", 20835, 50, "migrate-to-review-inbox", "design_gated", "syllabus"),
    ("sillabus_qarsilama_mesaji", 4676, 70, "migrate-partial-deduplicate", "design_gated", "syllabus"),
    ("sillabus_sem_muh", 131056, 60, "migrate-partial", "design_gated", "syllabus"),
    ("sillabus_serbest_is", 60878, 90, "migrate", "design_gated", "syllabus"),
    ("sillabus_tesviri_ve_meqsedi", 6491, 70, "migrate-partial-versioned", "design_gated", "syllabus"),
    ("sillabus_yoxlama_formasi", 8261, 40, "migrate-metadata+manual-modeling", "design_gated", "syllabus"),
    ("smestr", 9, 60, "lookup-transform", "review_gated", "academic_structure"),
    ("speciality", 83, 90, "migrate", "transform_candidate", "academic_structure"),
    ("students", 7816, 70, "migrate-critical+archive", "review_gated", "identity_rbac"),
    ("students_login_logs", 0, 70, "empty-skip", "empty_gated", "identity_rbac"),
    ("students_telegram", 48974, 0, "archive-only-sensitive", "security_gated", "communications"),
    ("students_tg_reply", 106, 0, "archive-only", "archive_gated", "communications"),
    ("track_student", 1003, 20, "archive-only-by-default", "archive_gated", "exams"),
    ("turnir_results", 0, 70, "empty-skip", "empty_gated", "live_tournament"),
    ("turnir_schedule", 0, 50, "empty-skip", "empty_gated", "live_tournament"),
    ("turnir_students_answers", 0, 80, "empty-skip", "empty_gated", "live_tournament"),
    ("turnirs", 0, 60, "empty-skip", "empty_gated", "live_tournament"),
    ("turnirs_joined_students", 0, 40, "empty-skip", "empty_gated", "live_tournament"),
    ("turnirs_questions", 0, 80, "empty-skip", "empty_gated", "live_tournament"),
    ("turnirs_starts", 0, 20, "empty-skip", "empty_gated", "live_tournament"),
    ("umumi_orta_bal", 1570, 20, "validation-only", "validate_only", "grading"),
    ("update_log", 253334, 60, "migrate-partial+archive", "review_gated", "grading"),
    ("workers", 729, 70, "migrate-critical+archive", "review_gated", "identity_rbac"),
    ("workers_login_logs", 0, 70, "empty-skip", "empty_gated", "identity_rbac"),
    ("workers_permits", 914, 60, "migrate-security-review", "security_gated", "identity_rbac"),
    ("xidmeti_muraciet", 2, 50, "sparse-migrate-partial", "review_gated", "service_request"),
    ("xidmeti_muraciet_files", 3, 10, "sparse-archive-only-gap", "archive_gated", "service_request"),
    ("yekun", 17194, 80, "migrate-historical", "review_gated", "grading"),
    ("yekun_24_02_2023", 0, 0, "historical-empty-skip", "empty_gated", "grading"),
    ("yekun_old", 0, 0, "historical-empty-skip", "empty_gated", "grading"),
)

_SYLLABUS_TABLES = frozenset(
    {
        "sillabus",
        "sillabus_certificates",
        "sillabus_dersin_islenme_formasi",
        "sillabus_derslikler",
        "sillabus_eldeolunacaq_tecrubeler",
        "sillabus_elmi_maraq",
        "sillabus_imtahan_suallari",
        "sillabus_qarsilama_mesaji",
        "sillabus_sem_muh",
        "sillabus_serbest_is",
        "sillabus_tesviri_ve_meqsedi",
        "sillabus_yoxlama_formasi",
    }
)
_FAIL_CLOSED_STATUS_ACTIONS = {
    "archive-only-sensitive": LegacyTableAction.SECURITY_GATED,
    "migrate-security-review": LegacyTableAction.SECURITY_GATED,
    "unknown-archive-only": LegacyTableAction.UNKNOWN_GATED,
    "empty-skip": LegacyTableAction.EMPTY_GATED,
    "historical-empty-skip": LegacyTableAction.EMPTY_GATED,
}
_DOMAIN_PHASES = {
    "academic_structure": 10,
    "identity_rbac": 20,
    "syllabus": 30,
    "exams": 40,
    "grading": 50,
    "communications": 60,
    "library": 60,
    "live_tournament": 60,
    "service_request": 60,
}


def _fingerprint(entries: tuple[LegacyTablePlanEntry, ...]) -> str:
    payload = {
        "entries": [
            [
                entry.source_table,
                entry.expected_rows,
                entry.compatibility_pct,
                entry.status,
                entry.action.value,
                entry.domain_key,
                entry.dependency_phase,
                entry.adapter_key,
            ]
            for entry in entries
        ],
        "source_snapshot_sha256": SOURCE_SNAPSHOT_SHA256,
        "version": TABLE_PLAN_VERSION,
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _validated_entries() -> tuple[LegacyTablePlanEntry, ...]:
    try:
        entries = tuple(
            LegacyTablePlanEntry(
                name,
                count,
                compatibility,
                status,
                LegacyTableAction(action),
                domain_key,
                _DOMAIN_PHASES[domain_key],
                None,
            )
            for name, count, compatibility, status, action, domain_key in _PLAN_ROWS
        )
    except Exception:
        raise LegacyTablePlanError("legacy_table_plan_invalid") from None

    names = tuple(entry.source_table for entry in entries)
    if (
        len(entries) != EXPECTED_TABLE_COUNT
        or len(set(names)) != len(names)
        or names != tuple(sorted(names))
        or any(not _SAFE_TABLE_NAME.fullmatch(name) for name in names)
        or sum(entry.expected_rows for entry in entries) != EXPECTED_ROW_COUNT
        or any(type(entry.expected_rows) is not int or entry.expected_rows < 0 for entry in entries)
        or any(type(entry.compatibility_pct) is not int or not 0 <= entry.compatibility_pct <= 100 for entry in entries)
        or any(entry.dependency_phase != _DOMAIN_PHASES.get(entry.domain_key) for entry in entries)
        or any(entry.adapter_key is not None for entry in entries)
    ):
        raise LegacyTablePlanError("legacy_table_plan_invariant_failed")

    syllabus_entries = {entry.source_table for entry in entries if entry.action is LegacyTableAction.DESIGN_GATED}
    if syllabus_entries != _SYLLABUS_TABLES:
        raise LegacyTablePlanError("legacy_table_plan_design_gate_failed")
    if {entry.source_table for entry in entries if entry.domain_key == "syllabus"} != _SYLLABUS_TABLES:
        raise LegacyTablePlanError("legacy_table_plan_syllabus_domain_failed")
    for entry in entries:
        required_action = _FAIL_CLOSED_STATUS_ACTIONS.get(entry.status)
        if required_action is not None and entry.action is not required_action:
            raise LegacyTablePlanError("legacy_table_plan_fail_closed_action_invalid")
        if entry.action is LegacyTableAction.TRANSFORM_CANDIDATE and entry.status != "migrate":
            raise LegacyTablePlanError("legacy_table_plan_import_action_invalid")
    special = next(entry for entry in entries if entry.source_table == "yekun_24_02_2023")
    if special.expected_rows != 0 or special.action is not LegacyTableAction.EMPTY_GATED:
        raise LegacyTablePlanError("legacy_table_plan_pkless_exception_invalid")
    return entries


@lru_cache(maxsize=1)
def load_legacy_table_plan() -> LegacyTablePlan:
    """Load and fully attest the code-owned v1 registry."""

    entries = _validated_entries()
    fingerprint = _fingerprint(entries)
    if fingerprint != _EXPECTED_PLAN_FINGERPRINT:
        raise LegacyTablePlanError("legacy_table_plan_fingerprint_mismatch")
    return LegacyTablePlan(
        version=TABLE_PLAN_VERSION,
        fingerprint=fingerprint,
        source_snapshot_sha256=SOURCE_SNAPSHOT_SHA256,
        expected_row_count=EXPECTED_ROW_COUNT,
        entries=entries,
    )

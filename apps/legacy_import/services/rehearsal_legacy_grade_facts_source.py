"""Legacy qiymət faktlarının xam, itkisiz mənbə proyeksiyası.

``yekun`` sətirləri və jurnalın bütün final-domen xanaları (``im``, ``im2`` və
naməlum xüsusi kodlar) burada oxunur. Arxiv kəsimi, dublikat seçkisi, fake jurnal
süzgəci və bal tavanı xam sübuta tətbiq edilmir: həmin qaydalar kanonik hədəf
üçündür, sübut qatında isə hər mənbə sətri ayrıca qalmalıdır.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

from apps.legacy_import.models import LegacyMigrationIssue

from .field_contracts import JOURNAL_POINT_ARCHIVE_FIELDS, JOURNAL_POINT_FIELDS, YEKUN_FIELDS
from .legacy_grade_field_contracts import EXAM_ENTRY_EXIT_FIELDS
from .rehearsal_contracts import LegacyRehearsalEvidenceError, RehearsalContext, source_row_hash
from .rehearsal_journal_enrollments_phase import JOURNAL_ENROLLMENT_ENTITY_TYPE, parse_student_ids
from .rehearsal_journal_offerings_source import journal_rows, legacy_int, validated_uniqid

# ``is_final_month`` final fazada yaşayır; dövri import yaratmamaq üçün eyni sadə
# domen predikatı burada lokal saxlanılır.
from .rehearsal_journal_points_source import (
    CALENDAR_MONTHS,
    COMPONENT_MONTHS,
    EXAM_MONTH,
    RESIT_MONTH,
    archive_rows,
    attested_rows,
    legacy_text,
    point_rows,
    yekun_rows,
)

SOURCE_SYSTEM = "myedu_mariadb"
SUMMARY_KIND = "summary"
EXAM_KIND = "exam"
RESIT_KIND = "resit"
OTHER_KIND = "other"
EXAM_ENTRY_EXIT_KIND = "exam_entry_exit"

LINKED = "linked"
GROUP_MISMATCH = "group_mismatch"
DISCARDED_SOURCE = "discarded_source"
UNRESOLVED = "unresolved"
CONFLICT = "conflict"


@dataclass(frozen=True)
class JournalMeta:
    uniqid: str
    discarded: bool
    lesson_ref: str
    student_refs: tuple[str, ...]


@dataclass(frozen=True)
class AttemptEnrollmentCandidate:
    uniqid: str
    source_enrollment_ref: str
    enrollment_pk: str
    discarded: bool


@dataclass(frozen=True)
class GradeFactRequest:
    source_table: str
    source_pk: int
    source_row_hash: str
    payload: dict[str, object]
    rule_codes: tuple[str, ...]

    @property
    def seal_key(self) -> str:
        return f"{self.source_table}:{self.source_pk}"


def is_grade_domain(month_id: str) -> bool:
    return month_id not in CALENDAR_MONTHS and month_id not in COMPONENT_MONTHS


def journal_metadata(context: RehearsalContext) -> tuple[dict[int, JournalMeta], dict[str, JournalMeta]]:
    by_id: dict[int, JournalMeta] = {}
    by_uniqid: dict[str, JournalMeta] = {}
    for legacy_pk, row in journal_rows(context):
        student_ids = parse_student_ids(row["students_id"]) or ()
        meta = JournalMeta(
            uniqid=validated_uniqid(row["uniqid"]),
            discarded=legacy_int(row["fake"]) == 1 or legacy_int(row["sonra_sil"]) == 1,
            lesson_ref=str(legacy_int(row["lesson_id"])),
            student_refs=tuple(str(student_id) for student_id in student_ids),
        )
        by_id[legacy_pk] = meta
        by_uniqid[meta.uniqid] = meta
    return by_id, by_uniqid


def attempt_enrollment_candidates(
    journals_by_uniqid: Mapping[str, JournalMeta],
    enrollments: Mapping[str, str],
) -> dict[tuple[str, str], AttemptEnrollmentCandidate]:
    """Yalnız tək mənbə jurnalına düşən (tələbə, fənn) cütünü həll et.

    ``imthngrscxsblr`` jurnal/qrup/semester açarı daşımır. Buna görə eyni
    tələbə+fənn üçün birdən çox jurnal varsa heç birini təxmin etmirik. Tək
    jurnal olduqda da yalnız həmin run-da MIGRATED enrollment möhürü hədəf
    UUID-sinə sübut verir; qalan hallarda xam fakt unresolved qalır.
    """

    possible: dict[tuple[str, str], list[JournalMeta]] = defaultdict(list)
    for journal in journals_by_uniqid.values():
        for student_ref in journal.student_refs:
            possible[(student_ref, journal.lesson_ref)].append(journal)

    resolved: dict[tuple[str, str], AttemptEnrollmentCandidate] = {}
    for key, journals in possible.items():
        if len(journals) != 1:
            continue
        journal = journals[0]
        source_ref = _source_enrollment_ref(journal.uniqid, key[0])
        enrollment_pk = enrollments.get(source_ref, "")
        if not enrollment_pk and not journal.discarded:
            continue
        resolved[key] = AttemptEnrollmentCandidate(
            uniqid=journal.uniqid,
            source_enrollment_ref=source_ref,
            enrollment_pk=enrollment_pk,
            discarded=journal.discarded,
        )
    return resolved


def group_mismatch_keys(context: RehearsalContext) -> set[str]:
    rows = LegacyMigrationIssue.objects.filter(
        run_id=context.run_id,
        entity_type=JOURNAL_ENROLLMENT_ENTITY_TYPE,
        rule_code="legacy_journal_student_group_mismatch",
    ).values_list("legacy_pk", flat=True)
    return set(rows.iterator(chunk_size=10_000))


def _number_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool) or type(value) not in (int, float, Decimal):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return format(value, "f") if isinstance(value, Decimal) else str(value)


def _number_decimal(text: str) -> Decimal | None:
    if text == "":
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value


def _recorded_at_text(value: object) -> str:
    if type(value) is not datetime.datetime:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value.isoformat(sep=" ")


def _mapping(
    *,
    uniqid: str,
    student_ref: str,
    enrollments: Mapping[str, str],
    discarded: bool,
    mismatches: set[str],
    conflicting: bool = False,
) -> tuple[str, str, str]:
    key = f"{uniqid}:{student_ref}" if uniqid else ""
    enrollment_pk = enrollments.get(key, "") if key else ""
    if discarded:
        return DISCARDED_SOURCE, "legacy_grade_fact_discarded_source", ""
    if key in mismatches:
        return GROUP_MISMATCH, "legacy_grade_fact_group_mismatch", ""
    if not enrollment_pk:
        return UNRESOLVED, "legacy_grade_fact_unresolved", ""
    if conflicting:
        return CONFLICT, "legacy_grade_fact_conflict", enrollment_pk
    return LINKED, "", enrollment_pk


def _source_enrollment_ref(uniqid: str, student_ref: str) -> str:
    """Target UUID-dən asılı olmayan canonical source mapping açarı."""

    return f"{uniqid}:{student_ref}" if uniqid else ""


def _score_range_rules(*, entry=None, exam=None, final=None) -> tuple[str, ...]:
    invalid = (
        (entry is not None and not Decimal("0") <= entry <= Decimal("50"))
        or (exam is not None and not Decimal("0") <= exam <= Decimal("50"))
        or (final is not None and not Decimal("0") <= final <= Decimal("100"))
    )
    return ("legacy_grade_fact_out_of_range",) if invalid else ()


def summary_conflicts(rows, *, journals_by_id, enrollments) -> set[str]:
    triplets: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for _legacy_pk, row in rows:
        journal = journals_by_id.get(legacy_int(row["journal_id"]))
        if journal is None:
            continue
        student_ref = str(legacy_int(row["student_id"]))
        enrollment_pk = enrollments.get(f"{journal.uniqid}:{student_ref}", "")
        if enrollment_pk:
            triplets[enrollment_pk].add(
                (_number_text(row["girish"]), _number_text(row["imtahanda"]), _number_text(row["yekun"]))
            )
    return {enrollment_pk for enrollment_pk, values in triplets.items() if len(values) > 1}


def summary_requests(
    context: RehearsalContext,
    *,
    rows,
    journals_by_id,
    enrollments,
    mismatches,
    conflicting_enrollments,
) -> Iterable[GradeFactRequest]:
    for legacy_pk, row in rows:
        journal_id = legacy_int(row["journal_id"])
        journal = journals_by_id.get(journal_id)
        student_ref = str(legacy_int(row["student_id"]))
        uniqid = journal.uniqid if journal else ""
        candidate = enrollments.get(f"{uniqid}:{student_ref}", "") if uniqid else ""
        status, issue, enrollment_pk = _mapping(
            uniqid=uniqid,
            student_ref=student_ref,
            enrollments=enrollments,
            discarded=bool(journal and journal.discarded),
            mismatches=mismatches,
            conflicting=bool(candidate and candidate in conflicting_enrollments),
        )
        entry_text = _number_text(row["girish"])
        exam_text = _number_text(row["imtahanda"])
        final_text = _number_text(row["yekun"])
        entry, exam, final = map(_number_decimal, (entry_text, exam_text, final_text))
        rules = tuple(filter(None, (issue,))) + _score_range_rules(entry=entry, exam=exam, final=final)
        yield GradeFactRequest(
            source_table=YEKUN_FIELDS.source_table,
            source_pk=legacy_pk,
            source_row_hash=source_row_hash(contract=YEKUN_FIELDS, legacy_pk=legacy_pk, projected_row=row),
            rule_codes=rules,
            payload={
                "enrollment_id": enrollment_pk or None,
                "evidence_kind": SUMMARY_KIND,
                "score_code": "yekun",
                "is_archive": False,
                "mapping_status": status,
                "mapping_issue_code": issue,
                "source_student_ref": student_ref,
                "source_journal_ref": str(journal_id),
                "source_lesson_ref": str(legacy_int(row["lesson_id"])),
                "source_group_ref": str(legacy_int(row["group_id"])),
                "source_enrollment_ref": _source_enrollment_ref(uniqid, student_ref),
                "entry_score_text": entry_text,
                "exam_score_text": exam_text,
                "resit_score_text": "",
                "final_score_text": final_text,
                "raw_score_text": "",
                "entry_score": entry,
                "exam_score": exam,
                "resit_score": None,
                "final_score": final,
                "legacy_kesr": _optional_int(row["kesr"]),
                "legacy_level": _optional_int(row["level"]),
                "legacy_attempt_type": None,
                "legacy_recorded_at_text": "",
                "legacy_guzest_girish_text": _number_text(row["guzest_girish"]),
                "legacy_guzest_artim_text": _number_text(row["guzest_artim"]),
            },
        )


def point_requests(
    context: RehearsalContext,
    *,
    rows,
    contract,
    is_archive: bool,
    journals_by_uniqid,
    enrollments,
    mismatches,
) -> Iterable[GradeFactRequest]:
    for legacy_pk, row in rows:
        month_id = legacy_text(row["month_id"])
        if not is_grade_domain(month_id):
            continue
        uniqid = validated_uniqid(row["journal_uniqid"])
        student_ref = str(legacy_int(row["student_id"]))
        journal = journals_by_uniqid.get(uniqid)
        status, issue, enrollment_pk = _mapping(
            uniqid=uniqid,
            student_ref=student_ref,
            enrollments=enrollments,
            discarded=bool(journal and journal.discarded),
            mismatches=mismatches,
        )
        raw = legacy_text(row["point"])
        numeric = Decimal(raw) if raw.isdigit() else None
        kind = EXAM_KIND if month_id == EXAM_MONTH else RESIT_KIND if month_id == RESIT_MONTH else OTHER_KIND
        rules = list(filter(None, (issue,)))
        if numeric is None:
            rules.append("legacy_grade_fact_non_numeric")
        elif month_id in (EXAM_MONTH, RESIT_MONTH) and numeric > Decimal("50"):
            rules.append("legacy_grade_fact_out_of_range")
        yield GradeFactRequest(
            source_table=contract.source_table,
            source_pk=legacy_pk,
            source_row_hash=source_row_hash(contract=contract, legacy_pk=legacy_pk, projected_row=row),
            rule_codes=tuple(rules),
            payload={
                "enrollment_id": enrollment_pk or None,
                "evidence_kind": kind,
                "score_code": month_id,
                "is_archive": is_archive,
                "mapping_status": status,
                "mapping_issue_code": issue,
                "source_student_ref": student_ref,
                "source_journal_ref": uniqid,
                "source_lesson_ref": "",
                "source_group_ref": "",
                "source_enrollment_ref": _source_enrollment_ref(uniqid, student_ref),
                "entry_score_text": "",
                "exam_score_text": raw if kind == EXAM_KIND else "",
                "resit_score_text": raw if kind == RESIT_KIND else "",
                "final_score_text": "",
                "raw_score_text": raw,
                "entry_score": None,
                "exam_score": numeric if kind == EXAM_KIND else None,
                "resit_score": numeric if kind == RESIT_KIND else None,
                "final_score": None,
                "legacy_kesr": None,
                "legacy_level": None,
                "legacy_attempt_type": None,
                "legacy_recorded_at_text": "",
                "legacy_guzest_girish_text": "",
                "legacy_guzest_artim_text": "",
            },
        )


def attempt_requests(
    context: RehearsalContext,
    *,
    rows,
    candidates: Mapping[tuple[str, str], AttemptEnrollmentCandidate],
    mismatches: set[str],
) -> Iterable[GradeFactRequest]:
    """İmtahan giriş/çıxış cəhdlərini clamp-siz immutable fakta çevir."""

    for legacy_pk, row in rows:
        student_ref = str(legacy_int(row["student_id"]))
        lesson_ref = str(legacy_int(row["lesson_id"]))
        candidate = candidates.get((student_ref, lesson_ref))
        uniqid = candidate.uniqid if candidate else ""
        status, issue, enrollment_pk = _mapping(
            uniqid=uniqid,
            student_ref=student_ref,
            enrollments={candidate.source_enrollment_ref: candidate.enrollment_pk} if candidate else {},
            discarded=bool(candidate and candidate.discarded),
            mismatches=mismatches,
        )
        entry_text = _number_text(row["giris_point"])
        exam_text = _number_text(row["cixis_point"])
        entry = _number_decimal(entry_text)
        exam = _number_decimal(exam_text)
        rules = tuple(filter(None, (issue,))) + _score_range_rules(entry=entry, exam=exam)
        yield GradeFactRequest(
            source_table=EXAM_ENTRY_EXIT_FIELDS.source_table,
            source_pk=legacy_pk,
            source_row_hash=source_row_hash(
                contract=EXAM_ENTRY_EXIT_FIELDS,
                legacy_pk=legacy_pk,
                projected_row=row,
            ),
            rule_codes=rules,
            payload={
                "enrollment_id": enrollment_pk or None,
                "evidence_kind": EXAM_ENTRY_EXIT_KIND,
                "score_code": EXAM_ENTRY_EXIT_KIND,
                "is_archive": False,
                "mapping_status": status,
                "mapping_issue_code": issue,
                "source_student_ref": student_ref,
                "source_journal_ref": uniqid,
                "source_lesson_ref": lesson_ref,
                "source_group_ref": "",
                "source_enrollment_ref": candidate.source_enrollment_ref if candidate else "",
                "entry_score_text": entry_text,
                "exam_score_text": exam_text,
                "resit_score_text": "",
                "final_score_text": "",
                "raw_score_text": "",
                "entry_score": entry,
                "exam_score": exam,
                "resit_score": None,
                "final_score": None,
                "legacy_kesr": None,
                "legacy_level": None,
                "legacy_guzest_girish_text": "",
                "legacy_guzest_artim_text": "",
                "legacy_attempt_type": _optional_int(row["type"]),
                "legacy_recorded_at_text": _recorded_at_text(row["added_date"]),
            },
        )


def attempt_rows(context: RehearsalContext):
    return attested_rows(
        context,
        contract=EXAM_ENTRY_EXIT_FIELDS,
        source_table=EXAM_ENTRY_EXIT_FIELDS.source_table,
    )


POINT_STREAMS = (
    (point_rows, JOURNAL_POINT_FIELDS, False),
    (archive_rows, JOURNAL_POINT_ARCHIVE_FIELDS, True),
)


__all__ = [
    "EXAM_ENTRY_EXIT_KIND",
    "GradeFactRequest",
    "POINT_STREAMS",
    "SOURCE_SYSTEM",
    "attempt_enrollment_candidates",
    "attempt_requests",
    "attempt_rows",
    "group_mismatch_keys",
    "journal_metadata",
    "point_requests",
    "summary_conflicts",
    "summary_requests",
    "yekun_rows",
]

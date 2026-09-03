"""Source side of the ``academic_catalog`` phase: stream, validate, derive.

Nothing here touches a Django model or writes a target row: the module turns the
three audited catalogue contracts (plus a read of the UNCLAIMED ``groups`` table)
into an immutable, fully classified cohort so the phase module can spend its
whole budget on ledger bookkeeping.  Every stream repeats the structure phase's
primary-key interlocks verbatim — type drift, range, strict ascent, exact plan
row count — because a catalogue table is accounted for in the very same batch
chain.

Three derivations only happen after ALL four tables are read, which makes the
cohort a pure function of the source: ``Curriculum.admission_year`` needs the
groups that reference the curriculum (V-7 — ``curricula.from_date`` is empty in
the live dump), ``Subject.ects`` needs the plan rows that reference the lesson,
and the subject dedup groups need every lesson name at once (E-4).

V-8/V-14: ``curricula_plan.lesson_id`` is a JSON array literal, NOT a scalar and
NOT ``lesson_code`` (V-6).  A multi-element array is EXPANDED — every resolvable
element becomes its own ``CurriculumSubject`` — so this module returns the whole
resolved tuple and lets the target module decide what a partial resolution means.

V-20/V-21 replaced the two places this module used to give up: the admission
year walks a four-tier ladder (``from_date`` → groups → ``to_date`` minus the
degree duration → the nearest dated neighbour) instead of quarantining, and
``curricula_plan.type`` is a real elective-block label instead of an unmapped
token.  Each derived tier carries its own issue code, so an inference is never
mistaken for a fact the source stated.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from .field_contracts import (
    CURRICULUM_CATALOG_FIELDS,
    CURRICULUM_PLAN_FIELDS,
    GROUP_STRUCTURE_FIELDS,
    LESSON_CATALOG_FIELDS,
)
from .legacy_text import clean_code, clean_text
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    PlanSemesterScheme,
    source_row_hash,
)
from .rehearsal_structure_source import (
    DEFAULT_DEGREE_LEVEL,
    DEGREE_BY_LEGACY,
    EDUCATION_FORM_BY_LEGACY,
    MASTER_DEGREE_LEVEL,
    MAX_ADMISSION_YEAR,
    MIN_ADMISSION_YEAR,
    group_admission_year,
)
from .source_extraction import open_audited_source_stream

CATALOG_COHORT_MAX_ROWS = 5_000  # lessons 2 521, curricula 126, plan 3 424, groups 766
SUBJECT_CODE_PREFIX = "MYEDU-L"
SUBJECT_NAME_MAX_LENGTH = 255  # registrar.Subject.name
SUBJECT_CODE_MAX_LENGTH = 32  # registrar.Subject.code; "MYEDU-L" + a bigint fits
MIN_SUBJECT_ECTS, MAX_SUBJECT_ECTS = 1, 60
DEFAULT_SUBJECT_ECTS = 5  # registrar.Subject.ects model default
MAX_SEMESTER_NUMBER = 16
SEMESTER_TOKEN_PATTERN = re.compile(r"(payiz|yaz)_(\d{1,2})\Z")
AUTUMN_TOKEN, SPRING_TOKEN = "payiz", "yaz"
LESSON_REFERENCE_PATTERN = re.compile(r"\d{1,10}\Z")
CURRICULUM_YEAR_PATTERN = re.compile(r"\d{4}\Z")
# V-21: ``2.1``/``4.07`` label an elective BLOCK; a bare integer is mandatory.
PLAN_ELECTIVE_TOKEN_PATTERN = re.compile(r"\d+\.\d+\Z")
PLAN_MANDATORY_TOKEN_PATTERN = re.compile(r"\d+\Z")
ELECTIVE_REQUIRED_CHOICES = 1  # one subject per block (V-21: the GROUP chooses)
LESSON_REFERENCE_MAX_LENGTH = 250  # curricula_plan.lesson_id is a varchar(250)
SEMESTER_TOKEN_MAX_LENGTH = 25
TYPE_TOKEN_MAX_LENGTH = 25
PLAN_TYPE_TOKEN_MAX_LENGTH = 10
LEGACY_CODE_MAX_LENGTH = 25
CURRICULUM_DATE_MAX_LENGTH = 4
_HOUR_FIELDS = ("saat_aks", "saat_as", "saat_muh", "saat_sem", "saat_lab", "saat_prak")
_DEGREE_TEXT_MAX_LENGTH = 64
# V-20 T3: ``to_date`` is the year the plan RUNS OUT, so the intake year is that
# year minus the programme's nominal length.  Both values are the AZ statutory
# ones (bakalavr 4 il, magistr 2 il), never a per-curriculum guess.
PROGRAM_DURATION_BY_DEGREE = MappingProxyType({DEFAULT_DEGREE_LEVEL: 4, MASTER_DEGREE_LEVEL: 2})
_VALUE_TYPE_UNSUPPORTED = "legacy_rehearsal_source_value_type_unsupported"
# V-13: ``payiz`` is an ODD semester and ``yaz`` an EVEN one, so under ORDINAL a
# ``payiz_2``/``yaz_3`` token contradicts the scheme itself (§5.3).
_ODD_SEMESTER_TOKEN = AUTUMN_TOKEN


@dataclass(frozen=True)
class SourceLesson:
    """One ``lessons`` row, already classified against §4."""

    legacy_pk: int
    source_row_hash: str
    name: str
    name_key: str  # dedup key half; a blank name never dedups (E-4)
    department_legacy_pk: int
    type_token: str
    legacy_code: str
    only_az: int
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class SubjectPlan:
    """A derived ``registrar.Subject``: one per DEDUPLICATED lesson group."""

    legacy_pk: int  # the winning lessons.id
    code: str
    name: str
    ects: int
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class SourceCurriculum:
    """One ``curricula`` row, already classified against §5.1."""

    legacy_pk: int
    source_row_hash: str
    speciality_legacy_pk: int
    degree_level: str
    education_form: str
    admission_year: int | None
    # V-20 ladder token: curriculum | group | to_date_minus_duration | neighbor | none
    admission_year_source: str
    to_date: str
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class SourcePlanRow:
    """One ``curricula_plan`` row, already classified against §5.2."""

    legacy_pk: int
    source_row_hash: str
    curriculum_legacy_pk: int
    lesson_legacy_pks: tuple[int, ...]  # V-14: () ⇒ no usable reference at all
    semester_number: int  # 0 ⇒ unresolved
    order: int
    type_token: str
    is_elective: bool  # V-21: derived from ``type``, never invented
    elective_group: str  # the block label ("" for a mandatory row)
    credit_ects: int  # 0 ⇒ contributes nothing to the ECTS derivation
    credit_text: str
    hours_token: str
    prerequisite_legacy_pk: int
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class CatalogCohort:
    """The whole phase input; every tuple is in a deterministic order."""

    lessons: tuple[SourceLesson, ...]  # ascending legacy_pk
    subjects: tuple[SubjectPlan, ...]  # ascending winning legacy_pk
    subject_owner: Mapping[int, int]  # lessons.id -> winning lessons.id
    curricula: tuple[SourceCurriculum, ...]  # ascending legacy_pk
    plan_rows: tuple[SourcePlanRow, ...]  # ascending legacy_pk


def _projected_rows(context, contract) -> list:
    """Stream one contract in attested, strictly ascending primary-key order."""

    entry = context.plan.entry_for(contract.source_table)
    if entry.expected_rows > CATALOG_COHORT_MAX_ROWS:
        raise LegacyRehearsalConfigError("legacy_rehearsal_cohort_too_large")
    rows = []
    previous_pk = 0
    with open_audited_source_stream(
        connection_factory=context.source_connection_factory,
        contract=contract,
        chunk_size=context.policy.source_chunk_size,
        cancellation_requested=context.cancellation_requested,
    ) as stream:
        for projected_row in stream:
            legacy_pk = projected_row["id"]
            # Mirror pk_inventory._row_pk exactly: no coercion, fail closed.
            if type(legacy_pk) is not int:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_type_drift")
            if not 1 <= legacy_pk <= MAX_LEDGER_PRIMARY_KEY:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_out_of_range")
            if legacy_pk <= previous_pk:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_order_invalid")
            previous_pk = legacy_pk
            rows.append((legacy_pk, projected_row))
            if len(rows) > entry.expected_rows:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
    if len(rows) != entry.expected_rows:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
    return rows


def _legacy_int(value: object) -> int:
    """A legacy integer column; ``NULL`` is the same zero sentinel MySQL writes."""

    if value is None:
        return 0
    # ``type() is int`` is already False for ``bool``, so the flags stay fatal.
    if type(value) is not int:
        raise LegacyRehearsalEvidenceError(_VALUE_TYPE_UNSUPPORTED)
    return value


def _legacy_float(value: object) -> float:
    """A legacy ``FLOAT`` column (C-2); ``Decimal`` would need its own branch."""

    if value is None:
        return 0.0
    if type(value) is not float:
        raise LegacyRehearsalEvidenceError(_VALUE_TYPE_UNSUPPORTED)
    return value


def _subject_name(value: object, legacy_pk: int, rule_codes: list[str]) -> tuple[str, str]:
    """Return ``(name, name_key)``; a blank name gets a key that never dedups."""

    name, truncated = clean_text(value, max_length=SUBJECT_NAME_MAX_LENGTH)
    if not name:
        rule_codes.append("legacy_subject_name_blank")
        return f"Fənn {legacy_pk}", f"\x00blank-{legacy_pk}"
    if truncated:
        rule_codes.append("legacy_subject_name_truncated")
    return name, name.casefold()


def _lesson(legacy_pk: int, row) -> SourceLesson:
    rule_codes: list[str] = []
    name, name_key = _subject_name(row["name"], legacy_pk, rule_codes)
    legacy_code, _truncated = clean_code(row["lesson_code"], max_length=LEGACY_CODE_MAX_LENGTH)
    type_token, _truncated = clean_code(row["type"], max_length=TYPE_TOKEN_MAX_LENGTH)
    return SourceLesson(
        legacy_pk=legacy_pk,
        source_row_hash=source_row_hash(contract=LESSON_CATALOG_FIELDS, legacy_pk=legacy_pk, projected_row=row),
        name=name,
        name_key=name_key,
        department_legacy_pk=_legacy_int(row["department_id"]),
        type_token=type_token,
        legacy_code=legacy_code,  # V-6: evidence only, never a target value
        only_az=_legacy_int(row["only_az"]),
        rule_codes=tuple(rule_codes),
    )


def lesson_references(value: object) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Parse ``curricula_plan.lesson_id`` (V-8) and expand it (V-14).

    Returns the referenced ``lessons.id`` values in source order, deduplicated,
    plus the rule codes the parse produced.  A ``json`` failure never escapes as
    anything but a code, and a malformed element degrades the row to whatever
    its siblings resolve to instead of killing the whole reference.
    """

    text, _truncated = clean_text(value, max_length=LESSON_REFERENCE_MAX_LENGTH)
    if not text:
        return (), ("legacy_plan_lesson_reference_invalid",)
    try:
        parsed = json.loads(text)
    except Exception:
        return (), ("legacy_plan_lesson_reference_invalid",)
    if not isinstance(parsed, list) or not parsed:
        return (), ("legacy_plan_lesson_reference_invalid",)
    references: list[int] = []
    rule_codes: list[str] = []
    for element in parsed:
        if type(element) is int and 1 <= element <= MAX_LEDGER_PRIMARY_KEY:
            reference = element
        elif type(element) is str and LESSON_REFERENCE_PATTERN.fullmatch(element.strip()):
            reference = int(element.strip())
        else:
            if "legacy_plan_lesson_reference_invalid" not in rule_codes:
                rule_codes.append("legacy_plan_lesson_reference_invalid")
            continue
        if reference not in references:
            references.append(reference)
    if len(references) > 1:
        # V-14: 883/3 424 live rows carry more than one element; each of them
        # becomes its own plan row instead of quarantining the whole reference.
        rule_codes.append("legacy_plan_lesson_reference_expanded")
    return tuple(references), tuple(rule_codes)


def semester_number(value: object, scheme: PlanSemesterScheme) -> tuple[int, tuple[str, ...]]:
    """``payiz_N``/``yaz_N`` → a semester number under the policy scheme (§5.3)."""

    token, _truncated = clean_code(value, max_length=SEMESTER_TOKEN_MAX_LENGTH)
    matched = SEMESTER_TOKEN_PATTERN.fullmatch(token.lower())
    if matched is None:
        return 0, ("legacy_plan_semester_invalid",)
    term, ordinal = matched.group(1), int(matched.group(2))
    if scheme is PlanSemesterScheme.TERM_PAIR:
        number = 2 * ordinal - 1 if term == AUTUMN_TOKEN else 2 * ordinal
    else:
        number = ordinal
    if not 1 <= number <= MAX_SEMESTER_NUMBER:
        return 0, ("legacy_plan_semester_out_of_range",)
    if scheme is PlanSemesterScheme.ORDINAL and (number % 2 == 0) == (term == _ODD_SEMESTER_TOKEN):
        # The row still migrates: the scheme is a policy choice, and a cohort
        # full of these warnings is exactly the evidence that it was the wrong one.
        return number, ("legacy_plan_semester_scheme_conflict",)
    return number, ()


def _credit(value: object) -> tuple[int, str, tuple[str, ...]]:
    """``kredit`` → an ECTS candidate; never rounded, so ``2.5`` contributes nothing."""

    credit = _legacy_float(value)
    credit_text = format(credit, ".4f")
    if credit.is_integer() and MIN_SUBJECT_ECTS <= credit <= MAX_SUBJECT_ECTS:
        return int(credit), credit_text, ()
    if credit == 0.0:
        # V-16: every live ``kredit`` is a whole number in 0..10, and 0 is the
        # "not recorded" sentinel — an absent fact, not an unsupported value.
        return 0, credit_text, ()
    return 0, credit_text, ("legacy_plan_credit_unsupported",)


def _hours(row) -> tuple[str, tuple[str, ...]]:
    """``saat_*`` is not modelled (E-7); the raw values still enter the token."""

    values = [_legacy_float(row[field_name]) for field_name in _HOUR_FIELDS]
    token = "|".join(format(value, ".2f") for value in values)
    return token, ("legacy_plan_hours_not_modelled",) if any(values) else ()


def plan_elective(type_token: str) -> tuple[bool, str, tuple[str, ...]]:
    """``curricula_plan.type`` → the elective block it names (V-21).

    The university answered V-9: ministry subjects are mandatory, university
    subjects are elective and the GROUP chooses.  Dotted tokens (``2.1``,
    ``4.01``…``4.24``) are block labels; a bare integer and a blank are
    mandatory.  A token in neither family stays visible rather than becoming
    mandatory by luck.
    """

    if not type_token:
        return False, "", ()
    if PLAN_ELECTIVE_TOKEN_PATTERN.fullmatch(type_token):
        return True, type_token, ("legacy_plan_elective_block",)
    if PLAN_MANDATORY_TOKEN_PATTERN.fullmatch(type_token):
        return False, "", ()
    return False, "", ("legacy_plan_type_unmapped",)


def _plan_row(legacy_pk: int, row, scheme: PlanSemesterScheme) -> SourcePlanRow:
    rule_codes: list[str] = []
    references, reference_rules = lesson_references(row["lesson_id"])
    rule_codes.extend(reference_rules)
    number, semester_rules = semester_number(row["semestr"], scheme)
    rule_codes.extend(semester_rules)
    type_token, _truncated = clean_code(row["type"], max_length=PLAN_TYPE_TOKEN_MAX_LENGTH)
    is_elective, elective_group, type_rules = plan_elective(type_token)
    rule_codes.extend(type_rules)
    credit_ects, credit_text, credit_rules = _credit(row["kredit"])
    rule_codes.extend(credit_rules)
    hours_token, hours_rules = _hours(row)
    rule_codes.extend(hours_rules)
    prerequisite = _legacy_int(row["lesson_before_id"])
    if prerequisite:
        rule_codes.append("legacy_plan_prerequisite_not_modelled")
    return SourcePlanRow(
        legacy_pk=legacy_pk,
        source_row_hash=source_row_hash(contract=CURRICULUM_PLAN_FIELDS, legacy_pk=legacy_pk, projected_row=row),
        curriculum_legacy_pk=_legacy_int(row["curricula_id"]),
        lesson_legacy_pks=references,
        semester_number=number,
        order=0,  # ranked once the whole table is read
        type_token=type_token,
        is_elective=is_elective,
        elective_group=elective_group,
        credit_ects=credit_ects,
        credit_text=credit_text,
        hours_token=hours_token,
        prerequisite_legacy_pk=prerequisite,
        rule_codes=tuple(rule_codes),
    )


def _ranked(plan_rows) -> tuple[SourcePlanRow, ...]:
    """Rank each row inside ``(curriculum, semester)`` by ascending ``legacy_pk``."""

    ranks: dict[tuple[int, int], int] = {}
    ordered = []
    for row in plan_rows:
        key = (row.curriculum_legacy_pk, row.semester_number)
        order = ranks.get(key, 0)
        ranks[key] = order + 1
        ordered.append(replace(row, order=order))
    return tuple(ordered)


def _curriculum_admission_year(
    row, years: Mapping[int, int], legacy_pk: int, degree_level: str
) -> tuple[int | None, str, tuple[str, ...]]:
    """The V-20 ladder, tiers T1..T3; T4 needs the whole cohort and runs later.

    T1 ``from_date`` (V-7: dead today, kept so a changed dump fails closed) → T2
    the MIN of the referencing groups' start years → T3 ``to_date`` minus the
    degree's nominal duration.  T3 is an INFERENCE, not a record, so it warns.
    """

    text, _truncated = clean_code(row["from_date"], max_length=CURRICULUM_DATE_MAX_LENGTH)
    if CURRICULUM_YEAR_PATTERN.fullmatch(text) and MIN_ADMISSION_YEAR <= int(text) <= MAX_ADMISSION_YEAR:
        return int(text), "curriculum", ()
    year = years.get(legacy_pk)
    if year is not None:
        return year, "group", ()
    to_date, _truncated = clean_code(row["to_date"], max_length=CURRICULUM_DATE_MAX_LENGTH)
    if CURRICULUM_YEAR_PATTERN.fullmatch(to_date):
        inferred = int(to_date) - PROGRAM_DURATION_BY_DEGREE[degree_level]
        if MIN_ADMISSION_YEAR <= inferred <= MAX_ADMISSION_YEAR:
            return inferred, "to_date_minus_duration", ("legacy_curriculum_admission_year_inferred",)
    return None, "none", ()


def _dated_neighbour_years(curricula: tuple[SourceCurriculum, ...]) -> tuple[SourceCurriculum, ...]:
    """V-20 T4: an undated curriculum adopts its nearest DATED neighbour's year.

    "Nearest" is measured on the legacy id the source assigns in creation order:
    the largest dated id BELOW this one, and only when there is none, the
    smallest dated id above.  ``dated`` inherits the cohort's ascent, so the
    choice is a pure function of the source, never of iteration luck.  A cohort
    in which NOTHING is dated is the only one left on the quarantine path.
    """

    dated = [(item.legacy_pk, item.admission_year) for item in curricula if item.admission_year is not None]
    resolved = []
    for curriculum in curricula:
        if curriculum.admission_year is not None:
            resolved.append(curriculum)
            continue
        below = [year for neighbour_pk, year in dated if neighbour_pk < curriculum.legacy_pk]
        if dated:
            year = below[-1] if below else dated[0][1]
            source, rule_code = "neighbor", "legacy_curriculum_admission_year_neighbor"
        else:
            year, source, rule_code = None, "none", "legacy_curriculum_admission_year_unresolved"
        resolved.append(
            replace(
                curriculum,
                admission_year=year,
                admission_year_source=source,
                rule_codes=curriculum.rule_codes + (rule_code,),
            )
        )
    return tuple(resolved)


def _curriculum(legacy_pk: int, row, years: Mapping[int, int]) -> SourceCurriculum:
    rule_codes: list[str] = []
    degree_text, _truncated = clean_text(row["bak_or_mag"], max_length=_DEGREE_TEXT_MAX_LENGTH)
    degree_level = DEGREE_BY_LEGACY.get(degree_text.casefold(), "")
    if not degree_level:
        degree_level = DEFAULT_DEGREE_LEVEL
        rule_codes.append("legacy_curriculum_degree_defaulted")
    form_text, _truncated = clean_text(row["eyani_qiyabi"], max_length=_DEGREE_TEXT_MAX_LENGTH)
    education_form = EDUCATION_FORM_BY_LEGACY.get(form_text.casefold(), "")
    if form_text:
        # ``Curriculum`` has no education_form column: two legacy rows that
        # differ ONLY by əyani/qiyabi merge into one row (§13.7).
        rule_codes.append("legacy_curriculum_education_form_not_modelled")
    # T4 (and the quarantine that replaced it) is decided once the whole cohort
    # is classified, so nothing here appends a year rule beyond T3's inference.
    admission_year, admission_year_source, year_rules = _curriculum_admission_year(row, years, legacy_pk, degree_level)
    rule_codes.extend(year_rules)
    to_date, _truncated = clean_code(row["to_date"], max_length=CURRICULUM_DATE_MAX_LENGTH)
    return SourceCurriculum(
        legacy_pk=legacy_pk,
        source_row_hash=source_row_hash(contract=CURRICULUM_CATALOG_FIELDS, legacy_pk=legacy_pk, projected_row=row),
        speciality_legacy_pk=_legacy_int(row["speciality_id"]),
        degree_level=degree_level,
        education_form=education_form,
        admission_year=admission_year,
        admission_year_source=admission_year_source,
        to_date=to_date,
        rule_codes=tuple(rule_codes),
    )


def _curriculum_years(group_rows) -> dict[int, int]:
    """MIN of the referencing groups' ``start_year`` — stable under later cohorts."""

    years: dict[int, int] = {}
    for _legacy_pk, row in group_rows:
        curricula_legacy_pk = _legacy_int(row["curricula_id"])
        if not curricula_legacy_pk:
            continue
        year, _rule_codes = group_admission_year(row["start_year"])
        if year is None:
            continue
        current = years.get(curricula_legacy_pk)
        if current is None or year < current:
            years[curricula_legacy_pk] = year
    return years


def _subject_plans(lessons, plan_rows) -> tuple[tuple[SubjectPlan, ...], Mapping[int, int]]:
    """Dedup by ``(name_key, department)`` and derive one ECTS per group (E-4/§4)."""

    credits_by_lesson: dict[int, set[int]] = {}
    for row in plan_rows:
        if not row.credit_ects:
            continue
        for reference in row.lesson_legacy_pks:
            credits_by_lesson.setdefault(reference, set()).add(row.credit_ects)
    members: dict[tuple[str, int], list[int]] = {}
    owner: dict[int, int] = {}
    for lesson in lessons:
        group = members.setdefault((lesson.name_key, lesson.department_legacy_pk), [])
        group.append(lesson.legacy_pk)
        owner[lesson.legacy_pk] = group[0]  # ascending stream ⇒ the lowest id wins
    names = {lesson.legacy_pk: lesson.name for lesson in lessons}
    plans = []
    for group in sorted(members.values(), key=lambda item: item[0]):
        winner = group[0]
        accepted: set[int] = set()
        for member in group:
            accepted |= credits_by_lesson.get(member, set())
        rule_codes: tuple[str, ...] = ()
        if len(accepted) == 1:
            ects = accepted.pop()
        elif not accepted:
            ects = DEFAULT_SUBJECT_ECTS
            rule_codes = ("legacy_subject_ects_unavailable",)
        else:
            ects = DEFAULT_SUBJECT_ECTS
            rule_codes = ("legacy_subject_ects_ambiguous",)
        plans.append(
            SubjectPlan(
                legacy_pk=winner,
                code=f"{SUBJECT_CODE_PREFIX}{winner}",
                name=names[winner],
                ects=ects,
                rule_codes=rule_codes,
            )
        )
    return tuple(plans), MappingProxyType(owner)


def build_catalog_cohort(context) -> CatalogCohort:
    """Read the three catalogue contracts plus ``groups`` and derive the cohort."""

    lessons = tuple(_lesson(legacy_pk, row) for legacy_pk, row in _projected_rows(context, LESSON_CATALOG_FIELDS))
    curriculum_rows = _projected_rows(context, CURRICULUM_CATALOG_FIELDS)
    raw_plan_rows = _projected_rows(context, CURRICULUM_PLAN_FIELDS)
    # ``groups`` belongs to the structure phase; reading an UNCLAIMED table is
    # explicitly permitted (C-8) and is the only source of an admission year.
    years = _curriculum_years(_projected_rows(context, GROUP_STRUCTURE_FIELDS))
    scheme = context.policy.plan_semester_scheme
    plan_rows = _ranked(_plan_row(legacy_pk, row, scheme) for legacy_pk, row in raw_plan_rows)
    subjects, subject_owner = _subject_plans(lessons, plan_rows)
    # Two passes over the SAME tuple: T1-T3 resolve row by row, then T4 fills the
    # remainder from the neighbours the first pass dated (V-20).
    curricula = _dated_neighbour_years(tuple(_curriculum(legacy_pk, row, years) for legacy_pk, row in curriculum_rows))
    return CatalogCohort(
        lessons=lessons,
        subjects=subjects,
        subject_owner=subject_owner,
        curricula=curricula,
        plan_rows=plan_rows,
    )


__all__ = [
    "CATALOG_COHORT_MAX_ROWS",
    "DEFAULT_SUBJECT_ECTS",
    "ELECTIVE_REQUIRED_CHOICES",
    "MAX_SEMESTER_NUMBER",
    "PROGRAM_DURATION_BY_DEGREE",
    "SUBJECT_CODE_PREFIX",
    "CatalogCohort",
    "SourceCurriculum",
    "SourceLesson",
    "SourcePlanRow",
    "SubjectPlan",
    "build_catalog_cohort",
    "lesson_references",
    "plan_elective",
    "semester_number",
]

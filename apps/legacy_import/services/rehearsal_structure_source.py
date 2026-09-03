"""Source side of the ``academic_structure`` phase: stream, validate, derive.

Nothing here touches a Django model or writes a target row: the module turns the
three audited structure contracts into an immutable, fully classified cohort so
the phase module can spend its whole budget on ledger bookkeeping.  Every stream
repeats the identity phase's primary-key interlocks verbatim (type drift, range,
strict ascent, exact plan row count) because a structure table is accounted for
in the very same batch chain.

Program derivation runs only after all three tables are read, which makes it a
pure function of the cohort: the observed degree levels of a speciality's groups
decide how many ``registrar.Program`` rows that speciality needs, and code
allocation walks the specialities in ascending primary-key order so the result
never depends on how the source happened to be chunked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType

from core.constants import OrgUnitType

from .field_contracts import DEPARTMENT_STRUCTURE_FIELDS, GROUP_STRUCTURE_FIELDS, SPECIALITY_STRUCTURE_FIELDS
from .legacy_text import clean_code, clean_text
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_contracts import LegacyRehearsalConfigError, LegacyRehearsalEvidenceError, source_row_hash
from .source_extraction import open_audited_source_stream

STRUCTURE_COHORT_MAX_ROWS = 5_000
DEPARTMENT_TYPE_FACULTY = 3
DEPARTMENT_TYPE_CHAIR = 4
DEPARTMENT_TYPE_UNTYPED = 0
EDUCATION_FORM_BY_LEGACY = MappingProxyType({"əyani": "full_time", "qiyabi": "part_time"})
DEGREE_BY_LEGACY = MappingProxyType({"bak": "bachelor", "mag": "master"})
SECTOR_VALUES = frozenset({"az", "en", "ru"})
DEFAULT_DEGREE_LEVEL = "bachelor"
MASTER_DEGREE_LEVEL = "master"
ECTS_TOTAL_BY_DEGREE = MappingProxyType({DEFAULT_DEGREE_LEVEL: 240, MASTER_DEGREE_LEVEL: 120})
MIN_ADMISSION_YEAR = 1950
MAX_ADMISSION_YEAR = 2100
PROGRAM_CODE_MAX_LENGTH = 32  # registrar.Program.code
PROGRAM_BASE_CODE_MAX_LENGTH = 30  # leaves room for the two-character master suffix
MASTER_CODE_SUFFIX = "-M"
# V-1: a speciality code is "real" only when it is a bare six-digit DIM code.
# The live dump carries 31 blank codes and 24 "5555" dummies, so the collision
# suffix must stay the exception it was designed to be.
REAL_PROGRAM_CODE_PATTERN = re.compile(r"\d{6}\Z")
_UNIT_TYPE_BY_DEPARTMENT_TYPE = MappingProxyType(
    {DEPARTMENT_TYPE_FACULTY: OrgUnitType.FACULTY, DEPARTMENT_TYPE_CHAIR: OrgUnitType.CHAIR}
)
_NAME_MAX_LENGTH = 255  # OrgUnit.name
_UNIT_CODE_MAX_LENGTH = 50  # OrgUnit.code
_SECTOR_MAX_LENGTH = 2
_PROVENANCE_MAX_LENGTH = 64
_VALUE_TYPE_UNSUPPORTED = "legacy_rehearsal_source_value_type_unsupported"


@dataclass(frozen=True)
class SourceDepartment:
    """One ``departments`` row, already classified against §4.1."""

    legacy_pk: int
    source_row_hash: str
    name: str
    parent_legacy_pk: int
    type_id: int
    unit_type: str  # "" ⇒ the type is unknown and the row must be quarantined
    kollec_or_uni: str
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class SourceSpeciality:
    """One ``speciality`` row, already classified against §4.2."""

    legacy_pk: int
    source_row_hash: str
    name: str
    code: str
    parent_legacy_pk: int
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class SourceGroup:
    """One ``groups`` row, already classified against §4.4."""

    legacy_pk: int
    source_row_hash: str
    name: str
    speciality_legacy_pk: int
    department_legacy_pk: int
    sector: str
    education_form: str
    degree_level: str
    admission_year: int | None
    curricula_legacy_pk: int
    kollec_or_uni: str
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class ProgramPlan:
    """A derived ``registrar.Program``: one per (speciality, observed degree)."""

    speciality_legacy_pk: int
    degree_level: str
    code: str
    name: str
    ects_total: int
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class StructureCohort:
    """The whole phase input; every tuple is in a deterministic order."""

    departments: tuple[SourceDepartment, ...]  # ascending legacy_pk
    specialities: tuple[SourceSpeciality, ...]  # ascending legacy_pk
    groups: tuple[SourceGroup, ...]  # ascending legacy_pk
    programs: tuple[ProgramPlan, ...]  # (speciality_legacy_pk, degree_level)


def _projected_rows(context, contract) -> list:
    """Stream one contract in attested, strictly ascending primary-key order."""

    entry = context.plan.entry_for(contract.source_table)
    if entry.expected_rows > STRUCTURE_COHORT_MAX_ROWS:
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


def group_admission_year(value: object) -> tuple[int | None, tuple[str, ...]]:
    """MySQL ``YEAR(4)``: 0 is the NOT-NULL "no value" sentinel (§4.4).

    Public because the catalogue phase re-reads ``groups.start_year`` to back
    ``Curriculum.admission_year``; one implementation is what keeps the two
    phases from drifting apart on the same column.
    """

    year = _legacy_int(value) or None
    if year is not None and not MIN_ADMISSION_YEAR <= year <= MAX_ADMISSION_YEAR:
        return None, ("legacy_group_start_year_invalid",)
    return year, ()


def _named(value: object, legacy_pk: int, *, fallback: str, rule_codes: list[str]) -> str:
    name, truncated = clean_text(value, max_length=_NAME_MAX_LENGTH)
    if not name:
        rule_codes.append("legacy_structure_name_blank")
        return f"{fallback} {legacy_pk}"
    if truncated:
        rule_codes.append("legacy_structure_name_truncated")
    return name


def _provenance_text(value: object) -> str:
    text, _truncated = clean_text(value, max_length=_PROVENANCE_MAX_LENGTH)
    return text


def _department(legacy_pk: int, row) -> SourceDepartment:
    rule_codes: list[str] = []
    name = _named(row["name"], legacy_pk, fallback="Bölmə", rule_codes=rule_codes)
    type_id = _legacy_int(row["department_types_id"])
    unit_type = _UNIT_TYPE_BY_DEPARTMENT_TYPE.get(type_id, "")
    if not unit_type:
        if type_id == DEPARTMENT_TYPE_UNTYPED:
            # The four untyped roots must stay visible and keep their children.
            unit_type = OrgUnitType.FACULTY
            rule_codes.append("legacy_structure_department_type_nonstandard")
        else:
            rule_codes.append("legacy_structure_department_type_unknown")
    return SourceDepartment(
        legacy_pk=legacy_pk,
        source_row_hash=source_row_hash(contract=DEPARTMENT_STRUCTURE_FIELDS, legacy_pk=legacy_pk, projected_row=row),
        name=name,
        parent_legacy_pk=_legacy_int(row["department_id"]),
        type_id=type_id,
        unit_type=unit_type,
        kollec_or_uni=_provenance_text(row["kollec_or_uni"]),
        rule_codes=tuple(rule_codes),
    )


def _speciality(legacy_pk: int, row) -> SourceSpeciality:
    rule_codes: list[str] = []
    name = _named(row["name"], legacy_pk, fallback="İxtisas", rule_codes=rule_codes)
    # This is where the trailing "\t" pollution inside speciality_code dies.
    code, _truncated = clean_code(row["speciality_code"], max_length=_UNIT_CODE_MAX_LENGTH)
    return SourceSpeciality(
        legacy_pk=legacy_pk,
        source_row_hash=source_row_hash(contract=SPECIALITY_STRUCTURE_FIELDS, legacy_pk=legacy_pk, projected_row=row),
        name=name,
        code=code,
        parent_legacy_pk=_legacy_int(row["department_id"]),
        rule_codes=tuple(rule_codes),
    )


def _group(legacy_pk: int, row) -> SourceGroup:
    rule_codes: list[str] = []
    name = _named(row["name"], legacy_pk, fallback="Qrup", rule_codes=rule_codes)
    sector, _truncated = clean_code(row["sector"], max_length=_SECTOR_MAX_LENGTH)
    sector = sector.lower()
    if sector and sector not in SECTOR_VALUES:
        rule_codes.append("legacy_group_sector_unknown")
        sector = ""
    form_text = _provenance_text(row["eyani_qiyabi"]).casefold()
    education_form = EDUCATION_FORM_BY_LEGACY.get(form_text, "")
    if form_text and not education_form:
        rule_codes.append("legacy_group_education_form_unknown")
    degree_level = DEGREE_BY_LEGACY.get(_provenance_text(row["bak_or_mag"]).casefold(), "")
    if not degree_level:
        degree_level = DEFAULT_DEGREE_LEVEL
        rule_codes.append("legacy_group_degree_level_defaulted")
    admission_year, year_rules = group_admission_year(row["start_year"])
    rule_codes.extend(year_rules)
    return SourceGroup(
        legacy_pk=legacy_pk,
        source_row_hash=source_row_hash(contract=GROUP_STRUCTURE_FIELDS, legacy_pk=legacy_pk, projected_row=row),
        name=name,
        speciality_legacy_pk=_legacy_int(row["speciality_id"]),
        department_legacy_pk=_legacy_int(row["department_id"]),
        sector=sector,
        education_form=education_form,
        degree_level=degree_level,
        admission_year=admission_year,
        curricula_legacy_pk=_legacy_int(row["curricula_id"]),
        kollec_or_uni=_provenance_text(row["kollec_or_uni"]),
        rule_codes=tuple(rule_codes),
    )


def _allocate_program_code(base: str, legacy_pk: int, degree_level: str, seen_codes: set[str]):
    """Allocate one column-safe program code against the running allocation set."""

    suffix = MASTER_CODE_SUFFIX if degree_level == MASTER_DEGREE_LEVEL else ""
    candidate = f"{base}{suffix}"[:PROGRAM_CODE_MAX_LENGTH]
    if candidate not in seen_codes:
        return candidate, ()
    candidate = f"{base}-{legacy_pk}{suffix}"[:PROGRAM_CODE_MAX_LENGTH]
    if candidate in seen_codes:
        raise LegacyRehearsalEvidenceError("legacy_program_code_unallocatable")
    return candidate, ("legacy_program_code_collision",)


def _program_plans(specialities, groups) -> tuple[ProgramPlan, ...]:
    """One program per (speciality, observed degree level) — see D-5 and V-1."""

    degrees_by_speciality: dict[int, set[str]] = {}
    for group in groups:
        degrees_by_speciality.setdefault(group.speciality_legacy_pk, set()).add(group.degree_level)
    plans: list[ProgramPlan] = []
    seen_codes: set[str] = set()
    for speciality in specialities:
        shared_rules: list[str] = []
        degrees = sorted(degrees_by_speciality.get(speciality.legacy_pk, ()))
        if not degrees:
            degrees = [DEFAULT_DEGREE_LEVEL]
            shared_rules.append("legacy_speciality_without_groups")
        base, truncated = clean_code(speciality.code, max_length=PROGRAM_BASE_CODE_MAX_LENGTH)
        if truncated:
            # A code too long for the column is exactly a code that cannot be
            # real under V-1; the issue records why the fallback was taken.
            shared_rules.append("legacy_program_code_truncated")
        if not REAL_PROGRAM_CODE_PATTERN.fullmatch(base):
            base = f"MYEDU-{speciality.legacy_pk}"
        for degree_level in degrees:
            code, allocation_rules = _allocate_program_code(base, speciality.legacy_pk, degree_level, seen_codes)
            seen_codes.add(code)
            plans.append(
                ProgramPlan(
                    speciality_legacy_pk=speciality.legacy_pk,
                    degree_level=degree_level,
                    code=code,
                    name=speciality.name,
                    ects_total=ECTS_TOTAL_BY_DEGREE[degree_level],
                    rule_codes=(*shared_rules, *allocation_rules),
                )
            )
    return tuple(plans)


def build_structure_cohort(context) -> StructureCohort:
    """Read the three structure contracts and derive the program catalogue."""

    departments = tuple(
        _department(legacy_pk, row) for legacy_pk, row in _projected_rows(context, DEPARTMENT_STRUCTURE_FIELDS)
    )
    specialities = tuple(
        _speciality(legacy_pk, row) for legacy_pk, row in _projected_rows(context, SPECIALITY_STRUCTURE_FIELDS)
    )
    groups = tuple(_group(legacy_pk, row) for legacy_pk, row in _projected_rows(context, GROUP_STRUCTURE_FIELDS))
    return StructureCohort(
        departments=departments,
        specialities=specialities,
        groups=groups,
        programs=_program_plans(specialities, groups),
    )


__all__ = [
    "DEGREE_BY_LEGACY",
    "ECTS_TOTAL_BY_DEGREE",
    "EDUCATION_FORM_BY_LEGACY",
    "SECTOR_VALUES",
    "STRUCTURE_COHORT_MAX_ROWS",
    "ProgramPlan",
    "SourceDepartment",
    "SourceGroup",
    "SourceSpeciality",
    "StructureCohort",
    "build_structure_cohort",
    "group_admission_year",
]

"""ATİS «Bakalavr» ixracının sətirləri → doldurma dəyərləri (YAZMIR).

Oxuma və dəyər tərcüməsi ``import_students_atis`` ilə EYNİ yoldur: ``intake.read_rows`` (başlıq xəritəsi) +
``intake.admission.enrich`` (qəbul sahələri) + ``intake.validate``-in tarix / cins / telefon normallaşdırması —
ATİS-dən gələn dəyər hər iki axında eyni formada yazılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from core.validators import validate_fin

from ..intake import admission, read_rows
from ..intake.parsing import IntakeFileError
from ..intake.validate import RowPlan, _normalized_phone, _parse_date, _parse_gender, _text
from .scope import person_key

#: Profil sahəsi → ATİS dəyərinin açarı (yalnız mətn sahələri; boş sətir = «boş»).
PROFILE_TEXT_FIELDS = (
    ("patronymic", "patronymic", 150),
    ("phone", "phone", 20),
    ("citizenship", "citizenship", 64),
    ("id_document_series", "id_series", 8),
    ("id_document_number", "id_number", 32),
    ("location", "address", 100),
)
#: Qeyd (``StudentAcademicRecord``) sahələri: boş = ``""`` / ``None`` / ``{}``.
RECORD_FIELDS = (
    "atis_id",
    "admission_score",
    "admission_exam_type",
    "admission_channel",
    "admission_tour",
    "instruction_language",
    "tuition_fee",
    "applied_at",
    "admitted_at",
    "admission_note",
    "admission_extra",
)


class AtisFileError(Exception):
    """Faylın oxunmaması (sabit kod)."""


class _Upload:
    """``intake.read_rows`` üçün minimal fayl obyekti (ad + ölçü + read)."""

    def __init__(self, path: Path):
        self.name = path.name
        self.size = path.stat().st_size
        self._path = path

    def read(self) -> bytes:
        return self._path.read_bytes()


@dataclass
class AtisRow:
    index: int
    fin: str
    name_key: tuple
    program_code: str
    language: str
    speciality: str
    specialization: str
    education_form: str
    email: str = ""
    birth_date: object = None
    gender: str = "unspecified"
    profile: dict = field(default_factory=dict)
    record: dict = field(default_factory=dict)


def _valid_fin(value: str) -> str:
    try:
        validate_fin(value)
    except ValidationError:
        return ""
    return value


def _valid_email(value: str) -> str:
    if not value:
        return ""
    try:
        validate_email(value)
    except ValidationError:
        return ""
    return value


def parse_row(index: int, raw: dict) -> AtisRow:
    plan = RowPlan(row=index)
    admission.enrich(plan, raw, None)
    birth, ok = _parse_date(raw.get("birth_date"))
    gender, _ok = _parse_gender(raw.get("gender"))
    values = {
        "patronymic": _text(raw.get("patronymic")),
        "phone": _normalized_phone(raw.get("phone")),
        "citizenship": plan.values.get("citizenship", ""),
        "id_series": plan.values.get("id_series", ""),
        "id_number": plan.values.get("id_number", ""),
        "address": plan.values.get("address", ""),
    }
    row = AtisRow(
        index=index,
        fin=_valid_fin(_text(raw.get("fin")).upper()),
        name_key=person_key(raw.get("last_name"), raw.get("first_name"), raw.get("patronymic")),
        program_code=_text(raw.get("program_code")),
        language=_text(raw.get("language_sector")),
        speciality=_text(raw.get("speciality")),
        specialization=_text(raw.get("specialization")),
        education_form=plan.values.get("education_form", ""),
        email=_valid_email(_text(raw.get("email"))),
        birth_date=birth if ok else None,
        gender=gender,
    )
    row.profile = {
        target: str(values[source] or "")[:limit] for target, source, limit in PROFILE_TEXT_FIELDS if values[source]
    }
    row.record = {name: plan.values.get(name) for name in RECORD_FIELDS}
    return row


def load_rows(path) -> list:
    path = Path(path)
    if not path.is_file():
        raise AtisFileError("atis_file_not_found")
    try:
        raw_rows = read_rows(_Upload(path))
    except IntakeFileError as exc:
        raise AtisFileError(f"atis_file_unreadable_{exc.code}") from None
    return [parse_row(int(raw.get("_row") or position), raw) for position, raw in enumerate(raw_rows, start=2)]


__all__ = ["AtisFileError", "AtisRow", "PROFILE_TEXT_FIELDS", "RECORD_FIELDS", "load_rows", "parse_row"]

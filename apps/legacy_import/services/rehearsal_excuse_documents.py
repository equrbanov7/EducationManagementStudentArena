"""J13 mənbə qatı: ``allowed_qb`` → ``registrar.LegacyExcuseDocument``.

Bu modul YALNIZ oxuyur, təmizləyir, qərar verir və hədəfi materiallaşdırır;
faza mühasibatı (ledger, digest zənciri, hesabat) ``rehearsal_excuse_documents
_phase``-dədir.

Mənbə faktı (canlı repetisiya bazasında ölçülüb)
-----------------------------------------------
* 2,964 sətir · 1,130 tələbə · 4 göndərən (``owner_id``) · 977 sənəd paketi
  (``uniq``) · 773 fərqli fayl adı;
* fayl adı HƏR sətirdə var (``1697461819.jpg`` — vaxt möhürü + uzantı), izah
  mətni 2,927 sətirdə;
* 8 sətrin ``student_id``-si ``students`` cədvəlində YOXDUR;
* ``allowed_date_end < allowed_date_start`` olan sətir YOXDUR (0);
* aralıq 1 gündən 369 günə qədərdir, 916 sətir çoxgünlükdür.

``uniq`` jurnal ``uniqid``-i DEYİL — bir imzalanmış aktın öz açarıdır: eyni
sənəd bir neçə tələbəyə aiddirsə sətirlər eyni ``uniq`` VƏ eyni ``file``
daşıyır (məs. «Texnopark» aktı 2 tələbəyə).  Ona görə hədəfdə o, qruplaşdırma
istinadıdır (``source_batch_ref``), FK deyil.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import transaction

from .excuse_field_contracts import ALLOWED_QB_DOCUMENT_FIELDS
from .legacy_text import clean_multiline_text, clean_text
from .rehearsal_contracts import (
    SOURCE_SYSTEM,
    LegacyRehearsalEvidenceError,
    RehearsalContext,
    encoded_part,
    stable_source_value,
)
from .rehearsal_journal_batch import normalized_key
from .rehearsal_journal_offerings_source import legacy_int
from .rehearsal_journal_points_source import attested_rows

EXCUSE_ENTITY_TYPE = "legacy_excuse_document"
EXCUSE_SOURCE_TABLE = ALLOWED_QB_DOCUMENT_FIELDS.source_table
EXCUSE_MODEL_APP = "registrar"
EXCUSE_MODEL_NAME = "LegacyExcuseDocument"

#: Fayl adı köhnə serverdə birbaşa yol hissəsi kimi işlədilir; ona görə yalnız
#: təhlükəsiz forma qəbul olunur (``1697461819.jpg``).  Uyğun gəlməyən ad
#: SAXLANMIR, sətir isə yenə köçürülür — qeyd itmir, uydurma da olmur.
_DOCUMENT_NAME_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_NOTE_MAX_LENGTH = 2000
_BATCH_REF_MAX_LENGTH = 32
_DOCUMENT_NAME_MAX_LENGTH = 64

_STATUS_LINKED = "linked"
_STATUS_STUDENT_UNRESOLVED = "student_unresolved"
_STATUS_WINDOW_INVALID = "window_invalid"

# Taksonomiya — hamısı bloklamayan müşahidədir: bu faza heç bir sətri ATMIR.
RULE_STUDENT_UNRESOLVED = "legacy_excuse_student_unresolved"
RULE_WINDOW_INVALID = "legacy_excuse_window_invalid"
RULE_DOCUMENT_ABSENT = "legacy_excuse_document_absent"
RULE_DOCUMENT_NAME_INVALID = "legacy_excuse_document_name_invalid"
RULE_NOTE_EMPTY = "legacy_excuse_note_empty"
RULE_NOTE_TRUNCATED = "legacy_excuse_note_truncated"


EXCUSE_SOURCE_ROW_DIGEST_NAMESPACE = b"legacy-excuse-source-row-v1\x00"
EXCUSE_MATERIALIZATION_DIGEST_NAMESPACE = b"legacy-excuse-materialization-v1\x00"


def excuse_source_row_hash(*, legacy_pk: int, row) -> str:
    """Bir ``allowed_qb`` sətrinin kontrakt sırasında sabit hash-i."""

    digest = hashlib.sha256(EXCUSE_SOURCE_ROW_DIGEST_NAMESPACE)
    for part in (
        ALLOWED_QB_DOCUMENT_FIELDS.fingerprint,
        ALLOWED_QB_DOCUMENT_FIELDS.source_table,
        str(legacy_pk),
    ):
        digest.update(encoded_part(part))
    for field_name in ALLOWED_QB_DOCUMENT_FIELDS.allowed_fields:
        digest.update(encoded_part(field_name))
        digest.update(encoded_part(stable_source_value(row[field_name])))
    return digest.hexdigest()


def excuse_materialization_digest(*, natural_key: tuple, source_row_hash: str, payload) -> str:
    """Cross-run sabit qərar möhürü.

    Hədəf UUID-si (``student_id``) payload-a QƏSDƏN girmir: hədəf açarları hər
    təmiz repetisiyada yenidən yaranır, ona görə möhür yalnız mənbə-sabit
    dəyərlərdən qurulur.
    """

    digest = hashlib.sha256(EXCUSE_MATERIALIZATION_DIGEST_NAMESPACE)
    for part in natural_key:
        digest.update(encoded_part(str(part)))
    digest.update(encoded_part(source_row_hash))
    for key in sorted(payload):
        digest.update(encoded_part(key))
        digest.update(encoded_part(stable_source_value(payload[key])))
    return digest.hexdigest()


def excuse_rows(context: RehearsalContext):
    return attested_rows(
        context,
        contract=ALLOWED_QB_DOCUMENT_FIELDS,
        source_table=EXCUSE_SOURCE_TABLE,
    )


def _legacy_datetime(value: object) -> datetime.datetime | None:
    """``DATETIME`` sütunu; başqa tip səssiz çevrilmir — pəncərə yararsızdır."""

    return value if type(value) is datetime.datetime else None


def _window_text(start: object, end: object) -> str:
    parts = []
    for value in (start, end):
        moment = _legacy_datetime(value)
        parts.append(moment.isoformat(sep=" ") if moment is not None else "")
    return "|".join(parts)[:64]


def _recorded_at_text(value: object) -> str:
    moment = _legacy_datetime(value)
    return moment.isoformat(sep=" ")[:32] if moment is not None else ""


def _document_name(value: object) -> tuple[str, tuple[str, ...]]:
    text, _truncated = clean_text(value, max_length=_DOCUMENT_NAME_MAX_LENGTH)
    text = text.replace(" ", "")
    if not text:
        return "", (RULE_DOCUMENT_NAME_INVALID,)
    if not _DOCUMENT_NAME_PATTERN.fullmatch(text):
        return "", (RULE_DOCUMENT_NAME_INVALID,)
    return text, ()


@dataclass(frozen=True)
class ExcuseRequest:
    """Bir ``allowed_qb`` sətrinin tam həll olunmuş hədəf forması."""

    source_pk: int
    source_row_hash: str
    payload: dict[str, object]
    student_target_pk: str
    rule_codes: tuple[str, ...]

    @property
    def seal_key(self) -> str:
        return f"{EXCUSE_SOURCE_TABLE}:{self.source_pk}"

    @property
    def natural_key(self) -> tuple:
        return (SOURCE_SYSTEM, EXCUSE_SOURCE_TABLE, self.source_pk)


def build_request(*, legacy_pk: int, row, students) -> ExcuseRequest:
    """Bir mənbə sətrini qərara çevir; heç bir sətir ATILMIR.

    Tələbə tapılmasa və ya tarix aralığı yararsız olsa sətir yenə saxlanır —
    yalnız ``mapping_status`` və issue kodları fərqlənir (sahibin qaydası:
    köhnə data itmir).
    """

    codes: list[str] = []
    start = _legacy_datetime(row["allowed_date_start"])
    end = _legacy_datetime(row["allowed_date_end"])
    window_ok = start is not None and end is not None and end.date() >= start.date()
    if not window_ok:
        codes.append(RULE_WINDOW_INVALID)

    source_student_ref = str(legacy_int(row["student_id"]))
    student_target_pk = students.get(source_student_ref, "")
    if not student_target_pk:
        codes.append(RULE_STUDENT_UNRESOLVED)

    note, truncated = clean_multiline_text(row["desc"], max_length=_NOTE_MAX_LENGTH)
    if truncated:
        codes.append(RULE_NOTE_TRUNCATED)
    if not note:
        codes.append(RULE_NOTE_EMPTY)

    document_name, name_codes = _document_name(row["file"])
    codes.extend(name_codes)
    # Faylın ÖZÜ hədəfdə yoxdur (köhnə serverdə qalıb) — hər sətir bunu açıq
    # bəyan edir ki, hesabatda "2,964 sənəd gözlənilir" rəqəmi görünsün.
    codes.append(RULE_DOCUMENT_ABSENT)

    if not window_ok:
        mapping_status = _STATUS_WINDOW_INVALID
    elif not student_target_pk:
        mapping_status = _STATUS_STUDENT_UNRESOLVED
    else:
        mapping_status = _STATUS_LINKED

    batch_ref, _ = clean_text(row["uniq"], max_length=_BATCH_REF_MAX_LENGTH)
    payload: dict[str, object] = {
        "mapping_status": mapping_status,
        "source_student_ref": source_student_ref,
        "source_owner_ref": str(legacy_int(row["owner_id"])),
        "source_batch_ref": batch_ref.replace(" ", ""),
        "starts_on_text": start.date().isoformat() if window_ok else "",
        "ends_on_text": end.date().isoformat() if window_ok else "",
        "source_window_text": _window_text(row["allowed_date_start"], row["allowed_date_end"]),
        "source_recorded_at_text": _recorded_at_text(row["added_date"]),
        "note": note,
        "document_name": document_name,
    }
    return ExcuseRequest(
        source_pk=legacy_pk,
        source_row_hash=excuse_source_row_hash(legacy_pk=legacy_pk, row=row),
        payload=payload,
        # Bağlanmamış sətir kanonik tələbəyə BAĞLANMIR (modelin ``clean``
        # qaydası ilə eyni) — yalnız mənbə istinadı qalır.
        student_target_pk=student_target_pk if mapping_status == _STATUS_LINKED else "",
        rule_codes=tuple(codes),
    )


def excuse_requests(context: RehearsalContext, *, rows, students):
    for legacy_pk, row in rows:
        yield build_request(legacy_pk=legacy_pk, row=row, students=students)


class LegacyExcuseMaterialiser:
    """Təbii açar → ``LegacyExcuseDocument`` pk (toplu, idempotent).

    Mövcud sətir tapılırsa ÜSTÜNDƏN YAZILMIR: yalnız materializasiya möhürü
    tutuşdurulur, uyğunsuzluq fail-closed olur.  Beləliklə təkrar icra heç bir
    dəyəri dəyişmir və sonradan qoşulmuş fayl da silinmir.
    """

    def __init__(self) -> None:
        self._payloads: dict[tuple[str, ...], dict[str, object]] = {}
        self._students: dict[tuple[str, ...], str] = {}

    def stage(self, natural_key: tuple, payload: dict[str, object], *, student_target_pk: str) -> None:
        key = normalized_key(natural_key)
        if key in self._payloads:
            raise LegacyRehearsalEvidenceError("legacy_excuse_batch_duplicate")
        self._payloads[key] = dict(payload)
        self._students[key] = student_target_pk

    def _model_kwargs(self, payload: dict[str, object], student_target_pk: str) -> dict[str, object]:
        values = dict(payload)
        starts = values.pop("starts_on_text")
        ends = values.pop("ends_on_text")
        values["starts_on"] = datetime.date.fromisoformat(starts) if starts else None
        values["ends_on"] = datetime.date.fromisoformat(ends) if ends else None
        values["student_id"] = student_target_pk or None
        return values

    def resolve(self, context, keys) -> dict[tuple[str, ...], str]:
        ordered = list(dict.fromkeys(keys))
        if not ordered:
            return {}
        wanted = {normalized_key(key) for key in ordered}
        model = django_apps.get_model(EXCUSE_MODEL_APP, EXCUSE_MODEL_NAME)
        rows = model.objects.filter(
            organization=context.organization,
            source_system__in={key[0] for key in ordered},
            source_table__in={key[1] for key in ordered},
            source_pk__in={key[2] for key in ordered},
        ).values_list("pk", "source_system", "source_table", "source_pk", "materialization_digest")
        resolved: dict[tuple[str, ...], str] = {}
        for pk, source_system, source_table, source_pk, digest in rows:
            key = normalized_key((source_system, source_table, source_pk))
            if key not in wanted:
                continue
            payload = self._payloads.get(key)
            if payload is None or digest != payload["materialization_digest"]:
                raise LegacyRehearsalEvidenceError("legacy_excuse_identity_conflict")
            resolved[key] = str(pk)

        missing = [key for key in ordered if normalized_key(key) not in resolved]
        if missing:
            pending = []
            for source_system, source_table, source_pk in missing:
                key = normalized_key((source_system, source_table, source_pk))
                payload = self._payloads.get(key)
                if payload is None:
                    raise LegacyRehearsalEvidenceError("legacy_excuse_payload_missing")
                pending.append(
                    model(
                        organization=context.organization,
                        source_system=source_system,
                        source_table=source_table,
                        source_pk=source_pk,
                        **self._model_kwargs(payload, self._students.get(key, "")),
                    )
                )
            with transaction.atomic():
                model.objects.bulk_create(pending)
            for key, instance in zip(missing, pending):
                resolved[normalized_key(key)] = str(instance.pk)

        for key in wanted:
            self._payloads.pop(key, None)
            self._students.pop(key, None)
        return resolved


__all__ = [
    "EXCUSE_ENTITY_TYPE",
    "EXCUSE_MODEL_APP",
    "EXCUSE_MODEL_NAME",
    "EXCUSE_SOURCE_TABLE",
    "RULE_DOCUMENT_ABSENT",
    "RULE_DOCUMENT_NAME_INVALID",
    "RULE_NOTE_EMPTY",
    "RULE_NOTE_TRUNCATED",
    "RULE_STUDENT_UNRESOLVED",
    "RULE_WINDOW_INVALID",
    "EXCUSE_MATERIALIZATION_DIGEST_NAMESPACE",
    "EXCUSE_SOURCE_ROW_DIGEST_NAMESPACE",
    "ExcuseRequest",
    "LegacyExcuseMaterialiser",
    "build_request",
    "excuse_requests",
    "excuse_materialization_digest",
    "excuse_rows",
    "excuse_source_row_hash",
]

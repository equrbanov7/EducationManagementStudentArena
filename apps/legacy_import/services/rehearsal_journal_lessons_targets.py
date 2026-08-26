"""Target side of ``journal_lessons`` (J3): seal-lar və Lesson yazısı.

Bir invariant buranındır: hədəf (``Lesson``) və onu hesaba alan ledger
müşahidəsi BİR ``transaction.atomic()`` içində bağlanır — yarımçıq cəhd
ledger-siz dərs qoya bilməz, resume isə yazılmış müşahidədə qısa-qapanır.

``gradebook.create_lesson`` semantikası qəsdən burada güzgülənir:
``apps.registrar.gradebook`` importu modul-sərhəd qrafına yeni
``legacy_import → registrar`` tili açardı (J1-dəki ``ensure_assessment_scheme``
qərarı ilə eyni səbəb).  Servisin invariantları bunlardır və hamısı qorunur:

* jurnal kilidi — J7-dən əvvəl heç bir sxem approved/published deyil (J1
  sxemləri DRAFT yaradır), yəni kilid struktur olaraq mümkün deyil;
* keçmiş-tarix rəddi — import məhz ``allow_past=True`` semantikasıdır (spec);
* eyni gün/saat toqquşması — servisdəki ``exists()`` yoxlaması burada
  ``(organization, offering, date, start_time)`` üzərində ``get_or_create``
  açarıdır: V7 merge nəticəsində eyni offering-ə qatlanan jurnalların eyni
  slotu EYNİ dərsə birləşir, dublikat yaranmır;
* ``ensure_assessment_scheme`` — J1 hər offering üçün sxemi artıq yaradıb;
* defoltlar — ``kind=lecture``, ``hours=2`` (spec J3), ``instructor`` açılışın
  müəllimi, ``created_by=None`` (import heç kimin adından yazmır).
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .field_contracts import JOURNAL_DATES_FIELDS
from .ledger import upsert_entity_map, upsert_issue
from .rehearsal_authorizer import LESSON_MODEL_LABEL
from .rehearsal_contracts import LegacyRehearsalEvidenceError, encoded_part

LESSON_ENTITY_TYPE = "lesson"
LESSON_SOURCE_TABLE = "journals_dates_added_by_teacher"

_DERIVATION_PREFIX = b"legacy-rehearsal-journal-lesson-derivation-v1\x00"
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State

# E-13: heç nə ERROR deyil — ilk jurnal rehearsal-ı tam histoqram verməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        # Törədilmiş il ilə qurula bilməyən tarix / "HH:MM" olmayan saat.
        "legacy_journal_lesson_invalid": _SEVERITY.WARNING,
        **dict.fromkeys(
            (
                # Spec J3: jurnal tapılmır və ya V6/karantinlə süzülüb.
                "legacy_journal_lesson_orphan",
                # Mənbədə eyni (jurnal, tarix, saat) slotu təkrarlanır —
                # ilk sətir (ən kiçik id) udur, qalanları qeydli SKIPPED.
                "legacy_journal_lesson_duplicate",
            ),
            _SEVERITY.INFO,
        ),
    }
)


@dataclass(frozen=True)
class LessonRequest:
    """Bir dərs sətrinin yazısı üçün lazım olan hər şey — həll bitib."""

    legacy_pk: int
    row_hash: str
    offering_pk: str
    instructor_pk: str  # "" → instructor=NULL (açılış müəlliminin güzgüsü)
    journal_ref: str
    date: datetime.date  # törədilmiş il daxil
    start_time: datetime.time

    @property
    def date_text(self) -> str:
        return self.date.isoformat()

    @property
    def time_text(self) -> str:
        return self.start_time.isoformat(timespec="minutes")


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def lesson_derivation_hash(
    *,
    legacy_pk: int,
    row_hash: str,
    outcome_token: str,
    journal_ref: str,
    date_text: str,
    time_text: str,
) -> str:
    """Cross-run-sabit dərs qərar kimliyi; heç bir UUID/target pk daxil olmur."""

    digest = hashlib.sha256(_DERIVATION_PREFIX)
    for part in (
        JOURNAL_DATES_FIELDS.fingerprint,
        str(legacy_pk),
        row_hash,
        outcome_token,
        journal_ref,
        date_text,
        time_text,
    ):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def recorded_decision(context, legacy_pk: str):
    """Resume qısayolu: möhürlənmiş qərarı yenidən törətmək əvəzinə oxu."""

    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            entity_map__entity_type=LESSON_ENTITY_TYPE,
            entity_map__legacy_pk=legacy_pk,
        )
        .values_list("state", "source_row_hash", "target_model_label")
        .first()
    )


def _seal(context, *, legacy_pk: str, digest: str, state: str, label: str = "", target_pk: str = ""):
    return upsert_entity_map(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        entity_type=LESSON_ENTITY_TYPE,
        legacy_pk=legacy_pk,
        source_row_hash=digest,
        state=state,
        target_model_label=label,
        target_pk=target_pk,
        target_validators=context.target_validators,
    )


def write_issue(context, *, legacy_pk: str, rule_code: str, digest: str, entity_map, issue_counts) -> None:
    """Issue həmişə öz map-ından sonra: ledger əks sıranı rədd edir."""

    severity = severity_for(rule_code)
    upsert_issue(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        source_table=LESSON_SOURCE_TABLE,
        entity_type=LESSON_ENTITY_TYPE,
        legacy_pk=legacy_pk,
        rule_code=rule_code,
        severity=severity,
        payload_digest=digest,
        entity_map_id=entity_map.pk,
    )
    issue_counts[(rule_code, severity)] += 1


def seal_skipped(
    context,
    *,
    legacy_pk: int,
    row_hash: str,
    rule_code: str,
    outcome_token: str,
    journal_ref: str,
    date_text: str = "",
    time_text: str = "",
    issue_counts,
):
    """Orphan/dublikat — SKIPPED; sətir ledger-də qalır, mənbədə heç nə silinmir."""

    digest = lesson_derivation_hash(
        legacy_pk=legacy_pk,
        row_hash=row_hash,
        outcome_token=outcome_token,
        journal_ref=journal_ref,
        date_text=date_text,
        time_text=time_text,
    )
    key = str(legacy_pk)
    entity_map = _seal(context, legacy_pk=key, digest=digest, state=_STATE.SKIPPED)
    write_issue(
        context, legacy_pk=key, rule_code=rule_code, digest=digest, entity_map=entity_map, issue_counts=issue_counts
    )
    return _STATE.SKIPPED, digest, ""


def seal_invalid(context, *, legacy_pk: int, row_hash: str, journal_ref: str, issue_counts):
    """Tarix/saat qurula bilmir — QUARANTINED, target yazısı yoxdur (data qorunur)."""

    digest = lesson_derivation_hash(
        legacy_pk=legacy_pk,
        row_hash=row_hash,
        outcome_token="invalid",
        journal_ref=journal_ref,
        date_text="",
        time_text="",
    )
    key = str(legacy_pk)
    entity_map = _seal(context, legacy_pk=key, digest=digest, state=_STATE.QUARANTINED)
    write_issue(
        context,
        legacy_pk=key,
        rule_code="legacy_journal_lesson_invalid",
        digest=digest,
        entity_map=entity_map,
        issue_counts=issue_counts,
    )
    return _STATE.QUARANTINED, digest, ""


def materialise_lesson(context, *, request: LessonRequest):
    """Lesson + ledger möhürü BİR unit of work içində (modul qeydindəki güzgü).

    Materialised sətrin issue-su yoxdur — map onsuz da hədəfi göstərir.
    """

    lesson_model = django_apps.get_model("registrar", "Lesson")
    with transaction.atomic():
        lesson, _created = lesson_model.objects.get_or_create(
            organization=context.organization,
            offering_id=request.offering_pk,
            date=request.date,
            start_time=request.start_time,
            defaults={
                # Spec J3: kind defolt lecture, hours defolt 2 (A.3, V2).
                "kind": "lecture",
                "hours": 2,
                "topic": "",
                "instructor_id": request.instructor_pk or None,
                "created_by": None,
            },
        )
        digest = lesson_derivation_hash(
            legacy_pk=request.legacy_pk,
            row_hash=request.row_hash,
            outcome_token="materialised",
            journal_ref=request.journal_ref,
            date_text=request.date_text,
            time_text=request.time_text,
        )
        _seal(
            context,
            legacy_pk=str(request.legacy_pk),
            digest=digest,
            state=_STATE.MIGRATED,
            label=LESSON_MODEL_LABEL,
            target_pk=str(lesson.pk),
        )
    return _STATE.MIGRATED, digest, LESSON_MODEL_LABEL

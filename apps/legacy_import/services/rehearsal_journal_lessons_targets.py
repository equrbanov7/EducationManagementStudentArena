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
  açarıdır: C6 birləşməsində eyni offering-ə qatlanan jurnalların eyni slotu
  EYNİ dərsə birləşir, dublikat yaranmır;
* 2026-08-28 (qrup-başına jurnal) — bir legacy dərs sətri jurnalın HƏR qrup
  dilimə TƏKRARLANIR, ona görə möhür açarı ``<legacy_pk>:<qrup>``dur;
* ``ensure_assessment_scheme`` — J1 hər offering üçün sxemi artıq yaradıb;
* defoltlar — ``kind=lecture``, ``hours=2`` (spec J3), ``instructor`` açılışın
  müəllimi, ``created_by=None`` (import heç kimin adından yazmır).
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .field_contracts import JOURNAL_DATES_FIELDS
from .rehearsal_authorizer import LESSON_MODEL_LABEL
from .rehearsal_contracts import LegacyRehearsalEvidenceError, encoded_part
from .rehearsal_journal_batch import Decision, TargetMaterialiser, normalized_key
from .rehearsal_journal_lesson_kinds import ABSENT_RULE_CODE, CONFLICT_RULE_CODE, LECTURE

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
                # Slotun HEÇ bir xanası yoxdur → növ törədilə bilmir, defolt
                # ``lecture`` qalır (dərsin özü yenə materiallaşır).
                ABSENT_RULE_CODE,
                # Slotun xanaları qarışıq növ daşıyır → əksəriyyət qazanır.
                CONFLICT_RULE_CODE,
            ),
            _SEVERITY.INFO,
        ),
    }
)


@dataclass(frozen=True)
class LessonRequest:
    """Bir dərs sətrinin yazısı üçün lazım olan hər şey — həll bitib."""

    legacy_pk: int
    seal_key: str  # ``<legacy_pk>:<qrup>`` — dilim başına bir möhür
    slice_ref: str  # dilimin legacy qrup pk-sı
    row_hash: str
    offering_pk: str
    journal_ref: str
    date: datetime.date  # törədilmiş il daxil
    start_time: datetime.time
    # Xanalardan törədilmiş dərs növü + onu müşayiət edən INFO kodu (boş = təmiz
    # əksəriyyət).  Bax ``rehearsal_journal_lesson_kinds``.
    kind: str = LECTURE
    kind_rule_code: str = ""

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
    slice_ref: str = "",
    kind: str = "",
) -> str:
    """Cross-run-sabit dərs qərar kimliyi; heç bir UUID/target pk daxil olmur.

    ``kind`` də qərarın bir hissəsidir: eyni slot üçün törədilmiş növ dəyişsə,
    möhür də dəyişməlidir — əks halda ledger köhnə qərarı təsdiqləmiş olardı.
    """

    digest = hashlib.sha256(_DERIVATION_PREFIX)
    for part in (
        JOURNAL_DATES_FIELDS.fingerprint,
        str(legacy_pk),
        row_hash,
        outcome_token,
        journal_ref,
        date_text,
        time_text,
        slice_ref,
        kind,
    ):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def recorded_decisions(context) -> dict[str, tuple[str, str, str]]:
    """Bu run-un BÜTÜN dərs möhürləri — resume üçün BİR sorğu.

    Əvvəl hər sətir üçün ayrıca ``.first()`` gedirdi (379 215 sorğu); açar sayı
    dərs cədvəlinin ölçüsündədir və indeks yaddaşa sığır.
    """

    rows = LegacyEntityObservation.objects.filter(
        run_id=context.run_id, entity_map__entity_type=LESSON_ENTITY_TYPE
    ).values_list("entity_map__legacy_pk", "state", "source_row_hash", "target_model_label")
    return {
        legacy_pk: (state, row_hash, label) for legacy_pk, state, row_hash, label in rows.iterator(chunk_size=10_000)
    }


def lesson_materialiser(instructors: Mapping[str, str], kinds: Mapping[tuple[str, ...], str]) -> TargetMaterialiser:
    """``gradebook.create_lesson`` defoltlarının toplu güzgüsü (modul qeydi).

    Açar ``(offering, tarix, saat)``-dır: V7 merge-də eyni offering-ə qatlanan
    jurnalların eyni slotu EYNİ dərsə birləşir — servisdəki ``exists()``
    yoxlamasının dəqiq qarşılığı.

    ``kinds`` həmin açar üzrə törədilmiş dərs növüdür (J3 fazası doldurur);
    açar tapılmasa defolt ``lecture`` qalır.
    """

    def _defaults(key):
        normalized = normalized_key(key)
        return {
            "instructor_id": instructors.get(str(key[0]), "") or None,
            "kind": kinds.get(normalized, LECTURE),
        }

    return TargetMaterialiser(
        app_label="registrar",
        model_name="Lesson",
        key_fields=("offering_id", "date", "start_time"),
        # Spec J3: hours defolt 2 (A.3, V2); ``created_by=None`` — import heç
        # kimin adından yazmır.  ``kind`` ARTIQ defolt deyil, xanalardan
        # törədilir (bax ``rehearsal_journal_lesson_kinds``) — tapılmayan slot
        # üçün ``_defaults`` yenə ``lecture`` verir.
        defaults=MappingProxyType({"kind": LECTURE, "hours": 2, "topic": "", "created_by": None}),
        defaults_for=_defaults,
    )


def skipped_decision(
    *,
    legacy_pk: int,
    row_hash: str,
    rule_code: str,
    outcome_token: str,
    journal_ref: str,
    date_text: str = "",
    time_text: str = "",
    seal_key: str = "",
    slice_ref: str = "",
) -> Decision:
    """Orphan/dublikat — SKIPPED; sətir ledger-də qalır, mənbədə heç nə silinmir."""

    return Decision(
        seal_key=seal_key or str(legacy_pk),
        state=_STATE.SKIPPED,
        digest=lesson_derivation_hash(
            legacy_pk=legacy_pk,
            row_hash=row_hash,
            outcome_token=outcome_token,
            journal_ref=journal_ref,
            date_text=date_text,
            time_text=time_text,
            slice_ref=slice_ref,
        ),
        rule_codes=(rule_code,),
    )


def invalid_decision(*, legacy_pk: int, row_hash: str, journal_ref: str) -> Decision:
    """Tarix/saat qurula bilmir — QUARANTINED, target yazısı yoxdur (data qorunur)."""

    return Decision(
        seal_key=str(legacy_pk),
        state=_STATE.QUARANTINED,
        digest=lesson_derivation_hash(
            legacy_pk=legacy_pk,
            row_hash=row_hash,
            outcome_token="invalid",
            journal_ref=journal_ref,
            date_text="",
            time_text="",
        ),
        rule_codes=("legacy_journal_lesson_invalid",),
    )


def lesson_decision(*, request: LessonRequest) -> Decision:
    """Materialised dərs; hədəf açarı dəstə yazıcısına ötürülür.

    Materialised sətir yalnız dərs NÖVÜ təmiz törədilmədikdə issue daşıyır
    (xana yoxdur / xanalar qarışıqdır) — dərsin özü hər halda yazılır.
    """

    return Decision(
        seal_key=request.seal_key,
        state=_STATE.MIGRATED,
        digest=lesson_derivation_hash(
            legacy_pk=request.legacy_pk,
            row_hash=request.row_hash,
            outcome_token="materialised",
            journal_ref=request.journal_ref,
            date_text=request.date_text,
            time_text=request.time_text,
            slice_ref=request.slice_ref,
            kind=request.kind,
        ),
        label=LESSON_MODEL_LABEL,
        rule_codes=(request.kind_rule_code,) if request.kind_rule_code else (),
        natural_key=(request.offering_pk, request.date, request.start_time),
    )

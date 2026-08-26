"""Target side of ``journal_offerings`` (J1): seal-lar və offering yazısı.

Bir invariant buranındır: hədəf (``CourseOffering`` + onun draft
``AssessmentScheme``-i) və onu hesaba alan ledger müşahidəsi BİR
``transaction.atomic()`` içində bağlanır — yarımçıq cəhd ledger-siz offering
qoya bilməz, resume isə yazılmış müşahidədə qısa-qapanır.

V7 qoruması: ``(org, subject, period, group=NULL)`` unikallığı PostgreSQL-də
NULL-toqquşmasız keçə bilər, ona görə yazıçı heç vaxt çılpaq ``create`` deyil —
ƏVVƏL EntityMap (resume qatı), SONRA modelin öz açarı üzərində
``get_or_create`` (bir run daxilində eyni açara qatlanan jurnallar EYNİ
offering-ə birləşir və ``legacy_journal_offering_merged`` İNFO-su ilə görünür).

``ensure_assessment_scheme`` semantikası qəsdən ``get_or_create`` ilə güzgüdür:
``apps.registrar.gradebook`` importu modul-sərhəd qrafına yeni
``legacy_import → registrar`` tili açardı; servis funksiyasının bütün gövdəsi
elə bu ``get_or_create``-dir, sxem DRAFT/kilidsiz qalır (E-qaydası, V10 → J7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from types import MappingProxyType as _Frozen

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .field_contracts import JOURNAL_FIELDS
from .rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from .rehearsal_contracts import LegacyRehearsalEvidenceError, encoded_part
from .rehearsal_journal_batch import Decision, TargetMaterialiser

COURSE_OFFERING_ENTITY_TYPE = "course_offering"

_DERIVATION_PREFIX = b"legacy-rehearsal-journal-offering-derivation-v1\x00"
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State

# Xəta taksonomiyası.  Çatışmayan açar INFO-ya düşmək əvəzinə fail-closed olur.
# E-13: heç nə ERROR deyil — ilk jurnal rehearsal-ı tam histoqram verməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                # V7: massiv boş/parse xətası → jurnal bütövlükdə karantinə.
                "legacy_journal_groups_invalid",
                "legacy_journal_group_unresolved",
                "legacy_journal_subject_unresolved",
                "legacy_journal_period_unresolved",
            ),
            _SEVERITY.WARNING,
        ),
        **dict.fromkeys(
            (
                # V6: fake/sonra_sil süzgəci qərarlı siyasətdir, anomaliya deyil.
                "legacy_journal_discarded_source",
                # V7: çoxqruplu jurnal → group=NULL tək offering.
                "legacy_journal_multi_group",
                # V5: instructor=NULL — legacy teacher_id qərar kimliyində qalır.
                "legacy_journal_instructor_unresolved",
                "legacy_journal_offering_merged",
            ),
            _SEVERITY.INFO,
        ),
    }
)


@dataclass(frozen=True)
class OfferingRequest:
    """Bir jurnalın offering yazısı üçün lazım olan hər şey — həll bitib."""

    uniqid: str
    row_hash: str
    subject_pk: str
    period_pk: str
    group_pk: str  # "" → group=NULL (V7 çoxqruplu forma)
    instructor_pk: str  # "" → instructor=NULL (V5)
    subject_ref: str
    period_ref: str
    groups_token: str
    group_state: str
    instructor_state: str
    merged_text: str


@dataclass(frozen=True)
class OfferingOutcome:
    """Bir sətrin möhürlənmiş nəticəsi: ledger state, digest, map, issue-lar."""

    state: str
    digest: str
    entity_map: object
    rule_codes: tuple[str, ...]


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def offering_derivation_hash(
    *,
    uniqid: str,
    row_hash: str,
    outcome_token: str,
    subject_ref: str,
    period_ref: str,
    groups_token: str,
    group_state: str,
    instructor_state: str,
    merged_text: str,
) -> str:
    """Cross-run-sabit offering qərar kimliyi; heç bir UUID ona daxil olmur.

    ``upsert_entity_map`` bunu map-ın kanonik dəyərlərinə qatlayır, ona görə
    fərqli qərar törədən resume cəhdi ledger-in özü tərəfindən
    ``legacy_entity_identity_conflict`` kimi rədd edilir.
    """

    digest = hashlib.sha256(_DERIVATION_PREFIX)
    for part in (
        JOURNAL_FIELDS.fingerprint,
        uniqid,
        row_hash,
        outcome_token,
        subject_ref,
        period_ref,
        groups_token,
        group_state,
        instructor_state,
        merged_text,
    ):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def recorded_decisions(context) -> dict[str, tuple[str, str, str]]:
    """Bu run-un BÜTÜN offering möhürləri — resume üçün BİR sorğu.

    Əvvəl hər jurnal üçün ayrıca ``.first()`` gedirdi (24 159 sorğu).
    """

    rows = LegacyEntityObservation.objects.filter(
        run_id=context.run_id, entity_map__entity_type=COURSE_OFFERING_ENTITY_TYPE
    ).values_list("entity_map__legacy_pk", "state", "source_row_hash", "target_model_label")
    return {
        legacy_pk: (state, row_hash, label) for legacy_pk, state, row_hash, label in rows.iterator(chunk_size=10_000)
    }


# ``gradebook.ensure_assessment_scheme`` güzgüsü: hər açılış üçün lazy/idempotent
# DRAFT sxem (modul qeydinə bax) — toplu yolda "companion" kimi təmin olunur.
OFFERING_MATERIALISER = TargetMaterialiser(
    app_label="registrar",
    model_name="CourseOffering",
    # V7: ``group_id=None`` legal açardır (çoxqruplu jurnal) — ``normalized_key``
    # onu ayrıca sentinel ilə daşıyır, süzgəc isə ``isnull`` budağı ilə tapır.
    key_fields=("subject_id", "period_id", "group_id"),
    defaults=_Frozen({"lesson_hours": 0, "is_active": True}),
    defaults_for=lambda key: {},
    companion=("registrar", "AssessmentScheme", "offering"),
)


def offering_materialiser(instructors_for) -> TargetMaterialiser:
    """Açar → instructor defoltu bağlanmış materialiser (V5: "" → NULL)."""

    from dataclasses import replace as _replace

    return _replace(OFFERING_MATERIALISER, defaults_for=lambda key: {"instructor_id": instructors_for(key) or None})


def discarded_decision(*, uniqid: str, row_hash: str) -> Decision:
    """V6: fake/sonra_sil — SKIPPED; uniqid ledger-də qalır, mənbədə heç nə silinmir."""

    return Decision(
        seal_key=uniqid,
        state=_STATE.SKIPPED,
        digest=offering_derivation_hash(
            uniqid=uniqid,
            row_hash=row_hash,
            outcome_token="discarded",
            subject_ref="",
            period_ref="",
            groups_token="",
            group_state="unread",
            instructor_state="unread",
            merged_text="0",
        ),
        rule_codes=("legacy_journal_discarded_source",),
    )


def unresolved_decision(*, request: OfferingRequest, rule_codes: tuple[str, ...]) -> Decision:
    """Həll olunmayan istinad — jurnal bütövlükdə QUARANTINED, target yazısı yoxdur."""

    return Decision(
        seal_key=request.uniqid,
        state=_STATE.QUARANTINED,
        digest=offering_derivation_hash(
            uniqid=request.uniqid,
            row_hash=request.row_hash,
            outcome_token="unresolved",
            subject_ref=request.subject_ref,
            period_ref=request.period_ref,
            groups_token=request.groups_token,
            group_state=request.group_state,
            instructor_state=request.instructor_state,
            merged_text="0",
        ),
        rule_codes=rule_codes,
    )


def offering_decision(*, request: OfferingRequest, rule_codes: tuple[str, ...]) -> Decision:
    """Materialised açılış; hədəf açarı ``(subject, period, group)`` cütüdür."""

    return Decision(
        seal_key=request.uniqid,
        state=_STATE.MIGRATED,
        digest=offering_derivation_hash(
            uniqid=request.uniqid,
            row_hash=request.row_hash,
            outcome_token="materialised",
            subject_ref=request.subject_ref,
            period_ref=request.period_ref,
            groups_token=request.groups_token,
            group_state=request.group_state,
            instructor_state=request.instructor_state,
            merged_text=request.merged_text,
        ),
        label=COURSE_OFFERING_MODEL_LABEL,
        rule_codes=rule_codes,
        natural_key=(request.subject_pk, request.period_pk, request.group_pk or None),
    )

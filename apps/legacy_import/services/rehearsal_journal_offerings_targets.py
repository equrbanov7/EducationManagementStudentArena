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

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .field_contracts import JOURNAL_FIELDS
from .ledger import upsert_entity_map, upsert_issue
from .rehearsal_authorizer import COURSE_OFFERING_MODEL_LABEL
from .rehearsal_contracts import LegacyRehearsalEvidenceError, encoded_part
from .rehearsal_journal_offerings_source import JOURNAL_SOURCE_TABLE

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


def recorded_decision(context, uniqid: str):
    """Resume qısayolu: möhürlənmiş qərarı yenidən törətmək əvəzinə oxu."""

    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            entity_map__entity_type=COURSE_OFFERING_ENTITY_TYPE,
            entity_map__legacy_pk=uniqid,
        )
        .values_list("state", "source_row_hash", "target_model_label")
        .first()
    )


def _seal(context, *, uniqid: str, digest: str, state: str, label: str = "", target_pk: str = ""):
    return upsert_entity_map(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        entity_type=COURSE_OFFERING_ENTITY_TYPE,
        legacy_pk=uniqid,
        source_row_hash=digest,
        state=state,
        target_model_label=label,
        target_pk=target_pk,
        target_validators=context.target_validators,
    )


def seal_discarded(context, *, uniqid: str, row_hash: str) -> OfferingOutcome:
    """V6: fake/sonra_sil — SKIPPED; uniqid ledger-də qalır, mənbədə heç nə silinmir."""

    digest = offering_derivation_hash(
        uniqid=uniqid,
        row_hash=row_hash,
        outcome_token="discarded",
        subject_ref="",
        period_ref="",
        groups_token="",
        group_state="unread",
        instructor_state="unread",
        merged_text="0",
    )
    entity_map = _seal(context, uniqid=uniqid, digest=digest, state=_STATE.SKIPPED)
    return OfferingOutcome(_STATE.SKIPPED, digest, entity_map, ("legacy_journal_discarded_source",))


def seal_unresolved(context, *, request: OfferingRequest, rule_codes: tuple[str, ...]) -> OfferingOutcome:
    """Həll olunmayan istinad — jurnal bütövlükdə QUARANTINED, target yazısı yoxdur."""

    digest = offering_derivation_hash(
        uniqid=request.uniqid,
        row_hash=request.row_hash,
        outcome_token="unresolved",
        subject_ref=request.subject_ref,
        period_ref=request.period_ref,
        groups_token=request.groups_token,
        group_state=request.group_state,
        instructor_state=request.instructor_state,
        merged_text="0",
    )
    entity_map = _seal(context, uniqid=request.uniqid, digest=digest, state=_STATE.QUARANTINED)
    return OfferingOutcome(_STATE.QUARANTINED, digest, entity_map, rule_codes)


def materialise_offering(context, *, request: OfferingRequest, rule_codes: tuple[str, ...]) -> OfferingOutcome:
    """Offering + draft sxem + ledger möhürü BİR unit of work içində."""

    offering_model = django_apps.get_model("registrar", "CourseOffering")
    scheme_model = django_apps.get_model("registrar", "AssessmentScheme")
    with transaction.atomic():
        offering, _created = offering_model.objects.get_or_create(
            organization=context.organization,
            subject_id=request.subject_pk,
            period_id=request.period_pk,
            group_id=request.group_pk or None,
            defaults={
                "instructor_id": request.instructor_pk or None,
                "lesson_hours": 0,
                "is_active": True,
            },
        )
        # ``gradebook.ensure_assessment_scheme`` güzgüsü: lazy/idempotent,
        # DRAFT/kilidsiz qalır (modul qeydinə bax).
        scheme_model.objects.get_or_create(organization=context.organization, offering=offering)
        digest = offering_derivation_hash(
            uniqid=request.uniqid,
            row_hash=request.row_hash,
            outcome_token="materialised",
            subject_ref=request.subject_ref,
            period_ref=request.period_ref,
            groups_token=request.groups_token,
            group_state=request.group_state,
            instructor_state=request.instructor_state,
            merged_text=request.merged_text,
        )
        entity_map = _seal(
            context,
            uniqid=request.uniqid,
            digest=digest,
            state=_STATE.MIGRATED,
            label=COURSE_OFFERING_MODEL_LABEL,
            target_pk=str(offering.pk),
        )
    return OfferingOutcome(_STATE.MIGRATED, digest, entity_map, rule_codes)


def write_issues(context, *, uniqid: str, outcome: OfferingOutcome, issue_counts) -> None:
    """Issue-lar həmişə öz map-ından sonra: ledger əks sıranı rədd edir."""

    for rule_code in outcome.rule_codes:
        severity = severity_for(rule_code)
        upsert_issue(
            run_id=context.run_id,
            actor=context.actor,
            authorize=context.authorize,
            source_table=JOURNAL_SOURCE_TABLE,
            entity_type=COURSE_OFFERING_ENTITY_TYPE,
            legacy_pk=uniqid,
            rule_code=rule_code,
            severity=severity,
            payload_digest=outcome.digest,
            entity_map_id=outcome.entity_map.pk,
        )
        issue_counts[(rule_code, severity)] += 1

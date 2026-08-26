"""Phase: ``journal_periods`` (J0) — ``semestr_jurnal`` → AcademicPeriod.

Worker fazası ilə eyni derived formadadır (``source_tables = ()``): cədvəl heç
bir batch zəncirinə iddia etmir, mənbə EYNİ audited kontrakt
(``SEMESTR_JURNAL_FIELDS``) üzərindən READ-ONLY axıdılır və hər sətrin qərarı
``(legacy_pk, state, derivation_hash, label)`` dördlüyü ilə möhürlənir (SA-2).

J-V9(F): hər legacy semestr üçün ``AcademicPeriod`` tenant-unikal
``(organization, name, academic_year)`` açarı ilə get-or-create olunur —
``format_year`` normalizasiyası modelin öz staticmethod-undandır, ona görə
"2021/2022 Payız" tipli sərbəst mətn həmişə "2021/2022" ilinə qatlanır.
13-sətirlik uyğunluq cədvəli (legacy id → yaradıldı / mövcud idi) hər sətrin
öz İNFO issue-su kimi ledger-ə düşür; ad ledger-ə YAZILMIR (PII-free forma),
amma legacy_pk + rule_code cütü operator baxışı üçün tam cədvəli verir.

V9 üzrə ``is_current`` HEÇ VAXT köçürülmür: cari dövr qərarı istifadəçinindir —
legacy bayraq yalnız İNFO kimi qeyd olunur, tenant-ın mövcud cari dövrü
toxunulmaz qalır.  E-qaydası: heç bir dövr bu dilimdə kilidlənmir.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue
from core.constants import AcademicPeriodType

from .field_contracts import SEMESTR_JURNAL_FIELDS
from .ledger import upsert_entity_map, upsert_issue
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_authorizer import ACADEMIC_PERIOD_MODEL_LABEL
from .rehearsal_catalog_phase import CATALOG_PHASE_KEY
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
    encoded_part,
    source_row_hash,
)
from .rehearsal_structure_phase import probe_cancellation
from .source_extraction import open_audited_source_stream

JOURNAL_PERIODS_PHASE_KEY = "journal_periods"
JOURNAL_PERIODS_PHASE_ORDER = 32  # sar-dan (28) sonra; 30 sillabusa rezervdir
ACADEMIC_PERIOD_ENTITY_TYPE = "academic_period"
PERIOD_SOURCE_TABLE = "semestr_jurnal"
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-journal-periods-v1"
REQUIRED_PHASE_KEYS = frozenset({CATALOG_PHASE_KEY})

_DERIVATION_PREFIX = b"legacy-rehearsal-journal-period-derivation-v1\x00"
_YEAR_PATTERN = re.compile(r"\d{4}")
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State

# ``semestr_jurnal.type`` qapalı enum-dur; hər fəsil deterministik ad və tarix
# pəncərəsi alır (akademik il Y/Y+1: payız Y-də başlayır, yaz/yay Y+1-dədir).
_SEASONS = MappingProxyType(
    {
        "autumn": ("Payız", (9, 15), (1, 31), 0, 1),
        "spring": ("Yaz", (2, 1), (6, 30), 1, 1),
        "summer": ("Yay", (7, 1), (8, 31), 1, 1),
    }
)

DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "period_materialised",
        _STATE.SKIPPED: "period_deferred",
        _STATE.QUARANTINED: "period_unresolved",
    }
)

# E-13: heç nə ERROR deyil — ilk jurnal rehearsal-ı SUCCEEDED-ə çata bilməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        "legacy_journal_period_invalid": _SEVERITY.WARNING,
        # J-V9(F) uyğunluq cədvəlinin iki sütunu + V9 cari-dövr bayrağı.
        **dict.fromkeys(
            (
                "legacy_journal_period_created",
                "legacy_journal_period_matched_existing",
                "legacy_journal_period_current_flag",
            ),
            _SEVERITY.INFO,
        ),
    }
)


@dataclass(frozen=True)
class PeriodPlan:
    """Bir legacy semestrin hədəf forması — parse artıq uğurla bitib."""

    academic_year: str
    name: str
    start_date: datetime.date
    end_date: datetime.date
    is_current_text: str


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def period_derivation_hash(
    *,
    legacy_pk: int,
    row_hash: str,
    outcome_token: str,
    academic_year: str,
    period_name: str,
    target_state: str,
    is_current_text: str,
) -> str:
    """Cross-run-sabit dövr qərar kimliyi; heç bir UUID ona daxil olmur."""

    digest = hashlib.sha256(_DERIVATION_PREFIX)
    for part in (
        SEMESTR_JURNAL_FIELDS.fingerprint,
        str(legacy_pk),
        row_hash,
        outcome_token,
        academic_year,
        period_name,
        target_state,
        is_current_text,
    ):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def _legacy_flag_text(value: object) -> str:
    """Enum '0'/'1' sütunu; MariaDB onu mətn kimi qaytarır, int də qəbulludur."""

    return "1" if value in (1, "1") else "0"


def parse_period(row) -> PeriodPlan | None:
    """``(name, type)`` cütündən hədəf dövrü törət; alınmasa ``None`` (karantin)."""

    name = row["name"]
    type_token = row["type"]
    if type(name) is not str or type(type_token) is not str:
        return None
    season = _SEASONS.get(type_token)
    match = _YEAR_PATTERN.search(name)
    if season is None or match is None:
        return None
    period_name, start_md, end_md, start_shift, end_shift = season
    start_year = int(match.group())
    if not 1900 <= start_year <= 2100:
        return None
    # Modelin öz normalizasiyası — "2021/2022 Payız" → "2021/2022".
    academic_year = django_apps.get_model("organizations", "AcademicPeriod").format_year(name)
    return PeriodPlan(
        academic_year=academic_year,
        name=period_name,
        start_date=datetime.date(start_year + start_shift, *start_md),
        end_date=datetime.date(start_year + end_shift, *end_md),
        is_current_text=_legacy_flag_text(row["is_current"]),
    )


def period_rows(context: RehearsalContext):
    """``semestr_jurnal``-ı attested, ciddi artan primary-key sırasında axıt."""

    entry = context.plan.entry_for(PERIOD_SOURCE_TABLE)
    previous_pk = 0
    observed = 0
    with open_audited_source_stream(
        connection_factory=context.source_connection_factory,
        contract=SEMESTR_JURNAL_FIELDS,
        chunk_size=context.policy.source_chunk_size,
        cancellation_requested=context.cancellation_requested,
    ) as stream:
        for projected_row in stream:
            legacy_pk = projected_row["id"]
            if type(legacy_pk) is not int:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_type_drift")
            if not 1 <= legacy_pk <= MAX_LEDGER_PRIMARY_KEY:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_out_of_range")
            if legacy_pk <= previous_pk:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_order_invalid")
            previous_pk = legacy_pk
            observed += 1
            if observed > entry.expected_rows:
                raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
            yield legacy_pk, projected_row
    if observed != entry.expected_rows:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")


def _recorded_decision(context: RehearsalContext, legacy_pk: str):
    """Resume qısayolu: möhürlənmiş qərarı yenidən törətmək əvəzinə oxu."""

    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            entity_map__entity_type=ACADEMIC_PERIOD_ENTITY_TYPE,
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
        entity_type=ACADEMIC_PERIOD_ENTITY_TYPE,
        legacy_pk=legacy_pk,
        source_row_hash=digest,
        state=state,
        target_model_label=label,
        target_pk=target_pk,
        target_validators=context.target_validators,
    )


def _write_issues(context, *, legacy_pk: str, digest: str, entity_map, rule_codes, issue_counts) -> None:
    """Issue-lar həmişə öz map-ından sonra: ledger əks sıranı rədd edir."""

    for rule_code in rule_codes:
        severity = severity_for(rule_code)
        upsert_issue(
            run_id=context.run_id,
            actor=context.actor,
            authorize=context.authorize,
            source_table=PERIOD_SOURCE_TABLE,
            entity_type=ACADEMIC_PERIOD_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            rule_code=rule_code,
            severity=severity,
            payload_digest=digest,
            entity_map_id=entity_map.pk,
        )
        issue_counts[(rule_code, severity)] += 1


class JournalPeriodsPhase:
    """J0: 13 legacy semestrin ``AcademicPeriod`` uyğunluğu, sətir-sətir."""

    phase_key = JOURNAL_PERIODS_PHASE_KEY
    order = JOURNAL_PERIODS_PHASE_ORDER
    source_tables = ()
    entity_types = (ACADEMIC_PERIOD_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            # Evidence, Config deyil: orkestrator run-u FAILED bitirir.
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        issue_counts: Counter[tuple[str, str]] = Counter()
        for legacy_pk, row in period_rows(context):
            probe_cancellation(context)
            legacy_pk_text = str(legacy_pk)
            recorded = _recorded_decision(context, legacy_pk_text)
            if recorded is not None:
                state, digest, label = recorded
            else:
                state, digest, label = self._decide(context, legacy_pk=legacy_pk, row=row, issue_counts=issue_counts)
            chain.advance(legacy_pk_text, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{JOURNAL_PERIODS_PHASE_KEY}.records.{sum(state_counts.values())}")
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            state_counts=dict(state_counts),
            issue_counts=MappingProxyType(dict(issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )

    def _decide(self, context, *, legacy_pk, row, issue_counts):
        """Bir semestr sətrinin qərarı: parse → get-or-create → möhür."""

        row_hash = source_row_hash(contract=SEMESTR_JURNAL_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        legacy_pk_text = str(legacy_pk)
        plan = parse_period(row)
        if plan is None:
            digest = period_derivation_hash(
                legacy_pk=legacy_pk,
                row_hash=row_hash,
                outcome_token="unresolved",
                academic_year="",
                period_name="",
                target_state="invalid",
                is_current_text=_legacy_flag_text(row["is_current"]),
            )
            entity_map = _seal(context, legacy_pk=legacy_pk_text, digest=digest, state=_STATE.QUARANTINED)
            _write_issues(
                context,
                legacy_pk=legacy_pk_text,
                digest=digest,
                entity_map=entity_map,
                rule_codes=("legacy_journal_period_invalid",),
                issue_counts=issue_counts,
            )
            return _STATE.QUARANTINED, digest, ""

        model = django_apps.get_model("organizations", "AcademicPeriod")
        with transaction.atomic():
            period, created = model.objects.get_or_create(
                organization=context.organization,
                name=plan.name,
                academic_year=plan.academic_year,
                defaults={
                    "period_type": AcademicPeriodType.SEMESTER,
                    "start_date": plan.start_date,
                    "end_date": plan.end_date,
                    # V9: cari-dövr qərarı istifadəçinindir — import qoymur.
                    "is_current": False,
                    "is_active": True,
                },
            )
            target_state = "created" if created else "existing"
            digest = period_derivation_hash(
                legacy_pk=legacy_pk,
                row_hash=row_hash,
                outcome_token="materialised",
                academic_year=plan.academic_year,
                period_name=plan.name,
                target_state=target_state,
                is_current_text=plan.is_current_text,
            )
            entity_map = _seal(
                context,
                legacy_pk=legacy_pk_text,
                digest=digest,
                state=_STATE.MIGRATED,
                label=ACADEMIC_PERIOD_MODEL_LABEL,
                target_pk=str(period.pk),
            )
        rule_codes = [
            "legacy_journal_period_created" if created else "legacy_journal_period_matched_existing",
        ]
        if plan.is_current_text == "1":
            rule_codes.append("legacy_journal_period_current_flag")
        _write_issues(
            context,
            legacy_pk=legacy_pk_text,
            digest=digest,
            entity_map=entity_map,
            rule_codes=tuple(rule_codes),
            issue_counts=issue_counts,
        )
        return _STATE.MIGRATED, digest, ACADEMIC_PERIOD_MODEL_LABEL

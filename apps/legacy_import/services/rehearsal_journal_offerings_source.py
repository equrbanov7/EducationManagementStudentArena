"""Source side of ``journal_offerings`` (J1): axın, parse və lookup indeksləri.

Yalnız oxumaq və təsnif etmək burada yaşayır — heç bir target yazısı yoxdur.
``journals`` cədvəli EYNİ audited kontrakt (``JOURNAL_FIELDS``) üzərindən
READ-ONLY axıdılır; ``groups_id`` JSON-mətn massivi CİDDİ parse olunur (V7:
parse xətası/boş massiv jurnalın bütövlükdə karantininə aparır, heç nə
təxminlə düzəldilmir).  Lookup indeksləri BU run-un MIGRATED müşahidələrindən
qurulur (§3.9 prinsipi): jurnal fazası özgə run-un hədəflərinə səssizcə
bağlana bilməz.
"""

from __future__ import annotations

import json
import re

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation

from .field_contracts import JOURNAL_FIELDS
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_contracts import IDENTITY_COHORT_MAX_ROWS, LegacyRehearsalEvidenceError, RehearsalContext
from .source_extraction import open_audited_source_stream

JOURNAL_SOURCE_TABLE = "journals"
_UNIQID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,254}\Z")  # ledger OPAQUE_KEY_PATTERN güzgüsü
_STATE = LegacyEntityMap.State


def legacy_int(value: object) -> int:
    """Legacy tam sütun; ``NULL`` MySQL-in yazdığı eyni sıfır sentinelidir."""

    if value is None:
        return 0
    # ``type() is int`` bool üçün onsuz da False-dur: bayraqlar fatal qalır.
    if type(value) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value


def validated_uniqid(value: object) -> str:
    """``uniqid`` ledger kimlik açarıdır — yararsız forma fail-closed olur."""

    if type(value) is not str or not _UNIQID_PATTERN.fullmatch(value):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_journal_uniqid_invalid")
    return value


def parse_group_ids(value: object) -> tuple[int, ...] | None:
    """``groups_id`` JSON-mətnini ciddi parse et; alınmasa ``None`` (V7 karantin).

    Qəbul olunan yeganə forma müsbət tam ədədlərin (mətn və ya ədəd) massividir;
    dublikatlar sıra qorunaraq tək nüsxəyə endirilir.  Boş massiv də ``None``-dur:
    qrupsuz jurnal mənbə hesabatlarına görə mövcud deyil, müdafiə qalır.
    """

    if type(value) is not str or not value.strip():
        return None
    try:
        payload = json.loads(value)
    except ValueError:
        return None
    if type(payload) is not list or not payload:
        return None
    members: list[int] = []
    for element in payload:
        if type(element) is str and element.isdigit():
            member = int(element)
        elif type(element) is int and type(element) is not bool:
            member = element
        else:
            return None
        if not 1 <= member <= MAX_LEDGER_PRIMARY_KEY:
            return None
        if member not in members:
            members.append(member)
    return tuple(members)


def migrated_target_index(context: RehearsalContext, entity_type: str) -> dict[str, str]:
    """BU run-un MIGRATED hədəfləri: ``legacy_pk`` → ``target_pk`` (§3.9)."""

    rows = list(
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            state=_STATE.MIGRATED,
            entity_map__entity_type=entity_type,
        ).values_list("entity_map__legacy_pk", "target_pk")
    )
    if len(rows) > IDENTITY_COHORT_MAX_ROWS:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_cohort_too_large")
    return dict(rows)


def journal_rows(context: RehearsalContext):
    """``journals``-ı attested, ciddi artan primary-key sırasında axıt."""

    entry = context.plan.entry_for(JOURNAL_SOURCE_TABLE)
    previous_pk = 0
    observed = 0
    with open_audited_source_stream(
        connection_factory=context.source_connection_factory,
        contract=JOURNAL_FIELDS,
        chunk_size=context.policy.source_chunk_size,
        cancellation_requested=context.cancellation_requested,
    ) as stream:
        for projected_row in stream:
            legacy_pk = projected_row["id"]
            # pk_inventory._row_pk ilə eyni: heç bir coercion, fail closed.
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

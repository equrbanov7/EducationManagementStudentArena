"""J4-J8-in paylaşdığı jurnal-səviyyə möhür (seal) qatı.

FAZA3B J0-J3-də hər faza öz möhür funksiyalarını təkrar yazırdı; J4-J8-də açar
forması EYNİdir (``uniqid`` → bir qərar, sonra issue-lar), ona görə burada tək
parametrləşdirilmiş ``JournalSealer`` var.  Fərqi yalnız ``entity_type``,
mənbə cədvəli, derivation prefiksi və taksonomiyadır.

Niyə jurnal-səviyyə açar (spec B.6): ``journals_dates_points`` 5,135,289
sətirdir — sətir-başına ``LegacyEntityMap`` ledger-i şişirdərdi.  Ona görə
J4/J5/J6 hər jurnal üçün BİR möhür qoyur, sətir hesabatı isə möhürün
derivation digest-inə qatlanır: qərarlar dəyişsə ``upsert_entity_map`` özü
``legacy_entity_identity_conflict`` ilə fail-closed olur.

Digest-ə heç bir UUID/target pk girmir — cross-run determinizm J0-J3 ilə eyni
qaydadadır.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation

from .ledger import upsert_entity_map, upsert_issue
from .rehearsal_contracts import LegacyRehearsalEvidenceError, encoded_part

_STATE = LegacyEntityMap.State


@dataclass(frozen=True)
class JournalSealer:
    """Bir fazanın ledger kimliyi: entity type + taksonomiya + digest resepti."""

    entity_type: str
    source_table: str
    derivation_prefix: bytes
    contract_fingerprint: str
    issue_severity: Mapping[str, str]

    def severity_for(self, rule_code: str) -> str:
        try:
            return self.issue_severity[rule_code]
        except (KeyError, TypeError):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None

    def derivation_hash(self, *, seal_key: str, outcome_token: str, parts: Sequence[str]) -> str:
        """Cross-run-sabit qərar kimliyi; sətir hesabatı da bura qatlanır."""

        digest = hashlib.sha256(self.derivation_prefix)
        for part in (self.contract_fingerprint, seal_key, outcome_token, *parts):
            digest.update(encoded_part(part))
        return digest.hexdigest()

    def recorded_decision(self, context, seal_key: str):
        """Resume qısayolu: möhürlənmiş qərarı yenidən törətmək əvəzinə oxu."""

        return (
            LegacyEntityObservation.objects.filter(
                run_id=context.run_id,
                entity_map__entity_type=self.entity_type,
                entity_map__legacy_pk=seal_key,
            )
            .values_list("state", "source_row_hash", "target_model_label")
            .first()
        )

    def recorded_decisions(self, context) -> dict[str, tuple[str, str, str]]:
        """Bu run-un BÜTÜN möhürləri — jurnal-səviyyə açar sayı minlərlədir."""

        return {
            legacy_pk: (state, row_hash, label)
            for legacy_pk, state, row_hash, label in LegacyEntityObservation.objects.filter(
                run_id=context.run_id, entity_map__entity_type=self.entity_type
            ).values_list("entity_map__legacy_pk", "state", "source_row_hash", "target_model_label")
        }

    def seal(self, context, *, seal_key: str, digest: str, state: str, label: str = "", target_pk: str = ""):
        return upsert_entity_map(
            run_id=context.run_id,
            actor=context.actor,
            authorize=context.authorize,
            entity_type=self.entity_type,
            legacy_pk=seal_key,
            source_row_hash=digest,
            state=state,
            target_model_label=label,
            target_pk=target_pk,
            target_validators=context.target_validators,
        )

    def write_issues(self, context, *, seal_key: str, digest: str, entity_map, rule_codes, issue_counts) -> None:
        """Issue-lar həmişə öz map-ından sonra: ledger əks sıranı rədd edir."""

        for rule_code in rule_codes:
            severity = self.severity_for(rule_code)
            upsert_issue(
                run_id=context.run_id,
                actor=context.actor,
                authorize=context.authorize,
                source_table=self.source_table,
                entity_type=self.entity_type,
                legacy_pk=seal_key,
                rule_code=rule_code,
                severity=severity,
                payload_digest=digest,
                entity_map_id=entity_map.pk,
            )
            issue_counts[(rule_code, severity)] += 1


def tally_parts(tally: Mapping[str, int]) -> tuple[str, ...]:
    """Sətir hesabatını digest üçün deterministik mətnə çevir (sıralı açarlar)."""

    return tuple(f"{key}={int(value)}" for key, value in sorted(tally.items()) if value)


def state_for(*, written: int, quarantined: int) -> str:
    """Jurnal-səviyyə nəticə: bir sətir də yazılıbsa MIGRATED.

    Heç nə yazılmayıbsa qərar karantinlə skip arasında bölünür — karantin
    "anlaşılmayan data" deməkdir, skip isə "yazılası bir şey yox idi".
    """

    if written:
        return _STATE.MIGRATED
    return _STATE.QUARANTINED if quarantined else _STATE.SKIPPED

"""Legacy qiymət faktlarının immutable target materializasiyası."""

from __future__ import annotations

import hashlib
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyMigrationIssue

from .rehearsal_contracts import LegacyRehearsalEvidenceError, encoded_part, stable_source_value
from .rehearsal_journal_batch import normalized_key

LEGACY_GRADE_FACT_MODEL_LABEL = "registrar.legacygradefact"
MATERIALIZATION_DIGEST_NAMESPACE = b"legacy-grade-fact-materialization-v2\x00"

_SEVERITY = LegacyMigrationIssue.Severity
ISSUE_SEVERITY = MappingProxyType(
    {
        "legacy_grade_fact_group_mismatch": _SEVERITY.WARNING,
        "legacy_grade_fact_discarded_source": _SEVERITY.WARNING,
        "legacy_grade_fact_unresolved": _SEVERITY.WARNING,
        "legacy_grade_fact_conflict": _SEVERITY.WARNING,
        "legacy_grade_fact_non_numeric": _SEVERITY.WARNING,
        "legacy_grade_fact_out_of_range": _SEVERITY.WARNING,
    }
)


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def fact_materialization_digest(*, natural_key: tuple, source_row_hash: str, payload) -> str:
    """Mənbə faktı + source-sabit mapping/provenance qərarlarının möhürü.

    ``Enrollment`` UUID-si disposable bazada təsadüfi yaradılır və cross-run
    determinizm sübutuna daxil ola bilməz. Onun yerinə payload-dakı
    ``source_enrollment_ref`` və yalnız linkin mövcudluq bayrağı möhürlənir.
    Eyni bazada yanlış target UUID reuse-u ``resolve``-dakı ayrıca müqayisə ilə
    fail-closed bloklanır.
    """

    digest = hashlib.sha256(MATERIALIZATION_DIGEST_NAMESPACE)
    for part in natural_key:
        digest.update(encoded_part(str(part)))
    digest.update(encoded_part(source_row_hash))
    deterministic_payload = {key: value for key, value in payload.items() if key != "enrollment_id"}
    deterministic_payload["enrollment_linked"] = payload.get("enrollment_id") is not None
    for key in sorted(deterministic_payload):
        digest.update(encoded_part(key))
        digest.update(encoded_part(stable_source_value(deterministic_payload[key])))
    return digest.hexdigest()


class LegacyGradeFactMaterialiser:
    """``JournalBatchWriter`` üçün source açarı → immutable fact həlli.

    Payload dəstə yazılana qədər yaddaşda qalır və ``resolve`` bitəndə silinir;
    beləliklə milyonlarla mənbə sətrinin məlumatı RAM-da yığılmır.
    """

    def __init__(self) -> None:
        self._payloads: dict[tuple[str, ...], dict[str, object]] = {}

    def stage(self, natural_key: tuple, payload: dict[str, object]) -> None:
        key = normalized_key(natural_key)
        if key in self._payloads:
            raise LegacyRehearsalEvidenceError("legacy_grade_fact_batch_duplicate")
        self._payloads[key] = dict(payload)

    def resolve(self, context, keys) -> dict[tuple[str, ...], str]:
        ordered = list(dict.fromkeys(keys))
        if not ordered:
            return {}
        wanted = {normalized_key(key) for key in ordered}
        model = django_apps.get_model("registrar", "LegacyGradeFact")
        rows = model.objects.filter(
            organization=context.organization,
            source_system__in={key[0] for key in ordered},
            source_table__in={key[1] for key in ordered},
            source_pk__in={key[2] for key in ordered},
        ).values_list(
            "pk",
            "source_system",
            "source_table",
            "source_pk",
            "materialization_digest",
            "enrollment_id",
        )
        resolved: dict[tuple[str, ...], str] = {}
        for pk, source_system, source_table, source_pk, digest, enrollment_id in rows:
            key = normalized_key((source_system, source_table, source_pk))
            if key not in wanted:
                continue
            payload = self._payloads.get(key)
            expected_enrollment = payload.get("enrollment_id") if payload is not None else None
            if (
                payload is None
                or digest != payload["materialization_digest"]
                or str(enrollment_id or "") != str(expected_enrollment or "")
            ):
                raise LegacyRehearsalEvidenceError("legacy_grade_fact_identity_conflict")
            resolved[key] = str(pk)

        missing = [key for key in ordered if normalized_key(key) not in resolved]
        if missing:
            pending = []
            for source_system, source_table, source_pk in missing:
                payload = self._payloads.get(normalized_key((source_system, source_table, source_pk)))
                if payload is None:
                    raise LegacyRehearsalEvidenceError("legacy_grade_fact_payload_missing")
                pending.append(
                    model(
                        organization=context.organization,
                        source_system=source_system,
                        source_table=source_table,
                        source_pk=source_pk,
                        **payload,
                    )
                )
            with transaction.atomic():
                model.objects.bulk_create(pending)
            for key, instance in zip(missing, pending):
                resolved[normalized_key(key)] = str(instance.pk)

        for key in wanted:
            self._payloads.pop(key, None)
        return resolved


__all__ = [
    "ISSUE_SEVERITY",
    "LEGACY_GRADE_FACT_MODEL_LABEL",
    "MATERIALIZATION_DIGEST_NAMESPACE",
    "LegacyGradeFactMaterialiser",
    "fact_materialization_digest",
    "severity_for",
]

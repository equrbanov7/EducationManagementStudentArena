"""Batched ledger writes — ``upsert_entity_map``/``upsert_issue`` ilə EYNİ semantika.

Niyə var (Rehearsal #9 ölçüsü, 2026-08-28)
------------------------------------------
``upsert_entity_map`` bir möhür üçün ~60, ``upsert_issue`` isə ~25 DB gediş-gəlişi
xərcləyir.  Sintetik profildə (500 sətir, sqlite) J2 fazasının **92 %-i** məhz bu
funksiyanın içindədir; onun da **68 %-i** ``full_clean(validate_constraints=True)``
çağırışıdır — Django hər ``CheckConstraint`` üçün AYRI ``SELECT 1 WHERE <ifadə>``
sorğusu göndərir (map+version+observation = sətir başına 27 belə sorğu).  172 471
qeydiyyat və 379 215 dərs sətrində bu, saatlarla vaxt deməkdir.

Bu modul EYNİ qərarları sətir-sətir deyil, N sətirlik dəstə ilə yazır:

* scope advisory kilidi, run oxunuşu, authorize və ``_require_active_run``
  dəstə başına BİR dəfə (əvvəl: sətir başına iki run SELECT-i + kilid);
* mövcud map / version / observation sətirləri BİR ``... IN (...)`` sorğusu ilə
  (``select_for_update`` saxlanılır — başqa transform_version-lu paralel run eyni
  canonical map-a toxuna bilər, kilid həmin qapını bağlı saxlayır);
* yeni sətirlər ``bulk_create`` ilə (``ignore_conflicts`` YOX — itən sətir
  olmamalıdır; unikallıq pozulsa PG ``IntegrityError`` verir və run FAIL olur).

Zəmanətlər NECƏ qorunur (heç biri zəifləmir)
--------------------------------------------
1. **Sahə validatorları** — hər instansiya üçün ``validate_columns`` çağırılır:
   regex/uzunluq/choice yoxlamalarının HAMISI qalır, yalnız ``ForeignKey``
   mövcudluq sorğuları çıxarılır (onları DB-nin öz FK constraint-i tutur).
2. **``Model.clean()`` cross-scope yoxlamaları** — həmin şərtlərin EYNİSİ artıq
   PG trigger-lərindədir (``legacy_import_map_integrity_guard``,
   ``legacy_import_observation_integrity_guard``, ``legacy_import_issue_integrity_guard``
   — hamısı ``FOR EACH ROW``, INSERT-də işləyir).  Burada onlar ƏLAVƏ olaraq
   Python-da da yoxlanılır, amma artıq oxunmuş ``run`` obyektindən — yəni sorğusuz.
3. **``CheckConstraint`` / ``UniqueConstraint``** — hamısı miqrasiyalarda REAL DB
   constraint-idir.  ``validate_constraints`` onları INSERT-dən ƏVVƏL bir daha
   DB-də hesablayırdı; batch yolunda qapını DB-nin özü tutur (fail-closed:
   pozulma ``IntegrityError`` → dəstə rollback → faza, sonra run FAILED).
4. **İdempotentlik** — mövcud sətir tapılırsa yenidən yazılmır, canonical
   dəyərlər fərqlidirsə eyni ``legacy_entity_identity_conflict`` /
   ``legacy_entity_observation_conflict`` kodları atılır.
5. **Determinizm** — bu modul heç bir digest hesablamır; qərar sırası və möhür
   açarları çağıran fazanındır.

Bir dəstə BİR ``transaction.atomic()`` içindədir (``locked_scope``): yarımçıq
dəstə qalmır — ya hamısı, ya heç biri (jurnal-atomic prinsipi ilə uyğun).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue
from apps.legacy_import.review_models import LegacyEntityMapVersion

from .ledger import (
    _SEVERITY_RANK,
    LedgerAction,
    LegacyLedgerConflictError,
    LegacyLedgerTargetError,
    _authorize,
    _get_run,
    _locked_scope,
    _require_active_run,
    _scope_parts,
    _target_validation,
)
from .versioning import SNAPSHOT_FIELDS

# Bir dəstənin maksimum ölçüsü: ``IN (...)`` siyahısı və ``bulk_create``
# paketi bu həddə saxlanılır (PG parametr limiti 65535-dir, 2000 × ~12 sütun
# rahat sığır; yaddaş izi də sabit qalır).
BATCH_ROWS = 2_000


@dataclass(frozen=True)
class SealRequest:
    """Bir möhür qərarı — ``upsert_entity_map`` arqumentlərinin eynisi."""

    legacy_pk: str
    source_row_hash: str
    state: str
    target_model_label: str = ""
    target_pk: str = ""


@dataclass(frozen=True)
class IssueRequest:
    """Bir issue qeydi — ``upsert_issue`` arqumentlərinin eynisi."""

    legacy_pk: str
    rule_code: str
    severity: str
    payload_digest: str


def validate_columns(instance) -> None:
    """Sahə validatorları — əlaqə sahələri istisna, yəni SORĞUSUZ.

    ``clean_fields()`` hər ``ForeignKey`` üçün ayrıca ``EXISTS`` sorğusu atır
    (map+version+observation = sətir başına 9 gediş-gəliş).  Həmin zəmanət
    ledger cədvəllərində onsuz da REAL DB foreign-key constraint-i ilə (üstəlik
    ``legacy_import_*_integrity_guard`` trigger-ləri ilə) təmin olunur; burada
    yalnız regex/uzunluq/choice yoxlamaları saxlanılır.
    """

    instance.clean_fields(exclude=[field.name for field in instance._meta.fields if field.is_relation])


def _canonical(request: SealRequest, *, transform_version: str) -> dict[str, str]:
    return {
        "source_row_hash": request.source_row_hash,
        "transform_version": transform_version,
        "target_model_label": request.target_model_label,
        "target_pk": request.target_pk,
        "state": request.state,
        "reconciliation_status": LegacyEntityMap.ReconciliationStatus.PENDING,
    }


def _chunks(items: Sequence[Any], size: int = BATCH_ROWS):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _deduplicated(requests: Iterable[SealRequest], *, transform_version: str) -> list[SealRequest]:
    """Eyni açarın təkrarı: dəyərlər eynidirsə birləşir, fərqlidirsə konflikt."""

    seen: dict[str, dict[str, str]] = {}
    ordered: list[SealRequest] = []
    for request in requests:
        values = _canonical(request, transform_version=transform_version)
        previous = seen.get(request.legacy_pk)
        if previous is None:
            seen[request.legacy_pk] = values
            ordered.append(request)
        elif previous != values:
            raise LegacyLedgerConflictError("legacy_entity_identity_conflict")
    return ordered


def _validated_targets(
    *,
    requests: Sequence[SealRequest],
    organization: Any,
    target_validators: Mapping[str, Any],
    bulk_target_validators: Mapping[str, Any] | None,
) -> None:
    """MIGRATED möhürlərin hədəfi: mövcudluq + tenant sahibliyi (fail closed).

    Toplu validator varsa etiket başına BİR sorğu, yoxdursa köhnə sətir-başına
    validator — nəticə hər iki yolda EYNİ ``legacy_target_*`` kodlarıdır.
    """

    by_label: dict[str, set[str]] = {}
    for request in requests:
        if request.state != LegacyEntityMap.State.MIGRATED:
            continue
        by_label.setdefault(request.target_model_label, set()).add(request.target_pk)
    for label, target_pks in by_label.items():
        # Allowlist qapısı toplu yolda da eynidir: qeydiyyatsız etiket keçmir.
        try:
            registered = target_validators.get(label)
        except AttributeError:
            raise LegacyLedgerTargetError("legacy_target_registry_invalid") from None
        if registered is None:
            raise LegacyLedgerTargetError("legacy_target_unregistered")
        bulk_validator = None if bulk_target_validators is None else bulk_target_validators.get(label)
        if bulk_validator is None:
            for target_pk in sorted(target_pks):
                _target_validation(
                    target_model_label=label,
                    target_pk=target_pk,
                    organization=organization,
                    target_validators=target_validators,
                )
            continue
        try:
            owned = bulk_validator(target_pks=frozenset(target_pks), organization=organization)
        except Exception:
            raise LegacyLedgerTargetError("legacy_target_validation_failed") from None
        if not isinstance(owned, (set, frozenset)):
            raise LegacyLedgerTargetError("legacy_target_validation_result_invalid")
        missing = target_pks - owned
        if missing:
            # Toplu validator "mövcud VƏ tenantındır" cavabını verir; ayırd
            # etmək üçün uduzan açar tək-tək yenidən yoxlanır (nadir yol).
            for target_pk in sorted(missing):
                _target_validation(
                    target_model_label=label,
                    target_pk=target_pk,
                    organization=organization,
                    target_validators=target_validators,
                )
            raise LegacyLedgerTargetError("legacy_target_not_found")


def _existing_maps(*, run, entity_type: str, legacy_pks: Sequence[str]) -> dict[str, LegacyEntityMap]:
    rows = (
        LegacyEntityMap.objects.select_for_update()
        .filter(
            organization_id=run.organization_id,
            source_system=run.source_system,
            entity_type=entity_type,
            legacy_pk__in=legacy_pks,
        )
        .order_by()
    )
    return {row.legacy_pk: row for row in rows}


def _created_maps(*, run, entity_type: str, requests, existing, values_for) -> list[LegacyEntityMap]:
    pending: list[LegacyEntityMap] = []
    for request in requests:
        if request.legacy_pk in existing:
            continue
        entity_map = LegacyEntityMap(
            organization=run.organization,
            source_system=run.source_system,
            entity_type=entity_type,
            legacy_pk=request.legacy_pk,
            created_run=run,
            **values_for[request.legacy_pk],
        )
        # Saf Python sahə validatorları (regex/uzunluq/choice) — sorğusuz.
        validate_columns(entity_map)
        pending.append(entity_map)
    if pending:
        LegacyEntityMap.objects.bulk_create(pending)
    return pending


def _latest_versions(*, maps: Sequence[LegacyEntityMap]) -> dict[Any, LegacyEntityMapVersion]:
    """Hər map üçün ən böyük ``version_number`` — bir sorğu, Python-da seçim."""

    latest: dict[Any, LegacyEntityMapVersion] = {}
    rows = (
        LegacyEntityMapVersion.objects.select_for_update()
        .filter(entity_map_id__in=[entity_map.pk for entity_map in maps])
        .order_by()
    )
    for version in rows:
        current = latest.get(version.entity_map_id)
        if current is None or version.version_number > current.version_number:
            latest[version.entity_map_id] = version
    return latest


def _ensured_versions(*, maps: Sequence[LegacyEntityMap], latest) -> dict[Any, LegacyEntityMapVersion]:
    """Versiyasız map üçün ``version_number=1`` snapshot-ı (``ensure_initial_version``)."""

    pending: list[LegacyEntityMapVersion] = []
    for entity_map in maps:
        if entity_map.pk in latest:
            continue
        version = LegacyEntityMapVersion(
            organization_id=entity_map.organization_id,
            entity_map=entity_map,
            version_number=1,
            recorded_run_id=entity_map.created_run_id,
            **{field: getattr(entity_map, field) for field in SNAPSHOT_FIELDS},
        )
        validate_columns(version)
        pending.append(version)
    if pending:
        LegacyEntityMapVersion.objects.bulk_create(pending)
        for version in pending:
            latest[version.entity_map_id] = version
    return latest


def _observations(*, run, maps: Sequence[LegacyEntityMap], latest, values_for) -> None:
    """Hər map üçün bu run-un dəyişməz müşahidəsi; mövcud olan yoxlanılır."""

    recorded = {
        observation.entity_map_id: observation
        for observation in LegacyEntityObservation.objects.select_for_update()
        .filter(run=run, entity_map_id__in=[entity_map.pk for entity_map in maps])
        .order_by()
    }
    pending: list[LegacyEntityObservation] = []
    for entity_map in maps:
        values = values_for[entity_map.legacy_pk]
        version = latest[entity_map.pk]
        observation = recorded.get(entity_map.pk)
        if observation is not None:
            if observation.map_version_id != version.pk or any(
                getattr(observation, field) != value for field, value in values.items()
            ):
                raise LegacyLedgerConflictError("legacy_entity_observation_conflict")
            continue
        observation = LegacyEntityObservation(
            organization_id=run.organization_id,
            run=run,
            entity_map=entity_map,
            map_version=version,
            **values,
        )
        validate_columns(observation)
        pending.append(observation)
    if pending:
        LegacyEntityObservation.objects.bulk_create(pending)


def seal_entity_maps(
    *,
    run_id: Any,
    actor: Any,
    authorize,
    entity_type: str,
    requests: Sequence[SealRequest],
    target_validators: Mapping[str, Any],
    bulk_target_validators: Mapping[str, Any] | None = None,
) -> dict[str, LegacyEntityMap]:
    """Bir dəstə möhür; nəticə ``legacy_pk`` → ``LegacyEntityMap`` (issue üçün)."""

    if not requests:
        return {}
    sealed: dict[str, LegacyEntityMap] = {}
    for chunk in _chunks(list(requests)):
        sealed.update(
            _seal_chunk(
                run_id=run_id,
                actor=actor,
                authorize=authorize,
                entity_type=entity_type,
                requests=chunk,
                target_validators=target_validators,
                bulk_target_validators=bulk_target_validators,
            )
        )
    return sealed


def _seal_chunk(
    *, run_id, actor, authorize, entity_type, requests, target_validators, bulk_target_validators
) -> dict[str, LegacyEntityMap]:
    scope = _scope_parts(_get_run(run_id))
    with _locked_scope(scope):
        run = _get_run(run_id, for_update=True)
        _authorize(actor=actor, organization=run.organization, action=LedgerAction.UPSERT_MAP, authorize=authorize)
        _require_active_run(run)
        ordered = _deduplicated(requests, transform_version=run.transform_version)
        values_for = {
            request.legacy_pk: _canonical(request, transform_version=run.transform_version) for request in ordered
        }
        _validated_targets(
            requests=ordered,
            organization=run.organization,
            target_validators=target_validators,
            bulk_target_validators=bulk_target_validators,
        )
        legacy_pks = [request.legacy_pk for request in ordered]
        existing = _existing_maps(run=run, entity_type=entity_type, legacy_pks=legacy_pks)
        created = _created_maps(
            run=run, entity_type=entity_type, requests=ordered, existing=existing, values_for=values_for
        )
        for entity_map in created:
            existing[entity_map.legacy_pk] = entity_map
        maps = [existing[legacy_pk] for legacy_pk in legacy_pks]
        latest = _ensured_versions(maps=maps, latest=_latest_versions(maps=maps))
        for entity_map in maps:
            version = latest[entity_map.pk]
            if any(getattr(version, field) != value for field, value in values_for[entity_map.legacy_pk].items()):
                # Eyni açar bu run-da FƏRQLİ qərar daşıyır — fail closed.
                raise LegacyLedgerConflictError("legacy_entity_identity_conflict")
        _observations(run=run, maps=maps, latest=latest, values_for=values_for)
    return existing


def record_issues(
    *,
    run_id: Any,
    actor: Any,
    authorize,
    source_table: str,
    entity_type: str,
    requests: Sequence[IssueRequest],
    entity_maps: Mapping[str, LegacyEntityMap],
) -> None:
    """Bir dəstə issue; hər biri ÖZ map-ından sonra yazılır (ledger qaydası)."""

    if not requests:
        return
    for chunk in _chunks(list(requests)):
        _record_issue_chunk(
            run_id=run_id,
            actor=actor,
            authorize=authorize,
            source_table=source_table,
            entity_type=entity_type,
            requests=chunk,
            entity_maps=entity_maps,
        )


def _issue_scope_checked(*, entity_map, run, entity_type: str, legacy_pk: str) -> None:
    """``ledger._get_issue_map`` yoxlamalarının sorğusuz güzgüsü."""

    if (
        entity_map.organization_id != run.organization_id
        or entity_map.source_system != run.source_system
        or entity_map.entity_type != entity_type
        or entity_map.legacy_pk != legacy_pk
    ):
        raise LegacyLedgerConflictError("legacy_issue_map_scope_mismatch")


def _record_issue_chunk(*, run_id, actor, authorize, source_table, entity_type, requests, entity_maps) -> None:
    scope = _scope_parts(_get_run(run_id))
    with _locked_scope(scope):
        run = _get_run(run_id, for_update=True)
        _authorize(actor=actor, organization=run.organization, action=LedgerAction.UPSERT_ISSUE, authorize=authorize)
        _require_active_run(run)
        maps: dict[str, LegacyEntityMap] = {}
        for request in requests:
            entity_map = entity_maps.get(request.legacy_pk)
            if entity_map is None:
                raise LegacyLedgerConflictError("legacy_issue_map_not_found")
            _issue_scope_checked(entity_map=entity_map, run=run, entity_type=entity_type, legacy_pk=request.legacy_pk)
            maps[request.legacy_pk] = entity_map
        observed = set(
            LegacyEntityObservation.objects.filter(
                run=run,
                entity_map_id__in=[entity_map.pk for entity_map in maps.values()],
                transform_version=run.transform_version,
            )
            .order_by()
            .values_list("entity_map_id", flat=True)
        )
        for request in requests:
            if request.rule_code != "legacy_entity_identity_conflict" and maps[request.legacy_pk].pk not in observed:
                raise LegacyLedgerConflictError("legacy_issue_map_scope_mismatch")
        recorded = {
            (issue.legacy_pk, issue.rule_code): issue
            for issue in LegacyMigrationIssue.objects.select_for_update()
            .filter(
                run=run,
                source_table=source_table,
                legacy_pk__in=[request.legacy_pk for request in requests],
            )
            .order_by()
        }
        created, updated = _issue_writes(
            run=run,
            source_table=source_table,
            entity_type=entity_type,
            requests=requests,
            maps=maps,
            recorded=recorded,
        )
        if created:
            LegacyMigrationIssue.objects.bulk_create(created)
        if updated:
            LegacyMigrationIssue.objects.bulk_update(updated, ["severity", "review_status", "entity_map"])


def _issue_writes(*, run, source_table, entity_type, requests, maps, recorded):
    """``upsert_issue``-nun eskalasiya/konflikt nərdivanı, sorğusuz."""

    created: list[LegacyMigrationIssue] = []
    updated: list[LegacyMigrationIssue] = []
    fresh: set[Any] = set()
    for request in requests:
        entity_map = maps[request.legacy_pk]
        issue = recorded.get((request.legacy_pk, request.rule_code))
        if issue is None:
            issue = LegacyMigrationIssue(
                organization_id=run.organization_id,
                run=run,
                source_table=source_table,
                entity_type=entity_type,
                legacy_pk=request.legacy_pk,
                rule_code=request.rule_code,
                payload_digest=request.payload_digest,
                severity=request.severity,
                review_status=LegacyMigrationIssue.ReviewStatus.OPEN,
                entity_map=entity_map,
            )
            validate_columns(issue)
            recorded[(request.legacy_pk, request.rule_code)] = issue
            created.append(issue)
            fresh.add(issue.pk)
            continue
        if issue.entity_type != entity_type or issue.payload_digest != request.payload_digest:
            raise LegacyLedgerConflictError("legacy_issue_identity_conflict")
        if issue.entity_map_id and issue.entity_map_id != entity_map.pk:
            raise LegacyLedgerConflictError("legacy_issue_map_conflict")
        if issue.entity_map_id is None:
            issue.entity_map = entity_map
        current_rank = _SEVERITY_RANK.get(issue.severity)
        incoming_rank = _SEVERITY_RANK.get(request.severity)
        if current_rank is None or incoming_rank is None:
            raise LegacyLedgerConflictError("legacy_issue_severity_invalid")
        if incoming_rank > current_rank:
            issue.severity = request.severity
            issue.review_status = LegacyMigrationIssue.ReviewStatus.OPEN
        if issue.pk not in fresh:
            updated.append(issue)
    return created, updated


__all__ = ["BATCH_ROWS", "IssueRequest", "SealRequest", "record_issues", "seal_entity_maps"]

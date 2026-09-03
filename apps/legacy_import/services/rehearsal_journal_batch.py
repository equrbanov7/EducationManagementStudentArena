"""J2/J3-ün paylaşdığı dəstə yazıcısı: hədəf ``bulk_create`` + toplu möhür/issue.

Niyə (Rehearsal #9, 2026-08-28)
-------------------------------
Sətir-başına ``get_or_create`` + ``upsert_entity_map`` + ``upsert_issue`` J2-də
saniyədə 14 sətir verirdi; profil bu vaxtın **92 %-ini** ledger möhüründə
göstərdi (bax ``ledger_batch`` modul qeydi).  Bu modul qərar SAYINI dəyişmir —
hər mənbə sətri yenə öz möhürünü və digest halqasını alır — sadəcə yazını
dəstələyir:

* hədəf sətirləri (``Enrollment`` / ``Lesson``) təbii açar üzrə BİR sorğu ilə
  axtarılır, çatmayanlar ``bulk_create`` ilə yaradılır (``ignore_conflicts``
  YOX: itən sətir olmamalıdır, unikallıq pozulsa run fail-closed dayanır);
* möhürlər və issue-lar ``ledger_batch`` ilə dəstə-dəstə yazılır, issue həmişə
  öz map-ından SONRA (ledger əks sıranı rədd edir).

İdempotentlik: axtarış sorğusu HƏR flush-da təzədən aparılır, ona görə həm
əvvəlki (resume) run-un, həm də bu run-un əvvəlki dəstələrinin yaratdığı sətirlər
tapılır — V7 merge-də eyni (tələbə, açılış) cütü EYNİ ``Enrollment``-ə qatlanır.

Atomiklik: bir dəstə bir ``transaction.atomic()`` içindədir (hədəf yazısı +
möhürlər).  Yarımçıq dəstə qalmır; kəsilmiş run resume-da qaldığı yerdən davam
edir, çünki möhürsüz hədəf sətri sonrakı flush-ın axtarışında yenidən tapılır.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Q

from apps.legacy_import.models import LegacyEntityMap

from .ledger_batch import BATCH_ROWS, IssueRequest, SealRequest, record_issues, seal_entity_maps
from .rehearsal_contracts import LegacyRehearsalEvidenceError

_STATE = LegacyEntityMap.State


NULL_TOKEN = "\x00null"  # NULL açar hissəsi üçün mətnlə toqquşmayan sentinel


def normalized_key(key) -> tuple[str, ...]:
    """Təbii açarın müqayisə forması: UUID/tarix/saat/NULL → sabit mətn.

    DB ``UUID``/``date``/``time`` obyektləri qaytarır, ledger isə açarları mətn
    kimi daşıyır; müqayisə tək formada aparılmasa cüt heç vaxt uyğun gəlməzdi.
    ``None`` (nullable açar sahəsi, məs. ``CourseOffering.group``) ayrıca
    sentinel alır: ``str(None)`` real dəyərlə qarışa bilərdi.
    """

    return tuple(NULL_TOKEN if part is None else str(part) for part in key)


@dataclass(frozen=True)
class Decision:
    """Bir mənbə sətrinin yekun qərarı — ledger-ə nə yazılacağı tam bəllidir."""

    seal_key: str
    state: str
    digest: str
    label: str = ""
    rule_codes: tuple[str, ...] = ()  # boş → issue yazılmır (materialised sətir)
    natural_key: tuple = ()  # MIGRATED üçün hədəfin təbii açarı


@dataclass(frozen=True)
class TargetMaterialiser:
    """Təbii açar → hədəf pk; ``get_or_create`` semantikasının toplu güzgüsü.

    ``key_fields`` modelin unikallıq açarıdır (org daxilində).  Axtarış sorğusu
    hər sahə üçün ``__in`` süzgəci qurur və nəticəni Python-da dəqiq açar cütünə
    görə süzür: bir dəstə üçün BİR sorğu, artıq sətir gətirsə də qərar dəqiqdir.
    """

    app_label: str
    model_name: str
    key_fields: tuple[str, ...]
    defaults: Mapping[str, Any]
    # Açardan asılı defoltlar (məs. dərsin açılış müəllimi); sabitlərlə birləşir.
    defaults_for: Callable[[tuple], Mapping[str, Any]] | None = None
    # Hər həll olunmuş hədəf üçün təmin edilən yoldaş sətir (məs. offering-in
    # DRAFT ``AssessmentScheme``-i) — ``(app_label, model_name, fk_field)``.
    companion: tuple[str, str, str] | None = None

    def model(self):
        return django_apps.get_model(self.app_label, self.model_name)

    def _defaults(self, key: tuple) -> dict[str, Any]:
        values = dict(self.defaults)
        if self.defaults_for is not None:
            values.update(self.defaults_for(key))
        return values

    def _filter(self, keys: Sequence[tuple]):
        """Açar sahələri üzrə ``__in`` süzgəci; NULL hissə ayrıca OR budağıdır.

        ``field__in=[None, ...]`` SQL-də ``IN (NULL, ...)`` olur və NULL sətri
        HEÇ VAXT tapmır — nullable açar (məs. ``group_id``) məhz bu səbəbdən
        ``isnull=True`` budağı ilə tamamlanır.
        """

        condition = Q()
        for index, field in enumerate(self.key_fields):
            values = {key[index] for key in keys}
            has_null = None in values
            values.discard(None)
            branch = Q(**{f"{field}__in": values}) if values else Q(pk__in=[])
            condition &= (branch | Q(**{f"{field}__isnull": True})) if has_null else branch
        return condition

    def existing(self, context, keys: Sequence[tuple]) -> dict[tuple, str]:
        model = self.model()
        wanted = {normalized_key(key) for key in keys}
        found: dict[tuple, str] = {}
        rows = model.objects.filter(self._filter(keys), organization=context.organization).values_list(
            "pk", *self.key_fields
        )
        for row in rows.iterator(chunk_size=5_000):
            key = normalized_key(row[1:])
            if key in wanted:
                found[key] = str(row[0])
        return found

    def create(self, context, keys: Sequence[tuple]) -> dict[tuple, str]:
        model = self.model()
        pending = [
            model(organization=context.organization, **dict(zip(self.key_fields, key)), **self._defaults(key))
            for key in keys
        ]
        # ``bulk_create`` INSERT-dir: PG tenant/identity trigger-ləri hər sətir
        # üçün işləyir, ``ReferenceIdentityValidationMixin`` isə yalnız UPDATE
        # yolunu qoruyur (yeni sətirdə onsuz da no-op).
        model.objects.bulk_create(pending)
        return {normalized_key(key): str(instance.pk) for key, instance in zip(keys, pending)}

    def ensure_companions(self, context, target_pks) -> None:
        """Yoldaş sətirləri idempotent təmin et (``get_or_create`` güzgüsü)."""

        if self.companion is None or not target_pks:
            return
        app_label, model_name, field = self.companion
        model = django_apps.get_model(app_label, model_name)
        wanted = {str(target_pk) for target_pk in target_pks}
        have = {
            str(value)
            for value in model.objects.filter(
                organization=context.organization, **{f"{field}__in": sorted(wanted)}
            ).values_list(field, flat=True)
        }
        missing = sorted(wanted - have)
        if missing:
            model.objects.bulk_create(
                [model(organization=context.organization, **{f"{field}_id": target_pk}) for target_pk in missing]
            )

    def resolve(self, context, keys: Sequence[tuple]) -> dict[tuple, str]:
        ordered = list(dict.fromkeys(keys))
        if not ordered:
            return {}
        resolved = self.existing(context, ordered)
        missing = [key for key in ordered if normalized_key(key) not in resolved]
        if missing:
            resolved.update(self.create(context, missing))
        self.ensure_companions(context, resolved.values())
        return resolved


class JournalBatchWriter:
    """Qərarları buferləyir, dəstə dolanda hədəf + möhür + issue yazır."""

    def __init__(
        self,
        context,
        *,
        entity_type: str,
        source_table: str,
        severity_for: Callable[[str], str],
        materialiser: TargetMaterialiser,
        batch_rows: int | None = None,
    ) -> None:
        self._context = context
        self._entity_type = entity_type
        self._source_table = source_table
        self._severity_for = severity_for
        self._materialiser = materialiser
        # Defolt icra vaxtı oxunur ki, test dəstə sərhədini dəyişə bilsin.
        self._batch_rows = max(1, int(BATCH_ROWS if batch_rows is None else batch_rows))
        self._pending: list[Decision] = []
        self.issue_counts: Counter[tuple[str, str]] = Counter()

    def add(self, decision: Decision) -> None:
        if decision.state == _STATE.MIGRATED and not decision.natural_key:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_batch_target_key_missing")
        self._pending.append(decision)
        if len(self._pending) >= self._batch_rows:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        context = self._context
        with transaction.atomic():
            targets = self._materialiser.resolve(
                context, [decision.natural_key for decision in batch if decision.state == _STATE.MIGRATED]
            )
            seals = [self._seal_request(decision, targets) for decision in batch]
            entity_maps = seal_entity_maps(
                run_id=context.run_id,
                actor=context.actor,
                authorize=context.authorize,
                entity_type=self._entity_type,
                requests=seals,
                target_validators=context.target_validators,
                bulk_target_validators=getattr(context, "bulk_target_validators", None),
            )
            issues = [
                IssueRequest(
                    legacy_pk=decision.seal_key,
                    rule_code=rule_code,
                    severity=self._severity_for(rule_code),
                    payload_digest=decision.digest,
                )
                for decision in batch
                for rule_code in decision.rule_codes
            ]
            record_issues(
                run_id=context.run_id,
                actor=context.actor,
                authorize=context.authorize,
                source_table=self._source_table,
                entity_type=self._entity_type,
                requests=issues,
                entity_maps=entity_maps,
            )
        for issue in issues:
            self.issue_counts[(issue.rule_code, issue.severity)] += 1

    def _seal_request(self, decision: Decision, targets: Mapping[tuple, str]) -> SealRequest:
        if decision.state != _STATE.MIGRATED:
            return SealRequest(
                legacy_pk=decision.seal_key,
                source_row_hash=decision.digest,
                state=decision.state,
            )
        target_pk = targets.get(normalized_key(decision.natural_key), "")
        if not target_pk:
            # Hədəf yaradıla bilmədisə möhür yalançı olardı — fail closed.
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_batch_target_unresolved")
        return SealRequest(
            legacy_pk=decision.seal_key,
            source_row_hash=decision.digest,
            state=decision.state,
            target_model_label=decision.label,
            target_pk=target_pk,
        )


__all__ = ["BATCH_ROWS", "NULL_TOKEN", "Decision", "JournalBatchWriter", "TargetMaterialiser", "normalized_key"]

"""Phase: ``worker_materialisation`` — müəllim yerləşdirmə + aktivasiya.

Bu faza HEÇ BİR mənbə cədvəli hesabatına sahib deyil (``source_tables = ()``):
``workers`` artıq ``identity_cohort`` tərəfindən iddia olunub və bir cədvəl
yalnız bir dəfə iddia oluna bilər.  Yenə də EYNİ audited kontrakt
(``WORKER_IDENTITY_FIELDS``) üzərindən oxuyur — ``department_id``,
``teacher_type`` və ``inzibati`` proyeksiyada ONSUZ DA var, ona görə heç bir
kontrakt barmaq izi dəyişmir (mənbə faktları bölməsi).

Fazanın işi (V-22..V-27): identity-nin stage etdiyi hər worker hesabını
(1) öz kafedrasına scope-lamaq — ``Membership.scope_unit`` ←
``myedu-dep-{department_id}`` slug-lu OrgUnit (yalnız NULL→dəyər, V-24/V-27) —
və (2) SAR fazasındakı eyni körpü ilə aktivləşdirmək (V-25).  ROL DƏYİŞMİR
(V-23): ``inzibati``/``teacher_type`` yalnız INFO issue kimi qeyd olunur.

Zəncir hər sətir üçün artan ``legacy_pk`` sırasında düz
``(legacy_pk, state, derivation_hash, label)`` ilə irəliləyir — MIGRATED
sətirdə ``label`` ``auth.user``-dir, əks halda boşdur; bu, bayt-bəbayt
``rehearsal_reconciliation._derived_phase_report_from_ledger``-in yenidən
qurduğu formadır (SA-2).

V-25 ortaq kapı: ``max_activated_accounts`` worker+SAR aktivasiyalarının
CƏMİNƏ şamildir — sayğac bu run-un SAR MIGRATED müşahidələri ilə başlayır və
``rehearsal_sar_phase`` də simmetrik olaraq worker istehlakı ilə başlayır.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from types import MappingProxyType

from django.apps import apps as django_apps

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation

from .field_contracts import WORKER_IDENTITY_FIELDS
from .legacy_text import clean_text, legacy_slug
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_authorizer import USER_MODEL_LABEL
from .rehearsal_contracts import (
    IDENTITY_COHORT_MAX_ROWS,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PhaseReport,
    RehearsalContext,
    source_row_hash,
)
from .rehearsal_identity_phase import IDENTITY_PHASE_KEY, WORKER_ENTITY_TYPE
from .rehearsal_sar_targets import SAR_ENTITY_TYPE, account_is_active, assert_activation_actor
from .rehearsal_structure_phase import STRUCTURE_PHASE_KEY, probe_cancellation
from .rehearsal_worker_targets import (
    WORKER_MATERIALISATION_ENTITY_TYPE,
    WORKER_SOURCE_TABLE,
    WorkerRequest,
    materialise_worker,
    migrated_observation_count,
    resolve_worker_role,
    seal_unscoped,
    worker_activation_evidence_digest,
    write_issues,
)
from .source_extraction import open_audited_source_stream

WORKER_PHASE_KEY = "worker_materialisation"
#: ``auth_user.first_name``/``last_name`` sütun limiti (placement ilə eyni).
NAME_MAX_LENGTH = 150
#: ``UserProfile.patronymic`` sütun limiti.
PATRONYMIC_MAX_LENGTH = 100

WORKER_PHASE_ORDER = 26  # placement-dən (25) sonra, SAR-dan (28) əvvəl
DERIVED_DIGEST_NAMESPACE = "legacy-rehearsal-worker-phase-v1"
REQUIRED_PHASE_KEYS = frozenset({STRUCTURE_PHASE_KEY, IDENTITY_PHASE_KEY})
DEPARTMENT_SLUG_KIND = "dep"  # academic_structure-un yaratdığı slug ailəsi

_STATE = LegacyEntityMap.State

# Token state açarları, migrated/skipped/quarantined DEYİL: derived qərar
# operator-üzlü ``totals.{migrated,skipped,quarantined}`` proyeksiyasına
# əlavə olunmamalıdır.
DERIVED_STATE_KEYS = MappingProxyType(
    {
        _STATE.MIGRATED: "worker_materialised",
        _STATE.SKIPPED: "worker_deferred",
        _STATE.QUARANTINED: "worker_unresolved",
    }
)


def _legacy_int(value: object) -> int:
    """Legacy tam sütun; ``NULL`` MySQL-in yazdığı eyni sıfır sentinelidir."""

    if value is None:
        return 0
    # ``type() is int`` bool üçün onsuz da False-dur: bayraqlar fatal qalır.
    if type(value) is not int:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_value_type_unsupported")
    return value


def worker_index(context: RehearsalContext) -> dict[str, str]:
    """BU run-un staged worker-ləri: ``legacy_pk`` → ``auth.user`` açarı."""

    rows = list(
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            state=_STATE.MIGRATED,
            target_model_label=USER_MODEL_LABEL,
            entity_map__entity_type=WORKER_ENTITY_TYPE,
        ).values_list("entity_map__legacy_pk", "target_pk")
    )
    if len(rows) > IDENTITY_COHORT_MAX_ROWS:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_cohort_too_large")
    return dict(rows)


def department_unit_index(context: RehearsalContext) -> dict[str, str]:
    """``myedu-dep-{id}`` slug → OrgUnit açarı (V-24, hərfi slug həlli).

    Slug tenant daxilində unikaldır (``unique_together (organization, slug)``),
    ona görə axtarış deterministikdir və ambiguity mümkün deyil.
    """

    prefix = f"myedu-{DEPARTMENT_SLUG_KIND}-"
    return {
        str(row["slug"]): str(row["id"])
        for row in django_apps.get_model("organizations", "OrgUnit")
        .objects.filter(organization=context.organization, slug__startswith=prefix)
        .values("id", "slug")
    }


def worker_rows(context: RehearsalContext):
    """``workers``-i attested, ciddi artan primary-key sırasında axıt."""

    entry = context.plan.entry_for(WORKER_SOURCE_TABLE)
    previous_pk = 0
    observed = 0
    with open_audited_source_stream(
        connection_factory=context.source_connection_factory,
        contract=WORKER_IDENTITY_FIELDS,
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


def _recorded_decision(context: RehearsalContext, legacy_pk: str):
    """Resume qısayolu: möhürlənmiş qərarı yenidən törətmək əvəzinə oxu."""

    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            entity_map__entity_type=WORKER_MATERIALISATION_ENTITY_TYPE,
            entity_map__legacy_pk=legacy_pk,
        )
        .values_list("state", "source_row_hash", "target_model_label")
        .first()
    )


class WorkerMaterialisationPhase:
    """V-24 scope yazısı və V-25 aktivasiya körpüsü, işçi başına bir qərar."""

    phase_key = WORKER_PHASE_KEY
    order = WORKER_PHASE_ORDER
    source_tables = ()
    entity_types = (WORKER_MATERIALISATION_ENTITY_TYPE,)
    derived_digest_namespace = DERIVED_DIGEST_NAMESPACE  # SA-2 hook

    def declared_source_rows(self, plan) -> int:
        return 0

    def derived_state_key(self, state) -> str:  # SA-2 hook
        return DERIVED_STATE_KEYS[str(state)]

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        if not REQUIRED_PHASE_KEYS <= set(context.policy.phase_keys):
            # Evidence, Config deyil: orkestrator run-u RUNNING saxlamaq əvəzinə
            # məhz bu kodla FAILED bitirir.
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_dependency_missing")
        probe_cancellation(context)

        workers = worker_index(context)
        units = department_unit_index(context)
        role = None
        if context.policy.stage_and_activate:
            # Açar bağlıdırsa hər iki pre-flight ötürülür: aktivasiya etməyən
            # run az-səlahiyyətli aktora və ya rolsuz tenant-a görə çökməməlidir.
            assert_activation_actor(context)
            role = resolve_worker_role(context)

        chain = OrderedDigest(DERIVED_DIGEST_NAMESPACE)
        state_counts: Counter[str] = Counter()
        issue_counts: Counter[tuple[str, str]] = Counter()
        # V-25: kap worker+SAR CƏMİNƏ şamildir — bu run-da SAR artıq nə qədər
        # aktivləşdiribsə, büdcə oradan başlayır.
        activated = migrated_observation_count(context, SAR_ENTITY_TYPE)
        for legacy_pk, row in worker_rows(context):
            legacy_pk_text = str(legacy_pk)
            if legacy_pk_text not in workers:
                continue  # bu run stage etməyib: nə map, nə issue, nə sayğac
            probe_cancellation(context)
            recorded = _recorded_decision(context, legacy_pk_text)
            if recorded is not None:
                state, digest, label = recorded
                # Resume olunan MIGRATED sətir kapa SAYILIR (SAR-dakı
                # 2026-08-26 tapıntısı ilə eyni qayda).
                activated += 1 if state == _STATE.MIGRATED else 0
            else:
                state, digest, label, promoted = self._decide(
                    context,
                    legacy_pk=legacy_pk,
                    row=row,
                    user_pk=workers[legacy_pk_text],
                    units=units,
                    role=role,
                    activated=activated,
                    issue_counts=issue_counts,
                )
                activated += promoted
            chain.advance(legacy_pk_text, str(state), digest, label)
            state_counts[self.derived_state_key(state)] += 1

        context.stdout_note(f"{WORKER_PHASE_KEY}.records.{sum(state_counts.values())}")
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=(),
            declared_source_rows=0,
            observed_source_rows=0,
            batches=(),
            # Yalnız MÜŞAHİDƏ olunmuş açarlar: ledger rebuild çılpaq Counter
            # qurur, öncədən əkilmiş sıfır ``--emit-report-only``-ni pozardı.
            state_counts=dict(state_counts),
            issue_counts=MappingProxyType(dict(issue_counts)),
            staged_account_count=0,
            phase_digest=chain.hexdigest(),
        )

    def _decide(self, context, *, legacy_pk, row, user_pk, units, role, activated, issue_counts):
        """V-24 → V-25 nərdivanı, yuxarıdan aşağı; hər pillə öz sətrini möhürləyir."""

        department_id = _legacy_int(row["department_id"])
        teacher_type = _legacy_int(row["teacher_type"])
        inzibati = _legacy_int(row["inzibati"])
        # V-23: mənbə faktları yalnız INFO olur; rol qərarına çevrilmir.
        info_codes: list[str] = []
        if inzibati == 1:
            info_codes.append("legacy_worker_administrative_flag")
        if teacher_type not in (1, 2, 3):
            info_codes.append("legacy_worker_type_unknown")

        department_slug = (
            legacy_slug(DEPARTMENT_SLUG_KIND, department_id) if 1 <= department_id <= MAX_LEDGER_PRIMARY_KEY else ""
        )
        unit_pk = units.get(department_slug, "") if department_slug else ""
        row_hash = source_row_hash(contract=WORKER_IDENTITY_FIELDS, legacy_pk=legacy_pk, projected_row=row)
        first_name, _truncated_first = clean_text(row["first_name"], max_length=NAME_MAX_LENGTH)
        last_name, _truncated_last = clean_text(row["last_name"], max_length=NAME_MAX_LENGTH)
        patronymic, _truncated_patronymic = clean_text(row["father_name"], max_length=PATRONYMIC_MAX_LENGTH)
        request = WorkerRequest(
            legacy_pk=legacy_pk,
            user_pk=user_pk,
            row_hash=row_hash,
            department_slug=department_slug,
            unit_pk=unit_pk,
            teacher_type_text=str(teacher_type),
            inzibati_text=str(inzibati),
            role=role,
            evidence_digest="",
            needs_activation=False,
            first_name=first_name,
            last_name=last_name,
            patronymic=patronymic,
        )

        if not unit_pk:
            # V-24: OrgUnit yoxdur — SKIPPED, hazırkı dump-da 0 gözlənilir.
            outcome = seal_unscoped(
                context, request=request, rule_codes=("legacy_worker_department_unresolved", *info_codes)
            )
            return self._account(context, request, outcome, issue_counts)
        if not context.policy.stage_and_activate:
            # V-25: açar bağlıdır — faza yalnız scope yazır, aktivasiya ETMİR.
            # 715 eyni INFO sətri xalis səs-küy olardı; sayı ``worker_deferred``
            # onsuz da deyir.
            outcome = materialise_worker(context, request=request, activate=False, activation_state="disabled")
            return self._account(context, request, outcome, issue_counts, extra_codes=tuple(info_codes))
        if activated >= context.policy.max_activated_accounts:
            outcome = materialise_worker(context, request=request, activate=False, activation_state="capped")
            return self._account(
                context,
                request,
                outcome,
                issue_counts,
                extra_codes=("legacy_worker_activation_cap_reached", *info_codes),
            )

        needs_activation = not account_is_active(context, user_pk)
        # ``replace``, YENİDƏN QURMA DEYİL: sıfırdan qurulan sorğu ad/soyad/ata
        # adını səssizcə itirirdi (aktivasiya yolunda hər üçü boş gedirdi) —
        # yeni sahə əlavə olunanda eyni tələ təkrarlanmasın.
        request = replace(
            request,
            evidence_digest=worker_activation_evidence_digest(
                transform_version=context.policy.transform_version(),
                snapshot_sha256=context.plan.source_snapshot_sha256,
                legacy_pk=legacy_pk,
            ),
            needs_activation=needs_activation,
        )
        outcome = materialise_worker(
            context,
            request=request,
            activate=True,
            activation_state="activated" if needs_activation else "preexisting",
        )
        return self._account(context, request, outcome, issue_counts, extra_codes=tuple(info_codes))

    def _account(self, context, request, outcome, issue_counts, *, extra_codes=()):
        """Issue-ları yaz və zəncirin gözlədiyi 4-lüyü qaytar."""

        write_issues(
            context,
            legacy_pk=str(request.legacy_pk),
            digest=outcome.digest,
            entity_map=outcome.entity_map,
            rule_codes=(*outcome.rule_codes, *extra_codes),
            issue_counts=issue_counts,
        )
        label = USER_MODEL_LABEL if outcome.state == _STATE.MIGRATED else ""
        return outcome.state, outcome.digest, label, 1 if outcome.state == _STATE.MIGRATED else 0

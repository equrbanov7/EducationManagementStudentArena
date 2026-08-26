"""Target side of ``worker_materialisation``: scope yazısı, aktivasiya, seal.

Üç şey burada yaşayır və başqa heç nə — kafedra scope yazısı (V-24), SAR
fazasındakı EYNİ aktivasiya körpüsü (V-25) və ledger seal-ları.  Faza modulu
iterasiyaya, indekslərə və digest zəncirinə sahibdir.

V-23: ROL YÜKSƏLTMƏ YOXDUR.  ``teacher_type``/``inzibati`` nə olursa olsun
hər kəs ``identity_cohort``-un verdiyi ``teacher`` rolunda qalır; bu modul rola
ümumiyyətlə TOXUNMUR — yalnız ``Membership.scope_unit`` NULL→dəyər keçidini və
mövcud SECURITY DEFINER aktivasiya yolunu icra edir (V-27).

Aktivasiya körpüsü SAR-dakı kimi shipped ``apps.accounts.public``
``activate_staged_account``-ı hərfiyyən çağırır; dərhal ondan sonra, EYNİ
transaction içində legacy e-mail neytrallaşdırılır (E-11): aktivasiya
*qurumun reyestri bu şəxsin mövcudluğunu deyir* iddiasıdır, heç vaxt *bu ünvan
təsdiqlənib* deyil.

``except`` qəsdən ``transaction.atomic()``-dən BAYIRDA oturur: PostgreSQL
``23514``/``42501`` imtinası tranzaksiyanı zəhərləyir, ona görə imtinanı
HESABATA salan ledger sətri təzə tranzaksiyada yazılmalıdır — bu,
``rehearsal_sar_targets.materialise_record`` forması ilə eyni səbəbdəndir.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from types import MappingProxyType

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .field_contracts import WORKER_IDENTITY_FIELDS
from .ledger import upsert_entity_map, upsert_issue
from .rehearsal_authorizer import USER_MODEL_LABEL
from .rehearsal_contracts import LegacyRehearsalConfigError, LegacyRehearsalEvidenceError, encoded_part

WORKER_MATERIALISATION_ENTITY_TYPE = "worker_materialisation"
# ``LegacyMigrationIssue`` (run, source_table, legacy_pk, rule_code) üzrə
# unikaldır və ``identity_cohort`` eyni cədvəl altında ``legacy_account_*``
# yazır, ona görə buradakı hər kod ``legacy_worker_`` prefiksi daşıyır.
WORKER_SOURCE_TABLE = "workers"
ACTIVATION_REASON_CODE = "signed_authoritative_export"  # AccountActivationEvidence.Reason

_ACTIVATION_EVIDENCE_PREFIX = b"legacy-rehearsal-activation-evidence-v1\x00"
_DERIVATION_PREFIX = b"legacy-rehearsal-worker-derivation-v1\x00"
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State
_TARGET_MISSING = "legacy_rehearsal_resume_target_missing"
_REFUSAL_TYPES: tuple[type[BaseException], ...] = ()

# Xəta taksonomiyası.  Çatışmayan açar INFO-ya düşmək əvəzinə fail-closed olur.
# E-13: burada heç nə ERROR deyil — ilk worker rehearsal-ı SUCCEEDED-ə çatıb
# tam histoqram verə bilməlidir.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                "legacy_worker_department_unresolved",
                "legacy_worker_activation_cap_reached",
                "legacy_worker_activation_refused",
                "legacy_worker_scope_refused",
            ),
            _SEVERITY.WARNING,
        ),
        # V-23: inzibati/teacher_type mənbə FAKTLARIDIR, anomaliya deyil; rol
        # yüksəltmə RİM-in əl qərarına saxlanılır (backlog).
        **dict.fromkeys(
            (
                "legacy_worker_administrative_flag",
                "legacy_worker_type_unknown",
                "legacy_worker_scope_preexisting",
            ),
            _SEVERITY.INFO,
        ),
    }
)


@dataclass(frozen=True)
class WorkerRequest:
    """Bir işçinin scope-və-aktivasiya vahid işinin ehtiyacı olan hər şey."""

    legacy_pk: int
    user_pk: str
    row_hash: str
    department_slug: str
    unit_pk: str
    teacher_type_text: str
    inzibati_text: str
    role: object
    evidence_digest: str
    needs_activation: bool
    # Mənbədəki ad/soyad/ata adı — YALNIZ boş sahəni doldurmaq üçün (bax
    # ``write_worker_names`` / ``write_worker_patronymic``); tələbə tərəfindəki
    # müqavilə ilə eynidir.
    first_name: str = ""
    last_name: str = ""
    patronymic: str = ""


@dataclass(frozen=True)
class WorkerOutcome:
    """Bir sətrin möhürlənmiş nəticəsi: ledger state, digest, map, issue-lar."""

    state: str
    digest: str
    entity_map: object
    rule_codes: tuple[str, ...]
    activation_state: str
    scope_state: str


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def _refusal_types() -> tuple[type[BaseException], ...]:
    """Aktivasiyanın ata biləcəyi imtina tipləri (fasad onları ixrac etmir)."""

    global _REFUSAL_TYPES
    if not _REFUSAL_TYPES:
        from apps.accounts.services.identity_access import IdentityAccessError

        _REFUSAL_TYPES = (IdentityAccessError, PermissionDenied, DatabaseError)
    return _REFUSAL_TYPES


def migrated_observation_count(context, entity_type: str) -> int:
    """BU run-un MIGRATED müşahidə sayı — V-25 ortaq kap hesabının yarısı.

    ``max_activated_accounts`` worker+SAR aktivasiyalarının CƏMİNƏ şamildir:
    hər faza öz sayğacını o biri fazanın bu run-da artıq istehlak etdiyi
    büdcə ilə başladır.
    """

    return LegacyEntityObservation.objects.filter(
        run_id=context.run_id, state=_STATE.MIGRATED, entity_map__entity_type=entity_type
    ).count()


def worker_activation_evidence_digest(*, transform_version: str, snapshot_sha256: str, legacy_pk: int) -> str:
    """Aktivasiya sübutu, pinned snapshot-dan deterministik (V-25, §7).

    ``rehearsal_sar_targets.activation_evidence_digest`` ilə eyni resept və eyni
    prefiks; yalnız entity hissəsi ``worker``-dir, ona görə eyni legacy_pk-lı
    tələbə və işçi heç vaxt eyni sübutu bölüşə bilməz.
    """

    digest = hashlib.sha256(_ACTIVATION_EVIDENCE_PREFIX)
    for part in (transform_version, snapshot_sha256, "worker", str(legacy_pk)):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def worker_derivation_hash(
    *,
    legacy_pk: int,
    row_hash: str,
    outcome_token: str,
    department_slug: str,
    scope_state: str,
    teacher_type_text: str,
    inzibati_text: str,
    activation_state: str,
    name_state: str = "unwritten",
    patronymic_state: str = "unwritten",
) -> str:
    """Cross-run-sabit worker qərar kimliyi; heç bir UUID ona daxil olmur.

    ``upsert_entity_map`` bunu map-ın kanonik dəyərlərinə qatlayır, ona görə
    fərqli qərar törədən resume cəhdi ledger-in özü tərəfindən
    ``legacy_entity_identity_conflict`` kimi rədd edilir.
    """

    digest = hashlib.sha256(_DERIVATION_PREFIX)
    for part in (
        WORKER_IDENTITY_FIELDS.fingerprint,
        str(legacy_pk),
        row_hash,
        outcome_token,
        department_slug,
        scope_state,
        teacher_type_text,
        inzibati_text,
        activation_state,
        name_state,
        patronymic_state,
    ):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def resolve_worker_role(context):
    """``identity_cohort``-un stage etdiyi EYNİ rol (V-23): bir siyasət adı."""

    role = (
        django_apps.get_model("organizations", "Role")
        .objects.filter(organization=context.organization, name=context.policy.worker_role_name, is_active=True)
        .first()
    )
    if role is None:
        raise LegacyRehearsalConfigError("legacy_rehearsal_worker_role_unavailable")
    return role


def write_worker_names(target_pk: str, first_name: str, last_name: str) -> str:
    """Boş ad sahələrini doldur; MÖVCUD dəyər heç vaxt üzərinə yazılmır.

    ``student_placement._write_names`` ilə eyni müqavilə (§4.5): idxal yalnız
    boşluğu doldurur, əl ilə düzəldilmiş adı pozmur.  ``auth_user``-in bu
    sütunlarında trigger yoxdur (0013 yalnız ``username``/``email``/``is_active``
    üzərindədir), ona görə accounts servis qapısı tətbiq olunmur.
    """

    users = django_apps.get_model("auth", "User")._default_manager.filter(pk=target_pk)
    row = users.values("first_name", "last_name").first()
    if row is None:
        raise LegacyRehearsalEvidenceError(_TARGET_MISSING)
    updates = {}
    if first_name and not row["first_name"]:
        updates["first_name"] = first_name
    if last_name and not row["last_name"]:
        updates["last_name"] = last_name
    if updates:
        users.update(**updates)
        return "written"
    return "blank" if not first_name and not last_name else "preserved"


def write_worker_patronymic(context, *, user_pk: str, patronymic: str) -> str:
    """Boş ``UserProfile.patronymic``-i doldur; MÖVCUD dəyər pozulmur.

    Ata adı Azərbaycanda kimliyin üçüncü hissəsidir və RİM axtarışı hesabı məhz
    ad+soyad+ATA ADI üçlüyü ilə tapır (``auth_user``-də belə sütun yoxdur).
    Profil ``_neutralise_legacy_email`` və ``_apply_fin`` ilə eyni cür tenant-a
    bağlı seçilir: RLS altında yalnız öz təşkilatının sətri görünür.
    """

    if not patronymic:
        return "blank"
    profiles = django_apps.get_model("accounts", "UserProfile").objects.filter(
        user_id=user_pk, organization=context.organization
    )
    row = profiles.values("patronymic").first()
    if row is None:
        raise LegacyRehearsalEvidenceError(_TARGET_MISSING)
    if row["patronymic"]:
        return "preserved"
    if profiles.filter(patronymic="").update(patronymic=patronymic, updated_at=timezone.now()) != 1:
        raise LegacyRehearsalEvidenceError(_TARGET_MISSING)
    return "written"


def apply_scope(context, *, user_pk: str, unit_pk: str) -> tuple[str, tuple[str, ...]]:
    """V-24 scope yazısı: yalnız NULL→dəyər; mövcud fərqli dəyərə TOXUNMA."""

    membership_model = django_apps.get_model("organizations", "Membership")
    rows = list(
        membership_model.objects.filter(user_id=user_pk, organization=context.organization)
        .order_by("pk")
        .values("id", "scope_unit_id")
    )
    if not rows:
        raise LegacyRehearsalEvidenceError(_TARGET_MISSING)
    if len(rows) != 1:
        # ``identity_cohort`` düz BİR üzvlük stage edir; ikinci sətir sübutun
        # planla ziddiyyətidir və heç bir yazı təxminlə seçilə bilməz.
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_worker_membership_ambiguous")
    current = rows[0]["scope_unit_id"]
    if current is None:
        updated = membership_model.objects.filter(pk=rows[0]["id"], scope_unit_id__isnull=True).update(
            scope_unit_id=unit_pk, updated_at=timezone.now()
        )
        if updated != 1:
            raise LegacyRehearsalEvidenceError(_TARGET_MISSING)
        return "written", ()
    if str(current) == str(unit_pk):
        return "preserved", ()  # idempotent replay: artıq bizim yazımızdır
    return "preexisting", ("legacy_worker_scope_preexisting",)


def _neutralise_legacy_email(context, user_pk: str) -> None:
    """E-11: legacy ünvan MÖVCUDLUQ üçün etibarlıdır, etimad üçün heç vaxt."""

    django_apps.get_model("accounts", "UserProfile").objects.filter(
        user_id=user_pk, organization=context.organization
    ).update(email_verified=False, password_change_required=True, updated_at=timezone.now())


def _activate(context, *, request: WorkerRequest) -> None:
    from apps.accounts.public import activate_staged_account

    activate_staged_account(
        user=django_apps.get_model("auth", "User")._default_manager.filter(pk=request.user_pk).first(),
        organization=context.organization,
        expected_role=request.role,
        actor=context.actor,
        email_authoritative=True,
        email_authority_evidence_digest=request.evidence_digest,
        email_authority_reason_code=ACTIVATION_REASON_CODE,
    )
    _neutralise_legacy_email(context, request.user_pk)


def _seal(context, *, legacy_pk: str, digest: str, state: str, label: str = "", target_pk: str = ""):
    return upsert_entity_map(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        entity_type=WORKER_MATERIALISATION_ENTITY_TYPE,
        legacy_pk=legacy_pk,
        source_row_hash=digest,
        state=state,
        target_model_label=label,
        target_pk=target_pk,
        target_validators=context.target_validators,
    )


def seal_unscoped(context, *, request: WorkerRequest, rule_codes: tuple[str, ...]) -> WorkerOutcome:
    """V-24: OrgUnit tapılmadı — SKIPPED, heç bir target yazısı yoxdur."""

    digest = worker_derivation_hash(
        legacy_pk=request.legacy_pk,
        row_hash=request.row_hash,
        outcome_token="deferred",
        department_slug=request.department_slug,
        scope_state="unresolved",
        teacher_type_text=request.teacher_type_text,
        inzibati_text=request.inzibati_text,
        activation_state="unscoped",
    )
    entity_map = _seal(context, legacy_pk=str(request.legacy_pk), digest=digest, state=_STATE.SKIPPED)
    return WorkerOutcome(_STATE.SKIPPED, digest, entity_map, rule_codes, "unscoped", "unresolved")


def materialise_worker(context, *, request: WorkerRequest, activate: bool, activation_state: str) -> WorkerOutcome:
    """Scope yazısı və (lazımsa) aktivasiya BİR unit of work içində (V-25)."""

    rule_codes: list[str] = []
    stage = "scope"
    try:
        with transaction.atomic():
            scope_state, scope_rules = apply_scope(context, user_pk=request.user_pk, unit_pk=request.unit_pk)
            rule_codes.extend(scope_rules)
            # Ad/soyad EYNİ vahid işdə: idxal edilən müəllim UI-da öz adı ilə
            # görünməlidir (yalnız boş sahə doldurulur — §4.5 müqaviləsi).
            name_state = write_worker_names(request.user_pk, request.first_name, request.last_name)
            patronymic_state = write_worker_patronymic(context, user_pk=request.user_pk, patronymic=request.patronymic)
            if activate:
                stage = "activation"
                if request.needs_activation:
                    _activate(context, request=request)
                state, outcome_token = _STATE.MIGRATED, "materialised"
            else:
                # ``--stage-and-activate`` False (silent) və ya kap dolub: faza
                # yalnız scope yazır, hesab STAGED qalır.
                state, outcome_token = _STATE.SKIPPED, "deferred"
            digest = worker_derivation_hash(
                legacy_pk=request.legacy_pk,
                row_hash=request.row_hash,
                outcome_token=outcome_token,
                department_slug=request.department_slug,
                scope_state=scope_state,
                teacher_type_text=request.teacher_type_text,
                inzibati_text=request.inzibati_text,
                activation_state=activation_state,
                name_state=name_state,
                patronymic_state=patronymic_state,
            )
            entity_map = _seal(
                context,
                legacy_pk=str(request.legacy_pk),
                digest=digest,
                state=state,
                label=USER_MODEL_LABEL if state == _STATE.MIGRATED else "",
                target_pk=request.user_pk if state == _STATE.MIGRATED else "",
            )
    except _refusal_types():
        # Tranzaksiya artıq geri qaytarılıb: yarı-aktivləşmiş hesab da,
        # yarı-yazılmış scope da yoxdur.  ``activation_state`` hansı yarıya
        # çatdığımızı yenə də qeyd edir.
        refused = "legacy_worker_activation_refused" if stage == "activation" else "legacy_worker_scope_refused"
        if stage == "activation":
            activation_state = "refused"
        digest = worker_derivation_hash(
            legacy_pk=request.legacy_pk,
            row_hash=request.row_hash,
            outcome_token="unresolved",
            department_slug=request.department_slug,
            scope_state="refused",
            teacher_type_text=request.teacher_type_text,
            inzibati_text=request.inzibati_text,
            activation_state=activation_state,
        )
        entity_map = _seal(context, legacy_pk=str(request.legacy_pk), digest=digest, state=_STATE.QUARANTINED)
        return WorkerOutcome(_STATE.QUARANTINED, digest, entity_map, (refused,), activation_state, "refused")
    return WorkerOutcome(state, digest, entity_map, tuple(rule_codes), activation_state, scope_state)


def write_issues(context, *, legacy_pk: str, digest: str, entity_map, rule_codes, issue_counts) -> None:
    """Issue-lar həmişə öz map-ından sonra: ledger əks sıranı rədd edir."""

    for rule_code in rule_codes:
        severity = severity_for(rule_code)
        upsert_issue(
            run_id=context.run_id,
            actor=context.actor,
            authorize=context.authorize,
            source_table=WORKER_SOURCE_TABLE,
            entity_type=WORKER_MATERIALISATION_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            rule_code=rule_code,
            severity=severity,
            payload_digest=digest,
            entity_map_id=entity_map.pk,
        )
        issue_counts[(rule_code, severity)] += 1

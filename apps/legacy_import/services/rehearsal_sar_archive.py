"""Arxiv qolu: ``students.azadedildi=1`` (V-18) hesabları üçün hədəf tərəfi.

Niyə ayrı qol. Məzun/xaric tələbənin hesabı ``is_active=False`` qaldığı müddətdə
``registrar_guard_active_member`` (0041 trigger + 0042 funksiya) NƏ ``Enrollment``,
NƏ ``StudentAcademicRecord`` sətrini qəbul etmir — çünki funksiya DÖRD şərtin
hamısını tələb edir: ``organization.is_active``, ``membership.is_active``,
``role.is_active`` və ``auth_user.is_active``. Nəticədə mənbənin ~30%-i (içində
36 399 imtahan balı) köçə bilmirdi.

Bu qol həmin qapını AÇIR, giriş qapısını isə BAĞLI SAXLAYIR:

* üzvlüyün rolu ``student`` → ``alumni`` (icazə dəsti BOŞ) edilir — trigger
  ``required_permission = ''`` ilə çağırıldığı üçün boş dəst kifayətdir;
* ``apps.accounts.public.archive_staged_account`` hesabı OLDUĞU KİMİ
  ``activate_staged_account`` qapılarından keçirir (aktor icazəsi, tenant,
  evidence, audit), sonra EYNİ tranzaksiyada profili ``archived`` edir;
* giriş ``identity.user_access_is_login_blocked`` ilə bütün autentifikasiya
  səthlərində bağlanır — portal təsnifatı QAPI DEYİL.

Qəbul ili həll olunmayan hal (A2). ``StudentAcademicRecord.admission_year``
``PositiveIntegerField()`` — NULL qəbul ETMİR; ``curriculum`` da NOT NULL-dur və
``uniq_curriculum_program_year`` açarında qəbul ilinə bağlıdır. Yəni «ilsiz SAR»
model səviyyəsində mümkün deyil. Ölçü isə göstərir ki, SAR-sız üzvlük tək başına
kifayət etmir: ÇOX qruplu jurnalda ``rehearsal_journal_slices.student_unit_index``
tələbənin qrupunu MƏHZ ``StudentAcademicRecord.group``-dan oxuyur, ona görə SAR
yoxdursa həmin xanalar ``legacy_journal_student_group_mismatch`` ilə itir
(Rehearsal ölçüsü: 8 922 sətir).

Ona görə arxiv qolu ili UYDURMUR, ``ARCHIVE_FALLBACK_ADMISSION_YEAR``
SENTİNELİNİ yazır: attestasiya olunmuş qəbul ili domeninin DÖŞƏMƏSİ (1950).
Bu, real qəbul ili ilə qarışa bilməyəcək qədər açıq bir dəyərdir, deterministikdir
və hər sətir ``legacy_sar_admission_year_fallback`` (WARNING) ilə işarələnir, ona
görə sonradan həqiqi il tapılanda düzəliş üçün tam siyahı hazırdır. SAR yalnız
proqram həll olunmayanda (``program_pk`` boş) buraxılır.

Akademik status qəsdən ``enrolled`` qalır: legacy ``azadedildi`` bayrağı
məzunla xaric edilməni AYIRMIR, ona görə burada ``graduated``/``expelled``
UYDURULMUR. Məzunluq faktı ``alumni`` üzvlüyü və ``legacy_sar_archived_student``
issue kodu ilə qeyd olunur.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap

from .rehearsal_authorizer import STUDENT_RECORD_MODEL_LABEL
from .rehearsal_contracts import LegacyRehearsalConfigError
from .rehearsal_sar_targets import (
    ACTIVATION_REASON_CODE,
    RecordOutcome,
    _bind_curriculum,
    _ensure_record,
    _neutralise_legacy_email,
    _refusal_types,
    _seal,
    sar_derivation_hash,
)
from .rehearsal_structure_source import MIN_ADMISSION_YEAR

#: ``activation_evidence_digest`` üçün subyekt etiketi — arxiv qolu tələbə
#: qolundan FƏRQLİ evidence üretir, beləcə iki qərar bir-birinə qarışa bilmir.
ARCHIVE_EVIDENCE_SUBJECT = "alumni"

#: Qəbul ili həll olunmayan sətir üçün sentinel: attestasiya olunmuş domenin
#: döşəməsi. Təxmin deyil — «bu il məlum deyil» sözünün model icazə verdiyi
#: yeganə formasıdır və ``legacy_sar_admission_year_fallback`` ilə hesabatda
#: açıq görünür.
#:
#: 2026-09-02: sentinel artıq YALNIZ arxiv qoluna aid deyil — qəbul ili
#: bilinməyən AKTİV tələbə də onu daşıyır (bax ``rehearsal_sar_phase`` §A2-fix),
#: ona görə neytral ad kanonikdir; ``ARCHIVE_*`` adı geri-uyğunluq üçün qalır.
FALLBACK_ADMISSION_YEAR = MIN_ADMISSION_YEAR
ARCHIVE_FALLBACK_ADMISSION_YEAR = FALLBACK_ADMISSION_YEAR

_STATE = LegacyEntityMap.State


def resolve_archive_role(context):
    """Arxiv üzvlüyünün rolu — ``alumni``; yoxdursa run fail-closed dayanır."""

    from apps.accounts.public import ARCHIVE_ROLE_NAME

    role = (
        django_apps.get_model("organizations", "Role")
        .objects.filter(organization=context.organization, name=ARCHIVE_ROLE_NAME, is_active=True)
        .first()
    )
    if role is None:
        raise LegacyRehearsalConfigError("legacy_rehearsal_sar_archive_role_unavailable")
    return role


def account_is_archived(context, user_pk: str) -> bool:
    """Təkrar run / davam etdirilmiş run: mövcud arxiv olduğu kimi qəbul olunur."""

    profile_model = django_apps.get_model("accounts", "UserProfile")
    return profile_model.objects.filter(
        user_id=user_pk,
        organization=context.organization,
        access_state=profile_model.AccessState.ARCHIVED,
        user__is_active=True,
    ).exists()


def _retarget_membership(context, *, user_pk: str, role) -> None:
    """Staged (deaktiv) üzvlüyün rolunu arxiv rolu ilə əvəz edir.

    ``activate_staged_account`` DƏQİQ bir üzvlük və DƏQİQ ``expected_role``
    tələb edir, staged üzvlük isə ``student`` rolu ilə yaradılıb. Üzvlük hələ
    deaktiv olduğu üçün bu dəyişiklik heç bir hüquq vermir.
    """

    membership_model = django_apps.get_model("organizations", "Membership")
    membership_model.objects.filter(user_id=user_pk, organization=context.organization, is_active=False).exclude(
        role_id=role.pk
    ).update(role_id=role.pk)


def _archive(context, *, request, role) -> None:
    from apps.accounts.public import archive_staged_account

    _retarget_membership(context, user_pk=request.user_pk, role=role)
    archive_staged_account(
        user=django_apps.get_model("auth", "User")._default_manager.filter(pk=request.user_pk).first(),
        organization=context.organization,
        expected_role=role,
        actor=context.actor,
        email_authoritative=True,
        email_authority_evidence_digest=request.evidence_digest,
        email_authority_reason_code=ACTIVATION_REASON_CODE,
    )
    _neutralise_legacy_email(context, request.user_pk)


def materialise_archive(context, *, request, role, write_record: bool) -> RecordOutcome:
    """Arxivləşdir (lazımdırsa) və SAR-ı BİR iş vahidində yaz (§8 ilə eyni forma)."""

    year_text = str(request.admission_year)
    activation_state = "archived" if request.needs_activation else "preexisting_archive"
    rule_codes: list[str] = ["legacy_sar_archived_student"]
    stage = "activation"
    try:
        with transaction.atomic():
            if request.needs_activation:
                _archive(context, request=request, role=role)
            stage = "write"
            if not write_record:
                # Üzvlük quruldu, amma il/proqram həll olunmadı → SAR YOX.
                digest = sar_derivation_hash(
                    legacy_pk=request.legacy_pk,
                    placement_row_hash=request.placement_row_hash,
                    outcome_token="archived",
                    program_code=request.program_code,
                    group_slug=request.group_slug,
                    admission_year_text="" if not request.admission_year else year_text,
                    curriculum_source="none",
                    curriculum_key="",
                    activation_state=activation_state,
                )
                entity_map = _seal(context, legacy_pk=str(request.legacy_pk), digest=digest, state=_STATE.SKIPPED)
                return RecordOutcome(_STATE.SKIPPED, digest, entity_map, tuple(rule_codes), activation_state)
            curriculum_pk, curriculum_source, curriculum_rules = _bind_curriculum(
                context,
                decision=request.decision,
                program_pk=request.program_pk,
                admission_year=request.admission_year,
            )
            rule_codes.extend(curriculum_rules)
            if not request.group_pk:
                rule_codes.append("legacy_sar_group_missing")
            record = _ensure_record(context, request=request, curriculum_pk=curriculum_pk)
            digest = sar_derivation_hash(
                legacy_pk=request.legacy_pk,
                placement_row_hash=request.placement_row_hash,
                outcome_token="created",
                program_code=request.program_code,
                group_slug=request.group_slug,
                admission_year_text=year_text,
                curriculum_source=curriculum_source,
                curriculum_key=f"{request.program_code}:{year_text}",
                activation_state=activation_state,
            )
            entity_map = _seal(
                context,
                legacy_pk=str(request.legacy_pk),
                digest=digest,
                state=_STATE.MIGRATED,
                label=STUDENT_RECORD_MODEL_LABEL,
                target_pk=str(record.pk),
            )
    except _refusal_types():
        # Tranzaksiya artıq geri alınıb: yarımçıq arxiv yoxdur.
        refused = "legacy_sar_archive_refused" if stage == "activation" else "legacy_sar_write_refused"
        if stage == "activation":
            activation_state = "refused"
        digest = sar_derivation_hash(
            legacy_pk=request.legacy_pk,
            placement_row_hash=request.placement_row_hash,
            outcome_token="unresolved",
            program_code=request.program_code,
            group_slug=request.group_slug,
            admission_year_text=year_text,
            curriculum_source="none",
            curriculum_key="",
            activation_state=activation_state,
        )
        entity_map = _seal(context, legacy_pk=str(request.legacy_pk), digest=digest, state=_STATE.QUARANTINED)
        return RecordOutcome(_STATE.QUARANTINED, digest, entity_map, (refused,), activation_state)
    return RecordOutcome(_STATE.MIGRATED, digest, entity_map, tuple(rule_codes), activation_state)


__all__ = [
    "ARCHIVE_EVIDENCE_SUBJECT",
    "ARCHIVE_FALLBACK_ADMISSION_YEAR",
    "FALLBACK_ADMISSION_YEAR",
    "account_is_archived",
    "materialise_archive",
    "resolve_archive_role",
]

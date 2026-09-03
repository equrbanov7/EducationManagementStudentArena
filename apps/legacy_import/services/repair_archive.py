"""P0-1 təmiri: səhvən «məzun» sayılmış CARİ tələbələrin seçimi və bərpası.

Qüsur (2026-09-02 auditi).  ``rehearsal_sar_phase`` iki qolla arxivləyirdi:
``students.azadedildi=1`` (mənbədə 200 sətir) VƏ «qəbul ili heç bir mənbədən
çıxmadı» (2 291 sətir).  İkinci qol məzunluq ölçüsü DEYİL: qəbul ili yalnız ona
görə tapılmır ki, tələbənin qrupunda ``groups.start_year='0000'`` yazılıb
(mənbədə belə 248 qrup var).  Nəticə: 2 291 cari tələbə
``access_state='archived'`` + ``alumni`` rolu aldı və
``user_access_is_login_blocked`` onları BÜTÜN autentifikasiya səthlərində
bloklayır.

Seçim qaydası (ledger sübutuna əsaslanır, təxminə YOX)
-----------------------------------------------------
Sətir yalnız və yalnız o halda bərpa olunur ki:

1. profil HƏQİQƏTƏN ``archived``-dir və hesab bu tenant-a aiddir;
2. ledger-də həmin legacy açar üçün ``legacy_sar_archived_no_admission_year``
   issue-su var — yəni arxiv qərarını MƏHZ qəbul ilinin həll olunmaması verib;
3. həmin legacy açar üçün ``legacy_sar_departed_student`` issue-su YOXDUR.

⚠️ ``legacy_sar_departed_student`` YALNIZ aktivasiya açarı BAĞLI olan run-da
yazılır; açar açıq olanda hər iki səbəb eyni ``legacy_sar_archived_student``
kodunu alır və buraxılmışları ilsizlərdən ayıran YEGANƏ nişan
``legacy_sar_archived_no_admission_year``-in OLMASIDIR (2 291 sətir).  Ona görə
qayda «bu kod VARSA bərpa et» şəklindədir — buraxılmış (``azadedildi=1``) sətirdə
o kod heç vaxt olmur.

``--require-activity`` verilərsə əlavə olaraq ən azı bir ``Enrollment`` tələb
olunur.  Buraxılmış (``azadedildi=1``) tələbə heç bir halda toxunulmur.

Nə YAZILIR
----------
* ``apps.accounts.public.restore_archived_account`` → profil ``archived→active``,
  üzvlüyün rolu ``alumni→student`` (üzvlük sətri SİLİNMİR, rolu dəyişir; əvvəlki
  rol audit sətrində qalır), ``auth_user.is_active`` toxunulmur (onsuz da True);
* ``StudentAcademicRecord.is_active=True`` (yalnız False idisə);
* hər dəyişən istifadəçi üçün ``core.audit.log_action``
  (``reason="legacy_repair:archive_status"``).

Qəbul ili sentineli (1950) QƏSDƏN olduğu kimi qalır — o, «bu il məlum deyil»
sözünün model icazə verdiyi yeganə formasıdır və ``Curriculum`` bağlantısı
(``program`` + ``admission_year``) ona görə qurulub.  ``--fix-admission-year``
açıq şəkildə veriləndə il tələbənin ƏN ERKƏN yazılışının akademik ilindən
törədilir (sübut: real dövr), amma kurikulum bağlantısına TOXUNULMUR.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .rehearsal_authorizer import USER_MODEL_LABEL

#: Arxiv qərarının səbəbini deyən ledger kodları.
ARCHIVED_NO_YEAR_RULE = "legacy_sar_archived_no_admission_year"
ARCHIVED_STUDENT_RULE = "legacy_sar_archived_student"
DEPARTED_RULE = "legacy_sar_departed_student"
#: Ledger-dəki entity adları — mənbə həqiqəti (``sar`` DEYİL).
SAR_ENTITY_TYPE = "student_record"
STUDENT_ENTITY_TYPE = "student"

AUDIT_REASON = "legacy_repair:archive_status"
#: ``AccountActivationEvidence.Reason`` üzvü: sübut məhz müəssisənin öz legacy
#: reyestridir (``students.azadedildi`` + yazılış tarixçəsi).
EVIDENCE_REASON_CODE = "institution_registry_match"
_EVIDENCE_PREFIX = b"legacy-repair-archive-status-v1\x00"


@dataclass(frozen=True)
class ArchiveDecision:
    """Bir arxiv sətri üçün qərar — cədvəldə bire-bir belə çap olunur."""

    legacy_pk: str
    user_pk: int
    username: str
    full_name: str
    group: str
    enrollments: int
    earliest_year: str
    latest_year: str
    departed: bool
    action: str  # restore | keep_archived | already_active
    reason: str

    def as_row(self):
        return (
            self.legacy_pk,
            self.username,
            self.full_name[:28],
            self.group[:14],
            self.enrollments,
            self.earliest_year,
            self.latest_year,
            "bəli" if self.departed else "xeyr",
            self.action,
            self.reason,
        )


TABLE_HEADERS = (
    "legacy",
    "username",
    "ad soyad",
    "qrup",
    "yazılış",
    "ilk il",
    "son il",
    "azad.",
    "qərar",
    "səbəb",
)


def evidence_digest(*, organization_pk, user_pk, legacy_pk: str) -> str:
    """Deterministik, PII-siz evidence rəqəmi (64 hex) — hər sətir üçün fərqli."""

    digest = hashlib.sha256(_EVIDENCE_PREFIX)
    for part in (str(organization_pk), str(user_pk), str(legacy_pk), AUDIT_REASON):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _issue_index(organization, rule_codes) -> dict[str, set[str]]:
    """``legacy_pk`` → həmin sətir üçün mövcud SAR issue kodları."""

    index: dict[str, set[str]] = {}
    rows = LegacyMigrationIssue.objects.filter(
        organization=organization, entity_type=SAR_ENTITY_TYPE, rule_code__in=sorted(rule_codes)
    ).values_list("legacy_pk", "rule_code")
    for legacy_pk, rule_code in rows:
        index.setdefault(str(legacy_pk), set()).add(str(rule_code))
    return index


def _student_map(organization) -> dict[str, str]:
    """``auth_user`` pk → legacy student açarı (yalnız bu tenant)."""

    rows = LegacyEntityMap.objects.filter(
        organization=organization,
        entity_type=STUDENT_ENTITY_TYPE,
        state=LegacyEntityMap.State.MIGRATED,
        target_model_label=USER_MODEL_LABEL,
    ).values_list("target_pk", "legacy_pk")
    return {str(target_pk): str(legacy_pk) for target_pk, legacy_pk in rows}


def _enrollment_evidence(organization, user_pks):
    """Hər tələbə üçün yazılış sayı + ən erkən/son akademik il (tək sorğu)."""

    enrollment = django_apps.get_model("registrar", "Enrollment")
    evidence: dict[int, list] = {}
    rows = enrollment.objects.filter(organization=organization, student_id__in=list(user_pks)).values_list(
        "student_id", "offering__period__academic_year"
    )
    for student_id, academic_year in rows:
        bucket = evidence.setdefault(int(student_id), [0, "", ""])
        bucket[0] += 1
        year = str(academic_year or "")
        if year:
            bucket[1] = year if not bucket[1] else min(bucket[1], year)
            bucket[2] = year if not bucket[2] else max(bucket[2], year)
    return evidence


def archived_profiles(organization, limit: int):
    """Bu tenant-ın arxiv profilləri, deterministik sıra ilə (``user_id``)."""

    profile_model = django_apps.get_model("accounts", "UserProfile")
    queryset = (
        profile_model.objects.filter(organization=organization, access_state=profile_model.AccessState.ARCHIVED)
        .select_related("user")
        .order_by("user_id")
    )
    return list(queryset[:limit] if limit else queryset)


def plan_decisions(organization, *, limit: int = 0, require_activity: bool = False):
    """Qərar cədvəlini qur — HEÇ NƏ YAZMADAN (dry-run ilə apply eyni planı görür)."""

    profiles = archived_profiles(organization, limit)
    student_map = _student_map(organization)
    issues = _issue_index(organization, (ARCHIVED_NO_YEAR_RULE, ARCHIVED_STUDENT_RULE, DEPARTED_RULE))
    evidence = _enrollment_evidence(organization, [profile.user_id for profile in profiles])
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    groups = {
        int(row["student_id"]): str(row["group__name"] or "")
        for row in record_model.objects.filter(
            organization=organization, student_id__in=[profile.user_id for profile in profiles]
        ).values("student_id", "group__name")
    }

    decisions: list[ArchiveDecision] = []
    for profile in profiles:
        legacy_pk = student_map.get(str(profile.user_id), "")
        codes = issues.get(legacy_pk, set()) if legacy_pk else set()
        count, earliest, latest = evidence.get(int(profile.user_id), [0, "", ""])
        departed = DEPARTED_RULE in codes
        if not legacy_pk:
            action, reason = "keep_archived", "ledger_map_missing"
        elif departed:
            action, reason = "keep_archived", "source_azadedildi"
        elif ARCHIVED_NO_YEAR_RULE not in codes:
            # Arxiv qərarı var, amma «ilsiz» nişanı yoxdur → yeganə qalan səbəb
            # mənbənin ``azadedildi=1`` bayrağıdır (V-18).
            action = "keep_archived"
            reason = "source_azadedildi" if ARCHIVED_STUDENT_RULE in codes else "archive_reason_unknown"
        elif require_activity and count == 0:
            action, reason = "keep_archived", "no_enrolment_evidence"
        else:
            action, reason = "restore", "no_admission_year_only"
        decisions.append(
            ArchiveDecision(
                legacy_pk=legacy_pk or "-",
                user_pk=int(profile.user_id),
                username=profile.user.username,
                full_name=f"{profile.user.first_name} {profile.user.last_name}".strip(),
                group=groups.get(int(profile.user_id), ""),
                enrollments=count,
                earliest_year=earliest,
                latest_year=latest,
                departed=departed,
                action=action,
                reason=reason,
            )
        )
    return decisions


def student_role(organization):
    role = (
        django_apps.get_model("organizations", "Role")
        .objects.filter(organization=organization, name="student", is_active=True)
        .first()
    )
    if role is None:
        raise RuntimeError("legacy_repair_student_role_unavailable")
    return role


def _sync_record(organization, user_pk: int, *, admission_year: int | None) -> bool:
    """SAR-ı yenidən aktiv et (və istənilibsə qəbul ilini düzəlt)."""

    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    updates: dict[str, object] = {}
    record = record_model.objects.filter(organization=organization, student_id=user_pk).order_by("pk").first()
    if record is None:
        return False
    if not record.is_active:
        updates["is_active"] = True
    if admission_year is not None and record.admission_year != admission_year:
        updates["admission_year"] = admission_year
    if not updates:
        return False
    record_model.objects.filter(pk=record.pk).update(**updates)
    return True


def derived_admission_year(decision: ArchiveDecision) -> int | None:
    """Ən erkən yazılışın akademik ilindən ("2022/2023" → 2022) kohort ili."""

    text = (decision.earliest_year or "").strip()[:4]
    return int(text) if text.isdigit() else None


def apply_decision(*, organization, actor, decision: ArchiveDecision, fix_admission_year: bool) -> bool:
    """Bir sətri bərpa et — hesab keçidi + SAR, HAMISI bir iş vahidində."""

    from apps.accounts.public import restore_archived_account

    year = derived_admission_year(decision) if fix_admission_year else None
    with transaction.atomic():
        result = restore_archived_account(
            user=django_apps.get_model("auth", "User")._default_manager.filter(pk=decision.user_pk).first(),
            organization=organization,
            expected_role=student_role(organization),
            actor=actor,
            email_authority_evidence_digest=evidence_digest(
                organization_pk=organization.pk, user_pk=decision.user_pk, legacy_pk=decision.legacy_pk
            ),
            email_authority_reason_code=EVIDENCE_REASON_CODE,
        )
        _sync_record(organization, decision.user_pk, admission_year=year)
    return bool(getattr(result, "restored", False))


__all__ = [
    "ARCHIVED_NO_YEAR_RULE",
    "AUDIT_REASON",
    "ArchiveDecision",
    "DEPARTED_RULE",
    "EVIDENCE_REASON_CODE",
    "TABLE_HEADERS",
    "apply_decision",
    "archived_profiles",
    "derived_admission_year",
    "evidence_digest",
    "plan_decisions",
    "student_role",
]

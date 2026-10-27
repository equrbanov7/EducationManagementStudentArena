"""«Arxivdən çıxar» — səhvən «məzun» (arxiv) sayılmış CARİ tələbənin girişini bərpa (sahib 2026-10-27).

Sahib: «Mən özüm də arxivdən çıxara bilim». Köçürmə qəbul ili həll olunmayan (``1950`` yer-tutucusu) bəzi
CARİ tələbələri arxivləyib: akademik qeyd ``enrolled`` və qrupda aktiv qalıb, giriş və parol bərpası isə
``access_state='archived'`` ilə bağlıdır.

Bu modul ORTAQ qaydadır — həm RİM UI-ı («Arxivdən çıxar» düyməsi), həm ops əmri
(``legacy_import restore_archived_students``) eyni uyğunluq qaydasından və eyni auditli keçiddən keçir:

* **Uyğunluq** (``restore_eligibility``): profil ``archived``, hesab aktiv (``is_active``), təşkilatda aktiv
  ``enrolled`` akademik qeyd var, qrupu «Xaric …» psevdo-qrupu DEYİL və hesabın təşkilatda tam BİR üzvlüyü var
  (0018 funksiyasının öz şərti — əks halda düymə göstərilib sonra DB-də yıxılardı).
* **Keçid**: mövcud ``restore_archived_account`` (0018 ``accounts_restore_archived_identity`` + append-only
  bərpa sübutu; sübut = sha256 həzm, səbəb ``manual_registry_verification``). Aktor icazəsi ``member.edit``
  həm burada, həm DB funksiyasında yoxlanılır.
* **Qəbul ili**: yalnız qeyd YER-TUTUCU (``1950``) ildədirsə və 2000–2100 aralığında il verilibsə düzəlir
  (ayrıca audit sətri). Real qəbul ili heç vaxt üstələnmir.

Rəsmi əmrlə bərpa (xaric edilmiş tələbə, ``identity_reinstate.py`` — qrup səhifəsində «Bərpa et») BU DEYİL:
orada əmr sənədi var; burada isə akademik qeyd onsuz da aktivdir, səhv olan yalnız hesabın arxiv bayrağıdır.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction

from ..models import UserProfile
from .identity_access import IdentityAccessError, _assert_tenant_permission
from .identity_archive import restore_archived_account

_CTX = "accounts.archive_restore"

#: Köçürmənin «qəbul ili həll olunmadı» yer-tutucusu.
SENTINEL_ADMISSION_YEAR = 1950
MIN_ADMISSION_YEAR = 2000
MAX_ADMISSION_YEAR = 2100
#: Bərpa sübutunun səbəb kodu (0018 allow-list-i).
EVIDENCE_REASON = "manual_registry_verification"
#: Aktorun açarı — ``restore_archived_account`` və 0018 funksiyası ilə EYNİ.
PERMISSION = "member.edit"
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 300
_EXPELLED_GROUP_PREFIX = "xaric"
_EVIDENCE_PREFIX = b"rim-archive-restore-v1\x00"

ELIGIBLE = "eligible"
NOT_ARCHIVED = "not_archived"
ACCOUNT_INACTIVE = "account_inactive"
NO_ACTIVE_RECORD = "no_active_record"
EXPELLED_GROUP = "expelled_group"
MEMBERSHIP_MISMATCH = "membership_mismatch"


def error_message(code: str) -> str:
    """Kod → istifadəçiyə göstərilən (tərcümə olunan) mətn."""
    messages = {
        "permission_denied": pgettext(_CTX, "Hesabı arxivdən çıxarmaq üçün icazəniz yoxdur."),
        "view_as_forbidden": pgettext(_CTX, "Başqasının adından baxış rejimində hesabı arxivdən çıxarmaq olmaz."),
        "target_required": pgettext(_CTX, "İstifadəçi seçilməyib."),
        "target_not_found": pgettext(_CTX, "İstifadəçi tapılmadı."),
        NOT_ARCHIVED: pgettext(_CTX, "Hesab arxivdə deyil."),
        ACCOUNT_INACTIVE: pgettext(_CTX, "Hesab bloklanıb — əvvəlcə blokdan çıxarılmalıdır."),
        NO_ACTIVE_RECORD: pgettext(_CTX, "Tələbənin aktiv akademik qeydi yoxdur — arxiv düzgündür."),
        EXPELLED_GROUP: pgettext(_CTX, "Tələbə «Xaric» qrupundadır — arxiv düzgündür."),
        MEMBERSHIP_MISMATCH: pgettext(
            _CTX, "Hesabın bu təşkilatda bir neçə üzvlüyü var — arxivdən çıxarmaq üçün RİM ilə yoxlanmalıdır."
        ),
        "student_role_missing": pgettext(_CTX, "Təşkilatda aktiv «Tələbə» rolu yoxdur."),
        "reason_required": pgettext(_CTX, "Səbəb yazılmalıdır (ən azı 3 simvol)."),
        "admission_year_invalid": pgettext(_CTX, "Qəbul ili 2000–2100 aralığında olmalıdır."),
        "restore_failed": pgettext(_CTX, "Hesabı arxivdən çıxarmaq alınmadı. Yenidən cəhd edin."),
    }
    return messages.get(code) or messages["restore_failed"]


class ArchiveRestoreError(Exception):
    """Əməliyyat rədd edildi — ``code`` maşın-oxunaqlı, ``message`` tərcümə olunmuş mətn."""

    def __init__(self, code: str, status: int = 409):
        super().__init__(code, status)
        self.code = code
        self.status = status

    @property
    def message(self) -> str:
        return error_message(self.code)

    def __str__(self):
        return self.code


@dataclass(frozen=True)
class RestoreEligibility:
    code: str
    record: object | None = None

    @property
    def eligible(self) -> bool:
        return self.code == ELIGIBLE

    @property
    def needs_admission_year(self) -> bool:
        return self.record is not None and self.record.admission_year == SENTINEL_ADMISSION_YEAR

    @property
    def group_name(self) -> str:
        group = getattr(self.record, "group", None)
        return getattr(group, "name", "") or ""


@dataclass(frozen=True)
class RestoreOutcome:
    restored: bool
    admission_year_fixed: bool
    admission_year: int | None


def _record_model():
    return django_apps.get_model("registrar", "StudentAcademicRecord")


def _active_record(user, organization, *, for_update=False):
    queryset = _record_model().objects.filter(
        organization=organization, student=user, is_active=True, status="enrolled"
    )
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    return queryset.select_related("group").order_by("pk").first()


def restore_eligibility(user, organization, *, for_update=False) -> RestoreEligibility:
    """Hesab «səhv arxiv»dirmi (arxivdən çıxarıla bilərmi) — kod + aktiv qeyd."""
    if user is None or organization is None:
        return RestoreEligibility(NOT_ARCHIVED)
    profile = UserProfile.objects.filter(user=user).only("access_state", "organization_id").first()
    if (
        profile is None
        or profile.access_state != UserProfile.AccessState.ARCHIVED
        or str(profile.organization_id) != str(organization.pk)
    ):
        return RestoreEligibility(NOT_ARCHIVED)
    if not user.is_active:
        return RestoreEligibility(ACCOUNT_INACTIVE)
    record = _active_record(user, organization, for_update=for_update)
    if record is None:
        return RestoreEligibility(NO_ACTIVE_RECORD)
    group = record.group
    if group is not None and group.name.strip().lower().startswith(_EXPELLED_GROUP_PREFIX):
        return RestoreEligibility(EXPELLED_GROUP, record)
    from apps.organizations.models import Membership

    if Membership.objects.filter(user=user, organization=organization).count() != 1:
        return RestoreEligibility(MEMBERSHIP_MISMATCH, record)
    return RestoreEligibility(ELIGIBLE, record)


def actor_can_restore(actor_user, organization) -> bool:
    """Aktor bu təşkilatda hesabı arxivdən çıxara bilərmi (``member.edit`` — servislə EYNİ qapı)."""
    if actor_user is None or not getattr(actor_user, "is_authenticated", False):
        return False
    try:
        _assert_tenant_permission(actor_user, organization, PERMISSION)
    except PermissionDenied:
        return False
    return True


def normalize_reason(raw) -> str:
    reason = " ".join(str(raw or "").strip().split())[:MAX_REASON_LENGTH]
    if len(reason) < MIN_REASON_LENGTH:
        raise ArchiveRestoreError("reason_required", status=400)
    return reason


def normalize_admission_year(raw) -> int | None:
    """Boş → ``None``; əks halda 2000–2100 aralığında tam ədəd (yoxsa ``admission_year_invalid``)."""
    if raw in (None, "", 0, "0"):
        return None
    try:
        year = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ArchiveRestoreError("admission_year_invalid", status=400) from None
    if not MIN_ADMISSION_YEAR <= year <= MAX_ADMISSION_YEAR:
        raise ArchiveRestoreError("admission_year_invalid", status=400)
    return year


def evidence_digest(organization_pk, user_pk, actor_pk) -> str:
    """Bərpa sübutunun həzmi — təşkilat + hesab + aktor + birdəfəlik nonce (sübut sətri append-only-dir)."""
    material = f"{organization_pk}:{user_pk}:{actor_pk}:{uuid.uuid4()}".encode()
    return hashlib.sha256(_EVIDENCE_PREFIX + material).hexdigest()


def _student_role(organization):
    role = (
        django_apps.get_model("organizations", "Role")
        .objects.filter(organization=organization, name="student", is_active=True)
        .first()
    )
    if role is None:
        raise ArchiveRestoreError("student_role_missing")
    return role


def _fix_admission_year(record, year, *, actor, organization, reason, request) -> bool:
    if year is None or record.admission_year != SENTINEL_ADMISSION_YEAR:
        return False
    _record_model().objects.filter(pk=record.pk, admission_year=SENTINEL_ADMISSION_YEAR).update(admission_year=year)
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=record,
        old_values={"admission_year": SENTINEL_ADMISSION_YEAR},
        new_values={"admission_year": year},
        reason=f"archive_restore: admission_year {SENTINEL_ADMISSION_YEAR} → {year}. {reason}",
        changes={"operation": "archive_restore_admission_year", "reason_text": reason},
        request=request,
    )
    return True


def restore_wrongly_archived_student(
    *, user, organization, actor, reason, admission_year=None, digest="", request=None
) -> RestoreOutcome:
    """Səhv arxivlənmiş cari tələbəni AKTİV et (+ istənilibsə yer-tutucu qəbul ilini düzəlt).

    Qaydalar: ``member.edit`` → uyğunluq (``restore_eligibility``) → ``restore_archived_account``
    (0018 + bərpa sübutu + audit, ``note`` = səbəb) → qəbul ili (yalnız ``1950``-dən). Hamısı BİR tranzaksiyada;
    hər rədd ``ArchiveRestoreError`` (403 icazə, 400 giriş, 409 vəziyyət).
    """
    reason = normalize_reason(reason)
    year = normalize_admission_year(admission_year)
    if not actor_can_restore(actor, organization):
        raise ArchiveRestoreError("permission_denied", status=403)
    with transaction.atomic():
        eligibility = restore_eligibility(user, organization, for_update=True)
        if not eligibility.eligible:
            raise ArchiveRestoreError(eligibility.code)
        role = _student_role(organization)
        try:
            result = restore_archived_account(
                user=user,
                organization=organization,
                expected_role=role,
                actor=actor,
                email_authority_evidence_digest=digest or evidence_digest(organization.pk, user.pk, actor.pk),
                email_authority_reason_code=EVIDENCE_REASON,
                request=request,
                note=reason,
            )
        except PermissionDenied as exc:
            raise ArchiveRestoreError("permission_denied", status=403) from exc
        except (IdentityAccessError, DatabaseError) as exc:
            raise ArchiveRestoreError("restore_failed") from exc
        fixed = _fix_admission_year(
            eligibility.record, year, actor=actor, organization=organization, reason=reason, request=request
        )
    return RestoreOutcome(
        restored=bool(getattr(result, "restored", False)),
        admission_year_fixed=fixed,
        admission_year=year if fixed else eligibility.record.admission_year,
    )


__all__ = [
    "ArchiveRestoreError",
    "MAX_ADMISSION_YEAR",
    "MIN_ADMISSION_YEAR",
    "RestoreEligibility",
    "RestoreOutcome",
    "SENTINEL_ADMISSION_YEAR",
    "actor_can_restore",
    "error_message",
    "normalize_admission_year",
    "restore_eligibility",
    "restore_wrongly_archived_student",
]

"""Dublikat işçi hesabı birləşdirməsinin QAPILARI (sahib 2026-11-03).

Plan YALNIZ id-lərdir (``--source-user`` dublikat, ``--target-user`` əsas hesab); hər işə salınmada yenidən yoxlanılır:

* hər iki hesab mövcud və fərqlidir, ikisi də təşkilatındır (profil və ya istənilən — aktiv/deaktiv — üzvlük);
* hədəf aktivdir, silinməyib və təşkilatda AKTİV üzvlüyü var (dərs/açılış müəllimi DB trigger-i bunu tələb edir);
* ikisi də İŞÇİ hesabıdır — təşkilatda tələbə qeydi (``StudentAcademicRecord``) olan hesab birləşdirilmir;
* mənbə superadmin/staff deyil və ya bloklanıb, ya da HEÇ VAXT daxil olmayıb — daxil olmuş aktiv hesabın
  «əsl» olub-olmaması sahibin qərarıdır;
* ad + soyad + ata adı eynidir — böyük/kiçik hərf, boşluq və diakritik fərqi nəzərə alınmır (köhnə sistemdə
  «QƏNİYEVA» / «Qeniyeva» / «Qəniyeva» yazılışları; «İ/ı» → «i»); boş ad/soyad/ata adı uyğunsuzluqdur.
  ``--force-name-mismatch`` yalnız sahib eyni şəxs olduğunu təsdiqləyəndə.
"""

from __future__ import annotations

import unicodedata

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model

MIN_REASON_LENGTH = 10


class StaffMergeError(Exception):
    """Qapı keçmədi — kod stdout-a / CommandError-a çıxır (şəxs adı yox)."""


def _norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").replace("İ", "i").replace("ı", "i").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.replace("ə", "e").split())


def _identity(user) -> tuple:
    profile = getattr(user, "profile", None)
    return _norm(user.first_name), _norm(user.last_name), _norm(getattr(profile, "patronymic", ""))


def names_match(source, target) -> bool:
    left, right = _identity(source), _identity(target)
    return all(left) and left == right


def _belongs(user, organization) -> bool:
    profile = getattr(user, "profile", None)
    if profile is not None and profile.organization_id == organization.pk:
        return True
    membership = django_apps.get_model("organizations", "Membership")
    return membership.objects.filter(organization=organization, user=user).exists()


def _is_student(user, organization) -> bool:
    record = django_apps.get_model("registrar", "StudentAcademicRecord")
    return record._base_manager.filter(organization=organization, student=user).exists()


def check(organization, source_id: int, target_id: int, *, reason: str, force_name_mismatch: bool = False):
    """Qapılardan keçən ``(source, target)`` cütünü qaytarır, keçməyəndə ``StaffMergeError(kod)``."""
    if len(str(reason or "").strip()) < MIN_REASON_LENGTH:
        raise StaffMergeError("reason_required")
    if source_id == target_id:
        raise StaffMergeError("same_user")
    users = get_user_model()._base_manager.select_for_update(of=("self",)).in_bulk([source_id, target_id])
    source, target = users.get(source_id), users.get(target_id)
    if source is None or target is None:
        raise StaffMergeError("user_not_found")
    if not (_belongs(source, organization) and _belongs(target, organization)):
        raise StaffMergeError("user_outside_organization")
    target_profile = getattr(target, "profile", None)
    if not target.is_active or (target_profile is not None and target_profile.is_deleted):
        raise StaffMergeError("target_not_active")
    membership = django_apps.get_model("organizations", "Membership")
    if not membership.objects.filter(organization=organization, user=target, is_active=True).exists():
        raise StaffMergeError("target_not_active_member")
    if _is_student(source, organization) or _is_student(target, organization):
        raise StaffMergeError("student_account")
    if source.is_superuser or source.is_staff:
        raise StaffMergeError("source_elevated")
    if source.is_active and source.last_login is not None:
        raise StaffMergeError("source_active_with_login")
    if not force_name_mismatch and not names_match(source, target):
        raise StaffMergeError("name_mismatch")
    return source, target

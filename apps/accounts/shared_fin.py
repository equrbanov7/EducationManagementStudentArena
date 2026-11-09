"""Eyni FİN — bir adamın tələbə və işçi hesabı (sahib 2026-11-09).

Sahib: «eyni FİN-dirsə bir dəfə təsdiq modalı açılsın — "sizin həm də tələbə hesabınız var, razısınızmı?" — sonra
bir də soruşmasın; eyni FİN həm işçi hesabında, həm də tələbə hesabında görünsün». Konkret hal: tələbə (tyutor
rolu da verilmiş) üçün ayrıca işçi hesabı açılır; ilk girişdə məcburi FİN xanasına öz FİN-ini yazır.

Qayda:

* FİN unikallığı ƏSAS hesablar arasındadır (``UserProfile.fin_shared_with`` boş) — DB məhdudiyyəti
  ``accounts_userprofile_fin_primary_uniq``;
* ikinci hesab eyni FİN-i yalnız **bağlı hesab** kimi daşıyır: ``fin_shared_with`` = əsas hesab,
  ``fin_shared_confirmed_at`` = sahibin təsdiq vaxtı. Bir əsas hesabın ən çoxu bir bağlı hesabı olur (OneToOne);
* bağ təklifi YALNIZ fərqli ailədən olan hesablar üçündür (biri tələbə, biri heyət) və ad-soyad uyğun olmalıdır —
  eyni ailədən iki hesab (iki tələbə) əvvəlki kimi «başqa hesabda qeydə alınıb» imtinası alır;
* bağ qurulandan sonra heç nə soruşulmur: FİN doludur, qapı keçir. RİM FİN redaktəsi bağlı cütü toqquşma saymır.

Yan təsir: heyət qapısı (:mod:`apps.organizations.self_conflict`) bağlı tələbə hesabını «özü» sayır —
işçi hesabı ilə öz qrupuna / jurnalına toxunmaq olmur (:func:`linked_student_user`).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.person_names import name_key

from . import profile_completion as policy

#: Təsdiq formasının gizli sahəsi — «hər iki hesab mənimdir».
CONFIRM_FIELD = "confirm_shared_fin"
AUDIT_REASON_LINKED = "shared_fin_linked"


def _name_keys(text: str) -> set:
    """«Məmmədova» latın klaviaturasında həm «Memmedova», həm «Mammadova» yazılır — hər iki açar."""
    return {name_key(text), name_key(str(text or "").replace("ə", "a").replace("Ə", "A"))} - {""}


def same_person(user_a, user_b) -> bool:
    """Ad və soyad (diakritiksiz) eynidirmi — FİN paylaşımının minimum sübutu."""
    return bool(_name_keys(user_a.first_name) & _name_keys(user_b.first_name)) and bool(
        _name_keys(user_a.last_name) & _name_keys(user_b.last_name)
    )


def family_of(user) -> str:
    """``student`` / ``staff`` / ``""`` — bütün aktiv üzvlüklərə görə (təşkilatdan asılı deyil)."""
    memberships = list(user.memberships.filter(is_active=True).select_related("role"))
    return policy.role_family(memberships)


_family = family_of


def fin_holder(fin: str, user):
    """Bu FİN-i daşıyan BAŞQA hesabın profili (``select_related('user')``) və ya ``None``."""
    from .models import UserProfile

    if not fin:
        return None
    return (
        UserProfile.objects.filter(fin=fin)
        .exclude(user_id=user.pk)
        .select_related("user")
        .order_by("fin_shared_with_id", "pk")  # əsas (bağsız) hesab əvvəl
        .first()
    )


def linked_user(user):
    """Bağlı digər hesab (hər iki istiqamət) və ya ``None`` — 1 sorğu."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return None
    if profile.fin_shared_with_id:
        return profile.fin_shared_with
    secondary = getattr(user, "fin_shared_secondary", None)
    try:
        return secondary.user if secondary is not None else None
    except Exception:  # noqa: BLE001 — related obyekt yoxdur
        return None


def linked_student_user(user):
    """İşçi hesabının bağlı TƏLƏBƏ hesabı (heyət qapısı üçün) — bağ işçi profilindədir, sorğusuz oxunur."""
    profile = getattr(user, "profile", None)
    if profile is None or not profile.fin_shared_with_id:
        return None
    other = profile.fin_shared_with
    return other if other is not None and other.is_active else None


def link_offer(fin: str, user):
    """FİN başqa hesabdadırsa və bağ MÜMKÜNDÜRSƏ — həmin hesabın ``User``-i; əks halda ``None``.

    Şərtlər: digər hesab aktivdir, əsas hesabdır (özü bağlı deyil) və hələ bağlı hesabı yoxdur; ailələr fərqlidir
    (biri tələbə, biri heyət); ad-soyad uyğundur.
    """
    holder = fin_holder(fin, user)
    if holder is None or holder.fin_shared_with_id or not holder.user.is_active:
        return None
    if getattr(user.profile, "fin_shared_with_id", None) or _has_secondary(holder.user):
        return None
    families = {_family(user), _family(holder.user)}
    if families != {policy.ROLE_STUDENT, policy.ROLE_STAFF}:
        return None
    return holder.user if same_person(user, holder.user) else None


def _has_secondary(user) -> bool:
    from .models import UserProfile

    return UserProfile.objects.filter(fin_shared_with=user).exists()


def is_linked_pair(user, other) -> bool:
    """İki hesab bir-birinə bağlıdırmı (RİM FİN redaktəsi, dublikat analizi üçün)."""
    if user is None or other is None:
        return False
    a = getattr(user, "profile", None)
    b = getattr(other, "profile", None)
    return bool(
        (a is not None and a.fin_shared_with_id == getattr(other, "pk", None))
        or (b is not None and b.fin_shared_with_id == getattr(user, "pk", None))
    )


def link_accounts(user, holder, *, fin: str, request=None) -> None:
    """Bağı qur: FİN hər iki hesabda görünür; bağ (``fin_shared_with``) HƏMİŞƏ işçi hesabındadır, tələbə hesabı
    əsas (bağsız) qalır — heyət qapısı və DB trigger-i bir istiqamətli, sorğusuz oxuyur. Audit hər iki hesaba.
    """
    from apps.audit.public import log_action
    from core.constants import AuditAction

    staff, student = (user, holder) if family_of(user) == policy.ROLE_STAFF else (holder, user)
    with transaction.atomic():
        # Əvvəl işçi hesabı: bağ qoyulanda əsas-unikal indeksdən çıxır, sonra tələbə FİN-i (əsas) yazılır.
        staff_profile = staff.profile
        staff_profile.fin = fin
        staff_profile.fin_shared_with = student
        staff_profile.fin_shared_confirmed_at = timezone.now()
        staff_fields = ["fin", "fin_shared_with", "fin_shared_confirmed_at", "updated_at"]
        if staff is user:
            staff_profile.fin_self_reported = True
            staff_fields.append("fin_self_reported")
        staff_profile.save(update_fields=staff_fields)
        if student is user:
            student_profile = student.profile
            student_profile.fin = fin
            student_profile.fin_self_reported = True
            student_profile.save(update_fields=["fin", "fin_self_reported", "updated_at"])
        for subject, other in ((user, holder), (holder, user)):
            try:
                log_action(
                    action=AuditAction.UPDATE,
                    user=user,
                    organization=getattr(request, "organization", None),
                    obj=subject,
                    reason=AUDIT_REASON_LINKED,
                    changes={"fields": ["fin", "fin_shared_with"], "linked_user_id": other.pk},
                    request=request,
                )
            except Exception:  # noqa: BLE001 — audit xətası istifadəçini bloklamamalıdır
                pass


def primary_first(profiles):
    """FİN → hesab lüğətləri üçün: eyni FİN-də əsas hesab bağlıdan ÜSTÜNDÜR (sonuncu yazılan qalır)."""
    return sorted(profiles, key=lambda row: 0 if row[-1] else 1)


__all__ = [
    "AUDIT_REASON_LINKED",
    "CONFIRM_FIELD",
    "family_of",
    "fin_holder",
    "is_linked_pair",
    "link_accounts",
    "link_offer",
    "linked_student_user",
    "linked_user",
    "same_person",
]

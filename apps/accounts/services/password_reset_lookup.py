"""«Parol sıfırlama» — hədəfin tapılması və təsdiq kartının serializasiyası.

Operator əksər hallarda istifadəçi adını BİLİR (tələbə öz loginini deyir) — ona
görə əvvəlcə DƏQİQ istifadəçi adı (böyük/kiçik hərfə həssas deyil) axtarılır.
Tapılmasa layihənin DÖZÜMLÜ şəxs axtarışı (`core.search_text.tolerant_q` —
«Aliyev» «Əliyev»i tapır, söz sırası vacib deyil) işə düşür.

Kart operatorun ŞƏXSİYYƏTİ TƏSDİQLƏMƏSİ üçündür: ad (ata adı ilə), rol(lar),
qrup / struktur bölmə, son giriş. Email/telefon/FİN QƏSDƏN göstərilmir — bu
açar kataloqun PII qapılarını (`people.view_contacts`) vermir.

Axtarış əhatəsi sıfırlama əhatəsi ilə EYNİDİR (`reset_scope_queryset`): operator
sıfırlaya bilmədiyi hesabı siyahıda görmür. Dəqiq istifadəçi adı ÖZ təşkilatında
olub əhatədən kənardırsa (daha yüksək rütbə, superadmin, özü) səbəb bildirilir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from django.utils.translation import pgettext

from core.search_text import fold_regex, tokens_of, tolerant_q
from core.staff_position import visible_role_label

from .password_reset_admin import (
    PasswordResetError,
    check_resettable,
    explain_unavailable,
    reset_scope_queryset,
    status_code_of,
)

_CTX = "accounts.password_reset"

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 120
MAX_RESULTS = 8
#: Yazdıqca təklif siyahısının ölçüsü (sahib 2026-09-30: «5–10 nəfər»).
SUGGEST_LIMIT = 8

#: Dözümlü axtarışın sahələri — email/FİN QƏSDƏN yoxdur (PII qapısı, yuxarıya bax).
_SEARCH_FIELDS = ("username", "first_name", "last_name", "profile__patronymic")


def normalize_query(raw) -> str:
    return " ".join(str(raw or "").strip().split())[:MAX_QUERY_LENGTH]


def _status_label(code: str) -> str:
    return {
        "active": pgettext(_CTX, "Aktiv"),
        "blocked": pgettext(_CTX, "Bloklanıb"),
        "deleted": pgettext(_CTX, "Silinib"),
        "login_closed": pgettext(_CTX, "Giriş bağlıdır"),
    }.get(code, code)


def _memberships_by_user(users, organization) -> dict:
    from apps.organizations.models import Membership

    queryset = Membership.objects.filter(user__in=users, is_active=True).select_related("role", "scope_unit")
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    grouped: dict = {}
    for membership in queryset.order_by("-role__level", "role__name"):
        grouped.setdefault(membership.user_id, []).append(membership)
    return grouped


def _student_groups(users, organization) -> dict:
    """{user_id: qrup adı} — tələbənin akademik qeydindən (TƏK sorğu)."""
    if organization is None:
        return {}
    from .people.students import RECORD_PICK_ORDER, student_records_qs

    groups: dict = {}
    rows = (
        student_records_qs(organization)
        .filter(student__in=users)
        .order_by("student_id", *RECORD_PICK_ORDER)
        .values_list("student_id", "group__name")
    )
    for student_id, group_name in rows:
        if student_id not in groups and group_name:
            groups[student_id] = group_name
    return groups


def _last_login_label(user) -> str:
    if not user.last_login:
        return pgettext(_CTX, "Heç vaxt daxil olmayıb")
    return timezone.localtime(user.last_login).strftime("%d.%m.%Y %H:%M")


def serialize_candidates(actor, users) -> list:
    """Təsdiq kartları — hər hədəf üçün ``can_reset`` + səbəb (düymə buna görə açılır)."""
    users = list(users)
    if not users:
        return []
    organization = actor.organization
    memberships = _memberships_by_user(users, organization)
    groups = _student_groups(users, organization)

    rows = []
    for user in users:
        profile = getattr(user, "profile", None)
        user_memberships = memberships.get(user.pk, [])
        roles = []
        for membership in user_memberships:
            label = visible_role_label(membership.role.name, membership.role.display_name)
            if label and label not in roles:
                roles.append(label)
        units = []
        if user.pk in groups:
            units.append(groups[user.pk])
        for membership in user_memberships:
            name = membership.scope_unit.name if membership.scope_unit_id else ""
            if name and name not in units:
                units.append(name)
        department = (getattr(profile, "department", "") or "").strip() if profile is not None else ""
        if department and department not in units:
            units.append(department)

        can_reset, reason = True, ""
        try:
            check_resettable(actor, user)
        except PasswordResetError as exc:
            can_reset, reason = False, exc.message
        status = status_code_of(user)
        full_name = profile.full_name_with_patronymic if profile is not None else user.get_full_name()
        rows.append(
            {
                "id": user.pk,
                "username": user.username,
                "full_name": full_name or user.username,
                "roles": roles,
                "units": units,
                "last_login": _last_login_label(user),
                "status": status,
                "status_label": _status_label(status),
                "password_change_required": bool(getattr(profile, "password_change_required", False)),
                "can_reset": can_reset,
                "reason": reason,
            }
        )
    return rows


def lookup(actor, raw_query) -> dict:
    """Axtarış nəticəsi: ``{mode, results, has_more, notice}``.

    ``mode`` — ``exact`` (istifadəçi adı tam uyğun gəldi) və ya ``search``.
    """
    query = normalize_query(raw_query)
    if len(query) < MIN_QUERY_LENGTH:
        raise PasswordResetError("query_too_short", status=400)

    base = reset_scope_queryset(actor)
    exact = list(base.filter(username__iexact=query)[:2])
    if exact:
        return {"mode": "exact", "results": serialize_candidates(actor, exact), "has_more": False, "notice": ""}

    notice = ""
    candidate = get_user_model().objects.select_related("profile").filter(username__iexact=query).first()
    if candidate is not None:
        # İstifadəçi adı tam uyğun gəldi, amma əhatədə deyil — öz təşkilatındadırsa səbəb.
        error = explain_unavailable(actor, candidate)
        if error.code != "target_not_found":
            notice = error.message

    search_filter = tolerant_q(query, _SEARCH_FIELDS)
    users = []
    if search_filter is not None:
        users = list(base.filter(search_filter).order_by("last_name", "first_name", "username")[: MAX_RESULTS + 1])
    has_more = len(users) > MAX_RESULTS
    return {
        "mode": "search",
        "results": serialize_candidates(actor, users[:MAX_RESULTS]),
        "has_more": has_more,
        "notice": notice,
    }


def suggest(actor, raw_query) -> list:
    """Yazdıqca təklif — YÜNGÜL: ``{id, username, full_name, hint}``, ən çoxu ``SUGGEST_LIMIT``.

    Sahib 2026-09-30: operator yazdıqca uyğun 5–10 nəfər görünsün, sistem yüklənmədən. Sabit
    sorğu sayı (istifadəçilər + üzvlüklər + qrup — 3 sorğu), ``check_resettable`` YOXDUR: tam
    kart (icazə səbəbi, sıfırla düyməsi) seçimdən sonra ``lookup`` ilə TƏK hədəf üçün qurulur.
    Əhatə ``lookup`` ilə eynidir (``reset_scope_queryset``) — sıfırlana bilməyən hesab görünmür.
    Sıra: istifadəçi adı tam → istifadəçi adı ilə başlayan → adı/soyadı ilk sözlə başlayan
    (hərf qatlaması ilə: «Əli» ≈ «Ali») → qalanı (məs. ata adının içində uyğunluq).
    """
    query = normalize_query(raw_query)
    if len(query) < MIN_QUERY_LENGTH:
        return []
    search_filter = tolerant_q(query, _SEARCH_FIELDS)
    if search_filter is None:
        return []
    starts = "^" + fold_regex(tokens_of(query)[0])
    users = list(
        reset_scope_queryset(actor)
        .filter(search_filter)
        .annotate(
            _pwr_rank=Case(
                When(username__iexact=query, then=Value(0)),
                When(username__istartswith=query, then=Value(1)),
                When(first_name__iregex=starts, then=Value(2)),
                When(last_name__iregex=starts, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by("_pwr_rank", "last_name", "first_name", "username")[:SUGGEST_LIMIT]
    )
    if not users:
        return []
    organization = actor.organization
    memberships = _memberships_by_user(users, organization)
    groups = _student_groups(users, organization)
    rows = []
    for user in users:
        profile = getattr(user, "profile", None)
        hint = groups.get(user.pk, "")
        if not hint:
            for membership in memberships.get(user.pk, []):
                hint = visible_role_label(membership.role.name, membership.role.display_name) or ""
                if hint:
                    break
        full_name = profile.full_name_with_patronymic if profile is not None else user.get_full_name()
        rows.append({"id": user.pk, "username": user.username, "full_name": full_name or user.username, "hint": hint})
    return rows


__all__ = [
    "MAX_RESULTS",
    "MIN_QUERY_LENGTH",
    "SUGGEST_LIMIT",
    "lookup",
    "normalize_query",
    "serialize_candidates",
    "suggest",
]

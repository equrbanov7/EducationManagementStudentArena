"""Kataloq filtrlərinin normallaşdırılması və Q qurulması.

İki baza queryset-i var və onların istifadəçiyə gedən yolu FƏRQLİDİR:

* müəllimlər → ``Membership``  (istifadəçi ``user__``, struktur ``scope_unit``)
* tələbələr  → ``StudentAcademicRecord`` (istifadəçi ``student__``, struktur ``group``)

Ona görə bütün Q qurucuları ``prefix`` alır; filtr məntiqi TƏK yerdə qalır və
iki siyahının davranışı bir-birindən ayrılmır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Q

from ...models import UserProfile
from .constants import AGE_UNKNOWN, GENDER_BUCKETS, MAX_PAGE_SIZE, MAX_QUERY_LENGTH, MAX_QUERY_TOKENS

STATUS_ALL = "all"
STATUS_ACTIVE = "active"
STATUS_BLOCKED = "blocked"
STATUS_DELETED = "deleted"
STATUS_ARCHIVED = "archived"
ALLOWED_STATUSES = (STATUS_ALL, STATUS_ACTIVE, STATUS_BLOCKED, STATUS_DELETED, STATUS_ARCHIVED)

_ARCHIVED = UserProfile.AccessState.ARCHIVED

#: Sorğu sözünün axtarıldığı sahələr (istifadəçi prefiksinə nisbətən).
#: RİM axtarışı ilə EYNİ dəst — operator bir yerdə tapdığını o birində də tapsın.
SEARCH_FIELDS = (
    "first_name",
    "last_name",
    "username",
    "email",
    "profile__patronymic",
    "profile__fin",
)

MAX_AGE = 120


@dataclass(frozen=True)
class PeopleFilters:
    """Normallaşdırılmış filtr dəsti — xam GET heç vaxt aşağı qata düşmür."""

    query: str = ""
    faculty: str = ""
    kafedra: str = ""
    group: str = ""
    program: str = ""
    subject: str = ""
    year: str = ""
    season: str = ""
    status: str = STATUS_ALL
    gender: str = ""
    age_min: int | None = None
    age_max: int | None = None
    age_unknown: bool = False
    sort: str = "name"
    page: int = 1
    page_size: int = 0

    def as_dict(self) -> dict:
        """UI-ın filtr vəziyyətini geri oxuya bilməsi üçün (context müqaviləsi)."""
        return {
            "q": self.query,
            "faculty": self.faculty,
            "kafedra": self.kafedra,
            "group": self.group,
            "program": self.program,
            "subject": self.subject,
            "year": self.year,
            "season": self.season,
            "status": self.status,
            "gender": self.gender,
            "age_min": self.age_min,
            "age_max": self.age_max,
            "age_unknown": self.age_unknown,
            "sort": self.sort,
            "page": self.page,
            "page_size": self.page_size,
        }


def _clean_text(raw, limit=120) -> str:
    return " ".join(str(raw or "").strip().split())[:limit]


def _clean_int(raw, *, minimum=None, maximum=None):
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return value


def parse_filters(params, *, sort_options, default_page_size) -> PeopleFilters:
    """GET (və ya dict) → ``PeopleFilters``. Naməlum dəyər susdurulur, atılmır.

    Fail-closed DEYİL, fail-SAFE: yanlış `sort` xəta vermir, defolta düşür —
    əks halda köhnə bookmark link-i istifadəçiyə 400 verərdi.
    """

    def get(key):
        return params.get(key, "")

    status = _clean_text(get("status"), 16).lower() or STATUS_ALL
    if status not in ALLOWED_STATUSES:
        status = STATUS_ALL

    gender = _clean_text(get("gender"), 16).lower()
    if gender not in GENDER_BUCKETS:
        gender = ""

    sort = _clean_text(get("sort"), 24)
    if sort not in sort_options:
        sort = "name"

    age_min = _clean_int(get("age_min"), minimum=0, maximum=MAX_AGE)
    age_max = _clean_int(get("age_max"), minimum=0, maximum=MAX_AGE)
    if age_min is not None and age_max is not None and age_min > age_max:
        age_min, age_max = age_max, age_min

    page_size = _clean_int(get("page_size"), minimum=1, maximum=MAX_PAGE_SIZE) or default_page_size

    return PeopleFilters(
        query=_clean_text(get("q"), MAX_QUERY_LENGTH),
        faculty=_clean_text(get("faculty"), 64),
        kafedra=_clean_text(get("kafedra"), 64),
        group=_clean_text(get("group"), 64),
        program=_clean_text(get("program"), 64),
        subject=_clean_text(get("subject"), 64),
        year=_clean_text(get("year"), 32),
        season=_clean_text(get("season"), 32),
        status=status,
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        age_unknown=str(get("age") or "").strip().lower() == AGE_UNKNOWN,
        sort=sort,
        page=_clean_int(get("page"), minimum=1) or 1,
        page_size=page_size,
    )


def search_q(query: str, prefix: str, *, extra=None) -> Q:
    """AND-of-ORs axtarış filtri (RİM `search.py` ilə eyni semantika).

    «Əliyev Elvin» → hər söz ad/soyad/ata adı/username/email/FİN sahələrindən
    HƏR HANSI BİRİNƏ uyğun gəlməlidir; söz sırası əhəmiyyətsizdir.

    ``extra`` — kataloqa MƏXSUS əlavə uyğunluq (bir token alır, ``Q``/``Exists``
    qaytarır). AXTARIŞ İNVARİANTI üçün lazımdır: tələbə kataloqu sətirdə ixtisas
    ŞİFRİNİ göstərir, ona görə həmin şifr axtarışda da tapılmalıdır — amma
    müəllim kataloqunda ixtisas anlayışı yoxdur, deməli sahə siyahısı ORTAQ
    ``SEARCH_FIELDS``-ə yazıla bilməz. Token-başına OR olur ki, «Aysel 050401»
    kimi qarışıq sorğu da işləsin.
    """
    tokens = [token for token in _clean_text(query, MAX_QUERY_LENGTH).split(" ") if token][:MAX_QUERY_TOKENS]
    combined = Q()
    for token in tokens:
        token_filter = Q()
        for field_name in SEARCH_FIELDS:
            token_filter |= Q(**{f"{prefix}{field_name}__icontains": token})
        if extra is not None:
            token_filter |= extra(token)
        combined &= token_filter
    return combined


def status_q(status: str, prefix: str) -> Q:
    """Hesab statusu filtri.

    ``archived`` (məzun/xaric) QƏSDƏN ayrıca səbətdir: `auth_user.is_active`
    onlar üçün True qalır (registrar trigger-ləri üçün), yəni «aktiv» səbətinə
    düşsəydilər operator hesabın girə bildiyini zənn edərdi.
    """
    if status == STATUS_ACTIVE:
        return (
            Q(**{f"{prefix}is_active": True})
            & ~Q(**{f"{prefix}profile__is_deleted": True})
            & ~Q(**{f"{prefix}profile__access_state": _ARCHIVED})
        )
    if status == STATUS_BLOCKED:
        return Q(**{f"{prefix}is_active": False}) & ~Q(**{f"{prefix}profile__is_deleted": True})
    if status == STATUS_DELETED:
        return Q(**{f"{prefix}profile__is_deleted": True})
    if status == STATUS_ARCHIVED:
        return Q(**{f"{prefix}profile__access_state": _ARCHIVED}) & ~Q(**{f"{prefix}profile__is_deleted": True})
    return Q()


def gender_q(gender: str, prefix: str) -> Q:
    """Cins filtri. ``unspecified`` səbəti mövcud sətirlərin ~79 %-idir — gizlədilmir."""
    if gender not in GENDER_BUCKETS:
        return Q()
    return Q(**{f"{prefix}profile__gender": gender})


def _shift_years(reference: date, years: int) -> date:
    """`reference` tarixindən `years` il əvvəl (29 fevral təhlükəsiz)."""
    try:
        return reference.replace(year=reference.year - years)
    except ValueError:  # 29 fevral → 28 fevral
        return reference.replace(month=2, day=28, year=reference.year - years)


def age_q(filters: PeopleFilters, prefix: str, *, today: date | None = None) -> Q:
    """Yaş aralığı filtri — doğum tarixindən hesablanır.

    ``age_unknown`` seçilibsə filtr TƏRSİNƏ işləyir: yalnız doğum tarixi
    OLMAYANLAR göstərilir. Bu, sahibin «təyin edilməyib səbətini açıq göstər»
    tələbinin backend qarşılığıdır — data 28 % dolu olduğu üçün qalan 72 %-in
    ünvanlana bilməsi məlumat itkisinin qarşısını alır.
    """
    field = f"{prefix}profile__birth_date"
    if filters.age_unknown:
        return Q(**{f"{field}__isnull": True})
    if filters.age_min is None and filters.age_max is None:
        return Q()
    today = today or date.today()
    condition = Q(**{f"{field}__isnull": False})
    if filters.age_min is not None:
        condition &= Q(**{f"{field}__lte": _shift_years(today, filters.age_min)})
    if filters.age_max is not None:
        condition &= Q(**{f"{field}__gt": _shift_years(today, filters.age_max + 1)})
    return condition


def account_status_of(user) -> str:
    """Bir hesabın kataloq statusu — RİM `account_status` ilə EYNİ qayda."""
    profile = getattr(user, "profile", None)
    if profile is not None and getattr(profile, "is_deleted", False):
        return STATUS_DELETED
    if not getattr(user, "is_active", False):
        return STATUS_BLOCKED
    if profile is not None and getattr(profile, "access_state", "") == _ARCHIVED:
        return STATUS_ARCHIVED
    return STATUS_ACTIVE


__all__ = [
    "ALLOWED_STATUSES",
    "MAX_AGE",
    "SEARCH_FIELDS",
    "STATUS_ACTIVE",
    "STATUS_ALL",
    "STATUS_ARCHIVED",
    "STATUS_BLOCKED",
    "STATUS_DELETED",
    "PeopleFilters",
    "account_status_of",
    "age_q",
    "gender_q",
    "parse_filters",
    "search_q",
    "status_q",
]

"""RİM istifadəçi axtarışı — ad + soyad + ATA ADI (username bilmədən).

Əsas ssenari (cutover): müəllim zəng edib «Mən Əliyev Elvin Səməd oğluyam,
sistemə girə bilmirəm» deyir. RİM operatoru username-i BİLMİR. Ona görə axtarış
sorğusu SÖZLƏRƏ bölünür və hər söz ad/soyad/ata adı/username/email/FİN
sahələrindən HƏR HANSI BİRİNƏ uyğun gəlməlidir (AND-of-ORs).

Nümunə: «Əliyev Elvin» → (ad|soyad|ata adı|… LIKE %Əliyev%) AND
                          (ad|soyad|ata adı|… LIKE %Elvin%)

Beləcə söz sırası əhəmiyyət daşımır («Elvin Əliyev» də tapır) və ad+soyad eyni
olan iki hesab ata adı ilə ayrılır.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Q

from ...models import UserProfile
from .policy import PERM_SEARCH, RimActor, manageable_users_queryset, require_permission

_ARCHIVED_ACCESS_STATE = UserProfile.AccessState.ARCHIVED

#: Sorğu sözünün axtarıldığı sahələr.
_SEARCH_FIELDS = (
    "first_name",
    "last_name",
    "username",
    "email",
    "profile__patronymic",
    "profile__fin",
)

#: Bir sorğuda nəzərə alınan maksimum söz (DoS qoruması — hər söz ayrı JOIN şərtidir).
MAX_QUERY_TOKENS = 6
MAX_QUERY_LENGTH = 120
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50

STATUS_ALL = "all"
STATUS_ACTIVE = "active"
STATUS_BLOCKED = "blocked"
STATUS_DELETED = "deleted"
#: Məzun/xaric arxiv hesabı. ``auth_user.is_active`` QƏSDƏN True-dur (registrar
#: trigger-ləri üçün), ona görə «aktiv» kimi görünsəydi operator hesabın girə
#: bildiyini zənn edərdi — ayrıca status olması təhlükəsizlik deyil, DOĞRULUQ
#: məsələsidir.
STATUS_ARCHIVED = "archived"
ALLOWED_STATUSES = (STATUS_ALL, STATUS_ACTIVE, STATUS_BLOCKED, STATUS_DELETED, STATUS_ARCHIVED)


def normalize_query(raw_query) -> str:
    return " ".join(str(raw_query or "").strip().split())[:MAX_QUERY_LENGTH]


def build_search_filter(query: str) -> Q:
    """Sorğu sözlərindən AND-of-ORs filtri qurur. Boş sorğu → boş Q (filtrsiz)."""
    tokens = [token for token in normalize_query(query).split(" ") if token][:MAX_QUERY_TOKENS]
    combined = Q()
    for token in tokens:
        token_filter = Q()
        for field_name in _SEARCH_FIELDS:
            token_filter |= Q(**{f"{field_name}__icontains": token})
        combined &= token_filter
    return combined


def apply_status_filter(queryset, status: str):
    """`active` / `blocked` / `deleted` statusuna görə filtr.

    Status hesabın CARİ vəziyyətidir: silinmiş hesab həm də `is_active=False`
    olur, ona görə «bloklanmış» silinmişləri qəsdən çıxarır.
    """
    if status == STATUS_ACTIVE:
        return (
            queryset.filter(is_active=True)
            .exclude(profile__is_deleted=True)
            .exclude(profile__access_state=_ARCHIVED_ACCESS_STATE)
        )
    if status == STATUS_BLOCKED:
        return queryset.filter(is_active=False).exclude(profile__is_deleted=True)
    if status == STATUS_DELETED:
        return queryset.filter(profile__is_deleted=True)
    if status == STATUS_ARCHIVED:
        return queryset.filter(profile__access_state=_ARCHIVED_ACCESS_STATE).exclude(profile__is_deleted=True)
    return queryset


def search_users(actor: RimActor, *, query="", status=STATUS_ALL, page=1, page_size=DEFAULT_PAGE_SIZE):
    """Səhifələnmiş axtarış nəticəsi qaytarır.

    İcazə qapısı burada tətbiq olunur — çağıran tərəf unutsa belə axtarış
    `user.search` olmadan işləmir (fail-closed).
    """
    require_permission(actor, PERM_SEARCH)

    status = str(status or STATUS_ALL).strip().lower()
    if status not in ALLOWED_STATUSES:
        status = STATUS_ALL

    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    queryset = manageable_users_queryset(actor)
    search_filter = build_search_filter(query)
    if search_filter:
        queryset = queryset.filter(search_filter)
    queryset = apply_status_filter(queryset, status)
    queryset = queryset.order_by("last_name", "first_name", "username")

    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(page)
    return {
        "results": list(page_obj.object_list),
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "total": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "query": normalize_query(query),
        "status": status,
    }


def account_status(user) -> str:
    """Hesabın RİM statusu: ``active`` / ``blocked`` / ``deleted`` / ``archived``."""
    profile = getattr(user, "profile", None)
    if profile is not None and getattr(profile, "is_deleted", False):
        return STATUS_DELETED
    if not getattr(user, "is_active", False):
        return STATUS_BLOCKED
    if profile is not None and getattr(profile, "access_state", "") == _ARCHIVED_ACCESS_STATE:
        return STATUS_ARCHIVED
    return STATUS_ACTIVE


__all__ = [
    "ALLOWED_STATUSES",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "MAX_QUERY_TOKENS",
    "STATUS_ACTIVE",
    "STATUS_ALL",
    "STATUS_ARCHIVED",
    "STATUS_BLOCKED",
    "STATUS_DELETED",
    "account_status",
    "apply_status_filter",
    "build_search_filter",
    "normalize_query",
    "search_users",
]

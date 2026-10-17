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
from django.db.models import Count, Exists, F, OuterRef, Q

from core.search_text import MAX_TOKENS, tolerant_q

from ...models import UserProfile
from ..people.constants import TEACHER_ROLE_NAMES
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
#: Kod kimi sahələr — ayırıcı/boşluğa dözümlü (kod rejimi).
_CODE_FIELDS = ("profile__fin",)

#: Bir sorğuda nəzərə alınan maksimum söz (DoS qoruması) — kanonik ``core.search_text.MAX_TOKENS``.
MAX_QUERY_TOKENS = MAX_TOKENS
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

# ── Sahib 2026-10-11: «ilk daxil olanda boş görünməsin» + əlavə filtr/sıralama ──────────────────────
#: Hesab növü — aktorun təşkilatındakı AKTİV üzvlüyün rolundan (superadmin üçün istənilən təşkilat).
KIND_ALL = ""
KIND_STUDENT = "student"
KIND_TEACHER = "teacher"
KIND_STAFF = "staff"
KIND_NONE = "none"
ALLOWED_KINDS = (KIND_STUDENT, KIND_TEACHER, KIND_STAFF, KIND_NONE)
STUDENT_ROLE_NAMES = ("student", "lead_student", "alumni")
#: Müəllim sayılanlar: kataloqun müəllim rolları + kafedra müdiri (dərs deyir). ``department_head`` QƏSDƏN
#: yoxdur — RİM-də o, inzibati şöbə müdiri kimi də işlənir (məktəb dəsti) və «Heyət»ə düşür.
TEACHING_ROLE_NAMES = (*TEACHER_ROLE_NAMES, "chair_head")

#: Hesab vəziyyəti bayrağı.
FLAG_INITIAL = "initial"  # ilk giriş gözlənilir (öz parolunu qurmayıb)
FLAG_NEVER = "never"  # sistemə heç daxil olmayıb
FLAG_UNVERIFIED = "unverified"  # email təsdiqlənməyib
FLAG_INCOMPLETE = "incomplete"  # məcburi profil məlumatı (FİN / telefon / e-poçt) boşdur — 2026-10-17
ALLOWED_FLAGS = (FLAG_INITIAL, FLAG_NEVER, FLAG_UNVERIFIED, FLAG_INCOMPLETE)

#: Sıralama. Sorğu YOXDURSA defolt «ən yeni» (operator son yaradılanları yoxlayır), varsa «ada görə».
SORT_NAME = "name"
SORT_RECENT = "recent"
SORT_LAST_LOGIN = "last_login"
SORTS = {
    SORT_NAME: ("last_name", "first_name", "username"),
    SORT_RECENT: ("-date_joined", "last_name", "first_name"),
    # Postgres DESC-də NULL-ları BİRİNCİ qoyur — heç daxil olmayanlar sona düşsün.
    SORT_LAST_LOGIN: (F("last_login").desc(nulls_last=True), "last_name", "first_name"),
}


def normalize_query(raw_query) -> str:
    return " ".join(str(raw_query or "").strip().split())[:MAX_QUERY_LENGTH]


def build_search_filter(query: str) -> Q:
    """Sorğu sözlərindən AND-of-ORs filtri qurur. Boş sorğu → boş Q (filtrsiz).

    Az/ing hərflərinə dözümlü (``core.search_text.tolerant_q``): «Aliyev» «Əliyev»i,
    «Sahzad» «Şahzad»ı tapır; FİN kod rejimindədir. Söz həddi kanonik ``MAX_TOKENS``-dir.
    """
    plain = tuple(field for field in _SEARCH_FIELDS if field not in _CODE_FIELDS)
    return tolerant_q(normalize_query(query), plain, compact_fields=_CODE_FIELDS) or Q()


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


def _membership_scope(actor: RimActor) -> Q:
    """Növ filtrinin baxdığı üzvlüklər: aktorun təşkilatı (superadmin — hamısı)."""
    scope = Q(user_id=OuterRef("pk"), is_active=True)
    if not actor.is_superadmin and actor.organization is not None:
        scope &= Q(organization=actor.organization)
    return scope


def apply_kind_filter(queryset, kind: str, actor: RimActor):
    """Tələbə / müəllim / heyət / rolsuz — EXISTS alt-sorğuları (JOIN dublikatı yoxdur)."""
    if kind not in ALLOWED_KINDS:
        return queryset
    from apps.organizations.models import Membership

    scope = _membership_scope(actor)
    any_role = Membership.objects.filter(scope)
    if kind == KIND_NONE:
        return queryset.filter(~Exists(any_role))
    if kind == KIND_STUDENT:
        return queryset.filter(Exists(any_role.filter(role__name__in=STUDENT_ROLE_NAMES)))
    if kind == KIND_TEACHER:
        return queryset.filter(Exists(any_role.filter(role__name__in=TEACHING_ROLE_NAMES)))
    return queryset.filter(
        Exists(any_role.exclude(role__name__in=(*STUDENT_ROLE_NAMES, *TEACHING_ROLE_NAMES, "member")))
    )


def apply_flag_filter(queryset, flag: str):
    if flag == FLAG_INITIAL:
        return queryset.filter(profile__password_change_required=True)
    if flag == FLAG_NEVER:
        return queryset.filter(last_login__isnull=True)
    if flag == FLAG_UNVERIFIED:
        return queryset.exclude(profile__email_verified=True)
    if flag == FLAG_INCOMPLETE:
        return _incomplete(queryset)
    return queryset


def _incomplete(queryset):
    """Qapının dayandıracağı hesablar: tələbə / heyət rolu var və vacib sahə boşdur (siyasət: profile_completion)."""
    from apps.organizations.models import Membership

    from ... import profile_completion

    gated_role = Membership.objects.filter(user_id=OuterRef("pk"), is_active=True).exclude(
        role__name__in=("alumni", "parent", "member")
    )
    return queryset.filter(profile_completion.missing_users_q()).filter(Exists(gated_role))


def status_counts(queryset) -> dict:
    """Status tabları üçün saylar — TƏK aqreqat sorğu (cari axtarış + növ + bayraq filtrlərinə görə)."""
    archived = Q(profile__access_state=_ARCHIVED_ACCESS_STATE)
    deleted = Q(profile__is_deleted=True)
    base = queryset.model.objects.filter(pk__in=queryset.order_by().values("pk"))
    counts = base.aggregate(
        all=Count("pk"),
        active=Count("pk", filter=Q(is_active=True) & ~deleted & ~archived),
        blocked=Count("pk", filter=Q(is_active=False) & ~deleted),
        archived=Count("pk", filter=archived & ~deleted),
        deleted=Count("pk", filter=deleted),
    )
    return {key: int(value or 0) for key, value in counts.items()}


def search_users(
    actor: RimActor,
    *,
    query="",
    status=STATUS_ALL,
    page=1,
    page_size=DEFAULT_PAGE_SIZE,
    kind="",
    flag="",
    sort="",
    with_counts=False,
):
    """Səhifələnmiş axtarış nəticəsi qaytarır.

    İcazə qapısı burada tətbiq olunur — çağıran tərəf unutsa belə axtarış
    `user.search` olmadan işləmir (fail-closed). Boş sorğu FİLTRSİZ siyahıdır (aktorun idarə
    sahəsi, səhifələnmiş) — ilk açılışda ekran boş qalmır (sahib 2026-10-11).
    """
    require_permission(actor, PERM_SEARCH)

    status = str(status or STATUS_ALL).strip().lower()
    if status not in ALLOWED_STATUSES:
        status = STATUS_ALL
    kind = str(kind or "").strip().lower()
    kind = kind if kind in ALLOWED_KINDS else KIND_ALL
    flag = str(flag or "").strip().lower()
    flag = flag if flag in ALLOWED_FLAGS else ""
    sort = str(sort or "").strip().lower()
    if sort not in SORTS:
        sort = SORT_NAME if normalize_query(query) else SORT_RECENT

    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    queryset = manageable_users_queryset(actor)
    search_filter = build_search_filter(query)
    if search_filter:
        queryset = queryset.filter(search_filter)
    queryset = apply_flag_filter(apply_kind_filter(queryset, kind, actor), flag)
    counts = status_counts(queryset) if with_counts else None
    queryset = apply_status_filter(queryset, status)
    queryset = queryset.order_by(*SORTS[sort], "pk")

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
        "kind": kind,
        "flag": flag,
        "sort": sort,
        "counts": counts,
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
    "ALLOWED_FLAGS",
    "ALLOWED_KINDS",
    "ALLOWED_STATUSES",
    "SORTS",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "MAX_QUERY_TOKENS",
    "STATUS_ACTIVE",
    "STATUS_ALL",
    "STATUS_ARCHIVED",
    "STATUS_BLOCKED",
    "STATUS_DELETED",
    "account_status",
    "apply_flag_filter",
    "apply_kind_filter",
    "apply_status_filter",
    "build_search_filter",
    "normalize_query",
    "search_users",
    "status_counts",
]

"""Akademik fəaliyyət qeydləri (AcademicProfileItem) üçün servis qatı.

Profil «Akademik fəaliyyət» bölməsinin CRUD məntiqi: sahiblik, rol-əsaslı növ
icazəsi, sahə validasiyası və say limitləri BURADA yoxlanılır — view qatı
yalnız HTTP giriş nöqtəsidir (SoC). Bax: docs/frontend/AJAX_SAFE_JS_PATTERN.md
(fetchJSON istehlakçısı: accounts/js/profile/academic_items.js).
"""

from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.accounts.models import AcademicProfileItem
from core.roles import ProfileRole

#: Hər növ üzrə istifadəçi başına maksimum qeyd — UI-nin oxunaqlı qalması və
#: sadə anti-abuse tavanı üçün.
MAX_ITEMS_PER_KIND = 30

TITLE_MAX_LENGTH = 200
DETAIL_MAX_LENGTH = 255
LINK_MAX_LENGTH = 300
YEAR_MIN = 1950

#: «Tədris etdiyi fənn» yalnız tədris heyəti üçün mənalıdır; qalan növlər
#: bütün rollara açıqdır (tələbə sertifikat/məqalə əlavə edə bilsin).
TEACHING_ONLY_KINDS = {AcademicProfileItem.Kind.SUBJECT}

#: «Qeyd tapılmadı.» — view qatı 404 statusunu bu mesajla tanıyır.
NOT_FOUND_ERROR = pgettext_lazy("accounts.academic_items.error", "Qeyd tapılmadı.")

#: Növ üzrə Font Awesome ikonları (idarəetmə + görünüş kartları).
KIND_ICONS = {
    AcademicProfileItem.Kind.SUBJECT: "fa-book-open",
    AcademicProfileItem.Kind.CERTIFICATE: "fa-certificate",
    AcademicProfileItem.Kind.PUBLICATION: "fa-file-lines",
    AcademicProfileItem.Kind.CONFERENCE: "fa-people-group",
}


def allowed_kinds_for(capabilities, user=None):
    """Rol imkanlarına görə icazəli növ dəyərlərinin siyahısı (sıralı).

    ``capabilities.is_teacher`` aktiv üzvlük kontekstindən gəlir
    ([[project_role_resolution_needs_active_membership]]); təşkilatsız (fərdi)
    müəllim üçün profil rolu fallback kimi yoxlanılır — rbac-dakı ``is_student``
    fallback-ının güzgüsü.
    """
    caps = capabilities or {}
    is_teaching_staff = bool(
        caps.get("is_teacher") or caps.get("is_unit_manager") or caps.get("is_org_admin") or caps.get("is_superadmin")
    )
    if not is_teaching_staff and user is not None:
        profile_role = getattr(getattr(user, "profile", None), "role", None)
        is_teaching_staff = profile_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}
    kinds = []
    for kind in AcademicProfileItem.Kind:
        if kind in TEACHING_ONLY_KINDS and not is_teaching_staff:
            continue
        kinds.append(kind)
    return kinds


def items_grouped_for(user, capabilities):
    """İstifadəçinin qeydlərini template üçün növ üzrə qruplaşdırır.

    Qaytarır: [{"kind", "label", "icon", "items": [...]}, ...] — yalnız
    icazəli növlər (boş qruplar da daxil, «Əlavə et» düyməsi görünsün deyə).
    """
    allowed = allowed_kinds_for(capabilities, user=user)
    items_by_kind = {kind: [] for kind in allowed}
    for item in user.academic_items.all():
        if item.kind in items_by_kind:
            items_by_kind[item.kind].append(item)
    return [
        {
            "kind": str(kind.value),
            "label": kind.label,
            "icon": KIND_ICONS.get(kind, "fa-star"),
            "items": items_by_kind[kind],
        }
        for kind in allowed
    ]


def display_groups_for(user):
    """Yalnız-oxu görünüş üçün DOLU qruplar (profil məlumatı + açıq profil).

    Rol icazəsi süzgəci yoxdur: qeyd mövcuddursa, yaradılarkən icazə yoxlanıb —
    kənar baxan da sahibin dərc etdiyi siyahını görür.
    """
    items_by_kind = {kind: [] for kind in AcademicProfileItem.Kind}
    for item in user.academic_items.all():
        if item.kind in items_by_kind:
            items_by_kind[item.kind].append(item)
    return [
        {
            "kind": str(kind.value),
            "label": kind.label,
            "icon": KIND_ICONS.get(kind, "fa-star"),
            "items": items_by_kind[kind],
        }
        for kind in AcademicProfileItem.Kind
        if items_by_kind[kind]
    ]


def _clean_year(raw_year):
    """İl sahəsini yoxlayır; (ok, dəyər|None, xəta) qaytarır."""
    text = str(raw_year or "").strip()
    if not text:
        return True, None, ""
    if not text.isdigit():
        return False, None, pgettext("accounts.academic_items.error", "İl rəqəmlə yazılmalıdır.")
    year = int(text)
    current_year = timezone.now().year
    if year < YEAR_MIN or year > current_year + 1:
        return (
            False,
            None,
            pgettext("accounts.academic_items.error", "İl %(low)s–%(high)s aralığında olmalıdır.")
            % {"low": YEAR_MIN, "high": current_year + 1},
        )
    return True, year, ""


def _clean_fields(*, kind, title, detail, year, link, capabilities, user=None):
    """Ümumi sahə validasiyası; (ok, cleaned|None, xəta) qaytarır."""
    valid_kinds = {str(k.value) for k in allowed_kinds_for(capabilities, user=user)}
    kind = str(kind or "").strip()
    if kind not in valid_kinds:
        return False, None, pgettext("accounts.academic_items.error", "Bu qeyd növü sizin rolunuz üçün mövcud deyil.")

    title = " ".join(str(title or "").split())
    if not title:
        return False, None, pgettext("accounts.academic_items.error", "Başlıq boş ola bilməz.")
    if len(title) > TITLE_MAX_LENGTH:
        return (
            False,
            None,
            pgettext("accounts.academic_items.error", "Başlıq %(limit)s simvoldan uzun ola bilməz.")
            % {"limit": TITLE_MAX_LENGTH},
        )

    detail = " ".join(str(detail or "").split())
    if len(detail) > DETAIL_MAX_LENGTH:
        return (
            False,
            None,
            pgettext("accounts.academic_items.error", "Ətraflı sahəsi %(limit)s simvoldan uzun ola bilməz.")
            % {"limit": DETAIL_MAX_LENGTH},
        )

    ok, year_value, error = _clean_year(year)
    if not ok:
        return False, None, error

    link = str(link or "").strip()
    if link:
        if len(link) > LINK_MAX_LENGTH:
            return (
                False,
                None,
                pgettext("accounts.academic_items.error", "Keçid %(limit)s simvoldan uzun ola bilməz.")
                % {"limit": LINK_MAX_LENGTH},
            )
        if not (link.startswith("https://") or link.startswith("http://")):
            return (
                False,
                None,
                pgettext("accounts.academic_items.error", "Keçid http:// və ya https:// ilə başlamalıdır."),
            )

    cleaned = {"kind": kind, "title": title, "detail": detail, "year": year_value, "link": link}
    return True, cleaned, ""


def create_item(user, capabilities, *, kind, title, detail="", year=None, link=""):
    """Yeni qeyd yaradır; (ok, item|None, xəta) qaytarır."""
    ok, cleaned, error = _clean_fields(
        kind=kind, title=title, detail=detail, year=year, link=link, capabilities=capabilities, user=user
    )
    if not ok:
        return False, None, error

    existing_count = user.academic_items.filter(kind=cleaned["kind"]).count()
    if existing_count >= MAX_ITEMS_PER_KIND:
        return (
            False,
            None,
            pgettext("accounts.academic_items.error", "Bu növ üzrə maksimum %(limit)s qeyd əlavə etmək olar.")
            % {"limit": MAX_ITEMS_PER_KIND},
        )

    item = AcademicProfileItem.objects.create(user=user, **cleaned)
    return True, item, ""


def update_item(user, capabilities, item_id, *, kind, title, detail="", year=None, link=""):
    """Mövcud qeydi yeniləyir; yalnız sahibi üçün. (ok, item|None, xəta)."""
    item = user.academic_items.filter(pk=item_id).first()
    if item is None:
        return False, None, str(NOT_FOUND_ERROR)

    ok, cleaned, error = _clean_fields(
        kind=kind, title=title, detail=detail, year=year, link=link, capabilities=capabilities, user=user
    )
    if not ok:
        return False, None, error

    # Növ dəyişirsə hədəf növün tavanı da qorunmalıdır — əks halda update ilə
    # per-kind limit keçilə bilərdi (2026-08-15 review tapıntısı).
    if cleaned["kind"] != item.kind:
        target_count = user.academic_items.filter(kind=cleaned["kind"]).exclude(pk=item.pk).count()
        if target_count >= MAX_ITEMS_PER_KIND:
            return (
                False,
                None,
                pgettext("accounts.academic_items.error", "Bu növ üzrə maksimum %(limit)s qeyd əlavə etmək olar.")
                % {"limit": MAX_ITEMS_PER_KIND},
            )

    for field, value in cleaned.items():
        setattr(item, field, value)
    item.save(update_fields=[*cleaned.keys(), "updated_at"])
    return True, item, ""


def delete_item(user, item_id):
    """Qeydi silir; yalnız sahibi üçün. (ok, xəta) qaytarır."""
    item = user.academic_items.filter(pk=item_id).first()
    if item is None:
        return False, str(NOT_FOUND_ERROR)
    item.delete()
    return True, ""

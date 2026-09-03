"""Vəzifə (staff position) etiket qatı — shared kernel.

İKİ İŞ GÖRÜR:

1. **«Üzv» doldurucusunu aradan qaldırır.**  ``member`` rolu real vəzifə deyil —
   o, heç bir vəzifəsi olmayan hesabın DEFOLT dəyəridir
   (``UserProfile.role`` default = ``member``).  Onu tələbənin/müəllimin adının
   yanında «Üzv» kimi yazmaq məzmunsuzdur; vəzifə yoxdursa **heç nə**
   yazılmamalıdır.

2. **Vəzifə etiketinin vahid həll zəncirini** verir::

       Membership.title  →  UserProfile.staff_position  →  real rol adı  →  ""

   İlk üç mənbədən hansı doludursa o göstərilir; heç biri yoxdursa boş sətir
   qayıdır və səth boşluq saxlayır.

⚠️ QAYDA: bu modul YALNIZ ETİKET qaytarır.  ``Membership.title`` və
``UserProfile.staff_position`` sırf mətn sahələridir — heç bir icazə, rol və ya
əhatə qərarı onlardan törəmir.  Legacy («myedudb») vəzifə kateqoriyaları da məhz
buna görə bura yazılır: naməlum bir mənbə kodu heç kimə səlahiyyət verə bilməz.

QAYDA: bu fayl heç bir app modulunu import edə bilməz (core→apps qadağandır).
"""

from django.utils.translation import pgettext_lazy

_POSITION_CTX = "organizations.staff_position"

#: Məzmunsuz doldurucu rol adları.  Bunlar şəxsin adının yanında vəzifə etiketi
#: kimi GÖSTƏRİLMİR.  Rol idarəetmə səthlərində (rol təyinatı, icazə redaktoru)
#: isə görünməyə davam edir — orada seçim variantıdır, etiket yox.
PLACEHOLDER_ROLE_NAMES = frozenset({"member"})


def is_placeholder_role_name(role_name) -> bool:
    """``role_name`` məzmunsuz doldurucu roldursa ``True``."""

    return str(role_name or "").strip().casefold() in PLACEHOLDER_ROLE_NAMES


def visible_role_label(role_name, role_label="") -> str:
    """Rol etiketi — doldurucu rol üçün boş sətir.

    2026-09-03: ``role_label`` seed zamanı yazılmış (dəyişməmiş) İngiliscə
    default dəyərdirsə ``core.roles.resolve_seeded_role_label`` onu AZ
    etiketlə əvəzləyir (PHASE21 U-2 — kabinetdə İngiliscə rol adları).
    Admin ``Role.display_name``-i fərqli bir mətnə dəyişibsə TOXUNULMUR.
    ``role_label`` heç nə vermirsə (nə seed, nə admin) ad özü qaytarılır.
    """

    if is_placeholder_role_name(role_name):
        return ""

    from core.roles import resolve_seeded_role_label

    label = str(resolve_seeded_role_label(role_name, role_label) or "").strip()
    if label:
        return label
    return str(role_name or "").strip()


def resolve_position_label(*, title="", staff_position="", role_name="", role_label="") -> str:
    """Vəzifə etiketi — title → staff_position → real rol → "".

    Heç bir mənbə yoxdursa boş sətir qayıdır (səthdə «Üzv» kimi doldurucu
    YAZILMIR).
    """

    explicit_title = str(title or "").strip()
    if explicit_title:
        return explicit_title
    explicit_position = str(staff_position or "").strip()
    if explicit_position:
        return explicit_position
    return visible_role_label(role_name, role_label)


# ── Legacy («myedudb») işçi kateqoriyaları ──────────────────────────────────
#
# Mənbədə ayrıca vəzifə cədvəli YOXDUR.  Yalnız `workers.inzibati` bayrağının
# mənası datadan təsdiqlənib (bax `docs/migration/LEGACY_STAFF_POSITIONS.md`);
# `workers.teacher_type` (1/2/3) NAMƏLUM qalır və heç bir etiketə çevrilmir.
LEGACY_STAFF_CATEGORY_ADMINISTRATIVE = "administrative"

LEGACY_STAFF_CATEGORY_LABELS = {
    LEGACY_STAFF_CATEGORY_ADMINISTRATIVE: pgettext_lazy(_POSITION_CTX, "İnzibati işçi"),
}


def legacy_staff_category_label(category):
    """Legacy kateqoriya kodunun tərcümə olunmuş etiketi (naməlumda ``None``)."""

    return LEGACY_STAFF_CATEGORY_LABELS.get(str(category or "").strip())

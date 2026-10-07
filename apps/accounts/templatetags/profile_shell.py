"""Profil örtüyü (sidebar) template tag-ləri.

* ``profile_sidebar`` — standalone səhifələr (məs. sual göndərişi workbench-i)
  profil sidebar-ını sol tərəfdə saxlaya bilsin deyə: sidebar-ı öz kontekstini
  HESABLAYARAQ render edir (cross-app Python importu yoxdur — tag accounts
  app-ındadır). Badge sayğacları verilmirsə şablonda sadəcə göstərilmir.
* ``profile_sidebar_layout`` — sidebar-ın DÜZÜMÜNÜ seçir (2026-09-25):
  tələbə/müəllim üçün düz menyu, qalan hər kəs üçün akkordeon. Qərar saf
  hesablamadır (``resolve_sidebar_layout``) — DB-yə getmir, sorğu büdcəsinə
  təsir etmir.
* ``profile_sidebar_filter_enabled`` — «Menyuda axtar» süzgəci yalnız uzun
  menyuda (> 20 bənd) göstərilir; say da eyni saf hesablamadandır.
* ``profile_can_reset_passwords`` / ``profile_surveys_inbox_count`` (2026-09-30) —
  «Tənzimləmələr → Parol sıfırlama» bəndinin görünürlüyü və «Sorğular» bəndinin
  badge-i. İkisi də `request`-dən hesablanır ki, SPA və embed sidebar EYNİ olsun.
* ``profile_section_css`` / ``profile_section_js`` (perf 2026-10-07) — kabinet qabığı
  yalnız RENDER OLUNAN bölmənin CSS/JS-ini verir (``views/profile/section_assets.py``).
"""

import logging

from django import template
from django.conf import settings
from django.urls import reverse
from django.utils.html import format_html_join

from apps.accounts.models import UserProfile
from apps.accounts.views._helpers.rbac import _role_capabilities
from apps.accounts.views.profile import section_assets
from apps.accounts.views.profile.context_builder._helpers import (
    _build_effective_user_roles,
    _build_primary_position_label,
)
from core.permissions import is_superadmin_user, request_has_permission

logger = logging.getLogger(__name__)

register = template.Library()

#: Sidebar düzümləri. «full» — heyətin akkordeonu (`sidebar/_group_*.html`).
SIDEBAR_LAYOUT_STUDENT = "student"
SIDEBAR_LAYOUT_TEACHER = "teacher"
SIDEBAR_LAYOUT_FULL = "full"

#: Düz ağacların GÖSTƏRƏ BİLDİYİ bölmə açarları. Mənbə şablonlardır:
#: `sidebar/compact/_student.html` və `_teacher.html` → daxil etdikləri
#: `sidebar/items/*.html`. Siyahı ilə şablon ayrılmasın deyə
#: `test_sidebar_compact.py` ikisini tutuşdurur. Ağaca bənd əlavə edəndə
#: açarı buraya da yazın; yazmasanız istifadəçi sadəcə akkordeona düşür
#: (heç nə itmir), əksinə — açar burada olub şablonda olmasa — bənd İTƏR.
COMPACT_SIDEBAR_TREES = {
    SIDEBAR_LAYOUT_STUDENT: frozenset(
        {
            "dashboard",
            "my-subjects",
            "my-schedule",
            "my-journal",
            "my-results",
            "my-transcript",
            "overall-academic",
            "academic-calendar",
            "my-subject-folders",
            "assigned-exams",
            "assigned-courses",
            "pending-answers",
            "my-appeals",
            "evaluation-survey",
            "surveys-inbox",
            "announcements",
            "notifications",
            "applications",
            "profile-info",
            "statistics",
        }
    ),
    SIDEBAR_LAYOUT_TEACHER: frozenset(
        {
            "dashboard",
            "my-journal",
            "my-schedule",
            "lessons-log",
            "subject-folders",
            "my-workload",
            "academic-calendar",
            "syllabus-list",
            "question-bank",
            "question-submissions",
            "my-exams",
            "my-courses",
            "pending-review",
            "subject-folder-review",
            "review-results",
            "notifications",
            "publish-notification",
            "applications",
            "surveys-inbox",
            "announcements",
            "profile-info",
            "statistics",
        }
    ),
}

#: Bölmə açarı OLMAYAN, bayraqla görünən bəndlər → onları göstərən düz ağaclar.
#: «İmtahan Nəzarət Sistemi» (`items/_final_center.html`) nəzarətçi müəllimdə var.
COMPACT_SIDEBAR_FLAG_ITEMS = {
    "can_access_final_center": frozenset({SIDEBAR_LAYOUT_TEACHER}),
}

#: Düzüm seçiminə TƏSİR ETMƏYƏN açarlar: menyuda ayrıca bənd kimi heç vaxt
#: görünməyənlər (gizli / yalnız URL ilə / başqa bəndin aktiv halı) və HƏR düzümdə
#: EYNİ yerdə — menyunun sonundakı «Tənzimləmələr» qrupunda — duranlar
#: (`sidebar/_group_settings.html`, 2026-09-30).
SIDEBAR_LAYOUT_NEUTRAL_SECTIONS = frozenset(
    {
        "blog",
        "delete-account",
        "student-organization-request",  # «Təşkilata qoşul» menyudan gizlidir
        "student-intake",  # «Tələbə qəbulu» (`student-admission`) onu əvəz edir
        "syllabus-editor",  # «Sillabuslar» bəndindən açılır, onu aktiv saxlayır
        "org-structure",  # köhnə açar — menyu bəndi yoxdur
        "groups",  # köhnə imtahan-kohortu bölməsi (2026-09-08 çıxarılıb)
        "edit-profile",  # «Tənzimləmələr» (2026-09-30; əvvəl header menyusunda)
        "change-password",  # «Tənzimləmələr» (2026-09-30; əvvəl header menyusunda)
        "account-password-reset",  # «Tənzimləmələr → Parol sıfırlama» (icazə ilə)
    }
)

#: «Parol sıfırlama» bölməsinin icazə açarı (NAV/PWD müqaviləsi 2026-09-30; bölmə
#: `account-password-reset`-i PWD qurur, menyu bəndi yalnız görünürlüyü yoxlayır).
PASSWORD_RESET_PERMISSION = "account.password_reset"

#: `request` üzərində «Sorğular» badge-inin keşi — kabinet renderində BİR çağırış.
_SURVEYS_INBOX_CACHE_ATTR = "_ems_surveys_inbox_badge"


#: «Menyuda axtar» süzgəci bu saydan başlayaraq göstərilir (sahib/orkestrator
#: 2026-09-25: «> 20 bənd» — qısa menyuda axtarış yalnız səs-küydür).
SIDEBAR_FILTER_MIN_ITEMS = 21


def _menu_sections(allowed_sections, capabilities, *, university_mode=True):
    """Menyuda AYRICA bənd kimi görünə bilən bölmə açarları (saf hesablama).

    Universitet rejimində tam menyu də bunları göstərmir: LMS kurs vitrini
    (`courses`) heç kimdə, bloq (`posts`, `create-post`) isə tələbədə gizlidir.
    """
    caps = capabilities or {}
    visible = set(allowed_sections or ()) - SIDEBAR_LAYOUT_NEUTRAL_SECTIONS
    if university_mode:
        visible.discard("courses")
        if caps.get("is_student"):
            visible -= {"posts", "create-post"}
    return visible


def sidebar_menu_item_count(allowed_sections, capabilities, *, university_mode=True):
    """Menyudakı bənd sayının (üst blok + qruplar) təxmini — süzgəc həddi üçün.

    Bölmə açarları + bayraqla görünən bəndlər («İmtahan Nəzarət Sistemi»).
    «Tənzimləmələr» qrupunun açarları (neytral) sayılmır — hədd əvvəlki kimi qalır.
    """
    caps = capabilities or {}
    flags = sum(1 for flag in COMPACT_SIDEBAR_FLAG_ITEMS if caps.get(flag))
    return len(_menu_sections(allowed_sections, caps, university_mode=university_mode)) + flags


def resolve_sidebar_layout(allowed_sections, capabilities, *, university_mode=True):
    """Sidebar düzümü: ``"student"`` | ``"teacher"`` | ``"full"``.

    Düz ağac YALNIZ istifadəçinin menyuda görünə bilən HƏR bölməsini əhatə
    edəndə seçilir — qarışıq rolda (müəllim + heyət, tələbə + müəllim,
    həvalə olunmuş idarəetmə bölməsi) akkordeon qalır ki, heç bir bənd
    itməsin. Görünürlük qaydaları DƏYİŞMİR: hər bəndin şərti yenə öz
    şablonundadır, burada yalnız təqdimat seçilir.
    """
    caps = capabilities or {}
    visible = _menu_sections(allowed_sections, caps, university_mode=university_mode)
    active_flags = {flag for flag in COMPACT_SIDEBAR_FLAG_ITEMS if caps.get(flag)}

    candidates = []
    if caps.get("is_student"):
        candidates.append(SIDEBAR_LAYOUT_STUDENT)
    if caps.get("is_teacher"):
        candidates.append(SIDEBAR_LAYOUT_TEACHER)
    for layout in candidates:
        if not visible <= COMPACT_SIDEBAR_TREES[layout]:
            continue
        if all(layout in COMPACT_SIDEBAR_FLAG_ITEMS[flag] for flag in active_flags):
            return layout
    return SIDEBAR_LAYOUT_FULL


@register.simple_tag(takes_context=True)
def profile_sidebar_layout(context):
    """`_sidebar.html` üçün düzüm — SPA və embed kontekstində eyni açarlar oxunur."""
    return resolve_sidebar_layout(
        context.get("allowed_sections") or (),
        context.get("role_capabilities") or {},
        university_mode=bool(context.get("university_mode", True)),
    )


@register.simple_tag(takes_context=True)
def profile_sidebar_filter_enabled(context):
    """«Menyuda axtar» süzgəci göstərilsinmi (menyuda > 20 bənd)."""
    count = sidebar_menu_item_count(
        context.get("allowed_sections") or (),
        context.get("role_capabilities") or {},
        university_mode=bool(context.get("university_mode", True)),
    )
    return count >= SIDEBAR_FILTER_MIN_ITEMS


@register.simple_tag(takes_context=True)
def profile_can_reset_passwords(context):
    """«Parol sıfırlama» bəndi görünsünmü: `account.password_reset` icazəsi və ya superadmin.

    Superadmin ƏVVƏL yoxlanır: `request_has_permission` üzvlüyü olmayan superadmin üçün
    hər çağırışda cross-org audit qeydi yazır — menyu renderi jurnalı doldurmasın.
    Faktiki qapı bölmənin öz view-undadır (PWD); bu yalnız menyu bəndidir.
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if request is None or not getattr(user, "is_authenticated", False):
        return False
    if is_superadmin_user(user):
        return True
    return request_has_permission(request, PASSWORD_RESET_PERMISSION)


@register.simple_tag(takes_context=True)
def profile_surveys_inbox_count(context):
    """«Sorğular» bəndinin badge-i — gözləyən sorğu sayı (0 → badge boş qalır).

    SRV-nin `apps.surveys.public.inbox_badge_count(user, organization)` funksiyası paralel
    qurulur, ona görə MÜDAFİƏLİ çağırılır: funksiya yoxdursa və ya xəta verirsə badge
    sadəcə görünmür, sidebar heç vaxt sınmır. Nəticə `request`-də keşlənir — kabinet
    renderində ən çoxu BİR çağırış (bənd bir neçə dəfə daxil olunsa belə).
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if request is None or not getattr(user, "is_authenticated", False):
        return 0
    cached = getattr(request, _SURVEYS_INBOX_CACHE_ATTR, None)
    if cached is not None:
        return cached
    count = 0
    try:
        from apps.surveys.public import inbox_badge_count

        count = max(0, int(inbox_badge_count(user, getattr(request, "organization", None)) or 0))
    except (ImportError, AttributeError):
        count = 0
    except Exception:  # noqa: BLE001 — sayğac sidebar-ı bloklamamalıdır
        logger.warning("surveys inbox badge failed", exc_info=True)
        count = 0
    setattr(request, _SURVEYS_INBOX_CACHE_ATTR, count)
    return count


def _asset_sections(context):
    return section_assets.asset_sections_for(context.get("active_section"), context.get("allowed_sections"))


@register.simple_tag(takes_context=True)
def profile_section_css(context):
    """Render olunan bölmənin (+ qabığın) CSS linkləri — `data-ems-css-order` kaskad sırasıdır.

    `section_assets.js` AJAX keçidində yeni linki bu sıraya görə yerləşdirir.
    """
    entries = section_assets.section_css(_asset_sections(context), context.get("allowed_sections"))
    return format_html_join(
        "\n", '<link rel="stylesheet" href="{}" data-ems-css-order="{}">', ((e["href"], e["order"]) for e in entries)
    )


@register.simple_tag(takes_context=True)
def profile_section_js(context, phase):
    """`_section_scripts.html`-in `phase` («pre» / «post») hissəsi — köhnə yerində, köhnə sırada."""
    srcs = section_assets.section_js(_asset_sections(context), context.get("allowed_sections"), phase)
    return format_html_join("\n", '<script src="{}"></script>', ((src,) for src in srcs))


@register.inclusion_tag("accounts/profile/_sidebar.html", takes_context=True)
def profile_sidebar(context, active_section=""):
    """Profil sidebar-ını verilmiş aktiv bölmə ilə render edir (standalone
    səhifələr üçün). Sidebar keçidləri tam URL-lərdir → profil səhifəsinə naviqasiya."""
    request = context.get("request")
    user = getattr(request, "user", None)
    profile = getattr(user, "profile", None)
    if profile is None and user is not None:
        profile = UserProfile.objects.filter(user=user).first()
    capabilities = _role_capabilities(user, profile)

    unread = 0
    try:
        from apps.notifications.public import get_unread_count

        unread = get_unread_count(user=user)
    except Exception:  # noqa: BLE001 — bildiriş sayğacı sidebar-ı bloklamamalıdır
        unread = 0

    # Inclusion tag TƏZƏ kontekstdə render olunur — context processor-lar
    # (university_mode, current_organization) və SPA-nın düzləşdirdiyi bayraqlar
    # burada YOXDUR. Onları özümüz veririk ki, standalone (embed) səhifələrdə
    # sidebar menyusu SPA ilə struktur olaraq eyni olsun (bax _sidebar.html-dəki
    # `not university_mode` / `current_organization` şərtləri). Hesab kartının
    # rol sətri SPA ilə EYNİ köməkçilərdəndir (üzvlüklər istifadəçidə keşlidir).
    return {
        "request": request,
        "role_capabilities": capabilities,
        "allowed_sections": capabilities.get("allowed_sections", []),
        "active_section": active_section,
        "profile_base_url": reverse("accounts:profile"),
        "notifications_unread_count": unread,
        "university_mode": bool(getattr(settings, "UNIVERSITY_MODE", True)),
        "current_organization": getattr(request, "organization", None),
        "can_manage_org": capabilities.get("can_manage_org"),
        "can_view_student_assignments": capabilities.get("can_view_student_assignments"),
        "primary_user_role_label": _build_primary_position_label(profile, _build_effective_user_roles(user, profile)),
    }

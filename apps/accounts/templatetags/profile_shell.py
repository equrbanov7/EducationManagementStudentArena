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
"""

from django import template
from django.conf import settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.views._helpers.rbac import _role_capabilities
from apps.accounts.views.profile.context_builder._helpers import (
    _build_effective_user_roles,
    _build_primary_position_label,
)

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
#: görünməyənlər (gizli / yalnız URL ilə / başqa bəndin aktiv halı) və hər iki
#: düzümdə EYNİ yerdə — alt hesab blokunda — duranlar.
SIDEBAR_LAYOUT_NEUTRAL_SECTIONS = frozenset(
    {
        "blog",
        "delete-account",
        "student-organization-request",  # «Təşkilata qoşul» menyudan gizlidir
        "student-intake",  # «Tələbə qəbulu» (`student-admission`) onu əvəz edir
        "syllabus-editor",  # «Sillabuslar» bəndindən açılır, onu aktiv saxlayır
        "org-structure",  # köhnə açar — menyu bəndi yoxdur
        "groups",  # köhnə imtahan-kohortu bölməsi (2026-09-08 çıxarılıb)
        "edit-profile",  # alt hesab bloku (hər iki düzüm)
        "change-password",  # alt hesab bloku (hər iki düzüm)
    }
)


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
    Alt hesab bloku sayılmır (onun bəndləri süzgəcə düşmür).
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

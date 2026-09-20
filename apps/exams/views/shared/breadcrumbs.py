"""İmtahan səhifələri üçün BREADCRUMB zənciri (sahib 2026-09-21).

«Geri düymələri hardan daxil olubsa ora qayıtsın, breadcrumbs qoş ki qarışıqlıq
olmasın.» Zəncir: kabinet bölməsi (``from_section``) → imtahan (detal) →
[aralıq səhifə] → cari səhifə. Bölmə adı kabinetin başlıq xəritəsi ilə EYNİ
msgid-lərdən gəlir (aşağıda `_SECTION_TITLES`) — eyni söz həm sidebar-da, həm
breadcrumb-da. Hər səhifə `exam_crumbs` kontekstini `exams/partials/_exam_crumbs.html`
ilə render edir; «Geri» düymələri isə əvvəlki kimi `return_to`/referer-ə qayıdır.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext_lazy

_VALID_SECTIONS = {
    "my-exams",
    "assigned-exams",
    "profile-info",
    "my-courses",
    "assigned-courses",
    "courses",
    "pending-review",
    "review-results",
}


#: Kabinet bölmə adları — `accounts.views.profile._sections.labels.build_section_titles`
#: ilə EYNİ msgctxt/msgid-lər (exams → accounts asılılığı yaratmamaq üçün burada
#: təkrarlanır; modul-sərhəd qapısı `exams → accounts` kənarına icazə vermir).
_SECTION_TITLES = {
    "my-exams": pgettext_lazy("profile.section", "my_exams"),
    "assigned-exams": pgettext_lazy("profile.section", "assigned_tasks"),
    "profile-info": pgettext_lazy("profile.section", "profile_info"),
    "my-courses": pgettext_lazy("profile.section", "my_created_courses"),
    "assigned-courses": pgettext_lazy("profile.section", "assigned_courses"),
    "courses": pgettext_lazy("profile.section", "my_courses"),
    "pending-review": pgettext_lazy("profile.section", "pending_review"),
    "review-results": pgettext_lazy("profile.sidebar", "Dəyərləndirilmiş nəticələr"),
}


def section_crumb(request, *, default_section="my-exams") -> dict:
    """Kabinet bölməsi krambı — `?from_section=` (etibarlı olmalıdır) və ya defolt."""
    section = (request.GET.get("from_section") or "").strip()
    if section not in _VALID_SECTIONS:
        section = default_section
    label = _SECTION_TITLES.get(section) or _SECTION_TITLES["my-exams"]
    return {"label": str(label), "url": f"{reverse('accounts:profile')}?section={section}"}


def exam_breadcrumbs(
    request, exam, *, current=None, navigation_query="", middle=None, default_section="my-exams"
) -> list:
    """[bölmə, imtahan, *aralıq, cari] — `current` boşdursa imtahan sonuncudur (detal səhifəsi)."""
    detail_url = reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
    if navigation_query:
        detail_url = f"{detail_url}?{navigation_query}"
    crumbs = [section_crumb(request, default_section=default_section), {"label": exam.title, "url": detail_url}]
    for item in middle or []:
        crumbs.append({"label": str(item.get("label", "")), "url": item.get("url", "")})
    if current:
        crumbs.append({"label": str(current), "url": ""})
    return crumbs

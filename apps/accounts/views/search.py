"""Qlobal axtarış (⌘K command palette) — role/tenant-aware JSON endpoint (U8).

Returns grouped quick-jump + entity results for the current user, scoped to the
active organisation (RLS) and gated by role capabilities:

* **Naviqasiya** — always-available quick links (profile, journal, schedule, …).
* **Jurnallarım** — offerings the user teaches (any instructor).
* **Fənlər / Tələbələr** — only for registrar-capable staff (privacy: a plain
  student can never enumerate other students).

The endpoint never leaks cross-tenant data: entity queries are filtered by
``request.organization`` and run under the request's RLS context.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _

from core.program_codes import PROGRAM_CODE_SEARCH_FIELDS
from core.search_text import tolerant_match, tolerant_q

from ._helpers import _role_capabilities
from .profile._sections.labels import build_section_titles

MAX_PER_GROUP = 6
#: Sorğu yazılanda naviqasiya qrupunun ölçüsü (bütün menyu bölmələri axtarılır).
MAX_NAV_MATCHES = 8
#: Menyudan birbaşa açılmayan / redaktor alt-səhifələri — axtarışda keçid kimi göstərilmir.
_NAV_SKIP = frozenset({"syllabus-editor", "curriculum-editor", "create-post", "create-category", "posts", "blog"})
#: İnsanların yazdığı sinonimlər (başlıqda olmayan): «parol» ↔ «şifrə», «anket» ↔ «sorğu» …
_NAV_KEYWORDS = {
    "change-password": "parol şifrə password dəyiş",
    "account-password-reset": "parol şifrə sıfırla reset unutdu",
    "edit-profile": "profil redaktə email e-poçt poçt telefon şəkil",
    "surveys-inbox": "sorğu anket survey",
    "surveys-builder": "sorğu anket survey qurucu yarat",
    "evaluation-survey": "sorğu anket qiymətləndirmə müəllim",
    "rim-center": "rim hesab istifadəçi blok",
    "publish-notification": "bildiriş göndər elan xəbər",
    "people-teachers": "müəllim heyət kataloq",
    "people-students": "tələbə kataloq siyahı",
    "question-bank": "sual bank",
    "my-results": "nəticə bal qiymət",
    "audit-log": "audit jurnal log hərəkət",
    "org-overview": "təşkilat universitet panel ümumi baxış statistika",
    "org-members": "üzv üzvlər işçi heyət siyahı",
    "org-roles": "rol rollar icazə",
}
#: Əlavə bölmələrin ikonları (yoxdursa ümumi ox).
_NAV_ICONS = {
    "dashboard": "fa-house",
    "edit-profile": "fa-user-pen",
    "change-password": "fa-key",
    "account-password-reset": "fa-key",
    "rim-center": "fa-user-shield",
    "surveys-inbox": "fa-square-poll-vertical",
    "surveys-builder": "fa-pen-ruler",
    "evaluation-survey": "fa-square-poll-vertical",
    "evaluation-results": "fa-chart-simple",
    "evaluation-campaigns": "fa-bullhorn",
    "publish-notification": "fa-paper-plane",
    "statistics": "fa-chart-column",
    "people-teachers": "fa-chalkboard-user",
    "people-students": "fa-user-graduate",
    "student-registry": "fa-id-card",
    "groups-registry": "fa-people-group",
    "programs-registry": "fa-graduation-cap",
    "subject-catalog": "fa-book",
    "syllabus-list": "fa-file-lines",
    "question-bank": "fa-circle-question",
    "my-results": "fa-square-poll-horizontal",
    "my-courses": "fa-layer-group",
    "courses": "fa-layer-group",
    "my-appeals": "fa-scale-balanced",
    "manage-appeals": "fa-scale-balanced",
    "appeal-stats": "fa-scale-balanced",
    "my-workload": "fa-briefcase",
    "workload-center": "fa-briefcase",
    "audit-log": "fa-clipboard-list",
    "org-members": "fa-users",
    "org-overview": "fa-gauge-high",
    "org-roles": "fa-user-shield",
    "schedule-manage": "fa-calendar-plus",
    "exam-center-pins": "fa-hashtag",
    "exam-center-stats": "fa-chart-pie",
    "applications": "fa-inbox",
}
MIN_ENTITY_QUERY = 2
#: Tələbə nəticəsinin kod sahələri: ixtisas şifrləri (hər iki nəsil) + alt sətirdə görünən qrup adı
#: («234king» → «234 K ing»). Qısa hərf tokeni («PA») kod sahəsində də bitişik axtarılır
#: (``core.search_text.code_regex``), ona görə «Qrup A1-1»ə uyğun gəlmir (proqram-şifr invariantı).
_STUDENT_CODE_FIELDS = tuple(f"program__{field}" for field in PROGRAM_CODE_SEARCH_FIELDS) + ("group__name",)


def _nav_targets(caps):
    """Rol-aware sürətli keçidlər — HAMISI profil shell-inin İÇİNƏ açılır (U16).

    "Bir səhifə, bir URL": nəticəyə klik sidebar-ı itirmir — `?section=` shell
    naviqasiyasıdır. Bölmə siyahısı ``allowed_sections``-a bağlıdır, ona görə
    superadminin söndürdüyü modullar axtarışdan da avtomatik itir. İSTİSNA
    YOXDUR: 2026-09-10-a qədər «Registrar (kataloq)» köhnə müstəqil
    `registrar:console` səhifəsinə atırdı (sahib: «bunu sil, bu köhnədi») —
    həmin səhifə silindi, keçid indi kabinet bölməsidir."""
    profile_url = reverse("accounts:profile")

    def shell(section):
        return f"{profile_url}?section={section}"

    allowed = caps.get("allowed_sections", set())
    candidates = [
        ("profile-info", _("Profil"), "fa-user", "profil dashboard kabinet profile"),
        ("my-subjects", _("Fənlərim"), "fa-book-open", "fənn subject kredit qayıb"),
        ("my-transcript", _("Transkript"), "fa-scroll", "transkript transcript gpa"),
        ("my-journal", _("Elektron jurnal"), "fa-book-open", "jurnal journal qiymət davamiyyət"),
        ("my-schedule", _("Dərs cədvəli"), "fa-calendar-week", "cədvəl schedule dərs vaxt"),
        ("academic-calendar", _("Akademik təqvim"), "fa-calendar-days", "təqvim calendar sessiya qeydiyyat"),
        ("journal-close", _("Jurnal bağlama"), "fa-lock", "jurnal bağla semestr rim"),
        (
            "exam-score-entry",
            _("İmtahan balının daxil edilməsi"),
            "fa-pen-to-square",
            "imtahan bal yazılı praktiki kağız daxil",
        ),
        ("analytics", _("Akademik analitika"), "fa-chart-line", "analitika statistika gpa keçid"),
        ("my-exams", _("İmtahanlarım"), "fa-clipboard-check", "imtahan exam test"),
        ("assigned-exams", _("İmtahanlar"), "fa-clipboard-check", "imtahan exam test"),
        ("notifications", _("Bildirişlər"), "fa-bell", "bildiriş notification xəbər"),
        ("registrar-catalog", _("Registrar (kataloq)"), "fa-sitemap", "registrar program fənn kataloq"),
    ]
    targets = [
        (title, icon, shell(section), keywords)
        for section, title, icon, keywords in candidates
        if section == "profile-info" or section in allowed
    ]
    # Sahib 2026-10-01: «fərdə görə» — istifadəçinin SOL MENYUSUNDAKI hər bölmə axtarışda tapılsın
    # (əvvəl yalnız yuxarıdakı 13 keçid idi: «parol», «sorğu», «RİM» heç nə tapmırdı). Başlıq
    # kabinetin öz başlığıdır (dil ilə); boş sorğuda yalnız yuxarıdakı seçilmiş keçidlər görünür.
    curated = {section for section, *_rest in candidates}
    titles = build_section_titles()
    for section in sorted(allowed):
        if section in curated or section in _NAV_SKIP or section not in titles:
            continue
        title = str(titles[section])
        keywords = f"{section.replace('-', ' ')} {title} {_NAV_KEYWORDS.get(section, '')}"
        targets.append((title, _NAV_ICONS.get(section, "fa-arrow-right"), shell(section), keywords))
    return targets


def _nav_group(caps, query):
    items = []
    for title, icon, url, keywords in _nav_targets(caps):
        # Az/ing dözümlü («jurnal», «cedvel» → «cədvəl»); boş sorğu → hamısı.
        if tolerant_match(query, f"{title} {keywords}"):
            items.append({"title": str(title), "subtitle": "", "icon": icon, "url": url})
    return items[: (MAX_NAV_MATCHES if query else MAX_PER_GROUP)]


def _journal_group(user, organization, query):
    Offering = django_apps.get_model("registrar", "CourseOffering")
    qs = Offering.objects.filter(instructor=user, is_active=True)
    if organization is not None:
        qs = qs.filter(organization=organization)
    # Fənn adı mətn, fənn kodu və qrup adı (alt sətirdə görünür) kod rejimində.
    search = tolerant_q(query, ("subject__name",), compact_fields=("subject__code", "group__name"))
    if search is not None:
        qs = qs.filter(search)
    qs = qs.select_related("subject", "group")[:MAX_PER_GROUP]
    return [
        {
            "title": f"{o.subject.code} — {o.subject.name}",
            "subtitle": o.group.name if o.group_id else "",
            "icon": "fa-book-open",
            "url": reverse("registrar:journal_detail", args=[o.id]),
        }
        for o in qs
    ]


def _section_url(section, params=None):
    """Kabinet bölməsinə keçid — lazım olsa bölmənin ÖZ süzgəc parametri ilə.

    Nəticəyə klik istifadəçini sətrin ÜSTÜNƏ gətirir: kataloq/reyestr sətirləri
    dialoqda açılır, ona görə birbaşa «sətir URL-i» yoxdur — əvəzinə bölmənin
    axtarış süzgəci öncədən doldurulur."""
    query = urlencode({"section": section, **(params or {})})
    return f"{reverse('accounts:profile')}?{query}"


def _subject_group(organization, query):
    Subject = django_apps.get_model("registrar", "Subject")
    qs = Subject.objects.filter(organization=organization)
    search = tolerant_q(query, ("name",), compact_fields=("code",))
    if search is not None:
        qs = qs.filter(search)
    qs = qs[:MAX_PER_GROUP]
    return [
        {
            "title": f"{s.code} — {s.name}",
            "subtitle": "",
            "icon": "fa-atom",
            "url": _section_url("registrar-catalog", {"rc_tab": "subjects", "rc_q": s.code}),
        }
        for s in qs
    ]


def _student_scope(request, organization, caps):
    """Tələbə axtarışının struktur süzgəci + e-poçt axtarışına icazə.

    Təhlükəsizlik auditi 2026-10-05: əvvəl BÜTÜN təşkilat axtarılırdı — UNIT-scope-lu
    dekan/koordinator öz fakültəsindən kənar tələbələri tapırdı, e-poçt sahəsi isə
    kontakt icazəsi olmayana oracle idi. Scope axtarışı AÇAN icazədən hesablanır
    (``member.view`` / ``member.student_manage``); ``None`` = scope yoxdur (fail-closed).
    """
    from apps.accounts.services.people import resolve_actor as resolve_people_actor
    from apps.organizations.public import get_permission_scope

    can_view_contacts = bool(caps.get("can_manage_registrar")) or resolve_people_actor(request).can_view_contacts
    if caps.get("can_manage_registrar"):
        return Q(), can_view_contacts
    permission = "member.view" if caps.get("can_search_directory") else "member.student_manage"
    scope = get_permission_scope(request.user, organization, permission, request=request)
    if scope.is_org_wide:
        return Q(), can_view_contacts
    if not scope.has_structure_access:
        return None, can_view_contacts
    return scope.unit_subtree_q(path_field="group__path", id_field="group_id"), can_view_contacts


def _student_group(organization, query, *, scope_q=None, search_email=True):
    """Tələbə nəticələri — alt sətirdə GÖSTƏRİLƏN hər şey axtarıla bilər.

    AXTARIŞ İNVARİANTI: alt sətir ``program.display_label`` çap edir («Dünya
    iqtisadiyyatı · 050401»), ona görə süzgəc yalnız ad/username üzrə qala
    bilməz — istifadəçi eyni qutuda GÖRDÜYÜ şifri yazanda sıfır nəticə alırdı.
    ``PROGRAM_CODE_SEARCH_FIELDS`` HƏR İKİ nəsil şifri əhatə edir; ``display_code``
    köhnə şifrə geri çəkildiyi üçün tək ``official_code`` kifayət etmir.

    Performans: ``program``/``group`` onsuz da ``select_related``-dədir, ona
    görə ``program__*`` süzgəci ƏLAVƏ JOIN açmır (Django eyni forward-FK
    join-unu təkrar istifadə edir) və sətir sayı ``MAX_PER_GROUP`` ilə kəsilir.
    """
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    qs = Record.objects.filter(organization=organization)
    if scope_q is not None:
        qs = qs.filter(scope_q)
    # Tokenləşmiş + az/ing dözümlü («Ad Soyad», «Aliyev» → «Əliyev», «Shahzad» →
    # «Şahzad»); şifrlər kod rejimində — bax core/search_text.py.
    fields = ("student__first_name", "student__last_name", "student__username", "program__name")
    search = tolerant_q(
        query,
        fields + (("student__email",) if search_email else ()),
        compact_fields=_STUDENT_CODE_FIELDS,
    )
    if search is not None:
        qs = qs.filter(search)
    qs = qs.select_related("student", "program", "group")[:MAX_PER_GROUP]
    items = []
    for r in qs:
        name = r.student.get_full_name() or r.student.username
        parts = [p for p in (r.program.display_label if r.program_id else "", r.group.name if r.group_id else "") if p]
        items.append(
            {
                "title": name,
                "subtitle": " · ".join(parts),
                "icon": "fa-user-graduate",
                "url": _section_url("student-registry", {"sr_q": r.student.username}),
            }
        )
    return items


@login_required
def global_search(request):
    """JSON: ``{"query", "groups": [{"key", "label", "items": [...]}]}``."""
    query = (request.GET.get("q") or "").strip()
    profile = getattr(request.user, "profile", None)
    caps = _role_capabilities(request.user, profile)
    organization = getattr(request, "organization", None)

    groups = []
    payload = {"query": query, "groups": groups}
    if not query:
        # «Son baxılanlar» (brauzerdə) yalnız hələ də icazəli bölmələri göstərsin.
        payload["nav_urls"] = [url for _title, _icon, url, _keywords in _nav_targets(caps)]

    nav_items = _nav_group(caps, query)
    if nav_items:
        groups.append({"key": "nav", "label": _("Naviqasiya"), "items": nav_items})

    if len(query) >= MIN_ENTITY_QUERY:
        journals = _journal_group(request.user, organization, query)
        if journals:
            groups.append({"key": "journals", "label": _("Jurnallarım"), "items": journals})

        can_search_people = (
            caps.get("can_search_directory")
            or caps.get("can_manage_registrar")
            or caps.get("teacher_can_manage_students")
        )
        if organization is not None and can_search_people:
            if caps.get("can_search_directory") or caps.get("can_manage_registrar"):
                subjects = _subject_group(organization, query)
                if subjects:
                    groups.append({"key": "subjects", "label": _("Fənlər"), "items": subjects})
            scope_q, search_email = _student_scope(request, organization, caps)
            students = (
                _student_group(organization, query, scope_q=scope_q, search_email=search_email)
                if scope_q is not None
                else []
            )
            if students:
                groups.append({"key": "students", "label": _("Tələbələr"), "items": students})

    return JsonResponse(payload)

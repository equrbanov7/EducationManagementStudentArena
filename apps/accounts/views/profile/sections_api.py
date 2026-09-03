"""
Profile section API (P3.1 + P3.2) — progressive enhancement endpoints.

Two endpoints:

* ``profile_section_fragment`` — returns HTML for the active section partial
  so the frontend can swap only the main content area without a full page
  reload. Reuses ``user_profile`` for context-building so permission, tenant,
  RLS and section-gating behaviour stays identical to ``/accounts/profile/``.

* ``profile_badges_api`` — returns sidebar badge counts as JSON via the
  cheap counters from ``_dashboard_helpers.cheap_counts``.

Server-side ``/accounts/profile/?section=...`` continues to work untouched;
the AJAX endpoints are pure progressive enhancement.

Security guarantees:
- ``@login_required`` on every endpoint
- only sections in ``AJAX_SAFE_SECTIONS`` are exposed via AJAX (forms/admin
  sections remain full-page only)
- access check uses the same ``_role_capabilities(...).allowed_sections``
  contract as ``user_profile``
- CSRF for these GET endpoints is irrelevant (read-only); POST forms inside
  rendered partials continue to use Django's CSRF middleware as before
- tenant/RLS scoping comes "for free" because we delegate to ``user_profile``
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse

# from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.models import UserProfile
from apps.notifications.public import build_profile_notification_state, get_unread_count
from core.cache import get_or_set_cached_profile_badge_counts
from core.logging_utils import safe_log_value

from .._dashboard_helpers.cheap_counts import compute_profile_badge_counts, count_assigned_tasks
from .._helpers import _get_active_organization, _role_capabilities

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Section mapping
# --------------------------------------------------------------------------- #

# Bütün mövcud profile section-ları → partial template adı.
SECTION_PARTIALS: dict[str, str] = {
    # «Ana səhifə» — kabinetin default bölməsi (FAZA 22).
    "dashboard": "accounts/profile/sections/_dashboard.html",
    "profile-info": "accounts/profile/sections/_profile_info.html",
    "notifications": "accounts/profile/sections/_notifications.html",
    "publish-notification": "accounts/profile/sections/_publish_notification.html",
    "create-post": "accounts/profile/sections/_create_post.html",
    "posts": "accounts/profile/sections/_posts.html",
    "my-exams": "accounts/profile/sections/_my_exams.html",
    "my-courses": "accounts/profile/sections/_my_courses.html",
    "courses": "accounts/profile/sections/_courses.html",
    "assigned-exams": "accounts/profile/sections/_assigned_exams.html",
    "assigned-courses": "accounts/profile/sections/_assigned_courses.html",
    "my-results": "accounts/profile/sections/_my_results.html",
    "my-subjects": "accounts/profile/sections/_my_subjects.html",
    "my-transcript": "accounts/profile/sections/_my_transcript.html",
    "overall-academic": "accounts/profile/sections/_overall_academic.html",
    "pending-answers": "accounts/profile/sections/_pending_answers.html",
    "groups": "accounts/profile/sections/_groups.html",
    "pending-post-approvals": "accounts/profile/sections/_pending_post_approvals.html",
    "pending-review": "accounts/profile/sections/_pending_review.html",
    "review-results": "accounts/profile/sections/_review_results.html",
    "role-assignment": "accounts/profile/sections/_role_assignment.html",
    "student-organization-request": "accounts/profile/sections/_student_org_request.html",
    "student-organization-management": "accounts/profile/sections/_student_org_management.html",
    "permission-editor": "accounts/profile/sections/_permission_editor.html",
    "manage-roles": "accounts/profile/sections/_manage_roles.html",
    "category-management": "accounts/profile/sections/_category_management.html",
    "create-category": "accounts/profile/sections/_create_category.html",
    "superadmin-org-features": "accounts/profile/sections/superadmin/_superadmin_org_features.html",
    "superadmin-organizations": "accounts/profile/sections/superadmin/_superadmin_organizations.html",
    "superadmin-users": "accounts/profile/sections/superadmin/_superadmin_user_management.html",
    "rim-center": "accounts/profile/sections/_rim_center.html",
    "superadmin-ai": "accounts/profile/sections/superadmin/_superadmin_ai_settings.html",
    "superadmin-exam-rooms": "accounts/profile/sections/superadmin/_superadmin_exam_rooms.html",
    "exam-center-pins": "accounts/profile/sections/_exam_center_pins.html",
    "exam-center-stats": "accounts/profile/sections/_exam_center_stats.html",
    "appeal-stats": "accounts/profile/sections/_appeal_stats.html",
    "kollokvium-windows": "accounts/profile/sections/_kollokvium_windows.html",
    "exam-score-entry": "accounts/profile/sections/_exam_score_entry.html",
    "legacy-grade-review": "accounts/profile/sections/_legacy_grade_review.html",
    "superadmin-contact-messages": "accounts/profile/sections/superadmin/_superadmin_contact_messages.html",
    "system-monitoring": "accounts/profile/sections/superadmin/_system_monitoring.html",
    "statistics": "accounts/profile/sections/_statistics.html",
    "edit-profile": "accounts/profile/sections/_edit_profile.html",
    "change-password": "accounts/profile/sections/_change_password.html",
    "question-bank": "accounts/profile/sections/_question_bank.html",
    "question-submissions": "accounts/profile/sections/_question_submissions.html",
    "my-appeals": "accounts/profile/sections/_my_appeals.html",
    "manage-appeals": "accounts/profile/sections/_manage_appeals.html",
    "org-structure": "accounts/profile/sections/_org_structure.html",
    "org-faculties": "accounts/profile/sections/_org_faculties.html",
    "org-kafedras": "accounts/profile/sections/_org_kafedras.html",
    "org-members": "accounts/profile/sections/_org_members.html",
    "org-roles": "accounts/profile/sections/_org_roles.html",
    "audit-log": "accounts/profile/sections/_audit_log.html",
    # 2026-08-27: bu ikisi `profile.html`-in `data-ajax-sections` siyahısında
    # VAR idi, amma burada YOX idi — yəni ön tərəf fraqment istəyirdi, backend
    # isə `_ensure_section_allowed`-da 403 qaytarırdı.  Dekan/kafedra müdiri
    # menyuda «Bölmə imtahanları»nı görür, klikləyəndə isə xəta alırdı.
    # (Tam səhifə yolu `?section=` işləyirdi — ona görə problem yalnız QA
    # süpürgəsində üzə çıxdı.)
    "unit-exams": "accounts/profile/sections/_unit_exams.html",
    "superadmin-org-inspector": "accounts/profile/sections/superadmin/_superadmin_org_inspector.html",
    # U12 — registrar kabinet bölmələri (profil shell-inin içində)
    "my-schedule": "accounts/profile/sections/_my_schedule.html",
    "academic-calendar": "accounts/profile/sections/_academic_calendar.html",
    "my-journal": "accounts/profile/sections/_my_journal.html",
    "journal-close": "accounts/profile/sections/_journal_close.html",
    # Cədvəl idarəetməsi (`schedule.manage`) — server-render panel, mutasiyalar
    # ayrıca JSON POST endpoint-inə gedir → AJAX swap təhlükəsizdir.
    "schedule-manage": "accounts/profile/sections/_schedule_manage.html",
    # «Tələbə idxalı» (`user.import`) — server yalnız çərçivəni verir; fayl
    # yüklənməsi, quru icra və tətbiq ayrıca JSON endpoint-lərinə gedir →
    # AJAX swap təhlükəsizdir.
    "student-intake": "accounts/profile/sections/_student_intake.html",
    # «Müraciətlərim» (apps.applications) — server yalnız çərçivəni verir,
    # bütün mutasiyalar ayrıca JSON endpoint-lərinə gedir → AJAX swap təhlükəsizdir.
    "applications": "accounts/profile/sections/_applications.html",
    "analytics": "accounts/profile/sections/_analytics.html",
    "academic-records": "accounts/profile/sections/_academic_records.html",
    # «Müəllimlər» / «Tələbələr» kataloqu (icazə: `people.*`, scope: unit)
    "people-teachers": "accounts/profile/sections/_people_teachers.html",
    "people-students": "accounts/profile/sections/_people_students.html",
    # Sillabus — müəllim səthi. Redaktor ayrıca TAM SƏHİFƏ deyil: o da profil
    # shell-inin içində açılır (sol sidebar qalır), hədəf versiya `?version=`
    # sorğu parametrindən gəlir.
    # Fənn təhvili (`journal.reassign`) — RİM / dekan / kafedra müdiri.
    "teaching-handover": "accounts/profile/sections/_teaching_handover.html",
    "syllabus-list": "accounts/profile/sections/_syllabus_list.html",
    "syllabus-editor": "accounts/profile/sections/_syllabus_editor.html",
    "syllabus-review": "accounts/profile/sections/_syllabus_review.html",
    # «Sual təsdiqi» (kafedra müdiri) — OXU-ONLY növbə; qərar ayrıca səhifədə.
    "question-chair-review": "accounts/profile/sections/_question_chair_review.html",
    # Dərs yükü (apps.workload) — kafedra bölgüsü + müəllimin öz yükü.
    "workload-distribution": "accounts/profile/sections/_workload_distribution.html",
    "my-workload": "accounts/profile/sections/_my_workload.html",
    # Mərhələ 4 — dərs yükü zənciri: tədris şöbəsi mərkəzi (12), koordinator
    # vizası (13), dekanlıq təsdiqi (15), rektorluq ümumi baxışı (17).
    # Hamısı SERVER-render OXU panelidir; mutasiyalar tək JSON POST-a gedir.
    "workload-center": "accounts/profile/sections/_workload_center.html",
    "workload-visa": "accounts/profile/sections/_workload_visa.html",
    "workload-approval": "accounts/profile/sections/_workload_approval.html",
    "workload-overview": "accounts/profile/sections/_workload_overview.html",
    # Tədris şöbəsi (dizayn handoff Mərhələ 1) — struktur ağacı, kafedra profili,
    # ixtisas reyestri, fənn kataloqu. Hamısı SERVER-render OXU panelidir;
    # mutasiyalar ayrıca JSON POST endpoint-lərinə gedir → AJAX swap təhlükəsizdir.
    "org-structure-tree": "accounts/profile/sections/_org_structure_tree.html",
    "chair-profile": "accounts/profile/sections/_chair_profile.html",
    "programs-registry": "accounts/profile/sections/_programs_registry.html",
    "subject-catalog": "accounts/profile/sections/_subject_catalog.html",
    # Mərhələ 2 — tədris planı redaktoru, akademik qrup reyestri, semestr açılışı.
    "curriculum-editor": "accounts/profile/sections/_curriculum_editor.html",
    "groups-registry": "accounts/profile/sections/_groups_registry.html",
    "semester-opening": "accounts/profile/sections/_semester_opening.html",
    # Mərhələ 3 — Tələbə Xidmətləri Mərkəzi: qəbul (08) və reyestr (09).
    # Hər ikisi SERVER-render OXU panelidir; mutasiyalar ayrıca JSON /
    # multipart endpoint-lərinə gedir → AJAX swap təhlükəsizdir.
    # Mərhələ 6 — ekran 21 «Keçilmiş dərslər» (müəllim + nəzarətçi, OXU-ONLY).
    "lessons-log": "accounts/profile/sections/_lessons_log.html",
    "student-admission": "accounts/profile/sections/_student_admission.html",
    "student-registry": "accounts/profile/sections/_student_registry.html",
}

# AJAX-safe sections (P3.4) — read-mostly bölmələr. Form-heavy admin
# bölmələri normal full-page naviqasiyada qalır.
AJAX_SAFE_SECTIONS: frozenset[str] = frozenset(
    {
        # «Ana səhifə» tam server-render, YALNIZ-OXU xülasədir → AJAX-safe.
        "dashboard",
        "profile-info",
        "notifications",
        "posts",
        "my-exams",
        "my-courses",
        "courses",
        "assigned-exams",
        "assigned-courses",
        "my-results",
        "my-subjects",
        "my-transcript",
        "overall-academic",
        "pending-answers",
        "groups",
        "pending-review",
        "review-results",
        "statistics",
        "system-monitoring",
        "pending-post-approvals",
        "question-bank",
        "question-submissions",
        "my-appeals",
        "manage-appeals",
        "org-structure",
        "org-faculties",
        "org-kafedras",
        "org-members",
        "org-roles",
        "audit-log",
        # Hər ikisi OXU-ONLY siyahıdır (form/admin vəziyyəti daşımır) — AJAX-safe.
        "unit-exams",
        "superadmin-org-inspector",
        # RİM mərkəzi — panel oxu-only render olunur (bütün mutasiyalar ayrıca
        # JSON POST endpoint-inə gedir), ona görə AJAX swap təhlükəsizdir.
        "rim-center",
        # U12 — registrar kabinet bölmələri (read-mostly; formlar registrar
        # endpoint-lərinə POST edir və `next` ilə shell-ə qayıdır).
        "my-schedule",
        "schedule-manage",
        "student-intake",
        "applications",
        "academic-calendar",
        "my-journal",
        "analytics",
        # Kataloq panelləri OXU-ONLY render olunur (bütün mutasiyalar ayrıca
        # JSON POST endpoint-inə gedir) → AJAX swap təhlükəsizdir.
        "people-teachers",
        "people-students",
        # Sillabus siyahısı və redaktoru OXU-ONLY render olunur — bütün yazı
        # əməliyyatları ayrıca JSON POST endpoint-inə gedir (autosave/əməllər),
        # ona görə AJAX swap təhlükəsizdir.
        "syllabus-list",
        "syllabus-editor",
        "syllabus-review",
        # Kafedra sual təsdiqi növbəsi OXU-ONLY render olunur (qərar ayrıca
        # səhifədə, POST-la) → AJAX swap təhlükəsizdir.
        "question-chair-review",
        # Fənn təhvili paneli də OXU-ONLY render olunur: cədvəl/seçicilər JSON
        # GET-lə, təhvil və geri qaytarma isə ayrıca JSON POST-la gedir.
        "teaching-handover",
        # Dərs yükü panelləri SPA-dır: server çərçivəni verir, sətirlər JSON
        # GET-lə gəlir, bölgü/təsdiq isə ayrıca JSON POST-la gedir.
        "workload-distribution",
        "my-workload",
        # Mərhələ 4 zənciri — panellər OXU-ONLY render olunur, mutasiyalar
        # `workload:action` endpoint-inə gedir → AJAX swap təhlükəsizdir.
        "workload-center",
        "workload-visa",
        "workload-approval",
        "workload-overview",
        # Dəqiqləşdirmə növbəsi də OXU-ONLY render olunur — server yalnız
        # çərçivəni verir, sətirlər JSON GET-lə gəlir, qərar/düzəliş isə ayrıca
        # POST endpoint-inə (multipart, sənədlə) gedir.
        "legacy-grade-review",
        # Tədris şöbəsi bölmələri — server yalnız oxu panelini verir; yaratma,
        # redaktə, rəhbər təyini və arxivləmə ayrıca JSON POST-a gedir.
        "org-structure-tree",
        "chair-profile",
        "programs-registry",
        "subject-catalog",
        # Mərhələ 2 panelləri də OXU-ONLY render olunur: plan sətri, qrup və
        # açılış mutasiyaları ayrıca JSON POST endpoint-lərinə gedir.
        "curriculum-editor",
        "groups-registry",
        "semester-opening",
        # Mərhələ 3 — qəbul paneli faylı ayrıca multipart endpoint-inə göndərir,
        # reyestr isə server-render cədvəldir (filtr/sıralama linklə).
        "student-admission",
        "student-registry",
        # Ekran 21 — tam OXU-ONLY hesabat paneli (mutasiya yoxdur) → AJAX-safe.
        "lessons-log",
    }
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _ensure_section_allowed(request: HttpRequest, section: str):
    """
    Return ``(profile, capabilities)`` if user may access ``section`` via AJAX,
    otherwise return ``None``.

    Permission contract is identical to ``user_profile``:
    - section must be in ``SECTION_PARTIALS``
    - section must be in ``AJAX_SAFE_SECTIONS`` (form/admin sections excluded)
    - section must be in the user's ``allowed_sections``
    """
    if section not in SECTION_PARTIALS:
        return None
    if section not in AJAX_SAFE_SECTIONS:
        return None
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)
    if section not in capabilities["allowed_sections"]:
        return None
    return profile, capabilities


# --------------------------------------------------------------------------- #
# P3.1 — Section HTML fragment endpoint
# --------------------------------------------------------------------------- #


@never_cache
@login_required
@require_GET
def profile_section_fragment(request: HttpRequest, section: str) -> HttpResponse:
    """
    Render and return only the active section's HTML partial.

    Reuses ``user_profile``'s full context builder so all permission, tenant,
    RLS, search, filter and pagination behaviour is identical to
    ``/accounts/profile/?section=<name>``.

    P3-extra — `@never_cache` qoyulub. Bu response istifadəçi/sessiya/təşkilat-a
    bağlı olduğu üçün brauzer və ya proxy onu kəş etməməlidir.
    """
    access = _ensure_section_allowed(request, section)
    if access is None:
        return JsonResponse(
            {"ok": False, "error": "forbidden_or_unknown_section"},
            status=403,
        )

    # Delegate context-building to user_profile via the existing
    # `_render_profile_section` helper. We set `direct_profile_section` so the
    # full-page template renders only the active section in case the caller
    # falls back to the full-page response (defensive).
    request.direct_profile_section = section
    mutable_get = request.GET.copy()
    mutable_get["section"] = section
    request.GET = mutable_get

    # KRİTİK: fragment KANONİK profil URL-i kimi render olunmalıdır.
    # Şablonlarda çoxlu form `next`/canonical üçün `request.get_full_path`-i
    # istifadə edir. Bu endpoint (`/accounts/profile/api/sections/...`) ilə
    # render olunanda həmin `next` API URL-inə işarələyir; full form submit
    # (moderate/delete/dil dəyişmə) `url_has_allowed_host_and_scheme`-dən keçib
    # istifadəçini xam JSON səhifəsinə aparır. `request.path`-i kanonik profil
    # URL-inə çeviririk ki, `get_full_path()` `/accounts/profile/?section=...`
    # qaytarsın. `resolver_match` (nav-active) dəyişmir, çünki o ayrıca atributdur.
    from django.urls import reverse

    _canonical_profile_path = reverse("accounts:profile")
    request.path = _canonical_profile_path
    request.path_info = _canonical_profile_path
    request.META["QUERY_STRING"] = mutable_get.urlencode()

    # Context yığımı tam profil view-i ilə EYNİ kod yolundan keçir (icazə,
    # tenant, RLS, axtarış, filtr, səhifələmə davranışı dəyişmir), lakin render
    # YALNIZ bölmənin öz partial-ına tətbiq olunur.
    #
    # ƏVVƏL: bu endpoint `user_profile(request)` çağırıb BÜTÜN səhifəni
    # (navbar + sidebar + footer + ~90 asset teqi) render edir, JSON-a bükür və
    # frontend oradan bir DOM node-u çıxarırdı — yəni hər bölmə dəyişməsində tam
    # səhifə render olunurdu. Kodun öz şərhi bunu müvəqqəti geri düşmə kimi
    # qeyd edib və `build_profile_context` hook-unu tələb edirdi; hook indi var.
    from django.template.loader import render_to_string

    from .context_builder.builder import build_profile_context

    early_response, context = build_profile_context(request)

    if early_response is not None:
        status = getattr(early_response, "status_code", 200)
        if 300 <= status < 400:
            return JsonResponse(
                {"ok": False, "error": "redirect_required", "location": early_response.get("Location", "")},
                status=409,
            )
        return JsonResponse({"ok": False, "error": "unavailable"}, status=status if status >= 400 else 409)

    # Bölmə context yığıldıqdan sonra da icazəli olmalıdır: `allowed_sections`
    # aktiv təşkilat kontekstindən asılıdır və `_ensure_section_allowed`
    # yoxlaması ondan ƏVVƏL işləyir.
    if section not in set(context.get("allowed_sections") or ()):
        return JsonResponse({"ok": False, "error": "forbidden_or_unknown_section"}, status=403)

    try:
        html = render_to_string(SECTION_PARTIALS[section], context, request=request)
    except Exception:  # noqa: BLE001 — defensive
        logger.exception("profile section fragment render failed: %s", safe_log_value(section))
        return JsonResponse({"ok": False, "error": "render_failed"}, status=500)

    return JsonResponse(
        {
            "ok": True,
            "section": section,
            "html": html,
            # Frontend hint: which DOM selector to extract from `html`.
            "extract_selector": '[data-profile-section-panel="{}"]'.format(section),
        }
    )


# --------------------------------------------------------------------------- #
# P3.2 — Sidebar badge endpoint
# --------------------------------------------------------------------------- #


@never_cache
@login_required
@require_GET
def profile_badges_api(request: HttpRequest) -> JsonResponse:
    """
    Lightweight JSON endpoint returning sidebar badge counts the user is
    allowed to see. The student/reviewer counts come from the SAME cached bundle
    (``get_or_set_cached_profile_badge_counts`` → ``compute_profile_badge_counts``)
    that ``user_profile`` uses, so page, section fragments and this API stay
    consistent and the heavy COUNT/aggregate queries run at most once per
    (user, org) per TTL window.

    P3-extra — `@never_cache` (HTTP) qalır; badge dəyərləri Redis-də ~45s
    eventual-consistent saxlanılır (öz datası, kiçik staleness məqbul).
    """
    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)

    payload: dict[str, int] = {}

    # In-app + org notifications (cheap counts).
    notification_state = build_profile_notification_state(user=request.user, profile=profile)
    in_app_unread = get_unread_count(user=request.user)
    payload["notifications_unread_count"] = notification_state.get("unread_count", 0) + in_app_unread

    # P3 — Student + reviewer badge sayğacları user_profile ilə EYNİ cached
    # dəstdən gəlir (köhnə inline ~90-sətirlik dublikat aqreqasiya silindi: DRY +
    # drift riski aradan qalxdı). Eyni (user, aktiv org) açarı paylaşıldığına görə
    # tam profil səhifəsi, section fragment-ləri və bu API həmişə eyni rəqəmləri
    # qaytarır (uyğunsuz "flicker" olmur). Qeyd: badge-lər ~45s eventual-consistent
    # olur; ani yenilənmə lazım olduqda submit/qiymətləndirmə kodu
    # core.cache.invalidate_profile_badge_counts_cache çağırmalıdır.
    active_org = _get_active_organization(request)

    def _compute_shared_badges() -> dict[str, int]:
        from apps.courses.models import Course
        from apps.exams.models import Exam

        from .._helpers import _tenant_scoped_courses, _tenant_scoped_exams

        return compute_profile_badge_counts(
            request,
            request.user,
            capabilities=capabilities,
            my_exams_qs=_tenant_scoped_exams(request, Exam.objects.filter(author=request.user)),
            teacher_courses=_tenant_scoped_courses(request, Course.objects.filter(owner=request.user)),
        )

    shared_badges = get_or_set_cached_profile_badge_counts(
        user_id=request.user.pk,
        org_id=active_org.pk if active_org is not None else None,
        compute=_compute_shared_badges,
    )
    if capabilities.get("can_view_student_assignments"):
        # This badge is part of the active task workflow: after a student finishes
        # an exam, the assigned-task panel is already live-empty, so the sidebar
        # must not wait for the short shared badge cache to expire.
        payload["assigned_tasks_count"] = count_assigned_tasks(request, request.user)
        payload["my_results_count"] = shared_badges.get("my_results", 0)
        payload["pending_answers_count"] = shared_badges.get("pending_answers", 0)
    if capabilities.get("can_review_submissions"):
        payload["pending_review_count"] = shared_badges.get("pending_review", 0)
        payload["evaluated_review_count"] = shared_badges.get("evaluated_review", 0)
    # «Müraciətlərim» — sayğac paylaşılan (keşlənən) dəstdən gəlir; müraciət
    # mutasiyaları keşi `applications.services.notify` içindən invalidasiya edir.
    if "applications" in capabilities.get("allowed_sections", set()):
        payload["applications_pending_count"] = shared_badges.get("applications_pending", 0)
    # «Sual təsdiqi» — kafedra növbəsi; yazılar keşi servis qatından
    # (``question_chair_review._invalidate_badges``) invalidasiya edir.
    if "question-chair-review" in capabilities.get("allowed_sections", set()):
        payload["question_chair_pending_count"] = shared_badges.get("question_chair_pending", 0)
    if capabilities.get("can_manage_appeals"):
        from apps.appeals.public import count_pending_manage_appeals

        payload["pending_appeals_count"] = count_pending_manage_appeals(request)

    # Post-approval badge (teachers/admins with that allowed section)
    if "pending-post-approvals" in capabilities.get("allowed_sections", set()):
        from apps.accounts import profile_hooks

        payload["pending_post_approval_count"] = profile_hooks.pending_posts_count(request.user)

    # Superadmin badges
    if capabilities.get("is_superadmin"):
        from apps.organizations.models import Organization

        payload["superadmin_pending_org_count"] = Organization.objects.filter(status="pending").count()
        if "superadmin-contact-messages" in capabilities.get("allowed_sections", set()):
            from apps.contact.models import ContactMessage
            from apps.trial_exams.models import TrialExamRequest

            payload["contact_unhandled_count"] = min(
                ContactMessage.objects.filter(is_handled=False).count()
                + TrialExamRequest.objects.filter(is_handled=False).count(),
                99,
            )

    return JsonResponse({"ok": True, "badges": payload})


__all__ = [
    "SECTION_PARTIALS",
    "AJAX_SAFE_SECTIONS",
    "profile_section_fragment",
    "profile_badges_api",
]

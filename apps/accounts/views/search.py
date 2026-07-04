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
from django.utils.translation import gettext as _

from ._helpers import _role_capabilities

MAX_PER_GROUP = 6
MIN_ENTITY_QUERY = 2


def _nav_targets(caps):
    """Static, role-aware quick-jump destinations (title + fa icon + keywords)."""
    targets = [
        (_("Profil"), "fa-user", reverse("accounts:profile"), "profil dashboard kabinet profile"),
        (_("Elektron jurnal"), "fa-book-open", reverse("registrar:journal_list"), "jurnal journal qiymət davamiyyət"),
        (_("Dərs cədvəli"), "fa-calendar-week", reverse("registrar:schedule"), "cədvəl schedule dərs vaxt"),
        (_("İmtahanlar"), "fa-clipboard-check", reverse("exams:student_exam_list"), "imtahan exam test"),
        (
            _("Bildirişlər"),
            "fa-bell",
            reverse("accounts:profile") + "?section=notifications",
            "bildiriş notification xəbər",
        ),
    ]
    if caps.get("can_approve_grades"):
        targets.append(
            (_("Qiymət təsdiqləri"), "fa-clipboard-check", reverse("registrar:approvals_inbox"), "təsdiq approval")
        )
    if caps.get("can_manage_registrar"):
        targets.append(
            (_("Registrar (kataloq)"), "fa-sitemap", reverse("registrar:console"), "registrar program fənn kataloq")
        )
    return targets


def _nav_group(caps, query):
    ql = query.lower()
    items = []
    for title, icon, url, keywords in _nav_targets(caps):
        if not ql or ql in f"{title} {keywords}".lower():
            items.append({"title": str(title), "subtitle": "", "icon": icon, "url": url})
    return items[:MAX_PER_GROUP]


def _journal_group(user, organization, query):
    Offering = django_apps.get_model("registrar", "CourseOffering")
    qs = Offering.objects.filter(instructor=user, is_active=True)
    if organization is not None:
        qs = qs.filter(organization=organization)
    qs = qs.filter(Q(subject__code__icontains=query) | Q(subject__name__icontains=query)).select_related(
        "subject", "group"
    )[:MAX_PER_GROUP]
    return [
        {
            "title": f"{o.subject.code} — {o.subject.name}",
            "subtitle": o.group.name if o.group_id else "",
            "icon": "fa-book-open",
            "url": reverse("registrar:journal_detail", args=[o.id]),
        }
        for o in qs
    ]


def _subject_group(organization, query):
    Subject = django_apps.get_model("registrar", "Subject")
    qs = Subject.objects.filter(organization=organization).filter(Q(code__icontains=query) | Q(name__icontains=query))[
        :MAX_PER_GROUP
    ]
    return [
        {
            "title": f"{s.code} — {s.name}",
            "subtitle": "",
            "icon": "fa-atom",
            "url": reverse("registrar:subject_edit", args=[s.id]),
        }
        for s in qs
    ]


def _student_group(organization, query):
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    qs = (
        Record.objects.filter(organization=organization)
        .filter(
            Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(student__username__icontains=query)
            | Q(student__email__icontains=query)
        )
        .select_related("student", "program", "group")[:MAX_PER_GROUP]
    )
    items = []
    for r in qs:
        name = r.student.get_full_name() or r.student.username
        parts = [p for p in (r.program.code if r.program_id else "", r.group.name if r.group_id else "") if p]
        items.append(
            {
                "title": name,
                "subtitle": " · ".join(parts),
                "icon": "fa-user-graduate",
                "url": reverse("registrar:student_record_edit", args=[r.id]),
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

    nav_items = _nav_group(caps, query)
    if nav_items:
        groups.append({"key": "nav", "label": _("Naviqasiya"), "items": nav_items})

    if len(query) >= MIN_ENTITY_QUERY:
        journals = _journal_group(request.user, organization, query)
        if journals:
            groups.append({"key": "journals", "label": _("Jurnallarım"), "items": journals})

        can_manage = caps.get("can_manage_registrar") or caps.get("teacher_can_manage_students")
        if organization is not None and can_manage:
            if caps.get("can_manage_registrar"):
                subjects = _subject_group(organization, query)
                if subjects:
                    groups.append({"key": "subjects", "label": _("Fənlər"), "items": subjects})
            students = _student_group(organization, query)
            if students:
                groups.append({"key": "students", "label": _("Tələbələr"), "items": students})

    return JsonResponse({"query": query, "groups": groups})

"""
Superadmin təşkilat baxışı ("Təşkilat məlumatları") bölməsinin datası.

Superadmin istənilən təşkilatı seçib onun imtahanlarına, nəticələrinə,
sual banklarına və kurslarına read-only baxa bilir.

Performans:
- Yalnız aktiv tabın queryset-i qurulur (digər tablar üçün sorğu YOXDUR).
- Hər siyahı select_related/annotate ilə N+1-siz gəlir və paginate olunur.
- Say göstəriciləri tək aggregate sorğusu ilə alınır.
Təhlükəsizlik: yalnız superadmin (rbac allowed_sections + burada təkrar yoxlama);
cross-org sorğular RLS bypass ilə işləyir (superadmin kontekstində təhlükəsizdir,
middleware request sonunda RLS kontekstini sıfırlayır.
"""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q

INSPECT_TABS = ("exams", "results", "banks", "courses")
PAGE_SIZE = 12


def build_superadmin_org_inspector_section(request, *, is_superadmin):
    from apps.organizations.models import Organization

    section = {
        "is_allowed": bool(is_superadmin),
        "organizations": [],
        "selected_org": None,
        "active_tab": "exams",
        "org_search": "",
        "page_obj": None,
        "counts": {},
        "pagination_query": "",
        "tab_query_base": "",
    }
    if not is_superadmin:
        return section

    from core.rls import bypass_rls

    org_search = (request.GET.get("inspect_org_search") or "").strip()[:120]
    selected_org_id = (request.GET.get("inspect_org") or "").strip()
    active_tab = (request.GET.get("inspect_tab") or "exams").strip().lower()
    if active_tab not in INSPECT_TABS:
        active_tab = "exams"

    section["org_search"] = org_search
    section["active_tab"] = active_tab

    with bypass_rls():
        org_qs = Organization.objects.filter(is_active=True).order_by("name")
        if org_search:
            org_qs = org_qs.filter(Q(name__icontains=org_search) | Q(slug__icontains=org_search))
        # Select üçün yüngül siyahı — yalnız lazım olan sütunlar.
        section["organizations"] = list(org_qs.values("id", "name", "org_type")[:200])

        selected_org = None
        if selected_org_id:
            selected_org = Organization.objects.filter(id=selected_org_id, is_active=True).first()
        section["selected_org"] = selected_org
        if selected_org is None:
            return section

        section["counts"] = _org_counts(selected_org)
        section["page_obj"] = _tab_page(request, selected_org, active_tab)

    base_params = {
        "section": "superadmin-org-inspector",
        "inspect_org": selected_org.id,
        "inspect_org_search": org_search,
    }
    section["tab_query_base"] = urlencode({k: v for k, v in base_params.items() if v})
    section["pagination_query"] = urlencode({k: v for k, v in {**base_params, "inspect_tab": active_tab}.items() if v})
    return section


def _org_counts(organization):
    """Tab başlıqları üçün saylar — hər model üzrə tək COUNT sorğusu."""
    from apps.courses.models import Course
    from apps.exams.models import Exam, ExamAttempt, QuestionBank

    return {
        "exams": Exam.objects.filter(organization=organization).count(),
        "results": ExamAttempt.objects.filter(
            exam__organization=organization, status__in=["submitted", "expired"]
        ).count(),
        "banks": QuestionBank.objects.filter(organization=organization).count(),
        "courses": Course.objects.filter(organization=organization).count(),
    }


def _tab_page(request, organization, tab):
    """Yalnız aktiv tabın paginated queryset-i."""
    from apps.courses.models import Course
    from apps.exams.models import Exam, ExamAttempt, QuestionBank

    page_number = request.GET.get("inspect_page")

    if tab == "exams":
        qs = (
            Exam.objects.filter(organization=organization)
            .select_related("author", "course")
            .annotate(attempts_total=Count("attempts", distinct=True))
            .order_by("-created_at")
        )
    elif tab == "results":
        qs = (
            ExamAttempt.objects.filter(exam__organization=organization, status__in=["submitted", "expired"])
            .select_related("exam", "user")
            .order_by("-started_at")
        )
    elif tab == "banks":
        qs = (
            QuestionBank.objects.filter(organization=organization)
            .select_related("created_by")
            .annotate(question_total=Count("library_questions", distinct=True))
            .order_by("-created_at")
        )
    else:  # courses
        qs = (
            Course.objects.filter(organization=organization)
            .select_related("owner", "unit")
            .annotate(members_total=Count("memberships", distinct=True))
            .order_by("-created_at")
        )

    return Paginator(qs, PAGE_SIZE).get_page(page_number)


__all__ = ["build_superadmin_org_inspector_section", "INSPECT_TABS"]

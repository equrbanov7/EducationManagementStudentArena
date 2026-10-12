"""Profil "unit-exams" bölməsi üçün context-fragment qurucusu.

Dekan/kafedra müdürü üçün öz alt-ağacının imtahanlarına oxu-only baxış. Data
scope-u ``organizations.scoping`` ilə.
"""

from django.core.paginator import Paginator
from django.db.models import Count, Q

from apps.accounts.views._helpers.formatting import _query_string
from apps.accounts.views._helpers.tenant import _get_active_organization
from core.search_text import tolerant_q


def _defaults() -> dict:
    return {
        "unit_exams_page_obj": None,
        "unit_exams_search_query": "",
        "unit_exams_total_count": 0,
        "unit_exams_pagination_query": "",
    }


def _subtree_exam_q(Exam, Membership, org, subtree_ids):
    """İmtahan alt-ağaca aiddirmi — əvvəl imtahanın ÖZ bağlantısı, yoxdursa müəllifin ƏSAS üzvlüyü.

    2026-10-13 (rol auditi B19): əvvəl müəllifin alt-ağacda İSTƏNİLƏN üzvlüyü kifayət edirdi — başqa
    kafedranın yükünü alan müəllimə verilən ƏLAVƏ müəllim üzvlüyü (``is_primary=False``, workload Forma 1
    importu) həmin müəllimin bütün imtahanlarını (başqa fakültənin fənləri daxil) bu dekana/müdirə açırdı.

    * Öz bağlantı (dəqiq): fənnin kafedrası (``subject.chair_unit``), kursun vahidi (``course.unit``) və ya
      təyin olunmuş reyestr qrupu (``allowed_units``) alt-ağacdadır.
    * Bağlantısız imtahan (fənn/kurs/qrup yoxdur) — müəllifin «ev» üzvlüyü alt-ağacdadırsa: vahidli ƏSAS
      üzvlüyü varsa yalnız o sayılır; yoxdursa (əsas işarəsiz köhnə hesablar) hər aktiv üzvlüyü (köhnə qayda).
    """
    from django.db.models import Exists, OuterRef

    group_link = Exam.allowed_units.through.objects.filter(exam_id=OuterRef("pk"))
    own_link = (
        Q(subject__chair_unit__in=subtree_ids)
        | Q(course__unit__in=subtree_ids)
        | Exists(group_link.filter(orgunit_id__in=subtree_ids))
    )
    unlinked = (
        Q(subject__chair_unit__isnull=True)
        & (Q(course__isnull=True) | Q(course__unit__isnull=True))
        & ~Exists(group_link)
    )
    active = Membership.objects.filter(organization=org, is_active=True)
    with_unit_primary = active.filter(is_primary=True, scope_unit__isnull=False).values("user_id")
    home_authors = (
        active.filter(scope_unit__in=subtree_ids)
        .filter(Q(is_primary=True) | ~Q(user_id__in=with_unit_primary))
        .values("user_id")
    )
    return own_link | (unlinked & Q(author_id__in=home_authors))


def build_unit_exams_context(request, *, allowed_sections, active_section) -> dict:
    """Unit imtahanları bölməsi üçün ``context`` açarlarını qaytarır. Bölmə aktiv
    deyil / org yoxdur / istifadəçi unit-scoped deyilsə default dəyərlər (davranış
    köhnə inline blokla eyni)."""
    if not (active_section == "unit-exams" and "unit-exams" in allowed_sections):
        return _defaults()

    from apps.exams.models import Exam
    from apps.organizations.models import Membership, OrgUnit
    from apps.organizations.public import get_permission_scope

    org = _get_active_organization(request)
    if org is None:
        return _defaults()
    # Bölmə qapısı `is_unit_manager`-dir (dekan / dekan müavini / kafedra
    # müdiri — bax rbac_university_sections.py); əhatə isə `exam.view` açarını
    # DAŞIYAN üzvlüyün alt-ağacıdır (P1-11, 2026-09-12). Köhnə `get_unit_scope`
    # dekanın əlaqəsiz müəllim təyinatının kafedrasını da bura qatırdı; sərt
    # resolverdə `scope_unit`-siz dekan `EMPTY_SCOPE` alır → bölmə boş qalır.
    scope = get_permission_scope(request.user, org, "exam.view", request=request)
    if not scope.is_unit_scoped:
        return _defaults()

    unit_ids = OrgUnit.objects.filter(organization=org).filter(scope.unit_subtree_q())
    qs = (
        Exam.objects.filter(organization=org, is_deleted=False)
        .filter(_subtree_exam_q(Exam, Membership, org, unit_ids.values("pk")))
        .select_related("author", "course")
        .annotate(attempts_total=Count("attempts", distinct=True))
        .order_by("-created_at")
    )
    search_query = (request.GET.get("unit_exam_q") or "").strip()[:120]
    search_q = tolerant_q(search_query, ("title", "author__username", "course__title"))
    if search_q is not None:
        qs = qs.filter(search_q)
    return {
        "unit_exams_total_count": qs.count(),
        "unit_exams_page_obj": Paginator(qs, 10).get_page(request.GET.get("unit_exam_page")),
        "unit_exams_search_query": search_query,
        "unit_exams_pagination_query": _query_string(section="unit-exams", unit_exam_q=search_query),
    }

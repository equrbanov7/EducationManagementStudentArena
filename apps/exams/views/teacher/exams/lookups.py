"""teacher exams paketi — AJAX axtarış/lookup endpoint-ləri.

İmtahan yaratma sehrbazındakı axtarışlı select-lər (fənn, qrup, tələbə) və
"mövcud sual sayı" xəbərdarlığı üçün yüngül JSON endpoint-ləri. Hamısı
təşkilata görə scope olunur və müəllim icazəsi tələb edir.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.exams.models import Exam, StudentGroup
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._shared import _resolve_required_organization

User = get_user_model()

_PAGE_SIZE_DEFAULT = 10
_PAGE_SIZE_MAX = 50


def _page_bounds(request):
    """(offset, limit) — səhifələmə üçün. Default səhifə ölçüsü 10.

    Nəticələr `limit + 1` gətirilir ki, `has_more` təyin edilə bilsin (sonra
    limit-ə qədər kəsilir) — infinite scroll üçün.
    """
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", _PAGE_SIZE_DEFAULT))
    except (TypeError, ValueError):
        limit = _PAGE_SIZE_DEFAULT
    limit = max(1, min(limit, _PAGE_SIZE_MAX))
    return offset, limit


def _paginate(qs, offset, limit, serializer):
    window = list(qs[offset : offset + limit + 1])
    has_more = len(window) > limit
    return [serializer(obj) for obj in window[:limit]], has_more


@login_required
@require_GET
def subject_search(request):
    """Fənn (registrar.Subject) axtarışı — təşkilata görə, code/name üzrə."""
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False})

    from apps.registrar.models import Subject

    query = (request.GET.get("q") or "").strip()
    qs = Subject.objects.filter(organization=organization)
    if query:
        qs = qs.filter(Q(code__icontains=query) | Q(name__icontains=query))
    qs = qs.order_by("code")

    offset, limit = _page_bounds(request)
    results, has_more = _paginate(qs, offset, limit, lambda s: {"id": str(s.pk), "text": f"{s.code} — {s.name}"})
    return JsonResponse({"results": results, "has_more": has_more})


def _org_user_queryset(request, organization):
    """İmtahan formasındakı `allowed_users` queryset-i ilə eyni scope."""
    qs = User.objects.filter(is_active=True).exclude(id=request.user.id)
    if organization is not None:
        qs = qs.filter(profile__organization=organization)
    return qs.distinct()


@login_required
@require_GET
def group_search(request):
    """İcazəli qrup axtarışı — təşkilata görə, ad üzrə (səhifələnən)."""
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False})

    query = (request.GET.get("q") or "").strip()
    qs = StudentGroup.objects.filter(organization=organization)
    if query:
        qs = qs.filter(name__icontains=query)
    qs = qs.order_by("name")

    offset, limit = _page_bounds(request)
    results, has_more = _paginate(qs, offset, limit, lambda g: {"id": str(g.id), "text": str(g)})
    return JsonResponse({"results": results, "has_more": has_more})


@login_required
@require_GET
def user_search(request):
    """Fərdi icazəli tələbə axtarışı — təşkilata görə; ad/username/e-poçt üzrə (səhifələnən)."""
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False})

    query = (request.GET.get("q") or "").strip()
    qs = _org_user_queryset(request, organization)

    # Qrup(lar) seçilibsə: sağ siyahı yalnız həmin qrupların üzvlərini göstərir
    # (seçilən qrupun tələbələri). `groups` — vergüllə ayrılmış qrup ID-ləri.
    group_ids = [gid for gid in (request.GET.get("groups") or "").split(",") if gid.strip().isdigit()]
    if group_ids:
        qs = qs.filter(student_groups_as_student__id__in=[int(gid) for gid in group_ids])

    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    qs = qs.order_by("username").distinct()

    offset, limit = _page_bounds(request)
    results, has_more = _paginate(
        qs, offset, limit, lambda u: {"id": str(u.id), "text": u.get_full_name() or u.username}
    )
    return JsonResponse({"results": results, "has_more": has_more})


@login_required
@require_GET
def invigilator_search(request):
    """Nəzarətçi namizədləri axtarışı — imtahan mərkəzi RƏHBƏRİ üçün.

    Zala nəzarətçi təyin panelində istifadə olunur: təşkilatın tələbə OLMAYAN
    aktiv üzvləri (müəllim + mərkəz işçiləri) + hər birinin KAFEDRA/bölmə adı.
    Səhifələnən (lazy) — bütün istifadəçilər eyni anda yüklənmir (performans).
    """
    from apps.exams.services.access_policy import can_assign_invigilators
    from apps.exams.views.exam_center._shared import center_staff_queryset
    from apps.exams.views.shared.tenant import get_active_organization
    from apps.organizations.models import Membership

    if not can_assign_invigilators(request.user):
        return JsonResponse({"results": [], "has_more": False}, status=403)
    organization = get_active_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False})

    from django.db.models import OuterRef, Subquery

    # Hər istifadəçi üçün TƏK kafedra adı (aktiv üzvlükdə scope_unit) — dublikatsız.
    kafedra_sq = (
        Membership.objects.filter(
            user=OuterRef("pk"), organization=organization, is_active=True, scope_unit__isnull=False
        )
        .order_by("-role__level")
        .values("scope_unit__name")[:1]
    )
    qs = center_staff_queryset(organization).annotate(kafedra=Subquery(kafedra_sq))

    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )

    offset, limit = _page_bounds(request)
    results, has_more = _paginate(
        qs,
        offset,
        limit,
        lambda u: {
            "id": str(u.id),
            "text": (u.get_full_name() or u.username),
            "username": u.username,
            "kafedra": getattr(u, "kafedra", "") or "",
        },
    )
    return JsonResponse({"results": results, "has_more": has_more})


@login_required
@require_GET
def assigned_student_count(request):
    """Seçilmiş qrup(lar) + fərdi tələbələr üzrə FƏRQLİ (distinct) tələbə sayı.

    Yaratma təsdiqi modalı üçün: "qrupda tələbələrin sayı toplamı". Qrup üzvləri
    ilə fərdi seçilən tələbələr birləşdirilir və təkrarlar sayılmır.
    """
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"total": 0})

    group_ids = [int(g) for g in (request.GET.get("groups") or "").split(",") if g.strip().isdigit()]
    user_ids = [int(u) for u in (request.GET.get("users") or "").split(",") if u.strip().isdigit()]
    if not group_ids and not user_ids:
        return JsonResponse({"total": 0})

    cond = Q()
    if group_ids:
        cond |= Q(student_groups_as_student__id__in=group_ids)
    if user_ids:
        cond |= Q(id__in=user_ids)
    total = _org_user_queryset(request, organization).filter(cond).distinct().count()
    return JsonResponse({"total": total})


@login_required
@require_GET
def exam_available_question_count(request, slug):
    """Redaktə olunan imtahanda mövcud aktiv sual sayı (canlı xəbərdarlıq üçün)."""
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"count": 0})

    exam = tenant_scoped_exams(request, Exam.objects.filter(slug=slug)).first()
    if exam is None:
        return JsonResponse({"count": 0})

    from apps.exams.services.randomizer import available_question_count

    return JsonResponse({"count": available_question_count(exam)})

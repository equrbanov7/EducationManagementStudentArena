"""teacher exams paketi — AJAX axtarış/lookup endpoint-ləri.

İmtahan yaratma sehrbazındakı axtarışlı select-lər (fənn, qrup, tələbə) və
"mövcud sual sayı" xəbərdarlığı üçün yüngül JSON endpoint-ləri. Hamısı
təşkilata görə scope olunur və müəllim icazəsi tələb edir.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.exams.models import StudentGroup
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.lookup_search import legacy_group_lookup_q, subject_lookup_q, unit_lookup_q
from apps.exams.services.subject_labels import subject_option
from apps.organizations.public import organization_role_user_queryset
from core.roles import ProfileRole
from core.search_text import starts_with_q, tolerant_q, word_prefix_q

from . import unit_assignment as _units
from ._shared import _resolve_required_organization

User = get_user_model()

_PAGE_SIZE_DEFAULT = 10
_PAGE_SIZE_MAX = 50

#: SEC-2 Low #2 (2026-10-17): tələbə axtarışı istifadəçi kataloqunu sadalamasın. Sorğu bu uzunluqdan qısadırsa
#: yalnız SEÇİLMİŞ qrupların üzvləri qayıdır (istisna etmək üçün); qrup yoxdursa boş. JS (`EMSSearchInput`)
#: onsuz da ≥ 2 simvolda axtarır, ilk açılış isə boş sorğu ilə gəlir.
USER_SEARCH_MIN_QUERY = 2
#: Tələbə axtarışının səhifə həddi — klient 10-luq istəyir; böyük `limit` ilə toplu çəkiliş olmasın.
USER_SEARCH_PAGE_MAX = 20
#: Sürüşdürmənin (offset) yuxarı həddi — eyni sorğu ilə kataloqu səhifə-səhifə çəkmək olmasın; daha çoxu
#: üçün müəllim sorğunu dəqiqləşdirir (JS `has_more: false` görüb dayanır).
USER_SEARCH_MAX_OFFSET = 200


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
    """Fənn (registrar.Subject) axtarışı — təşkilata görə, ad/kod üzrə.

    2026-10-08 (müəllim rəyi Q1): ad SÖZ BAŞLANĞICI ilə axtarılır («vo» → «VoIP …»,
    amma «bihevorial»/«Devops» yox), az/ing hərfə dözümlü; adı sorğu ilə BAŞLAYANLAR
    birinci, sonra sözü sorğu ilə başlayanlar, sonra kod uyğunluqları. Etiket «Ad (KOD)».
    """
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False})

    from apps.registrar.models import Subject

    query = (request.GET.get("q") or "").strip()
    qs = ranked_subject_queryset(Subject.objects.filter(organization=organization), query)
    offset, limit = _page_bounds(request)
    results, has_more = _paginate(qs, offset, limit, subject_option)
    return JsonResponse({"results": results, "has_more": has_more})


def ranked_subject_queryset(qs, query):
    """Fənn axtarışı süzgəci + sıralaması (``subject_search`` və müəllimin fənləri üçün ORTAQ)."""
    name_q = word_prefix_q(query, ("name",))
    # 2026-10-21 (sahib: «aralı yazarkən də tapılsın»): tokenlər ad və kod arasında paylana bilər, söz sırası,
    # ayırıcı («/», «-»), bitişik «634Qrafik» fərq etmir; kod — ayırıcıya dözümlü alt-sətir («1203» → «QKU-1203»).
    lookup_q = subject_lookup_q(query)
    if lookup_q is None:
        return qs.order_by("name", "code")
    return (
        qs.filter(lookup_q)
        .annotate(
            search_rank=Case(
                When(starts_with_q(query, "name"), then=Value(0)),
                When(name_q, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("search_rank", "name", "code")
    )


@login_required
@require_GET
def bank_teacher_search(request):
    """Müəllim axtarışı (sual bankı atribusiyası) — təşkilatın müəllim-rol üzvləri.

    Bank yaratma kartındakı "sualı göndərən müəllim" axtarışlı seçicisi üçün:
    ad/soyad/istifadəçi adı üzrə, səhifələnən (lazy).
    """
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False})

    query = (request.GET.get("q") or "").strip()
    qs = organization_role_user_queryset(
        organization,
        {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER},
        queryset=User.objects.filter(is_active=True),
    )
    search_q = tolerant_q(query, ("username", "first_name", "last_name"))
    if search_q is not None:
        qs = qs.filter(search_q)
    qs = qs.distinct().order_by("first_name", "last_name", "username")

    offset, limit = _page_bounds(request)
    results, has_more = _paginate(
        qs, offset, limit, lambda u: {"id": str(u.id), "text": u.get_full_name() or u.username}
    )
    return JsonResponse({"results": results, "has_more": has_more})


def _org_user_queryset(request, organization):
    """İmtahan formasındakı `allowed_users` queryset-i ilə eyni scope."""
    qs = User.objects.filter(is_active=True).exclude(id=request.user.id)
    if organization is not None:
        qs = organization_role_user_queryset(
            organization,
            {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT},
            queryset=qs,
        )
    return qs.distinct()


def _unit_ids_param(request, name="units"):
    """`?units=<uuid>,<uuid>` → yalnız etibarlı UUID-lər (siyahı)."""
    from uuid import UUID

    ids = []
    for piece in (request.GET.get(name) or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            ids.append(str(UUID(piece)))
        except (TypeError, ValueError):
            continue
    return ids


def _uuid_param(request, name):
    from uuid import UUID

    try:
        return str(UUID((request.GET.get(name) or "").strip()))
    except ValueError:
        return ""


def _unit_member_ids(request, organization, unit_ids, *, subject_id=""):
    """Seçilmiş reyestr qruplarının cari tələbə id-ləri (əhatə ilə skoplanmış) + fənn seçilibsə həmin fənnin bu
    qruplardakı CARİ jurnal tələbələri (giriş siyasəti ilə eyni: ``unit_assignment.journal_student_ids``)."""
    if not unit_ids:
        return set()
    from apps.exams.domain.unit_assignment import journal_student_ids, unit_student_record_filter
    from apps.registrar.public import subgroup_rollup

    units = list(_units.exam_unit_candidates(request, organization).filter(pk__in=unit_ids))
    # SAHİB (2026-09-21): ana qrup seçiləndə alt qrupların (234 K-1/-2) tələbələri də
    # «qrupla daxildir» kimi işarələnir.
    group_ids = {unit.pk for unit in units} | {u.pk for u in subgroup_rollup.subgroup_units(organization, units)}
    record_path = "academic_records__"
    registry = set(
        User.objects.filter(
            **{f"{record_path}group__in": list(group_ids)},
            **unit_student_record_filter(record_path),
        ).values_list("id", flat=True)
    )
    return registry | journal_student_ids(subject_id, [unit.pk for unit in units])


@login_required
@require_GET
def group_search(request):
    """İcazəli qrup axtarışı — təşkilata görə, ad üzrə (səhifələnən).

    2026-09-14 (W4 `w4wizard`, R2): `?kind=units` → qrup REYESTRİ (OrgUnit GROUP)
    namizədləri (təşkilat + istifadəçinin `exam.create` əhatəsi); parametrsiz →
    köhnə imtahan kohortları (`StudentGroup`, ikinci dərəcəli bölmə).
    """
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False})

    query = (request.GET.get("q") or "").strip()[:120]
    if (request.GET.get("kind") or "").strip() == "units":
        from apps.registrar.public import subgroup_rollup

        unit_qs = _units.exam_unit_candidates(request, organization)
        # «234king»/«234k ing» → «234 K ing», «233KE» → «233 KE»: ayırıcıya/diakritikaya dözümlü
        # (sahib 2026-09-21, 2026-09-26).
        # 2026-10-21: ixtisas (ana qrup) adı da — etiket «634 ing — Dizayn (Qrafik)»; «qrafik 634», «634Qrafik».
        unit_q = unit_lookup_q(query)
        if unit_q is not None:
            unit_qs = unit_qs.filter(unit_q)
        offset, limit = _page_bounds(request)
        page_units = list(unit_qs[offset : offset + limit + 1])
        has_more = len(page_units) > limit
        page_units = page_units[:limit]
        sub_map = subgroup_rollup.subgroup_map(organization, page_units)
        results = [
            {
                "id": str(u.pk),
                "text": _units.unit_display_label(u),
                # Ana qrupun alt qrupları — seçəndə avtomatik seçilir (klient).
                "subgroups": [
                    {"id": str(sub.pk), "text": _units.unit_display_label(sub)} for sub in sub_map.get(u.pk, [])
                ],
            }
            for u in page_units
        ]
        return JsonResponse({"results": results, "has_more": has_more})

    qs = StudentGroup.objects.filter(organization=organization)
    group_q = legacy_group_lookup_q(query)
    if group_q is not None:
        qs = qs.filter(group_q)
    qs = qs.order_by("name")

    offset, limit = _page_bounds(request)
    results, has_more = _paginate(qs, offset, limit, lambda g: {"id": str(g.id), "text": str(g)})
    return JsonResponse({"results": results, "has_more": has_more})


def _student_label(user, group_name: str = "") -> str:
    """«Ad Soyad Ata adı · qrup» — eyni adlı tələbələri ayırmaq üçün (sahib 2026-10-26)."""
    profile = getattr(user, "profile", None)
    name = (getattr(profile, "full_name_with_patronymic", "") if profile is not None else "") or user.get_full_name()
    name = name or user.username
    return f"{name} · {group_name}" if group_name else name


@login_required
@require_GET
def user_search(request):
    """Fərdi icazəli tələbə axtarışı — təşkilata görə; ad/username/e-poçt üzrə (səhifələnən)."""
    _ensure_teacher(request.user)
    organization = _resolve_required_organization(request)
    if organization is None:
        return JsonResponse({"results": [], "has_more": False})

    query = (request.GET.get("q") or "").strip()[:120]
    qs = _org_user_queryset(request, organization)

    # `groups` seçili qrupları bildirir. Həmin qrupların üzvləri metadata ilə işarələnir ki, frontend
    # onları checked göstərib ayrı-ayrı istisna etməyə imkan versin. Axtarış (≥ 2 simvol) bütün
    # təşkilat tələbələrini gəzir; qısa/boş sorğuda yalnız üzvlər qayıdır (SEC-2 Low #2).
    group_ids = [gid for gid in (request.GET.get("groups") or "").split(",") if gid.strip().isdigit()]
    group_member_ids = set()
    if group_ids:
        group_member_ids = set(
            StudentGroup.objects.filter(organization=organization, id__in=[int(gid) for gid in group_ids])
            .values_list("students__id", flat=True)
            .distinct()
        )
    # R2: seçilmiş reyestr qruplarının (`units`) tələbələri də «qrupla daxildir»
    # kimi işarələnir — müəllim onları ayrı-ayrı istisna edə bilsin.
    group_member_ids |= _unit_member_ids(
        request, organization, _unit_ids_param(request), subject_id=_uuid_param(request, "subject")
    )

    if len(query) < USER_SEARCH_MIN_QUERY:
        # Qısa/boş sorğu: kataloq YOX — yalnız seçilmiş qrupların üzvləri (yoxdursa boş siyahı).
        if not group_member_ids:
            return JsonResponse({"results": [], "has_more": False, "min_query": USER_SEARCH_MIN_QUERY})
        qs = qs.filter(id__in=group_member_ids)
    else:
        # Sahib 2026-10-26: eyni adlı tələbələr (3 × «Aynur Məmmədova») — ata adı ilə də axtarılır.
        search_q = tolerant_q(query, ("username", "first_name", "last_name", "email", "profile__patronymic"))
        if search_q is not None:
            qs = qs.filter(search_q)
    qs = qs.select_related("profile").distinct()
    if group_member_ids:
        qs = qs.annotate(
            group_member_rank=Case(
                When(id__in=group_member_ids, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("group_member_rank", "username")
    else:
        qs = qs.order_by("username")

    offset, limit = _page_bounds(request)
    if offset >= USER_SEARCH_MAX_OFFSET:
        return JsonResponse({"results": [], "has_more": False, "min_query": USER_SEARCH_MIN_QUERY})
    limit = min(limit, USER_SEARCH_PAGE_MAX, USER_SEARCH_MAX_OFFSET - offset)
    window = list(qs[offset : offset + limit + 1])
    has_more = len(window) > limit
    window = window[:limit]
    from apps.registrar.public import student_group_names

    groups = student_group_names.current_group_names(u.id for u in window)
    results = [
        {"id": str(u.id), "text": _student_label(u, groups.get(u.id, "")), "group_member": u.id in group_member_ids}
        for u in window
    ]
    has_more = has_more and offset + len(results) < USER_SEARCH_MAX_OFFSET
    return JsonResponse({"results": results, "has_more": has_more, "min_query": USER_SEARCH_MIN_QUERY})


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
    search_q = tolerant_q(query, ("username", "first_name", "last_name", "email"))
    if search_q is not None:
        qs = qs.filter(search_q)

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
    unit_ids = _unit_ids_param(request)
    user_ids = [int(u) for u in (request.GET.get("users") or "").split(",") if u.strip().isdigit()]
    excluded_user_ids = [int(u) for u in (request.GET.get("excluded") or "").split(",") if u.strip().isdigit()]
    if not group_ids and not unit_ids and not user_ids:
        return JsonResponse({"total": 0})

    cond = Q()
    if group_ids:
        cond |= Q(student_groups_as_student__id__in=group_ids)
    if unit_ids:
        # R2: reyestr qrupu tələbələri — `unit_assigned_exams_q` ilə eyni şərt.
        from apps.exams.domain.unit_assignment import unit_student_record_filter

        record_path = "academic_records__"
        cond |= Q(
            **{f"{record_path}group__in": _units.exam_unit_candidates(request, organization).filter(pk__in=unit_ids)},
            **unit_student_record_filter(record_path),
        )
    if user_ids:
        cond |= Q(id__in=user_ids)
    qs = _org_user_queryset(request, organization).filter(cond)
    if excluded_user_ids:
        qs = qs.exclude(id__in=excluded_user_ids)
    total = qs.distinct().count()
    return JsonResponse({"total": total})

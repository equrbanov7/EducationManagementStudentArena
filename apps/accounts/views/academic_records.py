"""Staff hierarchical academic-records ("Akademik qeydlər") — AJAX endpoints.

İyerarxik akademik-qeyd profil bölməsinin məlumat + axtarış endpoint-ləri:
filtr üzrə xülasə box-ları + səhifələnmiş tələbə siyahısı, bir tələbənin semestr-
üzrə detalı və fakültə → kafedra → ixtisas → qrup → tələbə axtarışlı seçiciləri.

Bu qat qəsdən **accounts** app-indədir (registrar-da yox): registrar-organizations
arasında modul-sərhəd dövrü yaratmamaq üçün — cross-domain glue (akademik nəticə +
təşkilat strukturu) hər ikisini import edən inteqrasiya qatına məxsusdur. Hər şey
aktiv təşkilata + istifadəçinin unit scope-una görə mühafizə olunur
(:mod:`apps.organizations.scoping`) — istifadəçi yalnız özündən aşağı səviyyəni görür.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.accounts import academic_records
from apps.organizations.models import OrgUnit
from apps.organizations.scoping import ORG_WIDE_SCOPE, get_unit_scope, scope_org_units
from apps.registrar import transcript
from apps.registrar.models import Program, StudentAcademicRecord
from core.roles import user_has_any_role

_FILTER_KEYS = ("faculty", "department", "program", "group", "student", "year", "season")
_PAGE_DEFAULT = 10
_PAGE_MAX = 50

# İmtahan mərkəzi + İKT rəhbəri MƏRKƏZİ rollardır — unit scope-ları olmasa da bütün
# təşkilat üzrə akademik nəticələri görməlidirlər (mərkəzi imtahan/idarəetmə nəzarəti).
# Dekan/kafedra müdiri unit-scope ilə qalır; adi müəllim/tələbə giriş almır.
_CENTRAL_ROLES = frozenset({"exam_center", "exam_center_head", "exam_center_staff", "ikt_rehber"})

#: Unit-scope ilə akademik qeydlərə baxa bilən İDARƏETMƏ rolları.
_UNIT_MANAGER_ROLES = frozenset({"dean", "vice_dean", "department_head"})

#: Org-səviyyə idarəetmə.
_ORG_ADMIN_ROLES = frozenset({"org_admin", "org_owner"})

#: Bu endpoint-lərə giriş hüququ olan bütün rollar.
#:
#: TƏHLÜKƏSİZLİK (2026-07-31 auditi): əvvəllər burada rol qapısı ÜMUMİYYƏTLƏ yox
#: idi — endpoint-lər yalnız ``scope.has_structure_access`` yoxlayırdı.
#: ``_resolve_unit_scope`` isə rolun adına/səviyyəsinə baxmadan HƏR üzvlüyün
#: ``scope_unit_id``-sini scope-a əlavə edir, «Müəllimi kafedraya təyin et»
#: əməliyyatı isə məhz onu doldurur. Nəticədə adi müəllim öz kafedra
#: alt-ağacındakı BÜTÜN tələbələrin GPA, semestr detalı və transkriptini oxuya
#: bilirdi. Sidebar ona ``academic-records`` bölməsini vermirdi — yəni endpoint
#: UI-dan geniş idi (gizli PII sızması). Siyahı sidebar qapısı ilə eyni
#: saxlanılır (``views/_helpers/rbac.py``: is_superadmin / is_org_admin /
#: is_unit_manager / is_exam_center).
ACADEMIC_RECORDS_ROLES = _CENTRAL_ROLES | _UNIT_MANAGER_ROLES | _ORG_ADMIN_ROLES


# ── Ortaq köməkçilər ─────────────────────────────────────────────────────────


def can_view_academic_records(user, organization) -> bool:
    """Akademik qeyd endpoint-lərinə rol qapısı (scope-dan ƏVVƏL).

    Scope «nəyi görürsən» sualına cavab verir, «görməyə haqqın varmı» sualına
    yox. Qapı fail-closed-dur: rol tanınmırsa giriş yoxdur.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    if organization is not None and getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    return user_has_any_role(user, ACADEMIC_RECORDS_ROLES)


def _scope(request):
    """(organization, scope) — aktiv təşkilat + istifadəçinin görünüş sahəsi.

    Superadmin/owner/rektorat org-wide, dekan/kafedra müdiri unit-subtree
    (:func:`get_unit_scope`). Mərkəzi rollar (imtahan mərkəzi / İKT rəhbəri) unit
    scope-ları olmadığından org-wide-a yüksəldilir — beləcə bütün tələbələri görürlər.

    Rol qapısından keçməyən istifadəçi üçün ``(None, None)`` qaytarılır: bütün
    çağıran endpoint-lər ``organization is None`` şərtini yoxlayır, yəni cavab
    ``has_access: False`` olur.
    """
    organization = getattr(request, "organization", None)
    if organization is None:
        return None, None
    if not can_view_academic_records(request.user, organization):
        return None, None
    scope = get_unit_scope(request.user, organization, request=request)
    if not scope.has_structure_access and user_has_any_role(request.user, _CENTRAL_ROLES):
        scope = ORG_WIDE_SCOPE
    return organization, scope


def _int_param(request, name, default):
    try:
        return int(request.GET.get(name, default))
    except (TypeError, ValueError):
        return default


def _bounds(request):
    offset = max(0, _int_param(request, "offset", 0))
    limit = max(1, min(_int_param(request, "limit", _PAGE_DEFAULT), _PAGE_MAX))
    return offset, limit


def _page(qs, request, serializer):
    offset, limit = _bounds(request)
    window = list(qs[offset : offset + limit + 1])
    return JsonResponse({"results": [serializer(o) for o in window[:limit]], "has_more": len(window) > limit})


def _num(value):
    if value is None:
        return None
    # 2 onluğa qədər, sondakı sıfırlar atılmış (məs. 8.00 → "8", 7.50 → "7.5").
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


# ── Data endpoint-ləri ───────────────────────────────────────────────────────


def _filters(request) -> dict:
    return {key: (request.GET.get(key) or "").strip() or None for key in _FILTER_KEYS}


@login_required
@require_GET
def records_overview_data(request):
    """Səhifələnmiş tələbə siyahısı (filtr + scope üzrə) — box-lar OLMADAN.

    Box-lar qəsdən ayrılıb (:func:`records_overview_summary`): onlar bütün süzgəc
    sahəsi üzrə aqreqatdır və səhifədən-səhifəyə dəyişmir, cədvəl isə yalnız
    görünən ~25 tələbəni tələb edir. Ayırmasaq, cədvəl hər dəfə box-ların tam
    keçidini gözləyirdi (5 000+ tələbəlik təşkilatda onlarla saniyə).
    """
    organization, scope = _scope(request)
    if organization is None or scope is None or not scope.has_structure_access:
        return JsonResponse({"has_access": False, "results": [], "has_more": False, "total": 0})

    payload = academic_records.build_records_page(
        organization=organization,
        scope=scope,
        filters=_filters(request),
        offset=_int_param(request, "offset", 0),
        limit=_int_param(request, "limit", academic_records.DEFAULT_PAGE_SIZE),
        sort=(request.GET.get("sort") or "").strip() or None,
    )
    return JsonResponse(payload)


@login_required
@require_GET
def records_overview_summary(request):
    """Xülasə box-ları + tədris ili seçimləri — cədvəldən AYRICA, gecikmiş sorğu."""
    organization, scope = _scope(request)
    if organization is None or scope is None or not scope.has_structure_access:
        return JsonResponse({"has_access": False, "summary": None, "year_options": []})

    payload = academic_records.build_records_summary(organization=organization, scope=scope, filters=_filters(request))
    return JsonResponse(payload)


def _serialize_semester(sem) -> dict:
    rows = []
    for row in sem["rows"]:
        result = row["result"]
        rows.append(
            {
                "code": row["subject"].code,
                "name": row["subject"].name,
                "credit": row["credit"],
                "teacher": row["teacher_name"] or "—",
                "entry": _num(result.get("entry_score")),
                "exit": _num(result.get("effective_exam")) if result.get("graded") else None,
                "total": _num(result.get("total")) if (result.get("passed") or result.get("failed")) else None,
                "letter": result.get("letter") if row["in_gpa"] else None,
                "passed": bool(result.get("passed")),
                "failed": bool(result.get("failed")),
                "barred": bool(result.get("barred")),
                # Nə keçib, nə kəsilib → «qiymətləndirilməyib» (imtahan çıxış
                # balı yoxdur).  Sətir başqa cür görünməz qalırdı.
                "ungraded": not (result.get("passed") or result.get("failed")),
                "fail_reason": row["fail_reason"],
            }
        )
    return {
        "year": sem["period"].year_display,
        "season": sem["season"],
        "credits_earned": sem["credits_earned"],
        "gpa": str(sem["gpa"]) if sem.get("gpa") is not None else None,
        "rows": rows,
    }


@login_required
@require_GET
def records_student_detail(request):
    """Bir tələbənin semestr-üzrə fənn detalı (yalnız scope daxilində)."""
    organization, scope = _scope(request)
    student_id = (request.GET.get("student") or "").strip()
    if organization is None or scope is None or not student_id:
        return JsonResponse({"has_access": False, "semesters": []})
    if not academic_records.student_is_in_scope(organization=organization, scope=scope, student_id=student_id):
        return JsonResponse({"has_access": False, "semesters": []})

    student = get_user_model().objects.filter(pk=student_id).first()
    if student is None:
        return JsonResponse({"has_access": False, "semesters": []})

    data = transcript.build_student_overall_record(student=student, organization=organization)
    student_name = (student.get_full_name() or "").strip() or student.username
    if not data["has_record"]:
        return JsonResponse({"has_access": True, "student_name": student_name, "semesters": []})
    return JsonResponse(
        {
            "has_access": True,
            "student_name": student_name,
            "semesters": [_serialize_semester(sem) for sem in data["semesters"]],
        }
    )


# ── Axtarışlı seçici (lookup) endpoint-ləri ──────────────────────────────────


def _subtree_filter(organization, unit_id, path_field):
    """Verilmiş OrgUnit-in alt-ağacı üçün Q (özü + törəmələri). Tapılmasa None."""
    unit = OrgUnit.objects.filter(organization=organization, pk=unit_id).only("id", "path").first()
    if unit is None:
        return None
    id_field = path_field.replace("__path", "_id") if path_field.endswith("__path") else "id"
    if unit.path:
        return Q(**{id_field: unit.id}) | Q(**{f"{path_field}__startswith": f"{unit.path}/"})
    return Q(**{id_field: unit.id})


@login_required
@require_GET
def faculty_search(request):
    """Fakültə/dekanlıq axtarışı — istifadəçinin scope alt-ağacı daxilində."""
    organization, scope = _scope(request)
    if organization is None or not scope.has_structure_access:
        return JsonResponse({"results": [], "has_more": False})
    qs = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=("faculty", "deanery"))
    qs = scope_org_units(qs, scope)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(name__icontains=query)
    return _page(qs.order_by("name"), request, lambda u: {"id": str(u.id), "text": u.name})


@login_required
@require_GET
def department_search(request):
    """Kafedra/bölmə axtarışı — `?faculty=` verilibsə həmin fakültəyə görə."""
    organization, scope = _scope(request)
    if organization is None or not scope.has_structure_access:
        return JsonResponse({"results": [], "has_more": False})
    qs = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=("chair", "department"))
    qs = scope_org_units(qs, scope)
    faculty = (request.GET.get("faculty") or "").strip()
    if faculty:
        qs = qs.filter(parent_id=faculty)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(name__icontains=query)
    return _page(qs.order_by("name"), request, lambda u: {"id": str(u.id), "text": u.name})


@login_required
@require_GET
def program_search(request):
    """İxtisas (Program) axtarışı — `?department=` verilibsə həmin kafedraya görə."""
    organization, scope = _scope(request)
    if organization is None or not scope.has_structure_access:
        return JsonResponse({"results": [], "has_more": False})
    qs = Program.objects.filter(organization=organization, is_active=True)
    qs = qs.filter(scope.unit_subtree_q(path_field="specialty_unit__path", id_field="specialty_unit_id"))
    department = (request.GET.get("department") or "").strip()
    if department:
        qs = qs.filter(specialty_unit__parent_id=department)
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query))
    return _page(qs.order_by("name"), request, lambda p: {"id": str(p.id), "text": f"{p.code} — {p.name}"})


@login_required
@require_GET
def group_search(request):
    """Qrup axtarışı — `?specialty=`/`?department=`/`?faculty=` üzrə daralır."""
    organization, scope = _scope(request)
    if organization is None or not scope.has_structure_access:
        return JsonResponse({"results": [], "has_more": False})
    qs = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type="group")
    qs = scope_org_units(qs, scope)
    for param in ("specialty", "department", "faculty"):
        value = (request.GET.get(param) or "").strip()
        if value:
            sub = _subtree_filter(organization, value, "path")
            qs = qs.filter(sub) if sub is not None else qs.none()
            break
    query = (request.GET.get("q") or "").strip()
    if query:
        qs = qs.filter(name__icontains=query)
    return _page(qs.order_by("name"), request, lambda u: {"id": str(u.id), "text": u.name})


@login_required
@require_GET
def student_search(request):
    """Tələbə axtarışı — scope + aktiv filtrlər daxilində, ad/istifadəçi adı üzrə."""
    organization, scope = _scope(request)
    if organization is None or not scope.has_structure_access:
        return JsonResponse({"results": [], "has_more": False})
    records = StudentAcademicRecord.objects.filter(organization=organization, is_active=True).select_related("student")
    records = records.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    group = (request.GET.get("group") or "").strip()
    if group:
        records = records.filter(group_id=group)
    program = (request.GET.get("program") or "").strip()
    if program:
        records = records.filter(program_id=program)
    query = (request.GET.get("q") or "").strip()
    if query:
        records = records.filter(
            Q(student__first_name__icontains=query)
            | Q(student__last_name__icontains=query)
            | Q(student__username__icontains=query)
        )
    records = records.order_by("student__last_name", "student__first_name", "student__username")

    offset, limit = _bounds(request)
    seen, results = set(), []
    for record in records[offset : offset + limit * 3 + 1]:
        sid = str(record.student_id)
        if sid in seen:
            continue
        seen.add(sid)
        student = record.student
        results.append({"id": sid, "text": (student.get_full_name() or "").strip() or student.username})
        if len(results) > limit:
            break
    return JsonResponse({"results": results[:limit], "has_more": len(results) > limit})


@login_required
@require_GET
def journal_teacher_search(request):
    """Müəllim axtarışı — təşkilatın dərs açılışlarının (offering) müəllimləri, scope
    daxilində. Elektron jurnal siyahısının müəllim filtri üçün (İKT rəhbəri/admin)."""
    organization, scope = _scope(request)
    if organization is None or not scope.has_structure_access:
        return JsonResponse({"results": [], "has_more": False})

    from apps.registrar.models import CourseOffering

    offerings = CourseOffering.objects.filter(organization=organization, is_active=True, instructor__isnull=False)
    # Unit-scoped istifadəçi yalnız öz alt-ağacındakı qrupların offering-lərinin
    # müəllimlərini görür; org-wide hamısını.
    if not scope.is_org_wide:
        offerings = offerings.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    teacher_ids = list(offerings.values_list("instructor_id", flat=True).distinct())
    if not teacher_ids:
        return JsonResponse({"results": [], "has_more": False})

    users = get_user_model().objects.filter(pk__in=teacher_ids)
    query = (request.GET.get("q") or "").strip()
    if query:
        users = users.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(username__icontains=query)
        )
    users = users.order_by("last_name", "first_name", "username")
    return _page(
        users,
        request,
        lambda u: {"id": str(u.id), "text": (u.get_full_name() or "").strip() or u.username},
    )

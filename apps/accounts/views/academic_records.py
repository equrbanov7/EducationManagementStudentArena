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
from apps.organizations.public import get_permission_scope, scope_org_units
from apps.registrar.models import Program, StudentAcademicRecord
from apps.registrar.public import transcript
from core.http_ids import parse_uuid
from core.program_codes import PROGRAM_CODE_SEARCH_FIELDS
from core.search_text import tolerant_q

_FILTER_KEYS = ("faculty", "department", "program", "group", "student", "year", "season")
_PAGE_DEFAULT = 10
_PAGE_MAX = 50

#: Bölmənin VƏ bütün endpoint-lərin TƏK qapısı + əhatə mənbəyi.
#:
#: 2026-10-13 (rol auditi B2, sahib: «hər rol öz səlahiyyəti qədər»): əvvəl qapı rol ADI ilə idi
#: (``ACADEMIC_RECORDS_ROLES`` = imtahan mərkəzi / İKT / dekan / kafedra müdiri / org admin), əhatə
#: ``grade.view``-dan gəlirdi, mərkəzi rollar isə açarsız ``ORG_WIDE_SCOPE``-a yüksəldilirdi
#: (``_CENTRAL_ROLES``). Nəticədə icazə redaktorunda ``grade.view`` almaq heç nəyi bağlamır, vermək heç
#: nəyi açmırdı. İndi menyu (``rbac_sections``) və data EYNİ açardan: ORGANIZATION rolu → bütün
#: təşkilat, UNIT rolu → ``scope_unit`` alt-ağacı, açarsız / ``scope_unit``-siz → giriş yoxdur
#: (fail-closed). ``grade.view`` seçilmədi: o, müəllimdə/laborantda da var — GPA reyestri onlara açılardı.
#: Açarı bu gün bölməni görən hər rol miqrasiya ``organizations/0061`` ilə alıb.
#: (Kataloq sabiti: ``organizations.permissions_role_audit.PERM_STUDENT_RECORDS_VIEW``.)
RECORDS_SCOPE_PERMISSION = "student.records_view"


# ── Ortaq köməkçilər ─────────────────────────────────────────────────────────


def records_scope(user, organization, *, request=None):
    """``student.records_view`` struktur əhatəsi (superadmin / təşkilat sahibi → org-wide)."""
    return get_permission_scope(user, organization, RECORDS_SCOPE_PERMISSION, request=request)


def can_view_academic_records(user, organization, *, request=None) -> bool:
    """Akademik qeydlərə giriş — açar struktur əhatəsi verirsə (menyu ilə eyni qayda)."""
    if user is None or not getattr(user, "is_authenticated", False) or organization is None:
        return False
    return records_scope(user, organization, request=request).has_structure_access


def _scope(request):
    """(organization, scope) — aktiv təşkilat + istifadəçinin görünüş sahəsi.

    Əhatə YALNIZ ``get_permission_scope(…, "student.records_view")``-dandır (B2, 2026-10-13): rol adına
    görə yüksəltmə yoxdur. Açarı ümumiyyətlə daşımayan aktor ``(None, None)`` alır (qapı əhatədən ƏVVƏL);
    açarı olan, amma ``scope_unit``-siz UNIT rolu BOŞ əhatə alır — hər endpoint ``scope.has_structure_access``
    yoxlayır → ``has_access: False``. 2026-09-12 (P1-11) qaydası qalır: sərt resolver yalnız açarı
    daşıyan üzvlüyün unitini sayır — dekanın başqa fakültədəki müəllim üzvlüyü əhatəyə düşmür.
    """
    organization = getattr(request, "organization", None)
    if organization is None:
        return None, None
    scope = records_scope(request.user, organization, request=request)
    if not scope.has_structure_access and not _holds_records_key(request.user, organization):
        return None, None
    return organization, scope


def _holds_records_key(user, organization) -> bool:
    """Aktorun aktiv üzvlüklərindən biri açarı (və ya onun wildcard-ını) daşıyırmı (memoizasiyalı)."""
    from core.permissions import has_permission

    from ._helpers.rbac import _collect_actor_permissions

    permissions, _grantable = _collect_actor_permissions(user, organization)
    return has_permission(list(permissions), RECORDS_SCOPE_PERMISSION)


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

    offset = _int_param(request, "offset", 0)
    payload = academic_records.build_records_page(
        organization=organization,
        scope=scope,
        filters=_filters(request),
        offset=offset,
        limit=_int_param(request, "limit", academic_records.DEFAULT_PAGE_SIZE),
        sort=(request.GET.get("sort") or "").strip() or None,
        # Yekun say YALNIZ ilk səhifədə hesablanır: süzgəc dəyişməyibsə rəqəm də
        # dəyişmir və UI onu saxlayır. Beləcə səhifə çevrilişində
        # ``COUNT(DISTINCT student_id)`` ümumiyyətlə getmir (bax academic_records).
        with_total=offset <= 0,
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
                # Şəffaflıq: status canlı qaydadan gəlir, yoxsa köhnə sistemdən
                # (və ya köhnə sistemin BOŞLUĞUNDAN) — bax exam_eligibility.
                "status_code": result.get("status_code") or "",
                "status_label": str(result["status_label"]) if result.get("status_label") else "",
                "status_notice": str(result["status_notice"]) if result.get("status_notice") else "",
                # JSON drill-down da server-render olunmuş transkript səthləri
                # ilə eyni legacy mənşə müqaviləsini daşımalıdır. Əks halda JS
                # ``row.legacy`` oxusa da marker səssizcə itirdi.
                "legacy": row.get("legacy"),
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
    if organization is None or scope is None or not scope.has_structure_access or not student_id:
        return JsonResponse({"has_access": False, "semesters": []})

    # Mühafizə + tələbə obyekti BİR sorğuda (əvvəl ``EXISTS`` + ayrıca ``User``
    # oxuması idi) — scope xaricindəki tələbə üçün nəticə eynidir: ``None``.
    student = academic_records.student_in_scope(organization=organization, scope=scope, student_id=student_id)
    if student is None:
        return JsonResponse({"has_access": False, "semesters": []})

    data = transcript.build_student_overall_record(student=student, organization=organization)
    student_name = (student.get_full_name() or "").strip() or student.username
    # 2026-10-13 (gecə): imtahan cəhdləri + apellyasiya izi (sahibin 2026-09-07 memo-su — koordinator/dekanlıq
    # görməlidir). YALNIZ-OXU; scope yuxarıdakı ``student_in_scope`` ilə artıq yoxlanıb.
    from apps.appeals.public import student_exam_history

    exam_history = student_exam_history(student=student, organization=organization)
    if not data["has_record"]:
        return JsonResponse(
            {"has_access": True, "student_name": student_name, "semesters": [], "exam_history": exam_history}
        )
    return JsonResponse(
        {
            "has_access": True,
            "student_name": student_name,
            "semesters": [_serialize_semester(sem) for sem in data["semesters"]],
            "exam_history": exam_history,
        }
    )


# ── Axtarışlı seçici (lookup) endpoint-ləri ──────────────────────────────────


def _search(queryset, request, fields, *, compact_fields=()):
    """``?q=`` süzgəci — tokenləşmiş, az/ing dözümlü (``core.search_text``); boş sorğu → süzgəc yoxdur."""
    search = tolerant_q(request.GET.get("q") or "", fields, compact_fields=compact_fields)
    return queryset.filter(search) if search is not None else queryset


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
    qs = _search(qs, request, ("name",))
    return _page(qs.order_by("name"), request, lambda u: {"id": str(u.id), "text": u.name})


@login_required
@require_GET
def department_search(request):
    """Kafedra/bölmə axtarışı — `?faculty=` verilibsə həmin fakültənin ALT-AĞACINDA.

    2026-10-24: əvvəl ``parent_id=faculty`` (yalnız birbaşa uşaq) idi — fakültə ilə kafedra
    arasında ara səviyyə olanda seçici boş qalırdı; pozuq id isə 500 verirdi."""
    organization, scope = _scope(request)
    if organization is None or not scope.has_structure_access:
        return JsonResponse({"results": [], "has_more": False})
    qs = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=("chair", "department"))
    qs = scope_org_units(qs, scope)
    faculty = parse_uuid(request.GET.get("faculty"))
    if faculty is not None:
        sub = _subtree_filter(organization, faculty, "path")
        qs = qs.filter(sub) if sub is not None else qs.none()
    elif (request.GET.get("faculty") or "").strip():
        qs = qs.none()
    qs = _search(qs, request, ("name",))
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
    # AXTARIŞ İNVARİANTI: seçicidə ``display_label`` göstərilir, o isə cari
    # şifr yoxdursa KÖHNƏ şifrə geri çəkilir. Ona görə axtarış HƏR İKİ nəsil
    # şifri əhatə etməlidir — əks halda istifadəçi ekranda gördüyü şifri
    # (məs. «050401») yazanda sıfır nəticə alırdı.
    qs = _search(qs, request, ("name",), compact_fields=PROGRAM_CODE_SEARCH_FIELDS)
    # Seçicidə YALNIZ rəsmi dövlət ixtisas kodu görünür (``display_label``);
    # daxili ``Program.code`` (``MYEDU-*``) nə axtarılır, nə göstərilir.
    return _page(qs.order_by("name"), request, lambda p: {"id": str(p.id), "text": p.display_label})


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
    # Qrup adı kod kimidir: «234king», «234k ing» → «234 K ing».
    qs = _search(qs, request, (), compact_fields=("name",))
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
    records = _search(records, request, ("student__first_name", "student__last_name", "student__username"))
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
    users = _search(users, request, ("first_name", "last_name", "username"))
    users = users.order_by("last_name", "first_name", "username")
    return _page(
        users,
        request,
        lambda u: {"id": str(u.id), "text": (u.get_full_name() or "").strip() or u.username},
    )

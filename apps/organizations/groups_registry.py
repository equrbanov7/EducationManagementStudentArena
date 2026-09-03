"""Ekran 06 «Qruplar» — AKADEMİK qrup reyestri (OXU tərəfi).

⚠️ TƏLƏ — İKİ FƏRQLİ «QRUP» ANLAYIŞI VAR, QARIŞDIRILMAMALIDIR:

  * **akademik qrup** = ``OrgUnit(unit_type="group")`` — tələbənin təhsil aldığı
    real qrup (İTM-24A). BU EKRAN ONUNDUR;
  * **imtahan kohortu** = ``apps.exams.StudentGroup`` — müəllimin imtahana
    dəvət etdiyi ad-hoc siyahı; kabinetdəki mövcud «Qruplar» bölməsi (`groups`)
    ONUNDUR və TOXUNULMUR. İki səth bir-birinə çarpaz keçid verir.

Qrupun metadatası (dil sektoru, kurs, qəbul ili, tədris planı) ``OrgUnit.settings``
JSON-undadır — YENİ CƏDVƏL YARADILMIR. Səbəb: akademik struktur universitetdən
universitetə dəyişir (dil sektoru bəzi tenantlarda yoxdur), ona görə sxem
sabitlənmir; oxu burada NORMALLAŞDIRILIR ki, şablon xam JSON görməsin.

ƏHATƏ (handoff §8/8 — «əhatə yoxdur ≠ bütün universitet»): ``unit.view`` açarını
DAŞIYAN üzvlükdən çıxarılır (``get_permission_scope``) — kafedra müdiri yalnız
öz alt-ağacının qruplarını görür, əhatəsiz aktor BOŞ siyahı alır.

MODUL SƏRHƏDİ: ``apps.registrar`` STATİK import EDİLMİR — Program/Curriculum/
StudentAcademicRecord ``django_apps.get_model`` ilə açılır (module_deps ratchet-i
``organizations``-dan ``registrar``-a yeni kənar yaratmasın).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils.translation import pgettext

from .scoping import get_permission_scope
from .views.shared._helpers import _has_org_permission, _visible_units_queryset

_CTX = "accounts.groups"

PERM_VIEW = "unit.view"
PERM_MANAGE = "unit.group_manage"

PAGE_SIZE = 25

#: `OrgUnit.settings` JSON açarları — TƏK MƏNBƏ (yazı tərəfi də bunu işlədir).
SETTING_KEYS = ("language_sector", "course_year", "admission_year", "curriculum_id", "capacity")

GROUP_SORTS: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "-name": ("-name",),
    "code": ("code", "name"),
    "-code": ("-code", "-name"),
}


def group_scope(request, organization):
    """Qrup reyestrinin əhatəsi — `unit.view` açarını daşıyan üzvlükdən."""
    return get_permission_scope(request.user, organization, PERM_VIEW, request=request)


def can_view_groups(request) -> bool:
    return _has_org_permission(request, PERM_VIEW)


def can_manage_groups(request) -> bool:
    return _has_org_permission(request, PERM_MANAGE)


def group_meta(unit) -> dict:
    """`settings` JSON-unu normallaşdırır (boş/korlanmış dəyər UI-ı pozmasın)."""
    raw = unit.settings if isinstance(unit.settings, dict) else {}
    meta = {key: raw.get(key, "") for key in SETTING_KEYS}
    try:
        meta["course_year"] = int(meta["course_year"]) if meta["course_year"] not in ("", None) else 0
    except (TypeError, ValueError):
        meta["course_year"] = 0
    try:
        meta["admission_year"] = int(meta["admission_year"]) if meta["admission_year"] not in ("", None) else 0
    except (TypeError, ValueError):
        meta["admission_year"] = 0
    return meta


def _specialty_chain(unit):
    """Qrupdan yuxarı: ixtisas → kafedra → fakültə (select_related ilə gəlir)."""
    specialty = getattr(unit, "parent", None)
    chair = getattr(specialty, "parent", None) if specialty is not None else None
    faculty = getattr(chair, "parent", None) if chair is not None else None
    return (
        getattr(specialty, "name", "") or "",
        getattr(chair, "name", "") or "",
        getattr(faculty, "name", "") or "",
    )


def language_options(organization) -> list:
    """Dil sektoru seçiciləri — TENANT DATASINDAN, hardcode YOX.

    Layihə yaddaşı: sektor tenant-konfiqurasiya olunandır; universitetdə hansı
    sektorlar varsa, süzgəcdə də onlar görünür.
    """
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    values = set()
    for raw in OrgUnit.objects.filter(organization=organization, unit_type="group").values_list("settings", flat=True):
        if isinstance(raw, dict):
            value = (raw.get("language_sector") or "").strip()
            if value:
                values.add(value)
    return [{"value": value, "label": value} for value in sorted(values)]


def build_groups_registry(request, organization) -> dict:
    """«Qruplar» reyestri: filtr + sıralama + səhifələmə (hamısı serverdə)."""
    if not can_view_groups(request):
        return {
            "has_access": False,
            "access_denied_message": pgettext(
                _CTX, "Qrup reyestrinə baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin."
            ),
        }

    scope = group_scope(request, organization)
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")

    search = (request.GET.get("gr_q") or "").strip()[:120]
    faculty = (request.GET.get("gr_faculty") or "").strip()
    specialty = (request.GET.get("gr_specialty") or "").strip()
    language = (request.GET.get("gr_lang") or "").strip()
    course = (request.GET.get("gr_course") or "").strip()
    show_archived = (request.GET.get("gr_arch") or "") == "1"
    sort = (request.GET.get("gr_sort") or "").strip()
    sort = sort if sort in GROUP_SORTS else "name"

    # ⚠️ Arxiv görünüşü scope helper-indən KEÇMİR: `_visible_units_queryset`
    # yalnız AKTİV vahidləri qaytarır (dizayn qərarı). Arxivdəkiləri göstərmək
    # üçün eyni scope filtri xam sorğuya tətbiq olunur.
    if show_archived:
        from .scoping import scope_org_units

        queryset = scope_org_units(OrgUnit.objects.filter(organization=organization, is_active=False), scope)
    else:
        queryset = _visible_units_queryset(organization, scope)
    queryset = queryset.filter(unit_type="group").select_related("parent", "parent__parent", "parent__parent__parent")

    total_count = queryset.count()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
    if specialty:
        queryset = queryset.filter(parent_id=specialty)
    if faculty:
        faculty_unit = OrgUnit.objects.filter(organization=organization, pk=faculty).only("id", "path").first()
        if faculty_unit is not None:
            queryset = queryset.filter(path__startswith=f"{faculty_unit.path}/")
        else:
            queryset = queryset.none()

    queryset = queryset.order_by(*GROUP_SORTS[sort])
    # Dil/kurs süzgəci JSON sahədədir — DB-dən asılı olmamaq üçün Python-da
    # tətbiq olunur (qrup sayı onluqlarla/yüzlərlədir, min deyil).
    units = list(queryset)
    if language:
        units = [unit for unit in units if group_meta(unit)["language_sector"] == language]
    if course.isdigit():
        units = [unit for unit in units if group_meta(unit)["course_year"] == int(course)]

    page_obj = Paginator(units, PAGE_SIZE).get_page(request.GET.get("gr_page"))

    page_ids = [unit.id for unit in page_obj.object_list]
    # «Plan yoxdur» qrupun ÖZ metadatasından DEYİL, ixtisasın TƏSDİQLƏNMİŞ
    # planından hesablanır (ekran 03/07 ilə eyni meyar) — köçürülmüş qruplarda
    # `settings.curriculum_id` boşdur və o, plan yoxluğu demək DEYİL.
    Curriculum = django_apps.get_model("registrar", "Curriculum")
    Program = django_apps.get_model("registrar", "Program")
    planned_program_ids = set(
        Curriculum.objects.filter(organization=organization, status="approved", is_active=True)
        .values_list("program_id", flat=True)
        .distinct()
    )
    planned_specialty_ids = set(
        Program.objects.filter(organization=organization, pk__in=planned_program_ids, specialty_unit__isnull=False)
        .values_list("specialty_unit_id", flat=True)
        .distinct()
    )
    student_counts = dict(
        StudentAcademicRecord.objects.filter(organization=organization, is_active=True, group_id__in=page_ids)
        .values_list("group_id")
        .annotate(total=Count("id"))
    )

    rows = []
    for unit in page_obj.object_list:
        meta = group_meta(unit)
        specialty_name, chair_name, faculty_name = _specialty_chain(unit)
        rows.append(
            {
                "id": str(unit.id),
                "name": unit.name,
                "code": unit.code or "",
                "specialty_name": specialty_name,
                "specialty_id": str(unit.parent_id) if unit.parent_id else "",
                "chair_name": chair_name,
                "faculty_name": faculty_name,
                "language_sector": meta["language_sector"],
                "course_year": meta["course_year"],
                "admission_year": meta["admission_year"],
                "capacity": meta["capacity"],
                "curriculum_id": meta["curriculum_id"],
                "students": student_counts.get(unit.id, 0),
                "tutor": (unit.head.get_full_name() or unit.head.username) if unit.head_id else "",
                "tutor_id": str(unit.head_id) if unit.head_id else "",
                "is_active": unit.is_active,
                "has_approved_plan": unit.parent_id in planned_specialty_ids,
                "status_key": (
                    "archived"
                    if not unit.is_active
                    else ("active" if unit.parent_id in planned_specialty_ids else "no_plan")
                ),
            }
        )

    return {
        "has_access": True,
        "rows": rows,
        "page_obj": page_obj,
        "table_state": "ready" if rows else "empty",
        "total_count": total_count,
        "filtered_count": page_obj.paginator.count,
        "student_total": sum(row["students"] for row in rows),
        "no_tutor_total": sum(1 for row in rows if not row["tutor"]),
        "no_plan_total": sum(1 for row in rows if row["status_key"] == "no_plan"),
        "filters": {
            "search": search,
            "faculty": faculty,
            "specialty": specialty,
            "language": language,
            "course": course,
            "show_archived": show_archived,
            "sort": sort,
        },
        "faculty_options": [
            {"value": str(unit.id), "label": unit.name}
            for unit in OrgUnit.objects.filter(organization=organization, is_active=True, unit_type="faculty").order_by(
                "name"
            )
        ],
        "specialty_options": [
            {"value": str(unit.id), "label": unit.name}
            for unit in OrgUnit.objects.filter(
                organization=organization, is_active=True, unit_type="specialty"
            ).order_by("name")[:500]
        ],
        "language_options": language_options(organization),
        "can_manage": can_manage_groups(request),
    }


__all__ = [
    "PAGE_SIZE",
    "PERM_MANAGE",
    "PERM_VIEW",
    "SETTING_KEYS",
    "build_groups_registry",
    "can_manage_groups",
    "can_view_groups",
    "group_meta",
    "group_scope",
    "language_options",
]

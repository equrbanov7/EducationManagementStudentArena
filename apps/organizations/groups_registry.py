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
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from core.constants import OrgUnitType
from core.search_text import tolerant_q

from .models import OrgUnit
from .scoping import EMPTY_SCOPE, faculty_read_scope, get_permission_scope, scope_org_units, unit_in_scope
from .views.shared._helpers import _has_org_permission, _visible_units_queryset

_CTX = "accounts.groups"

PERM_VIEW = "unit.view"
PERM_MANAGE = "unit.group_manage"
#: Tələbə hərəkəti (akademik məzuniyyət / xaric) — `apps.accounts.services.people`
#: ilə EYNİ açar; qrup çekmecəsindəki düymələr buna görə görünür/gizlənir.
PERM_STUDENT_MOVEMENT = "student.movement"
#: QA-2 F-03 (2026-10-17): qrupun TƏLƏBƏ SİYAHISI (ad, istifadəçi adı, ixtisas) və «Fərdi tədris planı» DOCX-u
#: yalnız tələbə tərəfi açarlarından birini daşıyana. ``unit.view`` təkcə STRUKTUR oxusudur — HR (heyət idxalı)
#: onu daşıyır, tələbə kataloqu isə HR-a bağlıdır (rol auditi B6). Qrup idarəsi / tələbə hərəkəti də sayılır:
#: həmin aktor çekmecədə tələbə ilə işləyir.
STUDENT_LIST_PERMISSIONS = (
    "people.view_students",
    "student.records_view",
    "student.registry_view",
    PERM_MANAGE,
    PERM_STUDENT_MOVEMENT,
)

PAGE_SIZE = 25

#: `OrgUnit.settings` JSON açarları — TƏK MƏNBƏ (yazı tərəfi də bunu işlədir).
SETTING_KEYS = ("language_sector", "course_year", "admission_year", "curriculum_id", "capacity", "education_form")

#: Dil sektoru seçicisinin STANDART variantları — tenant datasında olmasa da
#: formada görünür (sahib, 2026-09-07: «az, eng sektorlara görə də olsun»).
#: Universitetin öz datasındakı əlavə dəyərlər bunların ARDINCA gəlir.
DEFAULT_LANGUAGE_SECTORS = ("AZ", "EN", "RU")

#: Qəbul ili seçicisi: cari ildən neçə il geriyə (forma + filtr).
ADMISSION_YEAR_SPAN = 10

GROUP_SORTS: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "-name": ("-name",),
    "code": ("code", "name"),
    "-code": ("-code", "-name"),
}


def group_scope(request, organization):
    """Qrup reyestrinin OXU əhatəsi — `unit.view` açarını daşıyan üzvlükdən.

    2026-10-14 (sahib, kafedra müdiri kimi baxış: «ancaq öz fakültəsi daxilindəki qrupları»): kafedra
    kökü valideyn FAKÜLTƏYƏ genişlənir (`faculty_read_scope`) — qruplar fakültənin altındadır. Sətirlər,
    KPI-lər, süzgəclər, tələbə çekmecəsi və fərdi plan DOCX-u bu oxu əhatəsini işlədir; YAZI həmişə
    dar `group_manage_scope` ilə qalır.
    """
    return faculty_read_scope(request.user, organization, PERM_VIEW, request=request)


def group_manage_scope(request, organization):
    """YAZI əməllərinin əhatəsi — `unit.group_manage` açarını daşıyan üzvlükdən.

    Audit 2026-09-28 S4: yazı handler-ləri əvvəl `unit.view` əhatəsini alırdı —
    baxışı geniş (məs. bütün təşkilat), idarəsi dar (bir fakültə) olan aktor
    öz idarə əhatəsindən kənar qrupu dəyişə bilirdi. Yazı həmişə bu əhatə ilə.
    """
    return get_permission_scope(request.user, organization, PERM_MANAGE, request=request)


def student_record_scope_q(scope) -> Q:
    """`StudentAcademicRecord` üçün əhatə filtri — ixtisas bölməsi VƏ YA (arxiv) qrupu.

    Audit 2026-09-28 S3: qrupsuz tələbə namizədləri əvvəl bütün tenant üzrə
    gəlirdi. Qrupsuz tələbənin struktur yeri ixtisasının bölməsidir
    (`program.specialty_unit`); arxivlənmiş qrupu varsa o da sayılır.
    Təşkilat əhatəsi → filtr yoxdur; əhatəsiz → heç nə (fail-closed).
    """
    if scope.is_org_wide:
        return Q()
    return scope.unit_subtree_q(
        path_field="program__specialty_unit__path", id_field="program__specialty_unit_id"
    ) | scope.unit_subtree_q(path_field="group__path", id_field="group_id")


def can_view_groups(request) -> bool:
    return _has_org_permission(request, PERM_VIEW)


def can_manage_groups(request) -> bool:
    return _has_org_permission(request, PERM_MANAGE)


def can_move_students(request) -> bool:
    return _has_org_permission(request, PERM_STUDENT_MOVEMENT)


def can_view_group_students(request) -> bool:
    """Qrupun tələbə siyahısı / fərdi plan DOCX-u (bax ``STUDENT_LIST_PERMISSIONS``)."""
    return any(_has_org_permission(request, key) for key in STUDENT_LIST_PERMISSIONS)


def group_meta(unit) -> dict:
    """`settings` JSON-unu normallaşdırır (boş/korlanmış dəyər UI-ı pozmasın)."""
    raw = unit.settings if isinstance(unit.settings, dict) else {}
    meta = {key: raw.get(key, "") for key in SETTING_KEYS}
    # Köhnə datadan gələn qruplarda dil ``sector`` açarındadır (sahib 2026-10-26: «boş xana qalmasın»).
    meta["language_sector"] = str(meta["language_sector"] or raw.get("sector") or "").strip()
    try:
        meta["course_year"] = int(meta["course_year"]) if meta["course_year"] not in ("", None) else 0
    except (TypeError, ValueError):
        meta["course_year"] = 0
    try:
        meta["admission_year"] = int(meta["admission_year"]) if meta["admission_year"] not in ("", None) else 0
    except (TypeError, ValueError):
        meta["admission_year"] = 0
    meta["education_form"] = str(meta["education_form"] or "").strip()
    return meta


def education_form_choices() -> list:
    """Təhsil forması (əyani/qiyabi/distant) — registrar-ın TƏK mənbəyindən.

    Statik import YOXDUR (modul sərhədi): seçimlər `StudentAcademicRecord`
    sahəsinin `choices`-indən oxunur — yeni forma əlavə olunsa burada da görünür.
    """
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    field = StudentAcademicRecord._meta.get_field("education_form")
    return [{"value": str(value), "label": str(label)} for value, label in field.choices if value]


def education_form_label(value: str) -> str:
    for option in education_form_choices():
        if option["value"] == value:
            return option["label"]
    return ""


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


def _group_settings(organization, scope=None):
    """Qrupların `settings` JSON-ları — ``scope`` verilərsə YALNIZ əhatədəki qruplar (2026-10-14)."""
    queryset = OrgUnit.objects.filter(organization=organization, unit_type="group")
    if scope is not None:
        queryset = scope_org_units(queryset, scope)
    return queryset.values_list("settings", flat=True)


def language_options(organization, scope=None, *, settings_rows=None) -> list:
    """Dil sektoru seçiciləri — TENANT DATASINDAN, hardcode YOX.

    Layihə yaddaşı: sektor tenant-konfiqurasiya olunandır; universitetdə hansı
    sektorlar varsa, süzgəcdə də onlar görünür. ``settings_rows`` — eyni əhatə üçün artıq oxunmuş
    ``_group_settings`` siyahısı (PERF-1 F-08: reyestr onu bir dəfə oxuyur).
    """
    values = set()
    for raw in _group_settings(organization, scope) if settings_rows is None else settings_rows:
        if isinstance(raw, dict):
            value = (raw.get("language_sector") or raw.get("sector") or "").strip()
            if value:
                values.add(value)
    return [{"value": value, "label": value} for value in sorted(values)]


def language_form_options(organization, *, settings_rows=None) -> list:
    """Forma üçün dil sektoru seçimləri: standart AZ/EN/RU + tenantın öz dəyərləri (BÜTÜN qruplar üzrə)."""
    seen = []
    for value in DEFAULT_LANGUAGE_SECTORS:
        seen.append(value)
    for option in language_options(organization, settings_rows=settings_rows):
        if option["value"].upper() not in seen and option["value"] not in seen:
            seen.append(option["value"])
    return [{"value": value, "label": value} for value in seen]


def admission_year_options(organization, *, current_year: int, scope=None, settings_rows=None) -> list:
    """Qəbul ili seçimləri — cari il + geriyə `ADMISSION_YEAR_SPAN` il, tenant
    datasındakı kənar illər də (məs. köçürülmüş köhnə qruplar) əlavə olunur."""
    years = set(range(current_year + 1, current_year - ADMISSION_YEAR_SPAN, -1))
    for raw in _group_settings(organization, scope) if settings_rows is None else settings_rows:
        if isinstance(raw, dict):
            try:
                year = int(raw.get("admission_year") or 0)
            except (TypeError, ValueError):
                continue
            if year:
                years.add(year)
    return [{"value": str(year), "label": str(year)} for year in sorted(years, reverse=True)]


def scoped_filter_options(organization, scope, unit_type, *, limit=None) -> list:
    """Süzgəc seçimləri (`{value, label}`) — YALNIZ aktorun əhatəsindəki ``unit_type`` vahidləri.

    Əhatə alt-ağacı + əhatə köklərinin ƏCDADLARI (məs. ixtisas koordinatoru öz fakültəsini seçə bilsin —
    süzgəc sətirləri yenə əhatə ilə məhdudlaşır). Org əhatəsi → hamısı; əhatəsiz → boş (fail-closed).
    """
    queryset = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type=unit_type)
    if not scope.is_org_wide:
        if not scope.is_unit_scoped:
            return []
        ancestor_ids = {part for path in scope.unit_paths for part in str(path or "").split("/") if part}
        queryset = queryset.filter(scope.unit_subtree_q() | Q(pk__in=list(ancestor_ids)))
    queryset = queryset.order_by("name")
    if limit:
        queryset = queryset[:limit]
    return [{"value": str(unit.id), "label": unit.name} for unit in queryset]


def _parent_links(organization, page_units) -> tuple[dict, dict]:
    """Səhifədəki qruplar üçün ana qrup adları və alt qrup sayları — 2 toplu sorğu (səhifə ölçüsündən asılı deyil)."""
    parent_ids = {str((unit.settings or {}).get("parent_group") or "") for unit in page_units} - {""}
    parent_names = (
        dict(
            (str(pk), name)
            for pk, name in OrgUnit.objects.filter(organization=organization, pk__in=parent_ids).values_list(
                "pk", "name"
            )
        )
        if parent_ids
        else {}
    )
    page_ids = [str(unit.id) for unit in page_units]
    subgroup_counts = {}
    if page_ids:
        for parent_id in OrgUnit.objects.filter(
            organization=organization, unit_type=OrgUnitType.GROUP, is_active=True, settings__parent_group__in=page_ids
        ).values_list("settings__parent_group", flat=True):
            subgroup_counts[str(parent_id)] = subgroup_counts.get(str(parent_id), 0) + 1
    return parent_names, subgroup_counts


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
    current_year = timezone.localdate().year

    search = (request.GET.get("gr_q") or "").strip()[:120]
    faculty = (request.GET.get("gr_faculty") or "").strip()
    specialty = (request.GET.get("gr_specialty") or "").strip()
    language = (request.GET.get("gr_lang") or "").strip()
    course = (request.GET.get("gr_course") or "").strip()
    education_form = (request.GET.get("gr_form") or "").strip()
    admission_year = (request.GET.get("gr_year") or "").strip()
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
    # PERF-1 F-08: bütün əhatə qrupları JOIN-suz yüklənir (süzgəc/KPI yalnız öz sahələrini oxuyur);
    # ixtisas → kafedra → fakültə zənciri və tyutor yalnız SƏHİFƏ sətirləri üçün bir sorğu ilə gəlir.
    queryset = queryset.filter(unit_type="group")

    total_count = queryset.count()
    # Dözümlü kod axtarışı (sahib 2026-09-26): «234king», «234k ing», «234-K-ing» → «234 K ing».
    search_q = tolerant_q(search, ("name", "code"), compact=True)
    if search_q is not None:
        queryset = queryset.filter(search_q)
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
    python_filtered = bool(language or course.isdigit() or education_form or admission_year.isdigit())
    if language:
        units = [unit for unit in units if group_meta(unit)["language_sector"] == language]
    if course.isdigit():
        units = [unit for unit in units if group_meta(unit)["course_year"] == int(course)]
    if education_form:
        units = [unit for unit in units if group_meta(unit)["education_form"] == education_form]
    if admission_year.isdigit():
        units = [unit for unit in units if group_meta(unit)["admission_year"] == int(admission_year)]

    page_obj = Paginator(units, PAGE_SIZE).get_page(request.GET.get("gr_page"))

    page_ids = [unit.id for unit in page_obj.object_list]
    page_units_by_id = (
        OrgUnit.objects.filter(pk__in=page_ids)
        .select_related("parent", "parent__parent", "parent__parent__parent", "head")
        .in_bulk()
        if page_ids
        else {}
    )
    page_units = [page_units_by_id.get(unit.id, unit) for unit in page_obj.object_list]
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
    from .group_roster_union import roster_counts

    student_counts = roster_counts(organization, page_units)

    form_labels = {option["value"]: option["label"] for option in education_form_choices()}
    # PERF-1 F-08: qrup `settings` JSON-ları (dil / qəbul ili seçimləri) bir dəfə oxunur — əvvəl 3 dəfə idi.
    scoped_settings = list(_group_settings(organization, scope))
    # 2026-10-14: OXU əhatəsi fakültəyə genişləndi (kafedra/ixtisas tyutoru bütün fakültənin qruplarını görür),
    # YAZI isə dar `unit.group_manage` əhatəsindədir — sətir düymələri yalnız yazı əhatəsindəki qrupa (server
    # kənar qrupa onsuz da 404 qaytarır). Sorğusuz: əhatə bir dəfə, yoxlama yol üzrə.
    can_manage = can_manage_groups(request)
    manage_scope = group_manage_scope(request, organization) if can_manage else EMPTY_SCOPE
    can_view_students = can_view_group_students(request)
    parent_names, subgroup_counts = _parent_links(organization, page_units)
    rows = []
    for unit in page_units:
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
                "education_form": meta["education_form"],
                "education_form_label": form_labels.get(meta["education_form"], ""),
                # «Tələbə əlavə et» dialoqunun namizəd axtarışı (qrupsuz tələbələr).
                "candidates_url": reverse("organizations:group_student_candidates", args=[organization.slug, unit.id]),
                "students": student_counts.get(unit.id, 0),
                "tutor": (unit.head.get_full_name() or unit.head.username) if unit.head_id else "",
                "tutor_id": str(unit.head_id) if unit.head_id else "",
                "is_active": unit.is_active,
                # QA-2 F-16 (2026-10-17): ortaq ana / alt qrup əlaqəsi (settings.parent_group, bax parent_groups.py).
                "parent_group_name": parent_names.get(str((unit.settings or {}).get("parent_group") or ""), ""),
                "subgroup_count": subgroup_counts.get(str(unit.id), 0),
                "path": unit.path or "",
                "can_manage": can_manage and unit_in_scope(manage_scope, unit),
                "can_view_students": can_view_students,
                # Tələbə çekmecəsi (JSON) və rəsmi «Fərdi tədris planı» DOCX-u.
                "students_url": reverse("organizations:group_students", args=[organization.slug, unit.id]),
                "plan_url": reverse("registrar:group_individual_plan", args=[unit.id]),
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
        # KPI-lər SƏHİFƏ deyil, ƏHATƏDƏKİ süzülmüş qrupların hamısı üzrə (2026-10-14, sahib: dekan öz
        # fakültəsinin tələbə sayını görsün) — `units` artıq `unit.view` əhatəsi ilə süzülüb.
        # PERF-1 F-08: Python süzgəci yoxdursa `units` = `queryset` — uzun id siyahısı əvəzinə alt-sorğu.
        "student_total": (
            StudentAcademicRecord.objects.filter(
                organization=organization,
                is_active=True,
                group_id__in=[unit.id for unit in units] if python_filtered else queryset.values("pk"),
            ).count()
            if units
            else 0
        ),
        "no_tutor_total": sum(1 for unit in units if not unit.head_id),
        "no_plan_total": sum(1 for unit in units if unit.is_active and unit.parent_id not in planned_specialty_ids),
        "filters": {
            "search": search,
            "faculty": faculty,
            "specialty": specialty,
            "language": language,
            "course": course,
            "education_form": education_form,
            "admission_year": admission_year,
            "show_archived": show_archived,
            "sort": sort,
        },
        # 2026-10-14 (sahib: «fakültə başqa fakültənin qruplarını görməsin»): seçimlər ƏHATƏ ilə — əvvəl
        # bütün təşkilatın fakültə/ixtisasları siyahıda görünürdü (qrup sətirləri onsuz da süzülürdü).
        "faculty_options": scoped_filter_options(organization, scope, OrgUnitType.FACULTY),
        "specialty_options": scoped_filter_options(organization, scope, OrgUnitType.SPECIALTY, limit=500),
        "language_options": language_options(organization, scope, settings_rows=scoped_settings),
        "language_form_options": language_form_options(
            organization, settings_rows=scoped_settings if scope.is_org_wide else None
        ),
        "education_form_options": education_form_choices(),
        "current_year": current_year,
        "admission_year_options": admission_year_options(
            organization, current_year=current_year, scope=scope, settings_rows=scoped_settings
        ),
        # Köçürmə dialoqunun hədəf qrupları — əhatədəki AKTİV qruplar (səhifədən asılı deyil).
        "group_options": [
            {"value": str(unit_id), "label": name}
            for unit_id, name in _visible_units_queryset(organization, scope)
            .filter(unit_type="group")
            .order_by("name")
            .values_list("id", "name")[:1000]
        ],
        "can_manage": can_manage,
        "can_move_students": can_move_students(request),
        "can_view_students": can_view_students,
    }


__all__ = [
    "ADMISSION_YEAR_SPAN",
    "DEFAULT_LANGUAGE_SECTORS",
    "PAGE_SIZE",
    "PERM_MANAGE",
    "PERM_STUDENT_MOVEMENT",
    "PERM_VIEW",
    "SETTING_KEYS",
    "STUDENT_LIST_PERMISSIONS",
    "admission_year_options",
    "build_groups_registry",
    "can_manage_groups",
    "can_move_students",
    "can_view_group_students",
    "can_view_groups",
    "education_form_choices",
    "education_form_label",
    "group_manage_scope",
    "group_meta",
    "group_scope",
    "language_form_options",
    "language_options",
    "scoped_filter_options",
    "student_record_scope_q",
]


def visible_group(organization, scope, unit_id, *, include_archived=False):
    queryset = OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP)
    if not include_archived:
        queryset = queryset.filter(is_active=True)
    return scope_org_units(queryset, scope).filter(pk=(unit_id or "").strip()).select_related("parent", "head").first()

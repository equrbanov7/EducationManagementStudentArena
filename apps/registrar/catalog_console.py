"""Akademik kataloq konsolu — OXU və YAZI xidməti (kabinet bölməsi üçün).

Niyə var (sahib, 2026-09-09)
----------------------------
«Registrar (kataloq)» sidebar keçidi `registrar:console` MÜSTƏQİL səhifəsinə
aparırdı: kabinet qabığı və sol sidebar itirdi, hər yaratma/redaktə isə ayrıca
səhifəyə tullayırdı. Sahibin tələbi: «yeni səhifəyə atmamalıdı, sidebar solda
qalıb sağda bu açmalıdı».

Bu modul həmin konsolun MƏNTİQİNİ səhifədən ayırır ki, kabinet bölməsi
(`accounts/.../_sections/registrar_catalog.py`) onu server-render panel kimi
göstərə, dialoqlardan isə TƏK JSON son nöqtəsi ilə yaza bilsin.

Nə DƏYİŞMİR
-----------
* İcazə: org-wide ``course.edit`` (``can_manage``) — köhnə konsolun eyni qapısı.
* Validasiya: mövcud ``forms.py`` sinifləri (``ProgramForm`` …) və rubrik üçün
  ``rubrics.py`` xidməti — burada paralel qayda YAZILMIR.
* Tenant izolyasiyası: hər sorğu ``organization=`` ilə süzülür; başqa
  təşkilatın obyekti 404 verir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from core.constants import OrgUnitType

from .forms import CurriculumForm, OfferingForm, ProgramForm, StudentRecordForm, SubjectForm
from .models import (
    CourseOffering,
    Curriculum,
    Program,
    Rubric,
    StudentAcademicRecord,
    Subject,
)
from .views import _current_period

MANAGE_PERMISSION = "course.edit"

#: Tabların sabit sırası — sidebar-dakı «Registrar (kataloq)» bölməsinin içi.
TAB_KEYS = ("programs", "subjects", "curricula", "offerings", "rubrics", "students")

#: Siyahılar səhifələnmir; kataloq kiçikdir, amma pəncərə yenə də məhdudlaşır ki,
#: nasaz məlumatda panel donmasın.
ROW_LIMIT = 300

_FORMS = {
    "programs": (Program, ProgramForm),
    "subjects": (Subject, SubjectForm),
    "curricula": (Curriculum, CurriculumForm),
    "offerings": (CourseOffering, OfferingForm),
    "students": (StudentAcademicRecord, StudentRecordForm),
}


def can_manage(user, organization) -> bool:
    """Kataloq konsolunun qapısı — org-wide ``course.edit``.

    Vahid-əhatəli (unit) aktor buraxılmır: kataloq CRUD-u hələ obyekt səviyyəsində
    əhatələnmir, ona görə vahid aktoruna açsaq bütün təşkilatın sətirlərini
    görər/dəyişər. Bu, köhnə `console_views._can_manage_registrar` ilə EYNİ
    qaydadır (fail-closed).
    """
    if not getattr(user, "is_authenticated", False) or organization is None:
        return False
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return OrgUnit.user_permission_scope(user, organization, MANAGE_PERMISSION).is_org_wide


def current_period(organization):
    return _current_period(organization)


# ── Sorğular ────────────────────────────────────────────────────────────────


def _programs(organization):
    return Program.objects.filter(organization=organization).select_related("specialty_unit").order_by("name")


def _subjects(organization):
    return Subject.objects.filter(organization=organization).order_by("code")


def _curricula(organization):
    return (
        Curriculum.objects.filter(organization=organization)
        .select_related("program")
        .annotate(row_count=Count("rows"))
        .order_by("-admission_year", "program__name")
    )


def _offerings(organization, period):
    qs = (
        CourseOffering.objects.filter(organization=organization)
        .select_related("subject", "group", "instructor", "period")
        .order_by("subject__code")
    )
    return qs.filter(period=period) if period is not None else qs.none()


def _rubrics(organization):
    return Rubric.objects.filter(organization=organization).annotate(criteria_count=Count("criteria")).order_by("name")


def _students(organization):
    return (
        StudentAcademicRecord.objects.filter(organization=organization)
        .select_related("student", "program", "group", "curriculum")
        .order_by("-created_at")
    )


def counts(organization, period=None) -> dict:
    """Tab nişanlarındakı rəqəmlər — hər biri bir COUNT sorğusu."""
    return {
        "programs": _programs(organization).count(),
        "subjects": _subjects(organization).count(),
        "curricula": Curriculum.objects.filter(organization=organization).count(),
        "offerings": _offerings(organization, period).count(),
        "rubrics": Rubric.objects.filter(organization=organization).count(),
        "students": StudentAcademicRecord.objects.filter(organization=organization).count(),
    }


def _text(*parts) -> str:
    return " ".join(str(part) for part in parts if part).casefold()


def _person(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.username


def _program_rows(organization, query, status):
    rows = []
    for item in _programs(organization):
        if status == "active" and not item.is_active:
            continue
        if status == "inactive" and item.is_active:
            continue
        if query and query not in _text(item.name, item.code, item.official_code, item.legacy_official_code):
            continue
        rows.append(
            {
                "id": str(item.id),
                "title": item.name,
                "code": item.official_code_pair or item.code,
                "is_active": item.is_active,
                "meta": [
                    item.get_degree_level_display(),
                    f"{item.ects_total} ECTS",
                    f"{item.absence_limit_percent}%",
                ],
            }
        )
    return rows


def _subject_rows(organization, query, status):
    rows = []
    for item in _subjects(organization):
        if status == "active" and not item.is_active:
            continue
        if status == "inactive" and item.is_active:
            continue
        if query and query not in _text(item.name, item.code):
            continue
        rows.append(
            {
                "id": str(item.id),
                "title": item.name,
                "code": item.code,
                "is_active": item.is_active,
                "meta": [f"{item.ects} ECTS"],
            }
        )
    return rows


def _curriculum_rows(organization, query, status, program):
    rows = []
    for item in _curricula(organization):
        if status == "active" and not item.is_active:
            continue
        if status == "inactive" and item.is_active:
            continue
        if program and str(item.program_id) != program:
            continue
        if query and query not in _text(item.name, item.program.name, item.admission_year):
            continue
        rows.append(
            {
                "id": str(item.id),
                "title": item.name or item.program.display_label,
                "code": f"{item.program.display_label} · {item.admission_year}",
                "is_active": item.is_active,
                "meta": [f"{item.row_count}"],
                "detail_kind": "curriculum",
            }
        )
    return rows


def _offering_rows(organization, period, query, flag):
    rows = []
    for item in _offerings(organization, period):
        if flag == "no_instructor" and item.instructor_id:
            continue
        if flag == "with_instructor" and not item.instructor_id:
            continue
        if query and query not in _text(
            item.subject.name, item.subject.code, item.group and item.group.name, _person(item.instructor)
        ):
            continue
        rows.append(
            {
                "id": str(item.id),
                "title": item.subject.name,
                "code": item.subject.code,
                "is_active": item.is_active,
                "group": item.group.name if item.group else "",
                "instructor": _person(item.instructor),
                "meta": [f"{item.lesson_hours or 0}"],
            }
        )
    return rows


def _rubric_rows(organization, query, status):
    rows = []
    for item in _rubrics(organization):
        if status == "active" and not item.is_active:
            continue
        if status == "inactive" and item.is_active:
            continue
        if query and query not in _text(item.name, item.description):
            continue
        rows.append(
            {
                "id": str(item.id),
                "title": item.name,
                "code": "",
                "is_active": item.is_active,
                "description": item.description or "",
                "meta": [f"{item.criteria_count}"],
            }
        )
    return rows


def _student_rows(organization, query, status, program):
    rows = []
    for item in _students(organization)[:ROW_LIMIT]:
        if status and item.status != status:
            continue
        if program and str(item.program_id) != program:
            continue
        if query and query not in _text(_person(item.student), item.student.username, item.program.name):
            continue
        rows.append(
            {
                "id": str(item.id),
                "title": _person(item.student),
                "code": item.student.username,
                "is_active": item.is_active,
                "program": item.program.display_label,
                "group": item.group.name if item.group else "",
                "status": item.status,
                "status_label": item.get_status_display(),
                "meta": [str(item.admission_year)],
            }
        )
    return rows


def rows(organization, *, tab, period=None, query="", status="", program="", flag=""):
    """Seçilmiş tabın sətirləri (süzgəc SERVERDƏ tətbiq olunur)."""
    query = (query or "").strip().casefold()
    if tab == "programs":
        return _program_rows(organization, query, status)
    if tab == "subjects":
        return _subject_rows(organization, query, status)
    if tab == "curricula":
        return _curriculum_rows(organization, query, status, program)
    if tab == "offerings":
        return _offering_rows(organization, period, query, flag)
    if tab == "rubrics":
        return _rubric_rows(organization, query, status)
    if tab == "students":
        return _student_rows(organization, query, status, program)
    return []


def program_options(organization):
    return [{"value": str(p.id), "label": p.display_label} for p in _programs(organization)]


def subject_options(organization):
    return [{"value": str(s.id), "label": f"{s.code} — {s.name}"} for s in _subjects(organization) if s.is_active]


def curriculum_options(organization):
    return [
        {"value": str(c.id), "label": f"{c.program.display_label} · {c.admission_year}"}
        for c in Curriculum.objects.filter(organization=organization)
        .select_related("program")
        .order_by("-admission_year")
    ]


def period_options(organization):
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return [
        {"value": str(p.id), "label": p.name}
        for p in AcademicPeriod.objects.filter(organization=organization).order_by("-start_date")[:24]
    ]


def group_options(organization):
    """Qrup seçicisi.

    ⚠️ Qrup AYRICA model DEYİL — `organizations.OrgUnit`-in `group` tipidir
    (`CourseOffering.group` FK-sı da ora gedir).
    """
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return [
        {"value": str(unit.id), "label": unit.name}
        for unit in OrgUnit.objects.filter(
            organization=organization, unit_type=OrgUnitType.GROUP, is_active=True
        ).order_by("name")[:800]
    ]


def instructor_options(organization):
    """Müəllim seçicisi — kafedra/fakültə təyinatı olan AKTİV müəllim üzvlükləri.

    Siyahı ~700 sətir olur; `bootstrap-single-select` menyu daxili axtarışla
    (`data-live-search`) bunu rahat daşıyır, ona görə server-backed seçici
    qurulmur.
    """
    Membership = django_apps.get_model("organizations", "Membership")
    seen, out = set(), []
    rows = (
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            user__is_active=True,
            role__name__in=("teacher", "assistant", "assistant_teacher", "instructor", "collaborator"),
        )
        .select_related("user")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    for membership in rows:
        if membership.user_id in seen:
            continue
        seen.add(membership.user_id)
        out.append({"value": str(membership.user_id), "label": _person(membership.user)})
    return out


def status_options():
    return [
        {"value": key, "label": str(label)} for key, label in StudentAcademicRecord._meta.get_field("status").choices
    ]


def degree_options():
    return [{"value": key, "label": str(label)} for key, label in Program._meta.get_field("degree_level").choices]


# ── Yazı ────────────────────────────────────────────────────────────────────


def _instance(model, organization, pk):
    if not pk:
        return None
    return get_object_or_404(model, pk=pk, organization=organization)


def save(organization, *, tab, pk, data):
    """Kataloq sətrini yarat/yenilə. Qaytarır ``(obj, errors)``.

    Validasiya mövcud ``forms.py`` sinifləridir — burada paralel qayda yoxdur.
    Rubrik ayrıca gedir, çünki meyarları mətn sahəsindən oxunur.
    """
    if tab == "rubrics":
        return _save_rubric(organization, pk=pk, data=data)
    entry = _FORMS.get(tab)
    if entry is None:
        return None, {"__all__": ["unknown_tab"]}
    model, form_class = entry
    instance = _instance(model, organization, pk)
    form = form_class(data, instance=instance, organization=organization)
    if not form.is_valid():
        return None, {field: [str(msg) for msg in msgs] for field, msgs in form.errors.items()}
    obj = form.save(commit=False)
    obj.organization = organization
    try:
        obj.save()
        if hasattr(form, "save_m2m"):
            form.save_m2m()
    except IntegrityError as exc:
        return None, {"__all__": [str(exc)]}
    return obj, {}


def _save_rubric(organization, *, pk, data):
    from . import rubrics as rubrics_service

    instance = _instance(Rubric, organization, pk)
    try:
        criteria = rubrics_service.parse_criteria_text(data.get("criteria_text") or "")
        obj = rubrics_service.save_rubric(
            organization=organization,
            name=data.get("name") or "",
            description=data.get("description") or "",
            criteria=criteria,
            rubric=instance,
        )
    except ValidationError as exc:
        return None, {"__all__": [str(msg) for msg in exc.messages]}
    except ValueError as exc:
        return None, {"criteria_text": [str(exc)]}
    except IntegrityError:
        return None, {"name": ["duplicate"]}
    return obj, {}


def entity_values(organization, *, tab, pk) -> dict:
    """Redaktə dialoqunu doldurmaq üçün mövcud sətrin dəyərləri."""
    if tab == "rubrics":
        from . import rubrics as rubrics_service

        item = _instance(Rubric, organization, pk)
        return {
            "name": item.name,
            "description": item.description or "",
            "criteria_text": rubrics_service.criteria_text(item),
        }
    entry = _FORMS.get(tab)
    if entry is None:
        return {}
    model, form_class = entry
    item = _instance(model, organization, pk)
    form = form_class(instance=item, organization=organization)
    values = {}
    for name in form.fields:
        value = form.initial.get(name, form.get_initial_for_field(form.fields[name], name))
        if value is None:
            values[name] = ""
        elif isinstance(value, bool):
            values[name] = value
        else:
            values[name] = str(getattr(value, "pk", value))
    return values


def health(organization, period=None) -> dict:
    """Kataloqun «sağlamlıq» göstəriciləri — panelin KPI zolağı üçün."""
    offerings = _offerings(organization, period)
    return {
        "programs": _programs(organization).count(),
        "subjects": _subjects(organization).count(),
        "curricula": Curriculum.objects.filter(organization=organization).count(),
        "offerings": offerings.count(),
        "offerings_no_instructor": offerings.filter(Q(instructor__isnull=True)).count(),
        "empty_curricula": Curriculum.objects.filter(organization=organization)
        .annotate(n=Count("rows"))
        .filter(n=0)
        .count(),
    }

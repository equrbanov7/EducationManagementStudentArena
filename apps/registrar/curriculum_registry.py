"""Ekran 05 «Tədris planı redaktoru» — OXU tərəfi (yazı: ``curriculum_actions``).

Nə verir: plan seçicisi, semestr tabları, sətir cədvəli (sətir-içi validasiya
bayraqları ilə), semestr üzrə kredit/saat yekunları, balans paneli, əvvəlki
versiya ilə DİFF və audit timeline-ı.

QAYDALAR
--------
* Filtr / sıralama / səhifələmə SERVER tərəfdədir (handoff §8/14). Plan sətri
  azdır (bir semestr ~10 sətir), ona görə səhifələmə YOXDUR — semestr tabı
  təbii bölgüdür.
* «Açıq xəbərdarlıq» SAXLANILMIR — hər sorğuda hesablanır (§8/13).
* Təsdiqlənmiş plan IMMUTABLE-dır: bu modul yalnız `can_edit` bayrağını verir,
  faktiki qapı ``curriculum_state.assert_editable``-dədir (fail-closed).
* MODUL SƏRHƏDİ: ``apps.organizations`` STATİK import EDİLMİR — OrgUnit və
  AuditLog ``django_apps.get_model`` ilə açılır.
"""

from __future__ import annotations

import uuid

from django.apps import apps as django_apps
from django.db.models import Count, Q, Sum
from django.utils.translation import pgettext

from core.permissions import has_permission

from .curriculum_state import EDITABLE_STATUSES, next_transition, permission_for
from .models import Curriculum, CurriculumSubject, Program, Subject
from .models.curriculum_meta import (
    SEMESTER_CREDIT_TARGET,
    AssessmentForm,
    PlanStatus,
    contact_hours,
    expected_total_hours,
    row_hour_errors,
    weekly_load,
)

_CTX = "accounts.curriculum"

PERM_VIEW = "plan.view"
PERM_EDIT = "plan.edit"

#: Sətir xəta açarı → istifadəçi mətni (maşın açarı `curriculum_meta`-dadır).
ROW_ERROR_LABELS = {
    "credits_required": pgettext(_CTX, "Kredit təyin edilməyib"),
    "total_mismatch": pgettext(_CTX, "Ümumi saat kredit × 30 ilə uyğun gəlmir"),
    "split_mismatch": pgettext(_CTX, "Mühazirə + seminar + laboratoriya + sərbəst iş ümumi saatla uyğun gəlmir"),
}


def actor_permissions(request) -> list:
    return list(getattr(request, "org_permissions", []) or [])


def can_view_plans(request) -> bool:
    return has_permission(actor_permissions(request), PERM_VIEW)


def can_edit_plans(request) -> bool:
    return has_permission(actor_permissions(request), PERM_EDIT)


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def plan_scope(request, organization, permission: str):
    """Aktorun HƏMİN AÇAR üzrə struktur əhatəsi (``UnitScope``).

    MODUL SƏRHƏDİ: ``apps.organizations`` statik import EDİLMİR — scope
    ``OrgUnit.user_permission_scope`` sinif metodu ilə həll olunur
    (``apps/registrar/handover.py`` ilə eyni naxış).
    """
    return _org_unit_model().user_permission_scope(getattr(request, "user", None), organization, permission)


def unit_in_scope(organization, unit_id, scope) -> bool:
    """Verilmiş bölmə aktorun alt-ağacındadırmı — FAIL-CLOSED.

    Əhatəsiz aktor (``EMPTY_SCOPE``) və bölməsiz (``specialty_unit=None``)
    ixtisas üçün ``False``; org-wide rol üçün həmişə ``True``.
    """
    if not scope.has_structure_access:
        return False
    if scope.is_org_wide:
        return True
    if not unit_id:
        return False
    OrgUnit = _org_unit_model()
    return OrgUnit.objects.filter(organization=organization, pk=unit_id).filter(scope.unit_subtree_q()).exists()


def program_in_scope(request, organization, program, permission: str) -> bool:
    """İxtisas (``Program``) aktorun ``permission`` əhatəsindədirmi.

    ⚠️ TƏHLÜKƏSİZLİK (audit 2026-09-03, P1): açar («nə edə bilərsən») əhatə
    («nəyə toxuna bilərsən») demək DEYİL. ``plan.edit`` / ``plan.approve_chair``
    daşıyan kafedra müdiri əvvəl BÜTÜN universitetin planlarını redaktə edə və
    kafedra mərhələsini keçirə bilirdi — burada onun öz alt-ağacı ilə
    məhdudlaşdırılır. Tədris şöbəsi ORGANIZATION scope-lu olduğu üçün
    təsirlənmir.
    """
    scope = plan_scope(request, organization, permission)
    return unit_in_scope(organization, getattr(program, "specialty_unit_id", None), scope)


def plan_in_scope(request, organization, plan, permission: str) -> bool:
    """Plan (``Curriculum``) aktorun ``permission`` əhatəsindədirmi."""
    return program_in_scope(request, organization, plan.program, permission)


def chair_options(organization) -> list:
    OrgUnit = _org_unit_model()
    return [
        {"value": str(unit.id), "label": unit.name}
        for unit in OrgUnit.objects.filter(
            organization=organization, is_active=True, unit_type__in=("chair", "department")
        ).order_by("name")
    ]


# --------------------------------------------------------------------------- #
# Balans hesabı — SAF (model instansiyası yox, dict siyahısı alır)
# --------------------------------------------------------------------------- #


def plan_balance(rows: list, *, credit_target: int = SEMESTER_CREDIT_TARGET) -> dict:
    """Semestr üzrə kredit/saat yekunları + AÇIQ XƏBƏRDARLIQ siyahısı.

    Xəbərdarlıq iki mənbədən gəlir:
      * sətir səviyyəsi — saat uzlaşması (``row_hour_errors``);
      * semestr səviyyəsi — semestrin kredit cəmi hədəfdən (30) fərqlidir.

    ⚠️ Xəbərdarlıq SAXLANILMIR: hər sorğuda hesablanır (§8/13).
    """
    semesters: dict = {}
    for row in rows:
        bucket = semesters.setdefault(
            row["semester_number"],
            {
                "semester_number": row["semester_number"],
                "credits": 0,
                "total_hours": 0,
                "contact_hours": 0,
                "selfwork_hours": 0,
                "lecture_hours": 0,
                "seminar_hours": 0,
                "lab_hours": 0,
                "row_count": 0,
            },
        )
        bucket["credits"] += row["credits"]
        bucket["total_hours"] += row["total_hours"]
        bucket["contact_hours"] += row["contact_hours"]
        bucket["selfwork_hours"] += row["selfwork_hours"]
        bucket["lecture_hours"] += row["lecture_hours"]
        bucket["seminar_hours"] += row["seminar_hours"]
        bucket["lab_hours"] += row["lab_hours"]
        bucket["row_count"] += 1

    warnings: list = []
    for bucket in semesters.values():
        if bucket["credits"] != credit_target:
            bucket["credit_warning"] = True
            warnings.append(
                {
                    "kind": "semester_credits",
                    "semester_number": bucket["semester_number"],
                    "text": pgettext(_CTX, "%(sem)d-ci semestr: %(credits)d kredit (hədəf %(target)d)")
                    % {
                        "sem": bucket["semester_number"],
                        "credits": bucket["credits"],
                        "target": credit_target,
                    },
                }
            )
        else:
            bucket["credit_warning"] = False

    for row in rows:
        for key in row["errors"]:
            warnings.append(
                {
                    "kind": key,
                    "semester_number": row["semester_number"],
                    "text": f"{row['subject_code']} — {ROW_ERROR_LABELS.get(key, key)}",
                }
            )

    return {
        "semesters": [semesters[key] for key in sorted(semesters)],
        "warnings": warnings,
        "credit_target": credit_target,
        "total_credits": sum(bucket["credits"] for bucket in semesters.values()),
        "total_hours": sum(bucket["total_hours"] for bucket in semesters.values()),
        "total_contact": sum(bucket["contact_hours"] for bucket in semesters.values()),
        "total_selfwork": sum(bucket["selfwork_hours"] for bucket in semesters.values()),
    }


def _row_payload(row) -> dict:
    errors = row_hour_errors(
        credits=row.credits,
        total_hours=row.total_hours,
        lecture_hours=row.lecture_hours,
        seminar_hours=row.seminar_hours,
        lab_hours=row.lab_hours,
        selfwork_hours=row.selfwork_hours,
    )
    return {
        "id": str(row.id),
        "row_code": row.row_code or "",
        "subject_id": str(row.subject_id),
        "subject_code": row.subject.code,
        "subject_name": row.subject.name,
        "semester_number": row.semester_number,
        "credits": row.credits,
        "total_hours": row.total_hours,
        "expected_total": expected_total_hours(row.credits),
        "lecture_hours": row.lecture_hours,
        "seminar_hours": row.seminar_hours,
        "lab_hours": row.lab_hours,
        "selfwork_hours": row.selfwork_hours,
        "contact_hours": contact_hours(row.lecture_hours, row.seminar_hours, row.lab_hours),
        "weekly_hours": round(weekly_load(row.lecture_hours, row.seminar_hours, row.lab_hours), 1),
        "assessment_form": row.assessment_form,
        "assessment_label": row.get_assessment_form_display(),
        "language": row.language or "",
        "is_elective": row.is_elective,
        "elective_group": row.elective_group or "",
        "chair_id": str(row.teaching_chair_id) if row.teaching_chair_id else "",
        "chair_name": row.teaching_chair.name if row.teaching_chair_id else "",
        "errors": errors,
        "error_labels": [str(ROW_ERROR_LABELS.get(key, key)) for key in errors],
    }


def plan_options(organization, *, program_id: str = "") -> list:
    """Plan seçicisi — proqram + qəbul ili + versiya (ən yenisi əvvəldə)."""
    queryset = Curriculum.objects.filter(organization=organization).select_related("program")
    if program_id:
        queryset = queryset.filter(program_id=program_id)
    return [
        {
            "value": str(plan.id),
            "label": "%s · %s · v%s" % (plan.program.display_label, plan.admission_year, plan.version),
            "status": plan.status,
        }
        for plan in queryset.order_by("-admission_year", "program__name", "-version")[:200]
    ]


def _timeline(organization, plan) -> list:
    """Audit timeline — ayrıca cədvəl SAXLANMIR, ``core.audit`` oxunur."""
    from django.contrib.contenttypes.models import ContentType

    AuditLog = django_apps.get_model("audit", "AuditLog")
    content_type = ContentType.objects.get_for_model(Curriculum)
    entries = (
        AuditLog.objects.filter(organization=organization, content_type=content_type, object_id=str(plan.id))
        .select_related("user")
        .order_by("-created_at")[:25]
    )
    timeline = []
    for entry in entries:
        new_status = (entry.new_values or {}).get("status") if isinstance(entry.new_values, dict) else None
        timeline.append(
            {
                "who": (entry.user.get_full_name() or entry.user.username) if entry.user_id else "—",
                "when": entry.created_at,
                "what": entry.reason or entry.action,
                "reason": (entry.new_values or {}).get("reason", "") if isinstance(entry.new_values, dict) else "",
                "tone": "success" if new_status == PlanStatus.APPROVED else "info",
            }
        )
    return timeline


def _diff_against_previous(plan, rows) -> dict:
    """Əvvəlki versiya ilə fərq — fənn əsasında (əlavə / çıxarılmış / dəyişmiş)."""
    if plan.previous_version_id is None:
        return {"has_previous": False, "added": [], "removed": [], "changed": []}

    previous = {
        (row.subject_id, row.semester_number): row
        for row in CurriculumSubject.objects.filter(curriculum_id=plan.previous_version_id).select_related("subject")
    }
    current = {(row["subject_id"], row["semester_number"]): row for row in rows}

    added, removed, changed = [], [], []
    for key, row in current.items():
        match = previous.get((uuid.UUID(key[0]), key[1]))
        if match is None:
            added.append(row)
        elif (match.credits, match.total_hours) != (row["credits"], row["total_hours"]):
            changed.append(
                {
                    "subject_code": row["subject_code"],
                    "subject_name": row["subject_name"],
                    "old": f"{match.credits} kr / {match.total_hours} s",
                    "new": f"{row['credits']} kr / {row['total_hours']} s",
                }
            )
    for key, row in previous.items():
        if (str(key[0]), key[1]) not in current:
            removed.append({"subject_code": row.subject.code, "subject_name": row.subject.name})
    return {"has_previous": True, "added": added, "removed": removed, "changed": changed}


def build_curriculum_editor(request, organization) -> dict:
    """«Tədris planı redaktoru» konteksti (bütün seçim URL sorğusundan)."""
    if not can_view_plans(request):
        return {
            "has_access": False,
            "access_denied_message": pgettext(
                _CTX, "Tədris planına baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin."
            ),
        }

    program_id = (request.GET.get("cu_program") or "").strip()
    plan_id = (request.GET.get("cu_plan") or "").strip()
    semester = (request.GET.get("cu_sem") or "").strip()

    plans = plan_options(organization, program_id=program_id)
    plan = None
    if plan_id:
        plan = (
            Curriculum.objects.filter(organization=organization, pk=plan_id)
            .select_related("program", "previous_version")
            .first()
        )
    if plan is None and plans:
        plan = (
            Curriculum.objects.filter(organization=organization, pk=plans[0]["value"])
            .select_related("program", "previous_version")
            .first()
        )

    program_choices = [
        {"value": str(item.id), "label": item.display_label}
        for item in Program.objects.filter(organization=organization, is_archived=False).order_by("name")[:500]
    ]

    payload = {
        "has_access": True,
        "can_edit": can_edit_plans(request),
        "plan_options": plans,
        "program_options": program_choices,
        "chair_options": chair_options(organization),
        "assessment_options": [{"value": value, "label": str(label)} for value, label in AssessmentForm.choices],
        "filters": {"program": program_id, "plan": plan_id, "semester": semester},
        "plan": None,
        "rows": [],
        "balance": plan_balance([]),
        "semesters": [],
        "timeline": [],
        "diff": {"has_previous": False, "added": [], "removed": [], "changed": []},
        "subject_options": [],
    }
    if plan is None:
        payload["table_state"] = "empty"
        return payload

    row_queryset = (
        CurriculumSubject.objects.filter(curriculum=plan)
        .select_related("subject", "teaching_chair")
        .order_by("semester_number", "order", "subject__code")
    )
    all_rows = [_row_payload(row) for row in row_queryset]
    balance = plan_balance(all_rows)

    visible_rows = all_rows
    if semester.isdigit():
        visible_rows = [row for row in all_rows if row["semester_number"] == int(semester)]

    forward = next_transition(plan.status)
    # Düymə GİZLƏNMİR, `disabled` olur (handoff §4): istifadəçi əməlin mövcud
    # olduğunu, sadəcə ONUN səlahiyyətində olmadığını görməlidir. Server yenə də
    # fail-closed yoxlayır (`curriculum_state.resolve` → 403).
    permissions = actor_permissions(request)
    can_advance = bool(forward) and has_permission(permissions, forward.permission)
    can_return = plan.status not in EDITABLE_STATUSES and plan.status != PlanStatus.APPROVED
    if can_return:
        can_return = has_permission(permissions, permission_for("return", plan.status))
    payload.update(
        {
            "plan": {
                "id": str(plan.id),
                "name": plan.name or str(plan),
                "program_label": plan.program.display_label,
                "program_id": str(plan.program_id),
                "admission_year": plan.admission_year,
                "status": plan.status,
                "status_label": plan.get_status_display(),
                "version": plan.version,
                "protocol_number": plan.protocol_number,
                "last_reason": plan.last_reason,
                "is_editable": plan.status in EDITABLE_STATUSES,
                "is_approved": plan.status == PlanStatus.APPROVED,
                "ects_total": plan.program.ects_total,
                "next_action": forward.action if forward else "",
                "next_label": str(_ACTION_LABELS.get(forward.action, "")) if forward else "",
                "can_advance": can_advance,
                "can_return": can_return,
            },
            "rows": visible_rows,
            "all_row_count": len(all_rows),
            "balance": balance,
            "semesters": balance["semesters"],
            "timeline": _timeline(organization, plan),
            "diff": _diff_against_previous(plan, all_rows),
            "table_state": "ready" if visible_rows else "empty",
            "subject_options": [
                {"value": str(item.id), "label": f"{item.code} — {item.name}"}
                for item in Subject.objects.filter(organization=organization, is_archived=False).order_by("code")[:800]
            ],
        }
    )
    return payload


#: Keçid → düymə mətni (state maşınında YOXDUR — orada yalnız qayda var).
_ACTION_LABELS = {
    "submit": pgettext(_CTX, "Kafedra baxışına göndər"),
    "approve_chair": pgettext(_CTX, "Kafedra adından təsdiqlə"),
    "approve_council": pgettext(_CTX, "Fakültə şurası adından təsdiqlə"),
    "approve_office": pgettext(_CTX, "Tədris şöbəsi adından təsdiqlə"),
    "rework": pgettext(_CTX, "Yenidən işlə (qaralamaya qaytar)"),
}


def programs_without_approved_plan(organization) -> list:
    """«Plan yoxdur» bloklayıcıları — TƏSDİQLƏNMİŞ plan meyarı ilə (ekran 07).

    Mərhələ 1-də meyar AKTİV planın mövcudluğu idi; təsdiq zənciri gələndən
    sonra §6.1-ə uyğun olaraq «APPROVED plan yoxdur»a keçir.
    """
    approved = set(
        Curriculum.objects.filter(organization=organization, status=PlanStatus.APPROVED, is_active=True)
        .values_list("program_id", flat=True)
        .distinct()
    )
    return [
        {"id": str(program.id), "label": program.display_label}
        for program in Program.objects.filter(organization=organization, is_archived=False)
        .exclude(pk__in=approved)
        .order_by("name")
    ]


def plan_counts_by_status(organization) -> dict:
    """KPI sırası üçün status bölgüsü (tək sorğu)."""
    rows = (
        Curriculum.objects.filter(organization=organization)
        .values("status")
        .annotate(total=Count("id"))
        .order_by("status")
    )
    return {row["status"]: row["total"] for row in rows}


def plan_hour_totals(plan) -> dict:
    """Planın saat cəmi — semestr açılışında plan/fakt müqayisəsi üçün."""
    return CurriculumSubject.objects.filter(curriculum=plan).aggregate(
        credits=Sum("credits"),
        total_hours=Sum("total_hours"),
        contact=Sum("lecture_hours") + Sum("seminar_hours") + Sum("lab_hours"),
        rows=Count("id", filter=Q(pk__isnull=False)),
    )


__all__ = [
    "plan_in_scope",
    "plan_scope",
    "program_in_scope",
    "unit_in_scope",
    "PERM_EDIT",
    "PERM_VIEW",
    "ROW_ERROR_LABELS",
    "build_curriculum_editor",
    "can_edit_plans",
    "can_view_plans",
    "chair_options",
    "plan_balance",
    "plan_counts_by_status",
    "plan_hour_totals",
    "plan_options",
    "programs_without_approved_plan",
]

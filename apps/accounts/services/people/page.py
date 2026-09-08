"""Şəxs səhifəsi — müəllim / tələbə üçün «Ətraflı» (2026-09-08).

Sahib istəyi: kataloq çekmecəsindən bir kliklə (yeni tabda) şəxsin BÜTÜN vacib
məlumatına baxmaq:

* tələbə — akademik qeyd(lər): ixtisas, qrup, fakültə/kafedra, qəbul ili, kurs,
  təhsil forması (əyani/qiyabi), maliyyələşmə (ödənişli / dövlət sifarişi),
  status; transkript: hər semestrin fənləri, kreditlər, yekun bal, hərf,
  keçdi/kəsildi, KƏSRLƏR (səbəbi ilə: q/b, imtahan 25%), ÜOMG (100 bal);
* müəllim — fakültə/kafedra, vəzifə, iş stajı (ilk üzvlükdən), hansı fənləri
  hansı qruplara, hansı tədris ilində keçir, saat yekunları, rəhbəri olduğu
  bölmələr.

HEÇ BİR yeni səlahiyyət açılmır: hədəf aktorun kataloq əhatəsində olmalıdır
(`assert_in_catalog_scope`), əlaqə/demoqrafiya sahələri `identity_row`-un
icazə qapılarından keçir, tədris siyahısı aktorun struktur əhatəsi ilə süzülür,
akademik qeydlər `scoped_student_records` ilə. Transkript rəqəmləri tələbənin
öz kabinetindəki «Transkript» / «Ümumi tədris məlumatı» ilə EYNİ qurucudan
gəlir (`apps.registrar.transcript`) — burada keçmə/kəsr məntiqi təkrarlanmır.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from core.staff_position import visible_role_label

from .actions import assert_in_catalog_scope, load_target
from .detail import build_detail
from .permissions import PERM_VIEW_TEACHERS
from .rows import resolve_unit_ancestors
from .students import scoped_student_records

_CTX = "accounts.people.page"

FAIL_REASON_LABELS = {
    "qb": pgettext(_CTX, "Davamiyyətdən (q/b)"),
    "exam25": pgettext(_CTX, "İmtahandan (25% təkrar)"),
    "total": pgettext(_CTX, "Nəticə qeyd olunmayıb"),
}

_UNIT_TYPE_LABELS = None


def _unit_type_label(unit_type: str) -> str:
    from apps.organizations.structure_views.registry import unit_type_label

    return unit_type_label(unit_type)


def _years_between(start: date, today: date) -> float:
    days = (today - start).days
    return round(max(days, 0) / 365.25, 1)


# ─── Struktur / üzvlük ──────────────────────────────────────────────────────


def structure_block(target, organization, *, today: date | None = None) -> dict:
    from apps.organizations.models import Membership, OrgUnit

    today = today or timezone.localdate()
    memberships = list(
        Membership.objects.filter(user=target, organization=organization, is_active=True)
        .select_related("role", "scope_unit")
        .order_by("-is_primary", "-role__level", "created_at")
    )
    units = [m.scope_unit for m in memberships if m.scope_unit_id]
    ancestors = resolve_unit_ancestors(units, organization=organization)
    rows = []
    for membership in memberships:
        unit = membership.scope_unit
        chain = ancestors.get(unit.pk, {}) if unit is not None else {}
        rows.append(
            {
                "role": membership.role.name,
                "role_label": visible_role_label(membership.role.name, membership.role.display_name),
                "level": membership.role.level,
                "title": membership.title or "",
                "employee_id": membership.employee_id or "",
                "unit": unit.name if unit is not None else "",
                "unit_type_label": _unit_type_label(unit.unit_type) if unit is not None else "",
                "faculty": chain.get("faculty", "") if unit is not None and unit.unit_type != "faculty" else "",
                "kafedra": (
                    chain.get("kafedra", "")
                    if unit is not None and unit.unit_type not in ("faculty", "chair", "department")
                    else ""
                ),
                "since": membership.created_at.date() if membership.created_at else None,
                "is_primary": bool(membership.is_primary),
            }
        )
    heads = [
        {
            "name": unit.name,
            "type_label": _unit_type_label(unit.unit_type),
            "parent": unit.parent.name if unit.parent_id else "",
        }
        for unit in OrgUnit.objects.filter(organization=organization, is_active=True, head=target)
        .select_related("parent")
        .order_by("level", "name")
    ]
    primary = memberships[0] if memberships else None
    first_unit = units[0] if units else None
    chain = ancestors.get(first_unit.pk, {}) if first_unit is not None else {}
    since = min((m.created_at for m in memberships if m.created_at), default=None)
    faculty = chain.get("faculty", "") if first_unit is not None else ""
    kafedra = chain.get("kafedra", "") if first_unit is not None else ""
    if first_unit is not None:
        if first_unit.unit_type == "faculty":
            faculty = first_unit.name
        elif first_unit.unit_type in ("chair", "department"):
            kafedra = first_unit.name
    return {
        "memberships": rows,
        "heads": heads,
        "title": primary.title if primary is not None else "",
        "employee_id": primary.employee_id if primary is not None else "",
        "faculty": faculty,
        "kafedra": kafedra,
        "since": since.date() if since else None,
        "years": _years_between(since.date(), today) if since else None,
    }


# ─── Tədris (müəllim) ───────────────────────────────────────────────────────


def teaching_block(target, actor, organization, *, request=None) -> dict:
    from apps.registrar.models import CourseOffering

    empty = {
        "years": [],
        "totals": {"offerings": 0, "subjects": 0, "groups": 0, "hours": 0},
        "current": None,
        "restricted": False,
    }
    scope = actor.scope_for(PERM_VIEW_TEACHERS, request=request)
    if not scope.has_structure_access:
        empty["restricted"] = True
        return empty
    offerings = list(
        CourseOffering.objects.filter(organization=organization, instructor=target, is_active=True)
        .filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
        .select_related("subject", "group", "period")
        .order_by("-period__start_date", "subject__name", "group__name")
    )
    years: "OrderedDict[str, dict]" = OrderedDict()
    for offering in offerings:
        period = offering.period
        key = period.year_display if period is not None else ""
        bucket = years.get(key)
        if bucket is None:
            bucket = {
                "label": key or pgettext(_CTX, "Dövr göstərilməyib"),
                "rows": [],
                "hours": 0,
                "subjects": set(),
                "groups": set(),
                "is_current": False,
            }
            years[key] = bucket
        hours = int(offering.lesson_hours or 0)
        bucket["rows"].append(
            {
                "subject_code": offering.subject.code if offering.subject_id else "",
                "subject": offering.subject.name if offering.subject_id else "",
                "group": offering.group.name if offering.group_id else "",
                "period": period.name if period is not None else "",
                "hours": hours,
            }
        )
        bucket["hours"] += hours
        if offering.subject_id:
            bucket["subjects"].add(offering.subject_id)
        if offering.group_id:
            bucket["groups"].add(offering.group_id)
        if period is not None and period.is_current:
            bucket["is_current"] = True
    year_rows = []
    for bucket in years.values():
        year_rows.append(
            {
                "label": bucket["label"],
                "rows": bucket["rows"],
                "hours": bucket["hours"],
                "subjects": len(bucket["subjects"]),
                "groups": len(bucket["groups"]),
                "offerings": len(bucket["rows"]),
                "is_current": bucket["is_current"],
            }
        )
    totals = {
        "offerings": len(offerings),
        "subjects": len({o.subject_id for o in offerings if o.subject_id}),
        "groups": len({o.group_id for o in offerings if o.group_id}),
        "hours": sum(int(o.lesson_hours or 0) for o in offerings),
    }
    current = next((y for y in year_rows if y["is_current"]), year_rows[0] if year_rows else None)
    return {"years": year_rows, "totals": totals, "current": current, "restricted": False}


# ─── Akademik (tələbə) ─────────────────────────────────────────────────────


def _record_rows(records, organization, *, period):
    from .academic import STATUS_LABELS, STATUS_TONES, _course_label

    ancestors = resolve_unit_ancestors([r.group for r in records], organization=organization)
    rows = []
    for record in records:
        chain = ancestors.get(record.group_id, {}) if record.group_id else {}
        rows.append(
            {
                "id": str(record.pk),
                "program": record.program.name if record.program_id else "",
                "program_code": record.program.official_code_pair if record.program_id else "",
                "curriculum": str(record.curriculum) if record.curriculum_id else "",
                "group": record.group.name if record.group_id else "",
                "faculty": chain.get("faculty", ""),
                "kafedra": chain.get("kafedra", ""),
                "admission_year": record.admission_year,
                "course_label": _course_label(record.admission_year, period),
                "status": record.status,
                "status_label": STATUS_LABELS.get(record.status, record.status),
                "status_tone": STATUS_TONES.get(record.status, "info"),
                "education_form": record.education_form,
                "education_form_label": record.get_education_form_display(),
                "funding_type": record.funding_type,
                "funding_label": record.get_funding_type_display(),
                "is_active": bool(record.is_active),
                "athlete_exemption": bool(record.national_athlete_exemption),
            }
        )
    return rows


def _transcript_block(target, organization) -> dict:
    from apps.registrar import transcript as transcript_service

    data = transcript_service.build_student_overall_record(student=target, organization=organization)
    semesters = []
    failures = []
    subjects = passed = failed = pending = 0
    for sem in data.get("semesters", []):
        period = sem["period"]
        rows = []
        for row in sem["rows"]:
            result = row["result"] or {}
            subject = row["subject"]
            status = "passed" if result.get("passed") else ("failed" if result.get("failed") else "pending")
            subjects += 1
            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
            else:
                pending += 1
            entry = {
                "subject_code": getattr(subject, "code", "") or "",
                "subject": getattr(subject, "name", "") or "",
                "credit": row["credit"],
                "teacher": row.get("teacher_name", ""),
                "total": result.get("total") if result.get("graded") else None,
                "letter": result.get("letter") or "",
                "status": status,
                "fail_reason": row.get("fail_reason", ""),
                "fail_reason_label": FAIL_REASON_LABELS.get(row.get("fail_reason", ""), ""),
                "barred": bool(result.get("barred")),
                "in_gpa": bool(row.get("in_gpa")),
                "legacy": bool(row.get("legacy")),
            }
            rows.append(entry)
            if status == "failed":
                failures.append({**entry, "period": period.name, "season": sem.get("season", "")})
        semesters.append(
            {
                "period": period.name,
                "year": period.year_display,
                "season": sem.get("season", ""),
                "rows": rows,
                "credits_earned": sem.get("credits_earned", 0),
                "credits_gpa": sem.get("credits_gpa", 0),
                "gpa": sem.get("gpa"),
                "uomg_available": bool(sem.get("uomg_available")),
                "legacy_notice": sem.get("legacy_check_notice") or sem.get("legacy_missing_notice") or "",
            }
        )
    return {
        "has_record": bool(data.get("has_record")),
        "semesters": semesters,
        "failures": failures,
        "uomg": data.get("overall_uomg"),
        "uomg_available": bool(data.get("overall_uomg_available")),
        "uomg_label": data.get("overall_uomg_label", ""),
        "credits_earned": data.get("total_credits_earned", 0),
        "credits_gpa": data.get("total_credits_gpa", 0),
        "subjects": subjects,
        "passed": passed,
        "failed": failed,
        "pending": pending,
    }


def academic_block(target, actor, organization, *, request=None) -> dict:
    from .academic import _current_period

    scoped = scoped_student_records(actor, request=request)
    if scoped is None:
        return {"records": [], "transcript": None, "restricted": True, "current": None}
    records = list(
        scoped.filter(student=target)
        .select_related("program", "group", "curriculum")
        .order_by("-is_active", "-admission_year")
    )
    period = _current_period(organization)
    rows = _record_rows(records, organization, period=period)
    transcript = _transcript_block(target, organization) if records else None
    return {"records": rows, "transcript": transcript, "restricted": False, "current": rows[0] if rows else None}


# ─── Çekmecə xülasələri ─────────────────────────────────────────────────────


def academic_summary(target, actor, organization, *, request=None) -> dict | None:
    block = academic_block(target, actor, organization, request=request)
    current = block["current"]
    if current is None:
        return None
    transcript = block["transcript"] or {}
    return {
        "program": current["program"],
        "program_code": current["program_code"],
        "group": current["group"],
        "faculty": current["faculty"],
        "kafedra": current["kafedra"],
        "course_label": current["course_label"],
        "education_form_label": current["education_form_label"],
        "funding_label": current["funding_label"],
        "status_label": current["status_label"],
        "uomg": str(transcript["uomg"]) if transcript.get("uomg") is not None else "",
        "uomg_available": bool(transcript.get("uomg_available")),
        "credits_earned": transcript.get("credits_earned", 0),
        "credits_gpa": transcript.get("credits_gpa", 0),
        "failed": transcript.get("failed", 0),
        "subjects": transcript.get("subjects", 0),
    }


def teaching_summary(target, actor, organization, *, request=None, today: date | None = None) -> dict:
    structure = structure_block(target, organization, today=today)
    teaching = teaching_block(target, actor, organization, request=request)
    current = teaching["current"] or {}
    return {
        "faculty": structure["faculty"],
        "kafedra": structure["kafedra"],
        "title": structure["title"],
        "since": structure["since"].isoformat() if structure["since"] else "",
        "years": structure["years"],
        "heads": [h["name"] for h in structure["heads"]],
        "subjects": teaching["totals"]["subjects"],
        "groups": teaching["totals"]["groups"],
        "offerings": teaching["totals"]["offerings"],
        "hours_current": current.get("hours", 0),
        "current_year": current.get("label", ""),
        "restricted": teaching["restricted"],
    }


# ─── Səhifə ────────────────────────────────────────────────────────────────


def page_url_for(user_id) -> str:
    return reverse("accounts:people_person_page", kwargs={"user_id": user_id})


def build_person_page(*, actor, user_id, request=None, today: date | None = None) -> dict:
    """Tam səhifə konteksti. Scope-dan kənar hədəf üçün ``RimAccessError`` atılır."""
    today = today or timezone.localdate()
    target = load_target(actor, user_id)
    catalog = assert_in_catalog_scope(actor, target, request=request)
    organization = actor.organization

    detail = build_detail(actor=actor, user_id=user_id, request=request, today=today)
    person = detail["person"]
    structure = structure_block(target, organization, today=today)
    teaching = teaching_block(target, actor, organization, request=request) if person.get("is_teacher") else None
    academic = academic_block(target, actor, organization, request=request) if catalog == "student" else None

    kpis = []
    if academic is not None:
        transcript = academic["transcript"] or {}
        current = academic["current"] or {}
        uomg = transcript.get("uomg")
        kpis = [
            {
                "label": pgettext(_CTX, "ÜOMG"),
                "value": f"{uomg}" if (uomg is not None and transcript.get("uomg_available")) else "—",
                "note": pgettext(_CTX, "100 bal, kredit-çəkili"),
                "tone": "primary",
            },
            {
                "label": pgettext(_CTX, "Kredit"),
                "value": transcript.get("credits_earned", 0),
                "note": pgettext(_CTX, "qazanılıb / %(total)s qəti") % {"total": transcript.get("credits_gpa", 0)},
            },
            {
                "label": pgettext(_CTX, "Kəsr"),
                "value": transcript.get("failed", 0),
                "tone": "accent-warning" if transcript.get("failed") else "accent-success",
                "note": pgettext(_CTX, "kəsilmiş fənn") if transcript.get("failed") else pgettext(_CTX, "kəsr yoxdur"),
            },
            {
                "label": pgettext(_CTX, "Fənn"),
                "value": transcript.get("subjects", 0),
                "note": pgettext(_CTX, "keçilmiş: %(n)s") % {"n": transcript.get("passed", 0)},
            },
            {
                "label": pgettext(_CTX, "Kurs"),
                "value": current.get("course_label") or "—",
                "note": current.get("education_form_label", ""),
            },
        ]
    elif teaching is not None:
        current = teaching["current"] or {}
        kpis = [
            {
                "label": pgettext(_CTX, "İş stajı"),
                "value": f"{structure['years']:g}" if structure["years"] is not None else "—",
                "unit": pgettext(_CTX, "il") if structure["years"] is not None else "",
                "note": structure["since"].strftime("%d.%m.%Y") if structure["since"] else "",
                "tone": "primary",
            },
            {
                "label": pgettext(_CTX, "Fənn"),
                "value": teaching["totals"]["subjects"],
                "note": pgettext(_CTX, "fərqli fənn"),
            },
            {
                "label": pgettext(_CTX, "Qrup"),
                "value": teaching["totals"]["groups"],
                "note": pgettext(_CTX, "fərqli qrup"),
            },
            {
                "label": pgettext(_CTX, "Açılış"),
                "value": teaching["totals"]["offerings"],
                "note": pgettext(_CTX, "bütün dövrlər"),
            },
            {
                "label": pgettext(_CTX, "Saat"),
                "value": current.get("hours", 0),
                "note": current.get("label", "") or pgettext(_CTX, "cari il"),
            },
        ]

    return {
        "kind": catalog,
        "person": person,
        "capabilities": {
            "can_view_contacts": actor.can_view_contacts,
            "can_view_demographics": actor.can_view_demographics,
        },
        "structure": structure,
        "teaching": teaching,
        "academic": academic,
        "kpis": kpis,
        "organization": organization,
        "catalog_url": f"{reverse('accounts:profile')}?section={'people-students' if catalog == 'student' else 'people-teachers'}",
    }


__all__ = [
    "FAIL_REASON_LABELS",
    "academic_block",
    "academic_summary",
    "build_person_page",
    "page_url_for",
    "structure_block",
    "teaching_block",
    "teaching_summary",
]

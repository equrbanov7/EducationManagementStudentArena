"""Sillabus modulunun PUBLIC fasadı — CONTEXT MÜQAVİLƏSİ.

Növbəti mərhələlər (profil bölmələri, HTTP API, PDF) modulun DAXİLİNƏ girmir:
onlar yalnız buradakı üç context qurucusunu və :mod:`apps.syllabus.services`
funksiyalarını çağırır. Beləliklə UI dəyişəndə domen, domen dəyişəndə UI
sınmır.

⚠️ Bu ekranlar profil bölməsi kimi açılır (mövcud ``SECTION_PARTIALS``
arxitekturası, sol sidebar QALIR) — ayrıca tam-səhifə səth DEYİL. Bölmə
qeydiyyatı 4 yerdə eyni olmalıdır: ``sections_api.SECTION_PARTIALS``,
``AJAX_SAFE_SECTIONS``, ``profile.html`` ``data-ajax-sections`` və
``rbac.allowed_sections``.

──────────────────────────────────────────────────────────────────────────────
1. SİYAHI CONTEXT-i — ``build_syllabus_list_context``
──────────────────────────────────────────────────────────────────────────────
``{
    "syllabi": QuerySet[Syllabus],        # filtr + sıralama tətbiq olunmuş
    "counts": {status: int, "total": int},
    "statuses": [{"key", "label", "tokens": (bg, fg, accent), "next_step"}],
    "filters": {"search", "period", "academic_year", "chair_unit", "statuses", "sort"},
    "sort_keys": tuple[str],              # recent | subject | completion | status
    "can_create": bool,
    "can_review": bool,
}``

2. REDAKTOR CONTEXT-i — ``build_syllabus_editor_context``
``{
    "syllabus": Syllabus, "version": SyllabusVersion,
    "sections": [{"id", "label", "data", "is_complete", "revision"}],  # 10 sətir
    "completion": {"percent": int, "sections": {id: bool}, "issues": [Issue…]},
    "view_state": "normal" | "readonly" | "permission",
    "actions": tuple[str],                # available_actions nəticəsi
    "selfwork_options": {...}, "selfwork_disallowed": {...},
    "teaching_methods": tuple, "plan_hours": {...},
    "history": [timeline event…],
}``

3. TƏSDİQ CONTEXT-i — ``build_review_queue_context``
``{
    "queue": QuerySet[SyllabusVersion],   # SUBMITTED + REVIEW, ən köhnə başda
    "has_scope": bool,                    # False → «əhatə yoxdur» boş vəziyyəti
    "scope_mode": "chair" | "wide" | "noscope",   # yalnız GÖSTƏRİŞ rejimi
    "can_review": bool, "can_approve": bool, "can_revise": bool, "can_reject": bool,
    "coverage": {"group_by", "rows": […], "totals": {…}},
    "trend": [{"key","label","total","approved",…,"percent"}…],
}``

⚠️ ``has_scope`` YALNIZ ``services.has_review_scope``-dan gəlir: icazə açarı
olsa da struktur əhatəsi yoxdursa ekran BOŞ vəziyyət göstərir, bütün təşkilat
AÇILMIR (fail-closed).

──────────────────────────────────────────────────────────────────────────────
ISSUE KODLARI (``completion.Issue.code``) — UI mətnini bu kodlara görə yazır:
``info.teacher_missing``, ``info.office_hours_missing``,
``desc.description_too_short``, ``desc.goal_too_short``,
``out.too_few``, ``out.orphan_outcomes``,
``week.too_few_topics``, ``week.hours_mismatch``, ``week.hours_without_topic``,
``week.topic_without_hours``, ``week.outcome_not_linked``,
``method.too_few``, ``self.option_not_allowed``, ``self.topic_count_mismatch``,
``lit.primary_too_few``, ``lit.additional_too_few``.

KEÇİD XƏTA KODLARI (``TransitionDenied.code``):
``transition.unknown``, ``transition.invalid_source``,
``transition.permission_denied``, ``transition.out_of_scope``,
``transition.author_only``, ``transition.reason_required``,
``transition.incomplete``, ``version.approved_locked``, ``version.locked``,
``version.open_version_exists``, ``version.base_missing``,
``version.kind_unknown``, ``section.unknown``, ``section.conflict``,
``self.option_not_allowed``.

BÖLMƏ MƏZMUN SXEMİ (``SyllabusSection.data``) — bax
``apps.syllabus.services.drafts.BLANK_SECTION_DATA``; ``week`` sətri:
``{"topic": str, "lecture": int, "seminar": int, "lab": int, "outcome": "TN1"}``.
"""

from __future__ import annotations

from . import completion as completion_rules
from .constants import (
    EDITABLE_STATUSES,
    PERM_APPROVE,
    PERM_EDIT,
    PERM_REJECT,
    PERM_REVIEW,
    PERM_REVISE,
    SECTION_ORDER,
    SELFWORK_DISALLOWED,
    SELFWORK_OPTIONS,
    STATUS_NEXT_STEP,
    STATUS_TOKENS,
    TEACHING_METHODS,
    SectionKey,
    SyllabusStatus,
)
from .services import (
    GROUP_CHAIR,
    GROUP_PROGRAM,
    available_actions,
    can_view,
    coverage_report,
    has_review_scope,
    import_migrated_version,
    list_syllabi,
    resolve_actor,
    review_queue,
    section_data_map,
    status_counts,
    version_timeline,
)

#: Status kataloqu — şablon bu siyahını olduğu kimi render edir (7 çip).
STATUS_CATALOG = tuple(
    {
        "key": status.value,
        "label": status.label,
        "tokens": STATUS_TOKENS[status.value],
        "next_step": STATUS_NEXT_STEP[status.value],
    }
    for status in SyllabusStatus
)


def build_syllabus_list_context(
    request,
    *,
    organization,
    period=None,
    academic_year=None,
    chair_unit=None,
    statuses=None,
    search: str = "",
    sort: str = "recent",
) -> dict:
    """«Müəllim — Sillabuslar» bölməsinin context-i."""
    actor = resolve_actor(getattr(request, "user", None), organization, request=request)
    queryset = list_syllabi(
        organization=organization,
        actor=actor,
        period=period,
        academic_year=academic_year,
        chair_unit=chair_unit,
        statuses=statuses,
        search=search,
        sort=sort,
    )
    return {
        "syllabi": queryset,
        "counts": status_counts(queryset),
        "statuses": STATUS_CATALOG,
        "filters": {
            "search": search,
            "period": period,
            "academic_year": academic_year,
            "chair_unit": chair_unit,
            "statuses": list(statuses or []),
            "sort": sort,
        },
        "sort_keys": ("recent", "subject", "completion", "status"),
        "can_create": actor.has(PERM_EDIT),
        "can_review": actor.has(PERM_REVIEW),
    }


def build_syllabus_editor_context(request, *, organization, version) -> dict:
    """«Müəllim — Sillabus redaktoru» bölməsinin context-i (10 bölmə)."""
    actor = resolve_actor(getattr(request, "user", None), organization, request=request)
    syllabus = version.syllabus
    if not can_view(actor, syllabus):
        return {"view_state": "permission", "syllabus": None, "version": None, "sections": []}

    rows = {row.section_id: row for row in version.sections.all()}
    report = completion_rules.evaluate(section_data_map(version), version.plan_hours or {})
    sections = [
        {
            "id": section_id,
            "label": SectionKey(section_id).label,
            "data": (rows[section_id].data if section_id in rows else {}),
            # `prev` / `send` qayda bölməsi deyil — onlar həmişə «yoxlama bölməsi».
            "is_complete": bool(report.sections.get(section_id, True)),
            "is_rule_section": section_id in report.sections,
            "revision": rows[section_id].revision if section_id in rows else 0,
        }
        for section_id in SECTION_ORDER
    ]
    view_state = "normal" if version.status in EDITABLE_STATUSES else "readonly"
    return {
        "syllabus": syllabus,
        "version": version,
        "sections": sections,
        "completion": report.as_dict(),
        "view_state": view_state,
        "actions": available_actions(version=version, actor=actor),
        "selfwork_options": SELFWORK_OPTIONS,
        "selfwork_disallowed": SELFWORK_DISALLOWED,
        "teaching_methods": TEACHING_METHODS,
        "plan_hours": version.plan_hours or {},
        "history": version_timeline(syllabus),
        "statuses": STATUS_CATALOG,
    }


def _scope_mode(actor, report: dict) -> str:
    """«chair» (bir kafedra) vs «wide» (fakültə/universitet) — UI rejimi.

    Bu, İCAZƏ deyil, YALNIZ GÖSTƏRİŞ seçimidir: kafedra müdiri breakdown-u
    təhsil proqramları üzrə, dekan/rektor isə kafedralar üzrə görür. Əhatənin
    özü hər halda ``syllabus.review`` scope-u ilə daralıb.
    """
    if actor.is_superadmin or actor.scope_for(PERM_REVIEW).is_org_wide:
        return "wide"
    return "wide" if len(report["by_chair"]["rows"]) > 1 else "chair"


def _coverage_slice(report: dict, *, group_by: str) -> dict:
    """Hesabatdan UI-nın seçdiyi qruplaşmanı çıxarır (əlavə sorğu YOX)."""
    key = "by_chair" if group_by == GROUP_CHAIR else "by_program"
    return {"coverage": report[key], "trend": report["trend"]}


def build_review_queue_context(
    request,
    *,
    organization,
    chair_unit=None,
    program=None,
    statuses=None,
    search: str = "",
    sort: str = "wait",
    academic_year=None,
) -> dict:
    """«Kafedra müdiri — Sillabus təsdiqi» bölməsinin context-i."""
    actor = resolve_actor(getattr(request, "user", None), organization, request=request)
    if not has_review_scope(actor=actor):
        # Fail-closed: əhatəsi olmayan aktora heç bir sorğu açılmır.
        return {
            "queue": review_queue(organization=organization, actor=actor).none(),
            "has_scope": False,
            "scope_mode": "noscope",
            "can_review": actor.has(PERM_REVIEW),
            "can_approve": False,
            "can_revise": False,
            "can_reject": False,
            "coverage": {"group_by": GROUP_PROGRAM, "rows": [], "totals": {}},
            "trend": [],
            "statuses": STATUS_CATALOG,
        }
    report = coverage_report(organization=organization, actor=actor, academic_year=academic_year)
    mode = _scope_mode(actor, report)
    return {
        "queue": review_queue(
            organization=organization,
            actor=actor,
            chair_unit=chair_unit,
            program=program,
            statuses=statuses,
            search=search,
            sort=sort,
        ),
        "has_scope": True,
        "scope_mode": mode,
        "can_review": actor.has(PERM_REVIEW),
        "can_approve": actor.has(PERM_APPROVE),
        "can_revise": actor.has(PERM_REVISE),
        "can_reject": actor.has(PERM_REJECT),
        **_coverage_slice(report, group_by=(GROUP_CHAIR if mode == "wide" else GROUP_PROGRAM)),
        "statuses": STATUS_CATALOG,
    }


__all__ = [
    "STATUS_CATALOG",
    # ⚠️ İDXAL BORUSUNUN girişi — HTTP səthi DEYİL.  ``import_migrated_version``
    # icazə yoxlamır (bax ``services.drafts`` docstring-i), ona görə yalnız
    # köçürmə fazası / management əmri onu çağıra bilər; view qatı üçün
    # ``create_draft``/``copy_from_previous`` var.  Fasadda olması
    # ``apps.legacy_import``-un modulun DAXİLİNƏ girməməsi üçündür.
    "import_migrated_version",
    "build_review_queue_context",
    "build_syllabus_editor_context",
    "build_syllabus_list_context",
]

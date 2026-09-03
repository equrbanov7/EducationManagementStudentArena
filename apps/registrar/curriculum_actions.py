"""Ekran 05 «Tədris planı» ƏMƏLLƏRİ — tək JSON POST endpoint-i.

Əməllər: plan yarat · sətir yarat/redaktə et · sətri SİL (yalnız qaralamada) ·
status keçidi (göndər / təsdiqlə / qaytar / yenidən işlə) · YENİ VERSİYA.

──────────────────────────────────────────────────────────────────────────────
ÜÇ QAT QAPI
──────────────────────────────────────────────────────────────────────────────
1. tenant — hər sorğu ``request.organization`` ilə filtrlənir (cross-tenant
   id 404 alır, IDOR bağlıdır);
2. icazə — ``curriculum_state.permission_for`` hansı açarın lazım olduğunu
   STATUSA GÖRƏ seçir (kafedra müdiri şuranın qərarını qaytara bilməz);
3. state maşını — ``curriculum_state.resolve`` qeyri-qanuni keçidi **409**,
   təsdiqlənmiş plana yazmanı isə **409 plan_immutable** ilə rədd edir.

SİLMƏ: plan sətri YALNIZ qaralama/qaytarılmış planda silinir — təsdiqlənmiş
plandan heç nə silinmir (§8 qayda 1 + 5). Planın ÖZÜ heç vaxt silinmir: yeni
versiya köhnəni ``is_active=False`` edir və ``previous_version`` ilə bağlayır.

Hər əməl ``core.audit.log_action``-a aktor + timestamp + səbəblə yazılır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from core.audit import log_action
from core.constants import AuditAction

from .curriculum_registry import actor_permissions, can_edit_plans, can_view_plans, plan_balance
from .curriculum_state import PlanTransitionError, assert_editable, resolve
from .models import Curriculum, CurriculumSubject, Program, Subject
from .models.curriculum_meta import AssessmentForm, PlanStatus, expected_total_hours, row_hour_errors

_CTX = "accounts.curriculum"


def _error(message, *, status=400, code="invalid", field=""):
    payload = {"ok": False, "error": code, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def _int_or(value, default, *, low, high):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _chair_unit(organization, unit_id):
    if not unit_id:
        return None
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return OrgUnit.objects.filter(
        organization=organization, is_active=True, pk=unit_id, unit_type__in=("chair", "department")
    ).first()


def _plan(organization, plan_id):
    return Curriculum.objects.filter(organization=organization, pk=(plan_id or "").strip()).first()


def _row_dicts(plan) -> list:
    """Balans hesabı üçün minimal sətir payload-u (registry-dəki ilə eyni açarlar)."""
    rows = []
    for row in CurriculumSubject.objects.filter(curriculum=plan).select_related("subject"):
        rows.append(
            {
                "semester_number": row.semester_number,
                "credits": row.credits,
                "total_hours": row.total_hours,
                "contact_hours": row.lecture_hours + row.seminar_hours + row.lab_hours,
                "selfwork_hours": row.selfwork_hours,
                "lecture_hours": row.lecture_hours,
                "seminar_hours": row.seminar_hours,
                "lab_hours": row.lab_hours,
                "subject_code": row.subject.code,
                "errors": row_hour_errors(
                    credits=row.credits,
                    total_hours=row.total_hours,
                    lecture_hours=row.lecture_hours,
                    seminar_hours=row.seminar_hours,
                    lab_hours=row.lab_hours,
                    selfwork_hours=row.selfwork_hours,
                ),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Plan yaratma
# --------------------------------------------------------------------------- #


def _create_plan(request, organization):
    program = Program.objects.filter(organization=organization, pk=(request.POST.get("program") or "").strip()).first()
    if program is None:
        return _error(pgettext(_CTX, "İxtisas tapılmadı."), status=404, code="not_found", field="program")

    year = _int_or(request.POST.get("admission_year"), 0, low=1990, high=2100)
    if not year:
        return _error(pgettext(_CTX, "Qəbul ili düzgün deyil."), code="bad_year", field="admission_year")

    version = 1 + (
        Curriculum.objects.filter(organization=organization, program=program, admission_year=year)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    )
    try:
        plan = Curriculum.objects.create(
            organization=organization,
            program=program,
            admission_year=year,
            name=(request.POST.get("name") or "").strip()[:255],
            status=PlanStatus.DRAFT,
            version=version,
        )
    except IntegrityError:
        return _error(pgettext(_CTX, "Bu ixtisas və qəbul ili üçün plan artıq mövcuddur."), code="duplicate")

    log_action(
        action=AuditAction.CREATE,
        user=request.user,
        organization=organization,
        obj=plan,
        request=request,
        reason="curriculum: plan created",
        new_values={
            "program": program.display_label,
            "admission_year": year,
            "version": version,
            "status": plan.status,
        },
    )
    return JsonResponse({"ok": True, "id": str(plan.id), "version": version})


# --------------------------------------------------------------------------- #
# Sətir yarat / redaktə et / sil
# --------------------------------------------------------------------------- #


def _save_row(request, organization):
    plan = _plan(organization, request.POST.get("plan"))
    if plan is None:
        return _error(pgettext(_CTX, "Plan tapılmadı."), status=404, code="not_found")
    try:
        assert_editable(plan.status)
    except PlanTransitionError as exc:
        return _error(exc.message, status=exc.http_status, code=exc.code)

    row_id = (request.POST.get("id") or "").strip()
    instance = None
    if row_id:
        instance = CurriculumSubject.objects.filter(curriculum=plan, pk=row_id).first()
        if instance is None:
            return _error(pgettext(_CTX, "Plan sətri tapılmadı."), status=404, code="not_found")

    subject = Subject.objects.filter(organization=organization, pk=(request.POST.get("subject") or "").strip()).first()
    if subject is None:
        return _error(pgettext(_CTX, "Fənn seçilməyib."), code="subject_required", field="subject")

    semester = _int_or(request.POST.get("semester_number"), 0, low=1, high=16)
    if not semester:
        return _error(
            pgettext(_CTX, "Semestr 1–16 aralığında olmalıdır."), code="bad_semester", field="semester_number"
        )

    credits = _int_or(request.POST.get("credits"), 0, low=0, high=60)
    lecture = _int_or(request.POST.get("lecture_hours"), 0, low=0, high=600)
    seminar = _int_or(request.POST.get("seminar_hours"), 0, low=0, high=600)
    lab = _int_or(request.POST.get("lab_hours"), 0, low=0, high=600)
    # Ümumi saat verilməyibsə QANUNİ düsturla doldurulur (kredit × 30) — istifadəçi
    # onu ƏL İLƏ də verə bilər (bayram/qeyri-standart hallar üçün), amma uyğunsuzluq
    # dərhal sətir xətası kimi görünür və təsdiqə göndərməni bloklayır.
    total = _int_or(request.POST.get("total_hours"), expected_total_hours(credits), low=0, high=2000)
    selfwork = _int_or(request.POST.get("selfwork_hours"), max(total - (lecture + seminar + lab), 0), low=0, high=2000)

    assessment = (request.POST.get("assessment_form") or "").strip()
    if assessment not in dict(AssessmentForm.choices):
        assessment = AssessmentForm.EXAM

    is_create = instance is None
    if is_create:
        instance = CurriculumSubject(organization=organization, curriculum=plan)

    old_values = (
        {}
        if is_create
        else {"credits": instance.credits, "total_hours": instance.total_hours, "semester": instance.semester_number}
    )
    instance.subject = subject
    instance.semester_number = semester
    instance.row_code = (request.POST.get("row_code") or "").strip()[:32]
    instance.credits = credits
    instance.total_hours = total
    instance.lecture_hours = lecture
    instance.seminar_hours = seminar
    instance.lab_hours = lab
    instance.selfwork_hours = selfwork
    instance.assessment_form = assessment
    instance.language = (request.POST.get("language") or "").strip()[:8]
    instance.teaching_chair = _chair_unit(organization, (request.POST.get("teaching_chair") or "").strip())
    instance.is_elective = (request.POST.get("is_elective") or "") == "1"
    instance.elective_group = (request.POST.get("elective_group") or "").strip()[:50]
    try:
        instance.save()
    except IntegrityError:
        return _error(pgettext(_CTX, "Bu fənn həmin semestrdə artıq plandadır."), code="duplicate_row", field="subject")

    log_action(
        action=AuditAction.CREATE if is_create else AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=plan,
        request=request,
        reason="curriculum: plan row saved — %s" % subject.code,
        old_values=old_values or None,
        new_values={"subject": subject.code, "semester": semester, "credits": credits, "total_hours": total},
    )
    errors = row_hour_errors(
        credits=credits,
        total_hours=total,
        lecture_hours=lecture,
        seminar_hours=seminar,
        lab_hours=lab,
        selfwork_hours=selfwork,
    )
    return JsonResponse({"ok": True, "id": str(instance.id), "created": is_create, "row_errors": errors})


def _delete_row(request, organization):
    plan = _plan(organization, request.POST.get("plan"))
    if plan is None:
        return _error(pgettext(_CTX, "Plan tapılmadı."), status=404, code="not_found")
    try:
        assert_editable(plan.status)
    except PlanTransitionError as exc:
        return _error(exc.message, status=exc.http_status, code=exc.code)

    row = CurriculumSubject.objects.filter(curriculum=plan, pk=(request.POST.get("id") or "").strip()).first()
    if row is None:
        return _error(pgettext(_CTX, "Plan sətri tapılmadı."), status=404, code="not_found")

    snapshot = {"subject": row.subject.code, "semester": row.semester_number, "credits": row.credits}
    row.delete()
    log_action(
        action=AuditAction.DELETE,
        user=request.user,
        organization=organization,
        obj=plan,
        request=request,
        reason="curriculum: draft plan row removed",
        old_values=snapshot,
    )
    return JsonResponse({"ok": True})


# --------------------------------------------------------------------------- #
# Status keçidi + yeni versiya
# --------------------------------------------------------------------------- #


def _transition(request, organization, action):
    plan = _plan(organization, request.POST.get("plan"))
    if plan is None:
        return _error(pgettext(_CTX, "Plan tapılmadı."), status=404, code="not_found")

    reason = (request.POST.get("reason") or "").strip()
    balance = plan_balance(_row_dicts(plan))
    blocking = bool(balance["warnings"])
    try:
        target = resolve(
            action,
            current_status=plan.status,
            permissions=actor_permissions(request),
            reason=reason,
            has_blocking_warnings=blocking,
        )
    except PlanTransitionError as exc:
        return _error(exc.message, status=exc.http_status, code=exc.code)

    old_status = plan.status
    plan.status = target
    fields = ["status", "last_reason", "updated_at"]
    plan.last_reason = reason
    if action == "submit":
        plan.submitted_at = timezone.now()
        plan.submitted_by = request.user
        fields += ["submitted_at", "submitted_by"]
    if target == PlanStatus.APPROVED:
        plan.approved_at = timezone.now()
        plan.approved_by = request.user
        plan.protocol_number = (request.POST.get("protocol_number") or "").strip()[:64]
        fields += ["approved_at", "approved_by", "protocol_number"]
    plan.save(update_fields=fields)

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=organization,
        obj=plan,
        request=request,
        reason=f"curriculum: {action} — {old_status} → {target}" + (f" — {reason}" if reason else ""),
        old_values={"status": old_status},
        new_values={"status": target, "reason": reason},
    )
    _notify_next_approver(plan, target, actor=request.user)
    return JsonResponse({"ok": True, "status": target})


@transaction.atomic
def _new_version(request, organization):
    """Təsdiqlənmiş plandan YENİ QARALAMA versiya — köhnə plan SİLİNMİR."""
    plan = _plan(organization, request.POST.get("plan"))
    if plan is None:
        return _error(pgettext(_CTX, "Plan tapılmadı."), status=404, code="not_found")
    if plan.status != PlanStatus.APPROVED:
        return _error(
            pgettext(_CTX, "Yeni versiya yalnız təsdiqlənmiş plandan yaradılır."),
            status=409,
            code="not_approved",
        )
    if not can_edit_plans(request):
        return _error(pgettext(_CTX, "Plan redaktəsi üçün səlahiyyətiniz yoxdur."), status=403, code="forbidden")

    next_version = 1 + (
        Curriculum.objects.filter(
            organization=organization, program_id=plan.program_id, admission_year=plan.admission_year
        )
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    )
    clone = Curriculum.objects.create(
        organization=organization,
        program_id=plan.program_id,
        admission_year=plan.admission_year,
        name=plan.name,
        status=PlanStatus.DRAFT,
        version=next_version,
        previous_version=plan,
    )
    CurriculumSubject.objects.bulk_create(
        [
            CurriculumSubject(
                organization=organization,
                curriculum=clone,
                subject_id=row.subject_id,
                semester_number=row.semester_number,
                is_elective=row.is_elective,
                elective_group=row.elective_group,
                required_choices=row.required_choices,
                order=row.order,
                row_code=row.row_code,
                credits=row.credits,
                total_hours=row.total_hours,
                lecture_hours=row.lecture_hours,
                seminar_hours=row.seminar_hours,
                lab_hours=row.lab_hours,
                selfwork_hours=row.selfwork_hours,
                assessment_form=row.assessment_form,
                language=row.language,
                teaching_chair_id=row.teaching_chair_id,
            )
            for row in CurriculumSubject.objects.filter(curriculum=plan)
        ]
    )
    log_action(
        action=AuditAction.CREATE,
        user=request.user,
        organization=organization,
        obj=clone,
        request=request,
        reason="curriculum: new version from approved plan",
        old_values={"source_version": plan.version},
        new_values={"version": next_version, "status": clone.status},
    )
    return JsonResponse({"ok": True, "id": str(clone.id), "version": next_version})


def _notify_next_approver(plan, status, *, actor=None) -> None:
    """Növbəti təsdiqçiyə bildiriş (modul yoxdursa axın DAYANMIR)."""
    titles = {
        PlanStatus.CHAIR_REVIEW: "Tədris planı kafedra baxışına göndərildi",
        PlanStatus.FACULTY_COUNCIL: "Tədris planı fakültə şurasına göndərildi",
        PlanStatus.TEACHING_OFFICE: "Tədris planı Tədris şöbəsinə göndərildi",
        PlanStatus.APPROVED: "Tədris planı təsdiqləndi",
        PlanStatus.RETURNED: "Tədris planı geri qaytarıldı",
    }
    title = titles.get(status)
    if not title:
        return
    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.public import create_notification
    except Exception:  # pragma: no cover — bildiriş modulu yoxdursa keçid pozulmur
        return

    # Alıcı = ixtisasın strukturu üzrə YUXARI gedən zəncirdəki bölmə rəhbərləri
    # (ixtisas → kafedra → fakültə). Rol adına baxılmır: rəhbər kimdirsə, odur.
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    recipients = set()
    unit = getattr(plan.program, "specialty_unit", None)
    while unit is not None:
        if unit.head_id and unit.head_id != getattr(actor, "id", None):
            recipients.add(unit.head)
        unit = OrgUnit.objects.filter(pk=unit.parent_id).select_related("head").first() if unit.parent_id else None

    for recipient in recipients:
        try:
            create_notification(
                recipient=recipient,
                title=title[:255],
                message=f"{plan.program.display_label} · {plan.admission_year} · v{plan.version}",
                link="/accounts/profile/?section=curriculum-editor&cu_plan=%s" % plan.id,
                notification_type=NotificationType.SYSTEM,
                organization=plan.organization,
                metadata={"event": "curriculum_status", "plan_id": str(plan.id), "status": status},
            )
        except Exception:  # pragma: no cover — bildiriş xətası əməli geri qaytarmır
            continue


_TRANSITION_ACTIONS = ("submit", "approve_chair", "approve_council", "approve_office", "return", "rework")

_HANDLERS = {
    "create_plan": _create_plan,
    "save_row": _save_row,
    "delete_row": _delete_row,
    "new_version": _new_version,
}


@login_required
@require_POST
def curriculum_action(request):
    """Tədris planı əməlləri — tək JSON endpoint (`plan.*` qapısı)."""
    organization = getattr(request, "organization", None)
    if organization is None:
        return _error(pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."), status=403, code="no_org")
    if not can_view_plans(request):
        return _error(pgettext(_CTX, "Tədris planına səlahiyyətiniz yoxdur."), status=403, code="forbidden")

    action = (request.POST.get("action") or "").strip()
    if action in _TRANSITION_ACTIONS:
        return _transition(request, organization, action)

    handler = _HANDLERS.get(action)
    if handler is None:
        return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")
    # Yazma əməlləri `plan.edit` tələb edir; status keçidləri isə ÖZ açarını
    # (`curriculum_state.permission_for`) — ona görə yuxarıda ayrılır.
    if not can_edit_plans(request):
        return _error(pgettext(_CTX, "Plan redaktəsi üçün səlahiyyətiniz yoxdur."), status=403, code="forbidden")
    return handler(request, organization)


__all__ = ["curriculum_action"]

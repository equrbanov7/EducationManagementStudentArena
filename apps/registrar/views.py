"""Elektron jurnal — müəllim üzü (U3, UNEC modeli).

Müəllim öz tədris etdiyi offering-lərin siyahısını görür, birini seçib dərs
(``Lesson``) əlavə edir və hər tələbə üçün iştirak/qayıb (iə/qb), seminarda isə
bal yazır. Təhlükəsizlik: ``@login_required`` + hər offering üçün
``_can_edit_journal`` (müəllim / org sahibi / superuser) + tenant-izolyasiya RLS
→ başqa müəllimin/təşkilatın jurnalına giriş yoxdur (IDOR qorunması). Kilid və
klamp servis qatında (``gradebook.save_marks``) yenidən tətbiq olunur.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import finals, grade_audit, gradebook, schedule
from .models import (
    AttendanceStatus,
    CorrectionReason,
    CourseOffering,
    LessonKind,
    SlotKind,
    WeekType,
)


def _current_period(organization):
    """Current AcademicPeriod for the org (app-registry lookup — no static import)."""
    from django.apps import apps as django_apps

    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return (
        AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
        or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
    )


# Redaktə/giriş hüquq köməkçiləri ayrıca modulda (modul-ölçü limiti). Köhnə
# `_can_edit_journal` / `_is_direct_editor` adları geriyə-uyğunluq üçün saxlanılır
# (journal_actions + pdf_views bunları views-dan idxal edir).
from .journal_access import can_edit_journal as _can_edit_journal  # noqa: E402
from .journal_access import is_direct_editor as _is_direct_editor  # noqa: E402
from .journal_access import offering_or_404 as _offering_or_404  # noqa: E402
from .journal_access import schedule_slot_or_404 as _schedule_slot_or_404  # noqa: E402


@login_required
def journal_list(request):
    """The teacher's own offerings — entry points into each journal."""
    from apps.registrar import corrections as corrections_service
    from apps.registrar import page_contexts

    context = page_contexts.journal_list_context(request.user, request=request)
    context["active_main_nav"] = "journal"
    # Korrektorlara (superadmin / journal.correct) düzəliş interfeysinə keçid göstər.
    context["can_correct_journal"] = corrections_service.can_correct_journal(request)
    return render(request, "registrar/journal_list.html", context)


@login_required
def journal_detail(request, offering_id):
    """Lesson-by-lesson journal for one offering: view (GET) + edit (POST).

    Access: the offering instructor / org owner / superuser may edit; the
    corrector (İKT/RİM rəhbəri) may open it for a documented correction.

    TƏSDİQ ZƏNCİRİ YOXDUR (sahibin qərarı, 2026-08): müəllim balı yazır və bitir.
    Jurnalı semestr sonunda RİM toplu BAĞLAYIR — bax
    :mod:`apps.registrar.journal_close`."""
    offering = _offering_or_404(request, offering_id)
    from apps.registrar import corrections as corrections_service

    journal_locked = gradebook.journal_is_locked(offering)
    can_edit_perm = _can_edit_journal(request.user, offering)
    # Birbaşa redaktə (müəllim/sahib/superuser) — korrektor (İKT) DAXİL DEYİL.
    is_direct_editor = _is_direct_editor(request.user, offering)
    can_correct = corrections_service.can_correct_journal(request)
    # Do not leak existence: only editors or correctors (İKT/RİM rəhbəri) may
    # open the page.
    if not can_edit_perm and not can_correct:
        raise Http404
    # Yerində düzəliş rejimi (kilid-aç toggle) — yalnız korrektor + ?correct=1.
    correction_mode = request.method == "GET" and request.GET.get("correct") == "1" and can_correct

    if request.method == "POST":
        action = request.POST.get("action")
        # Birbaşa redaktə əməliyyatları YALNIZ müəllim/sahib/superuser üçün. Korrektor
        # (İKT) buradan keçə bilməz — dəyişikliyi düzəliş rejimi (correction_apply,
        # sənədli) ilə edir. Beləcə düzəliş rejimi aktiv olmadan heç nə dəyişmir.
        if not is_direct_editor:
            raise Http404
        if action == "add_lesson":
            return _handle_add_lesson(request, offering)
        if action == "save_finals":
            return _handle_save_finals(request, offering)
        if action == "save_components":
            return _handle_save_components(request, offering)
        if action == "save_component_scores":
            return _handle_save_component_scores(request, offering)
        if action == "publish":
            raise Http404
        return _handle_save_marks(request, offering)

    import datetime as _dt

    from django.utils import timezone as _tz

    from apps.registrar import journal_close_notices, journal_extras

    journal = gradebook.get_offering_journal(offering=offering, newest_first=True)
    corrections_map = corrections_service.corrections_map_for_offering(offering)
    coursework_rows = journal_extras.get_course_work_rows(offering)
    finals_data = finals.get_offering_results(offering=offering)
    work_by_enrollment = {row["enrollment"].id: row["work"] for row in coursework_rows}
    for row in finals_data["rows"]:
        row["coursework"] = work_by_enrollment.get(row["enrollment"].id)

    today = _tz.localdate()
    today_parity = schedule.week_parity(offering.period, today - _dt.timedelta(days=today.weekday()))

    context = {
        "offering": offering,
        "journal": journal,
        "corrections_map": corrections_map,
        "finals": finals_data,
        "final_breakdown": journal_extras.get_final_breakdown(offering),
        "kollokvium_grid": journal_extras.get_kollokvium_grid(offering),
        "selfwork_board": journal_extras.get_selfwork_board(offering),
        "coursework_rows": coursework_rows,
        "org_rubrics": _org_rubrics(offering.organization),
        "can_edit": is_direct_editor and not journal_locked,
        "journal_locked": journal_locked,
        # RİM xəbərdarlığı — kollokvium lenti ilə EYNİ dizayn (jd2-kmarquee).
        "journal_close_notice": journal_close_notices.journal_banner(offering, today),
        "grade_history": grade_audit.get_grade_history(offering=offering),
        "lesson_kinds": LessonKind.choices,
        "locked_lesson_kind": journal_extras.locked_lesson_kind(offering),
        "topic_choices": journal_extras.lesson_topic_choices(offering),
        "topic_choices_meta": journal_extras.lesson_topic_meta(offering, journal["lessons"]),
        "calendar_plan": journal_extras.calendar_plan(offering, journal["lessons"], today),
        "standard_times": schedule.STANDARD_LESSON_TIMES,
        "seminar_score_options": list(range(0, 11)),
        "kollokvium_score_options": list(range(0, journal_extras.KOLLOKVIUM_MAX + 1)),
        "today_parity": today_parity,
        "active_main_nav": "journal",
        "correction_mode": correction_mode,
        "can_correct_journal": can_correct,
        "can_override_lessons": bool(
            getattr(request.user, "is_superuser", False) or getattr(request.user, "is_ikt_rehber", False)
        ),
        # Korrektor-only (İKT): dərs modalında PDF sahələri HƏMİŞƏ tələb olunur.
        "is_corrector_only": can_correct and not is_direct_editor,
        "correction_reasons": CorrectionReason.choices,
        # #7/#8/#9 keçirilmiş saat + növ-müəllimləri; dərs modalı üçün müəllim seçimləri.
        "teaching_summary": journal_extras.journal_teaching_summary(offering),
        "lesson_teacher_choices": journal_extras.lesson_teacher_choices(offering),
    }
    if correction_mode:
        # Yerində düzəliş rejimi: audited correction editoru üçün kontekst
        # (journal + corrections_map include_document ilə əvəzlənir).
        from apps.registrar.correction_views import build_correction_context

        context.update(build_correction_context(offering, request))
    else:
        # Normal görünüş: sərbəst iş/kurs işi/kollokvium düzəlişləri də sarı + tarixçə.
        from apps.registrar import item_corrections

        context.update(item_corrections.annotate_normal_view(offering, context))
    return render(request, "registrar/journal_detail.html", context)


def _org_rubrics(organization):
    """Aktiv rubrik şablonları (komponent formasındakı select üçün, U22)."""
    from apps.registrar.models import Rubric

    return list(Rubric.objects.filter(organization=organization, is_active=True).order_by("name"))


@login_required
def rubric_grade_view(request, offering_id, component_id):
    """Meyar-meyar (rubrik) qiymətləndirmə səhifəsi (U22).

    Giriş jurnal detalı ilə eynidir; cədvəl = tələbələr (sətir) × meyarlar
    (sütun). Yazılan meyar cəmi komponent balına köçürülür (kilid + audit
    servis qatında)."""
    from apps.registrar import rubrics as rubrics_service
    from apps.registrar.models import AssessmentComponent

    offering = _offering_or_404(request, offering_id)
    # Rubrik kriteriya balları ComponentScore yazır → yalnız birbaşa redaktor (İKT yox).
    if not _is_direct_editor(request.user, offering):
        raise Http404
    component = get_object_or_404(AssessmentComponent, pk=component_id, offering=offering)
    grid = rubrics_service.get_rubric_grid(component)
    if grid is None:
        messages.warning(request, _("Bu komponentə rubrik qoşulmayıb."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]) + "#tab-components")

    if request.method == "POST":
        from django.core.exceptions import ValidationError

        entries = []
        for key, raw in request.POST.items():
            if not key.startswith("rpoints__"):
                continue
            parts = key.split("__")
            if len(parts) != 3:
                continue
            _prefix, criterion_id, enrollment_id = parts
            entries.append({"criterion_id": criterion_id, "enrollment_id": enrollment_id, "points": raw})
        try:
            written = rubrics_service.save_criterion_scores(component=component, entries=entries, by_user=request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect(reverse("registrar:rubric_grade", args=[offering.pk, component.pk]))
        if written or entries:
            messages.success(request, _("Rubrik balları yadda saxlanıldı."))
        return redirect(reverse("registrar:rubric_grade", args=[offering.pk, component.pk]))

    return render(
        request,
        "registrar/rubric_grade.html",
        {
            "offering": offering,
            "component": component,
            "grid": grid,
            "can_edit": not gradebook.journal_is_locked(offering),
            "active_main_nav": "journal",
        },
    )


def _handle_save_components(request, offering):
    """Define/upsert the offering's assessment components (name + max_score)."""
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — komponent redaktəsi bağlıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    definitions = []
    index = 0
    while f"comp_name__{index}" in request.POST:
        definitions.append(
            {
                "id": request.POST.get(f"comp_id__{index}") or None,
                "name": request.POST.get(f"comp_name__{index}"),
                "max_score": request.POST.get(f"comp_max__{index}"),
                "rubric_id": request.POST.get(f"comp_rubric__{index}") or None,
            }
        )
        index += 1
    gradebook.save_components(offering=offering, definitions=definitions, by_user=request.user)
    messages.success(request, _("Qiymətləndirmə komponentləri yadda saxlanıldı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_save_component_scores(request, offering):
    """Persist per-(component, enrollment) component scores (cscore__C__E keys)."""
    entries = []
    for key, raw in request.POST.items():
        if not key.startswith("cscore__"):
            continue
        parts = key.split("__", 2)
        if len(parts) != 3:
            continue
        _prefix, component_id, enrollment_id = parts
        entries.append({"component_id": component_id, "enrollment_id": enrollment_id, "score": raw})
    written = gradebook.save_component_scores(offering=offering, entries=entries, by_user=request.user)
    messages.success(request, _("Komponent balları yadda saxlanıldı (%(n)s xana).") % {"n": written})
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_save_finals(request, offering):
    """Persist final-exam + resit scores per student (exam__<enr> / resit__<enr>)."""
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — nəticə redaktəsi bağlıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    enrollments = {str(e.id): e for e in offering.enrollments.all()}
    extras: dict = {}
    for key, raw in request.POST.items():
        if key.startswith("exam__"):
            enrollment = enrollments.get(key[len("exam__") :])
            if enrollment is not None:
                finals.set_exam_score(enrollment=enrollment, score=raw, by_user=request.user)
        elif key.startswith("resit__"):
            enrollment = enrollments.get(key[len("resit__") :])
            if enrollment is not None and raw.strip() != "":
                finals.set_resit_score(enrollment=enrollment, score=raw, by_user=request.user)
        elif key.startswith("bonus__"):
            enrollment = enrollments.get(key[len("bonus__") :])
            if enrollment is not None:
                extras.setdefault(enrollment.id, {"enrollment": enrollment})["bonus"] = raw or "0"
        elif key.startswith("fcomment__"):
            enrollment = enrollments.get(key[len("fcomment__") :])
            if enrollment is not None:
                extras.setdefault(enrollment.id, {"enrollment": enrollment})["comment"] = raw
    # Bonus/cərimə + rəy (U15) — bal daxil edilməsindən SONRA yazılır ki,
    # evaluate_resit yekun vəziyyəti bonuslu total ilə görsün.
    for data in extras.values():
        finals.set_final_extras(
            enrollment=data["enrollment"],
            bonus=data.get("bonus"),
            comment=data.get("comment"),
            by_user=request.user,
        )
    messages.success(request, _("Yekun nəticələr yadda saxlanıldı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_add_lesson(request, offering):
    """Create a new lesson column (date + type + topic + standart dərs saatı)."""
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — dərs əlavə etmək olmaz."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    date = request.POST.get("lesson_date") or None
    # Dərs tipi kilidi: cədvəldə tək növ slot varsa POST nə deyirsə desin o növ.
    from apps.registrar import journal_extras as _je

    kind = _je.locked_lesson_kind(offering) or request.POST.get("lesson_kind")
    if kind not in dict(LessonKind.choices):
        kind = LessonKind.LECTURE
    if not date:
        messages.error(request, _("Dərs tarixi tələb olunur."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    hours_raw = (request.POST.get("lesson_hours") or "").strip()
    hours = int(hours_raw) if hours_raw.isdigit() and int(hours_raw) > 0 else None
    start_time, end_time = schedule.parse_time_slot(request.POST.get("lesson_time"))
    # Dərs saatı MƏCBURİDİR — standart saat seçilmədən dərs açılmasın.
    if not start_time or not end_time:
        messages.error(request, _("Dərs saatı seçilməlidir — standart dərs saatlarından birini seçin."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    # #6 — fənnin tam saat həddi: keçirilmiş + yeni saat toplamı keçməsin (60→62 olmaz).
    summary = _je.journal_teaching_summary(offering)
    if summary["total"] and summary["held_total"] + (hours or gradebook.DEFAULT_LESSON_HOURS) > summary["total"]:
        messages.error(
            request,
            _("Fənnin dərs saatı həddi (%(t)s saat) keçilir — keçirilmiş %(h)s saat, qalan yalnız %(r)s saat.")
            % {"t": summary["total"], "h": summary["held_total"], "r": summary["remaining"]},
        )
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    # #9 — bu dərsin müəllimi (fənn 2 müəllim arasında bölünübsə); boşdursa açılışınkı.
    instructor = None
    _inst_id = (request.POST.get("lesson_instructor") or "").strip()
    if _inst_id:
        from django.contrib.auth import get_user_model

        instructor = get_user_model().objects.filter(pk=_inst_id).first()

    # İKT/RİM Rəhbəri / superuser keçmiş tarixə də dərs aça bilər (tam override).
    allow_past = bool(getattr(request.user, "is_superuser", False) or getattr(request.user, "is_ikt_rehber", False))
    try:
        lesson = gradebook.create_lesson(
            offering=offering,
            date=date,
            kind=kind,
            topic=(request.POST.get("lesson_topic") or "").strip(),
            hours=hours,
            start_time=start_time,
            end_time=end_time,
            created_by=request.user,
            instructor=instructor,
            allow_past=allow_past,
        )
        if allow_past:  # geriyə-dönük sütun audit izinə düşür (2026-08 auditi)
            grade_audit.log_backdated_lesson(offering=offering, lesson=lesson, by_user=request.user)
        messages.success(request, _("Dərs əlavə edildi."))
    except gradebook.LessonRuleError as exc:
        messages.error(request, str(exc))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_save_marks(request, offering):
    """Parse editable grid cells → save_marks.

    Yeni format (üç-vəziyyətli çip): ``att__L__E`` = '' | present | absent —
    boş dəyər GÖNDƏRİLMİR/yazılmır (müəllim toxunmadığı xana işarə almır).
    Köhnə format (cell__/absent__) geriyə-uyğunluq üçün saxlanır."""
    entries = []
    tri_state = any(key.startswith("att__") for key in request.POST)
    if tri_state:
        for key, raw in request.POST.items():
            if not key.startswith("att__"):
                continue
            parts = key.split("__", 2)
            if len(parts) != 3:
                continue
            _prefix, lesson_id, enrollment_id = parts
            score = request.POST.get(f"score__{lesson_id}__{enrollment_id}")
            if raw not in (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT):
                # Bal yazılıbsa iştirak öz-özünə bəllidir (i/e) — ayrıca işarə lazım deyil.
                if (score or "").strip():
                    raw = AttendanceStatus.PRESENT
                else:
                    continue  # boş xana — işarə yazılmır
            entries.append({"lesson_id": lesson_id, "enrollment_id": enrollment_id, "status": raw, "score": score})
    else:
        for key in request.POST:
            if not key.startswith("cell__"):
                continue
            parts = key.split("__", 2)
            if len(parts) != 3:
                continue
            _prefix, lesson_id, enrollment_id = parts
            absent = f"absent__{lesson_id}__{enrollment_id}" in request.POST
            entries.append(
                {
                    "lesson_id": lesson_id,
                    "enrollment_id": enrollment_id,
                    "status": AttendanceStatus.ABSENT if absent else AttendanceStatus.PRESENT,
                    "score": request.POST.get(f"score__{lesson_id}__{enrollment_id}"),
                }
            )

    written = gradebook.save_marks(offering=offering, entries=entries, by_user=request.user)
    messages.success(request, _("Jurnal yadda saxlanıldı (%(n)s xana).") % {"n": written})
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


# ── Dərs cədvəli (timetable, U4) ─────────────────────────────────────────────


@login_required
def schedule_view(request):
    """Role-aware weekly timetable: student → group schedule, teacher → own slots.

    Teachers/org-owners may add slots for the offerings they teach (conflicts are
    rejected in the service). Tenant scoping comes from the active-org RLS context.
    Context building is shared with the profile cabinet section (page_contexts)."""
    from apps.registrar import page_contexts

    organization = getattr(request, "organization", None)
    if organization is None:
        return render(request, "registrar/schedule.html", {"has_context": False, "active_main_nav": "schedule"})

    if request.method == "POST":
        return _handle_add_slot(request, organization, _current_period(organization))

    context = page_contexts.schedule_context(request, organization)
    context["active_main_nav"] = "schedule"
    return render(request, "registrar/schedule.html", context)


def _redirect_after_schedule(request):
    """Redirect back to the caller: the profile shell (`next`, same-host only)
    or the standalone schedule page. Keeps the sidebar context after slot POSTs."""
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(nxt)
    return redirect(reverse("registrar:schedule"))


def _handle_add_slot(request, organization, period):
    offering = (
        CourseOffering.objects.filter(pk=request.POST.get("offering_id"), organization=organization)
        .select_related("organization")
        .first()
    )
    if offering is None or not _is_direct_editor(request.user, offering):
        raise Http404  # only the teaching instructor / org owner may schedule (NOT the corrector)

    from django.utils.dateparse import parse_time

    try:
        weekday = int(request.POST.get("weekday") or 0)
    except (TypeError, ValueError):
        weekday = 0
    # Standart dərs saatı seçimi (üstünlük); köhnə sərbəst vaxt sahələri fallback.
    start_time, end_time = schedule.parse_time_slot(request.POST.get("time_slot"))
    if start_time is None:
        start_time = parse_time(request.POST.get("start_time") or "")
        end_time = parse_time(request.POST.get("end_time") or "")
    week_type = request.POST.get("week_type")
    if week_type not in dict(WeekType.choices):
        week_type = WeekType.ALL
    slot_kind = request.POST.get("slot_kind")
    if slot_kind not in dict(SlotKind.choices):
        slot_kind = SlotKind.LECTURE
    if not (1 <= weekday <= 7) or start_time is None or end_time is None or start_time >= end_time:
        messages.error(request, _("Gün və düzgün başlama/bitmə vaxtı tələb olunur."))
        return _redirect_after_schedule(request)

    try:
        schedule.create_slot(
            offering=offering,
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
            room=(request.POST.get("room") or "").strip(),
            week_type=week_type,
            kind=slot_kind,
            created_by=request.user,
        )
        messages.success(request, _("Dərs cədvəlinə slot əlavə edildi."))
    except schedule.ScheduleConflict as exc:
        clash = exc.conflict
        messages.error(
            request,
            _("Konflikt: bu vaxt %(subject)s ilə üst-üstə düşür (qrup/müəllim/otaq).")
            % {"subject": clash.offering.subject.code},
        )
    return _redirect_after_schedule(request)


@login_required
def schedule_slot_delete(request, slot_id):
    """Delete a slot (only the teaching instructor / org owner / superuser)."""
    slot = _schedule_slot_or_404(request, slot_id)
    if request.method == "POST" and _is_direct_editor(request.user, slot.offering):
        slot.delete()
        messages.success(request, _("Slot silindi."))
    return _redirect_after_schedule(request)


# ── Akademik təqvim (U11) ────────────────────────────────────────────────────


@login_required
def calendar_view(request):
    """Academic calendar: semesters with their registration + exam-session windows.

    Read-only and open to every authenticated member of the active organization
    (students plan around these dates as much as staff). Window editing lives in
    the AcademicPeriod admin — tenant-configurable, per the variable-structure rule."""
    from apps.registrar import page_contexts

    organization = getattr(request, "organization", None)
    if organization is None:
        return render(request, "registrar/calendar.html", {"has_context": False, "active_main_nav": "calendar"})

    context = page_contexts.calendar_context(organization)
    context["active_main_nav"] = "calendar"
    return render(request, "registrar/calendar.html", context)


# The registrar console (K3) views live in ``apps.registrar.console_views`` to
# keep this module focused (journal + timetable) and under the size budget.

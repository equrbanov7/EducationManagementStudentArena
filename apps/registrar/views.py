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
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import finals, grade_audit, gradebook, journal_scope, legacy_excuse, lesson_rooms, schedule
from .models import AttendanceStatus, CorrectionReason, LessonKind


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
from .journal_access import can_observe_journal as _can_observe_journal  # noqa: E402
from .journal_access import is_direct_editor as _is_direct_editor  # noqa: E402
from .journal_access import offering_or_404 as _offering_or_404  # noqa: E402


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
    from apps.registrar import guest_roster

    journal_locked = gradebook.journal_is_locked(offering)
    can_edit_perm = _can_edit_journal(request.user, offering)
    # Birbaşa redaktə (müəllim/sahib/superuser) — korrektor (İKT) DAXİL DEYİL.
    is_direct_editor = _is_direct_editor(request.user, offering)
    can_correct = corrections_service.can_correct_journal(request)
    # Jurnal SİYAHISININ idarəsi (alt qrupdan əlavə/geri götürmə) — koordinator/
    # dekanlıq. Onlar müəllim deyil: jurnalı OXU rejimində açırlar, xanaya
    # toxuna bilmirlər (POST aşağıda `is_direct_editor` ilə kəsilir).
    # İCAZƏ (səhifəni aça bilirmi) ilə ƏMƏL (siyahını dəyişə bilirmi) AYRIDIR:
    # bağlanmış jurnal / keçmiş dövr koordinatoru səhifədən qovmur (tarixçəni
    # oxuya bilir), amma «alt qrupdan əlavə et» səthini tamamilə gizlədir.
    roster_scope = guest_roster.can_manage_offering_roster(request.user, offering)
    can_manage_roster = roster_scope and guest_roster.roster_is_open(offering)
    # Təhvil verən köhnə müəllim: AÇIR, yazmır (bax journal_access şərhi).
    handover_observer = _can_observe_journal(request.user, offering)
    # Səhifəni yalnız redaktor / korrektor / siyahı idarəçisi / köhnə müəllim açır.
    if not can_edit_perm and not can_correct and not roster_scope and not handover_observer:
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

    from apps.registrar import journal_close_notices, journal_extras, journal_policy, syllabus_notice

    journal = gradebook.get_offering_journal(offering=offering, newest_first=True)
    corrections_map = corrections_service.corrections_map_for_offering(offering)
    legacy_excuse.attach_to_offering_journal(offering, journal, corrections_map)  # sarı üq sənədi
    coursework_rows = journal_extras.get_course_work_rows(offering)
    finals_data = finals.get_offering_results(offering=offering)
    work_by_enrollment = {row["enrollment"].id: row["work"] for row in coursework_rows}
    # Çox cəhd (sahibin qərarı M2): rəsmi SONUNCU cəhddir, əvvəlkilərin balı
    # itmir — müəllim görünüşündə «Yekun» tabının QEYD sütununda açıq göstərilir.
    from apps.registrar import exam_attempt_history

    # Toplu oxu (tək sorğu) — sətir-sətir ``attempt_rows_for_enrollment``
    # 555 tələbəli açılışda 555 sorğu edirdi (2026-09-02 performans ölçməsi).
    attempts_by_student = exam_attempt_history.attempt_rows_by_student(
        student_ids=[row["enrollment"].student_id for row in finals_data["rows"]],
        subject_id=offering.subject_id,
        organization=offering.organization,
    )
    attempts_map = {
        row["enrollment"].id: attempts_by_student.get(row["enrollment"].student_id, []) for row in finals_data["rows"]
    }
    for row in finals_data["rows"]:
        row["coursework"] = work_by_enrollment.get(row["enrollment"].id)
        row["attempts"] = attempts_map.get(row["enrollment"].id, [])

    today = _tz.localdate()
    today_parity = schedule.week_parity(offering.period, today - _dt.timedelta(days=today.weekday()))
    rooms = lesson_rooms.lesson_room_choices(offering)
    syllabus_gate = journal_policy.syllabus_gate(offering)

    context = {
        "offering": offering,
        "journal": journal,
        "corrections_map": corrections_map,
        "finals": finals_data,
        "final_breakdown": _with_attempts(journal_extras.get_final_breakdown(offering), attempts_map),
        "kollokvium_grid": journal_extras.get_kollokvium_grid(offering),
        "selfwork_board": journal_extras.get_selfwork_board(offering),
        "coursework_rows": coursework_rows,
        "org_rubrics": _org_rubrics(offering.organization),
        "can_edit": is_direct_editor and not journal_locked and not syllabus_gate["locked"],
        "handover_observer": handover_observer,
        "journal_locked": journal_locked,
        # RİM xəbərdarlığı — kollokvium lenti ilə EYNİ dizayn (jd2-kmarquee).
        "journal_close_notice": journal_close_notices.journal_banner(offering, today),
        # Sillabus vəziyyəti: xəbərdarlıq zolağı + «Sillabusa bax» keçidi.
        # ⚠️ Jurnalı KİLİDLƏMİR — yalnız məlumat verir (bax syllabus_notice.py).
        "syllabus_notice": syllabus_notice.journal_syllabus_notice(offering),
        # README §8/2 qapısı — ORG SİYASƏTİ (default söndürülü).  Açıq olduqda
        # təsdiqlənmiş sillabusu olmayan jurnal YALNIZ-OXU olur (`can_edit`
        # yuxarıda söndürülür) və panel kilid + CTA göstərir.
        "syllabus_gate": syllabus_gate,
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
        # «Alt qrupdan tələbə əlavə et» düyməsi + sətir çipindəki geri götürmə.
        # Kilidli/keçmiş dövrdə False → düymə, modal və JS yüklənmir; «alt qrup»
        # çipi isə oxu-rejimində qalır (bax _jd_grid.html).
        "can_manage_roster": can_manage_roster,
        # Əhatəsi var, amma jurnal dondurulub — səbəbi göstərmək üçün.
        "roster_frozen_reason": guest_roster.roster_block_reason(offering) if roster_scope else "",
        "can_override_lessons": bool(
            getattr(request.user, "is_superuser", False) or getattr(request.user, "is_ikt_rehber", False)
        ),
        # Korrektor-only (İKT): dərs modalında PDF sahələri HƏMİŞƏ tələb olunur.
        "is_corrector_only": can_correct and not is_direct_editor,
        "correction_reasons": CorrectionReason.choices,
        # #7/#8/#9 keçirilmiş saat + növ-müəllimləri; dərs modalı üçün müəllim seçimləri.
        "teaching_summary": journal_extras.journal_teaching_summary(offering),
        "lesson_teacher_choices": journal_extras.lesson_teacher_choices(offering),
        # Dərs otağı: korpus (bina) → otaq kaskadı. Korpus ayrıca model deyil,
        # otağın öz sahəsidir; siyahı kiçik olduğu üçün modala JSON kimi düşür.
        "lesson_rooms": rooms,
        "lesson_buildings": lesson_rooms.lesson_building_choices(rooms),
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


def _with_attempts(breakdown, attempts_map):
    """«Yekun» tabının sətirlərinə rəqəmsal cəhd tarixçəsini qoş (M2).

    ``journal_extras.get_final_breakdown`` modul-ölçü budcəsinin tam həddindədir,
    ona görə qoşma burada — view qatında — edilir (hesablama dəyişmir)."""
    for row in breakdown.get("rows", []):
        row["attempts"] = attempts_map.get(row["enrollment"].id, [])
    return breakdown


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


def _can_write_finals(user, offering) -> bool:
    """Yekun imtahan / təkrar balı — YALNIZ `final_score.entry` daşıyan aktor (İmtahan
    Mərkəzi) və ya superuser.  Müəllim jurnal redaktoru olsa da bu sahəni yazmır
    (UI-da sahə yoxdur; crafted POST ilə yazıla bilirdi — QA 2026-09-05 JOURNAL-TEACHER-08)."""
    if getattr(user, "is_superuser", False):
        return True
    scope = journal_scope.permission_scope_for(user, offering.organization, "final_score.entry")
    return scope.has_structure_access


def _handle_save_finals(request, offering):
    """Yekun imtahan/təkrar balı (exam__/resit__) + bonus-rəy (bonus__/fcomment__).

    Bal sahəsi `final_score.entry` tələb edir (İmtahan Mərkəzi); bonus/rəy (U15)
    isə jurnal redaktorunundur. Ona görə icazəsiz aktorda bütün əməl 404 olmur —
    yalnız bal açarları nəzərə alınmır (QA 2026-09-05 JOURNAL-TEACHER-08).
    """
    can_write_scores = _can_write_finals(request.user, offering)
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — nəticə redaktəsi bağlıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    enrollments = {str(e.id): e for e in offering.enrollments.all()}
    extras: dict = {}
    refused_scores = False
    for key, raw in request.POST.items():
        if key.startswith("exam__"):
            if not can_write_scores:
                refused_scores = True
                continue
            enrollment = enrollments.get(key[len("exam__") :])
            if enrollment is not None:
                finals.set_exam_score(enrollment=enrollment, score=raw, by_user=request.user)
        elif key.startswith("resit__"):
            if not can_write_scores:
                refused_scores = True
                continue
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
    if refused_scores:
        messages.warning(request, _("İmtahan/təkrar balını yalnız İmtahan Mərkəzi yaza bilər — bu sahələr yazılmadı."))
    else:
        messages.success(request, _("Yekun nəticələr yadda saxlanıldı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_add_lesson(request, offering):
    """Create a new lesson column (date + type + topic + standart dərs saatı)."""
    # README §8/2 — siyasət açıqdırsa təsdiqlənmiş sillabussuz dərs açılmır:
    # 403 + SƏBƏB KODU (mesaj/redirect deyil, çünki qayda acceptance şərtidir).
    from apps.registrar import journal_policy

    gate = journal_policy.syllabus_gate(offering)
    if gate["locked"]:
        return HttpResponseForbidden(gate["reason_code"], content_type="text/plain; charset=utf-8")
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
    if summary["total"] and summary["scheduled_total"] + (hours or gradebook.DEFAULT_LESSON_HOURS) > summary["total"]:
        messages.error(
            request,
            _("Fənnin dərs saatı həddi (%(t)s saat) keçilir — keçirilmiş %(h)s saat, qalan yalnız %(r)s saat.")
            % {"t": summary["total"], "h": summary["scheduled_total"], "r": summary["remaining"]},
        )
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    # #9 — bu dərsin müəllimi (fənn 2 müəllim arasında bölünübsə); boşdursa açılışınkı.
    instructor = None
    _inst_id = (request.POST.get("lesson_instructor") or "").strip()
    if _inst_id:
        # Yeniləmə yolu ilə EYNİ həlledici: tip + təşkilat/rol yoxlaması (etibarsız
        # id və ya tələbə id-si əvvəl 500 ValueError/IntegrityError verirdi —
        # QA 2026-09-05 JOURNAL-TEACHER-02). Call-time import: journal_actions
        # views-dən idxal edir.
        from .journal_actions import _resolve_instructor

        try:
            instructor = _resolve_instructor(offering, _inst_id)
        except Http404:
            messages.error(request, _("Seçilmiş müəllim bu təşkilatın tədris heyətində deyil."))
            return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    # Dərsin otağı (opsional) — korpus yalnız UI süzgəcidir, saxlanan dəyər otaqdır.
    # Otaq təşkilat daxilində həll olunur: başqa tenant-ın otağı keçmir.
    room = lesson_rooms.resolve_lesson_room(offering.organization, request.POST.get("lesson_room"))

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
            room=room,
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

    if gradebook.journal_is_locked(offering):
        # Əvvəl «Jurnal yadda saxlanıldı (0 xana)» UĞUR mesajı gedirdi (QA 2026-09-05
        # JOURNAL-TEACHER-04) — kilidli jurnala yazı səssiz atılmamalıdır.
        messages.error(request, _("Jurnal bağlıdır — dəyişikliklər yazılmadı."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
    written = gradebook.save_marks(offering=offering, entries=entries, by_user=request.user)
    if entries and not written:
        messages.warning(request, _("Heç bir xana yazılmadı — dərs günü qaydası və ya xana kilidi buna imkan vermədi."))
    else:
        messages.success(request, _("Jurnal yadda saxlanıldı (%(n)s xana).") % {"n": written})
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


# The registrar console (K3) views live in ``apps.registrar.console_views`` to
# keep this module focused (journal + gradebook) and under the size budget;
# the weekly timetable (U4) and the academic calendar (U11) live in
# ``apps.registrar.schedule_views`` for the same reason.

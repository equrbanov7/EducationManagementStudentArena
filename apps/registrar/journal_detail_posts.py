"""Jurnal səhifəsinin (``views.journal_detail``) POST işləyiciləri — «Yeni dərs» və davamiyyət/bal yazısı.

``views.py`` modul-ölçü büdcəsinə görə bölünüb (2026-10-27): məntiq dəyişmədən buraya köçürülüb, üstəgəl
«Data bərpası» rejimi (``journal.teacher_full_edit``, :mod:`apps.registrar.journal_full_edit`) — rejim açıq və
aktor bu jurnalın birbaşa redaktorudursa bağlı jurnala / yazma pəncərəsindən kənar tarixə dərs açmaq, kilidli
xananı dəyişmək və təmizləmək YALNIZ səbəb ilə (``full_edit_reason``) mümkündür; söndürülüdə davranış eynidir.
Hüquq (birbaşa redaktor) və bölünmüş jurnalın əhatəsi ``journal_detail``-də bu işləyicilərdən ƏVVƏL yoxlanır.
"""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

from . import grade_audit, gradebook, schedule
from .audit_write import AuditWriteFailed, audit_failure_message
from .models import AttendanceStatus, LessonKind


def handle_add_lesson(request, offering):
    """Create a new lesson column (date + type + topic + standart dərs saatı)."""
    # README §8/2 — siyasət açıqdırsa təsdiqlənmiş sillabussuz dərs açılmır:
    # 403 + SƏBƏB KODU (mesaj/redirect deyil, çünki qayda acceptance şərtidir).
    from apps.registrar import journal_activation, journal_full_edit, journal_lesson_prefill, journal_policy

    gate = journal_policy.syllabus_gate(offering)
    if gate["locked"]:
        return HttpResponseForbidden(gate["reason_code"], content_type="text/plain; charset=utf-8")
    # «Data bərpası» (sahib 2026-10-27): rejim açıqdırsa bağlı jurnala və keçmiş tarixə də — yalnız səbəb ilə.
    full_edit = journal_full_edit.active_for(request.user, offering)
    if not full_edit and getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — dərs əlavə etmək olmaz."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    date = request.POST.get("lesson_date") or None
    # Dərs tipi kilidi: cədvəldə tək növ slot varsa POST nə deyirsə desin o növ.
    from apps.registrar import journal_extras as _je

    locked_kind = _je.locked_lesson_kind(offering)
    kind = locked_kind or request.POST.get("lesson_kind")
    if kind not in dict(LessonKind.choices):
        # QA 2026-09-05 (P3-9): naməlum dərs tipi səssizcə «mühazirə»yə çevrilirdi —
        # müəllim yanlış tipdə dərs açdığını görmürdü. Kilidli tipdə (cədvəl tək
        # növ verir) POST-a baxılmır, orada susmaq düzgündür.
        if locked_kind:
            kind = locked_kind
        else:
            messages.error(request, _("Dərs tipi düzgün seçilməyib."))
            return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
    if not date:
        messages.error(request, _("Dərs tarixi tələb olunur."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    hours_raw = (request.POST.get("lesson_hours") or "").strip()
    # QA 2026-09-05 (P3-9): «-5» / «abc» səssizcə standart saata çevrilirdi.
    # Boş dəyər normaldır (standart saat), amma YAZILMIŞ yanlış dəyər rədd olunur.
    if hours_raw and not (hours_raw.isdigit() and int(hours_raw) > 0):
        messages.error(request, _("Dərs saatı müsbət tam ədəd olmalıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
    hours = int(hours_raw) if hours_raw.isdigit() and int(hours_raw) > 0 else None
    start_time, end_time = schedule.parse_time_slot(request.POST.get("lesson_time"))
    # Modal bu günün cədvəl slotundan doldurulubsa (gizli slot_id, sahib 2026-10-10) saat slotdandır — təşkilatın
    # öz zəng saatı da keçir, səbəb tələb olunmur; yad / başqa günün slotu rədd olunur (journal_lesson_prefill).
    try:
        slot = journal_lesson_prefill.posted_slot(offering, request.POST, date=date, kind=kind)
    except gradebook.LessonRuleError as exc:
        messages.error(request, str(exc))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
    if slot is not None:
        start_time, end_time = slot.start_time, slot.end_time
    # Dərs saatı MƏCBURİDİR — standart saat seçilmədən dərs açılmasın.
    if not start_time or not end_time:
        messages.error(request, _("Dərs saatı seçilməlidir — standart dərs saatlarından birini seçin."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    # #6 saat həddi + cədvəldən kənar dərsin SƏBƏBİ (UNEC P1-1) — «Aktivləşdir» yolu ilə ORTAQ qayda.
    # Data bərpasında cədvəldən kənar keçmiş dərsin səbəbi ayrıca yazılmayıbsa bərpa səbəbi götürülür.
    raw_off_reason = request.POST.get("off_schedule_reason") or (
        journal_full_edit.posted_reason(request) if full_edit else ""
    )
    off_reason, rule_error = journal_activation.check_manual_lesson(
        offering, date=date, start_time=start_time, hours=hours, raw_reason=raw_off_reason
    )
    if rule_error:
        messages.error(request, rule_error)
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

    # Dərsin otağı (opsional; korpus yalnız UI süzgəcidir) — təşkilat daxilində həll olunur, boşdursa
    # həmin tarix/saatın cədvəl slotunun otağı (sahib 2026-10-17, journal_lesson_prefill.posted_room).
    room = journal_lesson_prefill.posted_room(
        offering, request.POST, date=date, start_time=start_time, kind=kind, slot=slot
    )

    # İKT/RİM Rəhbəri / superuser keçmiş tarixə də dərs aça bilər (tam override).
    allow_past = bool(getattr(request.user, "is_superuser", False) or getattr(request.user, "is_ikt_rehber", False))
    bypass = full_edit and journal_full_edit.lesson_needs_bypass(offering, date, allow_past=allow_past)
    full_reason = journal_full_edit.posted_reason(request) if bypass else ""
    if bypass and not full_reason:
        messages.error(request, journal_full_edit.reason_required_message())
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
    try:
        with transaction.atomic():  # dərs + data bərpası audit sətri birlikdə (audit yazılmasa dərs də yoxdur)
            _create(
                request,
                offering,
                bypass,
                full_reason,
                allow_past=allow_past,
                date=date,
                kind=kind,
                topic=(_je.posted_topic(request.POST) or "").strip(),  # plan seçimi və ya sərbəst mətn
                hours=hours,
                start_time=start_time,
                end_time=end_time,
                instructor=instructor,
                room=room,
                slot=slot,
                off_schedule_reason=off_reason,
            )
        messages.success(request, _("Dərs əlavə edildi."))
    except gradebook.LessonRuleError as exc:
        messages.error(request, str(exc))
    except AuditWriteFailed:
        messages.error(request, audit_failure_message())
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _create(request, offering, bypass, full_reason, *, allow_past, **fields):
    from apps.registrar import journal_full_edit

    lesson = gradebook.create_lesson(
        offering=offering, created_by=request.user, allow_past=allow_past, full_edit=bypass, **fields
    )
    if bypass:
        journal_full_edit.log_lesson_added(
            offering=offering, lesson=lesson, by_user=request.user, reason=full_reason, request=request
        )
    elif allow_past:  # geriyə-dönük sütun audit izinə düşür (2026-08 auditi)
        grade_audit.log_backdated_lesson(offering=offering, lesson=lesson, by_user=request.user)
    return lesson


def handle_save_marks(request, offering):
    """Parse editable grid cells → save_marks.

    Yeni format (üç-vəziyyətli çip): ``att__L__E`` = '' | present | absent —
    boş dəyər GÖNDƏRİLMİR/yazılmır (müəllim toxunmadığı xana işarə almır).
    Köhnə format (cell__/absent__) geriyə-uyğunluq üçün saxlanır.
    «Data bərpası» rejimində (sahib 2026-10-27) ``att__L__E=clear`` xananı silir və qapını keçən hər yazı
    ``full_edit_reason`` tələb edir (yoxdursa avtomatik yadda saxlama 409 ``reason_required`` alır)."""
    from apps.registrar import journal_full_edit

    full_edit = journal_full_edit.active_for(request.user, offering)
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
            if raw == journal_full_edit.CLEAR and full_edit:
                entries.append({"lesson_id": lesson_id, "enrollment_id": enrollment_id, "status": raw, "score": ""})
                continue
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

    from apps.registrar import journal_autosave  # sahib 2026-10-14: eyni yazı yolu, JSON cavab

    autosave = journal_autosave.requested(request)
    if gradebook.journal_is_locked(offering) and not full_edit:
        # Əvvəl «Jurnal yadda saxlanıldı (0 xana)» UĞUR mesajı gedirdi (QA 2026-09-05
        # JOURNAL-TEACHER-04) — kilidli jurnala yazı səssiz atılmamalıdır.
        if autosave:
            return journal_autosave.refused(_("Jurnal bağlıdır — dəyişikliklər yazılmadı."), code="locked")
        messages.error(request, _("Jurnal bağlıdır — dəyişikliklər yazılmadı."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
    try:
        result = gradebook.save_marks(
            offering=offering,
            entries=entries,
            by_user=request.user,
            report=True,
            request=request,
            full_edit=full_edit,
            full_reason=journal_full_edit.posted_reason(request) if full_edit else "",
        )
    except AuditWriteFailed:  # data bərpasının audit sətri yazılmadı — heç nə saxlanmadı (fail-closed)
        if autosave:
            return journal_autosave.refused(audit_failure_message(), code="audit_failed")
        messages.error(request, audit_failure_message())
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
    written, rejected = result["written"], result["rejected"]
    if autosave and result.get("reason_required"):  # klient səbəb dialoqunu açıb təkrar göndərir
        message = journal_full_edit.reason_required_message()
        return journal_autosave.refused(message, code=journal_full_edit.REASON_REQUIRED_CODE)
    if autosave:  # kilidli xanaya dəyişiklik → 409 + «RİM-ə müraciət» mətni (sahib 2026-10-25)
        return journal_autosave.marks_response(result, sent=len(entries))
    if result.get("reason_required"):
        messages.warning(request, journal_full_edit.reason_required_message())
    # dərs günü / yazma pəncərəsi / aktivləşdirmə pəncərəsi; kilidli xana (15 dəq. / köçürülmüş / düzəliş)
    blocked_reason = " ".join(filter(None, (result.get("blocked_reason"), result.get("locked_reason"))))
    if entries and not written:
        messages.warning(
            request,
            blocked_reason or _("Heç bir xana yazılmadı — dərs günü qaydası və ya xana kilidi buna imkan vermədi."),
        )
    else:
        messages.success(request, _("Jurnal yadda saxlanıldı (%(n)s xana).") % {"n": written})
        if blocked_reason:
            messages.warning(request, blocked_reason)
    if rejected:
        # QA 2026-09-05 (P3-10): səhv bal SƏSSİZ 0-a çevrilmirdi; xana yazılmır və
        # müəllim bunu görməlidir.
        messages.warning(
            request,
            _("%(n)s xana yazılmadı — bal 0–10 aralığında TAM ədəd olmalıdır.") % {"n": rejected},
        )
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

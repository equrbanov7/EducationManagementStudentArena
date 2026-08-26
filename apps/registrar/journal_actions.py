"""Jurnal iş sahəsinin POST əməliyyatları (yenidən-dizayn dalğası).

``views.journal_detail`` GET renderini saxlayır; buradakı view-lar yalnız
yazma əməliyyatlarıdır: dərs sütunu redaktə/silmə (2 saat pəncərəsi),
kollokvium tarixləri+balları, sərbəst iş mövzu/işarələri, kurs işi.
Hamısı ``_can_edit_journal`` + tenant RLS + servis-qatı kilidləri ilə qorunur.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import gradebook, journal_extras
from .journal_access import offering_or_404 as scoped_offering_or_404
from .models import Lesson, SelfWorkTopic
from .views import _can_edit_journal, _is_direct_editor


def _offering_or_404(request, offering_id):
    """Tenant-scope-lu yükləmə + redaktə səlahiyyəti yoxlaması."""
    offering = scoped_offering_or_404(request, offering_id)
    if not _can_edit_journal(request.user, offering):
        raise Http404
    return offering


def _back(offering, tab=""):
    url = reverse("registrar:journal_detail", args=[offering.pk])
    return redirect(f"{url}#{tab}" if tab else url)


def _can_write_documented_correction(request) -> bool:
    """Aktor sənədli (PDF + audit) düzəliş edə bilirmi — ``journal.correct``.

    Kilid bağlananda dəyişikliyi yalnız bu icazə daşıyan aktor (RİM/İKT rəhbəri,
    superadmin və ya icazə redaktorundan ``journal.correct`` almış istənilən rol)
    apara bilər. Adi müəllim sadəcə «pəncərə bitib» cavabı alır."""
    from apps.registrar import corrections as corrections_service

    return corrections_service.can_correct_journal(request)


def _corrector_direct_write_blocked(request, offering, tab=""):
    """Korrektor (İKT) birbaşa (audit-siz) yazmağa cəhd edirsə RƏDD et.

    İKT jurnalı yalnız «Jurnal düzəlişi» rejimində sənədli (audited) dəyişir; normal
    tab-lardan (sərbəst iş / kollokvium / kurs işi) birbaşa yazma qadağandır. Müəllim /
    sahib / superuser (birbaşa redaktor) təsirlənmir. Qaytarır: redirect (bloklandı) və
    ya None (icazə var)."""
    if _is_direct_editor(request.user, offering):
        return None
    messages.error(
        request,
        _(
            "Dəyişiklik üçün yuxarıdan «Jurnal düzəlişi» rejimini aktivləşdirin — İKT rəhbəri yalnız sənədli düzəliş edə bilər."
        ),
    )
    return _back(offering, tab)


def _resolve_instructor(offering, raw_id):
    """POST-dakı ``lesson_instructor`` id-ni istifadəçiyə çevir (boş → None).

    Bu dərsin müəllimi (fənn 2 müəllim arasında bölünübsə); boşdursa dəyişmə
    (None → update_lesson toxunmur, açılışın müəllimi qalır)."""
    raw_id = (raw_id or "").strip()
    if not raw_id:
        return None
    from django.contrib.auth import get_user_model
    from django.core.exceptions import ValidationError

    from apps.registrar.integrity import validate_instructor_assignment

    instructor = get_user_model().objects.filter(pk=raw_id).first()
    if instructor is None:
        raise Http404
    try:
        validate_instructor_assignment(
            organization=offering.organization,
            instructor=instructor,
        )
    except ValidationError as exc:
        raise Http404 from exc
    return instructor


@login_required
@require_POST
def lesson_action(request, offering_id, lesson_id):
    """Dərs sütunu: redaktə və ya silmə — yalnız yaranışdan 2 saat içində."""
    offering = _offering_or_404(request, offering_id)
    lesson = get_object_or_404(Lesson, pk=lesson_id, offering=offering)
    action = request.POST.get("action")
    # Silmə düyməsi redaktə formasının içindədir (eyni MƏCBURİ PDF-i paylaşır) →
    # do_delete=1 gələndə action-i silməyə çevir.
    if request.POST.get("do_delete") == "1":
        action = "delete_lesson"
    # İKT Rəhbəri / superuser: 2 saatlıq pəncərə DAXİLİNDƏ keçmiş-tarix qadağasını
    # keçir (səhv açılmış dərsin tarixini/növünü düzəltmək üçün).
    override = bool(getattr(request.user, "is_superuser", False) or getattr(request.user, "is_ikt_rehber", False))
    # Sənədli (PDF) yol MƏCBURİDİR, iki haldan biri varsa:
    #   * aktor birbaşa redaktor DEYİL (korrektor/İKT — normal görünüş read-only), VƏ YA
    #   * 2 saatlıq redaktə pəncərəsi bağlanıb / jurnal kilidlidir.
    #
    # 2026-08 auditi: əvvəl yalnız BİRİNCİ şərt vardı və `allow_locked=override`
    # kilidi eyni anda həm superuser-ə, həm də İKT/RİM rəhbərinə SƏNƏDSİZ keçməyə
    # imkan verirdi (məsələn, həm həmin fənnin müəllimi, həm də RİM rəhbəri olan
    # istifadəçi «birbaşa redaktor» sayılırdı). İndi pəncərə bağlananda dəyişiklik
    # yalnız səbəb + qeyd + PDF ilə — audited correction yolundan — keçir.
    window_open = gradebook.can_edit_lesson(lesson) and not gradebook.journal_is_locked(offering)
    corrector_only = (not _is_direct_editor(request.user, offering)) or (not window_open)
    if corrector_only and not _can_write_documented_correction(request):
        # Pəncərə bitib, sənədli düzəliş icazəsi (journal.correct) da yoxdur →
        # mövcud davranışla eyni rədd mesajı.
        messages.error(request, _("Dərs dəyişdirilmədi — 2 saatlıq düzəliş pəncərəsi bitib."))
        return _back(offering)

    if action == "delete_lesson":
        # Korrektor (İKT): silmə də bal/redaktə düzəlişi kimi rəsmi sənəd (səbəb +
        # qeyd + PDF) tələb edir; sənədsiz silmək OLMAZ.
        if corrector_only:
            from django.core.exceptions import ValidationError

            from apps.registrar import corrections as corrections_service

            try:
                corrections_service.apply_lesson_deletion(
                    lesson=lesson,
                    reason=request.POST.get("correction_reason") or "",
                    note=request.POST.get("correction_note") or "",
                    document=request.FILES.get("correction_document"),
                    by_user=request.user,
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return _back(offering)
            messages.success(request, _("Dərs sənədli əsasla silindi."))
            return _back(offering)
        # Bura yalnız pəncərə AÇIQ olanda çatılır → `allow_locked` lazım deyil.
        if gradebook.delete_lesson(lesson=lesson, by_user=request.user, allow_locked=False):
            messages.success(request, _("Dərs silindi."))
        else:
            messages.error(request, _("Dərs silinmədi — 2 saatlıq düzəliş pəncərəsi bitib."))
        return _back(offering)

    if action == "update_lesson":
        from apps.registrar import schedule as schedule_service
        from apps.registrar.journal_extras import locked_lesson_kind as _locked_lesson_kind

        start_time, end_time = schedule_service.parse_time_slot(request.POST.get("lesson_time"))
        hours = int(request.POST.get("lesson_hours")) if (request.POST.get("lesson_hours") or "").isdigit() else None
        # Dərs tipi: korrektor (İKT) kilidi keçir (mühazirə↔seminar qarışığını
        # düzəldə bilsin); adi müəllim üçün cədvəl tək növü kilidləyir.
        posted_kind = request.POST.get("lesson_kind") or None
        kind = posted_kind if override else (_locked_lesson_kind(offering) or posted_kind)
        instructor = _resolve_instructor(offering, request.POST.get("lesson_instructor"))

        # Korrektor (İKT): tarix/tip/saat/mövzu/müəllim dəyişikliyi — HƏR lock
        # vəziyyətində səbəb + qeyd + PDF MƏCBURİ və audit olunur.
        if corrector_only:
            from django.core.exceptions import ValidationError

            from apps.registrar import corrections as corrections_service

            try:
                corrections_service.apply_lesson_correction(
                    lesson=lesson,
                    new_date=request.POST.get("lesson_date") or None,
                    new_kind=kind,
                    new_hours=hours,
                    new_start_time=start_time or "",
                    new_end_time=end_time or "",
                    new_topic=request.POST.get("lesson_topic"),
                    new_instructor=instructor,
                    reason=request.POST.get("correction_reason") or "",
                    note=request.POST.get("correction_note") or "",
                    document=request.FILES.get("correction_document"),
                    by_user=request.user,
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return _back(offering)
            messages.success(request, _("Dərs sənədli düzəlişlə yeniləndi."))
            return _back(offering)

        try:
            ok = gradebook.update_lesson(
                lesson=lesson,
                date=request.POST.get("lesson_date") or None,
                kind=kind,
                topic=request.POST.get("lesson_topic"),
                hours=hours,
                start_time=start_time or "",
                end_time=end_time or "",
                instructor=instructor,
                allow_past=override,
                # Pəncərə açıqdır (yuxarıda yoxlanıb) — kilid keçidi lazım deyil.
                allow_locked=False,
            )
        except gradebook.LessonRuleError as exc:
            messages.error(request, str(exc))
            return _back(offering)
        if ok:
            messages.success(request, _("Dərs yeniləndi."))
        else:
            messages.error(request, _("Dərs yenilənmədi — 2 saatlıq düzəliş pəncərəsi bitib."))
        return _back(offering)

    raise Http404


@login_required
@require_POST
def kollokvium_save(request, offering_id):
    """Kollokvium balları — YALNIZ İmtahan Mərkəzi pəncərəsi AÇIQ olan K-lar üçün.

    Tarix xanaları yoxdur (aralığı İmtahan Mərkəzi təyin edir). Açıq pəncərədə
    2 saat kilidi bypass olunur — müəllim aralıq boyu balı dəyişə bilər.
    """
    from apps.registrar import kollokvium_windows as kw

    offering = _offering_or_404(request, offering_id)
    blocked = _corrector_direct_write_blocked(request, offering, "kollokvium")
    if blocked:
        return blocked
    components = list(journal_extras.ensure_kollokviums(offering))
    idx_by_id = {str(c.id): idx for idx, c in enumerate(components)}
    today = timezone.localdate()

    entries = []
    blocked = False
    for key, raw in request.POST.items():
        if not key.startswith("kscore__"):
            continue
        parts = key.split("__", 2)
        if len(parts) != 3 or parts[1] not in idx_by_id:
            continue
        if not kw.is_open(offering, idx_by_id[parts[1]], today):
            blocked = True
            continue  # pəncərə bağlı / aktiv deyil — bu K-ya yazma qadağandır
        entries.append({"component_id": parts[1], "enrollment_id": parts[2], "score": raw})

    if not entries:
        messages.error(
            request,
            _("Kollokvium bal-yazma pəncərəsi açıq deyil — İmtahan Mərkəzi aralığı aktivləşdirməlidir."),
        )
        return _back(offering, "kollokvium")

    written = gradebook.save_component_scores(
        offering=offering, entries=entries, by_user=request.user, bypass_edit_window=True
    )
    if blocked:
        messages.warning(request, _("Bəzi kollokviumların pəncərəsi bağlı olduğu üçün yazılmadı."))
    messages.success(request, _("Kollokvium balları yadda saxlanıldı (%(n)s xana).") % {"n": written})
    return _back(offering, "kollokvium")


@login_required
@require_POST
def selfwork_action(request, offering_id):
    """Sərbəst iş tabı: mövzu əlavə/sil və işarə (1/0) dəyişiklikləri."""
    offering = _offering_or_404(request, offering_id)
    blocked = _corrector_direct_write_blocked(request, offering, "serbest")
    if blocked:
        return blocked
    action = request.POST.get("action")
    # 2026-08 auditi: burada əvvəl `allow_locked = is_superuser or is_ikt_rehber`
    # vardı — yəni RİM/İKT rəhbəri (və superuser) 2 saatlıq geri-alma pəncərəsini
    # SƏNƏDSİZ keçirdi. Artıq keçmir: pəncərə bağlananda dəyişiklik yalnız
    # «Jurnal düzəlişi» rejimindən (``correction_apply`` → PDF + audit) keçir.

    if action == "add_topic":
        topic = journal_extras.add_selfwork_topic(offering=offering, title=request.POST.get("topic_title"))
        if topic is None:
            messages.error(request, _("Mövzu əlavə olunmadı (boş ad və ya limit doldu)."))
        else:
            messages.success(request, _("Sərbəst iş mövzusu əlavə edildi."))
        return _back(offering, "serbest")

    if action == "delete_topic":
        topic = get_object_or_404(SelfWorkTopic, pk=request.POST.get("topic_id"), offering=offering)
        if journal_extras.delete_selfwork_topic(topic=topic, by_user=request.user):
            messages.success(request, _("Mövzu (və üzrə balları) silindi."))
        else:
            messages.error(request, _("Mövzu silinmədi — jurnal bağlıdır."))
        return _back(offering, "serbest")

    # İşarə dəyişiklikləri: sw__<topic_id>__<enrollment_id> = 0|1
    changed = 0
    skipped = 0
    for key, raw in request.POST.items():
        if not key.startswith("sw__"):
            continue
        parts = key.split("__", 2)
        if len(parts) != 3:
            continue
        ok = journal_extras.set_selfwork_mark(
            offering=offering,
            topic_id=parts[1],
            enrollment_id=parts[2],
            done=raw == "1",
            by_user=request.user,
            allow_locked=False,  # pəncərə bitibsə → sənədli düzəliş rejimi
        )
        if ok:
            changed += 1
        else:
            skipped += 1
    if skipped:
        messages.warning(request, _("Bəzi işarələr dəyişilmədi — geri alma pəncərəsi bitib."))
    else:
        messages.success(request, _("Sərbəst iş işarələri yadda saxlanıldı."))
    return _back(offering, "serbest")


@login_required
@require_POST
def coursework_save(request, offering_id):
    """Kurs işi tabı.

    İki format dəstəklənir: mockup formu (``cw_enrollment``/``cw_topic``/
    ``cw_score``/``cw_date`` — bir tələbə) və toplu ``cwtopic__<id>`` sahələri."""
    offering = _offering_or_404(request, offering_id)
    blocked = _corrector_direct_write_blocked(request, offering, "kurs-isi")
    if blocked:
        return blocked
    enrollments = {str(e.id): e for e in offering.enrollments.all()}
    saved = 0
    frozen = 0
    # 2026-08 auditi: İKT/superuser üçün sənədsiz `allow_locked` güzəşti ləğv edildi —
    # 2 saatlıq pəncərə bitibsə kurs işi yalnız sənədli düzəlişlə dəyişir.

    single = enrollments.get(request.POST.get("cw_enrollment") or "")
    if single is not None:
        ok = journal_extras.save_course_work(
            enrollment=single,
            topic=request.POST.get("cw_topic"),
            score=request.POST.get("cw_score"),
            submitted_on=parse_date(request.POST.get("cw_date") or ""),
            by_user=request.user,
            allow_locked=False,
        )
        if ok:
            messages.success(request, _("Kurs işi yadda saxlanıldı."))
        else:
            messages.error(request, _("Kurs işi dəyişilmədi — 2 saatlıq pəncərə bitib."))
        return _back(offering, "kurs-isi")

    for key, raw in request.POST.items():
        if not key.startswith("cwtopic__"):
            continue
        enrollment_id = key[len("cwtopic__") :]
        enrollment = enrollments.get(enrollment_id)
        if enrollment is None:
            continue
        topic = (raw or "").strip()
        score = request.POST.get(f"cwscore__{enrollment_id}")
        submitted = parse_date(request.POST.get(f"cwdate__{enrollment_id}") or "")
        if not topic and not (score or "").strip():
            continue  # boş sətir — toxunma
        if journal_extras.save_course_work(
            enrollment=enrollment,
            topic=topic,
            score=score,
            submitted_on=submitted,
            by_user=request.user,
            allow_locked=False,
        ):
            saved += 1
        else:
            frozen += 1
    if frozen:
        messages.warning(request, _("Bəzi kurs işləri dəyişilmədi — 2 saatlıq pəncərə bitib."))
    if saved:
        messages.success(request, _("Kurs işi qeydləri yadda saxlanıldı (%(n)s sətir).") % {"n": saved})
    return _back(offering, "kurs-isi")

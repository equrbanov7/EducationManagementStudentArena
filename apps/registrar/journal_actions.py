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
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import gradebook, journal_extras
from .models import CourseOffering, Lesson, SelfWorkTopic
from .views import _can_edit_journal


def _offering_or_404(request, offering_id):
    offering = get_object_or_404(
        CourseOffering.objects.select_related("subject", "period", "group", "organization"),
        pk=offering_id,
    )
    if not _can_edit_journal(request.user, offering):
        raise Http404
    return offering


def _back(offering, tab=""):
    url = reverse("registrar:journal_detail", args=[offering.pk])
    return redirect(f"{url}#{tab}" if tab else url)


@login_required
@require_POST
def lesson_action(request, offering_id, lesson_id):
    """Dərs sütunu: redaktə və ya silmə — yalnız yaranışdan 2 saat içində."""
    offering = _offering_or_404(request, offering_id)
    lesson = get_object_or_404(Lesson, pk=lesson_id, offering=offering)
    action = request.POST.get("action")

    if action == "delete_lesson":
        if gradebook.delete_lesson(lesson=lesson, by_user=request.user):
            messages.success(request, _("Dərs silindi (2 saat pəncərəsi içində)."))
        else:
            messages.error(request, _("Dərs silinmədi — 2 saatlıq düzəliş pəncərəsi bitib."))
        return _back(offering)

    if action == "update_lesson":
        from apps.registrar import schedule as schedule_service
        from apps.registrar.journal_extras import locked_lesson_kind as _locked_lesson_kind

        start_time, end_time = schedule_service.parse_time_slot(request.POST.get("lesson_time"))
        try:
            ok = gradebook.update_lesson(
                lesson=lesson,
                date=request.POST.get("lesson_date") or None,
                # Dərs tipi kilidi: cədvəldə tək növ slot varsa dəyişilə bilməz.
                kind=_locked_lesson_kind(offering) or request.POST.get("lesson_kind") or None,
                topic=request.POST.get("lesson_topic"),
                hours=(
                    int(request.POST.get("lesson_hours"))
                    if (request.POST.get("lesson_hours") or "").isdigit()
                    else None
                ),
                start_time=start_time or "",
                end_time=end_time or "",
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
    """Kollokvium tabı: keçirilmə tarixləri + tələbə balları (kdate__/kscore__)."""
    offering = _offering_or_404(request, offering_id)
    components = {str(c.id): c for c in journal_extras.ensure_kollokviums(offering)}

    for key, raw in request.POST.items():
        if key.startswith("kdate__"):
            component = components.get(key[len("kdate__") :])
            if component is not None:
                journal_extras.set_kollokvium_date(component=component, held_on=parse_date(raw or "") or None)

    entries = []
    for key, raw in request.POST.items():
        if not key.startswith("kscore__"):
            continue
        parts = key.split("__", 2)
        if len(parts) != 3 or parts[1] not in components:
            continue
        entries.append({"component_id": parts[1], "enrollment_id": parts[2], "score": raw})
    written = gradebook.save_component_scores(offering=offering, entries=entries, by_user=request.user)
    messages.success(request, _("Kollokvium məlumatları yadda saxlanıldı (%(n)s xana).") % {"n": written})
    return _back(offering, "kollokvium")


@login_required
@require_POST
def selfwork_action(request, offering_id):
    """Sərbəst iş tabı: mövzu əlavə/sil və işarə (1/0) dəyişiklikləri."""
    offering = _offering_or_404(request, offering_id)
    action = request.POST.get("action")

    if action == "add_topic":
        topic = journal_extras.add_selfwork_topic(offering=offering, title=request.POST.get("topic_title"))
        if topic is None:
            messages.error(request, _("Mövzu əlavə olunmadı (boş ad və ya limit doldu)."))
        else:
            messages.success(request, _("Sərbəst iş mövzusu əlavə edildi."))
        return _back(offering, "serbest")

    if action == "delete_topic":
        topic = get_object_or_404(SelfWorkTopic, pk=request.POST.get("topic_id"), offering=offering)
        if journal_extras.delete_selfwork_topic(topic=topic):
            messages.success(request, _("Mövzu silindi."))
        else:
            messages.error(request, _("Mövzu silinmədi — artıq təhvil işarələri var."))
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
    enrollments = {str(e.id): e for e in offering.enrollments.all()}
    saved = 0
    frozen = 0

    single = enrollments.get(request.POST.get("cw_enrollment") or "")
    if single is not None:
        ok = journal_extras.save_course_work(
            enrollment=single,
            topic=request.POST.get("cw_topic"),
            score=request.POST.get("cw_score"),
            submitted_on=parse_date(request.POST.get("cw_date") or ""),
            by_user=request.user,
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
            enrollment=enrollment, topic=topic, score=score, submitted_on=submitted, by_user=request.user
        ):
            saved += 1
        else:
            frozen += 1
    if frozen:
        messages.warning(request, _("Bəzi kurs işləri dəyişilmədi — 2 saatlıq pəncərə bitib."))
    if saved:
        messages.success(request, _("Kurs işi qeydləri yadda saxlanıldı (%(n)s sətir).") % {"n": saved})
    return _back(offering, "kurs-isi")

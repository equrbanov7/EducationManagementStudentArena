"""«Tələbə reyestri» bölməsinin JSON/fayl endpoint-ləri (ekran 09).

Panelin ÖZÜ server-render-lidir (filtr/sıralama/səhifələmə linklə işləyir —
handoff §8/14), ona görə burada YALNIZ mutasiya və ağır/ikincili yüklər var:

* ``student_registry_card``      — çekmecə (drawer) məzmunu: akademik kart +
  GPA + hərəkət tarixçəsi (GET, bir tələbə üçün);
* ``student_registry_programs``  — hədəf ixtisas seçicisinin axtarışı (GET);
* ``student_registry_action``    — hərəkət əmri (POST, multipart — sənədlə);
* ``student_registry_export``    — CSV ixracı (GET, icazə-qapılı);
* ``student_registry_document``  — əmr sənədinin endirilməsi (GET, qapılı).

Hədəf QRUP seçicisi TƏKRAR YAZILMIR — mövcud ``people_academic_groups``
endpoint-i eyni müqaviləni (``EMSSearchableSelect``) onsuz da verir.

Hamısı FAIL-CLOSED: `student.registry_view` (oxu) / `student.movement`
(yazı) açarı olmayan aktor 403 alır; sahədən kənar qeyd 404-dür (mövcudluq
məlumat sızmasın deyə 403 DEYİL).
"""

from __future__ import annotations

import csv

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.services import people
from apps.accounts.services.people import movements as movement_service
from apps.accounts.services.people import registry as registry_service
from apps.accounts.services.rim.policy import RimAccessError

_CTX = "accounts.student_registry"

#: CSV ixracının sətir həddi — brauzer/yaddaş qapısı.
EXPORT_LIMIT = 10000

#: Axtarış sətrinin yuxarı həddi (uzun sorğu DB-yə ötürülmür).
MAX_QUERY_LENGTH = 80

#: Hədəf ixtisas seçicisinin səhifə ölçüsü.
PROGRAM_PAGE_SIZE = 20


def _error(exc: RimAccessError) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "has_access": False, "error": exc.reason_code, "message": exc.message},
        status=exc.status,
    )


@never_cache
@login_required
@require_GET
def student_registry_card(request, record_id):
    """Çekmecə: şəxsi blok + akademik göstəricilər + hərəkət tarixçəsi."""
    actor = people.resolve_actor(request)
    try:
        record = movement_service.load_registry_record(actor, record_id, request=request)
        history = movement_service.student_movements(actor, record_id=record_id, request=request)
    except RimAccessError as exc:
        return _error(exc)

    from apps.registrar import transcript as transcript_service

    # GPA YALNIZ burada hesablanır (bir tələbə) — siyahıda QƏSDƏN yoxdur.
    transcript = transcript_service.build_student_transcript(
        student=record.student, organization=record.organization, program=record.program
    )
    profile = getattr(record.student, "profile", None)
    return JsonResponse(
        {
            "ok": True,
            "has_access": True,
            "record_id": str(record.pk),
            "name": (record.student.get_full_name() or record.student.username).strip(),
            "fin": str(getattr(profile, "fin", "") or "") if actor.can_view_contacts else "",
            "student_code": str(getattr(profile, "institutional_identifier", "") or ""),
            "program_label": record.program.display_label,
            "group_name": str(getattr(record.group, "name", "") or ""),
            "admission_year": record.admission_year,
            "admission_score": str(record.admission_score) if record.admission_score is not None else "",
            "admission_exam_type": record.admission_exam_type,
            "atis_id": record.atis_id,
            "form_label": str(record.get_education_form_display()),
            "funding_label": str(record.get_funding_type_display()),
            "status": record.status,
            "gpa": str(transcript.get("cumulative_gpa") or ""),
            "gpa_available": bool(transcript.get("cumulative_gpa_available")),
            "credits_earned": transcript.get("total_credits_earned", 0),
            "can_move": bool(actor.can_move_students and actor.can_manage_academic),
            "movements": history,
        }
    )


@never_cache
@login_required
@require_GET
def student_registry_programs(request):
    """Hədəf ixtisas seçicisi — axtarışlı, səhifəli (`EMSSearchableSelect`)."""
    actor = people.resolve_actor(request)
    if not actor.can_view_registry:
        return JsonResponse({"has_access": False, "results": [], "has_more": False}, status=403)

    from apps.registrar.models import Program

    programs = Program.objects.filter(organization=actor.organization, is_active=True)
    query = (request.GET.get("q") or "").strip()[:MAX_QUERY_LENGTH]
    if query:
        from core.program_codes import program_code_search_q

        programs = programs.filter(program_code_search_q(query) | _name_contains(query))
    try:
        offset = max(0, int(request.GET.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0
    window = list(programs.order_by("name")[offset : offset + PROGRAM_PAGE_SIZE + 1])
    return JsonResponse(
        {
            "has_access": True,
            "results": [
                {"id": str(program.pk), "text": program.display_label} for program in window[:PROGRAM_PAGE_SIZE]
            ],
            "has_more": len(window) > PROGRAM_PAGE_SIZE,
        }
    )


def _name_contains(query: str):
    from django.db.models import Q

    return Q(name__icontains=query)


@never_cache
@login_required
@require_POST
def student_registry_action(request):
    """Hərəkət əmri — səbəb ≥20 simvol, əmr nömrəsi + tarix məcburi."""
    actor = people.resolve_actor(request)
    try:
        row = movement_service.create_movement(
            actor,
            record_id=(request.POST.get("record_id") or "").strip(),
            kind=(request.POST.get("kind") or "").strip(),
            order_number=request.POST.get("order_number") or "",
            order_date=request.POST.get("order_date") or "",
            reason=request.POST.get("reason") or "",
            request=request,
            target_group_id=(request.POST.get("target_group") or "").strip(),
            target_program_id=(request.POST.get("target_program") or "").strip(),
            target_form=(request.POST.get("target_form") or "").strip(),
            effective_until=(request.POST.get("effective_until") or "").strip(),
            document=request.FILES.get("document"),
        )
    except RimAccessError as exc:
        return _error(exc)
    return JsonResponse({"ok": True, "movement": row})


@never_cache
@login_required
@require_GET
def student_registry_export(request):
    """Cari filtr dəstinin CSV ixracı (server tərəfdə, icazə-qapılı)."""
    actor = people.resolve_actor(request)
    if not actor.can_view_registry:
        return JsonResponse(
            {"ok": False, "error": "permission_denied", "message": pgettext(_CTX, "İxrac üçün icazəniz yoxdur.")},
            status=403,
        )
    rows = registry_service.export_rows(actor=actor, request=request, limit=EXPORT_LIMIT)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="telebe_reyestri.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    # BOM — Excel AZ hərflərini düzgün açsın deyə (şablon faylı ilə eyni qayda).
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(
        [
            pgettext(_CTX, "Tələbə kodu"),
            pgettext(_CTX, "Ad Soyad"),
            pgettext(_CTX, "İxtisas"),
            pgettext(_CTX, "Qrup"),
            pgettext(_CTX, "Kurs"),
            pgettext(_CTX, "Qəbul ili"),
            pgettext(_CTX, "Forma"),
            pgettext(_CTX, "Təhsil haqqı"),
            pgettext(_CTX, "Status"),
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["student_code"],
                row["name"],
                row["program_label"],
                row["group_name"],
                row["course_label"],
                row["admission_year"],
                row["form_label"],
                row["funding_label"],
                row["status_label"],
            ]
        )
    return response


@never_cache
@login_required
@require_GET
def student_registry_document(request, movement_id):
    """Əmrin əsas sənədi — birbaşa media URL-i YOX, icazə yoxlayan qapı."""
    actor = people.resolve_actor(request)
    if not actor.can_view_registry or actor.organization is None:
        raise Http404

    from apps.registrar.models import StudentMovement

    movement = (
        StudentMovement.objects.filter(organization=actor.organization, pk=movement_id).select_related("record").first()
    )
    if movement is None or not movement.document:
        raise Http404
    # Sətir aktorun ƏHATƏSİNDƏDİRMİ — qeydin özü üzərindən yenidən yoxlanılır.
    try:
        movement_service.load_registry_record(actor, movement.record_id, request=request)
    except RimAccessError as exc:  # pragma: no cover — scope xaricində 404
        raise Http404 from exc

    try:
        handle = movement.document.open("rb")
    except OSError as exc:  # pragma: no cover — itmiş fayl
        raise Http404 from exc
    response = FileResponse(handle, as_attachment=True, filename=movement.document.name.rsplit("/", 1)[-1])
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = [
    "student_registry_action",
    "student_registry_card",
    "student_registry_document",
    "student_registry_export",
    "student_registry_programs",
]

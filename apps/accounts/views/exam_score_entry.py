"""İmtahan Mərkəzi — «İmtahan balının daxil edilməsi» (profil bölməsi).

SAHİBİN QƏRARI (2026-08): yazılı və praktiki imtahan kağız üzərində (praktikidə
kodda) keçir — sistemdən getmir. Balları sonradan İmtahan Mərkəzi köçürür:
dövr (tədris ili + semestr) → QRUP → fənn (açılış) → tələbə siyahısı → formada
bir-bir bal + (opsional) imtahan vərəqinin şəkli/PDF-i və mətn qeydi.

2026-09-12 (sahib: «qrup seçilsin, müəllim, tarix və s. lazımlı nə info varsa»):
hər yadda saxlama bir KÖÇÜRMƏ VƏRƏQİ (``ExamScoreSheet`` partiyası) yaradır —
imtahan tarixi, yoxlayan müəllim, nəzarətçi, protokol №, skan (opsional).
Dəyişdirilən ballar üçün səbəb + qeyd bir dəfə (dialoqda) verilir; sənəd
partiyanın skanıdır (sətir-səviyyə fayl da qəbul olunur — köhnə forma).

POST bölməyə redirect edir; GET ``_render_profile_section`` ilə profil bölməsini
render edir (``journal_close`` / ``kollokvium_windows`` pattern-i). Fayl idxalı
(şablon / quru icra / tətbiq) qardaş modul ``exam_score_import``-dadır.

İcazə qapısı: ``final_score.entry`` (bax ``apps/registrar/exam_score_entry.py``).
Sətir-sətir yazı servis qatındadır — orada ilk daxiletmə sərbəst, SONRAKI
dəyişiklik isə səbəb + qeyd + sənəd tələb edir.

2026-09-26 (sahib): BİTMİŞ dövrdə boş bal yazıla bilər (60 gündən köhnə dövrdə
sənədlə); yazılmış balı dəyişmək yalnız RİM rəhbəri / superadmin, yalnız «Düzəliş
rejimi»ndə (``correction_mode=1``) və tam təqdimatla (səbəb + qeyd + skan; skan
təsdiq dialoqunun fayl sahəsindən və ya vərəq kartından). Qayda
``apps/registrar/exam_score_period_lock.py``-dadır.

2026-09-14 (W2 `w2paper`): sətirdə sual-sual ballar ``q__<enr>__<n>``
(n = 1..sual sayı) — hər hansı biri doludursa imtahan balı onların CƏMİDİR
(server hesablayır, ``score__<enr>`` nəzərə alınmır); vərəqin sual şəbəkəsi
``question_count`` / ``question_max``; dəyişiklik növü ``kind``
(``correction`` | ``appeal``) dialoqdan bir dəfə gəlir.
"""

import logging
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext

from apps.registrar.models import CourseOffering, ExamScoreSheetSource
from apps.registrar.public import exam_score_entry as service
from apps.registrar.public import exam_score_sheets as sheets_service

from ._helpers import (
    _append_query_params,
    _get_active_organization,
    _is_superadmin_user,
    _render_profile_section,
    _resolve_next_url,
)

logger = logging.getLogger(__name__)

_CTX = "accounts.exam_score_entry"

SECTION = "exam-score-entry"


class ExamScoreEntryError(Exception):
    """Bölmənin istifadəçi-üzlü xətası (dispatcher-də tutulur)."""


def _can_manage(user, organization):
    """`final_score.entry` icazəsi + superadmin bypass."""
    if not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin_user(user):
        return True
    if organization is None:
        return False
    return service.can_enter_exam_scores(user, organization)


def _resolve_target_org(request):
    """Bu sorğunun idarə etdiyi təşkilat (superadmin: ?ese_org / POST organization_id)."""
    from apps.organizations.models import Organization

    if _is_superadmin_user(request.user):
        org_id = (request.POST.get("organization_id") or request.GET.get("ese_org") or "").strip()
        if org_id:
            try:
                UUID(org_id)
            except (ValueError, TypeError, AttributeError):
                return None
            return Organization.objects.filter(pk=org_id).first()
        return Organization.objects.filter(is_active=True).order_by("name").first()
    return _get_active_organization(request)


@login_required
def exam_score_entry(request):
    """İmtahan balının daxil edilməsi (profil SPA bölməsi)."""
    organization = _resolve_target_org(request) if request.method == "POST" else _get_active_organization(request)
    if not _can_manage(request.user, organization or _get_active_organization(request)):
        return HttpResponseForbidden(
            pgettext(_CTX, "Bu bölmə yalnız imtahan balı daxil etmə səlahiyyəti olanlar üçündür.")
        )

    fallback_next = _append_query_params(reverse("accounts:profile"), section=SECTION)

    if request.method == "POST":
        next_url = _resolve_next_url(request, fallback_next)
        # `_resolve_next_url` onsuz da same-origin yoxlayır; yoxlama BURADA da
        # təkrarlanır ki, statik analiz (CodeQL `py/url-redirection`) sanitizer-i
        # redirect nöqtəsinin ÖZ funksiyasında görsün. Davranış dəyişmir —
        # `fallback_next` `reverse()`-dən gəlir, yəni həmişə daxili URL-dir.
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            next_url = fallback_next
        if organization is None:
            messages.error(request, pgettext(_CTX, "Təşkilat konteksti tapılmadı."))
            return redirect(next_url)
        try:
            next_url = _handle_save(request, organization, next_url)
        except (ExamScoreEntryError, PermissionDenied) as exc:
            messages.error(request, str(exc) or pgettext(_CTX, "Bu əməliyyat üçün icazəniz yoxdur."))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(next_url)

    return _render_profile_section(request, SECTION)


def _offering_or_error(request, organization, offering_id=None):
    offering_id = (offering_id if offering_id is not None else request.POST.get("offering_id") or "").strip()
    try:
        UUID(offering_id)
    except (ValueError, TypeError, AttributeError):
        raise ExamScoreEntryError(pgettext(_CTX, "Fənn açılışı tapılmadı.")) from None
    offering = (
        CourseOffering.objects.filter(organization=organization, pk=offering_id)
        .select_related("subject", "period", "group", "instructor")
        .first()
        if offering_id
        else None
    )
    if offering is None:
        raise ExamScoreEntryError(pgettext(_CTX, "Fənn açılışı tapılmadı."))
    return offering


def _collect_rows(request):
    """POST açarlarından sətir siyahısı: ``score__<enr>`` + eyni sonluqlu köməkçilər.

    2026-09-12: səbəb/qeyd artıq BİR DƏFƏ (dialoqda, ``reason`` / ``note``)
    verilir və hər dəyişən sətrə tətbiq olunur; köhnə sətir-səviyyə
    ``reason__<enr>`` / ``note__<enr>`` / ``evidence__<enr>`` sahələri də
    oxunur (üstünlük sətir-səviyyəyə).
    """
    batch_reason = (request.POST.get("reason") or "").strip()
    batch_note = (request.POST.get("note") or "").strip()
    batch_kind = (request.POST.get("kind") or "").strip()
    question_count = service.exam_score_questions.QUESTION_COUNT_MAX
    rows = []
    for key, raw in request.POST.items():
        if not key.startswith("score__"):
            continue
        enrollment_id = key[len("score__") :]
        rows.append(
            {
                "enrollment_id": enrollment_id,
                "score": raw,
                "question_scores": _question_fields(request, enrollment_id, question_count),
                "kind": batch_kind,
                "reason": (request.POST.get(f"reason__{enrollment_id}") or "").strip() or batch_reason,
                "note": (request.POST.get(f"note__{enrollment_id}") or "").strip() or batch_note,
                "evidence": request.FILES.get(f"evidence__{enrollment_id}"),
            }
        )
    return rows


def _question_fields(request, enrollment_id, question_count):
    """``q__<enr>__1..n`` sahələri → xam siyahı (sonuncu dolu sahəyə qədər); heç biri yoxdursa ``None``.

    Sual sayından artıq (JS-in söndürdüyü) sahələr brauzerdən gəlmir; gəlsə
    belə servis vərəqin ``question_count``-u ilə rədd edir (fail-closed).
    """
    values = [request.POST.get(f"q__{enrollment_id}__{index}") for index in range(1, question_count + 1)]
    if all(value is None for value in values):
        return None
    while values and (values[-1] is None or not str(values[-1]).strip()):
        values.pop()
    return [value if value is not None else "" for value in values]


def _handle_save(request, organization, next_url):
    """Toplu yadda saxlama — partiya yaradılır, sətirlər servis qatında bir-bir yazılır."""
    action = (request.POST.get("action") or "").strip()
    if action != "save_scores":
        raise ExamScoreEntryError(pgettext(_CTX, "Naməlum əməliyyat."))

    offering = _offering_or_error(request, organization)
    # Unit-scoped aktor (dekan/kafedra müdiri `exam.*` ilə) yalnız öz alt-ağacına
    # yaza bilər — servis qatında fail-closed yoxlanır.
    if not _is_superadmin_user(request.user):
        service.assert_offering_in_actor_scope(request.user, organization, offering)

    # 2026-09-26: bitmiş dövr kilidi — partiya (və skan faylı) yaranmazdan ƏVVƏL
    # yoxlanır; servis (`save_roster_scores`) eyni qapını yenidən tətbiq edir.
    correction_mode = _past_period_precheck(request, organization, offering)
    metadata = sheets_service.sheet_metadata_from_post(request.POST, request.FILES, offering=offering)
    with transaction.atomic():
        sheet = sheets_service.create_sheet(
            offering=offering,
            by_user=request.user,
            source=ExamScoreSheetSource.MANUAL,
            request=request,
            **metadata,
        )
        result = service.save_roster_scores(
            offering=offering,
            rows=_collect_rows(request),
            by_user=request.user,
            request=request,
            sheet=sheet,
            correction_mode=correction_mode,
        )
        sheet = sheets_service.finalize_sheet(sheet, result, by_user=request.user, request=request)

    if result["written"]:
        messages.success(request, _written_message(result["written"], result["skipped"]))
    elif not result["errors"]:
        messages.info(request, pgettext(_CTX, "Dəyişiklik yoxdur — heç bir bal yenilənmədi."))
    for student_name, problem in result["errors"]:
        messages.error(request, f"{student_name}: {problem}")

    # `next` onsuz da açılışı daşıyırsa parametr təkrarlanmasın (URL təmizliyi).
    return _append_query_params(
        next_url,
        ese_offering="" if f"ese_offering={offering.pk}" in next_url else str(offering.pk),
        ese_saved="1" if result["written"] else "",
    )


def _past_period_precheck(request, organization, offering) -> bool:
    """Bitmiş dövr qaydası — partiya yaranmazdan ƏVVƏL.

    İcazəsiz aktorun ``correction_mode``-u ``PermissionDenied``; hər yazının
    təqdimatlı olduğu halda (düzəliş rejimi və ya 60 gündən köhnə dövr) səbəb +
    qeyd + skan ƏVVƏLCƏDƏN tələb olunur (yarımçıq partiya yaranmasın). Yazılmış
    balın rejimsiz dəyişdirilməsi sətir-sətir servisdə rədd olunur. Nəticə —
    servisə ötürülən ``correction_mode`` bayrağı; cari dövrdə əlavə sorğu yoxdur.
    """
    lock = service.exam_score_period_lock
    correction_mode = lock.correction_mode_requested(request.POST)
    policy = lock.write_policy(
        user=request.user, organization=organization, offering=offering, correction_mode=correction_mode
    )
    if policy.every_write_needs_submission:
        lock.require_submission(
            reason=(request.POST.get("reason") or "").strip(),
            note=(request.POST.get("note") or "").strip(),
            evidence=lock.submission_evidence(request.FILES),
        )
    return correction_mode


def _written_message(written, skipped):
    """Nəticə mesajı — msgid-lərdə `%` yoxdur (i18n qapısı tələbi)."""
    head = pgettext(_CTX, "bal yazıldı")
    tail = pgettext(_CTX, "sətir dəyişmədi")
    if not skipped:
        return f"{written} {head}."
    return f"{written} {head} · {skipped} {tail}."


__all__ = ["exam_score_entry", "ExamScoreEntryError", "_can_manage", "_resolve_target_org", "_offering_or_error"]

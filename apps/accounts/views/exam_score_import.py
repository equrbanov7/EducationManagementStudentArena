"""İmtahan Mərkəzi — yazılı imtahan ballarının FAYLDAN köçürülməsi (JSON endpoint-lər).

Sahib (2026-09-12): «tələbələrin balları sistemə yüklənsin». Üç marşrut:

* ``exam_score_import_template`` — seçilmiş açılışın siyahısı ilə DOLDURULMUŞ
  şablon (GET, .xlsx / .csv);
* ``exam_score_import_preview`` — QURU İCRA: fayl yüklənir, sətir-sətir yoxlanılır,
  HEÇ NƏ YAZILMIR (POST, multipart);
* ``exam_score_import_apply`` — tətbiq: partiya (``ExamScoreSheet``) + sətir başına
  savepoint, yazı YALNIZ ``registrar.exam_score_entry`` servisindən keçir
  (POST, multipart).

Hər üçü FAIL-CLOSED: ``final_score.entry`` (+ superadmin) və açılışın struktur
əhatəsi olmayan aktor 403 alır. Ön baxış və tətbiq EYNİ plan qurucusundan
keçir («gördüyün nəticə = alacağın nəticə»); fayl serverdə saxlanılmır.

2026-09-14 (W6 `w6paper`, məlum açıq məqamlar — `docs/features/kagiz_imtahan_bali.md` §10):
* şablon vərəqin sual şəbəkəsi və imtahan növü ilə gəlir (``?question_count=``
  / ``?question_max=`` / ``?exam_kind=``; parametr yoxdursa sonuncu vərəqin
  dəyərləri — vərəq məlumatları kartının göstərdiyi ilə eyni);
* quru icra da tətbiqlə EYNİ POST şəbəkəsini alır — ön baxışda 3 sual seçilibsə
  S4 dəyəri tətbiqdəki kimi rədd olunur (əvvəl ön baxış defolt şəbəkə ilə gedirdi).

2026-09-26: bitmiş dövrdə ilk daxiletmə sətirləri İmtahan Mərkəzinə açıqdır (60
gündən köhnə dövrdə təqdimatla); yazılmış balı DƏYİŞƏN sətirlər rejimsiz xətadır —
yalnız RİM rəhbəri / superadmin düzəliş rejimində (``correction_mode=1``) + tam
təqdimatla (``exam_score_period_lock``). Ön baxış eyni qaydanı göstərir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.registrar.models import CorrectionReason, ExamScoreSheetSource
from apps.registrar.public import exam_score_entry as service
from apps.registrar.public import exam_score_import as importer
from apps.registrar.public import exam_score_sheets as sheets_service
from core.write_rate_limit import score_write_rate_limited

from ._helpers import _is_superadmin_user
from .exam_score_entry import ExamScoreEntryError, _can_manage, _offering_or_error, _resolve_target_org

_CTX = "accounts.exam_score_entry"
#: Sual şəbəkəsinin təmiz validasiyası (``clean_question_grid``) — `exam_score_entry`
#: fasadı onu ``service.exam_score_questions`` kimi daşıyır (accounts registrar-ın
#: privat modulunu birbaşa import etmir).
questions = service.exam_score_questions


def _denied(message=""):
    return JsonResponse(
        {
            "ok": False,
            "error": "permission_denied",
            "message": message
            or pgettext(_CTX, "Bu bölmə yalnız imtahan balı daxil etmə səlahiyyəti olanlar üçündür."),
        },
        status=403,
    )


def _bad(code, message, status=400):
    return JsonResponse({"ok": False, "error": code, "message": message}, status=status)


def _gate(request):
    """``(organization, offering, error_response)`` — icazə + əhatə qapısı (fail-closed)."""
    organization = _resolve_target_org(request)
    if organization is None or not _can_manage(request.user, organization):
        return None, None, _denied()
    offering_id = request.POST.get("offering_id") or request.GET.get("offering") or ""
    try:
        offering = _offering_or_error(request, organization, offering_id)
    except ExamScoreEntryError as exc:
        return organization, None, _bad("offering_not_found", str(exc), status=404)
    if not _is_superadmin_user(request.user):
        try:
            service.assert_offering_in_actor_scope(request.user, organization, offering)
        except PermissionDenied as exc:
            return organization, None, _denied(str(exc))
    return organization, offering, None


def _clamp(value, low, high):
    """Sonuncu vərəqin şəbəkə dəyərini cari hədlərə sıx (``None`` / yad mətn → ``None`` = defolt)."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(low, min(high, number))


def _grid_from_params(params, *, defaults=None) -> dict:
    """``{"question_count", "question_max", "exam_kind"}`` — sorğu parametrlərindən, təmizlənmiş.

    Boş parametr ``defaults``-a (sonuncu vərəq) düşür; o da yoxdursa
    ``clean_question_grid`` defoltu (5 × 10, yazılı). Yanlış dəyər →
    ``ValidationError`` (çağıran 400 qaytarır). Sonuncu vərəqdən gələn dəyər
    cari tavana SIXILIR (tavan 10 qaydasından ƏVVƏLKİ vərəqlərdə 20 var —
    parametrsiz endirmə 400 verməməlidir); açıq parametr sıxılmır, rədd olunur.
    """
    defaults = defaults or {}
    count_raw = params.get("question_count")
    max_raw = params.get("question_max")
    kind_raw = params.get("exam_kind")
    if count_raw is None or count_raw == "":
        count_raw = _clamp(defaults.get("question_count"), 0, questions.QUESTION_COUNT_MAX)
    if max_raw is None or max_raw == "":
        max_raw = _clamp(defaults.get("question_max"), 1, questions.QUESTION_MAX_CEILING)
    if not kind_raw:
        kind_raw = defaults.get("exam_kind")
    question_count, question_max = questions.clean_question_grid(count_raw, max_raw)
    return {
        "question_count": question_count,
        "question_max": question_max,
        "exam_kind": sheets_service.clean_exam_kind(kind_raw),
    }


@never_cache
@login_required
@require_GET
def exam_score_import_template(request):
    """Siyahı ilə doldurulmuş şablon (Tələbə № · FİN · Ad Soyad · Qrup · İmtahan növü · Cari bal · Bal · S1..Sn).

    W6 (2026-09-14): S sütunlarının sayı və tavanı ``?question_count`` /
    ``?question_max``-dan (JS vərəq kartından ötürür); parametr yoxdursa sonuncu
    vərəqin şəbəkəsi — kartın ilkin dəyərləri ilə eyni mənbə (``latest_sheet_defaults``).
    """
    _organization, offering, error = _gate(request)
    if error is not None:
        return error
    fmt = "csv" if (request.GET.get("format") or "").strip().lower() == "csv" else "xlsx"
    defaults = sheets_service.latest_sheet_defaults(sheets_service.sheets_for_offering(offering=offering, limit=1))
    try:
        grid = _grid_from_params(request.GET, defaults=defaults)
    except ValidationError as exc:
        return _bad("validation_error", " ".join(exc.messages))
    roster = service.roster_for_offering(offering=offering)
    payload, content_type, filename = importer.build_template(roster=roster, fmt=fmt, **grid)
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _plan_from_request(request, offering):
    """``(roster, plan, error_response)`` — faylı oxuyub planı qurur (ön baxış = tətbiq).

    W6 (2026-09-14): plan POST-dakı vərəq şəbəkəsi (``question_count`` /
    ``question_max`` / ``exam_kind``) ilə qurulur — ``sheet_metadata_from_post``
    tətbiqdə EYNİ sahələri eyni funksiyalarla təmizləyir, ona görə ön baxışın
    rədd etdiyi sətri tətbiq də rədd edir (və əksinə). Boş sahə = defolt 5 × 10.
    """
    try:
        rows = importer.read_rows(request.FILES.get("file"))
    except importer.ImportFileError as exc:
        return None, None, _bad(exc.code, exc.message)
    try:
        grid = _grid_from_params(request.POST)
    except ValidationError as exc:
        return None, None, _bad("validation_error", " ".join(exc.messages))
    roster = service.roster_for_offering(offering=offering)
    return roster, importer.build_plan(roster=roster, rows=rows, **grid), None


def _payload(plan, roster, *, applied=False, result=None, sheet=None):
    summary = importer.summarize(plan, roster=roster)
    data = {
        "ok": True,
        "applied": applied,
        "summary": summary,
        "needs_justification": importer.needs_justification(plan),
        "rows": plan,
    }
    if result is not None:
        data["result"] = {
            "written": result["written"],
            "skipped": result["skipped"],
            "failed": result["failed"],
            "total": result["total"],
        }
    if sheet is not None:
        data["sheet"] = sheets_service.sheet_row(sheet)
    return data


def _period_policy(request, organization, offering):
    """``(policy, error_response)`` — bitmiş dövr qaydası (icazəsiz aktorun ``correction_mode``-u 403)."""
    lock = service.exam_score_period_lock
    try:
        policy = lock.write_policy(
            user=request.user,
            organization=organization,
            offering=offering,
            correction_mode=lock.correction_mode_requested(request.POST),
        )
    except PermissionDenied as exc:
        return None, _denied(str(exc))
    return policy, None


def _apply_period_rules(plan, policy):
    """Bitmiş dövrdə (rejimsiz) yazılmış balı DƏYİŞƏN sətirlər xəta olur — ön baxış = tətbiq.

    Sahib (2026-09-26): «İM də edə bilsin» — ilk daxiletmə sətirləri qalır;
    dəyişiklik isə yalnız RİM rəhbərinin düzəliş rejimindədir.
    """
    if not policy.changes_blocked:
        return plan
    message = " ".join(service.exam_score_period_lock.change_blocked_error().messages)
    for item in plan:
        if item["status"] == importer.STATUS_CHANGE:
            item["status"] = importer.STATUS_ERROR
            item["message"] = message
    return plan


def _needs_submission(plan, policy) -> bool:
    """Tətbiq təqdimat (səbəb + qeyd + skan) tələb edirmi — JS paneli və server eyni qaydadan."""
    if policy.every_write_needs_submission:
        return any(item["status"] in (importer.STATUS_NEW, importer.STATUS_CHANGE) for item in plan)
    return importer.needs_justification(plan)


@never_cache
@login_required
@require_POST
def exam_score_import_preview(request):
    """Quru icra — nə yazılacaq, nə ötürüləcək, harada xəta var."""
    organization, offering, error = _gate(request)
    if error is not None:
        return error
    policy, error = _period_policy(request, organization, offering)
    if error is not None:
        return error
    roster, plan, error = _plan_from_request(request, offering)
    if error is not None:
        return error
    plan = _apply_period_rules(plan, policy)
    data = _payload(plan, roster)
    data["needs_justification"] = _needs_submission(plan, policy)
    return JsonResponse(data)


def _justification_error(plan, request, policy):
    """Təqdimat lazımdırsa səbəb + qeyd + skan (partiya sənədi) BİRLİKDƏ tələb olunur.

    Servis onsuz da hər sətri ayrıca rədd edərdi; burada ƏVVƏLCƏDƏN yoxlanır ki,
    yarımçıq partiya (yeni ballar yazılıb, dəyişikliklər rədd olunub) yaranmasın —
    operator quru icrada K dəyişikliyi görüb, dialoqda üçünü də verir.

    2026-09-26: düzəliş rejimində və 60 gündən köhnə bitmiş dövrdə HƏR yazı
    təqdimatlıdır; skan paneldəki fayl sahəsindən (``justification_evidence``)
    və ya vərəq kartından.
    """
    if not _needs_submission(plan, policy):
        return None
    reason = (request.POST.get("reason") or "").strip()
    note = (request.POST.get("note") or "").strip()
    evidence = service.exam_score_period_lock.submission_evidence(request.FILES)
    if reason not in CorrectionReason.values or not note or evidence is None:
        if policy.every_write_needs_submission:
            return _bad(
                "submission_required",
                pgettext(
                    _CTX,
                    "Bitmiş dövrdə hər yazı təqdimat tələb edir — səbəb, qeyd və skan edilmiş sənəd məcburidir.",
                ),
            )
        return _bad(
            "justification_required",
            pgettext(_CTX, "Yazılmış balı dəyişən sətirlər var — səbəb, qeyd və skan edilmiş sənəd tələb olunur."),
        )
    return None


@never_cache
@login_required
@require_POST
@score_write_rate_limited("exam_score_import_apply")  # F-15 (2026-09-14)
def exam_score_import_apply(request):
    """Tətbiq — partiya + sətir başına savepoint; bir pis sətir faylı dayandırmır."""
    organization, offering, error = _gate(request)
    if error is not None:
        return error
    # Bitmiş dövr qaydası (2026-09-26) — fayl oxunmazdan və partiya yaranmazdan ƏVVƏL.
    policy, error = _period_policy(request, organization, offering)
    if error is not None:
        return error
    roster, plan, error = _plan_from_request(request, offering)
    if error is not None:
        return error
    plan = _apply_period_rules(plan, policy)
    error = _justification_error(plan, request, policy)
    if error is not None:
        return error
    upload = request.FILES.get("file")
    try:
        metadata = sheets_service.sheet_metadata_from_post(request.POST, request.FILES, offering=offering)
        with transaction.atomic():
            sheet = sheets_service.create_sheet(
                offering=offering,
                by_user=request.user,
                source=ExamScoreSheetSource.IMPORT,
                original_filename=getattr(upload, "name", "") or "",
                request=request,
                **metadata,
            )
            result = importer.apply_plan(
                offering=offering,
                plan=plan,
                by_user=request.user,
                request=request,
                sheet=sheet,
                reason=(request.POST.get("reason") or "").strip(),
                note=(request.POST.get("note") or "").strip(),
                correction_mode=policy.correction_mode,
            )
            sheet = sheets_service.finalize_sheet(sheet, result, by_user=request.user, request=request)
    except ValidationError as exc:
        return _bad("validation_error", " ".join(exc.messages))
    except PermissionDenied as exc:
        return _denied(str(exc))
    data = _payload(plan, roster, applied=True, result=result, sheet=sheet)
    data["needs_justification"] = _needs_submission(plan, policy)
    return JsonResponse(data)


__all__ = ["exam_score_import_apply", "exam_score_import_preview", "exam_score_import_template"]

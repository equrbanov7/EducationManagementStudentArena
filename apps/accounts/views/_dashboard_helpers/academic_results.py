"""Akademik (registrar/jurnal) fənn nəticələri — "Nəticələrim" səthi üçün.

NİYƏ VAR
--------
"Nəticələrim" tarixən YALNIZ yeni sistemin səthlərindən yığırdı: ``ExamAttempt``,
``Submission`` (sərbəst işlər), ``LabSubmission``, ``ProjectSubmission``. Köhnə
MyEdu sistemindən köçürülmüş tələbədə belə sətir ÜMUMİYYƏTLƏ yoxdur — onların
bütün tədris tarixçəsi registrar tərəfindədir (``Enrollment`` + ``FinalGrade`` +
``ComponentScore`` + ``ResitRecord``). Nəticə: ekran tam sıfır görünürdü
("Hamısı 0, İmtahanlar 0, ...") halbuki tələbənin illərlə nəticəsi bazada idi.

NƏ ETMİR
--------
Keçmə/kəsr/hərf/ÜOMG məntiqini TƏKRAR YAZMIR. Bütün rəqəmlər registrar fasadından
(``registrar.public.student_academic_record_rows`` →
``transcript.build_student_overall_record``) gəlir — "Ümumi tədris məlumatı"
bölməsini qidalandıran EYNİ qurucu. Ona görə iki səth arasında drift mümkün deyil.
Bu modul yalnız hazır sətirləri "Nəticələrim" kart müqaviləsinə (title/kind/score/
status/…) çevirir.

Bu bölmə RƏSMİ SƏNƏD DEYİL — sadəcə ekranda nəticə görüntüsüdür. PDF/yükləmə
düyməsi və transkriptə keçid QƏSDƏN yoxdur; ``STUDENT_TRANSCRIPT_SELF_SERVICE``
bayrağına toxunulmur (2026-08 qərarı: rəsmi transkript tələbədən gizlidir).
"""

from __future__ import annotations

from datetime import datetime, time

from django.conf import settings
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.registrar import exam_eligibility

from .._helpers import _get_active_organization
from .formatters import _format_score_display

# Kartın sol ikonu + növ etiketi (mövcud `_standard_item_type_meta` cədvəlinə
# paralel, amma akademik sətir registrar tərəfindən gəldiyi üçün ayrıca).
ACADEMIC_ICON = "fas fa-book-open"
ACADEMIC_TYPE_LABEL = pgettext_lazy("profile.results.academic", "Fənn nəticəsi")

_REQUEST_CACHE_ATTR = "_ems_my_results_academic_record"

FAIL_REASON_LABELS = {
    "qb": pgettext_lazy(
        "profile.results.academic",
        "Q/b-dan kəsilib — imtahana buraxılmayıb (fənn yenidən keçilməli)",
    ),
    "exam25": pgettext_lazy(
        "profile.results.academic",
        "İmtahandan kəsilib — 25 faiz ödənişlə təkrar imtahan hüququ",
    ),
    "total": pgettext_lazy("profile.results.academic", "Ümumi baldan kəsilib"),
}

OUTCOME_LABELS = {
    "pass": pgettext_lazy("profile.results.academic", "Keçdi"),
    "fail": pgettext_lazy("profile.results.academic", "Kəsildi"),
    "barred": pgettext_lazy("profile.results.academic", "Kəsilir"),
    "progress": pgettext_lazy("profile.results.academic", "Davam edir"),
    # Tarixi/köçürülmüş semestr, köhnə sistemdə nəticə yoxdur. «Davam edir»
    # DEYİL: semestr bağlanıb, sadəcə məlumat yazılmayıb (bax
    # :mod:`apps.registrar.exam_eligibility` — 1-ci sərhəd halı).
    "legacy_no_result": exam_eligibility.NO_LEGACY_RESULT_LABEL,
}


def _period_sort_datetime(period):
    """Semestrin bitmə tarixi → siyahı sıralaması üçün datetime.

    "Nəticələrim" bütün kartları vahid tarix oxu üzrə sıralayır, akademik sətirdə
    isə "təhvil vaxtı" anlayışı yoxdur — semestrin BİTMƏ (yoxdursa başlama)
    tarixi götürülür. Naive və aware datetime-ları müqayisə etmək Python-da
    ``TypeError`` verir, ona görə awareness ``timezone.now()`` ilə eyni olmalıdır
    (``USE_TZ``).
    """
    raw = getattr(period, "end_date", None) or getattr(period, "start_date", None)
    if raw is None:
        return None
    stamp = datetime.combine(raw, time.min)
    if not settings.USE_TZ:
        return stamp
    try:
        return timezone.make_aware(stamp, timezone.get_current_timezone())
    except Exception:  # pragma: no cover — DST kənar halı; sıralama itir, sətir qalır
        return None


def _outcome_code(result) -> str:
    if result.get("barred"):
        return "barred"
    if result.get("passed"):
        return "pass"
    if result.get("failed"):
        return "fail"
    if result.get("status_code") == exam_eligibility.STATUS_LEGACY_NO_RESULT:
        return "legacy_no_result"
    return "progress"


def academic_record_for(request) -> dict:
    """Tələbənin akademik qeydi (semestrlərə bölünmüş) — sorğu daxilində keşlənir.

    Qurucu bahalıdır (hər qeydiyyat üçün giriş balı + yekun + təkrar imtahan
    hesablanır), ona görə eyni sorğuda ikinci dəfə çağırılmasın.
    """
    cached = getattr(request, _REQUEST_CACHE_ATTR, None)
    if cached is not None:
        return cached

    organization = _get_active_organization(request)
    if organization is None:
        data = {"has_record": False, "semesters": [], "year_options": [], "season_options": []}
    else:
        from apps.registrar.public import student_academic_record_rows

        data = student_academic_record_rows(request, organization=organization)

    setattr(request, _REQUEST_CACHE_ATTR, data)
    return data


def count_academic_items(request) -> int:
    """Akademik sətirlərin ÜMUMİ sayı (il/semestr süzgəcindən asılı olmayan).

    Ağır qeyd artıq bu sorğuda qurulubsa oradan sayılır (əlavə sorğu YOX), əks
    halda registrar fasadının ucuz ``COUNT(*)``-ı çağırılır — tab/badge sayğacı
    üçün bütün transkript aqreqasiyasını işə salmaq lazım deyil.
    """
    cached = getattr(request, _REQUEST_CACHE_ATTR, None)
    if cached is not None:
        return sum(len(semester.get("rows") or []) for semester in cached.get("semesters") or [])

    organization = _get_active_organization(request)
    if organization is None:
        return 0

    from apps.registrar.public import count_student_academic_record_rows

    return count_student_academic_record_rows(request, organization=organization)


def academic_filter_options(request) -> tuple[list, list]:
    """(il, semestr) filtr açılışları — qurucunun ÖZ verdiyi siyahılar."""
    data = academic_record_for(request)
    return list(data.get("year_options") or []), list(data.get("season_options") or [])


def collect_academic_items(request, *, year="", season="") -> list[dict]:
    """Akademik fənn nəticələrini "Nəticələrim" kart sözlüklərinə çevirir.

    ``year`` / ``season`` boş deyilsə yalnız uyğun semestr sətirləri qaytarılır
    (dəyərlər ``academic_filter_options``-dan gələn xam etiketlərdir).
    """
    data = academic_record_for(request)
    if not data.get("has_record"):
        return []

    year = (year or "").strip()
    season = (season or "").strip()

    items: list[dict] = []
    for semester in data.get("semesters") or []:
        period = semester.get("period")
        period_year = getattr(period, "year_display", "") or ""
        period_season = semester.get("season") or ""
        if year and period_year != year:
            continue
        if season and period_season != season:
            continue

        sort_at = _period_sort_datetime(period)
        period_label = " · ".join(part for part in (period_year, period_season) if part)

        for row in semester.get("rows") or []:
            items.append(_build_item(row, period_label=period_label, sort_at=sort_at))
    return items


def _build_item(row, *, period_label, sort_at) -> dict:
    """Bir fənn sətri → kart sözlüyü. Heç bir hesablama YOX — yalnız formatlama."""
    result = row["result"]
    subject = row["subject"]
    teacher_name = row.get("teacher_name") or ""
    is_definite = bool(result.get("passed") or result.get("failed"))
    outcome = _outcome_code(result)

    # Axtarış mövcud `_collect_my_results` filtrindən keçir (title/kind/type_label),
    # ona görə fənn kodu + müəllim adı `kind`-ə yığılır ki, hər ikisi axtarılsın.
    kind_parts = [part for part in (getattr(subject, "code", "") or "", teacher_name) if part]

    return {
        "category": "academic",
        "title": getattr(subject, "name", "") or getattr(subject, "code", "") or "",
        "kind": " · ".join(kind_parts),
        "icon": ACADEMIC_ICON,
        "type_label": ACADEMIC_TYPE_LABEL,
        # Akademik sətirdə "təhvil vaxtı" yoxdur — kartda semestr etiketi göstərilir;
        # `sort_at` yalnız sıralama üçündür (bax `_period_sort_datetime`).
        "submitted_at": None,
        "sort_at": sort_at,
        "status": "graded" if is_definite else "pending",
        "status_raw": OUTCOME_LABELS[outcome],
        "score": f"{_format_score_display(result['total'])} / 100" if is_definite else None,
        "score_percent": "",
        "feedback": result.get("comment") or "",
        "detail_url": "",  # akademik sətrin detal səhifəsi YOXDUR (rəsmi sənəd deyil)
        "academic": {
            "period_label": period_label,
            "credit": row.get("credit") or 0,
            "teacher_name": teacher_name,
            "entry_score": result.get("entry_score"),
            "exit_score": result.get("effective_exam") if result.get("graded") else None,
            "total": result.get("total") if is_definite else None,
            "letter": result.get("letter") if row.get("in_gpa") else "",
            "outcome": outcome,
            "outcome_label": OUTCOME_LABELS[outcome],
            "fail_reason": row.get("fail_reason") or "",
            "fail_reason_label": FAIL_REASON_LABELS.get(row.get("fail_reason") or "", ""),
            # Bunlar kanonik hesabın hissəsi deyil: registrar fasadı köhnə
            # mənbə sətirlərini clamp-siz və çoxluq itirmədən ayrıca verir.
            "legacy_grade_facts": list(row.get("legacy_grade_facts") or []),
            "legacy_grade_review_required": bool(row.get("legacy_grade_review_required")),
            # Sətir səviyyəli nişan/qeyd — registrar fasadında hesablanır
            # (``legacy_grade_read.attach_legacy_provenance``).  Kart onu OLDUĞU
            # KİMİ ötürür: «qeyd görünsünmü?» qərarı burada TƏKRARLANSA,
            # «Ümumi tədris məlumatı» ilə sürüşərdi.
            "legacy": row.get("legacy"),
        },
    }


__all__ = [
    "academic_filter_options",
    "academic_record_for",
    "collect_academic_items",
    "count_academic_items",
]

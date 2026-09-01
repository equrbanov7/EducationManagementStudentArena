"""Təsdiq ƏHATƏSİ (coverage) analitikası — dizayn təhvili §3.3-ün ikinci tabı.

Kafedra müdiri üçün breakdown TƏHSİL PROQRAMI, dekan/fakültə səviyyəli aktor
üçün KAFEDRA üzrədir (dizaynda `colA` məhz bu iki halda dəyişir).

⚠️ FAIL-CLOSED: bütün sorğular aktorun ``syllabus.review`` əhatəsi ilə
daraldılır. Struktur əhatəsi tapılmayan istifadəçi BOŞ nəticə alır — «əhatə
yoxdursa bütün təşkilat görünsün» davranışı QƏSDƏN yoxdur (bu, əvvəlki
bloker idi). Tenant izolyasiyası əlavə olaraq RLS ilə DB-də qorunur.

«Gecikib» tərifi burada bir yerdədir: dosyenin təsdiqlənmiş versiyası YOXDUR və
semestrin başlama tarixi ARTIQ KEÇİB. Yəni semestri başlamamış fənn gecikmiş
sayılmır — bu, universitet normativindəki «semestr başına qədər sillabus»
tələbinin birbaşa qarşılığıdır.
"""

from __future__ import annotations

from django.utils import timezone

from core.program_codes import program_display_code, program_display_label

from ..constants import PERM_REVIEW, SyllabusStatus
from ..models import Syllabus

#: Breakdown-un qruplaşma açarları (UI `group_by` ilə seçir).
GROUP_PROGRAM = "program"
GROUP_CHAIR = "chair"

#: Hələ qərar gözləyən statuslar — «Baxışda» sütunu.
_IN_REVIEW = frozenset({SyllabusStatus.SUBMITTED.value, SyllabusStatus.REVIEW.value})

#: Bir sətir üçün lazım olan sahələr — TƏK sorğu, N+1 yoxdur.
#:
#: Şifr sahələri BURADA çəkilir: breakdown sətirlərinin etiketi «Ad · şifr»
#: olmalıdır (sahib: «ixtisasın yanında ixtisas kodları olsun»), və eyni etiket
#: filtr açılışını da qidalandırır (``accounts.views.syllabus.review``). Onları
#: sonradan model üzərindən oxumaq N+1 sorğu demək olardı.
_ROW_FIELDS = (
    "program_id",
    "program__name",
    "program__official_code",
    "program__legacy_official_code",
    "chair_unit_id",
    "chair_unit__name",
    "period_id",
    "period__academic_year",
    "period__name",
    "period__start_date",
    "current_version__status",
    "approved_version_id",
)


def _program_bucket(row) -> tuple:
    """Proqram sətrinin ``(ad, şifr)`` cütü — ``core.program_codes`` qaydası ilə.

    Sahələr ƏL İLƏ birləşdirilmir: hər iki nəsil şifr saf funksiyaya verilir,
    o da cari yoxdursa köhnəyə geri çəkilir.
    """
    return (
        (row["program__name"] or "").strip(),
        program_display_code(row["program__official_code"], row["program__legacy_official_code"]),
    )


def _chair_bucket(row) -> tuple:
    """Kafedra sətrində şifr YOXDUR — struktur vahidinin rəsmi şifri yoxdur."""
    return ((row["chair_unit__name"] or "").strip(), "")


#: Qruplaşma açarı → (id sahəsi, sətirdən ``(ad, şifr)`` çıxaran funksiya).
_GROUP_BUCKETS = {
    GROUP_PROGRAM: ("program_id", _program_bucket),
    GROUP_CHAIR: ("chair_unit_id", _chair_bucket),
}


def review_scope_queryset(*, organization, actor):
    """Aktorun ``syllabus.review`` əhatəsindəki dosyelər (fail-closed).

    Müəlliflik burada ROL OYNAMIR: bu, «mənim sillabuslarım» deyil, «mənim
    təsdiqlədiyim sillabuslar» sorğusudur — müəllim öz dosyesini bu səthdə
    görmür.
    """
    queryset = Syllabus.objects.filter(organization=organization, is_active=True)
    if actor.is_superadmin:
        return queryset
    if not actor.has(PERM_REVIEW):
        return queryset.none()
    scope = actor.scope_for(PERM_REVIEW)
    if scope.is_org_wide:
        return queryset
    if not scope.is_unit_scoped:
        return queryset.none()
    return queryset.filter(scope.unit_subtree_q(path_field="chair_unit__path", id_field="chair_unit__id"))


def has_review_scope(*, actor) -> bool:
    """«Əhatə təyin edilməyib» boş vəziyyəti üçün yeganə həqiqət mənbəyi."""
    if actor.is_superadmin:
        return True
    if not actor.has(PERM_REVIEW):
        return False
    return bool(actor.scope_for(PERM_REVIEW).has_structure_access)


def _blank(key, name: str, code: str = "") -> dict:
    """Boş səbət.

    ``name``/``code`` AYRI saxlanılır (cədvəl şifri ayrıca nişan kimi göstərir),
    ``label`` isə ikisinin kanonik birləşməsidir — filtr açılışı və başlıq zolağı
    məhz onu oxuyur, ona görə şifr ORADA DA görünür.
    """
    return {
        "key": key,
        "name": name,
        "code": code,
        "label": program_display_label(name, code),
        "total": 0,
        "approved": 0,
        "in_review": 0,
        "revision": 0,
        "late": 0,
    }


def _tally(bucket: dict, row: dict, *, today) -> None:
    bucket["total"] += 1
    status = row["current_version__status"]
    approved = bool(row["approved_version_id"])
    if approved:
        bucket["approved"] += 1
    if status in _IN_REVIEW:
        bucket["in_review"] += 1
    elif status == SyllabusStatus.REVISION.value:
        bucket["revision"] += 1
    start = row["period__start_date"]
    if not approved and start is not None and start <= today:
        bucket["late"] += 1


def _percent(bucket: dict) -> int:
    total = bucket["total"]
    return round(bucket["approved"] * 100 / total) if total else 0


def _scoped_rows(*, organization, actor, academic_year=None) -> list:
    queryset = review_scope_queryset(organization=organization, actor=actor)
    if academic_year:
        queryset = queryset.filter(period__academic_year=academic_year)
    return list(queryset.values(*_ROW_FIELDS))


def aggregate_breakdown(rows, *, group_by: str = GROUP_PROGRAM, today) -> dict:
    """SAF toplama — DB-yə getmir, verilmiş sətirləri qruplaşdırır.

    Nəticə::

        {"group_by": str,
         "rows": [{"key","name","code","label","total","approved","in_review",
                   "revision","late","percent"}…],
         "totals": {… + "percent"}}

    ``name`` BOŞ ola bilər (proqramı/kafedrası təyin edilməmiş dosye) — mətn
    qərarını UI qatı verir, domen «Təyin edilməyib» kimi sətir icad etmir.
    ``code`` yalnız proqram qruplaşmasında dolur (struktur vahidinin rəsmi şifri
    yoxdur); ``label`` isə ikisinin kanonik birləşməsidir.
    """
    id_field, bucket_parts = _GROUP_BUCKETS.get(group_by, _GROUP_BUCKETS[GROUP_PROGRAM])
    buckets: dict = {}
    totals = _blank("", "")
    for row in rows:
        key = row[id_field]
        bucket = buckets.get(key)
        if bucket is None:
            bucket = buckets[key] = _blank(key, *bucket_parts(row))
        _tally(bucket, row, today=today)
        _tally(totals, row, today=today)

    # Sıralama ADA görədir, etiketə görə yox: şifrin əlavə olunması sıranı
    # dəyişməməlidir (istifadəçi siyahını əlifba sırasında gözləyir).
    ordered = sorted(buckets.values(), key=lambda item: (item["name"] == "", item["name"]))
    for bucket in ordered:
        bucket["percent"] = _percent(bucket)
    totals["percent"] = _percent(totals)
    return {"group_by": group_by, "rows": ordered, "totals": totals}


def aggregate_trend(rows, *, limit: int = 4, today) -> list:
    """Son semestrlər üzrə təsdiq faizi (dizayndakı «Semestr üzrə dinamika»).

    Semestri olmayan «baza sillabus» qeydləri (köçürmə) dinamikaya DAXİL DEYİL —
    onların tarixi yoxdur və uydurulmur.
    """
    periods: dict = {}
    for row in rows:
        period_id = row["period_id"]
        if period_id is None or row["period__start_date"] is None:
            continue
        bucket = periods.get(period_id)
        if bucket is None:
            label = f"{row['period__academic_year']} {row['period__name']}".strip()
            bucket = periods[period_id] = _blank(period_id, label)
            bucket["start"] = row["period__start_date"]
        _tally(bucket, row, today=today)

    ordered = sorted(periods.values(), key=lambda item: item["start"], reverse=True)[:limit]
    for bucket in ordered:
        bucket["percent"] = _percent(bucket)
        bucket.pop("start", None)
    return ordered


def coverage_report(*, organization, actor, academic_year=None, trend_limit: int = 4, today=None) -> dict:
    """BİR sorğu → hər iki qruplaşma + semestr dinamikası.

    Ekran hansı qruplaşmanı göstərəcəyini aktorun əhatəsinə görə seçir (kafedra
    müdiri → proqram, dekan/org → kafedra), amma iki ayrı sorğu ATMIR: sətirlər
    bir dəfə oxunur, toplama Python-da aparılır. Dinamika QƏSDƏN il filtrindən
    kənardır — o, illər arası müqayisədir.
    """
    today = today or timezone.localdate()
    scoped = _scoped_rows(organization=organization, actor=actor)
    filtered = (
        [row for row in scoped if row["period__academic_year"] == academic_year] if academic_year else list(scoped)
    )
    return {
        "by_program": aggregate_breakdown(filtered, group_by=GROUP_PROGRAM, today=today),
        "by_chair": aggregate_breakdown(filtered, group_by=GROUP_CHAIR, today=today),
        "trend": aggregate_trend(scoped, limit=trend_limit, today=today),
    }


def coverage_breakdown(*, organization, actor, academic_year=None, group_by: str = GROUP_PROGRAM, today=None) -> dict:
    """Tək qruplaşma lazım olanda — sorğu + toplama."""
    today = today or timezone.localdate()
    rows = _scoped_rows(organization=organization, actor=actor, academic_year=academic_year)
    return aggregate_breakdown(rows, group_by=group_by, today=today)


def coverage_trend(*, organization, actor, limit: int = 4, today=None) -> list:
    """Tək dinamika lazım olanda — sorğu + toplama."""
    today = today or timezone.localdate()
    return aggregate_trend(_scoped_rows(organization=organization, actor=actor), limit=limit, today=today)


__all__ = [
    "GROUP_CHAIR",
    "GROUP_PROGRAM",
    "aggregate_breakdown",
    "aggregate_trend",
    "coverage_breakdown",
    "coverage_report",
    "coverage_trend",
    "has_review_scope",
    "review_scope_queryset",
]

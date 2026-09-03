"""Kataloq analitikası — ORTAQ qat (göstəricilər CARİ FİLTR dəstinə görə).

──────────────────────────────────────────────────────────────────────────────
ƏSAS QAYDA: analitika cədvəlin GÖRDÜYÜ dəsti sayır
──────────────────────────────────────────────────────────────────────────────
Sahibin tələbi: «statistik datada göstərmək olsun FİLTRDƏN SONRA da». Ona görə
bütün aqreqatlar ``filtered_teachers_qs`` / ``filtered_students_qs`` üzərində
qurulur — yəni scope + struktur + axtarış + status + demoqrafiya filtrləri artıq
tətbiq olunmuş dəst. Dekan fakültəsini süzəndə rəqəmlər həmin fakültəyə aiddir,
bütün təşkilata YOX.

──────────────────────────────────────────────────────────────────────────────
SORĞU BÜDCƏSİ: sətir sayından ASILI DEYİL
──────────────────────────────────────────────────────────────────────────────
Kataloq özü sabit sorğu ilə işləyir; analitika onu pozmamalıdır. Ona görə:

* bütün başlıq göstəriciləri (say, status, cins, yaş səbətləri) **TƏK**
  ``aggregate()`` sorğusundadır — şərti ``Count(..., filter=Q(...))`` ilə;
* bölgülər mənbə cədvəlindən (``Membership`` / ``StudentAcademicRecord``)
  ``GROUP BY`` ilə gəlir — hər bölgü 1 sorğu, sətir sayından asılı deyil;
* struktur adları ``resolve_unit_ancestors`` ilə TOPLU həll olunur (2 sorğu).

⚠️ **Niyə annotasiya üzərində GROUP BY etmirik.** Siyahı queryset-i
``unit_id``/``group_id``-ni korrelyasiyalı ``Subquery`` ilə annotasiya edir;
PostgreSQL belə ifadəyə görə qruplaşmağa icazə vermir («subquery uses ungrouped
column»). Ona görə bölgülər mənbə cədvəlindən, `pk = Subquery(picked)` şərti ilə
alınır: hər şəxs üçün DƏQİQ BİR sətir seçilir (siyahının seçdiyi eyni üzvlük/
qeyd), yəni səbətlərin cəmi ümumi sayla üst-üstə düşür.

Bax: ``apps/accounts/tests/test_people_analytics.py`` (2 və 40 sətirdə eyni
sorğu sayı kilidlənib).
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from django.db.models import Count, OuterRef, Q, Subquery
from django.utils.translation import pgettext_lazy

from .filters import (
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_BLOCKED,
    STATUS_DELETED,
    _shift_years,
    status_q,
)
from .rows import resolve_unit_ancestors

_CTX = "accounts.people.analytics"

#: Bölgüdə göstərilən maksimum səbət; qalanı «Digərləri»ndə cəmlənir.
MAX_BUCKETS = 12

STATUS_ORDER = (STATUS_ACTIVE, STATUS_BLOCKED, STATUS_ARCHIVED, STATUS_DELETED)

STATUS_LABELS = {
    STATUS_ACTIVE: pgettext_lazy(_CTX, "Aktiv"),
    STATUS_BLOCKED: pgettext_lazy(_CTX, "Dayandırılıb"),
    STATUS_ARCHIVED: pgettext_lazy(_CTX, "Arxiv"),
    STATUS_DELETED: pgettext_lazy(_CTX, "Silinib"),
}

GENDER_LABELS = {
    "male": pgettext_lazy(_CTX, "Kişi"),
    "female": pgettext_lazy(_CTX, "Qadın"),
    "unspecified": pgettext_lazy(_CTX, "Göstərilməyib"),
}

UNSET_LABEL = pgettext_lazy(_CTX, "Təyin edilməyib")
OTHERS_LABEL = pgettext_lazy(_CTX, "Digərləri")

#: Yaş səbətləri — (açar, etiket, min yaş, maks yaş). Sərhədlər DAXİLDİR.
AGE_BUCKETS = (
    ("u25", pgettext_lazy(_CTX, "25-dən kiçik"), None, 24),
    ("25_34", pgettext_lazy(_CTX, "25–34 yaş"), 25, 34),
    ("35_44", pgettext_lazy(_CTX, "35–44 yaş"), 35, 44),
    ("45_54", pgettext_lazy(_CTX, "45–54 yaş"), 45, 54),
    ("55_64", pgettext_lazy(_CTX, "55–64 yaş"), 55, 64),
    ("65p", pgettext_lazy(_CTX, "65 və yuxarı"), 65, None),
)


def empty_analytics(kind: str, filters=None) -> dict:
    """Fail-closed zərf: əhatəsi olmayan istifadəçi BOŞ statistika görür."""
    return {
        "has_access": False,
        "kind": kind,
        "total": 0,
        "can_view_demographics": False,
        "status": [],
        "gender": [],
        "age": {"buckets": [], "known": 0, "unknown": 0, "coverage_percent": 0.0},
        "breakdowns": [],
        "workload": [],
        "filters": filters.as_dict() if filters is not None else {},
    }


# ── Başlıq göstəriciləri (TƏK sorğu) ────────────────────────────────────────


def _age_bucket_q(minimum, maximum, today: date) -> Q:
    """Yaş səbətinin doğum-tarixi qarşılığı (indeksdən istifadə edən aralıq)."""
    condition = Q(profile__birth_date__isnull=False)
    if minimum is not None:
        condition &= Q(profile__birth_date__lte=_shift_years(today, minimum))
    if maximum is not None:
        condition &= Q(profile__birth_date__gt=_shift_years(today, maximum + 1))
    return condition


def headline(queryset, *, demographics: bool, today: date | None = None) -> dict:
    """Say + status + cins + yaş səbətləri — HAMISI bir ``aggregate()`` sorğusunda.

    Demoqrafiya açarı yoxdursa cins/yaş ÜMUMİYYƏTLƏ hesablanmır (sorğuya da
    düşmür) — icazəsiz istifadəçi aqreqat şəklində belə demoqrafiya görməsin.
    """
    today = today or date.today()
    aggregates = {"total": Count("pk")}
    for bucket in STATUS_ORDER:
        aggregates[f"st_{bucket}"] = Count("pk", filter=status_q(bucket, prefix=""))
    if demographics:
        aggregates["g_male"] = Count("pk", filter=Q(profile__gender="male"))
        aggregates["g_female"] = Count("pk", filter=Q(profile__gender="female"))
        aggregates["birth_known"] = Count("pk", filter=Q(profile__birth_date__isnull=False))
        for key, _label, minimum, maximum in AGE_BUCKETS:
            aggregates[f"age_{key}"] = Count("pk", filter=_age_bucket_q(minimum, maximum, today))

    row = queryset.aggregate(**aggregates)
    total = row.get("total") or 0

    status_rows = [
        {"key": bucket, "label": str(STATUS_LABELS[bucket]), "count": row.get(f"st_{bucket}") or 0}
        for bucket in STATUS_ORDER
    ]

    if not demographics:
        return {
            "total": total,
            "status": status_rows,
            "gender": [],
            "age": {"buckets": [], "known": 0, "unknown": 0, "coverage_percent": 0.0},
        }

    male = row.get("g_male") or 0
    female = row.get("g_female") or 0
    gender_rows = [
        {"key": "male", "label": str(GENDER_LABELS["male"]), "count": male},
        {"key": "female", "label": str(GENDER_LABELS["female"]), "count": female},
        # «Göstərilməyib» səbəti QƏSDƏN görünür: mənbədə cins ~21 % doludur,
        # onu gizlətmək rəqəmləri yalan göstərərdi (bax lookups.py şərhi).
        {"key": "unspecified", "label": str(GENDER_LABELS["unspecified"]), "count": max(total - male - female, 0)},
    ]

    known = row.get("birth_known") or 0
    age_rows = [
        {"key": key, "label": str(label), "count": row.get(f"age_{key}") or 0}
        for key, label, _minimum, _maximum in AGE_BUCKETS
    ]
    return {
        "total": total,
        "status": status_rows,
        "gender": gender_rows,
        "age": {
            "buckets": age_rows,
            "known": known,
            "unknown": max(total - known, 0),
            "coverage_percent": percent(known, total),
        },
    }


# ── Bölgülər (mənbə cədvəlindən, şəxs başına DƏQİQ BİR sətir) ───────────────


def picked_rows(source_qs, *, user_qs, user_field: str, pick_order, group_fields):
    """Filtrlənmiş şəxslərin SEÇİLMİŞ mənbə sətirləri üzrə ``GROUP BY``.

    ``pk = Subquery(picked)`` şərti siyahının seçdiyi eyni üzvlüyü/qeydi seçir
    (iki kafedrada işləyən müəllim iki dəfə sayılmır) — səbətlərin cəmi ümumi
    sayla üst-üstə düşür. Sorğu sayı: 1, sətir sayından asılı deyil.
    """
    picked_pk = source_qs.filter(**{user_field: OuterRef(user_field)}).order_by(*pick_order).values("pk")[:1]
    return (
        source_qs.filter(**{f"{user_field}__in": user_qs.values("pk")})
        .filter(pk=Subquery(picked_pk))
        .values(*group_fields)
        .annotate(bucket_total=Count("pk"))
        # ⚠️ `order_by` MƏCBURİDİR: modelin `Meta.ordering`-i əks halda GROUP BY-a
        # düşür və bölgü səbətlərini parçalayır (bax MEMORY «Meta.ordering trap»).
        .order_by("-bucket_total")
    )


def percent(count: int, total: int) -> float:
    return round(count * 100.0 / total, 1) if total else 0.0


def to_breakdown(key: str, title, counter: Counter, *, total: int, chart: str = "bar", order: str = "count") -> dict:
    """``Counter`` → qrafik + a11y cədvəli üçün hazır bölgü bloku.

    Səbətlər çoxdursa yalnız ən böyük ``MAX_BUCKETS`` göstərilir, qalanı
    «Digərləri»ndə cəmlənir — həm qrafik oxunaqlı qalır, həm AI yükü kiçilir.

    ``order="label"`` təbii sırası olan oxlar üçündür (kurs, qəbul ili): orada
    «ən çox» sırası oxunu mənasız qarışdırardı.
    """
    if order == "label":
        ordered = sorted(counter.items(), key=lambda item: str(item[0]))
    else:
        ordered = sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))
    head = ordered[:MAX_BUCKETS]
    tail_total = sum(value for _label, value in ordered[MAX_BUCKETS:])
    rows = [{"label": str(label), "count": value, "percent": percent(value, total)} for label, value in head if value]
    if tail_total:
        rows.append({"label": str(OTHERS_LABEL), "count": tail_total, "percent": percent(tail_total, total)})
    return {
        "key": key,
        "title": str(title),
        "chart": chart,
        "total": sum(row["count"] for row in rows),
        "rows": rows,
    }


def structure_counters(rows, *, organization, id_key: str, count_key: str = "bucket_total"):
    """Unit id-lərinə görə fakültə / kafedra / struktur sayğacları — 2 sorğu.

    ``rows`` bölgü sətirləridir (``picked_rows`` nəticəsi). Fərqli unit sayı
    strukturun ölçüsü ilə məhdudlanır, sətir sayı ilə YOX — ona görə sorğu
    büdcəsi sabit qalır.
    """
    unit_ids = {row.get(id_key) for row in rows}
    unit_ids.discard(None)

    ancestors = {}
    if unit_ids:
        from apps.organizations.models import OrgUnit

        units = list(
            OrgUnit.objects.filter(organization=organization, pk__in=unit_ids).only("id", "name", "path", "unit_type")
        )
        ancestors = resolve_unit_ancestors(units, organization=organization)

    faculty: Counter = Counter()
    kafedra: Counter = Counter()
    unit: Counter = Counter()
    for row in rows:
        value = row.get(count_key) or 0
        info = ancestors.get(row.get(id_key)) or {}
        # Açar həmişə SƏTİRDİR: lazy tərcümə proxy-si Counter açarı kimi
        # etibarsızdır (hash/bərabərlik dilə görə dəyişir).
        faculty[info.get("faculty") or str(UNSET_LABEL)] += value
        kafedra[info.get("kafedra") or str(UNSET_LABEL)] += value
        unit[info.get("unit") or str(UNSET_LABEL)] += value
    return faculty, kafedra, unit


def counter_from(rows, label_fn, *, count_key: str = "bucket_total") -> Counter:
    counter: Counter = Counter()
    for row in rows:
        counter[str(label_fn(row) or UNSET_LABEL)] += row.get(count_key) or 0
    return counter


def academic_year_start(today: date | None = None) -> int:
    """Cari tədris ilinin başlanğıc ili (sentyabr sərhədi) — «kurs» hesablaması üçün."""
    today = today or date.today()
    return today.year if today.month >= 9 else today.year - 1


__all__ = [
    "AGE_BUCKETS",
    "GENDER_LABELS",
    "MAX_BUCKETS",
    "OTHERS_LABEL",
    "STATUS_LABELS",
    "STATUS_ORDER",
    "UNSET_LABEL",
    "academic_year_start",
    "counter_from",
    "empty_analytics",
    "headline",
    "percent",
    "picked_rows",
    "structure_counters",
    "to_breakdown",
]

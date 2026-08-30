"""Kataloq analitikasının AI xülasəsi — **PII-siz** yük + mövcud AI servisi.

──────────────────────────────────────────────────────────────────────────────
1. ŞƏXSİ MƏLUMAT AI-a GETMİR (sərt tələb)
──────────────────────────────────────────────────────────────────────────────
Qayda **NAXIŞ TƏMİZLƏYİCİSİ DEYİL, AĞ SİYAHIDIR**: yükə yalnız

* saylar və faizlər;
* sabit siyahıların (choices/enum) etiketləri — status, cins, yaş səbətləri —
  özü də **KODDAKI xəritədən**, gələn datadan YOX;
* təşkilat STRUKTURUNUN adları — fakültə, kafedra, ixtisas, qrup, kurs, qəbul
  ili, akademik status, rol

düşür. Bu siyahıda OLMAYAN hər bölgünün **etiketləri ümumiyyətlə göndərilmir**:
onun yerinə yalnız «neçə fərqli dəyər / neçə nəfər» sayı gedir.

⚠️ **Niyə əvvəlki qat yetmirdi.** Köhnə variant «konstruksiyaya görə PII yoxdur»
sayırdı və yalnız e-poçt/telefon naxışını silirdi. Amma ``Membership.title``
(«Akademik dərəcə / vəzifə») **SƏRBƏST MƏTNDİR** — operator ora
``Dos. Elvin Qurbanov (FIN 5AB7C9D)`` yaza bilər. Naxış nə adı, nə FİN-i tutur,
ona görə həmin sətir AI yükündə olduğu kimi görünürdü. İndi ``title`` kimi
sərbəst mətn mənbəli bölgülərin etiketi **HEÇ VAXT** yükə düşmür.

**Fail-closed və gələcək dəyişikliklər.** Ağ siyahı AÇIQDIR: siyahıda olmayan
açar yükə DÜŞMÜR. Yəni sabah kimsə ``bio`` və ya ``staff_position`` bölgüsü
əlavə etsə, o, səssizcə AI-a getmir — etiketi görünsün deyə bu faylı bilərəkdən
redaktə etmək lazımdır (yəni kod baxışında görünən addım).

Üç qat qoruma:

* **üst səviyyə ağ siyahı** — yükə yalnız ``_ALLOWED_KEYS`` düşür;
* **etiket ağ siyahısı** — ``_LABELLED_BREAKDOWNS`` / ``_WORKLOAD_KEYS`` /
  enum xəritələri; qalanı sayla əvəz olunur;
* **axtarış və filtr mətni GÖNDƏRİLMİR** — operator axtarış xanasına (və ya
  ``?year=`` sorğu parametrinə) şəxsin adını yaza bilər, ona görə oradan yalnız
  «tətbiq olunub» bayrağı və ciddi formata uyğun tədris ili gedir.

``apps/accounts/tests/test_people_analytics.py`` bunu kilidləyir.

──────────────────────────────────────────────────────────────────────────────
2. KEŞ VƏ LİMİT (sahibin köhnə göstərişi — pozulmur)
──────────────────────────────────────────────────────────────────────────────
Çağırış ``apps.exams.services.ai_summary``-yə düşür: cavab **data hash-inə**
(SHA-256) görə keşlənir (TTL 24 saat), rate limit isə YALNIZ keş miss-ində
(real API çağırışında) yeyilir. Data dəyişməyibsə yeni API çağırışı EDİLMİR.
Model layihənin mövcud ``AIConfiguration`` konfiqurasiyasından gəlir.
"""

from __future__ import annotations

import re

from .analytics import AGE_BUCKETS, GENDER_LABELS, STATUS_LABELS
from .constants import GENDER_BUCKETS
from .filters import ALLOWED_STATUSES

#: AI yükünə düşməsinə icazə verilən üst səviyyə açarlar.
_ALLOWED_KEYS = ("kind", "total", "status", "gender", "age", "breakdowns", "workload", "scope")

#: Etiketi AI-a GÖNDƏRİLƏ BİLƏN bölgülər — AĞ SİYAHI (fail-closed).
#:
#: Meyar: etiketin mənbəyi **paylaşılan kataloq sətri** olsun — təşkilat
#: strukturunun adı (fakültə/kafedra/ixtisas/qrup), sabit siyahı (kurs, qəbul
#: ili, akademik status) və ya rol kataloqunun adı. Bunlar bir ŞƏXSİ deyil,
#: şəxslər SİNFİNİ adlandırır.
#:
#: ⚠️ Burada ``title`` QƏSDƏN YOXDUR: ``Membership.title`` şəxs-başına sərbəst
#: mətndir (bir nəfərlik səbətin etiketi məhz həmin şəxsin yazdığı sətirdir).
#: Eyni səbəblə gələcək ``bio`` / ``staff_position`` kimi sahələr də bura
#: ƏLAVƏ EDİLMƏMƏLİDİR.
_LABELLED_BREAKDOWNS = frozenset(
    {
        "faculty",
        "kafedra",
        "unit",
        "program",
        "group",
        "course",
        "admission_year",
        "academic_status",
        "role",
    }
)

#: Dərs yükü göstəriciləri — açar + RƏQƏM. Açarı tanınmayan sətir atılır.
_WORKLOAD_KEYS = frozenset({"offerings", "subjects", "groups", "with_load", "without_load", "avg_offerings", "seats"})

#: Enum sətirlərinin etiketi DATADAN yox, koddakı bu xəritələrdən götürülür.
_STATUS_LABELS = {key: str(label) for key, label in STATUS_LABELS.items()}
_GENDER_LABELS = {key: str(label) for key, label in GENDER_LABELS.items()}
_AGE_LABELS = {key: str(label) for key, label, _minimum, _maximum in AGE_BUCKETS}

#: Bölgü açarı kod tərəfindən verilən sabit slug-dır; formata uymayan açar
#: (yəni datadan gələ bilən sətir) ÜMUMİYYƏTLƏ yükə düşmür.
_SAFE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: Tədris ili yalnız ciddi formatda keçir (``2025/2026``) — `?year=` sorğu
#: parametri operator tərəfindən sərbəst yazıla bilər.
_YEAR_RE = re.compile(r"^\d{4}/\d{4}$")

_MAX_LABEL = 80
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s()\-]{6,}\d")


def scrub_label(value) -> str:
    """Ağ siyahıdan keçmiş etiketin son cilası (ikinci müdafiə xətti).

    ⚠️ Bu, ƏSAS qoruma DEYİL — əsas qoruma ağ siyahıdır (modul şərhinə bax).
    Burada yalnız uzunluq kəsilir, boşluqlar normallaşır və struktur adına
    təsadüfən düşmüş e-poçt/telefon izi silinir.
    """
    text = str(value or "").strip()
    text = _EMAIL_RE.sub("", text)
    text = _PHONE_RE.sub("", text)
    return " ".join(text.split())[:_MAX_LABEL]


def _number(value):
    """Rəqəm sahəsi — sətir gəlsə belə yükə RƏQƏM kimi düşür (və ya 0)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _enum_counts(rows, labels: dict) -> list:
    """Sabit siyahılı sətirlər — etiket KODDAN gəlir, açarı naməlumdursa atılır."""
    result = []
    for row in rows or []:
        key = str(row.get("key") or "")
        if key not in labels:
            continue
        result.append({"key": key, "label": labels[key], "count": int(row.get("count") or 0)})
    return result


def _rows(rows) -> list:
    return [
        {
            "label": scrub_label(row.get("label")),
            "count": int(row.get("count") or 0),
            "percent": float(row.get("percent") or 0.0),
        }
        for row in rows or []
    ]


def _breakdown(item) -> dict | None:
    """Bir bölgü bloku — ağ siyahıdadırsa etiketlərlə, deyilsə YALNIZ sayla."""
    key = str(item.get("key") or "")
    if not _SAFE_KEY_RE.match(key):
        return None
    rows = item.get("rows") or []
    if key in _LABELLED_BREAKDOWNS:
        return {"key": key, "title": scrub_label(item.get("title")), "rows": _rows(rows)}
    # Sərbəst mətn mənbəli (və ya sadəcə tanınmayan) bölgü: heç bir etiket
    # getmir. ⚠️ `distinct_values` göstərilən səbətlərin sayıdır — mənbədə
    # `MAX_BUCKETS` kəsimi olduğu üçün bu, «ən azı bu qədər» deməkdir.
    return {
        "key": key,
        "labels_withheld": True,
        "distinct_values": len(rows),
        "people": sum(int(row.get("count") or 0) for row in rows),
    }


def _workload(items) -> list:
    """Dərs yükü — ağ siyahıdakı açar + rəqəm. Sərbəst mətn ÜMUMİYYƏTLƏ yoxdur."""
    return [
        {"key": str(item.get("key") or ""), "value": _number(item.get("value"))}
        for item in items or []
        if str(item.get("key") or "") in _WORKLOAD_KEYS
    ]


def _scope(filters) -> dict:
    """Filtr vəziyyətinin PII-siz təsviri.

    ⚠️ ``q`` (axtarış mətni) QƏSDƏN yoxdur — orada şəxsin adı ola bilər.
    Struktur filtrləri UUID olduğu üçün AI-a dəyər vermir; yalnız «tətbiq
    olunub» bayrağı göndərilir. ``year``/``season`` da sorğu sətrindən gələn
    SƏRBƏST mətndir: yalnız ciddi formata uyğun tədris ili keçir, semestr isə
    bayrağa çevrilir.
    """
    if filters is None:
        return {}
    data = filters.as_dict()
    year = str(data.get("year") or "").strip()
    status = str(data.get("status") or "")
    gender = str(data.get("gender") or "")
    return {
        "search_applied": bool(data.get("q")),
        "faculty_filter": bool(data.get("faculty")),
        "kafedra_filter": bool(data.get("kafedra")),
        "group_filter": bool(data.get("group")),
        "program_filter": bool(data.get("program")),
        "subject_filter": bool(data.get("subject")),
        "academic_year": year if _YEAR_RE.match(year) else "",
        "season_filter": bool(data.get("season")),
        "status": status if status in ALLOWED_STATUSES else "",
        "gender": gender if gender in GENDER_BUCKETS else "",
        "age_min": _number(data.get("age_min")) if data.get("age_min") is not None else None,
        "age_max": _number(data.get("age_max")) if data.get("age_max") is not None else None,
        "age_unknown_only": bool(data.get("age_unknown")),
    }


def build_ai_payload(analytics: dict, *, filters=None) -> dict:
    """Analitika zərfindən AI üçün AQREQAT-ONLY yük (ağ siyahı, fail-closed)."""
    age = analytics.get("age") or {}
    breakdowns = [_breakdown(item) for item in analytics.get("breakdowns") or []]
    payload = {
        "kind": str(analytics.get("kind") or ""),
        "total": int(analytics.get("total") or 0),
        "status": _enum_counts(analytics.get("status"), _STATUS_LABELS),
        "gender": _enum_counts(analytics.get("gender"), _GENDER_LABELS),
        "age": {
            "buckets": _enum_counts(age.get("buckets"), _AGE_LABELS),
            "known": int(age.get("known") or 0),
            "unknown": int(age.get("unknown") or 0),
            "coverage_percent": float(age.get("coverage_percent") or 0.0),
        },
        "breakdowns": [item for item in breakdowns if item is not None],
        "workload": _workload(analytics.get("workload")),
        "scope": _scope(filters),
    }
    return {key: payload[key] for key in _ALLOWED_KEYS if key in payload}


def generate_analytics_summary(*, analytics: dict, filters=None, language_code=None, user_id=None) -> dict:
    """Kataloq analitikasının AI xülasəsi (keş + rate limit AI servisindədir)."""
    from apps.exams.public import generate_people_analytics_summary

    return generate_people_analytics_summary(
        kind=str(analytics.get("kind") or ""),
        stats=build_ai_payload(analytics, filters=filters),
        language_code=language_code,
        user_id=user_id,
    )


__all__ = ["build_ai_payload", "generate_analytics_summary", "scrub_label"]

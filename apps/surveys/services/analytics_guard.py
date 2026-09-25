"""Açıqlama nəzarəti (disclosure control) — «Sorğu nəticələri» UI-ının BÜTÜN görünüşləri
və ixracı bu qaydalardan keçir (təhlükəsizlik rəyi M-1 / M-2, 2026-09-25).

M-1 — CANLI NƏTİCƏ YOXDUR. Açıq (və ya planlaşdırılmış) kampaniyanın heç bir ortası,
paylanması, şərhi göstərilmir: iki yükləmə arasında «n₂·orta₂ − n₁·orta₁» çıxması bir
tələbənin cavabını açardı. Nəticə YALNIZ effektiv statusu ``closed`` olan (bağlanma
tarixi keçmiş və ya bağlanmış) kampaniyalardan hesablanır (:func:`published_campaigns`).
Açıq kampaniya üçün yalnız iştirak — qəbz sayı səbətlə (:func:`count_bucket`), faiz
5-ə yuvarlaqlaşdırılmış (:func:`round5`).

M-2 — KİÇİK QRUP ÇIXMA İLƏ AÇILMIR:
* SAY HEÇ YERDƏ DƏQİQ GÖSTƏRİLMİR — səbət: «<5», «5+», «10+», «20+», «50+», «100+»…
  (``count_bucket``); kliyent sıralaması/süzgəci səbətin alt həddi ilə (``count_floor``).
  Paylanma yalnız tam faizlə (xam say yoxdur).
* Qardaş xanalar (:func:`sibling_suppress`): görünən cəmin altındakı sətirlərdən gizli
  qalan varsa, gizli xana sayı ≥ 2 VƏ gizli cəm ≥ k olana qədər ən kiçik görünən
  sətirlər də gizlədilir (tək gizli xana cəmdən çıxılaraq heç vaxt bərpa olunmur).
* Kampaniya seçimi DARALDICI filtrdir (:func:`campaign_counts`): seçilmiş kampaniya
  alt-dəstinin sayı bütün bağlı kampaniyalardakı eyni dəstin sayından ``0 < fərq < k``
  qədər fərqlənirsə, dəst/sətir gizlədilir (tamamlayıcı qayda).
* Gizli sətrin heç bir aqreqatı qaytarılmır (:func:`redact`): ``n`` də daxil.
"""

from __future__ import annotations

from django.db.models import Count

from ..constants import Section
from . import filters as flt

#: Göstərilən saylar üçün səbət sərhədləri (aşağı həd → etiket «X+»).
BUCKETS = (5, 10, 20, 50, 100)
#: Gizli sətirdə boşaldılan sahələr (``n`` və iştirak da daxil).
REDACT_KEYS = (
    "n",
    "avg",
    "top2",
    "avg_overall",
    "likert_index",
    "likert_index_pct",
    "recommend_top2",
    "delta_department_overall",
    "delta_org_overall",
    "delta_department_index",
    "delta_org_index",
    "satisfaction",
    "facilities",
    "question_avg",
    "receipts",
    "rate",
)


# ── M-1: yalnız bağlı kampaniyalar ─────────────────────────────────────────


def published_campaigns(campaigns) -> list:
    """Nəticəsi göstərilə bilən kampaniyalar — effektiv status ``closed``."""
    return [row for row in campaigns if row.get("effective_status") == "closed"]


def live_campaigns(campaigns) -> list:
    """Davam edən (açıq/planlaşdırılmış) kampaniyalar — yalnız iştirak göstərilir."""
    return [row for row in campaigns if row.get("effective_status") in ("open", "scheduled")]


# ── Say səbətləri ──────────────────────────────────────────────────────────


def count_floor(n):
    """Səbətin alt həddi (``<5`` → 0); ``None`` → ``None``."""
    if n is None:
        return None
    n = int(n)
    if n >= BUCKETS[-1]:
        return (n // 50) * 50
    floor = 0
    for edge in BUCKETS:
        if n >= edge:
            floor = edge
    return floor


def count_bucket(n) -> str:
    """Göstərilən say etiketi — heç vaxt dəqiq deyil: «<5», «5+», «10+», «20+», «50+», «100+»…"""
    if n is None:
        return "—"
    floor = count_floor(n)
    return "<5" if floor == 0 else f"{floor}+"


def round5(rate):
    """Faiz (0–1) → 5-ə yuvarlaqlaşdırılmış tam faiz (0–100); ``None`` → ``None``."""
    if rate is None:
        return None
    return int(5 * round(float(rate) * 100 / 5))


# ── M-2: qardaş xanalar və gizlətmə ────────────────────────────────────────


def redact(row) -> dict:
    """Gizli sətrin bütün aqreqatlarını (``n`` daxil) silir."""
    for key in REDACT_KEYS:
        if key in row:
            row[key] = None
    return row


def _hide(row, reason="secondary"):
    row["suppressed"] = True
    row["secondary"] = row.get("secondary") or reason == "secondary"
    return row


def sibling_suppress(rows, *, k, total_n, label_key="label") -> list:
    """Görünən cəmin qardaş sətirlərini çıxmaya qarşı qoruyur (bax modul sənədi).

    ``total_n`` — ekranda (başqa yerdə) görünən cəmin DƏQİQ sayı; cəm gizlidirsə ``None``.
    Siyahıya düşməyən qalıq (``total_n − Σ n``) da gizli xana sayılır. Sətirlərin ``n``-i
    burada hələ dəqiq olmalıdır (``redact`` bundan SONRA çağırılır).
    """
    if not rows or total_n is None or not k:
        return rows
    listed = sum(int(row.get("n") or 0) for row in rows)
    unlisted = max(int(total_n) - listed, 0)
    hidden = [row for row in rows if row.get("suppressed") and int(row.get("n") or 0) > 0]
    visible = sorted(
        (row for row in rows if not row.get("suppressed")),
        key=lambda item: (int(item.get("n") or 0), str(item.get(label_key) or "")),
    )

    def exposed():
        cells = len(hidden) + (1 if unlisted else 0)
        amount = sum(int(row.get("n") or 0) for row in hidden) + unlisted
        return cells > 0 and (cells == 1 or amount < k)

    while visible and exposed():
        row = visible.pop(0)
        _hide(row)
        hidden.append(row)
    return rows


def finalize(rows, *, k, total_n, label_key="label") -> list:
    """Qardaş qaydası + gizli sətirlərin aqreqatlarının silinməsi (bütün bölgülər üçün son addım)."""
    sibling_suppress(rows, k=k, total_n=total_n, label_key=label_key)
    for row in rows:
        if row.get("suppressed"):
            redact(row)
    return rows


# ── Kampaniya seçimi daraldıcı filtrdir ────────────────────────────────────


def campaign_counts(organization, scope, filters, campaign_ids, *, key=None, section=Section.TEACHER):
    """Eyni filtrlərlə verilmiş kampaniyalar üzrə say: ``key`` yoxdursa tam ədəd, varsa
    ``{açar: say}`` (tamamlayıcı qaydanın «bütün bağlı kampaniyalar» bazası; 1 sorğu)."""
    queryset = flt.responses(organization, scope, filters, list(campaign_ids), section=section)
    if key is None:
        return queryset.count()
    return dict(queryset.values(key).annotate(c=Count("id")).values_list(key, "c"))


def campaign_narrowed(selected_ids, all_ids) -> bool:
    return bool(all_ids) and set(selected_ids) != set(all_ids)


def complement_ok(n, k, baseline) -> bool:
    """``n ≥ k`` və bazadan fərq 0 və ya ≥ k (F1 ``is_visible`` ilə eyni qayda)."""
    if n is None or n < k:
        return False
    if baseline is None:
        return True
    gap = int(baseline) - int(n)
    return gap <= 0 or gap >= k

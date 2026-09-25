"""Açıqlama nəzarəti (disclosure control) — «Sorğu nəticələri» UI-ının BÜTÜN görünüşləri
və ixracı bu qaydalardan keçir (təhlükəsizlik rəyi M-1 / M-2, 2026-09-25).

M-1 — CANLI NƏTİCƏ YOXDUR. Açıq/planlaşdırılmış kampaniyanın heç bir ortası, paylanması,
şərhi göstərilmir: iki yükləmə arasında «n₂·orta₂ − n₁·orta₁» çıxması bir tələbənin
cavabını açardı. Nəticə YALNIZ effektiv statusu ``closed`` olan kampaniyalardan
hesablanır (:func:`published_campaigns`); davam edən kampaniya üçün yalnız iştirak —
say səbətlə (:func:`count_bucket`), faiz 5-ə yuvarlaqlaşdırılmış (:func:`round5`).

M-2 — KİÇİK QRUP ÇIXMA İLƏ AÇILMIR:
* Say HEÇ YERDƏ dəqiq göstərilmir: «<5», «5+», «10+», «20+», «50+», «100+», sonra 50-lik
  addım (:func:`count_bucket`); kliyent sıralaması səbətin alt həddi ilə (:func:`count_floor`).
  Paylanmalar yalnız tam faizlə verilir (xam say yoxdur).
* Qardaş xanalar (:func:`sibling_suppress`): görünən cəmin altında gizli xana varsa,
  gizli xana sayı ≥ 2 VƏ gizli cəm ≥ k olana qədər ən kiçik görünən sətirlər də
  gizlədilir — tək gizli xana heç vaxt «cəm − görünənlər» ilə bərpa olunmur.
* Gizli sətrin heç bir aqreqatı qaytarılmır, ``n`` də daxil (:func:`redact`).
* KAMPANİYA SEÇİMİ də daraldıcı ölçüdür. Seçilə bilən dövr dəstləri — hər bağlı
  kampaniya, ≥ 2 kampaniyalı tədris ili, «bütün dövrlər» (:func:`campaign_family`).
  İki iç-içə dəst (A ⊂ B) eyni filtrlərlə ``0 < n(B) − n(A) < k`` qədər fərqlənirsə və ya
  B-nin tək-tək gizli kampaniyaları bir xana / cəmi < k olarsa, BÖYÜK dəst (B) gizlədilir
  (:func:`nested_ok`, :func:`nested_hidden_keys`). Tək kampaniya görünüşü (defolt) və
  dinamika nöqtələri buna görə heç vaxt itmir; dəstlər arasındakı kiçik qalıq isə heç
  bir görünən dəstlər fərqi kimi çıxmır.

Bütün kombinasiyaların (filtr × dövr × görünüş) tam qəfəsi yoxlanmır — bu, F1-in
sənədləşdirdiyi qalıq riskdir; UI xam sətir ixrac etmir və dəqiq say vermir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Count

from ..constants import DEFAULT_MIN_GROUP_SIZE, Section
from . import filters as flt

#: Göstərilən saylar üçün səbət sərhədləri (aşağı həd → etiket «X+»).
BUCKETS = (5, 10, 20, 50, 100)
#: Gizli sətirdə boşaldılan sahələr (``n`` və iştirak da daxil).
REDACT_KEYS = (
    "n",
    "avg",
    "top2",
    "bottom2",
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
    "expected",
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
    """Pay (0–1) → 5-ə yuvarlaqlaşdırılmış tam faiz (0–100); ``None`` → ``None``."""
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


def sibling_suppress(rows, *, k, total_n, label_key="label") -> list:
    """Görünən cəmin qardaş sətirlərini çıxmaya qarşı qoruyur (bax modul sənədi).

    ``total_n`` — ekranda (başqa yerdə) görünən cəmin DƏQİQ sayı; cəm gizlidirsə ``None``.
    Siyahıya düşməyən qalıq (``total_n − Σ n``) da gizli xana sayılır. Sətirlərin ``n``-i
    burada hələ dəqiq olmalıdır (:func:`redact` bundan SONRA çağırılır).
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
        row["suppressed"] = True
        row["secondary"] = True
        hidden.append(row)
    return rows


def finalize(rows, *, k, total_n, label_key="label") -> list:
    """Qardaş qaydası + gizli sətirlərin aqreqatlarının silinməsi (bütün bölgülər üçün son addım)."""
    sibling_suppress(rows, k=k, total_n=total_n, label_key=label_key)
    for row in rows:
        if row.get("suppressed"):
            redact(row)
    return rows


def complement_ok(n, k, baseline) -> bool:
    """``n ≥ k`` və bazadan fərq 0 və ya ≥ k (F1 ``is_visible`` ilə eyni qayda)."""
    if n is None or n < k:
        return False
    if baseline is None:
        return True
    gap = int(baseline) - int(n)
    return gap <= 0 or gap >= k


def general_filtered(filters) -> bool:
    """Ümumi bölmədə HƏR filtr daraldıcıdır: cavab tələbənin öz qrupu/ixtisası/fakültəsi
    ilə saxlanılır, ona görə fakültə (və s.) seçimi də kiçik qrup yarada bilər."""
    return any(
        value is not None
        for value in (
            filters.faculty_id,
            filters.department_id,
            filters.teacher_id,
            filters.subject_id,
            filters.group_id,
            filters.program_id,
            filters.course_year,
        )
    )


# ── Kampaniya ölçüsü: iç-içə seçilə bilən dövr dəstləri ────────────────────


@dataclass(frozen=True)
class CampaignFamily:
    """Seçilə bilən bağlı dövr dəstləri (``sets``) və hər kampaniyanın öz k-sı (``thresholds``)."""

    sets: tuple = ()
    thresholds: dict = field(default_factory=dict)


def campaign_family(campaigns) -> CampaignFamily:
    """Hər tək bağlı kampaniya, ≥ 2 kampaniyalı tədris ili və «bütün dövrlər» (təkrarsız)."""
    rows = published_campaigns(campaigns)
    sets = [frozenset([row["id"]]) for row in rows]
    years: dict = defaultdict(list)
    for row in rows:
        if row.get("academic_year"):
            years[row["academic_year"]].append(row["id"])
    sets.extend(frozenset(ids) for ids in years.values() if len(ids) > 1)
    if len(rows) > 1:
        sets.append(frozenset(row["id"] for row in rows))
    unique = []
    for item in sets:
        if item not in unique:
            unique.append(item)
    thresholds = {
        row["id"]: max(int(row.get("min_group_size") or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE) for row in rows
    }
    return CampaignFamily(sets=tuple(unique), thresholds=thresholds)


def _multi(campaign_ids, family) -> bool:
    return family is not None and len(set(campaign_ids or ())) > 1


def per_campaign_counts(organization, scope, filters, campaign_ids, *, key=None, section=Section.TEACHER):
    """``{campaign_id: n}`` və ya (``key`` — sahə adı / adlar kortejı) ``{açar: {campaign_id: n}}``."""
    queryset = flt.responses(organization, scope, filters, list(campaign_ids), section=section)
    if key is None:
        return dict(queryset.values("campaign_id").annotate(c=Count("id")).values_list("campaign_id", "c"))
    fields = (key,) if isinstance(key, str) else tuple(key)
    result: dict = defaultdict(dict)
    for row in queryset.values(*fields, "campaign_id").annotate(c=Count("id")):
        group = row[fields[0]] if len(fields) == 1 else tuple(row[field] for field in fields)
        result[group][row["campaign_id"]] = row["c"]
    return result


def nested_ok(selected_ids, counts, family, k) -> bool:
    """Çox kampaniyalı dəst göstərilə bilərmi (eyni filtrlərlə, ``counts`` — kampaniya üzrə say):

    1. ailədəki hər ÖZ alt-dəstlə fərq 0 və ya ≥ k;
    2. dəstin tək-tək GİZLİ kampaniyaları (öz k-sından az, > 0) bir xana deyil və cəmi ≥ k —
       əks halda «dəst − görünən kampaniyalar» (dinamika nöqtələri) gizli kampaniyanı açardı.
    """
    selected = frozenset(selected_ids or ())
    total = sum(counts.get(campaign_id, 0) for campaign_id in selected)
    for subset in family.sets:
        if subset < selected:
            gap = total - sum(counts.get(campaign_id, 0) for campaign_id in subset)
            if 0 < gap < k:
                return False
    hidden = [
        counts.get(campaign_id, 0)
        for campaign_id in selected
        if 0 < counts.get(campaign_id, 0) < family.thresholds.get(campaign_id, k)
    ]
    return not hidden or (len(hidden) > 1 and sum(hidden) >= k)


def nested_set_ok(organization, scope, filters, campaign_ids, family, k, *, section=Section.TEACHER) -> bool:
    """Dəst səviyyəsində kampaniya qaydası (tək kampaniyada sorğu yoxdur, həmişə keçir)."""
    if not _multi(campaign_ids, family):
        return True
    counts = per_campaign_counts(organization, scope, filters, campaign_ids, section=section)
    return nested_ok(campaign_ids, counts, family, k)


def nested_hidden_keys(organization, scope, filters, campaign_ids, family, k, *, key, section=Section.TEACHER) -> set:
    """Sətir səviyyəsində kampaniya qaydası: gizlədilməli açarlar (tək kampaniyada boş, sorğusuz)."""
    if not _multi(campaign_ids, family):
        return set()
    counts = per_campaign_counts(organization, scope, filters, campaign_ids, key=key, section=section)
    return {group for group, per in counts.items() if not nested_ok(campaign_ids, per, family, k)}

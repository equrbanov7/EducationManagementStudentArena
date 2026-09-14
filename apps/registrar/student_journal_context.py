"""Tələbənin elektron jurnalı (kabinet bölməsi) — görünüş qatının köməkçiləri.

2026-09-12 (tələbə kabineti redizaynı, audit bəndi 7/3). ``apps/registrar/
public.py`` modul-ölçü büdcəsindədir (SOFT_CAP 600); jurnalın görünüş məntiqi
— buraxılış vəziyyəti açarı, xəbərdarlıq siyahısı, KPI sırası, legend və
«bu günün dərsi gizlidir» qeydi — buradadır.  ``build_student_journal_context``
əvvəlki kimi DB-dən oxuyur, sonra :func:`decorate` bölmə lüğətini yerində
tamamlayır.  Heç bir yeni sorğu edilmir: hər şey artıq yığılmış sətirlərdən
hesablanır (sorğu sayı fənn sayından asılı deyil — test kilidləyir).

Sahib (2026-09-12): «Elektron jurnal hissəsində təkmilləşmələr apar… rənglər
və s. — hamısını qaydasına qoy. Tələbə üçün aydın olsun.»  Buna görə:
* status «Fənlərim» ilə EYNİ açar dəstindən (``exam_eligibility`` ailəsi) gəlir —
  iki bölmə bir fənnə fərqli rəng/etiket göstərmir;
* «Köhnə sistemdən» nişanı legend-də izah olunur (köçürülmüş, bağlı semestr);
* bu günün dərsinin gizlədilmə qaydası (müəllimin 2 saatlıq düzəliş pəncərəsi)
  tələbəyə kiçik məlumat qeydi ilə deyilir — əvvəl yalnız gizli qeyd VARSA
  bir sətir çıxırdı, qaydanın özü heç yerdə yazılmırdı.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import pgettext_lazy

from apps.registrar.student_subjects_context import NEAR_LIMIT_RATIO, eligibility_status, fmt_score

_CTX = "registrar.journal"


def warnings_for(subject_rows) -> list:
    """Limit xəbərdarlığı olan fənlər (qadağa VƏ YA icazəli qayıbın 75%-i).

    Donmuş (tarixi) fənlər siyahıya DÜŞMÜR: «həddə yaxınlaşırsan» xəbəri yalnız
    hələ qərar verilə bilən semestrdə mənalıdır — bağlanmış semestrdə tələbənin
    edə biləcəyi heç nə yoxdur.  ``barred`` orada onsuz da susdurulub; 75%
    yaxınlıq zolağını da susdurmasaq, yalnız o səth digərləri ilə ziddiyyət
    yaradardı (bax ``exam_eligibility``).  Hədd ``NEAR_LIMIT_RATIO`` — «Fənlərim»
    ilə eyni.
    """
    result = []
    for row in subject_rows:
        journal = row["journal"]
        if journal["eligibility"]["frozen"]:
            continue
        allowed = journal["allowed_absence"] or 0
        near = allowed > 0 and Decimal(str(journal["absence_hours"] or 0)) >= Decimal(str(allowed)) * NEAR_LIMIT_RATIO
        if journal["barred"] or near:
            result.append(row)
    return result


def _kpis(subject_rows) -> dict:
    entries = [row["journal"] for row in subject_rows if row.get("journal")]
    entry_avg = None
    entry_cap = None
    if entries:
        entry_avg = (sum(Decimal(str(j["entry_score"] or 0)) for j in entries) / len(entries)).quantize(Decimal("0.1"))
        caps = {int(j["entry_score_max"] or 0) for j in entries}
        entry_cap = caps.pop() if len(caps) == 1 else None
    statuses = [row["ui"]["status"] for row in subject_rows]
    return {
        "subject_count": len(subject_rows),
        "ects_total": sum(int(row.get("ects") or 0) for row in subject_rows),
        "entry_avg": entry_avg,
        "entry_cap": entry_cap,
        "absence_total": sum(Decimal(str(row["journal"]["absence_hours"] or 0)) for row in subject_rows),
        "barred_count": statuses.count("barred"),
        "near_count": statuses.count("near"),
        "frozen_count": statuses.count("frozen"),
    }


def _kpi_tiles(kpis: dict, section: dict) -> list:
    """`partials/ems_ui/_kpi_row.html` üçün kartlar (fənn kartları səhifəsi)."""
    n = kpis["subject_count"]
    period_label = " · ".join(str(part) for part in (section.get("academic_year"), section.get("season_label")) if part)
    if kpis["barred_count"]:
        elig_tone, elig_note = "danger", pgettext_lazy(_CTX, "qayıb həddi keçilib — dekanlığa müraciət edin")
    elif kpis["near_count"]:
        elig_tone = "warning"
        elig_note = pgettext_lazy(_CTX, "%(count)s fənn limitə yaxındır — davamiyyətə diqqət") % {
            "count": kpis["near_count"]
        }
    else:
        elig_tone, elig_note = "success", pgettext_lazy(_CTX, "bütün fənlərdə imtahana buraxılırsınız")
    return [
        {
            "label": pgettext_lazy(_CTX, "Fənn"),
            "value": n,
            "note": (
                pgettext_lazy(_CTX, "%(ects)s ECTS · %(period)s") % {"ects": kpis["ects_total"], "period": period_label}
                if period_label
                else pgettext_lazy(_CTX, "%(ects)s ECTS") % {"ects": kpis["ects_total"]}
            ),
        },
        {
            "label": pgettext_lazy(_CTX, "Giriş balı (orta)"),
            "value": fmt_score(kpis["entry_avg"]),
            "unit": f"/ {kpis['entry_cap']}" if kpis["entry_avg"] is not None and kpis["entry_cap"] else "",
            "note": pgettext_lazy(_CTX, "imtahana qədər toplanan bal"),
            "tone": "primary",
        },
        {
            "label": pgettext_lazy(_CTX, "Qayıb (cəmi)"),
            "value": fmt_score(kpis["absence_total"]),
            "unit": pgettext_lazy(_CTX, "saat"),
            "note": pgettext_lazy(_CTX, "üzrsüz buraxılmış dərs saatı, bütün fənlər üzrə"),
        },
        {
            "label": pgettext_lazy(_CTX, "İmtahana buraxılmayan"),
            "value": kpis["barred_count"],
            "unit": f"/ {n}",
            "note": elig_note,
            "tone": f"accent-{elig_tone}",
        },
    ]


#: Legend — rəng semantikası MƏTNlə (handoff §7); açarlar `exam_eligibility`
#: ailəsi ilə eynidir, izah jurnal dilində.
LEGEND = (
    {"status": "ok", "hint": pgettext_lazy(_CTX, "qayıb icazəli həddin altındadır")},
    {"status": "near", "hint": pgettext_lazy(_CTX, "icazəli qayıbın 75%-i keçilib — diqqət")},
    {"status": "barred", "hint": pgettext_lazy(_CTX, "qayıb həddi keçilib, yekun imtahana giriş yoxdur")},
    {
        "status": "frozen",
        "hint": pgettext_lazy(
            _CTX, "köhnə sistemdən köçürülmüş, bağlı semestr — status yenidən hesablanmır, faktiki nəticə göstərilir"
        ),
    },
)


def decorate(section: dict) -> dict:
    """Bölmə lüğətini görünüş açarları ilə tamamlayır (yerində; sorğusuz).

    Əlavə olunanlar: hər fənn sətrində ``ui.status``; ``warnings``; ``kpis``;
    ``legend``; detal varsa ``detail.ui.status``.
    """
    rows = section.get("subjects") or []
    for row in rows:
        journal = row.get("journal") or {}
        row["ui"] = {"status": eligibility_status(journal.get("eligibility"))}
    section["warnings"] = warnings_for(rows)
    section["kpis"] = _kpis(rows)
    section["kpi_tiles"] = _kpi_tiles(section["kpis"], section) if rows else []
    section["legend"] = LEGEND
    detail = section.get("detail")
    if detail:
        journal = detail.get("journal") or {}
        detail["ui"] = {"status": eligibility_status(journal.get("eligibility"))}
    return section

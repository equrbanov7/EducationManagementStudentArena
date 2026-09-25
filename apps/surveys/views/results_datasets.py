"""İxrac cədvəlləri — YALNIZ aqreqatlar (xam cavab sətri, şərh/təklif mətni, tələbə
məlumatı YOXDUR; bax ``apps.surveys.public`` — «F2 UI xam sətir ixracı ETMƏMƏLİDİR»).

Cədvəllər UI tablarının EYNİ qurucularından gəlir (``overview_tab``, ``teachers_tab``,
``general_tab``) — ekranda gizli olan sətir ixracda da gizlidir (göstəricilər boş,
«Status» sütununda səbəb). Hər cədvəl ``{"key", "title", "header", "rows"}``.
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.translation import pgettext

from .. import public

CTX = "surveys.results"

DATASETS = ("summary", "questions", "teachers", "departments", "trend", "general", "keywords")
CSV_DATASETS = ("teachers", "questions", "departments", "trend", "general", "keywords")


def _status(row) -> str:
    if not row.get("suppressed"):
        return pgettext(CTX, "görünür")
    if row.get("secondary"):
        return pgettext(CTX, "gizli — tamamlayıcı qayda")
    return pgettext(CTX, "gizli — n < k")


def _label_of(options, value) -> str:
    return next((item["label"] for item in options if str(item["id"]) == str(value)), "")


def filter_description(resolved, filters) -> str:
    choices = resolved.choices or {}
    parts = []
    for key, label, value in (
        ("faculties", pgettext(CTX, "Fakültə"), filters.faculty_id),
        ("departments", pgettext(CTX, "Kafedra"), filters.department_id),
        ("subjects", pgettext(CTX, "Fənn"), filters.subject_id),
        ("groups", pgettext(CTX, "Qrup"), filters.group_id),
        ("programs", pgettext(CTX, "İxtisas"), filters.program_id),
        ("course_years", pgettext(CTX, "Kurs"), filters.course_year),
    ):
        if value is not None:
            parts.append(f"{label}: {_label_of(choices.get(key, []), value) or value}")
    if filters.teacher_id is not None and resolved.teacher_name:
        parts.append(f"{pgettext(CTX, 'Müəllim')}: {resolved.teacher_name}")
    return "; ".join(parts) or pgettext(CTX, "yoxdur")


def _summary_table(resolved, filters, summary, participation, scope_label) -> dict:
    rate = participation.get("rate") if participation and not participation.get("approximate") else None
    rows = [
        (pgettext(CTX, "Dövr"), resolved.query.period.label),
        (pgettext(CTX, "Əhatə"), scope_label),
        (pgettext(CTX, "Filtrlər"), filter_description(resolved, filters)),
        (pgettext(CTX, "Anonimlik həddi (k)"), summary["k"]),
        (pgettext(CTX, "Cavab sayı"), summary["n"]),
        (pgettext(CTX, "Ümumi bölmə cavabları"), summary["general_n"]),
        (pgettext(CTX, "Doldurulmuş hədəf"), participation.get("receipts", 0) if participation else 0),
        (pgettext(CTX, "Gözlənilən hədəf"), participation.get("expected", 0) if participation else 0),
        (pgettext(CTX, "Cavab faizi (%)"), round(rate * 100, 1) if rate is not None else ""),
        (pgettext(CTX, "Orta ümumi bal (1–10)"), summary["avg_overall"]),
        (pgettext(CTX, "Likert indeksi (1–5)"), summary["likert_index"]),
        (
            pgettext(CTX, "Tövsiyə edənlər (%)"),
            round(summary["recommend_top2"] * 100) if summary["recommend_top2"] is not None else "",
        ),
        (pgettext(CTX, "Nəticəsi görünən müəllimlər"), summary["teachers_visible"]),
        (pgettext(CTX, "Müəllimlər (cəmi)"), summary["teachers"]),
        (pgettext(CTX, "Nəticə gizlidir"), pgettext(CTX, "bəli") if summary["suppressed"] else pgettext(CTX, "xeyr")),
        (pgettext(CTX, "Yaradılıb"), timezone.localtime().strftime("%d.%m.%Y %H:%M")),
    ]
    return {
        "key": "summary",
        "title": pgettext(CTX, "Xülasə"),
        "header": [pgettext(CTX, "Göstərici"), pgettext(CTX, "Dəyər")],
        "rows": [[label, "" if value is None else value] for label, value in rows],
    }


def _questions_table(overview) -> dict:
    header = [
        pgettext(CTX, "Kod"),
        pgettext(CTX, "Qısa ad"),
        pgettext(CTX, "Sual"),
        pgettext(CTX, "Cavab sayı"),
        pgettext(CTX, "Orta"),
        pgettext(CTX, "«Razı» payı (%)"),
        pgettext(CTX, "Universitet ortası"),
        *[str(score) for score in range(1, 6)],
    ]
    likert = {row["code"]: row for row in overview.get("likert", [])}
    rows = []
    for row in overview.get("questions", []):
        counts = likert.get(row["code"], {}).get("counts") or [""] * 5
        rows.append([row["code"], row["label"], row["text"], row["n"], row["avg"], row["top2"], row["org"], *counts])
    histogram = overview.get("histogram")
    if histogram:
        rows.append(
            [
                histogram["code"],
                histogram["label"],
                histogram["text"],
                histogram["n"],
                histogram["avg"],
                "",
                "",
                *histogram["counts"],
            ]
        )
        header.extend(str(score) for score in range(6, 11))
    return {"key": "questions", "title": pgettext(CTX, "Suallar"), "header": header, "rows": rows}


def _teachers_table(teachers) -> dict:
    header = [
        pgettext(CTX, "Yer"),
        pgettext(CTX, "Müəllim"),
        pgettext(CTX, "Kafedra"),
        pgettext(CTX, "Cavab sayı"),
        pgettext(CTX, "Doldurulmuş hədəf"),
        pgettext(CTX, "Gözlənilən hədəf"),
        pgettext(CTX, "Cavab faizi (%)"),
        pgettext(CTX, "Orta ümumi bal (1–10)"),
        pgettext(CTX, "Likert indeksi (1–5)"),
        pgettext(CTX, "Tövsiyə edənlər (%)"),
        pgettext(CTX, "Fərq: kafedra"),
        pgettext(CTX, "Fərq: universitet"),
        pgettext(CTX, "Vəziyyət"),
    ]
    rows = sorted(teachers.get("rows", []), key=lambda row: (row["rank"] is None, row["rank"] or 0, row["name"]))
    return {
        "key": "teachers",
        "title": pgettext(CTX, "Müəllimlər"),
        "header": header,
        "rows": [
            [
                row["rank"] or "",
                row["name"],
                row["department"],
                row["n"],
                row["receipts"],
                row["expected"],
                "" if row["rate"] is None else row["rate"],
                row["overall"],
                row["index"],
                row["recommend"],
                row["delta_department"],
                row["delta_org"],
                _status(row),
            ]
            for row in rows
        ],
    }


def _departments_table(overview) -> dict:
    rows = []
    for level, label in (("faculties", pgettext(CTX, "Fakültə")), ("departments", pgettext(CTX, "Kafedra"))):
        for row in overview.get(level, []):
            rows.append([label, row["label"], row["n"], row["overall"], row["index"], row["recommend"], _status(row)])
    return {
        "key": "departments",
        "title": pgettext(CTX, "Kafedralar"),
        "header": [
            pgettext(CTX, "Səviyyə"),
            pgettext(CTX, "Ad"),
            pgettext(CTX, "Cavab sayı"),
            pgettext(CTX, "Orta ümumi bal (1–10)"),
            pgettext(CTX, "Likert indeksi (1–5)"),
            pgettext(CTX, "Tövsiyə edənlər (%)"),
            pgettext(CTX, "Vəziyyət"),
        ],
        "rows": rows,
    }


def _trend_table(trend) -> dict:
    series = trend.get("series", [])
    rows = []
    for row in trend.get("rows", []):
        for item, cell in zip(series, row["cells"]):
            rows.append([row["label"], item["label"], cell["n"], cell["overall"], cell["index"], _status(cell)])
    return {
        "key": "trend",
        "title": pgettext(CTX, "Dinamika"),
        "header": [
            pgettext(CTX, "Dövr"),
            pgettext(CTX, "Seriya"),
            pgettext(CTX, "Cavab sayı"),
            pgettext(CTX, "Orta ümumi bal (1–10)"),
            pgettext(CTX, "Likert indeksi (1–5)"),
            pgettext(CTX, "Vəziyyət"),
        ],
        "rows": rows,
    }


def _general_table(general) -> dict:
    rows = []
    for row in general.get("likert", []):
        rows.append([pgettext(CTX, "Sual"), row["label"], row["n"], row["avg"], "", row["top2"], _status(row)])
    names = {
        "faculty": pgettext(CTX, "Fakültə"),
        "program": pgettext(CTX, "İxtisas"),
        "course_year": pgettext(CTX, "Kurs"),
    }
    for level, level_rows in (general.get("levels") or {}).items():
        for row in level_rows:
            rows.append(
                [
                    names.get(level, level),
                    row["label"],
                    row["n"],
                    row["satisfaction"],
                    row["facilities"],
                    "",
                    _status(row),
                ]
            )
    return {
        "key": "general",
        "title": pgettext(CTX, "Ümumi bölmə"),
        "header": [
            pgettext(CTX, "Səviyyə"),
            pgettext(CTX, "Ad"),
            pgettext(CTX, "Cavab sayı"),
            pgettext(CTX, "Ümumi məmnunluq (1–5)"),
            pgettext(CTX, "Tədris şəraiti (1–5)"),
            pgettext(CTX, "«Razı» payı (%)"),
            pgettext(CTX, "Vəziyyət"),
        ],
        "rows": rows,
    }


def _keywords_table(general) -> dict:
    digest = general.get("digest") or {}
    return {
        "key": "keywords",
        "title": pgettext(CTX, "Açar sözlər"),
        "header": [pgettext(CTX, "Söz"), pgettext(CTX, "Neçə təklifdə keçir")],
        "rows": [[item["word"], item["count"]] for item in digest.get("keywords", [])],
    }


def build_tables(resolved, filters, wanted, *, scope_label="") -> list:
    """İstənilən cədvəllər (``wanted`` ⊆ ``DATASETS``) — lazım olan tab qurucuları bir dəfə çağırılır."""
    from .results_general import general_tab
    from .results_overview import overview_tab
    from .results_panel import apply_publishing
    from .results_teachers import teachers_tab

    organization, scope, query = resolved.organization, resolved.scope, resolved.query
    wanted = [key for key in DATASETS if key in set(wanted)]
    summary = public.results_summary(organization, scope, filters, with_participation="summary" in wanted)
    published = public.publishable_teachers(organization, resolved.campaign_ids)
    apply_publishing(summary, filters, published)
    overview = teachers = general = {}
    if {"questions", "departments", "trend"} & set(wanted):
        overview = overview_tab(organization, scope, filters, summary, query)["overview"]
    if "teachers" in wanted:
        urls = {"detail_base": "", "detail_qs": ""}
        teachers = teachers_tab(organization, scope, filters, summary, query, urls, published)["teachers"]
    if {"general", "keywords"} & set(wanted):
        general = general_tab(organization, scope, filters, summary)["general"]
    builders = {
        "summary": lambda: _summary_table(resolved, filters, summary, summary["participation"], scope_label),
        "questions": lambda: _questions_table(overview),
        "teachers": lambda: _teachers_table(teachers),
        "departments": lambda: _departments_table(overview),
        "trend": lambda: _trend_table(overview.get("trend") or {}),
        "general": lambda: _general_table(general),
        "keywords": lambda: _keywords_table(general),
    }
    return [builders[key]() for key in wanted]

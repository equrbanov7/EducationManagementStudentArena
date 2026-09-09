"""«Sual Bankı» bölməsinin TƏQDİMAT qatı — ems_ui komponent modeli.

Sorğu/filtr məntiqi ``question_bank.py``-dədir; burada yalnız həmin nəticə
`ems_ui` komponentlərinin (KPI sırası, avto filtr paneli, cədvəl) gözlədiyi
struktura çevrilir.  Ayrı fayl saxlanır ki, hər iki modul kiçik qalsın
(``scripts/check_module_size.py``).

Dizayn qərarı (2026-09-09): yaratma forması artıq səhifənin yarısını tutan
kart deyil — başlıqdakı «Yeni bank» düyməsi ilə açılan dialoqdur; əsas məzmun
BANK SİYAHISIDIR.  Sahə adları, POST hədəfi və axtarışlı seçici çəngəlləri
olduğu kimi qalır (`exams:question_bank_list`, `js-qb-create-form`).
"""

from django.utils.translation import pgettext

#: msgctxt — HƏR çağırışda LİTERAL yazılır: `makemessages` (və
#: `scripts/i18n_source_scan.py`) dəyişənlə verilən konteksti
#: çıxara bilmir, mətn kataloqa düşmür.
CTX = "accounts.profile.question_bank"

#: Sətir/xana şablonlarının qovluğu.
CELL_DIR = "exams/teacher/partials/question_bank/"

#: İmtahan növü → badge tonu (rəng TƏK mənbədir: `ems_ui/badge.css`).
_KIND_TONES = {"final": "primary", "midterm": "info", "quiz": "warning"}


def kind_badge(kind: str, label) -> dict:
    """`_status_badge.html` müqaviləsi ilə uyğun sadə badge sözlüyü."""
    tone = _KIND_TONES.get(kind or "", "neutral")
    return {"css_class": f"ems-badge ems-badge--{tone}", "label": label}


def kpi_tiles(*, bank_count: int, question_count: int, kind_counts: dict, exam_kind_choices) -> list:
    """Bank sayı · sual sayı · imtahan növü üzrə paylanma."""
    tiles = [
        {"label": pgettext("accounts.profile.question_bank", "Bank"), "value": bank_count, "tone": "primary"},
        {"label": pgettext("accounts.profile.question_bank", "Sual"), "value": question_count},
    ]
    for value, label in exam_kind_choices:
        tiles.append({"label": label, "value": kind_counts.get(value, 0)})
    tiles.append(
        {
            "label": pgettext("accounts.profile.question_bank", "Ümumi"),
            "value": kind_counts.get("", 0),
            "note": pgettext("accounts.profile.question_bank", "təyinatsız bank"),
        }
    )
    return tiles


def _options(pairs, blank_label):
    result = [{"value": "", "label": blank_label}]
    result.extend({"value": value, "label": label} for value, label in pairs)
    return result


def filter_fields(
    *,
    search: str,
    kind: str,
    language: str,
    fmt: str,
    exam_kind_choices,
    language_choices,
    type_choices,
) -> list:
    """Avto filtr paneli: axtarış + təyinat + dil + format.

    Bütün parametrlər `bank_` prefiksindədir — «Sıfırla» yalnız bu bölmənin
    parametrlərini atır (bax `ems_ui/filter_bar.js`).
    """
    kind_options = _options(exam_kind_choices, pgettext("accounts.profile.question_bank", "Bütün təyinatlar"))
    kind_options.append({"value": "general", "label": pgettext("accounts.profile.question_bank", "Təyinatsız")})
    format_options = _options(type_choices, pgettext("accounts.profile.question_bank", "Bütün formatlar"))
    return [
        {
            "name": "bank_search",
            "label": pgettext("accounts.profile.question_bank", "Axtarış"),
            "kind": "search",
            "value": search,
            "wide": True,
            "placeholder": pgettext("accounts.profile.question_bank", "Bank adı, fənn və ya müəllim"),
        },
        {
            "name": "bank_kind",
            "label": pgettext("accounts.profile.question_bank", "Təyinat"),
            "kind": "select",
            "options": kind_options,
            "value": kind,
        },
        {
            "name": "bank_format",
            "label": pgettext("accounts.profile.question_bank", "Format"),
            "kind": "select",
            "options": format_options,
            "value": fmt,
        },
        {
            "name": "bank_lang",
            "label": pgettext("accounts.profile.question_bank", "Bankın dili"),
            "kind": "select",
            "options": _options(language_choices, pgettext("accounts.profile.question_bank", "Bütün dillər")),
            "value": language,
        },
    ]


def columns(*, is_center: bool) -> list:
    """Cədvəl başlıqları (birinci sütun `th scope=row` — bankın adı)."""
    cols = [
        {"key": "bank", "label": pgettext("accounts.profile.question_bank", "Bank")},
        {"key": "kind", "label": pgettext("accounts.profile.question_bank", "Təyinat")},
        {"key": "format", "label": pgettext("accounts.profile.question_bank", "Format")},
        {"key": "language", "label": pgettext("accounts.profile.question_bank", "Bankın dili")},
    ]
    if is_center:
        cols.append({"key": "teacher", "label": pgettext("accounts.profile.question_bank", "Müəllim")})
    cols += [
        {"key": "questions", "label": pgettext("accounts.profile.question_bank", "Sual"), "align": "num"},
        {"key": "created", "label": pgettext("accounts.profile.question_bank", "Yaradılıb")},
        {"key": "actions", "label": pgettext("accounts.profile.question_bank", "Əməllər")},
    ]
    return cols


def table_rows(rows: list, *, is_center: bool) -> list:
    """`_data_table.html` sətirləri — xanalar kiçik şablonlarla render olunur."""
    table = []
    for row in rows:
        cells = [
            {"include": f"{CELL_DIR}_cell_kind.html"},
            {"text": row["format_label"]},
            {"text": row["language_label"]},
        ]
        if is_center:
            cells.append({"text": row["teacher_name"] or "—", "muted": not row["teacher_name"]})
        cells += [
            {"text": row["question_count"], "num": True},
            {"text": row["created"], "nowrap": True},
        ]
        table.append(
            {
                "row_head": row["name"],
                "head_include": f"{CELL_DIR}_cell_bank.html",
                "cells": cells,
                "actions_include": f"{CELL_DIR}_row_actions.html",
                "data": row,
            }
        )
    return table


def states(*, has_filters: bool, can_create: bool) -> tuple:
    """Boş vəziyyət mətnləri — filtrli boşluq ≠ heç bank olmaması."""
    if has_filters:
        return (
            pgettext("accounts.profile.question_bank", "Filtrə uyğun bank tapılmadı"),
            pgettext("accounts.profile.question_bank", "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın."),
        )
    if can_create:
        return (
            pgettext("accounts.profile.question_bank", "Hələ sual bankı yoxdur"),
            pgettext(
                "accounts.profile.question_bank",
                "«Yeni bank» ilə boş bank yaradın, sonra ona test və ya yazılı sual əlavə edin.",
            ),
        )
    return (
        pgettext("accounts.profile.question_bank", "Hələ sual bankı yoxdur"),
        pgettext("accounts.profile.question_bank", "Sizə açıq bank yaranan kimi burada görünəcək."),
    )


def subtitle(*, is_center: bool):
    if is_center:
        return pgettext(
            "accounts.profile.question_bank",
            "İmtahan mərkəzinin sual kitabxanası: bank yaradın, müəllim göndərişlərini "
            "banka yazın və sualları imtahanlara buradan götürün.",
        )
    return pgettext(
        "accounts.profile.question_bank",
        "Şəxsi sual kitabxananız — imtahandan asılı deyil. Bank yaradın, sual əlavə edin, "
        "sonra istənilən imtahanda təkrar istifadə edin.",
    )

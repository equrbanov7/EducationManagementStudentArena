"""«Sual göndərişləri» bölməsinin TƏQDİMAT qatı — ems_ui komponent modeli.

Sorğu/filtr məntiqi ``question_submissions.py``-dədir.  Burada nəticə KPI
kartlarına (klik edilə bilən status filtrləri), avto filtr panelinin sahələrinə,
cədvəl sətirlərinə və «yol» çekmecəsinin JSON yükünə çevrilir.

Ayrı fayl saxlanır ki, hər iki modul `scripts/check_module_size.py` büdcəsində
qalsın.
"""

from django.utils.translation import pgettext

#: msgctxt — HƏR çağırışda LİTERAL yazılır: `makemessages` (və
#: `scripts/i18n_source_scan.py`) dəyişənlə verilən konteksti
#: çıxara bilmir, mətn kataloqa düşmür.
CTX = "accounts.profile.question_submissions"
CELL_DIR = "exams/teacher/partials/question_submissions/"

#: Status açarı → (etiket, badge tonu).  Etiketlər mövcud msgid-lərdir.
_STATUS_TONES = {
    "draft": "neutral",
    "submitted_to_chair": "warning",
    "chair_revision": "danger",
    "chair_approved": "info",
    "center_review": "info",
    "center_revision": "danger",
    "accepted": "success",
    "rejected": "danger",
}


def status_label(status: str, *, is_reviewer: bool):
    """Zəncir statusunun istifadəçi etiketi (müəllim ↔ mərkəz fərqi ilə)."""
    labels = {
        "submitted_to_chair": pgettext("accounts.profile.question_submissions", "Kafedra müdirinə göndərilib"),
        "chair_revision": pgettext("accounts.profile.question_submissions", "Kafedra düzəliş istəyib"),
        "chair_approved": pgettext("accounts.profile.question_submissions", "Kafedra təsdiqləyib — İmtahan Mərkəzində"),
        "center_review": pgettext("accounts.profile.question_submissions", "İmtahan Mərkəzi baxır"),
        "center_revision": pgettext("accounts.profile.question_submissions", "İmtahan Mərkəzi düzəliş istəyib"),
        "accepted": pgettext("accounts.profile.question_submissions", "Qəbul"),
        "rejected": (
            pgettext("accounts.profile.question_submissions", "Rədd")
            if is_reviewer
            else pgettext("accounts.profile.question_submissions", "Rədd edilib — düzəldib yenidən göndərə bilərsiniz")
        ),
    }
    return labels.get(status, pgettext("accounts.profile.question_submissions", "Qaralama"))


def status_badge(status: str, *, is_reviewer: bool) -> dict:
    tone = _STATUS_TONES.get(status, "neutral")
    return {
        "css_class": f"ems-badge ems-badge--{tone} ems-badge--wrap",
        "label": status_label(status, is_reviewer=is_reviewer),
    }


def kpi_tiles(counts: dict, *, active_status: str, is_reviewer: bool) -> list:
    """KPI kartları = KLİK EDİLƏ BİLƏN status filtrləri (`data-ems-kpi-filter`)."""
    returned_label = (
        pgettext("accounts.profile.question_submissions", "Rədd edilmiş")
        if is_reviewer
        else pgettext("accounts.profile.question_submissions", "Düzəliş gözləyən")
    )
    tiles = [
        {
            "key": "",
            "label": pgettext("accounts.profile.question_submissions", "Ümumi göndəriş"),
            "value": counts["total"],
            "tone": "primary",
        },
    ]
    if not is_reviewer:
        # Müəllim zəncirin HƏR İKİ dayanacağını ayrıca görür.
        tiles.append(
            {
                "key": "at_chair",
                "label": pgettext("accounts.profile.question_submissions", "Kafedrada"),
                "value": counts["at_chair"],
            }
        )
    tiles += [
        {
            "key": "at_center",
            "label": pgettext("accounts.profile.question_submissions", "Baxılır"),
            "value": counts["at_center"],
        },
        {
            "key": "accepted",
            "label": pgettext("accounts.profile.question_submissions", "Qəbul edilmiş"),
            "value": counts["accepted"],
            "tone": "success",
        },
        {"key": "returned", "label": returned_label, "value": counts["returned"], "tone": "danger"},
    ]
    return [
        {
            "label": tile["label"],
            "value": tile["value"] or 0,
            "tone": tile.get("tone"),
            # Boş açar = «hamısı»; `filter` verilən kart düymə kimi render olunur.
            "filter": tile["key"] or "all",
            "pressed": (active_status or "all") == (tile["key"] or "all"),
        }
        for tile in tiles
    ]


def _options(pairs, blank_label):
    result = [{"value": "", "label": blank_label}]
    result.extend({"value": value, "label": label} for value, label in pairs)
    return result


def status_options(*, is_reviewer: bool) -> list:
    returned_label = (
        pgettext("accounts.profile.question_submissions", "Rədd edilmiş")
        if is_reviewer
        else pgettext("accounts.profile.question_submissions", "Düzəliş gözləyən")
    )
    pairs = []
    if not is_reviewer:
        pairs.append(("at_chair", pgettext("accounts.profile.question_submissions", "Kafedrada")))
    pairs += [
        ("at_center", pgettext("accounts.profile.question_submissions", "Baxılır")),
        ("accepted", pgettext("accounts.profile.question_submissions", "Qəbul edilmiş")),
        ("returned", returned_label),
    ]
    return _options(pairs, pgettext("accounts.profile.question_submissions", "Bütün statuslar"))


def filter_fields(*, filters, is_reviewer, sources) -> list:
    """Avto filtr paneli — `qsub_` prefiksli sahələr.

    Uzun siyahılar (fakültə, kafedra, müəllim) Bootstrap seçicisinin DAXİLİ
    axtarışı ilə gəlir (`searchable`), qısa siyahılar (il/semestr/dil) sadə
    açılan menyudur.  Layihə qaydası: xam `<select>` yoxdur.
    """
    fields = [
        {
            "name": "qsub_q",
            "label": pgettext("accounts.profile.question_submissions", "Axtarış"),
            "kind": "search",
            "value": filters["q"],
            "wide": True,
            "placeholder": (
                pgettext("accounts.profile.question_submissions", "Başlıq, fənn, qrup və ya müəllim")
                if is_reviewer
                else pgettext("accounts.profile.question_submissions", "Başlıq, fənn və ya qrup")
            ),
        },
        {
            "name": "qsub_status",
            "label": pgettext("accounts.profile.question_submissions", "Vəziyyət"),
            "kind": "select",
            "options": status_options(is_reviewer=is_reviewer),
            "value": filters["status"],
        },
    ]
    if not is_reviewer:
        return fields
    fields += [
        {
            "name": "qsub_faculty",
            "label": pgettext("accounts.profile.question_submissions", "Fakültə"),
            "kind": "select",
            "searchable": True,
            "options": _options(
                sources["faculties"], pgettext("accounts.profile.question_submissions", "Bütün fakültələr")
            ),
            "value": filters["faculty"],
        },
        {
            "name": "qsub_kafedra",
            "label": pgettext("accounts.profile.question_submissions", "Kafedra"),
            "kind": "select",
            "searchable": True,
            "options": _options(
                sources["kafedras"], pgettext("accounts.profile.question_submissions", "Bütün kafedralar")
            ),
            "value": filters["kafedra"],
        },
        {
            "name": "qsub_teacher",
            "label": pgettext("accounts.profile.question_submissions", "Müəllim"),
            "kind": "select",
            "searchable": True,
            "options": _options(
                sources["teachers"], pgettext("accounts.profile.question_submissions", "Bütün müəllimlər")
            ),
            "value": filters["teacher"],
        },
        {
            "name": "qsub_year",
            "label": pgettext("accounts.profile.question_submissions", "Tədris ili"),
            "kind": "select",
            "options": _options(sources["years"], pgettext("accounts.profile.question_submissions", "Bütün illər")),
            "value": filters["year"],
        },
        {
            "name": "qsub_period",
            "label": pgettext("accounts.profile.question_submissions", "Semestr"),
            "kind": "select",
            "options": _options(
                sources["periods"], pgettext("accounts.profile.question_submissions", "Bütün semestrlər")
            ),
            "value": filters["period"],
        },
        {
            "name": "qsub_lang",
            "label": pgettext("accounts.profile.question_submissions", "Dil"),
            "kind": "select",
            "options": _options(
                sources["languages"], pgettext("accounts.profile.question_submissions", "Bütün dillər")
            ),
            "value": filters["lang"],
        },
    ]
    return fields


def columns(*, is_reviewer: bool) -> list:
    cols = [{"key": "title", "label": pgettext("accounts.profile.question_submissions", "Göndəriş")}]
    if is_reviewer:
        cols.append({"key": "teacher", "label": pgettext("accounts.profile.question_submissions", "Müəllim")})
    cols += [
        {"key": "status", "label": pgettext("accounts.profile.question_submissions", "Vəziyyət")},
        {"key": "questions", "label": pgettext("accounts.profile.question_submissions", "Sual"), "align": "num"},
        {"key": "signals", "label": pgettext("accounts.profile.question_submissions", "Xəbərdarlıq")},
        {"key": "created", "label": pgettext("accounts.profile.question_submissions", "Tarix")},
        {"key": "actions", "label": pgettext("accounts.profile.question_submissions", "Əməllər")},
    ]
    return cols


def table_rows(rows: list, *, is_reviewer: bool) -> list:
    table = []
    for row in rows:
        cells = []
        if is_reviewer:
            cells.append({"text": row["teacher"]})
        cells += [
            {"include": f"{CELL_DIR}_cell_status.html"},
            {"text": row["question_count"], "num": True},
            {"include": f"{CELL_DIR}_cell_signals.html"},
            {"text": row["created"], "nowrap": True},
        ]
        table.append(
            {
                "row_head": row["title"],
                "head_include": f"{CELL_DIR}_cell_title.html",
                "cells": cells,
                "actions_include": f"{CELL_DIR}_row_actions.html",
                "data": row,
            }
        )
    return table


def drawer_data(rows: list) -> dict:
    """Çekmecənin yükü — sətir id-si → detal.

    Şablonda `json_script` filtri ilə verilir (XSS-təhlükəsiz kodlaşdırma,
    `application/json` bloku — icra olunan skript deyil).
    """
    return {
        row["id"]: {
            "title": row["title"],
            "status": row["status_badge"]["label"],
            "statusClass": row["status_badge"]["css_class"],
            "meta": row["drawer_meta"],
            "bank": row["bank_note"],
            "url": row["open_url"],
            "events": row["events"],
        }
        for row in rows
    }


def states(*, has_filters: bool, is_reviewer: bool) -> tuple:
    if has_filters:
        return (
            pgettext("accounts.profile.question_submissions", "Bu şərtlərə uyğun göndəriş tapılmadı"),
            pgettext(
                "accounts.profile.question_submissions", "Filtri dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın."
            ),
        )
    if is_reviewer:
        return (
            pgettext("accounts.profile.question_submissions", "Hələ göndəriş yoxdur"),
            pgettext(
                "accounts.profile.question_submissions",
                "Göndərişlər müəllimdən kafedra müdirinə, təsdiqdən sonra isə buraya gəlir — "
                "kafedrada gözləyən dəstlər burada görünmür.",
            ),
        )
    return (
        pgettext("accounts.profile.question_submissions", "Hələ göndərişiniz yoxdur"),
        pgettext(
            "accounts.profile.question_submissions",
            "«Yeni göndəriş» ilə sual mətnini yükləyin: dəst əvvəlcə kafedra müdirinə, "
            "təsdiqdən sonra İmtahan Mərkəzinə gedir.",
        ),
    )


def subtitle(*, is_reviewer: bool):
    if is_reviewer:
        return pgettext(
            "accounts.profile.question_submissions",
            "Müəllimlərin göndərdiyi sual toplularına baxın: qəbul edin (banka yazılır) " "və ya qeydlə geri qaytarın.",
        )
    return pgettext(
        "accounts.profile.question_submissions",
        "Suallarınızı elektron şəkildə imtahan mərkəzinə göndərin — xəbərdarlıqları görün, "
        "düzəldin və ya birbaşa göndərin.",
    )

"""Profil «exam-score-entry» — seçilmiş açılışın doldurulması (siyahı, KPI, vərəq, idxal URL-ləri).

2026-09-14 (W2 `w2paper`): ``exam_score_entry`` bölmə modulundan (SOFT_CAP=600)
buraya köçürülüb; davranış eynidir. Əlavə: sual şəbəkəsi
(``question_count`` / ``question_max`` — defolt sonuncu vərəqdən), sual sayı
seçimi və idxal sütunlarında S1..Sn.
"""

from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.views._helpers.formatting import _append_query_params

SECTION = "exam-score-entry"
_CTX = "registrar.exam_score_entry"


def _fill_offering(section, offering, period, service, sheets_service, selected_org, is_superadmin, sheet_kind=""):
    """Seçilmiş açılış: metadata (müəllim, qrup, fənn), siyahı, KPI, partiyalar, idxal URL-ləri.

    ``sheet_kind`` — partiya siyahısının növ çipi (``written`` / ``practical`` / boş = hamısı).
    Formanın defoltları (o cümlədən ``exam_kind``) SÜZÜLMƏMİŞ sonuncu vərəqdən gəlir.
    """
    from apps.registrar.public import exam_score_import as importer

    roster = service.roster_for_offering(offering=offering)
    section["rows"] = roster["rows"]
    section["exam_score_max"] = roster["exam_score_max"]
    section["journal_locked"] = _journal_locked(offering)
    section.update(_roster_kpis(roster["rows"]))
    section["kpi_tiles"] = _kpi_tiles(section)
    section["tabs"] = [
        {"key": "manual", "label": pgettext(_CTX, "Əl ilə daxil et"), "current": True},
        {"key": "import", "label": pgettext(_CTX, "Fayldan yüklə (XLSX / CSV)"), "current": False},
    ]
    section["offering_meta"] = {
        "subject_code": offering.subject.code,
        "subject_name": offering.subject.name,
        "group_label": service.offering_label(offering),
        "instructor": sheets_service.instructor_label(offering) or "—",
        "period_label": f"{period.season_label} — {period.name}",
    }
    sheets = sheets_service.sheets_for_offering(offering=offering)
    section["sheet_defaults"] = sheets_service.latest_sheet_defaults(sheets)
    section["sheets_total"] = len(sheets)
    section["sheets"] = [row for row in sheets if not sheet_kind or row["exam_kind"] == sheet_kind]
    section["sheet_kind"] = sheet_kind
    section["exam_kind_options"] = service.exam_score_changes.exam_kind_options(with_all=False)
    section["sheet_defaults"]["examiner_name"] = section["sheet_defaults"][
        "examiner_name"
    ] or sheets_service.instructor_label(offering)
    section["steps"] = _steps(offering=offering, saved=section["saved_flag"])
    grid = section["sheet_defaults"]
    section["question_count"] = int(grid.get("question_count") or 0)
    section["question_max"] = int(grid.get("question_max") or service.exam_score_questions.QUESTION_MAX_DEFAULT)
    section["question_count_options"] = [
        {"value": str(n), "label": str(n) if n else pgettext(_CTX, "0 — yalnız yekun bal")}
        for n in range(0, service.exam_score_questions.QUESTION_COUNT_MAX + 1)
    ]
    section["import_columns"] = importer.template_columns(
        roster["exam_score_max"], section["question_count"], section["question_max"]
    )
    section["import_max_rows"] = importer.MAX_ROWS
    section["import_max_upload_mb"] = importer.MAX_UPLOAD_BYTES // (1024 * 1024)
    org_param = {"ese_org": str(selected_org.pk)} if is_superadmin else {}
    section["import_template_url"] = _append_query_params(
        reverse("accounts:exam_score_import_template"), offering=str(offering.pk), **org_param
    )
    section["import_template_csv_url"] = _append_query_params(
        reverse("accounts:exam_score_import_template"), offering=str(offering.pk), format="csv", **org_param
    )
    section["import_preview_url"] = reverse("accounts:exam_score_import_preview")
    section["import_apply_url"] = reverse("accounts:exam_score_import_apply")


def _steps(*, offering, saved) -> list:
    """«Seç → Yoxla → Yaz» lenti (ems_ui/_stepper). JS yalnız 2↔3 arasını canlı dəyişir."""
    if offering is None:
        return [
            {"label": pgettext(_CTX, "Seç"), "state": "current", "note": pgettext(_CTX, "qrup və fənni seçin")},
            {"label": pgettext(_CTX, "Yoxla"), "state": "todo", "note": ""},
            {"label": pgettext(_CTX, "Yaz"), "state": "todo", "note": ""},
        ]
    return [
        {"label": pgettext(_CTX, "Seç"), "state": "done", "note": ""},
        {
            "label": pgettext(_CTX, "Yoxla"),
            "state": "done" if saved else "current",
            "note": pgettext(_CTX, "balları yazın və ya faylı yoxlayın"),
        },
        {
            "label": pgettext(_CTX, "Yaz"),
            "state": "done" if saved else "todo",
            "note": pgettext(_CTX, "yadda saxlanıldı") if saved else "",
        },
    ]


def _kpi_tiles(section) -> list:
    """ems_ui/_kpi_row kartları — «dəyişdirilib» kartını JS canlı yeniləyir (key=dirty)."""
    avg = section["kpi_avg"]
    return [
        {
            "label": pgettext(_CTX, "Tələbə"),
            "value": section["kpi_students"],
            "note": pgettext(_CTX, "qeydiyyatlı"),
            "key": "students",
        },
        {
            "label": pgettext(_CTX, "Bal yazılıb"),
            "value": section["kpi_recorded"],
            "note": pgettext(_CTX, "sistemə köçürülüb"),
            "tone": "accent-success" if section["kpi_recorded"] else "",
            "key": "recorded",
        },
        {
            "label": pgettext(_CTX, "Gözləyir"),
            "value": section["kpi_pending"],
            "note": pgettext(_CTX, "bal yazılmayıb"),
            "tone": "accent-warning" if section["kpi_pending"] else "",
            "key": "pending",
        },
        {
            "label": pgettext(_CTX, "Orta imtahan balı"),
            "value": avg if avg is not None else "—",
            "note": "%s %s" % (pgettext(_CTX, "maksimum"), section["exam_score_max"]),
            "key": "avg",
        },
        {
            "label": pgettext(_CTX, "Dəyişdirilib"),
            "value": 0,
            "note": pgettext(_CTX, "yadda saxlanmayıb"),
            "key": "dirty",
        },
    ]


def _roster_kpis(rows) -> dict:
    """Bölmə başındakı KPI rəqəmləri — siyahı ARTIQ yaddaşdadır, əlavə sorğu yoxdur."""
    recorded = [row for row in rows if row.get("has_score")]
    scores = [row["exam_score"] for row in recorded if row.get("exam_score") is not None]
    return {
        "kpi_students": len(rows),
        "kpi_recorded": len(recorded),
        "kpi_pending": len(rows) - len(recorded),
        "kpi_avg": round(sum(scores) / len(scores), 1) if scores else None,
    }


def _journal_locked(offering) -> bool:
    """Jurnal bağlıdırmı — səthdə «bal yenə yazılır» izahını göstərmək üçün."""
    from apps.registrar.public import gradebook

    return gradebook.journal_is_locked(offering)

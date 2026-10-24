"""Dərs yükü mərkəzi → «Dərs yükü faylı» görünüşü (sahib 2026-10-23) — GLUE qatı.

Məntiq ``apps.workload.services.load_upload``-dadır; burada sessiyadakı hesabat `ems_ui` komponentlərinin
(KPI sırası, banner, cədvəl) formasına salınır: statusların AZ etiketləri və rəng tonu.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

_CTX = "accounts.workload_load"
_LINES_LIMIT = 400


def _teacher_labels() -> dict:
    return {
        "matched": (pgettext(_CTX, "Tapıldı"), "success"),
        "fuzzy": (pgettext(_CTX, "Tapıldı (yazı səhvi nəzərə alındı)"), "success"),
        "initials": (pgettext(_CTX, "Tapıldı (inisiallarla)"), "success"),
        "patronymic_similar": (pgettext(_CTX, "Tapıldı — ata adı fərqli yazılıb, yoxlayın"), "warning"),
        "created": (pgettext(_CTX, "Yeni müəllim hesabı"), "primary"),
        "created_namesake": (pgettext(_CTX, "Yeni hesab — eyni adlı başqa şəxs var, yoxlayın"), "warning"),
        "ambiguous": (pgettext(_CTX, "Bir neçə uyğun hesab — vakant qalır"), "danger"),
        "review": (pgettext(_CTX, "Dəqiq tapılmadı — vakant qalır"), "danger"),
        "blocked": (pgettext(_CTX, "Hesab bloklanıb — RİM aktivləşdirməlidir"), "danger"),
        "name_unreadable": (pgettext(_CTX, "Müəllimin adı oxunmadı"), "danger"),
        "other_chair": (pgettext(_CTX, "Yoxlanmadı — sətir başqa kafedranındır"), "neutral"),
    }


def _row_label(value: str) -> tuple[str, str]:
    value = str(value or "")
    head, _, detail = value.partition(":")
    if head.startswith("matched"):
        return pgettext(_CTX, "Mövcud sətir"), "success"
    if head == "row_created":
        if detail.startswith("groups_missing="):
            return (
                pgettext(_CTX, "Yeni sətir; tapılmayan qrup: %(groups)s") % {"groups": detail.split("=", 1)[1]},
                "warning",
            )
        return pgettext(_CTX, "Yeni sətir"), "primary"
    if head == "group_not_found":
        return pgettext(_CTX, "Qrup sistemdə tapılmadı: %(groups)s") % {"groups": detail}, "danger"
    if head == "subject_unresolved":
        return pgettext(_CTX, "Fənn müəyyən olunmadı"), "danger"
    if head == "row_blocked":
        return pgettext(_CTX, "Tapşırıq bu statusda yeni sətir qəbul etmir"), "danger"
    if head == "other_chair_row":
        # Sahib 2026-10-25: başqa kafedranın fənni bu kafedraya yazılmır (saat iki dəfə sayılmasın).
        return (
            pgettext(_CTX, "Fənn başqa kafedraya aiddir: %(chair)s — sətir o kafedranın yükündədir, burada yazılmadı")
            % {"chair": detail},
            "warning",
        )
    if head == "other_chair_subject":
        return (
            pgettext(_CTX, "Fənn başqa kafedraya aiddir: %(chair)s — o kafedranın faylı ilə yüklənməlidir")
            % {"chair": detail},
            "warning",
        )
    if head == "no_task_row":
        return pgettext(_CTX, "Sətir tapılmadı"), "danger"
    return value, "neutral"


def _assignment_label(value: str) -> str:
    value = str(value or "")
    labels = {
        "assigned": pgettext(_CTX, "Təyin olundu"),
        "reassigned": pgettext(_CTX, "Müəllim dəyişdirildi"),
        "unchanged": pgettext(_CTX, "Dəyişiklik yoxdur"),
    }
    parts = [part.strip() for part in value.split(";") if part.strip()]
    return " · ".join(labels.get(part.split(":")[0], part) for part in parts) or "—"


def _skip_label(reason: str) -> str:
    return {
        "no_choice_marker": pgettext(_CTX, "Seçmə bloku — seçilmiş fənni yazın"),
        "no_contact_hours": pgettext(_CTX, "Saat yoxdur"),
        "subject_missing": pgettext(_CTX, "Fənnin adı boşdur"),
        "teacher_missing": pgettext(_CTX, "Müəllim yazılmayıb"),
        "non_teaching": pgettext(_CTX, "Dərs deyil (dissertasiya rəhbərliyi və s.)"),
    }.get(reason, reason)


_UNRESOLVED_TEACHER = ("ambiguous", "review", "blocked", "name_unreadable")
_SEASONS = {"fall": "I", "spring": "II"}


def load_context(load: dict | None, *, year: str) -> dict:
    """``center_registry._load_view`` nəticəsi → şablon konteksti."""
    if not load:
        return {}
    stored = load.get("stored") or None
    context = {
        "allowed": load.get("allowed", False),
        "chair_options": load.get("chair_options", []),
        "template_url": reverse("workload:load_template"),
        "year": year,
        "stored": None,
    }
    if not stored:
        return context
    report = stored.get("report") or {}
    counters = report.get("counters") or {}
    teacher_labels = _teacher_labels()
    lines, problems = [], 0
    for line in report.get("lines", []):
        teacher_text, teacher_tone = teacher_labels.get(
            line.get("teacher_status", ""), (line.get("teacher_status"), "neutral")
        )
        row_text, row_tone = _row_label(line.get("row", ""))
        bad = teacher_tone == "danger" or row_tone == "danger"
        problems += bad
        lines.append(
            {
                **line,
                "season_label": _SEASONS.get(line.get("season"), ""),
                "teacher_label": teacher_text,
                "teacher_tone": teacher_tone,
                "row_label": row_text,
                "row_tone": row_tone,
                "assignment_label": _assignment_label(line.get("assignment", "")),
                "problem": bad,
            }
        )
    lines.sort(key=lambda item: (not item["problem"], item.get("line") or 0))
    new_teachers = report.get("new_teachers") or []
    created_rows = int(counters.get("row_created", 0))
    other_chair = int(counters.get("other_chair_row", 0)) + int(counters.get("other_chair_subject", 0))
    unresolved = sum(int(counters.get(f"teacher_{key}", 0)) for key in _UNRESOLVED_TEACHER)
    applied = bool(report.get("applied"))
    context["stored"] = {
        "chair_name": stored.get("chair_name", ""),
        "file_name": stored.get("file_name", ""),
        "applied": applied,
        "lines": lines[:_LINES_LIMIT],
        "lines_hidden": max(0, len(lines) - _LINES_LIMIT),
        "problems": problems,
        "new_teachers": new_teachers,
        "skipped": [
            {
                "line": item.get("line"),
                "subject": item.get("subject", ""),
                "reason": _skip_label(item.get("reason", "")),
            }
            for item in report.get("skipped", [])
        ],
        "tiles": [
            {"label": pgettext(_CTX, "FAYL SƏTRİ"), "value": report.get("entries", 0)},
            {"label": pgettext(_CTX, "YENİ SƏTİR"), "value": created_rows, "tone": "accent-primary"},
            {
                "label": pgettext(_CTX, "BAŞQA KAFEDRANIN FƏNNİ"),
                "value": other_chair,
                "note": pgettext(_CTX, "bu kafedraya yazılmır"),
                "tone": "accent-warning" if other_chair else "",
            },
            {"label": pgettext(_CTX, "YENİ MÜƏLLİM"), "value": len(new_teachers), "tone": "accent-primary"},
            {
                "label": pgettext(_CTX, "HƏLL OLUNMAYAN"),
                "value": problems,
                "note": pgettext(_CTX, "müəllim: %(n)d") % {"n": unresolved},
                "tone": "accent-danger" if problems else "accent-success",
            },
            {
                "label": pgettext(_CTX, "TƏYİN / DƏYİŞİKLİK"),
                "value": int(counters.get("assigned", 0)) + int(counters.get("reassigned", 0)),
            },
            {"label": pgettext(_CTX, "DƏYİŞMƏYƏN"), "value": int(counters.get("unchanged", 0))},
            {"label": pgettext(_CTX, "YENİ JURNAL (AÇILIŞ)"), "value": int(counters.get("offering_created", 0))},
            {"label": pgettext(_CTX, "TƏLƏBƏ QEYDİYYATI"), "value": int(counters.get("students_enrolled", 0))},
        ],
    }
    return context


__all__ = ["load_context"]

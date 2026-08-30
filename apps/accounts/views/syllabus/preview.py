"""Sillabusun OXU-REJİMİ görünüşü — siyahının baxış paneli + redaktorun «Yekun görünüş».

Bir mənbə, iki istehlakçı: siyahı ekranındakı drawer (JSON ilə) və redaktorun
``prev`` bölməsi (şablonda birbaşa). Beləliklə tələbənin, kafedra müdirinin və
müəllimin gördüyü mətn EYNİ koddan çıxır — dizayn tələbi «tələbə və kafedra ilə
eyni görünüş» məhz budur.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import SELFWORK_OPTIONS, SectionKey, SyllabusStatus

from .labels import STATUS_TONES

_CTX = "accounts.syllabus"

_EMPTY = pgettext_lazy(_CTX, "— doldurulmayıb —")

BLOCK_TITLES = {
    "description": pgettext_lazy(_CTX, "Fənnin təsviri"),
    "goal": pgettext_lazy(_CTX, "Fənnin məqsədi"),
    "outcomes": pgettext_lazy(_CTX, "Təlim nəticələri"),
    "weeks": pgettext_lazy(_CTX, "Həftəlik mövzular"),
    "methods": pgettext_lazy(_CTX, "Tədris metodları"),
    "assessment": pgettext_lazy(_CTX, "Qiymətləndirmə strukturu"),
    "selfwork": pgettext_lazy(_CTX, "Sərbəst iş"),
    "literature": pgettext_lazy(_CTX, "Ədəbiyyat"),
}

_HOUR_SHORT = {
    "lecture": pgettext_lazy(_CTX, "mühazirə"),
    "seminar": pgettext_lazy(_CTX, "seminar"),
    "lab": pgettext_lazy(_CTX, "laboratoriya"),
}

_HOURS_SUFFIX = pgettext_lazy(_CTX, "saat")
_NO_HOURS = pgettext_lazy(_CTX, "saat yazılmayıb")
_POINTS = pgettext_lazy(_CTX, "bal")

#: Baxış panelinin yuxarısındakı izah banneri — statusa görə (dizayn §3.1).
BANNERS = {
    SyllabusStatus.APPROVED.value: pgettext_lazy(
        _CTX,
        "Bu versiya təsdiqlənib və dəyişdirilə bilmir. Elektron jurnalın mövzu siyahısı, qiymətləndirmə strukturu "
        "və sərbəst iş konfiqurasiyası bu sənəddən götürülür.",
    ),
    SyllabusStatus.REVISION.value: pgettext_lazy(
        _CTX, "Kafedra müdiri düzəliş tələb edib. Qeydləri nəzərə alıb yenidən göndərin."
    ),
    SyllabusStatus.REJECTED.value: pgettext_lazy(
        _CTX, "Versiya rədd edilib. Səbəbi oxuyub yeni versiya yaradın."
    ),
    SyllabusStatus.SUBMITTED.value: pgettext_lazy(
        _CTX, "Göndərilmiş versiya baxış müddətində kilidlidir. Dəyişiklik lazımsa təqdimatı geri çağırın."
    ),
    SyllabusStatus.REVIEW.value: pgettext_lazy(
        _CTX, "Kafedra müdiri versiyanı açıb — baxış davam edir, redaktə bağlıdır."
    ),
    SyllabusStatus.ARCHIVED.value: pgettext_lazy(_CTX, "Arxiv nüsxəsi — yalnız baxış üçündür."),
    SyllabusStatus.DRAFT.value: pgettext_lazy(
        _CTX, "Qaralama tələbələrə görünmür — yalnız təsdiqlənmiş versiya aktiv olur."
    ),
}


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _lines(value) -> list:
    if isinstance(value, (list, tuple)):
        return [_text(item) for item in value if _text(item)]
    return [line for line in (_text(value).split("\n")) if line.strip()]


def _week_line(index, row) -> str:
    kinds = []
    for kind, label in _HOUR_SHORT.items():
        try:
            hours = int(row.get(kind) or 0)
        except (TypeError, ValueError):
            hours = 0
        if hours:
            kinds.append(f"{label} {hours} {_HOURS_SUFFIX}")
    topic = _text(row.get("topic")) or "—"
    tail = " + ".join(kinds) if kinds else str(_NO_HOURS)
    outcome = _text(row.get("outcome"))
    line = f"{index}. {topic} · {tail}"
    return f"{line} · {outcome}" if outcome else line


def build_preview_blocks(section_map: dict) -> list:
    """``{section_id: data}`` → oxunaqlı bloklar (başlıq + çoxsətirli gövdə)."""
    info = section_map.get(SectionKey.DESC.value, {}) or {}
    outcomes = _lines((section_map.get(SectionKey.OUT.value, {}) or {}).get("outcomes"))
    weeks = [row for row in ((section_map.get(SectionKey.WEEK.value, {}) or {}).get("rows") or []) if isinstance(row, dict)]
    method = section_map.get(SectionKey.METHOD.value, {}) or {}
    assess = section_map.get(SectionKey.ASSESS.value, {}) or {}
    selfwork = section_map.get(SectionKey.SELF.value, {}) or {}
    literature = section_map.get(SectionKey.LIT.value, {}) or {}

    option = _text(selfwork.get("option"))
    config = SELFWORK_OPTIONS.get(option)
    topics = [row for row in (selfwork.get("topics") or []) if isinstance(row, dict)]

    try:
        midterm = int(assess.get("midterm") or 0)
    except (TypeError, ValueError):
        midterm = 0
    project = max(0, 30 - midterm)

    blocks = [
        {"title": BLOCK_TITLES["description"], "body": _text(info.get("description")) or str(_EMPTY)},
        {"title": BLOCK_TITLES["goal"], "body": _text(info.get("goal")) or str(_EMPTY)},
        {
            "title": BLOCK_TITLES["outcomes"],
            "body": "\n".join(f"TN{index}. {text}" for index, text in enumerate(outcomes, start=1)) or str(_EMPTY),
        },
        {
            "title": BLOCK_TITLES["weeks"],
            "body": "\n".join(_week_line(index, row) for index, row in enumerate(weeks, start=1)) or str(_EMPTY),
        },
        {
            "title": BLOCK_TITLES["methods"],
            "body": "\n".join(_lines(method.get("methods")) + _lines(method.get("note"))) or str(_EMPTY),
        },
        {
            "title": BLOCK_TITLES["assessment"],
            "body": (
                f"10 + 10 + {midterm} + {project} + 50 = 100 {_POINTS}"
            ),
        },
        {
            "title": BLOCK_TITLES["selfwork"],
            "body": "\n".join(
                f"{index}. {_text(row.get('title')) or '—'}"
                f" ({config['per_score'] if config else 0} {_POINTS})"
                for index, row in enumerate(topics, start=1)
            )
            or str(_EMPTY),
        },
        {
            "title": BLOCK_TITLES["literature"],
            "body": "\n".join(_lines(literature.get("primary")) + _lines(literature.get("additional")))
            or str(_EMPTY),
        },
    ]
    return blocks


def build_preview_payload(syllabus) -> dict:
    """Siyahının baxış paneli üçün JSON gövdəsi."""
    from apps.syllabus.services import section_data_map, version_timeline

    version = syllabus.current_version
    status = version.status if version is not None else SyllabusStatus.DRAFT.value
    section_map = section_data_map(version) if version is not None else {}

    history = []
    for event in version_timeline(syllabus):
        actor = event.get("actor")
        who = ""
        if actor is not None:
            who = (actor.get_full_name() or "").strip() or getattr(actor, "username", "")
        history.append(
            {
                "version": event.get("version", ""),
                "what": str(SyllabusStatus(event["status"]).label) if event.get("kind") == "version" else str(
                    event.get("reason") or ""
                ),
                "who": who,
                "at": event["at"].strftime("%d.%m.%Y %H:%M") if event.get("at") else "",
            }
        )

    return {
        "code": syllabus.subject.code,
        "name": syllabus.subject.name,
        "program": syllabus.program.name if syllabus.program_id else "",
        "period": (f"{syllabus.period.year_display} · {syllabus.period.name}" if syllabus.period_id else ""),
        "version": version.label if version is not None else "—",
        "status": status,
        "status_label": str(SyllabusStatus(status).label),
        "status_tone": STATUS_TONES.get(status, "neutral"),
        "banner": str(BANNERS.get(status, "")),
        "decision_reason": (version.decision_reason or "") if version is not None else "",
        "blocks": [{"title": str(block["title"]), "body": block["body"]} for block in build_preview_blocks(section_map)],
        "history": history,
    }


__all__ = ["BANNERS", "BLOCK_TITLES", "build_preview_blocks", "build_preview_payload"]

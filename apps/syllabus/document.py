"""Sillabus SƏNƏDİNİN oxu-rejimli qurulması — ekran, drawer və PDF üçün BİR mənbə.

Dizayn təhvilinin §3.2 (`prev` bölməsi) tələbi belədir: «tələbə və kafedra ilə
EYNİ görünüş». Bu yalnız tək qurucu ilə saxlanıla bilər — ona görə bloklar
burada, domen modulunda yığılır və ÜÇ istehlakçı onu olduğu kimi işlədir:

* müəllim — redaktorun «Yekun görünüş» bölməsi + siyahının baxış paneli
  (:mod:`apps.accounts.views.syllabus.preview`);
* kafedra müdiri — təsdiq panelinin oxu hissəsi (eyni yerdən);
* jurnal və tələbə kabineti — :mod:`apps.registrar.syllabus_views` (JSON + PDF).

⚠️ Niyə mətn domen modulundadır: ``apps.accounts`` ARTIQ ``apps.registrar``-ı
idxal edir, ona görə ``registrar → accounts`` istiqaməti YENİ DÖVR yaradır və
``scripts/module_deps.py`` qapısını çökdürür. Ortaq qurucunun yeganə dövrsüz
evi ``apps.syllabus``-dur (registrar → syllabus tək istiqamətlidir).
Bölmə başlıqları onsuz da burada — ``constants.SectionKey`` etiketləri kimi —
saxlanılır; STRUKTURLAŞMIŞ kodlar (issue/keçid) isə əvvəlki kimi UI qatında
mətnə çevrilir.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from .constants import SELFWORK_OPTIONS, SectionKey, SyllabusStatus

_CTX = "syllabus.document"

_EMPTY = pgettext_lazy(_CTX, "— doldurulmayıb —")

#: Sənədin blok başlıqları — ekranda və PDF-də EYNİ ardıcıllıqla göstərilir.
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
    weeks = [
        row for row in ((section_map.get(SectionKey.WEEK.value, {}) or {}).get("rows") or []) if isinstance(row, dict)
    ]
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

    return [
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
            "body": (f"10 + 10 + {midterm} + {project} + 50 = 100 {_POINTS}"),
        },
        {
            "title": BLOCK_TITLES["selfwork"],
            "body": "\n".join(
                f"{index}. {_text(row.get('title')) or '—'}" f" ({config['per_score'] if config else 0} {_POINTS})"
                for index, row in enumerate(topics, start=1)
            )
            or str(_EMPTY),
        },
        {
            "title": BLOCK_TITLES["literature"],
            "body": "\n".join(_lines(literature.get("primary")) + _lines(literature.get("additional"))) or str(_EMPTY),
        },
    ]


def build_document(syllabus, version) -> dict:
    """Bir versiyanın TAM oxu-rejimli sənədi — başlıq bloku + 8 məzmun bloku.

    ⚠️ ``version`` AÇIQ verilir, ``syllabus.current_version``-dan GÖTÜRÜLMÜR:
    tələbə həmişə ``approved_version``-u görür, müəllim isə üzərində işlədiyi
    cari versiyanı. Mənbəni çağıran tərəf seçir — bu funksiya seçmir.
    """
    from .services import section_data_map

    status = version.status if version is not None else SyllabusStatus.DRAFT.value
    section_map = section_data_map(version) if version is not None else {}
    approver = getattr(version, "approved_by", None) if version is not None else None

    return {
        "code": syllabus.subject.code,
        "name": syllabus.subject.name,
        "program": syllabus.program.name if syllabus.program_id else "",
        "period": (f"{syllabus.period.year_display} · {syllabus.period.name}" if syllabus.period_id else ""),
        "version": version.label if version is not None else "—",
        "status": status,
        "status_label": str(SyllabusStatus(status).label),
        "approved_at": getattr(version, "approved_at", None) if version is not None else None,
        "approved_by": (approver.get_full_name() or approver.username).strip() if approver is not None else "",
        "author": _author_name(syllabus),
        "blocks": [
            {"title": str(block["title"]), "body": block["body"]} for block in build_preview_blocks(section_map)
        ],
    }


def _author_name(syllabus) -> str:
    author = getattr(syllabus, "author", None)
    if author is None:
        offering = getattr(syllabus, "offering", None)
        author = getattr(offering, "instructor", None) if offering is not None else None
    if author is None:
        return ""
    return (author.get_full_name() or author.username).strip()


__all__ = ["BLOCK_TITLES", "build_document", "build_preview_blocks"]

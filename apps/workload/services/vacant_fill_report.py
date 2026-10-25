"""``fill_vacant_from_journals`` hesabatı (Markdown, ADLI — yalnız 0600 fayla; stdout-a saylar düşür)."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .vacant_fill import (
    CONFLICT,
    FILL,
    KIND_MISSING,
    NO_JOURNAL,
    NO_SUBJECT,
    SOURCE_LEGACY,
    TEACHER_BLOCKED,
    TEACHER_UNRESOLVED,
)

_ACTIVITY = {"lecture": "Mühazirə", "seminar": "Seminar", "lab": "Laboratoriya"}
_REASON = {
    CONFLICT: "Sübut ziddiyyətlidir — bu növü bir neçə müəllim keçir (heç biri ≥ 75 % deyil)",
    KIND_MISSING: "Fənn + qrupun jurnalı var, amma bu növü keçən görünmür",
    NO_JOURNAL: "Nə yeni, nə köhnə sistemdə bu fənn + qrup üçün jurnal (keçirilmiş dərs) yoxdur",
    NO_SUBJECT: "Sətrin fənni seçilməyib — jurnalla tutuşdurmaq olmur",
    TEACHER_UNRESOLVED: "Köhnə jurnalın müəllimi yeni sistemdə hesabla tutuşmadı",
    TEACHER_BLOCKED: "Dərsi keçən müəllimin hesabı aktiv deyil / bloklanıb / arxivdədir",
}


def _names(items) -> dict:
    ids = set()
    for item in items:
        ids |= {pk for pk in item.evidence if pk} | set(item.owners) | set(item.hints)
        ids |= {journal["teacher_id"] for journal in item.legacy if journal["teacher_id"]}
    users = get_user_model().objects.filter(pk__in=ids)
    return {user.pk: f"{user.get_full_name() or user.username} ({user.username})" for user in users}


def _subject(row) -> str:
    return (row.subject.name if row.subject_id else "") or row.subject_text or "—"


def _groups(row) -> str:
    return ", ".join(sorted(group.name for group in row.groups.all())) or row.groups_text or "—"


def _who(names, pk) -> str:
    return names.get(pk, str(pk)) if pk else "tutuşmayan müəllim"


def _evidence(item, names) -> str:
    unit = "jurnal tarixi" if item.source == SOURCE_LEGACY else "dərs"
    where = "köhnə jurnal" if item.source == SOURCE_LEGACY else "yeni jurnal (müəllimli dərs)"
    pool = ", seminar↔lab hovuzu" if item.pooled else ""
    parts = [f"{_who(names, pk)}: {count}" for pk, count in item.evidence.most_common()]
    return f"{where}{pool} — {'; '.join(parts)} {unit}" if parts else "—"


def _legacy(item, names) -> str:
    parts = []
    for journal in sorted(item.legacy, key=lambda j: -int(j["dates"] or 0)):
        kinds = "+".join(_ACTIVITY.get(kind, kind)[:3].lower() for kind in journal["kinds"]) or "?"
        parts.append(f"{_who(names, journal['teacher_id'])} [{kinds}, {journal['dates']} tarix]")
    return "; ".join(parts) or "—"


def _hints(item, names) -> str:
    return "; ".join(f"{_who(names, pk)} ({count})" for pk, count in item.hints.most_common(3)) or "—"


def _cell(value) -> str:
    return str(value).replace("|", "/").replace("\n", " ")


def _table(lines: list, header: tuple, rows) -> None:
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")


def build_report(*, mode, batch, year, season, before, after, items, counts) -> str:
    names = _names(items)
    lines = [
        f"# Vakant saatların doldurulması — jurnal datası ({year}, {season})",
        "",
        f"* Rejim: **{mode}** · paket: `{batch}`",
        "* Qayda: həmin növü keçən müəllim sübutun ≥ 75 %-ni təşkil edirsə vakant saat ona yazılır (rəsmi düzəliş "
        "qeydi, geri qaytarıla bilər). Sübut: yeni jurnalın müəllimli dərsləri, yoxdursa köhnə sistemin cari semestr "
        "jurnalı (müəllim + elan etdiyi növlər, dərs tarixi sayı). Qalanı aşağıdakı siyahıdadır (kafedra müdirinə).",
        "",
        "## Vakant: əvvəl → sonra (kafedra üzrə)",
        "",
    ]
    chairs = sorted(set(before) | set(after))
    total = [sum(v[key] for v in data.values()) for data in (before, after) for key in ("rows", "hours")]
    _table(
        lines,
        ("Kafedra", "Sətir əvvəl", "Saat əvvəl", "Sətir sonra", "Saat sonra"),
        [
            (chair, *(data.get(chair, {}).get(key, 0) for data in (before, after) for key in ("rows", "hours")))
            for chair in chairs
        ]
        + [("**Cəmi**", *total)],
    )
    lines += ["", "## Saylar", ""] + [f"* {key}: {value}" for key, value in sorted(counts.items())]
    filled = [item for item in items if item.decision == FILL]
    heading = f"## Sübutu tapılan ({len(filled)} cüt, {sum(i.hours for i in filled)} saat) — nəticə sütununa baxın"
    lines += ["", heading, ""]
    _table(
        lines,
        ("Kafedra", "Fənn", "Qrup(lar)", "Növ", "Saat", "Müəllim", "Sübut", "Kənar", "Nəticə"),
        [
            (
                item.chair.name,
                _subject(item.row),
                _groups(item.row),
                _ACTIVITY.get(item.activity, item.activity),
                item.hours,
                _who(names, item.teacher_id),
                f"{_evidence(item, names)} ({item.share:.0%})",
                "bəli (saathesabı)" if item.outside else "",
                item.result or ("dry-run" if mode != "apply" else ""),
            )
            for item in filled
        ],
    )
    rest = [item for item in items if item.decision != FILL]
    lines += [
        "",
        f"## Məlumat yoxdur / qərar lazımdır ({len(rest)} cüt, {sum(i.hours for i in rest)} saat) — kafedra müdirinə",
        "",
    ]
    for chair in sorted({item.chair.name for item in rest}):
        chair_items = [item for item in rest if item.chair.name == chair]
        lines += [f"### {chair} ({len(chair_items)} cüt, {sum(i.hours for i in chair_items)} saat)", ""]
        _table(
            lines,
            (
                "Fənn", "Qrup(lar)", "Növ", "Saat", "Səbəb", "Sübut", "Köhnə jurnal(lar)", "Yeni jurnalın sahibi",
                "Bu fənni başqa qruplarda keçir", "Tələbə",
            ),  # fmt: skip
            [
                (
                    _subject(item.row),
                    _groups(item.row),
                    _ACTIVITY.get(item.activity, item.activity),
                    item.hours,
                    _REASON.get(item.decision, item.decision),
                    _evidence(item, names),
                    _legacy(item, names),
                    ", ".join(_who(names, pk) for pk in sorted(item.owners)) or "—",
                    _hints(item, names),
                    item.students,
                )
                for item in chair_items
            ],
        )
        lines.append("")
    blocked = [item for item in filled if item.result.startswith(("blocked", "skipped"))]
    if blocked:
        lines += ["## Yazıla bilmədi (bloker)", ""]
        lines += [
            f"* {_cell(item.chair.name)} · {_cell(_subject(item.row))} · {_cell(_groups(item.row))} · "
            f"{_ACTIVITY.get(item.activity, item.activity)} — `{item.result}`"
            for item in blocked
        ]
    return "\n".join(lines) + "\n"


__all__ = ["build_report"]

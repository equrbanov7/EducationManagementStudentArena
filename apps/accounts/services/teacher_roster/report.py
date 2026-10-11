"""Tutuşdurma planının HESABATI — konsol xülasəsi və markdown fayl (sahib 2026-10-11).

Şəxsi məlumat: hər kateqoriyada ən çoxu ``max_names`` ad göstərilir (defolt 10); tam siyahı yalnız
``--details`` ilə (lokal fayl, repoya düşmür).
"""

from __future__ import annotations

from collections import Counter

from .matching import (
    STATUS_AMBIGUOUS,
    STATUS_CONFLICT,
    STATUS_FUZZY,
    STATUS_MATCHED,
    STATUS_NOT_FOUND,
    STATUS_REVIEW,
    STATUS_STUDENT_ONLY,
)

STATUS_LABELS = {
    STATUS_MATCHED: "tapıldı (dəqiq)",
    STATUS_FUZZY: "tapıldı (yazılış fərqi və ya tərs sıra, ata adı eyni)",
    STATUS_AMBIGUOUS: "çox mənalı (bir neçə hesab)",
    STATUS_CONFLICT: "ad-soyad eyni, ata adı fərqli",
    STATUS_REVIEW: "oxşar hesab var — yoxlanmalı",
    STATUS_STUDENT_ONLY: "yalnız tələbə hesabı uyğun gəlir",
    STATUS_NOT_FOUND: "hesab yoxdur",
}
STATUS_ORDER = list(STATUS_LABELS)
FLAG_LABELS = {
    "chair_mismatch": "kafedra fərqlidir (köçürülmür, yalnız hesabat)",
    "no_chair": "hesabın kafedra üzvlüyü yoxdur",
    "account_blocked": "hesab artıq bloklu/silinib",
    "no_teacher_role": "müəllim rolu yoxdur",
    "multi_row": "faylda bir neçə sətir (ştat cəmlənir)",
    "patronymic_unverified": "ata adı bir tərəfdə boşdur",
    "patronymic_spelling": "ata adının yazılışı fərqlidir (məs. Rəhim/Rahim)",
    "typo": "ad/soyadda yazılış fərqi və ya tərs sıra",
}


def summary(plan) -> dict:
    statuses = Counter(match.status for match in plan.matches)
    flags = Counter(flag for user in plan.users.values() for flag in user.flags)
    profile_fields = Counter(field for user in plan.users.values() for field in user.profile_changes)
    workload = Counter(
        "create" if user.workload["created"] else "update"
        for user in plan.users.values()
        if user.workload and user.workload["changed"]
    )
    protected = Counter(reason.split(":")[0] for _account, reasons in plan.protected for reason in reasons)
    return {
        "rows": len(plan.roster.rows),
        "chairs": len(plan.roster.chairs),
        "skipped_rows": len(plan.roster.skipped),
        "statuses": dict(statuses),
        "matched_accounts": len(plan.users),
        "flags": dict(flags),
        "profile_fields": dict(profile_fields),
        "workload": dict(workload),
        "block": len(plan.block),
        "protected": len(plan.protected),
        "protected_reasons": dict(protected),
        "already_blocked": len(plan.already_blocked),
    }


def _names(items, limit):
    items = list(items)
    shown = ", ".join(items[:limit])
    return f"{shown}{' …' if len(items) > limit else ''}" if items else "—"


def per_chair(plan) -> list:
    rows = {}
    for match in plan.matches:
        bucket = rows.setdefault(match.row.chair, Counter())
        bucket[match.status] += 1
        bucket["rows"] += 1
    for user in plan.users.values():
        for row in user.rows:
            for flag in ("chair_mismatch", "no_chair"):
                if flag in user.flags:
                    rows[row.chair][flag] += 1
    return [(chair, rows.get(chair, Counter())) for chair in plan.roster.chairs]


def render_markdown(plan, *, max_names: int = 10, title: str = "") -> str:
    data = summary(plan)
    out = [f"# {title or 'Forma 7 — müəllim siyahısının tutuşdurulması'}", ""]
    out.append(
        f"Təşkilat: `{plan.organization.slug}` · tədris ili: **{plan.academic_year}** · "
        f"fayl: {data['rows']} sətir, {data['chairs']} kafedra (ötürülən sətir: {data['skipped_rows']})"
    )
    out += ["", "## Sətirlərin tutuşdurulması", "", "| Kateqoriya | Sətir |", "|---|---:|"]
    for status in STATUS_ORDER:
        out.append(f"| {STATUS_LABELS[status]} | {data['statuses'].get(status, 0)} |")
    out.append(f"| **uyğun hesab (unikal)** | **{data['matched_accounts']}** |")

    out += ["", "## Uyğun hesablar üzrə qeydlər", "", "| Qeyd | Hesab |", "|---|---:|"]
    for flag, label in FLAG_LABELS.items():
        out.append(f"| {label} | {data['flags'].get(flag, 0)} |")
    out += [
        "",
        f"Profil yeniləməsi: elmi ad {data['profile_fields'].get('academic_title', 0)}, "
        f"elmi dərəcə {data['profile_fields'].get('academic_degree', 0)} hesabda. "
        f"Yük profili ({plan.academic_year}): yeni {data['workload'].get('create', 0)}, "
        f"dəyişən {data['workload'].get('update', 0)}.",
    ]

    out += ["", "## Bloklama", ""]
    out.append(f"* bloklanacaq müəllim hesabı (siyahıda yoxdur): **{data['block']}**")
    out.append(f"* qorunan (inzibati rol, sahib, superuser, tələbə …): **{data['protected']}**")
    for reason, count in sorted(data["protected_reasons"].items()):
        out.append(f"  * `{reason}`: {count}")
    out.append(f"* siyahıda yoxdur, onsuz da bloklu/silinmiş: {data['already_blocked']}")

    out += [
        "",
        "## Kafedralar",
        "",
        "| Fayldakı kafedra | Sistemdəki bölmə | Bal | Sətir | Tapıldı | Çox mənalı | Yoxdur | Kafedra fərqli |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for chair, counts in per_chair(plan):
        mapped = plan.chair_map.get(chair, {})
        unit = mapped.get("unit")
        found = counts.get(STATUS_MATCHED, 0) + counts.get(STATUS_FUZZY, 0)
        unclear = sum(counts.get(status, 0) for status in (STATUS_AMBIGUOUS, STATUS_CONFLICT, STATUS_REVIEW))
        out.append(
            f"| {chair} | {unit[1] if unit else '— (uyğun bölmə yoxdur)'} | {mapped.get('score', 0):.2f} | "
            f"{counts.get('rows', 0)} | {found} | {unclear} | "
            f"{counts.get(STATUS_NOT_FOUND, 0) + counts.get(STATUS_STUDENT_ONLY, 0)} | "
            f"{counts.get('chair_mismatch', 0)} |"
        )

    out += ["", f"## Nümunələr (hər kateqoriyada ən çoxu {max_names} ad)", ""]
    for status in (STATUS_NOT_FOUND, STATUS_AMBIGUOUS, STATUS_CONFLICT, STATUS_REVIEW, STATUS_STUDENT_ONLY):
        names = [match.row.name.display for match in plan.matches if match.status == status]
        out.append(f"* {STATUS_LABELS[status]} ({len(names)}): {_names(names, max_names)}")
    fuzzy = [
        f"{match.row.name.display} → {match.account.display}" for match in plan.matches if match.status == STATUS_FUZZY
    ]
    out.append(f"* {STATUS_LABELS[STATUS_FUZZY]} ({len(fuzzy)}): {_names(fuzzy, max_names)}")
    out.append(f"* bloklanacaq ({len(plan.block)}): {_names((a.display for a in plan.block), max_names)}")
    out.append(
        f"* qorunan ({len(plan.protected)}): "
        + _names((f"{a.display} [{', '.join(r)}]" for a, r in plan.protected), max_names)
    )
    diffs = [
        f"{user.account.display}: "
        + ", ".join(f"{field} {old or '∅'}→{new}" for field, (old, new) in user.profile_changes.items())
        for user in plan.users.values()
        if user.profile_changes
    ]
    out.append(f"* profil fərqləri ({len(diffs)}): {_names(diffs, max_names)}")
    if plan.roster.skipped:
        out.append(f"* ötürülən sətirlər: {_names((f'#{n} {reason}' for n, _t, reason in plan.roster.skipped), 20)}")
    return "\n".join(out) + "\n"


def details_csv_rows(plan):
    """Tam siyahı (``--details``): sətir, kafedra, ad, status, hesab, qeydlər."""
    yield ["row", "chair", "name", "status", "username", "flags", "title", "degree", "rate"]
    flags_by_user = {user_id: user.flags for user_id, user in plan.users.items()}
    for match in plan.matches:
        account = match.account
        yield [
            match.row.row_no,
            match.row.chair,
            match.row.name.display,
            match.status,
            account.username if account else "|".join(candidate.username for candidate in match.candidates),
            ",".join(flags_by_user.get(account.user_id, []) if account else match.flags),
            match.row.title or "",
            match.row.degree or "",
            match.row.rate.kind,
        ]
    for account in plan.block:
        yield ["", "", account.display, "to_block", account.username, "", "", "", ""]
    for account, reasons in plan.protected:
        yield ["", "", account.display, "protected", account.username, ",".join(reasons), "", "", ""]


__all__ = ["STATUS_LABELS", "details_csv_rows", "per_chair", "render_markdown", "summary"]

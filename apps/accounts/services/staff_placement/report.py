"""Yerləşdirmə planının hesabatı: saylar (stdout üçün) + ADLI Markdown/CSV (şəxsi məlumat — 0600 lokal fayl)."""

from __future__ import annotations

import os
from collections import Counter

from .plan import DEACTIVATE, JOIN, PRIMARY

NOTE_LABELS = {
    "home_unresolved": "ştat kafedrası avtomatik düzəlmir (əsas üzvlük inzibati roldadır / yük köhnə kafedradadır)",
    "home_ambiguous": "faylda bir neçə ştat kafedrası — hansı əsasdır, qərar lazımdır",
    "journal_chair_unknown": "cari jurnalın kafedrası məlum deyil — siyahıdakı kafedra üzvlüyünə toxunulmadı",
    "stray_primary_kept": "artıq kafedradakı üzvlük əsasdır — deaktiv edilmədi",
}


def summary(plan, block_plan=None) -> dict:
    people = plan.people.values()
    data = {
        "evidence_forma7": len(plan.sources.forma7),
        "evidence_structure": len(plan.sources.structure),
        "evidence_loads": len(plan.sources.loads),
        "matched_people": len(plan.people),
        "dormant_matched": len(plan.dormant_ids),
        "unmatched_rows": len(plan.unmatched),
        "home_mismatch_before": sum(1 for p in people if p.expected_home and p.current_home != p.expected_home),
        "home_mismatch_after": sum(1 for p in people if p.expected_home and p.final_home != p.expected_home),
        "home_ambiguous": sum(1 for p in people if "home_ambiguous" in p.notes),
        "join": sum(1 for a in plan.actions if a.kind == JOIN),
        "primary": sum(1 for a in plan.actions if a.kind == PRIMARY),
        "deactivate": sum(1 for a in plan.actions if a.kind == DEACTIVATE),
        "duplicate_groups": len(
            {frozenset({p.user_id, *(a.user_id for a in p.duplicates)}) for p in people if p.duplicates}
        ),
        "roles_missing": len(plan.roles_missing),
        "roles_stale": len(plan.roles_stale),
        "unlisted_chairs": len(plan.unlisted_chairs),
        "incomplete_accounts": len(plan.incomplete_accounts),
    }
    if block_plan is not None:
        data["block"] = len(block_plan.block)
        data["block_protected_teaching_now"] = sum(
            1 for _account, reasons in block_plan.protected if "teaching_now" in reasons
        )
        data["block_already_blocked"] = len(block_plan.already_blocked)
    data["unmatched_by_status"] = dict(Counter(result.status for _item, result in plan.unmatched))
    return data


def _who(account) -> str:
    name = " ".join(part for part in (account.last, account.first, account.patronymic) if part) or "—"
    state = "" if account.is_active else " · BLOKLU"
    return f"{name} (`{account.username}`{state})"


def _membership_text(plan, user_id) -> str:
    names = plan.facts.unit_names
    rows = sorted(plan.facts.memberships.get(user_id, []), key=lambda row: (not row["is_primary"], row["role__name"]))
    parts = [
        f"{row['role__name']}@{names.get(row['scope_unit_id'], '—')}{'*' if row['is_primary'] else ''}" for row in rows
    ]
    return "; ".join(parts) or "aktiv üzvlük yoxdur"


def _load_text(plan, user_id) -> str:
    names = plan.facts.unit_names
    load = plan.facts.load_chairs.get(user_id, {})
    hours = ", ".join(f"{names.get(chair, chair)} {value} s" for chair, value in sorted(load.items()))
    journals = plan.facts.journal_count.get(user_id, 0)
    return f"yük: {hours or '—'} · cari jurnal: {journals}"


def render_markdown(plan, block_plan=None) -> str:
    names = plan.facts.unit_names
    data = summary(plan, block_plan)
    out = [f"# Heyət yerləşdirmə auditi — {plan.organization.slug} · {plan.academic_year}", ""]
    out += ["## Saylar", ""] + [f"* `{key}`: {value}" for key, value in data.items()] + [""]
    out += ["## Fayldakı kafedra adı → sistem kafedrası", ""]
    for chair, mapped in sorted(plan.sources.chair_map.items()):
        unit = mapped.get("unit")
        out.append(
            f"* {chair} → {unit[1] if unit else '**tapılmadı**'} ({mapped.get('source')}, {mapped.get('score')})"
        )
    out += ["", "## Siyahılarda kafedra kimi OLMAYAN kafedra tipli bölmələr (qərar)", ""]
    for row in plan.unlisted_chairs:
        out.append(
            f"* **{row['name']}** — aktiv üzvlük {row['members']} (köçürmədən sonra {row['members_left']}), "
            f"{plan.academic_year} tapşırığı: {'var' if row['tasks'] else 'yox'}, cari açılış (fənn kafedrası): "
            f"{row['offerings']}"
        )
    out += ["", "## Ştat (əsas) kafedrası uyğunsuzluqları", ""]
    out.append("| Şəxs | Sistemdə | Faylda | Mənbə | Əməllər | Sonra | Qeyd |")
    out.append("|---|---|---|---|---|---|---|")
    for person in sorted(plan.people.values(), key=lambda p: (p.account.last_key, p.account.first_key)):
        mismatch = person.expected_home and person.current_home != person.expected_home
        if not (mismatch or "home_ambiguous" in person.notes):
            continue
        acts = ", ".join(f"{a.kind}:{names.get(a.unit_id, '—')}" for a in person.actions) or "—"
        expected = names.get(person.expected_home) or " / ".join(names.get(u, u) for u in person.home_options)
        notes = "; ".join(NOTE_LABELS.get(n, n) for n in person.notes if n != "journal_chair_unknown")
        out.append(
            f"| {_who(person.account)} | {names.get(person.current_home, '—')} | {expected} | {person.home_reason} "
            f"| {acts} | {names.get(person.final_home, '—')} | {notes} |"
        )
    out += ["", "## Əlavə müəllim üzvlüyü (dərs yükü / Forma 7 kafedrası) və deaktiv ediləcək artıq üzvlüklər", ""]
    for person in sorted(plan.people.values(), key=lambda p: (p.account.last_key, p.account.first_key)):
        acts = [a for a in person.actions if a.kind in (JOIN, DEACTIVATE)]
        if acts:
            text = ", ".join(f"{'+' if a.kind == JOIN else '−'}{names.get(a.unit_id, '—')}" for a in acts)
            dormant = " · hesab yalnız deaktiv üzvlüklə qalmışdı" if person.user_id in plan.dormant_ids else ""
            out.append(f"* {_who(person.account)}: {text}{dormant}")
    out += ["", "## Dublikat / adaş hesablar (QƏRAR — birləşdirmə əl ilə)", ""]
    seen_groups = set()
    for person in sorted(plan.people.values(), key=lambda p: (p.account.last_key, p.account.first_key)):
        group = frozenset({person.user_id, *(account.user_id for account in person.duplicates)})
        if not person.duplicates or group in seen_groups:
            continue
        seen_groups.add(group)
        out.append(
            f"* {_who(person.account)} — {_membership_text(plan, person.user_id)}; {_load_text(plan, person.user_id)}"
        )
        for other in person.duplicates:
            out.append(
                f"  * ↔ {_who(other)} — {_membership_text(plan, other.user_id)}; {_load_text(plan, other.user_id)}"
            )
    out += ["", "## Tutuşmayan sətirlər", ""]
    for item, result in plan.unmatched:
        candidates = ", ".join(f"`{account.username}`" for account in result.candidates[:5]) or "—"
        out.append(
            f"* [{item.source}] {item.raw_name} — {item.section} · **{result.status}** · namizədlər: {candidates}"
        )
    out += ["", "## Rollar (struktur siyahısı ilə)", "", "### Çatışmayan rol (siyahıda var, sistemdə yox)", ""]
    for person, item in plan.roles_missing:
        who = _who(person.account) if person else f"{item.raw_name} (hesab tutuşmadı)"
        out.append(f"* {who}: `{item.kind}` @ {item.unit_name} ({item.detail})")
    out += ["", "### Siyahıda olmayan rol (sistemdə var — köhnəlmiş ola bilər)", ""]
    for user_id, role, unit_id in plan.roles_stale:
        account = plan.accounts.get(user_id)
        who = _who(account) if account else f"istifadəçi #{user_id}"
        out.append(f"* {who}: `{role}` @ {names.get(unit_id, unit_id)}")
    out += ["", "## Natamam / sınaq görünüşlü müəllim hesabları (yalnız hesabat)", ""]
    for row in plan.incomplete_accounts:
        suggest = " · **blok təklifi**" if row["suggest_block"] else ""
        out.append(
            f"* {_who(row['account'])} — {', '.join(row['reasons'])}; yük {row['load_hours']} s, "
            f"cari jurnal {row['journals']}{suggest}"
        )
    if block_plan is not None:
        out += ["", "## Bloklama (Forma 7-də yoxdur, dərs yükü / cari jurnal yoxdur)", ""]
        for account in block_plan.block:
            out.append(f"* {_who(account)}")
        out += ["", "### Forma 7-də yoxdur, amma DƏRS DEYİR — bloklanmır", ""]
        for account, reasons in block_plan.protected:
            if "teaching_now" in reasons:
                out.append(f"* {_who(account)} — {', '.join(reasons)}")
    return "\n".join(out) + "\n"


def details_rows(plan) -> list:
    names = plan.facts.unit_names
    rows = [["istifadəçi", "ad", "əməl", "kafedra", "ştat_sistemdə", "ştat_faylda", "ştat_sonra", "qeyd"]]
    for person in plan.people.values():
        account = person.account
        name = " ".join(part for part in (account.last, account.first, account.patronymic) if part)
        for action in person.actions or [None]:
            rows.append(
                [
                    account.username,
                    name,
                    action.kind if action else "",
                    names.get(action.unit_id, "") if action else "",
                    names.get(person.current_home, ""),
                    names.get(person.expected_home, ""),
                    names.get(person.final_home, ""),
                    ";".join(person.notes),
                ]
            )
    return rows


def write_private(path, text: str) -> None:
    """0600 fayl (şəxsi məlumat) — mövcud faylın icazəsi də daraldılır."""
    descriptor = os.open(os.path.expanduser(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(os.path.expanduser(path), 0o600)


__all__ = ["details_rows", "render_markdown", "summary", "write_private"]

"""Dublikat planının ADLI hesabatı (Markdown + CSV) — şəxsi məlumatdır, 0600 faylda saxlanılır, loga düşmür."""

from __future__ import annotations

from .plan import MODE_FLIP, MODE_RIM_PASSWORD, STATUS_OK

STATUS_LABELS = {
    STATUS_OK: "qərar verildi",
    "all_blocked": "hamısı artıq bloklu — toxunulmadı",
    "kept_blocked": "jurnallı/saxlanılacaq hesab BLOKLUDUR — əl ilə qərar",
    "fin_conflict": "iki hesabda FİN var (FİN unikaldır → fərqli adamlar) — toxunulmadı",
    "patronymic_conflict": "qrupda ata adı ziddiyyəti — toxunulmadı",
}
MODE_LABELS = {
    "normal": "adi: saxlanılan hesab dəyişmir",
    MODE_FLIP: "XÜSUSİ: jurnallı hesab heç vaxt girməyib → jurnallar «Fənn təhvili» ilə GİRƏN hesaba keçir",
    MODE_RIM_PASSWORD: "XÜSUSİ: jurnallı hesab heç vaxt girməyib, amma dərs yükü var → o saxlanılır, girən hesab "
    "dondurulur, RİM parol təyin etməlidir",
}
SKIP_LABELS = {
    "protected": "qorunan hesab (superuser / təşkilatın sahibi) — dondurulmur",
    "has_load": "dublikatın dərs yükü var (yük sənədinin düzəliş axını lazımdır) — dondurulmur, əl ilə",
    "handover_blocked": "açılışın təhvili mümkün deyil (bağlı jurnal / bitmiş dövr) — dondurulmur",
}


def _login(person) -> str:
    return person.last_login.strftime("%Y-%m-%d") if person.last_login else "heç vaxt"


def _roles(person) -> str:
    return ", ".join(sorted({row["role"] for row in person.memberships})) or "—"


def _row(person) -> str:
    state = "aktiv" if person.is_active else "BLOKLU"
    fin = "var" if person.has_fin else "—"
    return (
        f"| `{person.username}` | {person.display} | {state} | {_login(person)} | {person.journals} | "
        f"{person.load} | {_roles(person)} | {fin} |"
    )


def _cluster_md(cluster, index: int) -> list:
    lines = [f"### {index}. {cluster.members[0].display}", ""]
    lines += [
        "| Hesab | Ad | Vəziyyət | Son giriş | Jurnal | Yük | Rollar | FİN |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [_row(person) for person in cluster.members]
    lines.append("")
    lines.append(f"* Status: **{STATUS_LABELS.get(cluster.status, cluster.status)}**")
    if cluster.status == STATUS_OK:
        lines.append(f"* Saxlanılan: **`{cluster.kept.username}`** — {MODE_LABELS.get(cluster.mode, cluster.mode)}")
        if cluster.journal_holder is not None:
            lines.append(
                f"* Jurnallar `{cluster.journal_holder.username}` → `{cluster.kept.username}` "
                f"({len(cluster.journal_holder.owned)} açılış)"
            )
        for action in cluster.dups:
            person = action.person
            if action.skip:
                lines.append(f"* `{person.username}`: {SKIP_LABELS.get(action.skip, action.skip)}")
                continue
            if not action.writes:
                lines.append(f"* `{person.username}`: artıq dondurulub (dəyişiklik yoxdur)")
                continue
            parts = []
            if action.transfer:
                roles = ", ".join(row["role"] for row in action.transfer)
                parts.append(f"rollar saxlanılana verilir: {roles}")
            if action.heads:
                parts.append(f"{len(action.heads)} bölmənin rəhbəri saxlanılan olur")
            if action.handover:
                parts.append(f"{len(action.handover)} jurnal təhvil verilir")
            if action.deactivate:
                parts.append(f"{len(action.deactivate)} üzvlük deaktiv")
            if action.block:
                parts.append("hesab DONDURULUR")
            if person.history:
                parts.append(f"cari semestrdə {person.history} dərs/qiymət sətri onun adında qalır (tarix)")
            lines.append(f"* `{person.username}`: " + "; ".join(parts))
    elif cluster.kept is not None:
        lines.append(f"* Saxlanılmalı (jurnal/yük): `{cluster.kept.username}`")
    for person, _reason in cluster.excluded:
        lines.append(f"* Eyni ad, ata adı fərqli — BAŞQA ADAM, toxunulmadı: `{person.username}` ({person.display})")
    lines.append("")
    return lines


def render_markdown(plan, *, batch: str = "", title_suffix: str = "") -> str:
    from .plan import summary

    lines = [f"# Dublikat heyət hesabları — {plan.organization.slug} · {plan.academic_year}{title_suffix}", ""]
    if batch:
        lines += [f"Paket: `{batch}` (geri: `freeze_duplicate_accounts --org … --undo {batch}`)", ""]
    lines += ["## Saylar", ""] + [f"* {key}: {value}" for key, value in summary(plan).items()] + [""]
    rim = [cluster for cluster in plan.clusters if cluster.status == STATUS_OK and cluster.mode == MODE_RIM_PASSWORD]
    lines += ["## RİM — «parol təyin et» siyahısı", ""]
    if rim:
        lines.append(
            "Jurnallı hesab saxlanılır, şəxsin girdiyi hesab dondurulur — RİM saxlanılan hesaba parol verməlidir:"
        )
        for cluster in rim:
            frozen = ", ".join(f"`{a.person.username}`" for a in cluster.dups if a.block or not a.person.is_active)
            lines.append(f"* `{cluster.kept.username}` ({cluster.kept.display}) — dondurulan: {frozen or '—'}")
    else:
        lines.append("Yoxdur.")
    never = [
        cluster
        for cluster in plan.clusters
        if cluster.status == STATUS_OK and cluster.mode != MODE_RIM_PASSWORD and cluster.kept.last_login is None
    ]
    if never:
        lines += ["", "Saxlanılan, amma HEÇ VAXT girməmiş hesablar (dublikat da girməyib — məlumat üçün):"]
        lines += [f"* `{cluster.kept.username}` ({cluster.kept.display})" for cluster in never]
    lines += ["", "## Qruplar", ""]
    for index, cluster in enumerate(plan.clusters, start=1):
        lines += _cluster_md(cluster, index)
    lines += ["## Qeyri-müəyyən (bir neçə namizəd — toxunulmadı)", ""]
    if plan.ambiguous:
        for person, candidates in plan.ambiguous:
            names = ", ".join(f"`{other.username}`" for other in candidates)
            lines.append(f"* `{person.username}` ({person.display}) ↔ {names}")
    else:
        lines.append("Yoxdur.")
    lines += ["", "## Oxşar ad, ata adı fərqli və ya yoxlanıla bilmir (başqa adamlar — toxunulmadı)", ""]
    for bucket in plan.homonyms:
        lines.append("* " + " ↔ ".join(f"`{person.username}` ({person.display})" for person in bucket))
    if not plan.homonyms:
        lines.append("Yoxdur.")
    return "\n".join(lines) + "\n"


def csv_rows(plan) -> list:
    rows = [["qrup", "status", "rejim", "hesab", "ad", "aktiv", "son_giris", "jurnal", "yuk", "rollar", "qerar"]]
    for index, cluster in enumerate(plan.clusters, start=1):
        actions = {action.person.user_id: action for action in cluster.dups}
        for person in cluster.members:
            if cluster.kept is person and cluster.status == STATUS_OK:
                decision = "saxla"
            elif person.user_id in actions:
                action = actions[person.user_id]
                decision = f"ötür:{action.skip}" if action.skip else ("dondur" if action.writes else "artıq dondurulub")
            else:
                decision = "toxunma"
            rows.append([
                index, cluster.status, cluster.mode, person.username, person.display, int(person.is_active),
                _login(person), person.journals, person.load, _roles(person), decision,
            ])  # fmt: skip
    return rows


__all__ = ["csv_rows", "render_markdown"]

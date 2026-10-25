"""``fix_workload_overcount`` adlı hesabatı (Markdown) — şəxs adları VAR, fayl 0600 / şifrəli artifakt.

Stdout-a heç nə yazmır; əmr yalnız saylar çap edir.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.contrib.auth import get_user_model
from django.utils import timezone

from ..models import TeacherWorkloadProfile
from .norms import norms_for
from .overcount_detect import TEACHING_ACTIVITIES

ACT = {"lecture": "Mühazirə", "seminar": "Seminar", "lab": "Laboratoriya"}
SEASON = {"fall": "payız", "spring": "yaz", "summer": "yay"}
DECISION_TEXT = {
    "teachers_differ": "müəllimlər fərqlidir — hansı bölgünün düzgün olduğu kafedranın qərarıdır",
    "hours_differ": "saatlar fərqlidir — hansı sətrin düzgün olduğu kafedranın qərarıdır",
    "overlap_complex": "qrup dəstləri qarışıq kəsişir (örtən sətir + bir-birini kəsən qrup sətirləri)",
    "objection_open": "sətirdə müəllim etirazı var (etiraz reyestri append-only) — əvvəl etiraz həll olunmalıdır",
}


class _Names:
    def __init__(self, ids):
        users = get_user_model().objects.filter(pk__in=[pk for pk in ids if pk])
        self.names = {user.pk: (user.get_full_name() or user.username).strip() for user in users}

    def __call__(self, pk) -> str:
        return self.names.get(pk, "VAKANT") if pk else "VAKANT"


def _groups(info) -> str:
    return ", ".join(sorted(info.group_names.values())) or "—"


def _hours(info) -> str:
    return "/".join(f"{ACT[a][0]}{info.hours[a]}" for a in TEACHING_ACTIVITIES if info.hours[a]) or "0"


def _assign(info, name) -> str:
    return "; ".join(f"{ACT.get(a[1], a[1])[:3]} {name(a[0])} {a[2]}" for a in info.assignments) or "bölgü yoxdur"


def _row_line(info, name) -> str:
    return (
        f"{info.chair_name} · {SEASON.get(info.row.season, info.row.season)} · **{info.subject}** · {_groups(info)} · "
        f"{_hours(info)} · [{info.source}] · {_assign(info, name)}"
    )


def _pct(value: int, norm: int) -> str:
    return f"{round(value * 100 / norm)}%" if norm else "—"


def load_table(organization, year, before: dict, after: dict, focus: set, name) -> list[str]:
    ids = set(before) | set(after)
    profiles = {
        p.teacher_id: p
        for p in TeacherWorkloadProfile.objects.filter(
            organization=organization, teacher_id__in=ids, academic_year=year
        )
    }
    norms = norms_for(organization, list(ids), profiles)
    lines = [
        "| Müəllim | Norma | Əvvəl | % | Sonra | % | Fərq |",
        "|---|---|---|---|---|---|---|",
    ]
    rows = []
    for teacher_id in ids:
        norm = norms.get(teacher_id) or 0
        old = before.get(teacher_id, {}).get("total", 0)
        new = after.get(teacher_id, {}).get("total", 0)
        over = norm and (old > norm or new > norm)
        if over or teacher_id in focus:
            rows.append((name(teacher_id), norm, old, new))
    for label, norm, old, new in sorted(rows, key=lambda r: -r[2]):
        lines.append(f"| {label} | {norm} | {old} | {_pct(old, norm)} | {new} | {_pct(new, norm)} | {new - old:+d} |")
    return lines


def build_report(*, organization, year, mode, batch, first, last, fixer, before, after, focus) -> str:
    ids = {a[0] for info in first.rows for a in info.assignments} | set(before) | set(after)
    name = _Names(ids)
    out = [
        f"# Dərs yükü — artıq sayılan saat auditi ({year})",
        "",
        f"Hazırlanma: {timezone.localtime():%Y-%m-%d %H:%M}. Rejim: **{mode}**. Paket: `{batch}`.",
        "",
        "## 0. Kök səbəb",
        "",
        "Müəllimin yükü = bütün kafedraların tapşırıqlarındakı bölgü saatlarının cəmidir; hesab düzgündür, ARTIQ "
        "saat datadadır. Model axını tanıyır (çox qruplu sətir = bir axın: mühazirə `union_count`, seminar/lab "
        "`subgroup_count` çarpanı ilə), amma eyni dərs bir neçə sətirdə yazılıb:",
        "",
        "1. **Köhnə sistem deltasının yük fazası / «Dərs yükü faylı»** (`Dərs yükü faylından əlavə olundu` qeydli "
        "sətirlər) fənni başqa adla yazılmış mövcud sətri tanımayıb (məs. «… (Digital Forensics fudamentals», "
        "«… (Malware analysis)») və YENİ sətir açıb → eyni qrup + fənn iki dəfə.",
        "2. Köhnə sistemdə eyni müəllimin eyni fənni həm birgə (bir neçə qrup), həm də qrup-qrup ayrı jurnallarda "
        "idi → delta hər jurnal üçün sətir açıb: birgə sətir + qrup sətirləri (örtən dublikat).",
        "3. Birgə dərs (patok) qrup başına AYRI sətirlərdə — hər sətirdə mühazirə (bəzən seminar da) tam saatla.",
        "4. Kafedralar arası: eyni fənn + qrup həm Proqramlaşdırmanın, həm İT-nin tapşırığında (İT-dəki VAKANT).",
        "",
    ]
    out += _journal_main(fixer.joint_detection or first, name)
    out += _summary(first, fixer)
    out += ["", "## 2. Müəllim yükləri — əvvəl / sonra (norma > 100 % və ya yoxlanılan müəllimlər)", ""]
    out += load_table(organization, year, before, after, focus, name)
    out += ["", "## 3. Kafedra üzrə (aşkarlanan, əvvəlki hal)", ""] + _per_chair(first)
    out += ["", "## 4. Avtomatik düzəlişlər", ""] + _actions(fixer, name)
    out += ["", "## 5. Qərar tələb edən hallar (avtomatik DƏYİŞDİRİLMƏDİ)", ""] + _decisions(fixer, last, name)
    out += ["", "## 6. Plan / kurikulum saatından artıq (yalnız hesabat)", ""] + _plan(last, name)
    return "\n".join(out) + "\n"


def _journal_main(first, name) -> list[str]:
    """ƏSAS cədvəl (sahib 2026-10-25): jurnala görə birgə keçirilir, amma yükdə ayrı-ayrı sayılıb — artıq N saat."""
    by_teacher = defaultdict(Counter)
    by_chair = defaultdict(Counter)
    total = Counter()
    for stream in first.joint:
        activity = stream["activity"]
        for info in stream["others"]:
            hours = info.hours[activity]
            by_teacher[stream["teacher_id"]][activity] += hours
            by_chair[info.chair_name][activity] += hours
            total[activity] += hours
        by_teacher[stream["teacher_id"]]["streams"] += 1
        by_chair[stream["anchor"].chair_name]["streams"] += 1
        total["streams"] += 1
        total["journal" if "journal" in stream["evidence"] else "schedule"] += 1
    for item in first.joint_unproven:
        if item.get("uncertain"):
            by_teacher[item["teacher_id"]]["uncertain"] += 1
            by_chair[item["rows"][0].chair_name]["uncertain"] += 1
            total["uncertain"] += 1
            total["uncertain_h"] += item["hours"]
    journal = defaultdict(Counter)
    for stat in first.journal_stats:
        journal[stat["teacher_id"]]["groups"] += stat["groups"]
        journal[stat["teacher_id"]]["streams"] += stat["streams"]
    excess = sum(total[a] for a in TEACHING_ACTIVITIES)
    lines = [
        "## 1. Jurnala görə birgə keçirilir, amma yükdə ayrı-ayrı sayılıb",
        "",
        f"**Ümumi artıq yük: {excess} saat** (mühazirə {total['lecture']}, seminar {total['seminar']}, "
        f"laboratoriya {total['lab']}) — {total['streams']} axın ({total['journal']} jurnalla, {total['schedule']} "
        f"yalnız cədvəllə sübutlu). Qeyri-müəyyən (bəzi tarixlərdə birgə, < 75 %): {total['uncertain']} hal, "
        f"{total['uncertain_h']} saat (Σ, avtomatik dəyişmir).",
        "",
        "Qayda: eyni müəllim + fənn + növ + tarix + başlama saatı bir neçə qrupun jurnalında → həmin növ BİRGƏ "
        "keçirilir, yükdə bir dəfə sayılmalıdır. Fərqli müəllimlərin eyni növ saatı birləşdirilmir.",
        "",
        "### Kafedra üzrə",
        "",
        "| Kafedra | Axın | Artıq M | Artıq S | Artıq L | Cəmi artıq | Qeyri-müəyyən |",
        "|---|---|---|---|---|---|---|",
    ]
    for chair, c in sorted(by_chair.items(), key=lambda kv: -sum(kv[1][a] for a in TEACHING_ACTIVITIES)):
        lines.append(
            f"| {chair} | {c['streams']} | {c['lecture']} | {c['seminar']} | {c['lab']} | "
            f"{sum(c[a] for a in TEACHING_ACTIVITIES)} | {c['uncertain']} |"
        )
    lines += [
        "",
        "### Müəllim üzrə",
        "",
        "| Müəllim | Axın | Artıq M | Artıq S | Artıq L | Cəmi artıq | Qeyri-müəyyən | Jurnal: qrup → axın |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for teacher, c in sorted(by_teacher.items(), key=lambda kv: -sum(kv[1][a] for a in TEACHING_ACTIVITIES)):
        j = journal.get(teacher, Counter())
        lines.append(
            f"| {name(teacher)} | {c['streams']} | {c['lecture']} | {c['seminar']} | {c['lab']} | "
            f"{sum(c[a] for a in TEACHING_ACTIVITIES)} | {c['uncertain']} | {j['groups']} → {j['streams']} |"
        )
    lines += [
        "",
        "«Jurnal: qrup → axın» — müəllimin bu semestr jurnalında (fənn × növ üzrə, ≥ 2 qrup) qrup sayı və onların "
        "neçə ayrı dərsə (axına) düşdüyü.",
        "",
    ]
    return lines


def _summary(first, fixer) -> list[str]:
    dup = first.duplicates
    exact = [c for c in dup if c["exact"]]
    partial = [c for c in dup if not c["exact"]]
    sources = Counter()
    for cluster in dup:
        for source in cluster["sources"]:
            if source != "task":
                sources[source] += 1
    joint = defaultdict(lambda: [0, 0])
    for stream in first.joint:
        joint[stream["activity"]][0] += 1
        joint[stream["activity"]][1] += stream["excess"]
    unproven = defaultdict(lambda: [0, 0])
    for item in first.joint_unproven:
        unproven[item["activity"]][0] += 1
        unproven[item["activity"]][1] += item["hours"]
    counts = fixer.counts
    lines = [
        "## 1a. Bütün kateqoriyalar (aşkarlanan — düzəlişdən əvvəl)",
        "",
        "| Kateqoriya | Say | Artıq saat (yuxarı hədd) |",
        "|---|---|---|",
        f"| (a) dublikat — eyni qrup dəsti | {len(exact)} | {sum(c['excess'] for c in exact)} |",
        f"| (a) dublikat — örtən / kəsişən qrup dəsti | {len(partial)} | {sum(c['excess'] for c in partial)} |",
        f"|  ↳ kafedralar arası | {sum(1 for c in dup if c['cross_chair'])} | "
        f"{sum(c['excess'] for c in dup if c['cross_chair'])} |",
        f"| (d) dublikatda «Dərs yükü faylı»/delta sətri | {sources['load_file']} | — |",
        f"| (d) dublikatda intensiv kurs sətri | {sources['intensive']} | — |",
        f"| (d) dublikatda cədvəldən yaranmış sətir | {sources['timetable']} | — |",
        f"| (b) mühazirə axını (sübutlu) | {joint['lecture'][0]} | {joint['lecture'][1]} |",
        f"| (b) seminar da axın — ikiqat sayılıb (sübutlu) | {joint['seminar'][0]} | {joint['seminar'][1]} |",
        f"| (b) laboratoriya da axın — ikiqat sayılıb (sübutlu) | {joint['lab'][0]} | {joint['lab'][1]} |",
        f"| (b) eyni müəllim + fənn, ayrı qrup sətirləri, SÜBUTSUZ (mühazirə) | {unproven['lecture'][0]} | "
        f"{unproven['lecture'][1]} (Σ, artıq deyil) |",
        f"| (b) eyni müəllim + fənn, ayrı qrup sətirləri, SÜBUTSUZ (seminar/lab) | "
        f"{unproven['seminar'][0] + unproven['lab'][0]} | {unproven['seminar'][1] + unproven['lab'][1]} (Σ) |",
        f"| (c) plan / kurikulum saatından artıq sətir-fəaliyyət | {len(first.plan_overrun)} | — |",
        "",
        "Düzəliş sayları: " + ", ".join(f"`{k}={v}`" for k, v in sorted(counts.items())),
        "",
        "Saat qeydi: «artıq saat» = klasterdə fəaliyyət üzrə Σ − ən böyük sətir (dublikat) / lövbərdən başqa "
        "sətirlərin həmin növ saatı (axın). Sübut: dərs cədvəlində eyni gün+saat+həftə+növ slotu və ya jurnalda "
        "eyni tarix+saat+növ (≥ 2 tarix, kiçik tərəfin tarixlərinin ≥ 75 %-i).",
    ]
    return lines


def _per_chair(first) -> list[str]:
    table = defaultdict(Counter)
    for cluster in first.duplicates:
        for chair in {info.chair_name for info in cluster["rows"]}:
            table[chair]["dup"] += 1
            table[chair]["dup_h"] += cluster["excess"]
    for stream in first.joint:
        chair = stream["anchor"].chair_name
        table[chair][f"j_{stream['activity']}"] += 1
        table[chair]["j_h"] += stream["excess"]
    for item in first.joint_unproven:
        table[item["rows"][0].chair_name]["unproven"] += 1
    for item in first.plan_overrun:
        table[item["info"].chair_name]["plan"] += 1
    lines = [
        "| Kafedra | Dublikat klaster | Saat | Axın M | Axın S | Axın L | Axın saatı | Sübutsuz | Plan aşımı |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for chair, c in sorted(table.items(), key=lambda kv: -(kv[1]["dup_h"] + kv[1]["j_h"])):
        lines.append(
            f"| {chair} | {c['dup']} | {c['dup_h']} | {c['j_lecture']} | {c['j_seminar']} | {c['j_lab']} | "
            f"{c['j_h']} | {c['unproven']} | {c['plan']} |"
        )
    return lines


def _actions(fixer, name) -> list[str]:
    if not fixer.actions:
        return ["Yoxdur."]
    lines = []
    for action in fixer.actions:
        info, kept = action["info"], action["kept"]
        if action["kind"] == "delete":
            lines.append(
                f"- **sətir silindi** ({action['rule']}, −{action['hours']} s bölgülü): {_row_line(info, name)}  \n"
                f"  ↳ qalan: {_row_line(kept, name)}"
            )
        else:
            lines.append(
                f"- **{ACT[action['activity']]} axında** (sübut: {action['evidence']}, −{action['hours']} s): "
                f"{_row_line(info, name)}  \n  ↳ lövbər: {_row_line(kept, name)}"
            )
    return lines


def _decisions(fixer, last, name) -> list[str]:
    lines = []
    for item in fixer.decisions:
        if item["kind"] == "duplicate":
            cluster = item["cluster"]
            lines.append(
                f"- **dublikat** — {DECISION_TEXT.get(item['code'], item['code'])} (artıq ≤ {cluster['excess']} s):"
            )
            lines += [f"  - {_row_line(info, name)}" for info in cluster["rows"]]
        elif item["kind"] == "joint":
            stream = item["stream"]
            lines.append(
                f"- **{ACT[stream['activity']]} axını sübutludur, amma qrup saatları fərqlidir** "
                f"(sübut: {', '.join(stream['evidence'])}; müəllim {name(stream['teacher_id'])}):"
            )
            lines += [f"  - {_row_line(info, name)}" for info in stream["rows"]]
        else:
            lines.append(f"- **yazı bloklandı** ({item['code']}): {_row_line(item['info'], name)}")
    lines += ["", "### Qeyri-müəyyən və sübutsuz axın namizədləri (eyni müəllim + fənn, ayrı qrup sətirləri)", ""]
    for item in sorted(last.joint_unproven, key=lambda i: not i.get("uncertain")):
        tag = "QEYRİ-MÜƏYYƏN (jurnalda qismən birgə)" if item.get("uncertain") else "sübut yoxdur — qrup üzrə qalır"
        lines.append(f"- {tag} · {ACT[item['activity']]} · {name(item['teacher_id'])} · Σ {item['hours']} s:")
        lines += [f"  - {_row_line(info, name)}" for info in item["rows"]]
    return lines or ["Yoxdur."]


def _plan(last, name) -> list[str]:
    if not last.plan_overrun:
        return ["Yoxdur."]
    basis = {"row_plan": "sətrin planı × çarpan", "curriculum": "kurikulumda fənnin ən böyük saatı"}
    return [
        f"- {ACT[item['activity']]} {item['total']} > {item['limit']} ({basis[item['basis']]}): "
        f"{_row_line(item['info'], name)}"
        for item in last.plan_overrun
    ]


__all__ = ["build_report", "load_table"]

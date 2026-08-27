"""§3 nümunə-yoxlama, §4 bal bütövlüyü və §5 keyfiyyət bölmələrinin render-i."""

from __future__ import annotations

from .analysis import (
    DELTA_BUCKETS,
    DOMAIN_LABELS,
    DOMAINS,
    diff_flag,
    fmt_int,
    fmt_num,
    fmt_pct,
    md_table,
)

SAMPLE_HEADERS = [
    "Fənn",
    "Tərəf",
    "Qayıb",
    "Seminar bal",
    "Kollokvium",
    "Sərbəst iş",
    "İmtahan",
    "Giriş balı",
    "Yekun",
    "⚑",
]


def render_sample(context: dict) -> str:
    """20 tələbənin köhnə/yeni yan-yana müqayisəsi."""

    students = context["sample"]
    lines = [
        "## 3. Nümunə-yoxlama — 20 təsadüfi tələbə",
        "",
        f"Seçim toxumu: `random.Random({context['sample_seed']})` — **təkrarlana biləndir**:",
        "eyni əmr hər dəfə eyni 20 nəfəri göstərir.",
        "",
        "Nümunə **bərabər bölünüb**: yarısı yazılışı köçən, yarısı köçməyən tələbədən.",
        "Sırf təsadüfi seçim bu datada demək olar ki, həmişə arxiv tələbələrini gətirir",
        "və «heç nə köçməyib» mənzərəsi yaradır; bərabər bölgü hər iki tərəfi göstərir —",
        "köçən datanın xana-bəxana düzgünlüyünü VƏ köçməyənin miqyasını.",
        "",
        "Hər fənn üçün iki sətir var: `köhnə` (MyEdu xanalarından yenidən hesablanmış)",
        "və `yeni` (EMS Arena cədvəllərindən).  Sağ sütun: ✅ = tutur, 🔴 = fərq var,",
        "`↔ birləşmə` = bu legacy jurnal başqa bir jurnalla EYNİ açılışa birləşib",
        "(«yeni» sütunu birləşmiş nəticəni göstərir, ona görə ayrıca müqayisə olunmur).",
        "«Giriş balı» və «Yekun» sütunlarında `—` o deməkdir ki, legacy `yekun`",
        "cədvəlində bu fənn üçün sətir yoxdur — bu, uyğunsuzluq DEYİL.",
    ]
    if not students:
        return "\n".join(lines + ["", "> Nümunə hovuzu boşdur."])

    lines += ["", "### Nümunənin bir baxışda mənzərəsi", "", _sample_overview(students)]
    for student in students:
        lines += ["", _student_heading(student), ""]
        rows = []
        for subject in student["subjects"]:
            rows.extend(_subject_rows(subject))
        lines.append(md_table(SAMPLE_HEADERS, rows) if rows else "> Bu tələbə üçün jurnal xanası tapılmadı.")
    lines += [
        "",
        "> **Qeyd:** «Giriş balı» sütunundakı fərqi XƏTA saymayın — düstur hazırda",
        "> yenilənir (bax §4.2).",
    ]
    return "\n".join(lines)


def _sample_overview(students: list) -> str:
    """20 nəfərin hansı vəziyyətdə olduğu — detala girmədən əvvəl bir mənzərə."""

    rows = []
    for student in students:
        matched, total = student["matched"], student["total_subjects"]
        if total == 0:
            verdict = "— jurnal xanası yoxdur"
        elif matched == total:
            verdict = "✅ bütün fənlər köçüb"
        elif matched == 0:
            verdict = "🔴 heç bir fənn köçməyib"
        else:
            verdict = f"⚠️ {matched}/{total} fənn köçüb"
        rows.append(
            [
                student["source_name"],
                f"`#{student['legacy_id']}`",
                student["source_group"] or "—",
                "aktiv" if student["membership_active"] else "arxiv",
                f"{matched}/{total}",
                verdict,
            ]
        )
    return md_table(["Tələbə", "Legacy ID", "Qrup", "Üzvlük", "Fənn (köçən/cəmi)", "Nəticə"], rows)


def _student_heading(student: dict) -> str:
    membership = "aktiv üzvlük" if student["membership_active"] else "**arxiv üzvlüyü** (qeyri-aktiv)"
    name_flag = " 🔴" if student["source_name"] != student["target_name"] else ""
    return (
        f"### {student['source_name']} — legacy `#{student['legacy_id']}` → `auth.user #{student['user_id']}`{name_flag}\n\n"
        f"| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |\n|---|---|---|\n"
        f"| Ad, soyad | {student['source_name'] or '—'} | {student['target_name'] or '—'} |\n"
        f"| Qrup | {student['source_group'] or '—'} | {student['target_group'] or '—'} |\n"
        f"| İxtisas / proqram | {student['source_speciality'] or '—'} | {student['target_program'] or '—'} |\n"
        f"| Statusu | — | {student['target_status'] or '—'} ({membership}) |"
    )


def _subject_rows(subject: dict) -> list:
    source = subject["source"]
    yekun = subject["source_yekun"]
    target = subject["target"]
    computed = subject["computed"]
    if target is None:
        return [
            [
                subject["fenn"],
                "köhnə",
                fmt_int(source.get("qayib", 0)),
                fmt_num(source.get("seminar_sum")),
                fmt_num(source.get("kollokvium")),
                fmt_num(source.get("serbest")),
                fmt_num(source.get("imtahan") if source.get("imtahan") is not None else yekun.get("imtahan")),
                fmt_num(yekun.get("girish")),
                fmt_num(yekun.get("yekun")),
                "🔴",
            ],
            ["", "yeni", "—", "—", "—", "—", "—", "—", "—", subject["reason"] or "hədəfdə yoxdur"],
        ]

    source_exam = source.get("imtahan") if source.get("imtahan") is not None else yekun.get("imtahan")
    target_exam = target["tekrar"] if target["tekrar"] is not None else target["imtahan"]
    # Mənbədə dəyər YOXDURSA müqayisə edilmir — «yoxluq» uyğunsuzluq deyil.
    # (`yekun` cədvəli yalnız bəzi buraxılışları əhatə edir; onun boşluğu
    #  hədəfdə səhv olduğunu göstərmir.)
    comparisons = [
        diff_flag(source.get("qayib", 0), target["qayib"]),
        _compare_if_present(source.get("seminar_sum"), target["seminar"]),
        _compare_if_present(source.get("kollokvium"), target["kollokvium"]),
        _compare_if_present(source_exam, target_exam),
        _compare_if_present(yekun.get("yekun"), computed.get("yekun")),
    ]
    flags = "".join(flag for flag in comparisons if flag)
    verdict = "↔ birləşmə" if subject["merged"] else (flags[:1] or "✅")
    return [
        [
            subject["fenn"],
            "köhnə",
            fmt_int(source.get("qayib", 0)),
            fmt_num(source.get("seminar_sum")),
            fmt_num(source.get("kollokvium")),
            fmt_num(source.get("serbest")),
            fmt_num(source_exam),
            fmt_num(yekun.get("girish")),
            fmt_num(yekun.get("yekun")),
            verdict,
        ],
        [
            "",
            "yeni",
            fmt_int(target["qayib"]),
            fmt_num(target["seminar"]),
            fmt_num(target["kollokvium"]),
            fmt_num(target["serbest"]),
            fmt_num(target_exam),
            fmt_num(computed.get("girish")),
            fmt_num(computed.get("yekun")),
            subject["reason"],
        ],
    ]


def _compare_if_present(source_value, target_value) -> str:
    """Mənbə dəyəri yoxdursa boş qaytar — «sübut yoxdur» ≠ «uyğunsuzluq»."""

    return "" if source_value is None else diff_flag(source_value, target_value)


def render_finals(context: dict) -> str:
    """§4 — `yekun` cədvəli ilə hədəfin hesabladığı yekunun üzləşdirilməsi."""

    finals = context["finals"]
    ledger = _ledger_finals(context)
    lines = [
        "## 4. Bal bütövlüyü",
        "",
        "### 4.1 `yekun` cədvəli ↔ hədəfin hesabladığı yekun",
        "",
        md_table(
            ["Göstərici", "Say"],
            [
                ["Mənbədəki `yekun` sətri", fmt_int(finals["source_rows"])],
                ["Hədəfdəki yazılışa bağlanan sətir", fmt_int(finals["linked_rows"])],
                ["…bunlardan birləşən jurnal səbəbindən eyni yazılışa düşən", fmt_int(finals["collapsed"])],
                ["…yəni fərqli yazılış sayı", fmt_int(finals["linked"])],
                ["Bağlana bilməyən (yazılış köçürülməyib)", fmt_int(finals["unresolved"])],
                ["Bağlandı, amma registrar-da tapılmadı", fmt_int(finals["missing_target"])],
                ["Müqayisə edilən yekun bal", fmt_int(finals["total_compared"])],
                ["*J8 fazasının öz rəqəmi:* bağlana bilməyən", fmt_int(ledger["unresolved"])],
                ["*J8 fazasının öz rəqəmi:* kənarlaşan yekun", fmt_int(ledger["deviation"])],
            ],
        ),
        "",
        "> Son iki sətir ledger-dən gəlir (`legacy_journal_reconcile_*`) və bu hesabatın",
        "> MÜSTƏQİL hesabladığı rəqəmlərlə üzləşdirilir — iki sübut mənbəyi bir-birini",
        "> yoxlayır.",
        "",
        "**Yekun balı fərqinin paylanması** (hədəfin hesabladığı − legacy `yekun`):",
        "",
        _histogram(finals["total_hist"], finals["total_compared"]),
        "",
        "> ⚠️ Bu paylanmadakı böyük fərqlərin əsas mənbəyi **giriş balı düsturudur**",
        "> (§4.2) — yekun = giriş + imtahan olduğu üçün giriş kənarlaşması birbaşa",
        "> yekuna keçir.  Düsturdan asılı olmayan hissəni aşağıdakı iki cədvəldə görün.",
        "",
        "**İmtahan balı fərqinin paylanması** (`im`/`im2` ↔ `FinalGrade`/`ResitRecord`):",
        "",
        _histogram(finals["exam_hist"], finals["exam_compared"]),
        "",
        "**`yekun − giriş` fərqinin paylanması** — giriş düsturundan ASILI OLMAYAN hissə:",
        "",
        _histogram(finals["net_hist"], finals["net_compared"]),
        "",
        "### 4.2 ⏳ Giriş balı — DÜSTUR GÖZLƏYİR",
        "",
        "> Giriş balının hesablanma düsturu **hazırda yenilənir**.  Aşağıdakı paylanma",
        "> `entry = min(seminar + kollokvium, entry_score_max)` cari güzgüsü ilə",
        "> hesablanıb və **XƏTA SAYILMIR** — düstur dəqiqləşəndə bu bölmə yenidən",
        "> işlədilməlidir.",
        "",
        _histogram(finals["entry_hist"], finals["entry_compared"]),
        "",
        "### 4.3 Xana dəyərlərinin paylanması",
        "",
        "`ie` = «iştirak edib» — bu **davamiyyətdir, bal deyil**; hədəfdə",
        "`LessonMark.status = present` (bal sütunu boş) kimi oturur.",
        "",
        _value_distribution(context),
    ]
    return "\n".join(lines)


def _ledger_finals(context: dict) -> dict:
    """J8 fazasının ledger-ə möhürlədiyi öz rəqəmləri (çarpaz yoxlama üçün)."""

    counts = {"unresolved": 0, "deviation": 0}
    for _table, rule, _severity, count in context["target"]["issues"]:
        if rule == "legacy_journal_reconcile_final_unresolved":
            counts["unresolved"] = count
        elif rule == "legacy_journal_reconcile_final_deviation":
            counts["deviation"] = count
    return counts


def _histogram(histogram: dict, total: int) -> str:
    rows = [
        [bucket, fmt_int(histogram.get(bucket, 0)), fmt_pct(histogram.get(bucket, 0), total)]
        for bucket in DELTA_BUCKETS
    ]
    return md_table(["Fərq", "Say", "Pay"], rows)


def _value_distribution(context: dict) -> str:
    values = context["source"]["values"]
    shapes = sorted({key[2] for key in values})
    rows = []
    for domain in DOMAINS:
        for shape in shapes:
            count = sum(count for key, count in values.items() if key[1] == domain and key[2] == shape)
            if count:
                rows.append([DOMAIN_LABELS[domain], shape, fmt_int(count)])
    target = context["target"]["entity_counts"]
    rows += [
        ["→ hədəf: `LessonMark.status = present`", "davamiyyət", fmt_int(target.get("lessonmark_present", 0))],
        ["→ hədəf: `LessonMark.status = absent`", "davamiyyət", fmt_int(target.get("lessonmark_absent", 0))],
        ["→ hədəf: `LessonMark.status = excused`", "üzrlü davamiyyət", fmt_int(target.get("lessonmark_excused", 0))],
        ["→ hədəf: `LessonMark.score` dolu", "bal", fmt_int(target.get("lessonmark_scored", 0))],
        ["→ hədəf: `ComponentScore` (kollokvium)", "bal", fmt_int(target.get("componentscore_kollokvium", 0))],
        ["→ hədəf: `ComponentScore` (sərbəst iş)", "bal", fmt_int(target.get("componentscore_selfwork", 0))],
    ]
    return md_table(["Domen / hədəf sətri", "Dəyər forması", "Say"], rows)


def render_quality(context: dict, source_labels: dict, target_labels: dict) -> str:
    """§5 — boş sahələr, dublikatlar, orfan istinadlar (hər iki tərəfdə)."""

    source = context["source"]["quality"]
    target = context["target"]["quality"]
    source_rows = [[source_labels.get(key, key), fmt_int(value), _verdict(value)] for key, value in source.items()]
    target_rows = [[target_labels.get(key, key), fmt_int(value), _verdict(value)] for key, value in target.items()]
    return "\n".join(
        [
            "## 5. Keyfiyyət yoxlamaları",
            "",
            "### 5.1 Mənbədə (MyEdu) — köçürmədən ƏVVƏLKİ vəziyyət",
            "",
            "Buradakı rəqəmlər köçürmənin qüsuru deyil, **mənbənin öz vəziyyətidir**.",
            "",
            md_table(["Yoxlama", "Say", "Qiymət"], source_rows),
            "",
            "### 5.2 Hədəfdə (EMS Arena) — köçürmədən SONRAKI vəziyyət",
            "",
            md_table(["Yoxlama", "Say", "Qiymət"], target_rows),
        ]
    )


def _verdict(value: int) -> str:
    return "✅ təmiz" if value == 0 else "⚠️ baxılmalıdır"

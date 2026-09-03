"""§1.3-ün izah qatı: yazı nərdivanının SƏBƏB pillələri və onların kəsişməsi.

Niyə ayrı modul
---------------
2026-08-31-ə qədər nərdivanın son iki pilləsi («dərs slotu tapılmadı»,
«hədəf açarı toqquşması») İKİ ümumi sətir idi.  Hər ikisi ÖLÇÜLDÜKDƏN sonra
məlum oldu ki, onların içində məzmunca TAMAM FƏRQLİ hallar var:

* dərs slotu **mənbədə də yoxdur** — bu, köçürmə qüsuru deyil, mənbənin öz
  boşluğudur; J12 (``journal_lesson_recovery``) məhz bunu bərpa edir, ona görə
  bərpadan sonra pillə SIFIRA enməlidir;
* dərs slotu **mənbədə var**, hədəfə düşməyib — ölçüldü: bunların hamısı
  mənbənin öz təqvim/saat səhvidir (31 aprel, 30 fevral, ``80:30``), yəni J3
  onlardan HƏQİQİ tarix qura bilmir; adlandırıla bilməyən hissə açıq qalır;
* toqquşmada **eyni dəyər** — fakt qorunub, itki YOXDUR;
* toqquşmada **fərqli dəyər** — uduzan dəyər sətir yaratmır (sübut qatına
  yazılır), yəni jurnal interfeysində görünmür.

Pillələr üst-üstə düşməməlidir.  Bu modul onu İDDİA ETMİR — ÖLÇÜR:
``identity_residuals`` xana səviyyəsində (bütöv = hissələrin cəmi), ``rung_overlaps``
isə jurnal/yazılış səviyyəsində kəsişməni verir və hər ikisi hesabata çap olunur.
"""

from __future__ import annotations

from .analysis import DOMAIN_LABELS, DOMAINS, fmt_int, fmt_pct, fmt_signed, md_table
from .write_replay import (
    RUNG_LABELS,
    STEP_COLLISION,
    STEP_COLLISION_OTHER,
    STEP_COLLISION_REPEAT,
    STEP_COLLISION_SAME,
    STEP_LESSON_SOURCE_ABSENT,
    STEP_LESSON_SOURCE_PRESENT,
    STEP_SYNTH_TIME_UNKNOWN,
    SUBSTEP_DAY_ABSENT,
    SUBSTEP_DAY_PRESENT_TIME_DIFFERS,
    SUBSTEP_IMPOSSIBLE_DATE,
    SUBSTEP_LEAP_DEPENDENT_DATE,
    SUBSTEP_SLOT_NOT_MATERIALISED,
    SUBSTEP_UNREADABLE_TIME,
    identity_residuals,
    rung_overlaps,
)

SUBSTEP_LABELS = {
    SUBSTEP_DAY_ABSENT: "həmin GÜN üçün mənbədə heç bir dərs sətri yoxdur",
    SUBSTEP_DAY_PRESENT_TIME_DIFFERS: "gün mənbədə var, SAAT uyğun gəlmir (oxunmayan saat daxil)",
    SUBSTEP_IMPOSSIBLE_DATE: "tarix heç bir ildə mövcud deyil (31 aprel · 31 sentyabr · 31 noyabr · 30 fevral)",
    SUBSTEP_LEAP_DEPENDENT_DATE: "29 fevral — mənbədə İL sütunu yoxdur, uzun il olub-olmadığı bilinmir",
    SUBSTEP_UNREADABLE_TIME: "saat divar saatı deyil (`80:30`, `45:00`, `10:0_`…)",
    SUBSTEP_SLOT_NOT_MATERIALISED: "🟠 tarix də, saat da qanunidir — səbəb hələ ADLANDIRILMAYIB",
}


def render_write_steps(context: dict) -> str:
    """Səbəb pillələri + itkinin tərkibi + kəsişmə ölçüsü."""

    replay = context["replay"]
    parts = [
        _intro(),
        _lesson_rungs(context),
        recovery_block(
            context.get("target", {}).get("recovery") or {},
            replay.total(STEP_LESSON_SOURCE_ABSENT),
            replay.total(STEP_SYNTH_TIME_UNKNOWN),
        ),
        _collision_rungs(context),
        _overlap(context),
    ]
    return "\n\n".join(parts)


def recovery_block(recovery: dict, absent: int, synth_time_unknown: int = 0) -> str:
    """1-ci pillənin proqnozu: bərpa tətbiq olunubsa pillə SIFIR olmalıdır.

    Saf funksiyadır (bazaya toxunmur) — proqnoz testdə də yoxlana bilir.
    Dörd hal ayrılır və heç biri o birinin yerinə keçmir; «bərpa var, pillə
    hələ dolu» halı 🔴 ilə AÇIQ qalır, susdurulmur.
    """

    head = "**1-ci pillənin proqnozu — bu hədəf nüsxəsində bərpa varmı?**"
    if not recovery.get("present"):
        return "\n".join(
            [
                head,
                "",
                "Nüsxənin sxemi bərpanı TANIMIR (`registrar_lesson.is_legacy_synthesised`",
                "sütunu yoxdur — `registrar.0059` miqrasiyası tətbiq olunmayıb), yəni bu",
                f"ölçmə bərpadan ƏVVƏLKİ vəziyyətdir: pillə 1 = **{fmt_int(absent)}** xana",
                "hələ də bərpanın hədəfidir.",
            ]
        )
    lessons = int(recovery.get("lessons", 0))
    if not lessons:
        return "\n".join(
            [
                head,
                "",
                "Sxem bərpanı tanıyır, amma bu nüsxədə sintetik dərs YOXDUR — J12",
                f"işlədilməyib.  Pillə 1 = **{fmt_int(absent)}** xana açıq qalır.",
            ]
        )
    marks = int(recovery.get("marks", 0))
    verdict = (
        "✅ **Proqnoz TUTDU**: pillə 1 = **0** — mənbədə dərsi olmayan xanaların hamısı bərpa dərslərinə oturub."
        if absent == 0
        else f"🔴 **Proqnoz TUTMADI**: bərpaya baxmayaraq pillə 1 hələ **{fmt_int(absent)}**"
        " xana göstərir — bərpa TAM DEYİL, sual AÇIQ qalır."
    )
    lines = [
        head,
        "",
        f"Bu nüsxədə J12 bərpası tətbiq olunub: **{fmt_int(lessons)}** sintetik `Lesson`",
        f"(`is_legacy_synthesised`) və onlara bağlı **{fmt_int(marks)}** `LessonMark`.",
        "",
        verdict,
    ]
    if synth_time_unknown:
        lines += [
            "",
            f"Bunlardan **{fmt_int(synth_time_unknown)}** xananın legacy saatı pozuqdur",
            "(`80:30`, `45:00` kimi 26 yazı səhvi) — J12 onlar üçün dərsi",
            "`start_time = NULL` ilə yaradır, nərdivan da xananı həmin dərsə bağlayır",
            "(`legacy_lesson_synth_time_unknown` güzgüsü).  Bu qayda olmadan həmin",
            "xanalar hədəfdə MÖVCUD olduğu halda «yazılmayıb» sayılırdı.",
        ]
    return "\n".join(lines)


def _intro() -> str:
    return "\n".join(
        [
            "#### Yazı nərdivanının səbəb pillələri — nə ölçülüb",
            "",
            "Bu pillələr ledger sayğacından DEYİL, mənbə xanalarının öz axınından",
            "hesablanır: import-un `_decide()` qərarı oflayn təkrar icra olunur.",
            "Ledger HADİSƏ sayır, nərdivan XANA sayır — fərq vacibdir, çünki",
            '`classify_mark_write()` mövcud xanaya eyni dəyər gələndə `"written"`',
            "qaytarır (ledger «yazıldı» görür), hədəfdə isə sətir YARANMIR.",
            "",
            "Hədəfdən yalnız iki materiallaşmış xəritə oxunur (dərs slotları,",
            "yazılış→açılış); üçüncü sübut — MƏNBƏNİN öz dərs indeksi",
            "(`journals_dates_added_by_teacher`) — birbaşa mənbədən gəlir və",
            "pilləni hədəfdən asılı olmadan ikiyə bölür.",
        ]
    )


def _lesson_rungs(context: dict) -> str:
    replay = context["replay"]
    absent = replay.total(STEP_LESSON_SOURCE_ABSENT)
    present = replay.total(STEP_LESSON_SOURCE_PRESENT)
    total = absent + present
    lines = [
        "**Pillə 1–2. Dərs slotu tapılmadı → İKİ AYRI SƏBƏB.**  `LessonMark` yalnız",
        "mövcud `Lesson`-a bağlana bilər.  Xananın `(açılış, ay, gün, saat)` slotu",
        "hədəfdə materiallaşmayıbsa xana yazılmır.  Sual: həmin dərs MƏNBƏDƏ varmı?",
        "",
        md_table(
            ["Pillə", "Xana", "Pay", "Bu nə deməkdir"],
            [
                [
                    f"**1.** {RUNG_LABELS[STEP_LESSON_SOURCE_ABSENT]}",
                    f"**{fmt_int(absent)}**",
                    fmt_pct(absent, total),
                    "Mənbənin öz boşluğu — köçürmə qüsuru DEYİL.  J12 bərpası xananın "
                    "öz `(ay, gün, saat)` açarından dərsi yaradır → bərpadan sonra bu pillə **0** olur.",
                ],
                [
                    f"**2.** {RUNG_LABELS[STEP_LESSON_SOURCE_PRESENT]}",
                    f"**{fmt_int(present)}**",
                    fmt_pct(present, total),
                    "Dərs sətri mənbədə VAR, hədəfə düşməyib.  Səbəb aşağıda ayrıca ölçülür — "
                    "sətrin öz tarixi/saatı həqiqi təqvim anı deyilsə J3 dərs yarada bilmir.",
                ],
                ["**CƏMİ**", f"**{fmt_int(total)}**", "", ""],
            ],
        ),
        "",
        "İtən xananın NƏ DAŞIDIĞI (pillə üzrə) — «bal itdi» ilə «davamiyyət itdi»",
        "eyni şey deyil:",
        "",
    ]
    shape_rows = []
    for rung in (STEP_LESSON_SOURCE_ABSENT, STEP_LESSON_SOURCE_PRESENT):
        shapes = replay.rung_shapes.get(rung, {})
        for shape, count in sorted(shapes.items(), key=lambda item: -item[1]):
            shape_rows.append([RUNG_LABELS[rung], shape, fmt_int(count)])
    lines += [
        md_table(["Pillə", "Xananın məzmunu", "Xana"], shape_rows or [["—", "—", "—"]]),
        "",
        f"Təsirlənən jurnal (hər iki pillə birlikdə): **{fmt_int(len(replay.lesson_missing_journals))}**.",
        "🔴 Rəqəmli bal daşıyan xanalar birmənalı **akademik data itkisidir**;",
        "`qb` xanaları `Enrollment.absence_hours`-u aşağı göstərir.",
    ]

    substeps = replay.source_slot_substeps
    if substeps:
        lines += [
            "",
            "**1-ci pillənin daxili bölgüsü** — «mənbədə yoxdur» nə qədər dərindir?",
            "(gün səviyyəsində indeks ilə ölçülüb; bu, ayrıca nərdivan pilləsi DEYİL):",
            "",
            md_table(
                ["Alt-hal", "Xana", "Pay"],
                [
                    [SUBSTEP_LABELS.get(key, key), fmt_int(count), fmt_pct(count, absent)]
                    for key, count in sorted(substeps.items(), key=lambda item: -item[1])
                ],
            ),
        ]

    present_substeps = replay.source_present_substeps
    if present_substeps:
        open_cells = present_substeps.get(SUBSTEP_SLOT_NOT_MATERIALISED, 0)
        lines += [
            "",
            "**2-ci pillənin daxili bölgüsü** — dərs sətri mənbədə VAR, bəs niyə",
            "hədəfdə dərs yoxdur?  J3 dərsi yalnız HƏQİQİ təqvim anından yarada bilir",
            "(`parse_lesson_schedule`), ona görə bu pillə də adlandırılmış hallara bölünür:",
            "",
            md_table(
                ["Alt-hal", "Xana", "Pay"],
                [
                    [SUBSTEP_LABELS.get(key, key), fmt_int(count), fmt_pct(count, present)]
                    for key, count in sorted(present_substeps.items(), key=lambda item: -item[1])
                ],
            ),
            "",
            (
                "✅ Bu pillədə **adsız qalıq YOXDUR**: hər xana mənbənin öz təqvim/saat"
                " səhvi ilə izah olunur — köçürmə qərarı deyil."
                if open_cells == 0
                else f"🟠 **{fmt_int(open_cells)}** xana hələ adlandırılmayıb — AÇIQ qalır," " fərziyyə ilə bağlanmır."
            ),
        ]
    return "\n".join(lines)


def _collision_rungs(context: dict) -> str:
    replay = context["replay"]
    lines = [
        "**Pillə 3–4. Hədəf açarı toqquşması → İKİ AYRI SƏBƏB.**  J-V4 dedup açarı",
        "`journal_uniqid`-i daxil edir, hədəf açarı isə etmir.  Bir neçə legacy",
        "jurnal BİR açılışa birləşdiyi üçün (`legacy_journal_offering_merged`) iki",
        "mənbə xanası eyni hədəf açarına düşür — ikincisi sətir yaratmır.  Uduzan",
        "xananın dəyəri qalibin dəyəri ilə müqayisə olunur:",
        "",
    ]
    rows = []
    for domain in DOMAINS:
        total = replay.step(domain, STEP_COLLISION)
        if not total:
            continue
        rows.append(
            [
                DOMAIN_LABELS[domain],
                fmt_int(total),
                fmt_int(replay.step(domain, STEP_COLLISION_SAME)),
                f"**{fmt_int(replay.step(domain, STEP_COLLISION_OTHER))}**",
            ]
        )
    rows.append(
        [
            "**CƏMİ**",
            f"**{fmt_int(replay.total(STEP_COLLISION))}**",
            f"**{fmt_int(replay.total(STEP_COLLISION_SAME))}**",
            f"**{fmt_int(replay.total(STEP_COLLISION_OTHER))}**",
        ]
    )
    lines += [
        md_table(
            [
                "Domen",
                "Toqquşma",
                f"**3.** {RUNG_LABELS[STEP_COLLISION_SAME]}",
                f"🔴 **4.** {RUNG_LABELS[STEP_COLLISION_OTHER]}",
            ],
            rows,
        ),
        "",
        "**3-cü pillə (eyni dəyər)** — eyni fakt iki birləşən jurnalda qeyd olunub,",
        "hədəfdə bir dəfə durur: dəyər QORUNUB, itki yoxdur.  Bu pillə nərdivanda",
        "«izahlı buraxılış» kimi durur.",
        "",
        "**4-cü pillə (fərqli dəyər)** — iki jurnal eyni tələbə üçün FƏRQLİ dəyər",
        "saxlayır, hədəfə yalnız biri düşür.  Uduzan dəyər jurnal interfeysində",
        "GÖRÜNMÜR; sübut qatında (`registrar_legacygradefact`) saxlanılır.",
        "",
        f"Təsirlənən jurnal: **{fmt_int(len(replay.collision_journals))}**.",
        "",
        "**Bölgünün qeyri-müəyyənliyi — ölçülüb.**  Toqquşmanın ÜMUMİ sayı axın",
        "sırasından asılı deyil, «eyni / fərqli» bölgüsü isə yalnız bir halda",
        "asılıdır: eyni hədəf açarını ÜÇ və daha çox mənbə xanası iddia edəndə.",
        f"Belə xana: **{fmt_int(replay.total(STEP_COLLISION_REPEAT))}** "
        f"({fmt_pct(replay.total(STEP_COLLISION_REPEAT), replay.total(STEP_COLLISION))}).",
        "Bu rəqəm 3-cü və 4-cü pillə arasında sürüşə biləcək MAKSİMUM xana sayıdır —",
        "yəni bölgünün xəta payının yuxarı sərhədi.  Cəm heç bir halda dəyişmir.",
    ]
    return "\n".join(lines)


def _overlap(context: dict) -> str:
    """Pillələr üst-üstə düşürmü — İDDİA yox, ÖLÇÜ."""

    replay = context["replay"]
    identity_rows = []
    identity_bad = 0
    for domain, whole, whole_count, part_sum, residual in identity_residuals(replay):
        identity_bad += abs(residual)
        identity_rows.append(
            [
                DOMAIN_LABELS[domain],
                f"`{whole}`",
                fmt_int(whole_count),
                fmt_int(part_sum),
                ("✅ 0" if residual == 0 else f"🔴 {fmt_signed(residual)}"),
            ]
        )
    overlap_rows = [
        [
            RUNG_LABELS.get(first, first),
            RUNG_LABELS.get(second, second),
            fmt_int(journals),
            fmt_int(enrollments),
        ]
        for first, second, journals, enrollments in rung_overlaps(replay)
    ]
    verdict = (
        "✅ Hər bütöv öz hissələrinin CƏMİNƏ bərabərdir → xana səviyyəsində pillələr "
        "AYRIQDIR: heç bir xana iki pilləyə düşmür, heç bir xana pilləsiz qalmır."
        if identity_bad == 0
        else f"🔴 {fmt_int(identity_bad)} xana ya iki pilləyə düşür, ya da heç birinə — nərdivan ETİBARSIZDIR."
    )
    return "\n".join(
        [
            "#### Pillələr üst-üstə düşürmü — kəsişmənin ÖLÇÜSÜ",
            "",
            "«Pillələr ayrıqdır» iddiası kodun quruluşuna (hər xana bir `continue`-da",
            "bitir) söykənir, amma hesabat iddianı yoxlayır: hər bütövün öz",
            "hissələrinə bərabərliyi AYRICA sayılır.",
            "",
            md_table(["Domen", "Bütöv", "Bütövün sayı", "Hissələrin cəmi", "Qalıq"], identity_rows),
            "",
            verdict,
            "",
            "XANA səviyyəsində kəsişmə sıfır olsa da, eyni JURNAL və ya eyni YAZILIŞ",
            "bir neçə pillədə görünə bilər.  Bu, ikiqat çıxılma DEYİL (say ikiqat",
            "getmir), amma «pillələr müstəqil hadisələrdir» fərziyyəsini yalanlayır —",
            "ona görə ölçülüb göstərilir:",
            "",
            md_table(["Pillə A", "Pillə B", "Ortaq jurnal", "Ortaq yazılış"], overlap_rows or [["—", "—", "—", "—"]]),
        ]
    )

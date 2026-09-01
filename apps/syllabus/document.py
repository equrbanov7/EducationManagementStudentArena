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

⚠️ Bu qurucu HEÇ NƏ QURAŞDIRMIR — yalnız yazılanı göstərir
=========================================================
Sənəd tələbəyə göstərilir, yəni buradakı hər sətir onun üçün REAL faktdır.
Ona görə blok gövdəsində tətbiqin DEFOLT dəyərindən qurulmuş «sanki data»
sətri OLA BİLMƏZ.  Konkret presedent: qiymətləndirmə bloku əvvəllər bal
bölgüsünü ``10 + 10 + {midterm} + {project} + 50 = 100 bal`` kimi QURURDU və
``note``/``exam_questions`` sahələrini heç oxumurdu — nəticədə köçürülmüş
8,248 sillabusun hamısında tələbə mənbədə OLMAYAN «10 + 10 + 0 + 30 + 50»
bölgüsünü görür, mənbədəki əsl qayda mətni isə (Nazirlər Kabinetinin 348
nömrəli qərarına istinad edən bəndlər) heç yerdə çıxmırdı.  İndi bölgü sətri
yalnız çəkilər DOLDURULANDA yazılır, mətn və suallar isə olduğu kimi göstərilir
(bax :func:`_assessment_body`).  Eyni qayda sərbəst iş balına da aiddir: bal
məlum deyilsə «(0 bal)» YAZILMIR (bax :func:`_selfwork_line`).

Eyni ailədən daha üç qayda (2026-08-31 baxışı)
----------------------------------------------
* **Yarımçıq cütlükdən bölgü çıxarılmır.** ``project`` açarı yoxdursa ikinci
  yarı siyasətdən HESABLANMIR — bu, uydurma cəmin başqa qapısı idi.
* **Mümkün olmayan cəm göstərilmir.** Cəm siyasətin 100-ünə düşmürsə sətir çap
  edilmir və hadisə log-a yazılır (bax :func:`_assessment_weights`).
* **Abzas boşluğu oxucuya çatır.** Köçürmə təmizləyicisi (``legacy_text.
  clean_multiline_text``) abzas fasiləsini QƏSDƏN saxlayır; oxucu onu artıq
  atmır (bax :func:`_prose_lines`).
"""

from __future__ import annotations

import logging

from django.utils.translation import pgettext_lazy

from .constants import SELFWORK_OPTIONS, SELFWORK_TOTAL_SCORE, SectionKey, SyllabusStatus

_CTX = "syllabus.document"

logger = logging.getLogger(__name__)

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

#: Qiymətləndirmə blokunun BOŞ hallı.  Uydurma cəm (defolt rəqəmlərdən
#: qurulmuş «10 + 10 + 0 + 30 + 50 = 100 bal») tələbəyə REAL siyasət kimi
#: görünürdü; boşluq indi AÇIQ deyilir.  ⚠️ Bu etiket blokun YEGANƏ sətri
#: olanda çıxır — mənbə mətninin üstündə çıxanda o mətni təkzib edirdi
#: (bax :func:`_assessment_body`).
_WEIGHTS_UNSPECIFIED = pgettext_lazy(_CTX, "Bal bölgüsü göstərilməyib")
_EXAM_QUESTIONS_LABEL = pgettext_lazy(_CTX, "İmtahan sualları")

# ── Universitet siyasəti ilə KİLİDLİ çəkilər ─────────────────────────────────
# Redaktorun ``ASSESSMENT_POLICY`` cədvəli ilə (apps.accounts.views.syllabus.
# editor) EYNİ rəqəmlər: davamiyyət 10, sərbəst iş 10 (``SELFWORK_TOTAL_SCORE``),
# yekun imtahan 50; qalan 30 bal isə aralıq imtahan ↔ semestr layihəsi arasında
# müəllim tərəfindən bölünür. ⚠️ Bu rəqəmlər YALNIZ müəllim bölgünü DOLDURANDA
# göstərilir — doldurulmamış dosyedə (o cümlədən köçürülmüş sillabusda) onları
# çap etmək mənbədə olmayan struktur uydurmaq deməkdir.
_ATTENDANCE_SCORE = 10
_FINAL_EXAM_SCORE = 50
_FLEX_SCORE = 30
#: Siyasətin YEGANƏ mümkün cəmi.  Bölgü sətri bu rəqəmə düşmürsə o, bölgü DEYİL
#: (bax :func:`_assessment_weights`) — tələbəyə «= 110 bal» kimi mümkün olmayan
#: qayda göstərmək uydurmanın başqa formasıdır.
_POLICY_TOTAL = _ATTENDANCE_SCORE + SELFWORK_TOTAL_SCORE + _FLEX_SCORE + _FINAL_EXAM_SCORE


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _lines(value) -> list:
    """NÖMRƏLƏNƏN siyahı üçün: hər boş sətir atılır.

    ⚠️ Yalnız ``outcomes`` bu formadadır — orada boş sətir saxlamaq «TN2. »
    kimi boş nömrə yaradardı.  Sərbəst mətn üçün :func:`_prose_lines` var.
    """

    if isinstance(value, (list, tuple)):
        return [_text(item) for item in value if _text(item)]
    return [line for line in (_text(value).split("\n")) if line.strip()]


def _prose_lines(value) -> list:
    """SƏRBƏST MƏTN üçün: abzas boşluğu OXUCUYA ÇATIR.

    ``legacy_text.clean_multiline_text`` köçürmə yolunda abzas boşluğunu QƏSDƏN
    saxlayır (üç ardıcıl ``\r\n`` bir boş sətrə sıxılır, biri isə müəllimin
    yazdığı abzas fasiləsidir).  Oxucu hər boş sətri atanda o iş tamamilə
    itirdi — canlı ölçmədə saxlanılan 588 boşluğun 588-i.  Burada təmizləyici
    ilə EYNİ resept işlədilir: baş/son boşluqlar atılır, daxildəki hər boş
    seriya BİR sətrə sıxılır.  Siyahı gələndə fərq yoxdur — mövqe daşımayan
    boş element onsuz da atılır.
    """

    if isinstance(value, (list, tuple)):
        # ⚠️ Siyahı elementi ARTIQ mövqe daşıya bilər.  Redaktorun toplayıcısı
        # (`syllabus_editor_fields.js::toProseLines`) abzas fasiləsini boş
        # ELEMENT kimi saxlayır; onu burada atmaq itkini oxu tərəfinə köçürərdi.
        # Element daxilindəki `\n` də sətirlərə açılır ki, iki qol eyni resepti
        # işlətsin (nəticə mətn kimi eynidir, struktur isə qorunur).
        raw = []
        for item in value:
            raw.extend(_text(item).split("\n"))
    else:
        raw = _text(value).split("\n")
    kept: list = []
    for line in raw:
        stripped = line.strip()
        if stripped:
            kept.append(stripped)
        elif kept and kept[-1]:
            kept.append("")
    while kept and not kept[-1]:
        kept.pop()
    return kept


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


def _int_or_zero(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _assessment_weights(assess: dict):
    """Müəllimin DOLDURDUĞU bal bölgüsü — YOXDURSA və ya MÜMKÜN DEYİLSƏ ``None``.

    Bölgü redaktorda TƏK sürüşdürücüdən gəlir və avtosave həmişə CÜTLÜKDƏ yazır
    (``project = 30 − midterm``), yəni müəllim paneli bir dəfə də olsun
    saxlayıbsa çəkilərdən ƏN AZI BİRİ müsbətdir — sürüşdürücü 0-da qalsa belə
    ``project`` 30 olur.  Boş sxem (``drafts.BLANK_SECTION_DATA``) və köçürmə
    borusu isə hər ikisini 0 yazır: bu, «bölgü YOXDUR» deməkdir, «hər ikisi
    sıfırdır» yox.  Fərq məhz burada saxlanılır — əks halda tələbə mənbədə
    olmayan defolt cəmi real bölgü kimi görür.

    ⚠️ İKİ fail-closed qapı — hər ikisi məhz UYDURMANIN qarşısını alır:

    1. **Yarımçıq cütlük bölgü DEYİL.**  Əvvəl ``project`` açarı olmayan sətir
       üçün ikinci yarı siyasətdən ÇIXARILIRDI (``project = 30 − midterm``) —
       yəni tələbə heç kimin yazmadığı rəqəmi real qayda kimi görürdü.  Bu,
       məhz ləğv etdiyimiz sinifdəndir; ``project`` indi yalnız YAZILANDA
       oxunur, yoxdursa 0-dır (və 2-ci qapı onu süzür).
    2. **Siyasətlə mümkün olmayan cəm göstərilmir.**  ``save_section`` sərbəst
       JSON qəbul edir, yəni ``midterm=20, project=20`` kimi cütlük saxlanıla
       bilər.  Onun cəmi 110-dur — belə qayda universitetdə YOXDUR, ona görə
       sətir çap edilmir və hadisə operator üçün log-a düşür.  Rəqəmlər
       susdurulmur: onlar log-dadır, sadəcə tələbəyə «qayda» kimi verilmir.
    """
    midterm = max(0, _int_or_zero(assess.get("midterm")))
    project = max(0, _int_or_zero(assess.get("project")))
    if midterm <= 0 and project <= 0:
        return None
    total = _ATTENDANCE_SCORE + SELFWORK_TOTAL_SCORE + midterm + project + _FINAL_EXAM_SCORE
    if total != _POLICY_TOTAL:
        logger.warning(
            "syllabus.assessment_weights_off_policy midterm=%s project=%s total=%s expected=%s",
            midterm,
            project,
            total,
            _POLICY_TOTAL,
        )
        return None
    return midterm, project


def _assessment_body(assess: dict) -> str:
    """Qiymətləndirmə bloku — QURAŞDIRILMIR, yazılanı göstərir.

    Ardıcıllıq: bal bölgüsü (yalnız doldurulubsa) → qiymətləndirmə qaydasının
    ÖZ mətni (``note``) → imtahan sualları.

    ⚠️ «Bal bölgüsü göstərilməyib» etiketi YALNIZ blokda BAŞQA HEÇ NƏ olmayanda
    yazılır.  Əvvəl o, mətnin ÜSTÜNDƏ çap olunurdu və canlı ölçmədə (8,260
    uniqid) etiketin göründüyü 5,942 blokun **4,071-i (68.5 %)** bölgünü elə öz
    ardınca gələn mənbə mətnində AÇIQ deyirdi — məsələn «məşğələ (0-30 bal),
    sərbəst iş (0-10 bal), davamiyyət (0-10 bal), imtahan (0-50 bal)».  Tələbə
    əvvəlcə «göstərilməyib» oxuyur, sonra bölgünün özünü — etiket öz altındakı
    mətni TƏKZİB edirdi.  Mətn varsa o, boşluğun cavabıdır; etiket isə yalnız
    həqiqətən heç nə olmayanda mənalıdır (orada da ümumi «— doldurulmayıb —»
    işarəsindən daha dəqiqdir: bu blokun struktur məzmunu MƏHZ bölgüdür).
    """
    weights = _assessment_weights(assess)
    note = _prose_lines(assess.get("note"))
    questions = _prose_lines(assess.get("exam_questions"))

    body: list = []
    if weights is not None:
        midterm, project = weights
        total = _ATTENDANCE_SCORE + SELFWORK_TOTAL_SCORE + midterm + project + _FINAL_EXAM_SCORE
        body.append(
            f"{_ATTENDANCE_SCORE} + {SELFWORK_TOTAL_SCORE} + {midterm} + {project}"
            f" + {_FINAL_EXAM_SCORE} = {total} {_POINTS}"
        )
    body.extend(note)
    if questions:
        body.append(f"{_EXAM_QUESTIONS_LABEL}:")
        body.extend(questions)
    return "\n".join(body) or str(_WEIGHTS_UNSPECIFIED)


def _selfwork_line(index, row, config) -> str:
    """Sərbəst iş sətri — bal YALNIZ MƏLUM OLANDA yazılır.

    ``config`` yoxdur = variant (1x10/2x5/10x1) seçilməyib, yəni tapşırığın balı
    MƏLUM DEYİL.  Əvvəl bu hal «(0 bal)» kimi çap olunurdu — mənbədə variant
    daşımayan köçürülmüş sillabuslarda tələbə hər mövzunu sıfır ballıq sanırdı.
    """
    title = _text(row.get("title")) or "—"
    if config is None:
        return f"{index}. {title}"
    return f"{index}. {title} ({config['per_score']} {_POINTS})"


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
            "body": "\n".join(_prose_lines(method.get("methods")) + _prose_lines(method.get("note"))) or str(_EMPTY),
        },
        {"title": BLOCK_TITLES["assessment"], "body": _assessment_body(assess)},
        {
            "title": BLOCK_TITLES["selfwork"],
            "body": "\n".join(_selfwork_line(index, row, config) for index, row in enumerate(topics, start=1))
            or str(_EMPTY),
        },
        {
            "title": BLOCK_TITLES["literature"],
            "body": "\n".join(_prose_lines(literature.get("primary")) + _prose_lines(literature.get("additional")))
            or str(_EMPTY),
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
        "program": syllabus.program.display_label if syllabus.program_id else "",
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

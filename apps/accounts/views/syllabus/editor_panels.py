"""Redaktor panellərinin MƏNBƏ-ƏSASLI qurulması (həftə / metod / sərbəst iş).

Niyə ayrı modul
===============
Bu funksiyalar redaktorun DOM-unu təyin edir, yəni **autosave gövdəsinin
sərhədini** onlar cızır: JS toplayıcısı yalnız burada render olunan elementləri
görə bilir.  ``editor.py`` isə context müqaviləsi/`nav`/`summary` işidir.  Modul
ölçüsü qaydası (SOFT_CAP=600) da bu bölgünü tələb edirdi.

⚠️ SİNİF SƏHVİ — «redaktor mənbədən DAR render edir»
====================================================
``save_section`` PATCH-dir və açar səviyyəsində birləşdirir (bax
``apps.syllabus.services.drafts.save_section``), amma bu, açarın **içindəki**
itkini dayandırmır: göndərilən ``methods: []`` / ``topics: []`` / 16 sətirlik
``rows`` AÇIQ dəyərdir, yəni haqlı olaraq yazılır.  Köçürülmüş sillabusda üç
yolla məzmun itirdi:

* ``method.methods`` — redaktor yalnız ``TEACHING_METHODS`` kataloqunun sabit
  çiplərini render edirdi; köçürülmüş sərbəst mətn metodu heç bir çipə uyğun
  gəlmirdi, ona görə ilk autosave-də ``[]`` gedirdi (canlı: 8,260 sillabus);
* ``self.topics`` — köçürmə ``option: ""`` yazır, redaktor isə variant
  seçilməyəndə **0 yuva** açırdı → ``topics: []`` (canlı: 8,258 sillabus);
* ``week.rows`` — cədvəl HƏMİŞƏ dəqiq 16 sətrə normallaşırdı (mənbədə 120-yə
  qədər sətir var), üstəlik hər sətrin ``practical``/``note`` açarları
  toplayıcının qurduğu yeni lüğətdə itirdi (canlı: 1,970 + 8,220 sillabus).

Həll: **redaktor mənbəni RENDER EDİR.**  Serverdə «siyahı açarlarının quyruğunu
saxla» qaydası qoymaq daha ucuz görünürdü, amma o, «açıq boş dəyər = silmə
niyyəti» semantikasını pozardı — müəllim son metodu söndürəndə də silinməzdi.

⚠️ İKİNCİ QAT — DOM-un idarə ETMƏDİYİ açarlar
=============================================
Sətir/yuva daxilində redaktorun input-u OLMAYAN hər açar ``carry_over()`` ilə
``data-extra`` JSON-una yığılır; toplayıcı sətri məhz ondan qurub yalnız
DOM-un idarə etdiyi açarları üstələyir.  Beləliklə sxemə gələcəkdə əlavə olunan
sahə üçün heç nə etmək lazım gəlmir — avtomatik qorunur.
"""

from __future__ import annotations

import json

from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import (
    LESSON_HOUR_KINDS,
    SELFWORK_DISALLOWED,
    SELFWORK_OPTIONS,
    SELFWORK_TOTAL_SCORE,
    WEEK_ROWS,
)

from .labels import HOUR_KIND_LABELS

_CTX = "accounts.syllabus"

#: `data-extra`-da daşınan açarların İNSAN ADI — müəllim gizli dəyəri görsün.
#: Siyahıda olmayan açar öz adı ilə göstərilir (uydurma etiket yazılmır).
CARRIED_LABELS = {
    "practical": pgettext_lazy(_CTX, "praktiki saat"),
    "note": pgettext_lazy(_CTX, "mənbə qeydi"),
}

#: NÖMRƏSİZ (boş) təlim nəticəsi sətrinin etiketi.  Durğu işarəsidir, tərcümə
#: olunan mətn deyil — göndərilən JS-dəki `BLANK_TAG` ilə eynidir.
BLANK_OUTCOME_TAG = "\u2014"

#: Həftəlik cədvəldəki saat seçimləri (dizayn: «—», 1 s … 4 s).
#: ⚠️ Mənbədə bundan BÖYÜK saat ola bilər; belə sətirdə seçim siyahısına həmin
#: dəyər ƏLAVƏ olunur, yoxsa `<select>` heç birini seçməz, brauzer birinci
#: variantı (0) göstərər və ilk autosave saatı sıfırlayardı.
HOUR_CHOICES = (0, 1, 2, 3, 4)

#: Həftə sətrində redaktorun İDARƏ ETDİYİ açarlar (qalanı `data-extra`-ya gedir).
WEEK_ROW_KEYS = frozenset({"topic", "outcome", *LESSON_HOUR_KINDS})

#: Sərbəst iş yuvasında redaktorun/şablonun idarə etdiyi açarlar.
SELFWORK_SLOT_KEYS = frozenset({"title", "graded", "graded_count"})

#: Arxiv sətrində şablonun `data-*` ilə daşıdığı açarlar.
SELFWORK_ARCHIVED_KEYS = frozenset({"title", "note"})


def to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def is_blank(value) -> bool:
    """Dəyər «boş»dur? — quyruq kəsimi və görünən qeyd üçün YEGANƏ meyar.

    ``False``/``0``/``""``/``[]``/``{}``/``None`` boş sayılır; qalan hər şey
    məzmundur.  Bu, ``graded: True`` və ya ``graded_count: 3`` daşıyan yuvanı
    avtomatik «dolu» edir, yəni qiymətlənmiş tapşırıq quyruqdan heç vaxt
    düşmür.
    """
    if value is None or value is False:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (int, float)):
        return not value
    if isinstance(value, (list, tuple, dict, set)):
        return not value
    return False


def without_blank_tail(rows) -> list:
    """Siyahının QUYRUĞUNDAKI tam boş elementləri render siyahısından çıxarır.

    ⚠️ Niyə lazımdır — xəbərdarlıq banneri ƏBƏDİ idi
    ================================================
    Banner müəllimə «lazımsız sətirlərin mövzusunu və saatını boşaldın» deyirdi;
    müəllim məhz onu edirdi, saxlayırdı, səhifə yenidən render olunurdu və
    **heç nə dəyişmirdi** (23 sətir yenə 23, 7 yuva yenə 7), çünki say
    ``len(raw)``-dan çıxırdı.  Yəni göstəriş İCRA EDİLƏ BİLMİRDİ.

    ⚠️ Yalnız QUYRUQ.  Ortadakı boş sətir yerində qalır — 5-ci həftəni
    boşaltmaq 6-cı həftəni 5-ə sürüşdürməməlidir (nömrələmə mənbənin
    strukturudur).

    ⚠️ Serverdə heç nə silinmir və heç nə kəsilmir: bu, yalnız RENDER
    qərarıdır.  Saxlanılan data yalnız müəllimin növbəti AÇIQ avtosaxlaması ilə
    qısalır — həm də yalnız bütün açarları boş olan elementlər qədər, yəni
    məzmun daşımayan quyruq qədər.
    """
    kept = list(rows)
    while kept and all(is_blank(value) for value in kept[-1].values()):
        kept.pop()
    return kept


def carried_note(source, known) -> str:
    """DOM-un idarə ETMƏDİYİ, amma SAXLANILAN açarların GÖRÜNƏN xülasəsi.

    ``carry_over`` dəyəri sağ saxlayır, lakin onu tamamilə GÖRÜNMƏZ edirdi:
    müəllim sətri boşaldıb «sildim» sanırdı, halbuki ``practical: 2`` (948
    sillabus) və ``note`` (145 sillabus) geri yazılırdı.  Redaktorun bu sahələr
    üçün input-u yoxdur — ən azı varlığı görünməlidir.
    """
    if not isinstance(source, dict):
        return ""
    parts = []
    for key in sorted(source):
        if key in known or is_blank(source[key]):
            continue
        label = CARRIED_LABELS.get(key)
        parts.append(f"{label if label is not None else key}: {source[key]}")
    return " · ".join(parts)


def carry_over(source, known) -> str:
    """DOM-un idarə ETMƏDİYİ açarları JSON sətrinə yığır (yoxdursa boş sətir).

    Toplayıcı sətri bu lüğətdən qurur, sonra DOM açarlarını üstələyir — yəni
    ``practical``, ``note`` və sxemə SONRA əlavə olunacaq hər açar heç bir kod
    dəyişikliyi olmadan geri yazılır.
    """
    if not isinstance(source, dict):
        return ""
    extra = {key: value for key, value in source.items() if key not in known}
    return json.dumps(extra, ensure_ascii=False, sort_keys=True) if extra else ""


def outcome_rows(data) -> list:
    """Redaktorun ``out`` panelinin sətirləri — BOŞ sətir TN NÖMRƏSİ TUTMUR.

    Toplayıcı boş sətri də göndərir (müəllimin yazmaqda olduğu sətir itməsin),
    ``outcome_tags`` və ``apps.syllabus.completion`` isə yalnız DOLU nəticələri
    sayır.  Panel əvvəllər sətirləri XAM sıra ilə nömrələyirdi
    (``TN{{ forloop.counter }}``), yəni boş sətir bir nömrəni «yeyirdi» və iki
    panel bir-birini təkzib edirdi: redaktorda «TN2» görünən nəticə həftə
    cədvəlinin açılış siyahısında «TN1» kimi seçilirdi.  Data itmirdi, amma
    müəllim hansı nəticəni bağladığını bilmirdi.

    İndi nömrə yalnız dolu sətrə verilir; eyni qaydanı göndərilən JS-in
    ``retagOutcomes``-u canlı yazı zamanı da tətbiq edir.
    """
    rows = []
    number = 0
    for item in data.get("outcomes") or []:
        text = str(item)
        if text.strip():
            number += 1
            rows.append({"text": text, "tag": f"TN{number}"})
        else:
            rows.append({"text": text, "tag": BLANK_OUTCOME_TAG})
    return rows


def outcome_tags(data) -> list:
    """Mövcud təlim nəticələrinin etiketləri — həftə sətrinin açılış siyahısı."""
    return [row["tag"] for row in outcome_rows(data) if row["tag"] != BLANK_OUTCOME_TAG]


def week_rows(data, tags=()) -> list:
    """``week`` sətirləri — ƏN AZI 16, mənbə daha uzundursa MƏNBƏ QƏDƏR.

    Əvvəllər burada ``range(WEEK_ROWS)`` vardı: 23 sətirlik köçürülmüş cədvəl
    16-ya kəsilir, toplayıcı isə 16 sətir geri göndərib qalan 7-ni silirdi.
    İndi artıq sətirlər `is_extra` damğası ilə göstərilir — müəllim onları
    ŞÜURLU boşaldır, redaktor səssizcə atmır.
    """
    # Quyruqdakı TAM boş sətirlər render siyahısına düşmür — yoxsa müəllimin
    # «boşaldın» göstərişini icra etməsi heç nəyi dəyişməzdi (banner əbədi).
    raw = without_blank_tail([row for row in (data.get("rows") or []) if isinstance(row, dict)])
    tag_list = list(tags)
    rows = []
    for index in range(max(WEEK_ROWS, len(raw))):
        source = raw[index] if index < len(raw) else {}
        outcome = str(source.get("outcome") or "")
        row = {
            "index": index + 1,
            "topic": (source.get("topic") or "").strip(),
            "outcome": outcome,
            "is_extra": index >= WEEK_ROWS,
            # Sətrin `practical` / `note` (və gələcək) açarları — toplayıcı
            # onları OLDUĞU KİMİ geri göndərsin deyə.
            "extra": carry_over(source, WEEK_ROW_KEYS),
            # Həmin açarların GÖRÜNƏN qarşılığı (input yoxdur, ən azı bilinsin).
            "extra_note": carried_note(source, WEEK_ROW_KEYS),
        }
        for kind in LESSON_HOUR_KINDS:
            row[kind] = to_int(source.get(kind))
        # Şablon xüsusi filtr yazmadan dövr edə bilsin deyə saat xanaları hazır
        # siyahı kimi verilir (`{{ row|dictkey:… }}` kimi tələ qalmır).
        row["cells"] = [
            {
                "key": kind,
                "label": HOUR_KIND_LABELS[kind],
                "value": row[kind],
                "choices": sorted(set(HOUR_CHOICES) | {row[kind]}),
            }
            for kind in LESSON_HOUR_KINDS
        ]
        # Mənbədəki TN etiketi cari siyahıda yoxdursa da seçim kimi qalır —
        # əks halda `<select>` onu itirər və autosave "" yazardı.
        row["outcome_choices"] = tag_list if (not outcome or outcome in tag_list) else [*tag_list, outcome]
        rows.append(row)
    return rows


def hour_totals(rows, plan_hours) -> dict:
    totals = {kind: sum(row[kind] for row in rows) for kind in LESSON_HOUR_KINDS}
    planned = {kind: to_int((plan_hours or {}).get(kind)) for kind in LESSON_HOUR_KINDS}
    return {
        "rows": [
            {
                "kind": kind,
                "have": totals[kind],
                "planned": planned[kind],
                "ok": totals[kind] == planned[kind],
            }
            for kind in LESSON_HOUR_KINDS
        ],
        "have": sum(totals.values()),
        "planned": sum(planned.values()),
        "ok": totals == planned,
    }


def selfwork(data, notes) -> dict:
    """``self`` paneli — MÖVCUD mövzular variant seçilməsə də yuva kimi açılır.

    Köçürmə ``option: ""`` yazır (köhnə sistemdə struktur anlayışı yoxdur), köhnə
    kodda isə yuva sayı yalnız variantdan çıxırdı → 7 mövzu, 0 yuva, ``[]``.
    İndi yuva sayı ``max(variant sayı, mövzu sayı)``-dır: variant seçilənə qədər
    mövzular görünür, variantdan ARTIQ qalanlar `is_extra` damğası alır.

    ⚠️ Bal bölgüsünə TOXUNULMUR (sahibin qərarı ilə bağlı mövzudur): variant
    seçilməyibsə `per_score` sadəcə BOŞ qalır, uydurma bal yazılmır.
    """
    option = (data.get("option") or "").strip()
    # Həftə cədvəlindəki ilə EYNİ qayda: boşaldılmış quyruq yuvası siyahıdan
    # düşür, yoxsa «artıq mövzuları boşaldın» banneri əbədi qalırdı.
    topics = without_blank_tail([row for row in (data.get("topics") or []) if isinstance(row, dict)])
    options = []
    for key, config in SELFWORK_OPTIONS.items():
        options.append(
            {
                "key": key,
                "title": f"{config['count']} × {config['per_score']}",
                "count": config["count"],
                "per_score": config["per_score"],
                "total": config["count"] * config["per_score"],
                "note": notes.get(key, ""),
                "active": option == key,
                "allowed": True,
            }
        )
    for key, config in SELFWORK_DISALLOWED.items():
        options.append(
            {
                "key": key,
                "title": f"{config['count']} × {config['per_score']}",
                "count": config["count"],
                "per_score": config["per_score"],
                "total": config["count"] * config["per_score"],
                "note": notes.get(key, ""),
                # ⚠️ QƏSDƏN sabit `False` — «saxlanılan dəyəri işarələ» DEYİL.
                # Baxışda bu, itki yolu kimi görünür (heç bir çip `is-on`
                # olmur, `collectSelf` `option: ""` göndərir).  Əslində DEYİL:
                # `drafts.save_section` icazəsiz variantı ONSUZ DA rədd edir
                # (`self.option_not_allowed`), yəni belə dəyər heç vaxt
                # saxlanıla bilmir.  Çipi `is-on` etmək bölmənin HƏR
                # avtosaxlamasını çökdürərdi — ölçülüb, bax
                # `test_a_disallowed_selfwork_option_can_never_be_stored`.
                "active": False,
                "allowed": False,
            }
        )
    config = SELFWORK_OPTIONS.get(option)
    planned = config["count"] if config else 0
    slots = []
    for index in range(max(planned, len(topics))):
        source = topics[index] if index < len(topics) else {}
        slots.append(
            {
                "index": index + 1,
                "title": (source.get("title") or "").strip(),
                "graded": bool(source.get("graded")),
                "graded_count": to_int(source.get("graded_count")),
                "per_score": config["per_score"] if config else None,
                "is_extra": index >= planned,
                "extra": carry_over(source, SELFWORK_SLOT_KEYS),
                "extra_note": carried_note(source, SELFWORK_SLOT_KEYS),
            }
        )
    return {
        "option": option,
        "options": options,
        "slots": slots,
        "planned_count": planned,
        "extra_count": sum(1 for slot in slots if slot["is_extra"]),
        # Arxiv sətri də `data-extra` daşıyır: toplayıcı onu `carried()` ilə
        # oxuyur, yəni sxemə sonra əlavə olunan açar burada da qorunur.
        "archived": [
            {**row, "extra": carry_over(row, SELFWORK_ARCHIVED_KEYS)}
            for row in (data.get("archived") or [])
            if isinstance(row, dict)
        ],
        "total_score": SELFWORK_TOTAL_SCORE,
    }


def methods(catalog, data) -> dict:
    """``method`` paneli — kataloq çipləri + KATALOQDA OLMAYAN metodlar.

    Köhnə kod yalnız ``catalog``-u render edirdi, ona görə köçürülmüş sərbəst
    mətn («1. mühazirə\\n2. mövzunun müzakirəsi…») heç bir çipə düşmürdü və
    ``collectMethod`` onu ilk autosave-də silirdi.

    İndi kataloqa uyğun gəlməyən hər metod AYRICA, açıq işarələnmiş çip kimi
    render olunur və `is-on` gəlir.  Silmək mümkündür, amma TƏSADÜFƏN yox:
    çipin gövdəsi klik qəbul etmir, yalnız ayrıca «Çıxar» düyməsi vəziyyəti
    çevirir (və eyni düymə geri qaytarır).
    """
    catalog_labels = [str(label) for label in catalog]
    known = set(catalog_labels)
    chosen = {str(item) for item in (data.get("methods") or []) if str(item).strip()}
    chips = [{"label": label, "value": label, "active": label in chosen} for label in catalog_labels]

    custom, seen = [], set()
    for item in data.get("methods") or []:
        text = str(item)
        if not text.strip() or text in known or text in seen:
            continue
        seen.add(text)
        custom.append({"label": text, "value": text, "active": True})
    return {"catalog": chips, "custom": custom, "custom_count": len(custom)}


__all__ = [
    "CARRIED_LABELS",
    "HOUR_CHOICES",
    "SELFWORK_ARCHIVED_KEYS",
    "SELFWORK_SLOT_KEYS",
    "WEEK_ROW_KEYS",
    "carried_note",
    "carry_over",
    "is_blank",
    "hour_totals",
    "methods",
    "outcome_rows",
    "outcome_tags",
    "selfwork",
    "to_int",
    "week_rows",
    "without_blank_tail",
]

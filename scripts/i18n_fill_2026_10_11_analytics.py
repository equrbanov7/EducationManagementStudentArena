#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-11: «Akademik analitika» səliqəsi (ortaq KPI/cədvəl komponentləri).

Əlavə olunan mətnlər (`registrar.analytics`): KPI kartlarının qeydləri (yekunlaşmış nəticə
yoxdursa «—» səbəbi, proqram/qrup sayı, kəsilmə həddi), cədvəl kartlarının alt-yazıları,
sətir sayı nişanı və boş vəziyyət izahı. Mənbə: `apps/registrar/analytics_display.py`,
`apps/registrar/templates/registrar/partials/_analytics_content.html`.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_11_analytics.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AN = "registrar.analytics"

_AN = [
    # ── KPI qeydləri (analytics_display.py) ──────────────────────────────
    _t(
        "Hələ yekunlaşmış qiymət yoxdur",
        "No finalized grades yet",
        "Итоговых оценок пока нет",
        "Henüz kesinleşmiş not yok",
    ),
    _t(
        "%(passed)s / %(definite)s yekunlaşmış nəticə",
        "%(passed)s / %(definite)s finalized results",
        "%(passed)s / %(definite)s итоговых результатов",
        "%(passed)s / %(definite)s kesinleşmiş sonuç",
    ),
    _t(
        "Yekunlaşmış qiymət olmadan hesablanmır",
        "Not calculated until grades are finalized",
        "Не рассчитывается без итоговых оценок",
        "Kesinleşmiş not olmadan hesaplanmaz",
    ),
    _t(
        "Kredit-çəkili, 100 bal şkalası",
        "Credit-weighted, 100-point scale",
        "Взвешено по кредитам, 100-балльная шкала",
        "Kredi ağırlıklı, 100 puan ölçeği",
    ),
    _t(
        "Kəsilmə həddində: %(count)s qeydiyyat",
        "Over the absence bar: %(count)s enrollments",
        "Превышен лимит пропусков: %(count)s записей",
        "Devamsızlık sınırında: %(count)s kayıt",
    ),
    _t(
        "Kəsilmə həddində qeydiyyat yoxdur",
        "No enrollments over the absence bar",
        "Нет записей с превышением лимита пропусков",
        "Devamsızlık sınırında kayıt yok",
    ),
    _t(
        "Proqram: %(programs)s · qrup: %(groups)s",
        "Programmes: %(programs)s · groups: %(groups)s",
        "Программ: %(programs)s · групп: %(groups)s",
        "Program: %(programs)s · grup: %(groups)s",
    ),
    _t(
        "Yekunlaşıb: %(done)s · davam edir: %(open)s",
        "Finalized: %(done)s · in progress: %(open)s",
        "Завершено: %(done)s · в процессе: %(open)s",
        "Kesinleşti: %(done)s · devam ediyor: %(open)s",
    ),
    # ── Şablon (_analytics_content.html) ────────────────────────────────
    _t(
        "Seçilmiş semestrdə əhatənizdəki qruplara fənn qeydiyyatı yoxdur. Yuxarıdan başqa semestr seçin.",
        "There are no enrollments for the groups in your scope in the selected semester. Pick another semester above.",
        "В выбранном семестре у групп в вашей зоне нет записей на дисциплины. Выберите другой семестр выше.",
        "Seçilen dönemde kapsamınızdaki gruplara ders kaydı yok. Yukarıdan başka bir dönem seçin.",
    ),
    _t(
        "Keçid faizi və orta GPA yalnız yekunlaşmış nəticələrdən hesablanır; hələ yoxdursa «—».",
        "Pass rate and average GPA count only finalized results; “—” means none yet.",
        "Процент сдачи и средний GPA считаются только по итоговым результатам; «—» — их пока нет.",
        "Geçme oranı ve ortalama GPA yalnızca kesinleşmiş sonuçlardan hesaplanır; henüz yoksa «—».",
    ),
    _t("Sətir sayı", "Row count", "Количество строк", "Satır sayısı"),
    _t(
        "«Kəsilmə həddində» — qayıb limitini keçmiş fənn qeydiyyatlarının sayı.",
        "“Over absence bar” — number of enrollments that exceeded the absence limit.",
        "«Превышен лимит» — число записей на дисциплины, превысивших лимит пропусков.",
        "«Devamsızlık sınırında» — devamsızlık sınırını aşan ders kayıtlarının sayısı.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    AN: {row["az"]: row for row in _AN},
}

#: Hazırda məcburi düzəliş yoxdur (yalnız boş/fuzzy girişlər doldurulur).
FORCE: set = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                flags = ["python-format"] if "%(" in msgid else []
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want, flags=flags))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()

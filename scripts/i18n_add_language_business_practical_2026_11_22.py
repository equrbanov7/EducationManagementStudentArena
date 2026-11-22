#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-22 (2): «Xarici dildə işgüzar kommunikasiya» — praktiki məşğələ + sərbəst iş bir sütunda.

Sahib (RİM rəhbəri): «Praktiki məşğələ balını hesabla seminar kimi»; səviyyəsiz adlar da profildədir. ``django``
kataloquna (``core.runtime_settings`` + ``registrar.journal`` + ``profile.subjects``) beş dildə əlavə edir; AZ msgstr =
msgid. İdempotent.
İstifadə:  python scripts/i18n_add_language_business_practical_2026_11_22.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_RS = "core.runtime_settings"
_J = "registrar.journal"
_PS = "profile.subjects"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _RS, "«Xarici dildə işgüzar kommunikasiya»: davamiyyət 10 + praktiki / sərbəst iş 10 + midterm 10"): (
        "«Business communication in a foreign language»: attendance 10 + practical / independent work 10 + midterm 10",
        "«Деловая коммуникация на иностранном языке»: посещаемость 10 + практика / самостоятельная работа 10 + мидтерм 10",
        "«Yabancı dilde iş iletişimi»: devam 10 + uygulama / bağımsız çalışma 10 + ara sınav 10",
        "«Geschäftskommunikation in einer Fremdsprache»: Anwesenheit 10 + Übung / Selbststudium 10 + Midterm 10",
    ),
    (
        "django",
        _RS,
        "Yandırılıbsa «Xarici dildə işgüzar (və akademik) kommunikasiya -1, -2, -3» fənlərində (səviyyəsiz və ya "
        "Beginner, Elementary, Pre-intermediate, Intermediate) imtahana qədər bal = davamiyyət 10 + praktiki / "
        "sərbəst iş 10 (praktiki məşğələ ortası + sərbəst iş, ən çox 10) + midterm 10, yekun imtahan 70. Sərbəst "
        "iş tabı açıqdır, müəllim midterm balını (0–10) jurnalda özü yaza bilər. Söndürüləndə səviyyəli fənlər "
        "digər səviyyə fənləri kimi (davamiyyət + praktiki məşğələ + midterm 10, imtahan 70), səviyyəsizlər "
        "universitet standartı ilə hesablanır.",
    ): (
        "When on, in the subjects «Business (and academic) communication in a foreign language -1, -2, -3» (without a "
        "level or Beginner, Elementary, Pre-intermediate, Intermediate) the pre-exam score = attendance 10 + practical "
        "/ independent work 10 (practical class average + independent work, at most 10) + midterm 10, final exam 70. "
        "The independent work tab is open and the teacher can enter the midterm score (0–10) in the journal. When "
        "off, the level subjects are graded like the other level subjects (attendance + practical classes + midterm "
        "10, exam 70) and those without a level by the university standard.",
        "Если включено, в дисциплинах «Деловая (и академическая) коммуникация на иностранном языке -1, -2, -3» (без "
        "уровня или Beginner, Elementary, Pre-intermediate, Intermediate) балл до экзамена = посещаемость 10 + "
        "практика / самостоятельная работа 10 (средний балл практических занятий + самостоятельная работа, не более "
        "10) + мидтерм 10, итоговый экзамен 70. Вкладка самостоятельной работы открыта, преподаватель сам может "
        "внести балл мидтерма (0–10) в журнал. Если выключено, уровневые дисциплины оцениваются как остальные "
        "уровневые (посещаемость + практические занятия + мидтерм 10, экзамен 70), а без уровня — по стандарту "
        "университета.",
        "Açıksa «Yabancı dilde iş (ve akademik) iletişimi -1, -2, -3» derslerinde (seviyesiz veya Beginner, "
        "Elementary, Pre-intermediate, Intermediate) sınav öncesi puan = devam 10 + uygulama / bağımsız çalışma 10 "
        "(uygulama ortalaması + bağımsız çalışma, en çok 10) + ara sınav 10, final sınavı 70. Bağımsız çalışma "
        "sekmesi açıktır, öğretmen ara sınav puanını (0–10) deftere kendisi yazabilir. Kapalıysa seviyeli dersler "
        "diğer seviye dersleri gibi (devam + uygulama + ara sınav 10, sınav 70), seviyesizler üniversite standardıyla "
        "hesaplanır.",
        "Wenn aktiviert, gilt in den Fächern «Geschäfts- (und akademische) Kommunikation in einer Fremdsprache -1, -2, "
        "-3» (ohne Niveau oder Beginner, Elementary, Pre-intermediate, Intermediate): Punkte vor der Prüfung = "
        "Anwesenheit 10 + Übung / Selbststudium 10 (Durchschnitt der praktischen Übungen + Selbststudium, höchstens "
        "10) + Midterm 10, Abschlussprüfung 70. Der Reiter Selbststudium ist offen, und die Lehrkraft kann die "
        "Midterm-Punkte (0–10) selbst ins Journal eintragen. Wenn deaktiviert, werden die Niveaufächer wie die anderen "
        "Niveaufächer bewertet (Anwesenheit + praktische Übungen + Midterm 10, Prüfung 70), die ohne Niveau nach dem "
        "Universitätsstandard.",
    ),
    ("django", _J, "Praktiki / sərbəst iş"): (
        "Practical / independent work",
        "Практика / самостоятельная работа",
        "Uygulama / bağımsız çalışma",
        "Übung / Selbststudium",
    ),
    ("django", _J, "Praktiki məşğələ ballarının ortası + sərbəst iş balı; cəmi ən çox 10."): (
        "Average of practical class scores + independent work score; at most 10 in total.",
        "Средний балл практических занятий + балл самостоятельной работы; в сумме не более 10.",
        "Uygulama puanlarının ortalaması + bağımsız çalışma puanı; toplam en çok 10.",
        "Durchschnitt der Übungspunkte + Punkte für das Selbststudium; insgesamt höchstens 10.",
    ),
    (
        "django",
        _J,
        "Giriş balı = davamiyyət + Midterm + praktiki / sərbəst iş (hər biri 10); tam ədədə yuvarlaqlaşdırılır (tavan",
    ): (
        "Entry score = attendance + midterm + practical / independent work (10 each); rounded to a whole number (cap",
        "Входной балл = посещаемость + мидтерм + практика / самостоятельная работа (по 10); округляется до целого "
        "(предел",
        "Giriş puanı = devam + ara sınav + uygulama / bağımsız çalışma (her biri 10); tam sayıya yuvarlanır (üst sınır",
        "Zulassungspunkte = Anwesenheit + Midterm + Übung / Selbststudium (je 10); auf ganze Zahl gerundet (Obergrenze",
    ),
    ("django", _PS, "Praktiki / sərbəst iş"): (
        "Practical / independent work",
        "Практика / самостоятельная работа",
        "Uygulama / bağımsız çalışma",
        "Übung / Selbststudium",
    ),
}


def main():
    for domain in ("django",):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
                if "%(" in msgid:
                    entry.flags.append("python-format")
                po.append(entry)
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()

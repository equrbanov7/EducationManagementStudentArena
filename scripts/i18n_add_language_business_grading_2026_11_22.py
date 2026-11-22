#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-22: «Xarici dildə işgüzar kommunikasiya» qiymətləndirmə profili.

Sahib (RİM rəhbəri): «Dil fənlərində 10 bal sərbəst iş, 10 bal davamiyyət, 10 bal midterm; midterm üçün xana; final
70». ``django`` kataloquna (``core.runtime_settings`` + ``registrar.journal`` + ``profile.subjects``) beş dildə əlavə
edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_language_business_grading_2026_11_22.py
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
    ("django", _RS, "«Xarici dildə işgüzar kommunikasiya»: sərbəst iş 10 + davamiyyət 10 + midterm 10"): (
        "«Business communication in a foreign language»: independent work 10 + attendance 10 + midterm 10",
        "«Деловая коммуникация на иностранном языке»: самостоятельная работа 10 + посещаемость 10 + мидтерм 10",
        "«Yabancı dilde iş iletişimi»: bağımsız çalışma 10 + devam 10 + ara sınav 10",
        "«Geschäftskommunikation in einer Fremdsprache»: Selbststudium 10 + Anwesenheit 10 + Midterm 10",
    ),
    (
        "django",
        _RS,
        "Yandırılıbsa «Xarici dildə işgüzar (və akademik) kommunikasiya -1, -2, -3» (Beginner, Elementary, "
        "Pre-intermediate, Intermediate) fənlərində imtahana qədər bal = sərbəst iş 10 + davamiyyət 10 + midterm 10, "
        "yekun imtahan 70. Praktiki məşğələ balı bu fənlərdə toplanmır, sərbəst iş tabı açıqdır, müəllim midterm balını "
        "(0–10) jurnalda özü yaza bilər. Söndürüləndə bu fənlər digər səviyyə fənləri kimi hesablanır: davamiyyət 10 + "
        "praktiki məşğələ 10 + midterm 10, imtahan 70.",
    ): (
        "When on, in the subjects «Business (and academic) communication in a foreign language -1, -2, -3» (Beginner, "
        "Elementary, Pre-intermediate, Intermediate) the pre-exam score = independent work 10 + attendance 10 + midterm "
        "10, final exam 70. Practical class scores are not added in these subjects, the independent work tab is open, "
        "and the teacher can enter the midterm score (0–10) in the journal. When off, these subjects are graded like "
        "the other level subjects: attendance 10 + practical classes 10 + midterm 10, exam 70.",
        "Если включено, в дисциплинах «Деловая (и академическая) коммуникация на иностранном языке -1, -2, -3» "
        "(Beginner, Elementary, Pre-intermediate, Intermediate) балл до экзамена = самостоятельная работа 10 + "
        "посещаемость 10 + мидтерм 10, итоговый экзамен 70. Баллы практических занятий в этих дисциплинах не "
        "суммируются, вкладка самостоятельной работы открыта, преподаватель сам может внести балл мидтерма (0–10) в "
        "журнал. Если выключено, эти дисциплины оцениваются как остальные уровневые: посещаемость 10 + практические "
        "занятия 10 + мидтерм 10, экзамен 70.",
        "Açıksa «Yabancı dilde iş (ve akademik) iletişimi -1, -2, -3» (Beginner, Elementary, Pre-intermediate, "
        "Intermediate) derslerinde sınav öncesi puan = bağımsız çalışma 10 + devam 10 + ara sınav 10, final sınavı 70. "
        "Bu derslerde uygulama puanları toplanmaz, bağımsız çalışma sekmesi açıktır, öğretmen ara sınav puanını (0–10) "
        "deftere kendisi yazabilir. Kapalıysa bu dersler diğer seviye dersleri gibi hesaplanır: devam 10 + uygulama 10 "
        "+ ara sınav 10, sınav 70.",
        "Wenn aktiviert, gilt in den Fächern «Geschäfts- (und akademische) Kommunikation in einer Fremdsprache -1, -2, "
        "-3» (Beginner, Elementary, Pre-intermediate, Intermediate): Punkte vor der Prüfung = Selbststudium 10 + "
        "Anwesenheit 10 + Midterm 10, Abschlussprüfung 70. Punkte aus praktischen Übungen werden in diesen Fächern "
        "nicht addiert, der Reiter Selbststudium ist offen, und die Lehrkraft kann die Midterm-Punkte (0–10) selbst ins "
        "Journal eintragen. Wenn deaktiviert, werden diese Fächer wie die anderen Niveaufächer bewertet: Anwesenheit 10 "
        "+ praktische Übungen 10 + Midterm 10, Prüfung 70.",
    ),
    (
        "django",
        _J,
        "Giriş balı = davamiyyət + Midterm + sərbəst iş (hər biri 10); tam ədədə yuvarlaqlaşdırılır (tavan",
    ): (
        "Entry score = attendance + midterm + independent work (10 each); rounded to a whole number (cap",
        "Входной балл = посещаемость + мидтерм + самостоятельная работа (по 10); округляется до целого (предел",
        "Giriş puanı = devam + ara sınav + bağımsız çalışma (her biri 10); tam sayıya yuvarlanır (üst sınır",
        "Zulassungspunkte = Anwesenheit + Midterm + Selbststudium (je 10); auf ganze Zahl gerundet (Obergrenze",
    ),
    (
        "django",
        _J,
        "Bu fəndə Midterm balını (0–%(max)s) özünüz yazırsınız — İmtahan Mərkəzinin pəncərəsini gözləmək lazım deyil. "
        "Yazılmış bal digər jurnal balları kimi qısa müddət ərzində dəyişdirilə bilər, sonra yalnız sənədli düzəliş "
        "ilə. İmtahan Mərkəzində keçirilən midterm nəticəsi də bu xanaya 10 ballıq şkala ilə köçürülür.",
    ): (
        "In this subject you enter the midterm score (0–%(max)s) yourself — there is no need to wait for the Exam "
        "Center window. Like other journal scores, an entered score can be changed for a short time, after that only "
        "through a documented correction. A midterm held at the Exam Center is also transferred to this cell on the "
        "10-point scale.",
        "В этой дисциплине балл мидтерма (0–%(max)s) вы вносите сами — ждать окна Экзаменационного центра не нужно. "
        "Как и другие баллы журнала, внесённый балл можно изменить в течение короткого времени, затем только через "
        "документальное исправление. Результат мидтерма, проведённого в Экзаменационном центре, тоже переносится в эту "
        "ячейку по 10-балльной шкале.",
        "Bu derste ara sınav puanını (0–%(max)s) kendiniz yazarsınız — Sınav Merkezinin penceresini beklemeniz "
        "gerekmez. Yazılan puan diğer defter puanları gibi kısa süre içinde değiştirilebilir, sonrasında yalnızca "
        "belgeli düzeltmeyle. Sınav Merkezinde yapılan ara sınav sonucu da bu hücreye 10 puanlık ölçekle aktarılır.",
        "In diesem Fach tragen Sie die Midterm-Punkte (0–%(max)s) selbst ein — auf das Fenster des Prüfungszentrums "
        "müssen Sie nicht warten. Wie andere Journalpunkte kann ein eingetragener Wert kurze Zeit geändert werden, "
        "danach nur über eine dokumentierte Korrektur. Ein im Prüfungszentrum geschriebener Midterm wird ebenfalls auf "
        "der 10-Punkte-Skala in diese Zelle übertragen.",
    ),
    ("django", _PS, "Xarici dildə işgüzar kommunikasiya"): (
        "Business communication in a foreign language",
        "Деловая коммуникация на иностранном языке",
        "Yabancı dilde iş iletişimi",
        "Geschäftskommunikation in einer Fremdsprache",
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

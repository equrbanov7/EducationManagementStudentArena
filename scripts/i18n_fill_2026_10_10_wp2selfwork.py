#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10 (WP2): «Sərbəst iş» yeni qayda dövrlərində gizlədilir (sahib 2026-10-10).

Əlavə olunan mətnlər:
  * `syllabus.assessment`: 5 + 5 düsturu (seminar / laboratoriya ayrıca ortalanır) və onun izahları;
  * `accounts.syllabus`: sərbəst işsiz qaydanın redaktor izahı (midterm 30), təsdiq banneri / dialoq sətri,
    «Böyük dəyişiklik» izahı, semestr balının izahı;
  * `registrar.selfwork` / `registrar.selfwork_hook`: «bu semestrdə sərbəst iş tətbiq olunmur» imtinaları;
  * `subject_folder.error` / `subject_folder.ui`: sərbəst işsiz qovluq mətnləri.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_wp2selfwork.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AS = "accounts.syllabus"
SA = "syllabus.assessment"
RS = "registrar.selfwork"
RH = "registrar.selfwork_hook"
SE = "subject_folder.error"
SU = "subject_folder.ui"

_ASSESSMENT = [
    _t(
        "Seminar ballarının ortası",
        "Seminar score average",
        "Среднее баллов за семинары",
        "Seminer puanları ortalaması",
    ),
    _t(
        "Laboratoriya ballarının ortası",
        "Laboratory score average",
        "Среднее баллов за лабораторные",
        "Laboratuvar puanları ortalaması",
    ),
    _t(
        "Seminar ballarının ədədi ortası",
        "Average of seminar scores",
        "Среднее арифметическое баллов за семинары",
        "Seminer puanlarının aritmetik ortalaması",
    ),
    _t(
        "Laboratoriya ballarının ədədi ortası",
        "Average of laboratory scores",
        "Среднее арифметическое баллов за лабораторные",
        "Laboratuvar puanlarının aritmetik ortalaması",
    ),
    _t(
        "Seminar və laboratoriya: seminar ballarının ortası 5 + laboratoriya ballarının ortası 5",
        "Seminar and laboratory: seminar score average 5 + laboratory score average 5",
        "Семинар и лабораторные: среднее за семинары 5 + среднее за лабораторные 5",
        "Seminer ve laboratuvar: seminer puanları ortalaması 5 + laboratuvar puanları ortalaması 5",
    ),
    _t(
        "Seminar ballarının ədədi ortası (10): semestr ərzində yazılmış bütün seminar ballarının ortası.",
        "Average of seminar scores (10): the average of all seminar scores recorded during the semester.",
        "Среднее арифметическое баллов за семинары (10): среднее всех баллов за семинары, выставленных в семестре.",
        "Seminer puanlarının aritmetik ortalaması (10): dönem boyunca girilen tüm seminer puanlarının ortalaması.",
    ),
    _t(
        "Laboratoriya ballarının ədədi ortası (10): semestr ərzində yazılmış bütün laboratoriya ballarının ortası.",
        "Average of laboratory scores (10): the average of all laboratory scores recorded during the semester.",
        "Среднее арифметическое баллов за лабораторные (10): среднее всех баллов за лабораторные, выставленных "
        "в семестре.",
        "Laboratuvar puanlarının aritmetik ortalaması (10): dönem boyunca girilen tüm laboratuvar puanlarının "
        "ortalaması.",
    ),
    _t(
        "Seminar və laboratoriya: seminar ballarının ortası 5 + laboratoriya ballarının ortası 5 (cəmi 10).",
        "Seminar and laboratory: seminar score average 5 + laboratory score average 5 (10 in total).",
        "Семинар и лабораторные: среднее за семинары 5 + среднее за лабораторные 5 (всего 10).",
        "Seminer ve laboratuvar: seminer puanları ortalaması 5 + laboratuvar puanları ortalaması 5 (toplam 10).",
    ),
]

_ACCOUNTS = [
    _t(
        "Bal bölgüsü universitet standartıdır: davamiyyət 10, midterm 30, seminar/laboratoriya balları 10 "
        "(semestr 50) və yekun imtahan 50 — müəllim dəyişmir. Fəaliyyət növü dərs yükündən gəlir.",
        "The score split is a university standard: attendance 10, midterm 30, seminar/laboratory scores 10 "
        "(semester 50) and final exam 50 — the teacher does not change it. The activity type comes from the "
        "teaching load.",
        "Распределение баллов — стандарт университета: посещаемость 10, мидтерм 30, баллы за семинары/лабораторные "
        "10 (семестр 50) и итоговый экзамен 50 — преподаватель его не меняет. Вид занятий берётся из нагрузки.",
        "Puan dağılımı üniversite standardıdır: devam 10, vize 30, seminer/laboratuvar puanları 10 (dönem 50) ve "
        "final sınavı 50 — öğretim elemanı değiştirmez. Etkinlik türü ders yükünden gelir.",
    ),
    _t(
        "Bu versiya təsdiqlənib və dəyişdirilə bilmir. Elektron jurnalın mövzu siyahısı və qiymətləndirmə "
        "strukturu bu sənəddən götürülür.",
        "This version is approved and cannot be changed. The e-journal's topic list and assessment structure are "
        "taken from this document.",
        "Эта версия утверждена и не может быть изменена. Список тем электронного журнала и структура оценивания "
        "берутся из этого документа.",
        "Bu sürüm onaylandı ve değiştirilemez. E-not defterinin konu listesi ve değerlendirme yapısı bu belgeden "
        "alınır.",
    ),
    _t(
        "Təsdiqlənmiş versiya həftəlik mövzuların və qiymətləndirmə strukturunun yeganə mənbəyi olur",
        "The approved version becomes the single source for weekly topics and the assessment structure",
        "Утверждённая версия становится единственным источником еженедельных тем и структуры оценивания",
        "Onaylanan sürüm, haftalık konuların ve değerlendirme yapısının tek kaynağı olur",
    ),
    _t(
        "Həftəlik mövzular və ya qiymətləndirmə çəkiləri dəyişir. Yalnız növbəti semestrdən qüvvəyə minir — "
        "cari jurnal təsirlənmir.",
        "Weekly topics or assessment weights change. It only takes effect from the next semester — the current "
        "journal is not affected.",
        "Меняются еженедельные темы или веса оценивания. Вступает в силу только со следующего семестра — текущий "
        "журнал не затрагивается.",
        "Haftalık konular veya değerlendirme ağırlıkları değişir. Yalnızca gelecek dönemden itibaren geçerli olur "
        "— geçerli not defteri etkilenmez.",
    ),
    _t(
        "Semestr balı %(semester)s (davamiyyət + midterm + seminar/laboratoriya balları), yekun imtahan 50 — "
        "cəmi %(total)s bal. Bölgü universitet standartıdır və dəyişdirilmir.",
        "Semester score %(semester)s (attendance + midterm + seminar/laboratory scores), final exam 50 — total "
        "%(total)s points. The split is a university standard and cannot be changed.",
        "Балл за семестр %(semester)s (посещаемость + мидтерм + баллы за семинары/лабораторные), итоговый экзамен "
        "50 — всего %(total)s баллов. Распределение — стандарт университета и не меняется.",
        "Dönem puanı %(semester)s (devam + vize + seminer/laboratuvar puanları), final sınavı 50 — toplam "
        "%(total)s puan. Dağılım üniversite standardıdır ve değiştirilemez.",
    ),
]

_REGISTRAR = [
    _t(
        "Bu semestrdə sərbəst iş tətbiq olunmur — düzəliş mümkün deyil.",
        "Independent work does not apply in this semester — no correction is possible.",
        "В этом семестре самостоятельная работа не применяется — корректировка невозможна.",
        "Bu dönemde bağımsız çalışma uygulanmıyor — düzeltme yapılamaz.",
    ),
]

_HOOK = [
    _t(
        "Bu semestrdə sərbəst iş tətbiq olunmur — bal jurnala yazılmadı.",
        "Independent work does not apply in this semester — the score was not recorded in the journal.",
        "В этом семестре самостоятельная работа не применяется — балл не записан в журнал.",
        "Bu dönemde bağımsız çalışma uygulanmıyor — puan deftere yazılmadı.",
    ),
]

_FOLDER_ERRORS = [
    _t(
        "Bu semestrdə sərbəst iş tətbiq olunmur (universitet qaydası) — əməliyyat mümkün deyil.",
        "Independent work does not apply in this semester (university rule) — the action is not possible.",
        "В этом семестре самостоятельная работа не применяется (правило университета) — действие невозможно.",
        "Bu dönemde bağımsız çalışma uygulanmıyor (üniversite kuralı) — işlem yapılamaz.",
    ),
]

_FOLDER_UI = [
    _t(
        "Fənn qovluqlarına göndərilən ev tapşırıqları. Bəyənilməyən iş rəylə qaytarılır — 0 yazılmır.",
        "Homework submitted to subject folders. Unsatisfactory work is returned with feedback — no zero is "
        "recorded.",
        "Домашние задания, отправленные в папки предметов. Неудачная работа возвращается с отзывом — ноль не "
        "ставится.",
        "Ders klasörlerine gönderilen ev ödevleri. Beğenilmeyen çalışma geri bildirimle iade edilir — 0 yazılmaz.",
    ),
    _t(
        "Müəllimlərinizin paylaşdığı tədris materialları və ev tapşırıqları.",
        "Teaching materials and homework shared by your teachers.",
        "Учебные материалы и домашние задания от ваших преподавателей.",
        "Öğretmenlerinizin paylaştığı ders materyalleri ve ev ödevleri.",
    ),
    _t(
        "Mövzular təsdiqlənmiş sillabusla uzlaşdırılsın? Göndərişi olan heç nə silinmir.",
        "Sync topics with the approved syllabus? Nothing with submissions is deleted.",
        "Согласовать темы с утверждённым силлабусом? Ничего с отправками не удаляется.",
        "Konular onaylı izlenceyle eşitlensin mi? Gönderimi olan hiçbir şey silinmez.",
    ),
    _t(
        "Qovluğu tədris etdiyiniz qruplara təyin edin — tələbələr yalnız təyin olunmuş qovluğu görür.",
        "Assign the folder to the groups you teach — students only see assigned folders.",
        "Назначьте папку группам, которые вы ведёте, — студенты видят только назначенные папки.",
        "Klasörü ders verdiğiniz gruplara atayın — öğrenciler yalnızca atanan klasörü görür.",
    ),
    _t(
        "Hər fənn üçün tədris materialları və ev tapşırıqları bir qovluqda. Mövzular təsdiqlənmiş sillabusdan gəlir.",
        "Teaching materials and homework for each subject in one folder. Topics come from the approved syllabus.",
        "Учебные материалы и домашние задания по каждому предмету в одной папке. Темы берутся из утверждённого "
        "силлабуса.",
        "Her ders için ders materyalleri ve ev ödevleri tek klasörde. Konular onaylı izlenceden gelir.",
    ),
    _t(
        "«Yeni qovluq» ilə tədris etdiyiniz fənn üçün qovluq yaradın — mövzular sillabusdan avtomatik çəkiləcək.",
        "Use “New folder” to create a folder for a subject you teach — topics will be imported from the syllabus "
        "automatically.",
        "Создайте папку для своего предмета кнопкой «Новая папка» — темы подтянутся из силлабуса автоматически.",
        "“Yeni klasör” ile ders verdiğiniz ders için klasör oluşturun — konular izlenceden otomatik alınacak.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    SA: {row["az"]: row for row in _ASSESSMENT},
    AS: {row["az"]: row for row in _ACCOUNTS},
    RS: {row["az"]: row for row in _REGISTRAR},
    RH: {row["az"]: row for row in _HOOK},
    SE: {row["az"]: row for row in _FOLDER_ERRORS},
    SU: {row["az"]: row for row in _FOLDER_UI},
}

FORCE = set()


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
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
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

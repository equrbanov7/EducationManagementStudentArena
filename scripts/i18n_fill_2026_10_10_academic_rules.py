#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10: «Sistem tənzimləmələri»-ndə akademik qaydalar bayraqları (sahib «Yeni qayda var»).

Əlavə olunan mətnlər:
  * `core.runtime_settings`: «Akademik qaydalar» və «İmtahanlar» qrupları, sərbəst iş / 5+5 / «Aktivləşdir» /
    AI düyməsi / «Mövcud imtahanlar» bayraqlarının adları və izahları;
  * `accounts.runtime_settings`: açar (switch) vəziyyətləri və bayraq xətası.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_academic_rules.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AR = "accounts.runtime_settings"
CR = "core.runtime_settings"

_ACCOUNTS = [
    _t("Yanılı", "On", "Включено", "Açık"),
    _t("Söndürülü", "Off", "Выключено", "Kapalı"),
    _t(
        "Yandırılmış və ya söndürülmüş olmalıdır.",
        "Must be switched on or off.",
        "Должно быть включено или выключено.",
        "Açık veya kapalı olmalıdır.",
    ),
]

_CORE = [
    _t("Akademik qaydalar", "Academic rules", "Академические правила", "Akademik kurallar"),
    _t("İmtahanlar", "Exams", "Экзамены", "Sınavlar"),
    _t(
        "Sərbəst iş (10 bal)",
        "Independent work (10 points)",
        "Самостоятельная работа (10 баллов)",
        "Bağımsız çalışma (10 puan)",
    ),
    _t(
        "Söndürülüdə sərbəst iş jurnalda, sillabusda, fənn qovluğunda və kabinetdə görünmür, onun 10 balı "
        "midterm-ə keçir (midterm 30). Yandırılanda əvvəlki qayda: midterm 20 + sərbəst iş 10. "
        "Yalnız 2026/2027 və sonrakı semestrlərə aiddir; köhnə semestrlərin qiymətləri dəyişmir.",
        "When off, independent work is hidden in the journal, syllabus, subject folder and cabinet, and its 10 points "
        "move to the midterm (midterm 30). When on, the previous rule applies: midterm 20 + independent work 10. "
        "Applies only to 2026/2027 and later semesters; grades of earlier semesters do not change.",
        "В выключенном состоянии самостоятельная работа скрыта в журнале, силлабусе, папке предмета и кабинете, а её "
        "10 баллов переходят к промежуточному экзамену (midterm 30). Во включённом — прежнее правило: midterm 20 + "
        "самостоятельная работа 10. Действует только для семестров 2026/2027 и позже; оценки прошлых семестров не меняются.",
        "Kapalıyken bağımsız çalışma ders defterinde, izlencede, ders klasöründe ve kabinette görünmez; 10 puanı "
        "ara sınava geçer (ara sınav 30). Açıkken önceki kural geçerlidir: ara sınav 20 + bağımsız çalışma 10. "
        "Yalnızca 2026/2027 ve sonraki dönemlere uygulanır; önceki dönemlerin notları değişmez.",
    ),
    _t(
        "Seminar və laboratoriya ayrıca (5 + 5 bal)",
        "Seminar and laboratory separately (5 + 5 points)",
        "Семинар и лаборатория отдельно (5 + 5 баллов)",
        "Seminer ve laboratuvar ayrı (5 + 5 puan)",
    ),
    _t(
        "Fəndə həm seminar, həm laboratoriya varsa fəallıq balı: seminar ballarının ortası 5 + laboratoriya "
        "ballarının ortası 5. Yalnız biri varsa 10 bal onun ortasından. Söndürülüdə bütün seminar və "
        "laboratoriya balları birgə ortalanır.",
        "If a subject has both seminars and labs, the activity score is: seminar average 5 + lab average 5. "
        "If it has only one of them, all 10 points come from its average. When off, all seminar and lab scores "
        "are averaged together.",
        "Если у предмета есть и семинары, и лабораторные, балл активности: среднее по семинарам 5 + среднее по "
        "лабораторным 5. Если есть только один вид — 10 баллов из его среднего. В выключенном состоянии все "
        "оценки семинаров и лабораторных усредняются вместе.",
        "Derste hem seminer hem laboratuvar varsa etkinlik puanı: seminer ortalaması 5 + laboratuvar ortalaması 5. "
        "Yalnızca biri varsa 10 puan onun ortalamasından gelir. Kapalıyken tüm seminer ve laboratuvar puanlarının "
        "ortalaması birlikte alınır.",
    ),
    _t(
        "Cədvəldəki dərsi «Aktivləşdir» düyməsi",
        "«Activate» button for scheduled lessons",
        "Кнопка «Активировать» для занятия из расписания",
        "Programdaki ders için «Etkinleştir» düğmesi",
    ),
    _t(
        "Söndürülüdə jurnalda «Aktivləşdir» düyməsi yoxdur — müəllim «Yeni dərs» ilə dərsi özü yaradır, "
        "forma dərs cədvəli və son dərsə görə əvvəlcədən doldurulur.",
        "When off, the journal has no «Activate» button — the teacher creates the lesson with «New lesson», and the "
        "form is pre-filled from the timetable and the last lesson.",
        "В выключенном состоянии в журнале нет кнопки «Активировать» — преподаватель сам создаёт занятие через "
        "«Новое занятие», форма заранее заполняется по расписанию и последнему занятию.",
        "Kapalıyken ders defterinde «Etkinleştir» düğmesi yoktur — öğretmen dersi «Yeni ders» ile kendisi oluşturur; "
        "form ders programına ve son derse göre önceden doldurulur.",
    ),
    _t(
        "Ayrılmış tələbələrin jurnala yazılmasının qarşısını al",
        "Keep students who left out of journals",
        "Не записывать в журналы выбывших студентов",
        "Ayrılan öğrencileri ders defterlerine yazma",
    ),
    _t(
        "Yanılıdırsa hesabı arxivdə olan (məzun, xaric) tələbələr yeni jurnallara yazılmır, qrupun seçmə "
        "fənni dəyişəndə və ya fənn ləğv olunanda köhnə BOŞ yazılışlar çıxarılır. Balı olan yazılışlara "
        "toxunulmur.",
        "When on, students whose account is archived (graduated, expelled) are not enrolled in new journals, and old "
        "EMPTY enrollments are removed when a group changes its elective or a subject is cancelled. Enrollments with "
        "scores are never touched.",
        "Во включённом состоянии студенты с архивным аккаунтом (выпускники, отчисленные) не записываются в новые "
        "журналы, а старые ПУСТЫЕ записи удаляются при смене группой элективного предмета или отмене предмета. "
        "Записи с оценками не затрагиваются.",
        "Açıkken hesabı arşivde olan (mezun, kaydı silinmiş) öğrenciler yeni ders defterlerine yazılmaz; grubun "
        "seçmeli dersi değiştiğinde veya ders iptal edildiğinde eski BOŞ kayıtlar çıkarılır. Notu olan kayıtlara "
        "dokunulmaz.",
    ),
    _t("AI köməkçi düyməsi", "AI assistant button", "Кнопка ИИ-помощника", "Yapay zekâ asistanı düğmesi"),
    _t(
        "Söndürülüdə ekranın küncündəki AI düyməsi heç kimə göstərilmir. Yanılıdırsa hər istifadəçi onu öz "
        "ekranında gizlədə və sürüşdürüb yerini dəyişə bilər.",
        "When off, the AI button in the corner of the screen is shown to nobody. When on, every user can hide it on "
        "their own screen or drag it to another place.",
        "В выключенном состоянии кнопка ИИ в углу экрана никому не показывается. Во включённом каждый пользователь "
        "может скрыть её у себя или перетащить в другое место.",
        "Kapalıyken ekranın köşesindeki yapay zekâ düğmesi kimseye gösterilmez. Açıkken her kullanıcı onu kendi "
        "ekranında gizleyebilir veya sürükleyerek yerini değiştirebilir.",
    ),
    _t(
        "«Mövcud imtahanlar» səhifəsi",
        "«Available exams» page",
        "Страница «Доступные экзамены»",
        "«Mevcut sınavlar» sayfası",
    ),
    _t(
        "Sahib 2026-10-10: hələlik lazım deyil. Söndürülüdə səhifə və ona aparan keçidlər görünmür; "
        "kod saxlanılır — yandıranda geri qayıdır.",
        "Owner 2026-10-10: not needed for now. When off, the page and the links to it are hidden; the code is kept — "
        "switching it on brings it back.",
        "Владелец 2026-10-10: пока не нужна. В выключенном состоянии страница и ссылки на неё скрыты; код сохранён — "
        "при включении она возвращается.",
        "Sahip 2026-10-10: şimdilik gerekli değil. Kapalıyken sayfa ve ona giden bağlantılar gizlenir; kod "
        "korunur — açıldığında geri gelir.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    AR: {row["az"]: row for row in _ACCOUNTS},
    CR: {row["az"]: row for row in _CORE},
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

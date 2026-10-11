#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-11 (WP14): «Jurnal təmizliyi» → «Keçirilməyən fənlər» mətnləri.

Əlavə olunan mətnlər:
  * `registrar.journal_hygiene`: kateqoriya adı, səbəb / etiketlər, yarımçıq açılış xətası;
  * `accounts.journal_hygiene`: yeni tab, KPI, kömək mətni, süzgəc, JS mətnləri (json_script), yenilənmiş alt başlıq.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_11_wp14notheld.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


RH = "registrar.journal_hygiene"
AH = "accounts.journal_hygiene"

_REGISTRAR = [
    _t("Keçirilməyən fənn", "Subject not held", "Непроведённый предмет", "Yapılmamış ders"),
    _t(
        "Fənn keçirilməyib — qrupda heç kimin imtahan balı yoxdur",
        "Subject not held — nobody in the group has an exam score",
        "Предмет не проводился — ни у кого в группе нет экзаменационного балла",
        "Ders yapılmadı — grupta kimsenin sınav notu yok",
    ),
    _t("Yalnız giriş balı", "Entry score only", "Только допускной балл", "Yalnızca giriş puanı"),
    _t("Heç bir bal yoxdur", "No scores at all", "Нет ни одного балла", "Hiç puan yok"),
    _t(
        "Dərs / kollokvium izi var",
        "Lessons / colloquium recorded",
        "Есть записи занятий / коллоквиумов",
        "Ders / kolokyum kaydı var",
    ),
    _t(
        "Keçirilməyən fənn bütöv açılış kimi çıxarılır — açılışın bütün sətirlərini seçin.",
        "A subject that was not held is removed as a whole offering — select all of its rows.",
        "Непроведённый предмет убирается целиком — выберите все строки этого курса.",
        "Yapılmamış ders bütün açılış olarak çıkarılır — açılışın tüm satırlarını seçin.",
    ),
]

_ACCOUNTS = [
    _t(
        "Oxumayan, amma jurnalda adı qalan tələbələri, nəticələrə «boş» düşmüş və qrupda keçirilməmiş fənləri tapın. "
        "Heç nə silinmir: sətir dondurulur və ya nəticələrdən çıxarılır, hər qərar tarixçəyə və audit jurnalına "
        "yazılır və «Bərpa et» ilə geri qaytarılır.",
        "Find students who no longer study but remain in journals, subjects that show up «empty» in results, and "
        "subjects that were never held for a group. Nothing is deleted: a row is suspended or removed from results, "
        "every decision is written to the history and the audit log and can be undone with «Restore».",
        "Найдите студентов, которые не учатся, но остались в журналах, «пустые» предметы в результатах и предметы, "
        "не проводившиеся в группе. Ничего не удаляется: строка замораживается или убирается из результатов, каждое "
        "решение записывается в историю и журнал аудита и отменяется кнопкой «Восстановить».",
        "Okumayan ama defterde adı kalan öğrencileri, sonuçlara «boş» düşen dersleri ve grupta yapılmamış dersleri "
        "bulun. Hiçbir şey silinmez: satır dondurulur veya sonuçlardan çıkarılır, her karar geçmişe ve denetim "
        "kaydına yazılır ve «Geri yükle» ile geri alınır.",
    ),
    _t("Keçirilməyən fənlər", "Subjects not held", "Непроведённые предметы", "Yapılmamış dersler"),
    _t(
        "açılış (fənn × qrup × semestr)",
        "offerings (subject × group × semester)",
        "курсы (предмет × группа × семестр)",
        "açılış (ders × grup × dönem)",
    ),
    _t(
        "Bitmiş semestrdə qrupun HEÇ BİR tələbəsinin imtahan («çıxış») balı yoxdur — yalnız giriş balı və ya heç nə, "
        "nəticədə hamı kəsr / nəticəsiz görünür. Vahid açılışdır: bütün tələbələri birlikdə nəticələrdən çıxarılır. "
        "«Güclü siqnal» — qrupun eyni semestrdəki digər fənlərinin ən azı yarısında imtahan var və bu fənndə dərs / "
        "kollokvium izi yoxdur; «Dərs / kollokvium izi var» etiketli fənn keçirilib, amma imtahanı yazılmayıb ola "
        "bilər — əvvəlcə yoxlayın.",
        "In a finished semester NONE of the group's students has an exam («exit») score — only the entry score or "
        "nothing, so everyone appears failed / without a result. The unit is the offering: all its students are "
        "removed from results together. «Strong signal» — at least half of the group's other subjects in the same "
        "semester have exams and this subject has no lesson / colloquium records; a subject tagged «Lessons / "
        "colloquium recorded» may have been taught with its exam simply not recorded — review it first.",
        "В завершённом семестре НИ У ОДНОГО студента группы нет экзаменационного («выходного») балла — только "
        "допускной балл или ничего, поэтому все выглядят несдавшими / без результата. Единица — курс: все его "
        "студенты убираются из результатов вместе. «Сильный сигнал» — хотя бы у половины других предметов группы в "
        "том же семестре есть экзамен, а у этого предмета нет записей занятий / коллоквиумов; предмет с меткой «Есть "
        "записи занятий / коллоквиумов» мог проводиться, но экзамен не был внесён — сначала проверьте.",
        "Biten dönemde grubun HİÇBİR öğrencisinin sınav («çıkış») notu yok — yalnızca giriş puanı veya hiçbir şey, "
        "bu yüzden herkes başarısız / sonuçsuz görünür. Birim açılıştır: tüm öğrencileri sonuçlardan birlikte "
        "çıkarılır. «Güçlü sinyal» — grubun aynı dönemdeki diğer derslerinin en az yarısında sınav var ve bu derste "
        "ders / kolokyum kaydı yok; «Ders / kolokyum kaydı var» etiketli ders yapılmış ama sınavı girilmemiş "
        "olabilir — önce kontrol edin.",
    ),
    _t("Əlamət", "Sign", "Признак", "Belirti"),
    _t(
        "Bu süzgəcə uyğun keçirilməyən fənn yoxdur.",
        "No subjects not held match this filter.",
        "Нет непроведённых предметов по этому фильтру.",
        "Bu filtreye uyan yapılmamış ders yok.",
    ),
    _t("açılışda {n} tələbə", "{n} students in the offering", "студентов в курсе: {n}", "açılışta {n} öğrenci"),
    _t("açılış · {n} sətir", "offerings · {n} rows", "курсов · строк: {n}", "açılış · {n} satır"),
    _t(
        "{n} açılış yarımçıq seçilib — keçirilməyən fənn bütöv çıxarılır. "
        "Açılışın bütün tələbələrini seçin («Uyğun olanların hamısını seç»).",
        "{n} offering(s) partially selected — a subject that was not held is removed as a whole. "
        "Select all students of the offering («Select all matching»).",
        "Курсов выбрано не полностью: {n} — непроведённый предмет убирается целиком. "
        "Выберите всех студентов курса («Выбрать все подходящие»).",
        "{n} açılış eksik seçildi — yapılmamış ders bütün olarak çıkarılır. "
        "Açılışın tüm öğrencilerini seçin («Uygun olanların hepsini seç»).",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    RH: {row["az"]: row for row in _REGISTRAR},
    AH: {row["az"]: row for row in _ACCOUNTS},
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

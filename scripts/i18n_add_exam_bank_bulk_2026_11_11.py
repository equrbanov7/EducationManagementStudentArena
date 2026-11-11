#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-11: sual bankı toplu əməlləri («Bütün sualları deaktiv et / aktiv et», «Bütün N sualı
seç»), cavablanmış sualın «yeni versiya»sı və nəticələrin «Bütün N nəticəni seç» sıfırlaması.

Beş kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid (açar tipli msgid-lər üçün ayrıca AZ mətni). İdempotent.
İstifadə:  python scripts/i18n_add_exam_bank_bulk_2026_11_11.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")

_B = "exams.template.teacher_questions_bank"
_F = "exams.template.question_form"
_G = "exams.view.questions_bank.guard"
_R = "exams.attempt_reset"

# (ctx, msgid): (en, ru, tr, de)
STRINGS = {
    (_B, "Bütün %(total)s sualı seç"): (
        "Select all %(total)s questions",
        "Выбрать все вопросы (%(total)s)",
        "Tüm %(total)s soruyu seç",
        "Alle %(total)s Fragen auswählen",
    ),
    (_B, "Süzgəcə uyğun bütün {count} sual seçilib"): (
        "All {count} questions matching the filter are selected",
        "Выбраны все вопросы по фильтру: {count}",
        "Filtreye uyan tüm {count} soru seçildi",
        "Alle {count} zum Filter passenden Fragen sind ausgewählt",
    ),
    (_B, "Seçim bütün səhifələri əhatə edir."): (
        "The selection covers every page.",
        "Выбор охватывает все страницы.",
        "Seçim tüm sayfaları kapsar.",
        "Die Auswahl umfasst alle Seiten.",
    ),
    (_B, "Bütün suallar üzrə əməliyyatlar"): (
        "Actions on all questions",
        "Действия со всеми вопросами",
        "Tüm sorular için işlemler",
        "Aktionen für alle Fragen",
    ),
    (_B, "Suallar silinmir — cavablar və nəticələr qalır; istənilən vaxt geri qaytarmaq olar."): (
        "Questions are not deleted — answers and results are kept; you can undo this at any time.",
        "Вопросы не удаляются — ответы и результаты сохраняются; действие можно отменить в любой момент.",
        "Sorular silinmez — cevaplar ve sonuçlar kalır; istediğiniz zaman geri alabilirsiniz.",
        "Fragen werden nicht gelöscht — Antworten und Ergebnisse bleiben erhalten; jederzeit umkehrbar.",
    ),
    (_B, "Bütün sualları deaktiv et"): (
        "Deactivate all questions",
        "Деактивировать все вопросы",
        "Tüm soruları devre dışı bırak",
        "Alle Fragen deaktivieren",
    ),
    (_B, "Bütün sualları aktiv et"): (
        "Activate all questions",
        "Активировать все вопросы",
        "Tüm soruları etkinleştir",
        "Alle Fragen aktivieren",
    ),
    (_B, "İmtahanın bütün sualları (bütün dillər və səhifələr) deaktiv olunur — yeni cəhdlərə düşmür."): (
        "Every question of the exam (all languages and pages) is deactivated — it will not appear in new attempts.",
        "Все вопросы экзамена (все языки и страницы) деактивируются — в новые попытки они не попадают.",
        "Sınavın tüm soruları (tüm diller ve sayfalar) devre dışı kalır — yeni denemelere düşmez.",
        "Alle Fragen der Prüfung (alle Sprachen und Seiten) werden deaktiviert — sie erscheinen nicht in neuen Versuchen.",
    ),
    (_B, "Deaktiv edilmiş bütün suallar yenidən aktiv olunur."): (
        "All deactivated questions become active again.",
        "Все деактивированные вопросы снова становятся активными.",
        "Devre dışı bırakılmış tüm sorular yeniden etkinleşir.",
        "Alle deaktivierten Fragen werden wieder aktiv.",
    ),
    (_B, "İmtahanın bütün {count} sualı aktiv ediləcək. Davam edək?"): (
        "All {count} questions of the exam will be activated. Continue?",
        "Все вопросы экзамена ({count}) будут активированы. Продолжить?",
        "Sınavın tüm {count} sorusu etkinleştirilecek. Devam edilsin mi?",
        "Alle {count} Fragen der Prüfung werden aktiviert. Fortfahren?",
    ),
    (_B, "İmtahanın bütün {count} sualı deaktiv ediləcək (silinmir — cavablar və nəticələr qalır). Davam edək?"): (
        "All {count} questions of the exam will be deactivated (not deleted — answers and results are kept). Continue?",
        "Все вопросы экзамена ({count}) будут деактивированы (не удаляются — ответы и результаты сохраняются). "
        "Продолжить?",
        "Sınavın tüm {count} sorusu devre dışı bırakılacak (silinmez — cevaplar ve sonuçlar kalır). Devam edilsin mi?",
        "Alle {count} Fragen der Prüfung werden deaktiviert (nicht gelöscht — Antworten und Ergebnisse bleiben). "
        "Fortfahren?",
    ),
    (_B, "Cavablanıb"): ("Answered", "Есть ответы", "Cevaplandı", "Beantwortet"),
    (_B, "Yeni versiya"): ("New version", "Новая версия", "Yeni sürüm", "Neue Version"),
    (_B, "Dəyiş (yeni versiya)"): (
        "Change (new version)",
        "Изменить (новая версия)",
        "Değiştir (yeni sürüm)",
        "Ändern (neue Version)",
    ),
    (
        _B,
        "Bu suala tələbə cavabı və ya apellyasiya bağlıdır — silinmir, yalnız deaktiv edilir və ya yeni versiya ilə "
        "əvəzlənir.",
    ): (
        "Student answers or an appeal are attached to this question — it is not deleted, only deactivated or replaced "
        "by a new version.",
        "К этому вопросу привязаны ответы студентов или апелляция — он не удаляется, а только деактивируется или "
        "заменяется новой версией.",
        "Bu soruya öğrenci cevabı veya itiraz bağlıdır — silinmez, yalnızca devre dışı bırakılır veya yeni sürümle "
        "değiştirilir.",
        "Mit dieser Frage sind Antworten oder ein Einspruch verknüpft — sie wird nicht gelöscht, nur deaktiviert oder "
        "durch eine neue Version ersetzt.",
    ),
    (_B, "Bu sual əvvəlki (deaktiv) sualın redaktə olunmuş yeni versiyasıdır."): (
        "This question is the edited new version of an earlier (deactivated) question.",
        "Этот вопрос — отредактированная новая версия прежнего (деактивированного) вопроса.",
        "Bu soru, önceki (devre dışı) sorunun düzenlenmiş yeni sürümüdür.",
        "Diese Frage ist die bearbeitete neue Version einer früheren (deaktivierten) Frage.",
    ),
    (
        _F,
        "Bu suala artıq cavab verilib: dəyişikliyiniz YENİ VERSİYA kimi saxlanacaq — köhnə sual deaktiv olunur və "
        "keçmiş cəhdlərdə olduğu kimi qalır (ballar dəyişmir).",
    ): (
        "This question has already been answered: your change will be saved as a NEW VERSION — the old question is "
        "deactivated and stays exactly as it was in past attempts (scores do not change).",
        "На этот вопрос уже отвечали: изменение будет сохранено как НОВАЯ ВЕРСИЯ — старый вопрос деактивируется и "
        "остаётся в прошлых попытках без изменений (баллы не меняются).",
        "Bu soru zaten cevaplandı: değişikliğiniz YENİ SÜRÜM olarak kaydedilecek — eski soru devre dışı kalır ve "
        "geçmiş denemelerde olduğu gibi durur (puanlar değişmez).",
        "Diese Frage wurde bereits beantwortet: Ihre Änderung wird als NEUE VERSION gespeichert — die alte Frage wird "
        "deaktiviert und bleibt in früheren Versuchen unverändert (Punkte ändern sich nicht).",
    ),
    (_F, "Keçmiş cəhdlərdə düzgün cavabı dəyişmək üçün — «Cavab açarı düzəlişi» (apellyasiyalar)."): (
        "To change the correct answer for past attempts — “Answer key correction” (appeals).",
        "Чтобы изменить правильный ответ в прошлых попытках — «Исправление ключа ответов» (апелляции).",
        "Geçmiş denemelerde doğru cevabı değiştirmek için — «Cevap anahtarı düzeltmesi» (itirazlar).",
        "Um die richtige Antwort für frühere Versuche zu ändern — „Korrektur des Antwortschlüssels“ (Einsprüche).",
    ),
    (
        "exams.view.questions.version",
        "Sualın yeni versiyası yaradıldı. Köhnə sual deaktiv edildi — keçmiş cəhdlərdə olduğu kimi qalır, ballar "
        "dəyişmədi.",
    ): (
        "A new version of the question was created. The old question was deactivated — it stays as it was in past "
        "attempts; scores did not change.",
        "Создана новая версия вопроса. Старый вопрос деактивирован — в прошлых попытках он остаётся без изменений, "
        "баллы не изменились.",
        "Sorunun yeni sürümü oluşturuldu. Eski soru devre dışı bırakıldı — geçmiş denemelerde olduğu gibi kalır, "
        "puanlar değişmedi.",
        "Eine neue Version der Frage wurde erstellt. Die alte Frage wurde deaktiviert — sie bleibt in früheren "
        "Versuchen unverändert; die Punkte haben sich nicht geändert.",
    ),
    (_G, "İstifadə olunmuş suallar silinmir"): (
        "Used questions are not deleted",
        "Использованные вопросы не удаляются",
        "Kullanılmış sorular silinmez",
        "Verwendete Fragen werden nicht gelöscht",
    ),
    (_G, "Bəli, deaktiv et"): ("Yes, deactivate", "Да, деактивировать", "Evet, devre dışı bırak", "Ja, deaktivieren"),
    (
        _G,
        "Seçilmiş suallardan {used}-i istifadə olunub (tələbə cavabı var) və silinə bilməz. Onlar deaktiv edilsin, "
        "qalan {unused} sual silinsin?",
    ): (
        "{used} of the selected questions have been used (students answered them) and cannot be deleted. Deactivate "
        "them and delete the remaining {unused}?",
        "Из выбранных вопросов использовано: {used} (есть ответы студентов) — их нельзя удалить. Деактивировать их, "
        "а остальные ({unused}) удалить?",
        "Seçilen sorulardan {used} tanesi kullanılmış (öğrenci cevabı var) ve silinemez. Bunlar devre dışı bırakılsın, "
        "kalan {unused} soru silinsin mi?",
        "{used} der ausgewählten Fragen wurden verwendet (es gibt Antworten) und können nicht gelöscht werden. Diese "
        "deaktivieren und die übrigen {unused} löschen?",
    ),
    (_G, "İstifadə olunmuş {used} sual silinə bilməz — deaktiv edilsin? Cavablar və nəticələr qalır."): (
        "{used} used question(s) cannot be deleted — deactivate instead? Answers and results are kept.",
        "Использованные вопросы ({used}) нельзя удалить — деактивировать? Ответы и результаты сохраняются.",
        "Kullanılmış {used} soru silinemez — devre dışı bırakılsın mı? Cevaplar ve sonuçlar kalır.",
        "{used} verwendete Frage(n) können nicht gelöscht werden — stattdessen deaktivieren? Antworten und Ergebnisse "
        "bleiben erhalten.",
    ),
    (_G, "İstifadə olunmuş {count} sual silinmədi — deaktiv edildi (cavablar və nəticələr qalır)."): (
        "{count} used question(s) were not deleted — they were deactivated (answers and results are kept).",
        "Использованные вопросы ({count}) не удалены — они деактивированы (ответы и результаты сохраняются).",
        "Kullanılmış {count} soru silinmedi — devre dışı bırakıldı (cevaplar ve sonuçlar kalır).",
        "{count} verwendete Frage(n) wurden nicht gelöscht — sie wurden deaktiviert (Antworten und Ergebnisse bleiben).",
    ),
    (_R, "Səhifədəkilərin hamısını seç"): (
        "Select everything on this page",
        "Выбрать все на странице",
        "Sayfadakilerin tümünü seç",
        "Alle auf dieser Seite auswählen",
    ),
    (_R, "Bütün %(total)s nəticəni seç"): (
        "Select all %(total)s results",
        "Выбрать все результаты (%(total)s)",
        "Tüm %(total)s sonucu seç",
        "Alle %(total)s Ergebnisse auswählen",
    ),
    (
        _R,
        "Seçim cari süzgəcə uyğun BÜTÜN nəticələri əhatə edir (bütün səhifələr) — yalnız bu səhifədə görünənləri yox.",
    ): (
        "The selection covers ALL results matching the current filter (every page) — not only the ones shown on "
        "this page.",
        "Выбор охватывает ВСЕ результаты по текущему фильтру (все страницы), а не только показанные на этой странице.",
        "Seçim, geçerli filtreye uyan TÜM sonuçları (tüm sayfalar) kapsar — yalnızca bu sayfada görünenleri değil.",
        "Die Auswahl umfasst ALLE Ergebnisse des aktuellen Filters (alle Seiten) — nicht nur die auf dieser Seite.",
    ),
    (
        _R,
        "Siyahı dəyişib: təsdiqlədiyiniz %(expected)s nəticə əvəzinə indi %(actual)s nəticə uyğundur. Heç nə silinmədi "
        "— səhifəni yoxlayıb yenidən cəhd edin.",
    ): (
        "The list has changed: instead of the %(expected)s results you confirmed, %(actual)s now match. Nothing was "
        "deleted — check the page and try again.",
        "Список изменился: вместо подтверждённых %(expected)s результатов сейчас подходит %(actual)s. Ничего не "
        "удалено — проверьте страницу и повторите.",
        "Liste değişti: onayladığınız %(expected)s sonuç yerine şimdi %(actual)s sonuç uyuyor. Hiçbir şey silinmedi — "
        "sayfayı kontrol edip yeniden deneyin.",
        "Die Liste hat sich geändert: statt der bestätigten %(expected)s Ergebnisse passen jetzt %(actual)s. Nichts "
        "wurde gelöscht — Seite prüfen und erneut versuchen.",
    ),
}

# Açar tipli msgid (AZ mətni msgid-dən fərqlidir): (az, en, ru, tr, de)
KEYED = {
    ("exams.model.question.field", "replaces"): (
        "Əvəz etdiyi sual",
        "Replaces question",
        "Заменяет вопрос",
        "Yerine geçtiği soru",
        "Ersetzt Frage",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        for (ctx, msgid), (az, en, ru, tr, de) in KEYED.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": az, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()

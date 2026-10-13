#!/usr/bin/env python3
"""EMSArena i18n — apellyasiya gecə paketi 2026-10-13 (`appeals`).

Əlavə olunan mətnlər:
  * cavab açarı düzəlişi (bütün tələbələr üçün) — forma, kart, xəta və bildiriş mətnləri;
  * apellyasiya son tarixi («Apellyasiya son tarixi: …») — yaratma səhifəsi, «Apellyasiyalarım», nəticə səhifəsi;
  * qərar modalında tarixçə və müqayisə etiketləri;
  * «Akademik qeydlər» çekməcəsində imtahan cəhdləri + apellyasiya izi (dekan/koordinator);
  * «Sistem tənzimləmələri»: `exam.appeal_window_days`.

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir.
Sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_appeals_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

NOTE = "appeals.notification"
KEYERR = "appeals.service.key_correction.error"
VIEW = "appeals.view.message"
HIST = "appeals.history"
TPL = "appeals.template"
RESULT = "exams.template.student_exam_result"
RECORDS = "registrar.records"
RUNTIME = "core.runtime_settings"


def t(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


DEADLINE = "Apellyasiya son tarixi: %(deadline)s"
DEADLINE_T = t(
    "Appeal deadline: %(deadline)s", "Крайний срок апелляции: %(deadline)s", "İtiraz son tarihi: %(deadline)s"
)

# ctx → msgid → {lang: msgstr}.
ENTRIES = {
    RUNTIME: {
        "Apellyasiya müddəti": t("Appeal period", "Срок подачи апелляции", "İtiraz süresi"),
        (
            "Nəticə tələbəyə açıldıqdan sonra neçə təqvim günü apellyasiya vermək olar (son günün sonunadək, "
            "Bakı vaxtı). Tələbə evdən də müraciət edə bilir; müddət bitəndə düymə gizlənir və server qəbul etmir."
        ): t(
            "How many calendar days after the result is released a student may appeal (until the end of the last "
            "day, Baku time). Students can also appeal from home; when the period ends the button disappears and "
            "the server refuses.",
            "Сколько календарных дней после публикации результата студент может подать апелляцию (до конца "
            "последнего дня, по бакинскому времени). Подать можно и из дома; по истечении срока кнопка скрывается, "
            "а сервер не принимает заявку.",
            "Sonuç öğrenciye açıldıktan sonra kaç takvim günü itiraz edilebilir (son günün sonuna kadar, Bakü "
            "saati). Öğrenci evden de başvurabilir; süre dolunca düğme gizlenir ve sunucu kabul etmez.",
        ),
        "gün": t("days", "дн.", "gün sayısı"),
    },
    NOTE: {
        "Midterm balını elektron jurnalda özünüz yeniləyin (midterm jurnala avtomatik yazılmır).": t(
            "Please update the midterm score in the e-journal yourself (midterm is not written automatically).",
            "Обновите балл промежуточного экзамена в электронном журнале сами (он не записывается автоматически).",
            "Ara sınav puanını e-dersdefterinde kendiniz güncelleyin (ara sınav otomatik yazılmaz).",
        ),
        "Elektron jurnalda imtahan balı avtomatik yeniləndi.": t(
            "The exam score in the e-journal was updated automatically.",
            "Балл экзамена в электронном журнале обновлён автоматически.",
            "E-dersdefterindeki sınav puanı otomatik olarak güncellendi.",
        ),
        "Apellyasiya nəticəsində bal dəyişdi": t(
            "Score changed after an appeal", "Балл изменён по итогам апелляции", "İtiraz sonucunda puan değişti"
        ),
        '{student} — "{exam}": apellyasiya qəbul olundu, bal {delta} dəyişdi. {hint}': t(
            '{student} — "{exam}": the appeal was accepted, score changed by {delta}. {hint}',
            "{student} — «{exam}»: апелляция принята, балл изменён на {delta}. {hint}",
            '{student} — "{exam}": itiraz kabul edildi, puan {delta} değişti. {hint}',
        ),
        "Cavab açarı düzəlişi geri alındı": t(
            "Answer key correction revoked",
            "Исправление ключа ответов отменено",
            "Cevap anahtarı düzeltmesi geri alındı",
        ),
        '"{exam}" imtahanının {no}-ci sualı üzrə açar düzəlişi geri alındı — əlavə bal çıxarıldı.': t(
            'The key correction for question {no} of "{exam}" was revoked — the extra point was removed.',
            "Исправление ключа к вопросу {no} экзамена «{exam}» отменено — дополнительный балл снят.",
            '"{exam}" sınavının {no}. sorusundaki anahtar düzeltmesi geri alındı — ek puan çıkarıldı.',
        ),
        "Cavab açarı düzəldildi": t("Answer key corrected", "Ключ ответов исправлен", "Cevap anahtarı düzeltildi"),
        '"{exam}" imtahanının {no}-ci sualının cavab açarı düzəldildi — balınız artırıldı.': t(
            'The answer key for question {no} of "{exam}" was corrected — your score was increased.',
            "Ключ ответа к вопросу {no} экзамена «{exam}» исправлен — ваш балл повышен.",
            '"{exam}" sınavının {no}. sorusunun cevap anahtarı düzeltildi — puanınız artırıldı.',
        ),
        "Cavab açarı düzəlişi": t("Answer key correction", "Исправление ключа ответов", "Cevap anahtarı düzeltmesi"),
        '"{exam}" imtahanının {no}-ci sualı üzrə açar {action}: {count} tələbənin balı dəyişdi. {hint}': t(
            'Answer key for question {no} of "{exam}" {action}: {count} students\' scores changed. {hint}',
            "Ключ к вопросу {no} экзамена «{exam}» {action}: баллы {count} студентов изменились. {hint}",
            '"{exam}" sınavının {no}. sorusunun anahtarı {action}: {count} öğrencinin puanı değişti. {hint}',
        ),
        "düzəlişi geri alındı": t("correction revoked", "исправление отменено", "düzeltmesi geri alındı"),
        "düzəldildi": t("corrected", "исправлен", "düzeltildi"),
    },
    KEYERR: {
        "Düzgün variant seçimi yanlışdır.": t(
            "The correct-option selection is invalid.",
            "Неверный выбор правильного варианта.",
            "Doğru seçenek seçimi geçersiz.",
        ),
        "Ən azı bir düzgün variant seçin.": t(
            "Select at least one correct option.",
            "Выберите хотя бы один правильный вариант.",
            "En az bir doğru seçenek seçin.",
        ),
        "Seçilən variant bu suala aid deyil.": t(
            "The selected option does not belong to this question.",
            "Выбранный вариант не относится к этому вопросу.",
            "Seçilen seçenek bu soruya ait değil.",
        ),
        "Açar düzəlişinin səbəbini yazın (ən azı {n} simvol).": t(
            "Write the reason for the key correction (at least {n} characters).",
            "Укажите причину исправления ключа (не менее {n} символов).",
            "Anahtar düzeltmesinin gerekçesini yazın (en az {n} karakter).",
        ),
        "Səbəb {n} simvoldan uzun ola bilməz.": t(
            "The reason cannot be longer than {n} characters.",
            "Причина не может быть длиннее {n} символов.",
            "Gerekçe {n} karakterden uzun olamaz.",
        ),
        "Açar düzəlişi yalnız test (variantlı) suallar üçündür.": t(
            "Key correction is only for multiple-choice (test) questions.",
            "Исправление ключа возможно только для тестовых вопросов с вариантами.",
            "Anahtar düzeltmesi yalnızca çoktan seçmeli (test) sorular içindir.",
        ),
        "Bu sual üçün aktiv açar düzəlişi artıq var — əvvəlcə onu geri alın.": t(
            "This question already has an active key correction — revoke it first.",
            "Для этого вопроса уже есть активное исправление ключа — сначала отмените его.",
            "Bu soru için zaten etkin bir anahtar düzeltmesi var — önce onu geri alın.",
        ),
        "Yeni açar köhnə açarla eynidir — düzəliş lazım deyil.": t(
            "The new key is the same as the old one — no correction needed.",
            "Новый ключ совпадает со старым — исправление не требуется.",
            "Yeni anahtar eskisiyle aynı — düzeltme gerekmiyor.",
        ),
        "Bu açar düzəlişi artıq geri alınıb.": t(
            "This key correction has already been revoked.",
            "Это исправление ключа уже отменено.",
            "Bu anahtar düzeltmesi zaten geri alınmış.",
        ),
    },
    VIEW: {
        "Apellyasiya tapılmadı.": t("Appeal not found.", "Апелляция не найдена.", "İtiraz bulunamadı."),
        "Cavab açarı düzəldildi: sualı cavablayan {affected} tələbədən {credited} nəfərin balı artırıldı.": t(
            "Answer key corrected: {credited} of {affected} students who answered the question got extra credit.",
            "Ключ исправлен: из {affected} студентов, ответивших на вопрос, балл повышен у {credited}.",
            "Cevap anahtarı düzeltildi: soruyu yanıtlayan {affected} öğrenciden {credited} kişinin puanı artırıldı.",
        ),
        "Açar düzəlişi geri alındı.": t(
            "Key correction revoked.", "Исправление ключа отменено.", "Anahtar düzeltmesi geri alındı."
        ),
    },
    HIST: {
        "Cavab açarı düzəlişi geri alındı": t(
            "Answer key correction revoked", "Исправление ключа отменено", "Cevap anahtarı düzeltmesi geri alındı"
        ),
        "Cavab açarı düzəldildi (hamı üçün)": t(
            "Answer key corrected (for everyone)",
            "Ключ ответов исправлен (для всех)",
            "Cevap anahtarı düzeltildi (herkes için)",
        ),
        "Yekun (final)": t("Final", "Итоговый (final)", "Final (dönem sonu)"),
        "Aralıq (midterm)": t("Midterm", "Промежуточный (midterm)", "Ara sınav (midterm)"),
        "Apellyasiya göndərildi ({count} sual)": t(
            "Appeal submitted ({count} questions)",
            "Апелляция подана ({count} вопр.)",
            "İtiraz gönderildi ({count} soru)",
        ),
        "{no}-ci sual: {status}": t("Question {no}: {status}", "Вопрос {no}: {status}", "{no}. soru: {status}"),
        "{no}-ci sual: bal düzəlişi geri alındı": t(
            "Question {no}: score adjustment revoked",
            "Вопрос {no}: корректировка балла отменена",
            "{no}. soru: puan düzeltmesi geri alındı",
        ),
        "{no}-ci sual: +{delta} bal": t(
            "Question {no}: +{delta} pt", "Вопрос {no}: +{delta} балл", "{no}. soru: +{delta} puan"
        ),
        "{no}-ci sual: cavab açarı düzəldildi — {credited}/{affected} tələbəyə kredit": t(
            "Question {no}: answer key corrected — credit to {credited}/{affected} students",
            "Вопрос {no}: ключ исправлен — балл начислен {credited}/{affected} студентам",
            "{no}. soru: cevap anahtarı düzeltildi — {credited}/{affected} öğrenciye puan",
        ),
        "{no}-ci sual: açar düzəlişi geri alındı": t(
            "Question {no}: key correction revoked",
            "Вопрос {no}: исправление ключа отменено",
            "{no}. soru: anahtar düzeltmesi geri alındı",
        ),
    },
    TPL: {
        "Variantlar — tələbənin gördüyü kimi": t(
            "Options — as the student saw them",
            "Варианты — как их видел студент",
            "Seçenekler — öğrencinin gördüğü gibi",
        ),
        "Açar (imtahan anında)": t("Key (at exam time)", "Ключ (на момент экзамена)", "Anahtar (sınav anında)"),
        "Düzəldilmiş açar": t("Corrected key", "Исправленный ключ", "Düzeltilmiş anahtar"),
        "Cavab yazılmayıb": t("No answer written", "Ответ не написан", "Cevap yazılmamış"),
        "Yoxlayanın balı": t("Grader's score", "Балл проверяющего", "Değerlendiren puanı"),
        "İdeal cavab (imtahan anında)": t(
            "Model answer (at exam time)", "Эталонный ответ (на момент экзамена)", "Örnek cevap (sınav anında)"
        ),
        "Cavab açarı düzəldilib (bütün tələbələr üçün)": t(
            "Answer key has been corrected (for all students)",
            "Ключ ответов исправлен (для всех студентов)",
            "Cevap anahtarı düzeltildi (tüm öğrenciler için)",
        ),
        "Sualı cavablayan %(affected)s tələbədən %(credited)s nəfərə kredit verildi.": t(
            "%(credited)s of %(affected)s students who answered the question received credit.",
            "Из %(affected)s студентов, ответивших на вопрос, балл получили %(credited)s.",
            "Soruyu yanıtlayan %(affected)s öğrenciden %(credited)s kişiye puan verildi.",
        ),
        "Geri alma səbəbi": t("Reason for revoking", "Причина отмены", "Geri alma gerekçesi"),
        "Açar düzəlişini geri almaq?": t(
            "Revoke the key correction?", "Отменить исправление ключа?", "Anahtar düzeltmesi geri alınsın mı?"
        ),
        "Bu düzəlişlə verilmiş bütün əlavə ballar geri götürüləcək və tələbələrə bildiriş gedəcək. Qeyd tarixçədə qalır.": t(
            "All extra points granted by this correction will be removed and students will be notified. "
            "The record stays in the history.",
            "Все дополнительные баллы по этому исправлению будут сняты, студенты получат уведомление. "
            "Запись остаётся в истории.",
            "Bu düzeltmeyle verilen tüm ek puanlar geri alınacak ve öğrencilere bildirim gidecek. Kayıt geçmişte kalır.",
        ),
        "Düzəlişi geri al": t("Revoke correction", "Отменить исправление", "Düzeltmeyi geri al"),
        "Ən azı bir düzgün variant seçin.": t(
            "Select at least one correct option.",
            "Выберите хотя бы один правильный вариант.",
            "En az bir doğru seçenek seçin.",
        ),
        "Açar düzəlişinin səbəbini yazın.": t(
            "Write the reason for the key correction.",
            "Укажите причину исправления ключа.",
            "Anahtar düzeltmesinin gerekçesini yazın.",
        ),
        "Cavab açarını hamı üçün düzəltmək?": t(
            "Correct the answer key for everyone?",
            "Исправить ключ ответов для всех?",
            "Cevap anahtarı herkes için düzeltilsin mi?",
        ),
        (
            "Bu imtahanda bu sualı yeni açara uyğun cavablayan HƏR tələbənin balı artırılacaq, jurnal yenilənəcək "
            "və bildiriş gedəcək. Heç kimin balı azalmır. Əməliyyat audit olunur."
        ): t(
            "EVERY student in this exam whose answer to this question matches the new key will get extra credit, "
            "the journal will be updated and notifications sent. Nobody's score goes down. The action is audited.",
            "КАЖДОМУ студенту этого экзамена, чей ответ на этот вопрос совпадает с новым ключом, будет начислен "
            "балл, журнал обновится, уйдут уведомления. Ничей балл не снижается. Действие фиксируется в аудите.",
            "Bu sınavda bu soruyu yeni anahtara uygun yanıtlayan HER öğrencinin puanı artırılacak, dersdefteri "
            "güncellenecek ve bildirim gidecek. Kimsenin puanı düşmez. İşlem denetim kaydına alınır.",
        ),
        "Açar səhvdir? Bütün tələbələr üçün düzəlt": t(
            "Key is wrong? Correct it for all students",
            "Ключ неверен? Исправить для всех студентов",
            "Anahtar yanlış mı? Tüm öğrenciler için düzelt",
        ),
        (
            "«Qəbul et» yalnız bu tələbəyə +1 verir. Açar özü səhvdirsə, düzgün variant(lar)ı seçin — sualı həmin "
            "variantla cavablayan hər kəs eyni krediti alır."
        ): t(
            '"Accept" gives +1 only to this student. If the key itself is wrong, select the correct option(s) — '
            "everyone who chose that option gets the same credit.",
            "«Принять» даёт +1 только этому студенту. Если неверен сам ключ, выберите правильный вариант(ы) — "
            "все, кто выбрал этот вариант, получат такой же балл.",
            '"Kabul et" yalnızca bu öğrenciye +1 verir. Anahtarın kendisi yanlışsa doğru seçeneği/seçenekleri '
            "seçin — o seçeneği işaretleyen herkes aynı puanı alır.",
        ),
        "Düzgün variant(lar)": t("Correct option(s)", "Правильный вариант(ы)", "Doğru seçenek(ler)"),
        "köhnə açar": t("old key", "старый ключ", "eski anahtar"),
        "Səbəb (audit üçün)": t("Reason (for the audit)", "Причина (для аудита)", "Gerekçe (denetim için)"),
        "Məs.: B variantı da düzgündür — mənbə: dərslik, 4.2": t(
            "E.g.: option B is also correct — source: textbook, 4.2",
            "Напр.: вариант B тоже верен — источник: учебник, 4.2",
            "Örn.: B seçeneği de doğru — kaynak: ders kitabı, 4.2",
        ),
        "Açarı düzəlt və balları yenilə": t(
            "Correct the key and update scores",
            "Исправить ключ и обновить баллы",
            "Anahtarı düzelt ve puanları güncelle",
        ),
        "Tarixçə": t("History", "История", "Geçmiş"),
        DEADLINE: DEADLINE_T,
        "Nəticə açıqlandıqdan sonra %(days)s təqvim günü ərzində (son günün sonunadək, Bakı vaxtı) müraciət edə bilərsiniz.": t(
            "You can appeal within %(days)s calendar days after the result is released (until the end of the last "
            "day, Baku time).",
            "Подать апелляцию можно в течение %(days)s календарных дней после публикации результата (до конца "
            "последнего дня, по бакинскому времени).",
            "Sonuç açıklandıktan sonra %(days)s takvim günü içinde (son günün sonuna kadar, Bakü saati) itiraz "
            "edebilirsiniz.",
        ),
        (
            "Nəticə açıqlandıqdan sonra %(days)s təqvim günü ərzində (son günün sonunadək, Bakı vaxtı) müraciət edə "
            "bilərsiniz — evdən də."
        ): t(
            "You can appeal within %(days)s calendar days after the result is released (until the end of the last "
            "day, Baku time) — from home too.",
            "Подать апелляцию можно в течение %(days)s календарных дней после публикации результата (до конца "
            "последнего дня, по бакинскому времени) — в том числе из дома.",
            "Sonuç açıklandıktan sonra %(days)s takvim günü içinde (son günün sonuna kadar, Bakü saati) itiraz "
            "edebilirsiniz — evden de.",
        ),
    },
    RESULT: {DEADLINE: DEADLINE_T},
    RECORDS: {
        "İmtahan cəhdləri və apellyasiyalar": t(
            "Exam attempts and appeals", "Попытки экзаменов и апелляции", "Sınav denemeleri ve itirazlar"
        ),
        "cəhd": t("attempt", "попытка", "deneme"),
        "rəsmi": t("official", "официальная", "resmî"),
        "ləğv olundu": t("superseded", "аннулирована", "geçersiz kılındı"),
        "nəzarətçi tərəfindən çıxarılıb": t(
            "removed by the invigilator", "удалён наблюдателем", "gözetmen tarafından çıkarıldı"
        ),
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        if os.path.isdir(os.path.join(BASE, "locale", locale)):
            fill(locale)

#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-08: müəllim rəyi (imtahan sehrbazı, sual göndərişləri, sual bankı, dərs yükü).

Yeni mətnlər:
* E1 — `core.datetime_input`: locale-dən asılı olmayan «gg.aa.iiii ss:dd» tarix-saat sahəsi
  (xəta mesajları, seçici düymələri). Ay/gün adları Django-nun öz kataloqundandır.
* E2 — sehrbaz/formalarda gettext-siz qalan mətnlər (sual sayı köməkçisi «0 yazsanız…»,
  praktiki imtahan / nəzarət deaktiv mesajları, «Variant N») və qeyri-rəsmi «seç» → «seçin».

Mənbə dili AZ-dır (msgid = AZ mətn). ⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir;
sonra `.mo` faylları `msgfmt` ilə yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_08_teacher_feedback.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

# (kontekst, az) → (en, ru, tr)
ROWS = {
    "core.datetime_input": {
        "Tarixi və saatı gg.aa.iiii ss:dd formatında yazın (məsələn, 06.10.2026 09:30).": (
            "Enter the date and time as dd.mm.yyyy hh:mm (for example, 06.10.2026 09:30).",
            "Введите дату и время в формате дд.мм.гггг чч:мм (например, 06.10.2026 09:30).",
            "Tarihi ve saati gg.aa.yyyy ss:dd biçiminde yazın (örneğin 06.10.2026 09:30).",
        ),
        "Belə tarix yoxdur. Günü, ayı və ili yoxlayın (gg.aa.iiii).": (
            "This date does not exist. Check the day, month and year (dd.mm.yyyy).",
            "Такой даты не существует. Проверьте день, месяц и год (дд.мм.гггг).",
            "Böyle bir tarih yok. Günü, ayı ve yılı kontrol edin (gg.aa.yyyy).",
        ),
        "Saat 00:00 ilə 23:59 arasında olmalıdır (24 saat formatı).": (
            "The time must be between 00:00 and 23:59 (24-hour format).",
            "Время должно быть от 00:00 до 23:59 (24-часовой формат).",
            "Saat 00:00 ile 23:59 arasında olmalıdır (24 saat biçimi).",
        ),
        "Saatı da yazın (ss:dd, 24 saat formatı).": (
            "Add the time as well (hh:mm, 24-hour format).",
            "Укажите и время (чч:мм, 24-часовой формат).",
            "Saati de yazın (ss:dd, 24 saat biçimi).",
        ),
        "gg.aa.iiii ss:dd": ("dd.mm.yyyy hh:mm", "дд.мм.гггг чч:мм", "gg.aa.yyyy ss:dd"),
        "Format: gg.aa.iiii ss:dd (24 saat)": (
            "Format: dd.mm.yyyy hh:mm (24-hour)",
            "Формат: дд.мм.гггг чч:мм (24 часа)",
            "Biçim: gg.aa.yyyy ss:dd (24 saat)",
        ),
        "Təqvimi aç": ("Open calendar", "Открыть календарь", "Takvimi aç"),
        "Tarix və saatı seçin": ("Choose the date and time", "Выберите дату и время", "Tarih ve saati seçin"),
        "Əvvəlki ay": ("Previous month", "Предыдущий месяц", "Önceki ay"),
        "Növbəti ay": ("Next month", "Следующий месяц", "Sonraki ay"),
        "Saatı seçin": ("Choose the hour", "Выберите час", "Saati seçin"),
        "Dəqiqəni seçin": ("Choose the minute", "Выберите минуты", "Dakikayı seçin"),
        "Bu gün": ("Today", "Сегодня", "Bugün"),
        "Hazırdır": ("Done", "Готово", "Tamam"),
    },
    # E2 — sehrbaz/formalarda gettext-siz və ya qeyri-rəsmi qalan mətnlər.
    "exams.form.exam.help": {
        "0 yazsanız, bütün aktiv suallar düşəcək. Boş qalarsa, standart olaraq 10 sual götürülür. "
        "Test, yazılı və praktiki imtahanlara aiddir.": (
            "Enter 0 to include all active questions. If left empty, 10 questions are used by default. "
            "Applies to test, written and practical exams.",
            "Укажите 0, чтобы включить все активные вопросы. Если оставить поле пустым, по умолчанию "
            "берётся 10 вопросов. Относится к тестовым, письменным и практическим экзаменам.",
            "Tüm aktif soruların dahil edilmesi için 0 yazın. Boş bırakılırsa varsayılan olarak 10 soru "
            "alınır. Test, yazılı ve uygulamalı sınavlar için geçerlidir.",
        ),
    },
    "exams.template.create_exam_modal_form": {
        "İmtahanın kateqoriyasını seçin: Sınaq, Midterm və ya Final.": (
            "Choose the exam category: Quiz, Midterm or Final.",
            "Выберите категорию экзамена: пробный, Midterm или Final.",
            "Sınav kategorisini seçin: Deneme, Midterm veya Final.",
        ),
    },
    "exams.features": {
        "Praktiki imtahan hazırda production mühitində deaktivdir.": (
            "Practical exams are currently disabled in production.",
            "Практические экзамены сейчас отключены в рабочей среде.",
            "Uygulamalı sınavlar şu anda canlı ortamda devre dışı.",
        ),
        "İmtahan nəzarəti production mühitində deaktivdir.": (
            "Exam supervision is disabled in production.",
            "Наблюдение за экзаменами отключено в рабочей среде.",
            "Sınav gözetimi canlı ortamda devre dışı.",
        ),
    },
    "exams.form.question.label": {
        "Variant %(n)s": ("Option %(n)s", "Вариант %(n)s", "Seçenek %(n)s"),
    },
    # S2 — sual göndərişi: fənn/qrup dərs yükündən; boşdursa «niyə».
    "exams.service.submission_sources": {
        "Təşkilatda cari semestr təyin olunmayıb — fənlər dərs yükünüzdən göstərilə bilmir.": (
            "No current semester is set for the organisation, so subjects cannot be shown from your teaching load.",
            "В организации не задан текущий семестр — дисциплины из вашей нагрузки показать нельзя.",
            "Kurumda geçerli dönem tanımlanmamış; dersler ders yükünüzden gösterilemiyor.",
        ),
        "Bu fənlər dərs yükünüzdə var, amma fənn kataloquna bağlanmayıb: {names}. Kafedraya müraciət edin.": (
            "These subjects are in your teaching load but are not linked to the subject catalogue: {names}. "
            "Please contact your department.",
            "Эти дисциплины есть в вашей нагрузке, но не привязаны к каталогу дисциплин: {names}. "
            "Обратитесь на кафедру.",
            "Bu dersler ders yükünüzde var ancak ders kataloğuna bağlanmamış: {names}. Bölüme başvurun.",
        ),
        "Dərs yükünüz kafedra tərəfindən hələ təsdiqlənməyib — təsdiqdən sonra fənləriniz burada görünəcək.": (
            "Your teaching load has not been approved by the department yet; your subjects will appear here "
            "after approval.",
            "Ваша нагрузка ещё не утверждена кафедрой — после утверждения дисциплины появятся здесь.",
            "Ders yükünüz bölüm tarafından henüz onaylanmadı; onaydan sonra dersleriniz burada görünecek.",
        ),
        "Cari semestrdə ({period}) dərs yükünüz yoxdur. Fənlər yalnız cari semestr üzrə göstərilir.": (
            "You have no teaching load in the current semester ({period}). Only current-semester subjects are shown.",
            "В текущем семестре ({period}) у вас нет нагрузки. Показываются только дисциплины текущего семестра.",
            "Geçerli dönemde ({period}) ders yükünüz yok. Yalnızca geçerli dönemin dersleri gösterilir.",
        ),
        "Cari semestrdə ({period}) sizin adınıza təsdiqlənmiş dərs yükü və ya jurnal tapılmadı. "
        "Fənlər dərs yükündən gəlir — fənn qovluğu yaratmaq lazım deyil; kafedra müdirinə müraciət edin.": (
            "No approved teaching load or journal was found for you in the current semester ({period}). "
            "Subjects come from the teaching load — creating a subject folder is not required; "
            "please contact the head of department.",
            "В текущем семестре ({period}) для вас не найдены утверждённая нагрузка или журнал. "
            "Дисциплины берутся из нагрузки — создавать папку дисциплины не нужно; обратитесь к заведующему кафедрой.",
            "Geçerli dönemde ({period}) adınıza onaylanmış ders yükü veya not defteri bulunamadı. "
            "Dersler ders yükünden gelir; ders klasörü oluşturmanız gerekmez, bölüm başkanına başvurun.",
        ),
    },
    "exams.template.question_submission": {
        "Cari semestr üzrə dərs yükünüzdəki fənlər görünür.": (
            "Subjects from your teaching load for the current semester are shown.",
            "Показаны дисциплины из вашей нагрузки на текущий семестр.",
            "Geçerli dönem ders yükünüzdeki dersler gösterilir.",
        ),
        "Cari semestrin dərs yükündə sizə bağlı qrup tapılmadı — kafedra müdirinə müraciət edin.": (
            "No groups are linked to you in the current semester's teaching load; please contact the head of "
            "department.",
            "В нагрузке текущего семестра нет привязанных к вам групп — обратитесь к заведующему кафедрой.",
            "Geçerli dönemin ders yükünde size bağlı grup bulunamadı; bölüm başkanına başvurun.",
        ),
    },
    # W1 — «Dərs yüküm» cədvəlinin «CƏMİ» xanası görünən sətirlərin cəmidir.
    "accounts.workload": {
        "CƏMİ (bütün semestrlər)": ("TOTAL (all semesters)", "ИТОГО (все семестры)", "TOPLAM (tüm dönemler)"),
        "CƏMİ — {season} semestri": (
            "TOTAL — {season} semester",
            "ИТОГО — семестр «{season}»",
            "TOPLAM — {season} dönemi",
        ),
    },
}

#: Bu skriptin öz kontekstləri — dəyər həmişə buradakı ilə sinxronlanır.
FORCE = set(ROWS)
#: Mövcud (başqa skriptin) kontekstlərində yalnız boş/fuzzy dəyər doldurulur,
#: amma bu açarlar üçün dəyər bilərəkdən YENİLƏNİR (məs. qeyri-rəsmi «yazsan» → «yazsanız»).
FORCE_KEYS: set[tuple[str, str]] = set()


def _value(lang, az, row):
    return az if lang == "az" else row[LANGS.index(lang) - 1]


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ROWS.items():
        for msgid, row in items.items():
            want = _value(lang, msgid, row)
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=want))
                added += 1
            elif entry.msgstr != want and (
                not entry.msgstr
                or "fuzzy" in entry.flags
                or entry.obsolete
                or ctx in FORCE
                or (ctx, msgid) in FORCE_KEYS
            ):
                entry.msgstr, entry.obsolete = want, False
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
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

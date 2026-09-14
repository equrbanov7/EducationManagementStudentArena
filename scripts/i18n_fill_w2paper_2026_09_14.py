#!/usr/bin/env python3
"""EMSArena i18n — W2 `w2paper` (2026-09-14): kağız imtahan ballarının sual-sual köçürülməsi,
imtahan növü (yazılı / praktiki), «Dəyişən nəticələr» alt-görünüşü, statistika KPI-ları.

Sahibin tələbi: «qrupu seçib balları yazmaq; filter, search, müəllim seçmək;
apellyasiyadan sonra DƏYİŞƏN nəticələrin izlənməsi; max bal 50 / sualdan 10 /
yekun 100». Kontekstlər:

* `registrar.exam_score_entry` — bölmə şablonları, validasiya mesajları, CSV başlıqları;
* `registrar.exam_score_entry_kind` — yeni `appeal` növü (model choices, EN msgid);
* `registrar.exam_score_sheet_kind` — vərəqin imtahan növü (model choices, EN msgid);
* `exams.center.stats` — imtahan mərkəzi statistikasında kağız imtahan KPI bloku.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir (i18n qapısı
`msgstr == msgid` sətrini «tərcümə olunmamış» sayır). Model choices-lərin msgid-i
ingiliscədir (qardaş choices ilə eyni üslub) — AZ tərcüməsi burada verilir.

İstifadə:  python scripts/i18n_fill_w2paper_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ESE = "registrar.exam_score_entry"
KIND = "registrar.exam_score_entry_kind"
SHEET_KIND = "registrar.exam_score_sheet_kind"
STATS = "exams.center.stats"

# msgid → {dil: msgstr}. `az` verilməyibsə msgid-in özü (AZ mənbə).
ENTRIES = {
    KIND: {
        "Appeal result": {
            "az": "Apellyasiya nəticəsi",
            "en": "Appeal result",
            "ru": "Результат апелляции",
            "tr": "İtiraz sonucu",
        },
    },
    SHEET_KIND: {
        "Written": {"az": "Yazılı", "en": "Written", "ru": "Письменный", "tr": "Yazılı sınav"},
        "Practical": {"az": "Praktiki", "en": "Practical", "ru": "Практический", "tr": "Uygulamalı"},
    },
    STATS: {
        "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
        "Kağız imtahanlar (köçürülmüş nəticələr)": {
            "en": "Paper exams (transferred results)",
            "ru": "Бумажные экзамены (перенесённые результаты)",
            "tr": "Kâğıt sınavlar (aktarılan sonuçlar)",
        },
        "daxiletmə": {"en": "entries", "ru": "записей", "tr": "giriş"},
        "dəyişiklik": {"en": "changes", "ru": "изменений", "tr": "değişiklik"},
        "orta imtahan balı": {"en": "average exam score", "ru": "средний балл экзамена", "tr": "ortalama sınav puanı"},
        "tələbə": {"en": "students", "ru": "студентов", "tr": "öğrenci"},
        "vərəq": {"en": "sheets", "ru": "ведомостей", "tr": "cetvel"},
        "İmtahan növü": {"en": "Exam kind", "ru": "Вид экзамена", "tr": "Sınav türü"},
    },
    ESE: {
        "%(label)s balı 0 ilə %(max)s arasında olmalıdır.": {
            "en": "%(label)s score must be between 0 and %(max)s.",
            "ru": "Балл %(label)s должен быть от 0 до %(max)s.",
            "tr": "%(label)s puanı 0 ile %(max)s arasında olmalıdır.",
        },
        "%(label)s balı tam ədəd olmalıdır.": {
            "en": "%(label)s score must be a whole number.",
            "ru": "Балл %(label)s должен быть целым числом.",
            "tr": "%(label)s puanı tam sayı olmalıdır.",
        },
        "0 seçilsə yalnız yekun imtahan balı yazılır (köhnə vərəqlər).": {
            "en": "If 0 is selected, only the total exam score is entered (legacy sheets).",
            "ru": "Если выбрано 0, вводится только итоговый балл экзамена (старые ведомости).",
            "tr": "0 seçilirse yalnızca toplam sınav puanı girilir (eski cetveller).",
        },
        "0 — yalnız yekun bal": {
            "en": "0 — total score only",
            "ru": "0 — только итоговый балл",
            "tr": "0 — yalnızca toplam puan",
        },
        "Bir sualın maksimum balı 1 ilə 100 arasında olmalıdır.": {
            "en": "The maximum score per question must be between 1 and 100.",
            "ru": "Максимальный балл за вопрос должен быть от 1 до 100.",
            "tr": "Soru başına en yüksek puan 1 ile 100 arasında olmalıdır.",
        },
        "Bir sualın maksimumu": {"en": "Max per question", "ru": "Максимум за вопрос", "tr": "Soru başına en yüksek"},
        "Bu dəyişikliyin tam qeydi: köhnə → yeni bal, sual balları, səbəb, qeyd, vərəq və sənəd.": {
            "en": "Full record of this change: old → new score, question scores, reason, note, sheet and document.",
            "ru": "Полная запись изменения: старый → новый балл, баллы по вопросам, причина, заметка, ведомость и документ.",
            "tr": "Bu değişikliğin tam kaydı: eski → yeni puan, soru puanları, gerekçe, not, cetvel ve belge.",
        },
        "Bu filtrə uyğun dəyişiklik yoxdur.": {
            "en": "No changes match this filter.",
            "ru": "Нет изменений по этому фильтру.",
            "tr": "Bu filtreye uyan değişiklik yok.",
        },
        "Bu filtrə uyğun tələbə yoxdur.": {
            "en": "No students match this filter.",
            "ru": "Нет студентов по этому фильтру.",
            "tr": "Bu filtreye uyan öğrenci yok.",
        },
        "Bu vərəq tək yekun bal rejimindədir — sual balı qəbul olunmur.": {
            "en": "This sheet is in total-score mode — per-question scores are not accepted.",
            "ru": "Эта ведомость в режиме итогового балла — баллы по вопросам не принимаются.",
            "tr": "Bu cetvel toplam puan modunda — soru puanları kabul edilmez.",
        },
        "Bütün fənlər": {"en": "All subjects", "ru": "Все предметы", "tr": "Tüm dersler"},
        "Bütün müəllimlər": {"en": "All teachers", "ru": "Все преподаватели", "tr": "Tüm öğretmenler"},
        "Bütün növlər": {"en": "All kinds", "ru": "Все виды", "tr": "Tüm türler"},
        "Bütün qruplar": {"en": "All groups", "ru": "Все группы", "tr": "Tüm gruplar"},
        "CSV ixrac": {"en": "Export CSV", "ru": "Экспорт CSV", "tr": "CSV dışa aktar"},
        "Dəyişiklik": {"en": "Changes", "ru": "Изменения", "tr": "Değişiklik"},
        "Dəyişikliyin növü": {"en": "Kind of change", "ru": "Вид изменения", "tr": "Değişiklik türü"},
        "Dəyişən nəticələr": {"en": "Changed results", "ru": "Изменённые результаты", "tr": "Değişen sonuçlar"},
        "Fənn / qrup": {"en": "Subject / group", "ru": "Предмет / группа", "tr": "Ders / grup"},
        "Giriş balı (%(entry)s) + imtahan balı (%(exam)s) 100-dən çox ola bilməz.": {
            "en": "Entry score (%(entry)s) + exam score (%(exam)s) cannot exceed 100.",
            "ru": "Балл допуска (%(entry)s) + балл экзамена (%(exam)s) не может превышать 100.",
            "tr": "Giriş puanı (%(entry)s) + sınav puanı (%(exam)s) 100'ü aşamaz.",
        },
        "Görünüş": {"en": "View", "ru": "Вид", "tr": "Görünüm"},
        "Köhnə bal": {"en": "Old score", "ru": "Старый балл", "tr": "Eski puan"},
        "Köhnə → yeni": {"en": "Old → new", "ru": "Старый → новый", "tr": "Eski → yeni"},
        "Növ": {"en": "Kind", "ru": "Вид", "tr": "Tür"},
        "S1..Sn sütunları doludursa bal onların cəmidir. İmtahan növü (yazılı / praktiki) və sual şəbəkəsi vərəq məlumatları kartından götürülür — bütün fayla aiddir.": {
            "en": "If the S1..Sn columns are filled, the score is their sum. The exam kind (written / practical) and the question grid come from the sheet details card and apply to the whole file.",
            "ru": "Если заполнены столбцы S1..Sn, балл — их сумма. Вид экзамена (письменный / практический) и сетка вопросов берутся из карточки ведомости и относятся ко всему файлу.",
            "tr": "S1..Sn sütunları doluysa puan bunların toplamıdır. Sınav türü (yazılı / uygulamalı) ve soru şeması cetvel bilgileri kartından alınır ve tüm dosya için geçerlidir.",
        },
        "Sual balları": {"en": "Question scores", "ru": "Баллы по вопросам", "tr": "Soru puanları"},
        "Sual sayı": {"en": "Number of questions", "ru": "Количество вопросов", "tr": "Soru sayısı"},
        "Sual sayı 0 ilə %(max)s arasında olmalıdır.": {
            "en": "The number of questions must be between 0 and %(max)s.",
            "ru": "Количество вопросов должно быть от 0 до %(max)s.",
            "tr": "Soru sayısı 0 ile %(max)s arasında olmalıdır.",
        },
        "Sual sayı vərəqin sual sayından (%(count)s) çox ola bilməz.": {
            "en": "The number of questions cannot exceed the sheet's question count (%(count)s).",
            "ru": "Количество вопросов не может превышать число вопросов ведомости (%(count)s).",
            "tr": "Soru sayısı cetvelin soru sayısını (%(count)s) aşamaz.",
        },
        "Sualların cəmi (%(total)s) imtahan balının tavanını (%(max)s) aşır.": {
            "en": "The sum of question scores (%(total)s) exceeds the exam score cap (%(max)s).",
            "ru": "Сумма баллов по вопросам (%(total)s) превышает предел балла экзамена (%(max)s).",
            "tr": "Soru puanlarının toplamı (%(total)s) sınav puanı üst sınırını (%(max)s) aşıyor.",
        },
        "Sualların cəmi imtahan balının tavanını aşa bilməz.": {
            "en": "The sum of question scores cannot exceed the exam score cap.",
            "ru": "Сумма баллов по вопросам не может превышать предел балла экзамена.",
            "tr": "Soru puanlarının toplamı sınav puanı üst sınırını aşamaz.",
        },
        "Sənəd": {"en": "Document", "ru": "Документ", "tr": "Belge"},
        "Tarix": {"en": "Date", "ru": "Дата", "tr": "Tarih"},
        "Tarixdən": {"en": "From date", "ru": "С даты", "tr": "Tarihten"},
        "Tarixədək": {"en": "To date", "ru": "По дату", "tr": "Tarihe kadar"},
        "Tələbə axtarışı": {"en": "Student search", "ru": "Поиск студента", "tr": "Öğrenci arama"},
        "Xətalı sual balı var — hər sual 0 ilə maksimum arasında tam ədəd olmalıdır.": {
            "en": "There is an invalid question score — each question must be a whole number between 0 and the maximum.",
            "ru": "Есть некорректный балл по вопросу — каждый вопрос должен быть целым числом от 0 до максимума.",
            "tr": "Hatalı soru puanı var — her soru 0 ile en yüksek değer arasında tam sayı olmalıdır.",
        },
        "Yazılmış imtahan balının hər sonrakı dəyişikliyi (apellyasiya qərarı və ya sənədli düzəliş) burada izlənir: köhnə → yeni bal, səbəb, kim və sənəd.": {
            "en": "Every later change of a recorded exam score (appeal decision or documented correction) is tracked here: old → new score, reason, who and document.",
            "ru": "Каждое последующее изменение записанного балла экзамена (решение апелляции или документированная правка) отслеживается здесь: старый → новый балл, причина, кто и документ.",
            "tr": "Kaydedilmiş sınav puanının sonraki her değişikliği (itiraz kararı veya belgeli düzeltme) burada izlenir: eski → yeni puan, gerekçe, kim ve belge.",
        },
        "Yazılı və ya praktiki — vərəqin və bütün sətirlərinin növü.": {
            "en": "Written or practical — the kind of the sheet and all of its rows.",
            "ru": "Письменный или практический — вид ведомости и всех её строк.",
            "tr": "Yazılı veya uygulamalı — cetvelin ve tüm satırlarının türü.",
        },
        "ad · istifadəçi adı · FİN · tələbə №": {
            "en": "name · username · FIN · student no.",
            "ru": "имя · логин · FIN · № студента",
            "tr": "ad · kullanıcı adı · FİN · öğrenci no",
        },
        "hamısı": {"en": "all", "ru": "все", "tr": "tümü"},
        "İmtahan növü": {"en": "Exam kind", "ru": "Вид экзамена", "tr": "Sınav türü"},
        "İmtahan növü yazılı və ya praktiki olmalıdır.": {
            "en": "The exam kind must be written or practical.",
            "ru": "Вид экзамена должен быть письменным или практическим.",
            "tr": "Sınav türü yazılı veya uygulamalı olmalıdır.",
        },
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
            msgstr = translations.get(lang, msgid) if lang != "az" else translations.get("az", msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)

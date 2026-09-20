#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-20: jurnal siyahısı redizaynı + dərs modalında korpus
defoltu. Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent;
sonra `compilemessages`.

İstifadə:  python scripts/i18n_add_journal_list_redesign_2026_09_20.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

# (ctx, msgid): (en, ru, tr)
STRINGS = {
    ("registrar.journal", "<b>%(count)s</b> jurnal"): (
        "<b>%(count)s</b> journals",
        "<b>%(count)s</b> журналов",
        "<b>%(count)s</b> günlük",
    ),
    ("registrar.journal", "Vakant"): ("Vacant", "Вакантно", "Boş"),
    ("registrar.journal", "Dəyişikliklər yadda saxlanmayıb"): (
        "Unsaved changes",
        "Изменения не сохранены",
        "Değişiklikler kaydedilmedi",
    ),
    ("registrar.journal", "Formada tətbiq olunmamış dəyişikliklər var. Bağlasanız, onlar itəcək."): (
        "The form has changes that were not applied. If you close it, they will be lost.",
        "В форме есть неприменённые изменения. Если закрыть, они будут потеряны.",
        "Formda uygulanmamış değişiklikler var. Kapatırsanız kaybolacak.",
    ),
    ("registrar.journal", "Bağla, itsin"): ("Close and discard", "Закрыть и отменить", "Kapat, vazgeç"),
    ("ai_assistant.tooltip", "Sualınızı yazın — dərhal cavab alın"): (
        "Type your question — get an instant answer",
        "Напишите вопрос — получите ответ сразу",
        "Sorunuzu yazın — hemen yanıt alın",
    ),
    ("ai_assistant.status", "Tezliklə"): ("Coming soon", "Скоро", "Yakında"),
    ("ai_assistant.status", "Onlayn"): ("Online", "Онлайн", "Çevrimiçi"),
    (
        "ai_assistant.status",
        "AI assistent hazırlanır — bu pəncərə tezliklə suallarınızı cavablandıracaq. Hələlik sualları kafedra və ya RİM-ə ünvanlayın.",
    ): (
        "The AI assistant is being prepared — this window will answer your questions soon. For now, address questions to your department or the Digital Development Centre.",
        "AI-ассистент готовится — это окно скоро будет отвечать на ваши вопросы. Пока обращайтесь на кафедру или в Центр цифрового развития.",
        "AI asistan hazırlanıyor — bu pencere yakında sorularınızı yanıtlayacak. Şimdilik soruları bölümünüze veya Dijital Gelişim Merkezi'ne yöneltin.",
    ),
    ("ai_assistant.limit", "Saatlıq sorğu limiti"): ("Hourly request limit", "Часовой лимит запросов", "Saatlik istek sınırı"),
    (
        "ai_assistant.footnote",
        "Cavablar avtomatik yaradılır və səhv ola bilər. Şəxsi məlumat (şifrə, kart, FİN) yazmayın.",
    ): (
        "Answers are generated automatically and may be wrong. Do not enter personal data (passwords, cards, FIN).",
        "Ответы формируются автоматически и могут быть неточными. Не вводите личные данные (пароли, карты, FIN).",
        "Yanıtlar otomatik üretilir ve hatalı olabilir. Kişisel veri (şifre, kart, FİN) girmeyin.",
    ),
    ("ai_assistant.disabled", "AI assistent hazırda söndürülüb — tezliklə yenidən aktiv olacaq."): (
        "The AI assistant is currently switched off — it will be back soon.",
        "AI-ассистент сейчас отключён — скоро снова заработает.",
        "AI asistan şu anda kapalı — yakında yeniden etkinleşecek.",
    ),
    (
        "registrar.journal",
        "Korpus qrupun ixtisasına görə «%(building)s» seçilib — dəyişə bilərsiniz; otaqlar korpusa görə süzülür. Otaq məcburi deyil.",
    ): (
        "Building “%(building)s” is preselected from the group's programme — you can change it; rooms are filtered by building. Room is optional.",
        "Корпус «%(building)s» выбран по специальности группы — его можно изменить; аудитории фильтруются по корпусу. Аудитория необязательна.",
        "Bina, grubun programına göre «%(building)s» olarak seçildi — değiştirebilirsiniz; odalar binaya göre süzülür. Oda zorunlu değildir.",
    ),
    # ── Qiymətləndirmə standartı (sahib 2026-09-20) ──────────────────────────
    ("syllabus.assessment", "Davamiyyət"): ("Attendance", "Посещаемость", "Devam"),
    ("syllabus.assessment", "Kollokvium (aralıq qiymətləndirmə)"): (
        "Colloquium (midterm assessment)",
        "Коллоквиум (промежуточная оценка)",
        "Kolokyum (ara değerlendirme)",
    ),
    ("syllabus.assessment", "Sərbəst iş"): ("Independent work", "Самостоятельная работа", "Bağımsız çalışma"),
    ("syllabus.assessment", "Yekun imtahan"): ("Final exam", "Итоговый экзамен", "Final sınavı"),
    ("syllabus.assessment", "Seminar (ədədi orta)"): ("Seminar (average)", "Семинар (среднее)", "Seminer (ortalama)"),
    ("syllabus.assessment", "Laboratoriya (ədədi orta)"): (
        "Laboratory (average)",
        "Лаборатория (среднее)",
        "Laboratuvar (ortalama)",
    ),
    ("syllabus.assessment", "Seminar + laboratoriya (birgə ədədi orta — cəm 2n-ə bölünür)"): (
        "Seminar + laboratory (joint average — the sum is divided by 2n)",
        "Семинар + лаборатория (общее среднее — сумма делится на 2n)",
        "Seminer + laboratuvar (ortak ortalama — toplam 2n'ye bölünür)",
    ),
    ("syllabus.assessment", "Seminar balı: semestr ərzindəki bütün seminar qiymətlərinin ədədi ortası (maksimum 10)."): (
        "Seminar score: the average of all seminar grades during the semester (maximum 10).",
        "Балл за семинары: среднее всех оценок за семинары в семестре (максимум 10).",
        "Seminer puanı: dönem içindeki tüm seminer notlarının ortalaması (en fazla 10).",
    ),
    (
        "syllabus.assessment",
        "Laboratoriya balı: semestr ərzindəki bütün laboratoriya qiymətlərinin ədədi ortası (maksimum 10).",
    ): (
        "Laboratory score: the average of all laboratory grades during the semester (maximum 10).",
        "Балл за лабораторные: среднее всех оценок за лабораторные в семестре (максимум 10).",
        "Laboratuvar puanı: dönem içindeki tüm laboratuvar notlarının ortalaması (en fazla 10).",
    ),
    (
        "syllabus.assessment",
        "Fənndə həm seminar, həm laboratoriya var: bütün seminar və laboratoriya qiymətləri toplanıb ümumi sayına (2n) bölünür — birgə ədədi orta, maksimum 10.",
    ): (
        "The subject has both seminars and laboratories: all seminar and laboratory grades are summed and divided by their total count (2n) — a joint average, maximum 10.",
        "В предмете есть и семинары, и лабораторные: все оценки суммируются и делятся на их общее число (2n) — общее среднее, максимум 10.",
        "Derste hem seminer hem laboratuvar var: tüm seminer ve laboratuvar notları toplanıp toplam sayıya (2n) bölünür — ortak ortalama, en fazla 10.",
    ),
    ("syllabus.assessment", "bal"): ("points", "баллов", "puan"),
    ("syllabus.assessment", "semestr"): ("semester", "семестр", "dönem"),
    ("syllabus.assessment", "imtahan"): ("exam", "экзамен", "sınav"),
    ("accounts.syllabus", "Universitet standartı"): ("University standard", "Стандарт университета", "Üniversite standardı"),
    (
        "accounts.syllabus",
        "Semestr balı %(semester)s (davamiyyət + kollokvium + sərbəst iş + seminar/laboratoriya ədədi ortası), yekun imtahan 50 — cəmi %(total)s bal. Bölgü universitet standartıdır və dəyişdirilmir.",
    ): (
        "Semester score %(semester)s (attendance + colloquium + independent work + seminar/laboratory average), final exam 50 — total %(total)s points. The split is a university standard and cannot be changed.",
        "Балл за семестр %(semester)s (посещаемость + коллоквиум + самостоятельная работа + среднее за семинары/лабораторные), итоговый экзамен 50 — всего %(total)s баллов. Распределение — стандарт университета и не меняется.",
        "Dönem puanı %(semester)s (devam + kolokyum + bağımsız çalışma + seminer/laboratuvar ortalaması), final sınavı 50 — toplam %(total)s puan. Dağılım üniversite standardıdır ve değiştirilemez.",
    ),
    (
        "accounts.syllabus",
        "Bu fənn üçün tədris planı / dərs yükü saatı tapılmadı. Fənnin semestr saatını növ üzrə yazın:",
    ): (
        "No curriculum / teaching-load hours were found for this subject. Enter the semester hours by type:",
        "Часы учебного плана / нагрузки для этого предмета не найдены. Укажите часы за семестр по видам:",
        "Bu ders için müfredat / ders yükü saati bulunamadı. Dönem saatini türe göre yazın:",
    ),
    ("accounts.syllabus", "Saatı yadda saxla"): ("Save hours", "Сохранить часы", "Saati kaydet"),
    (
        "accounts.syllabus",
        "Bal bölgüsü universitet standartıdır: davamiyyət 10, kollokvium 20, sərbəst iş 10, seminar/laboratoriya ədədi ortası 10 (semestr 50) və yekun imtahan 50 — müəllim dəyişmir. Fəaliyyət növü dərs yükündən gəlir.",
    ): (
        "The score split is a university standard: attendance 10, colloquium 20, independent work 10, seminar/laboratory average 10 (semester 50) and final exam 50 — the teacher does not change it. The activity type comes from the teaching load.",
        "Распределение баллов — стандарт университета: посещаемость 10, коллоквиум 20, самостоятельная работа 10, среднее за семинары/лабораторные 10 (семестр 50) и итоговый экзамен 50 — преподаватель его не меняет. Вид занятий берётся из нагрузки.",
        "Puan dağılımı üniversite standardıdır: devam 10, kolokyum 20, bağımsız çalışma 10, seminer/laboratuvar ortalaması 10 (dönem 50) ve final sınavı 50 — öğretim elemanı değiştirmez. Etkinlik türü ders yükünden gelir.",
    ),
    # ── Workbench: önizləmə skeletonu + təsdiq xülasəsi (sahib 2026-09-20) ────
    ("exams.template.test_question_bank", "Suallar yoxlanılır, önizləmə hazırlanır…"): (
        "Checking questions, preparing the preview…",
        "Проверяем вопросы, готовим предпросмотр…",
        "Sorular kontrol ediliyor, önizleme hazırlanıyor…",
    ),
    ("exams.template.test_question_bank", "Göndərişi təsdiqləyin"): ("Confirm the submission", "Подтвердите отправку", "Gönderimi onaylayın"),
    ("exams.template.test_question_bank", "Bəli, göndər"): ("Yes, send", "Да, отправить", "Evet, gönder"),
    ("exams.template.test_question_bank", "Geri qayıt"): ("Go back", "Вернуться", "Geri dön"),
    ("exams.template.test_question_bank", "Heç bir sual seçilməyib — əvvəlcə siyahıdan sual seçin."): (
        "No question is selected — pick questions from the list first.",
        "Не выбран ни один вопрос — сначала выберите вопросы в списке.",
        "Hiç soru seçilmedi — önce listeden soru seçin.",
    ),
    ("exams.template.test_question_bank", "Seçilmiş sual"): ("Selected questions", "Выбрано вопросов", "Seçilen soru"),
    ("exams.template.test_question_bank", "Məcburi sahələri doldurun — çatışmayan sahə vurğulandı."): (
        "Fill in the required fields — the missing field is highlighted.",
        "Заполните обязательные поля — незаполненное поле выделено.",
        "Zorunlu alanları doldurun — eksik alan vurgulandı.",
    ),
    ("exams.template.test_question_bank", "Xətalı sual"): ("Questions with errors", "Вопросов с ошибками", "Hatalı soru"),
    ("exams.template.test_question_bank", "Xəbərdarlıqlı sual"): ("Questions with warnings", "Вопросов с предупреждениями", "Uyarılı soru"),
}  # fmt: skip


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            target = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            entry = existing.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=target))
                added += 1
            elif not entry.msgstr:
                entry.msgstr = target
                added += 1
        po.save(path)
        print(f"{lang}: {added} əlavə/doldurma")


if __name__ == "__main__":
    main()

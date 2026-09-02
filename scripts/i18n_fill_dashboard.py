#!/usr/bin/env python3
"""EMSArena i18n — «Ana səhifə» (dashboard) bölməsinin sətirləri (4 dil). İdempotent.

FAZA 22-də əlavə olunan kabinet ana səhifəsinin bütün UI mətnləri + FAZA 28
inteqrasiyasında aşkarlanan qalıq `source_missing` girişləri.

⚠️ NİYƏ ƏL İLƏ? `dashboard*.py` fayllarında kontekst modul-səviyyə dəyişəndir
(`_CTX = "accounts.dashboard"` — layihədə 20+ faylda eyni konvensiya). Nə
`xgettext`, nə də `scripts/i18n_source_scan.py` dəyişən-kontekstli çağırışı
literal kimi görmür, ona görə bu girişlər `makemessages` ilə çıxarılmır.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silə bilir) — skript
yalnız ƏLAVƏ edir və mövcud girişə toxunmur (bax i18n_fill_student_intake.py).

İstifadə:  python scripts/i18n_fill_dashboard.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_C = "accounts.dashboard"

ENTRIES = {
    # ── Sidebar bəndi (ÜMUMİ qrupunun birinci sətri) ────────────────────────
    "profile.sidebar": {
        "Ana səhifə": {"en": "Home", "ru": "Главная", "tr": "Ana sayfa"},
    },
    # ── Ana səhifənin öz mətnləri ───────────────────────────────────────────
    _C: {
        # Salamlama + boş vəziyyət
        "Salam, %(name)s": {
            "en": "Hello, %(name)s",
            "ru": "Здравствуйте, %(name)s",
            "tr": "Merhaba, %(name)s",
        },
        "Xülasə hazır deyil": {
            "en": "The summary is not ready",
            "ru": "Сводка не готова",
            "tr": "Özet hazır değil",
        },
        "Bu kabinet üçün hələ göstəriləcək xülasə yoxdur — sol menyudan bölmə seçin.": {
            "en": "There is no summary to show for this cabinet yet — pick a section from the left menu.",
            "ru": "Для этого кабинета пока нет сводки — выберите раздел в меню слева.",
            "tr": "Bu kabin için henüz gösterilecek bir özet yok — soldaki menüden bir bölüm seçin.",
        },
        # ── Vidjet başlıqları ───────────────────────────────────────────────
        "Bu gün dərslər": {"en": "Today's lessons", "ru": "Занятия сегодня", "tr": "Bugünkü dersler"},
        "Bu gün dərslərim": {"en": "My lessons today", "ru": "Мои занятия сегодня", "tr": "Bugünkü derslerim"},
        "Davamiyyət": {"en": "Attendance", "ru": "Посещаемость", "tr": "Devam durumu"},
        "Son qiymətlər": {"en": "Latest marks", "ru": "Последние оценки", "tr": "Son notlar"},
        "Fənlərim": {"en": "My subjects", "ru": "Мои предметы", "tr": "Derslerim"},
        "Sillabus işlərim": {
            "en": "My syllabus tasks",
            "ru": "Мои работы по силлабусам",
            "tr": "Ders izlencesi işlerim",
        },
        "Dərs yüküm": {"en": "My teaching load", "ru": "Моя учебная нагрузка", "tr": "Ders yüküm"},
        "Müraciətlər": {"en": "Applications", "ru": "Обращения", "tr": "Başvurular"},
        "Sillabus təsdiqi": {
            "en": "Syllabus approval",
            "ru": "Утверждение силлабуса",
            "tr": "Ders izlencesi onayı",
        },
        "Yük bölgüsü": {"en": "Load distribution", "ru": "Распределение нагрузки", "tr": "Yük dağıtımı"},
        "Cədvəl idarəetməsi": {
            "en": "Timetable management",
            "ru": "Управление расписанием",
            "tr": "Program yönetimi",
        },
        "Kollokvium pəncərələri": {
            "en": "Colloquium windows",
            "ru": "Окна коллоквиумов",
            "tr": "Kolokyum pencereleri",
        },
        "Yaxın imtahanlar": {"en": "Upcoming exams", "ru": "Ближайшие экзамены", "tr": "Yaklaşan sınavlar"},
        "Apellyasiyalar": {"en": "Appeals", "ru": "Апелляции", "tr": "İtirazlar"},
        "Jurnal düzəlişləri": {
            "en": "Journal corrections",
            "ru": "Правки журнала",
            "tr": "Yoklama defteri düzeltmeleri",
        },
        "Jurnal bağlama": {
            "en": "Journal closing",
            "ru": "Закрытие журналов",
            "tr": "Yoklama defteri kapatma",
        },
        "Tələbə idxalı": {"en": "Student intake", "ru": "Импорт студентов", "tr": "Öğrenci alımı"},
        "Universitet göstəriciləri": {
            "en": "University indicators",
            "ru": "Показатели университета",
            "tr": "Üniversite göstergeleri",
        },
        # ── Keçid linkləri ──────────────────────────────────────────────────
        "Cədvələ keç": {"en": "Go to the timetable", "ru": "Перейти к расписанию", "tr": "Programa git"},
        "Jurnala keç": {
            "en": "Go to the journal",
            "ru": "Перейти к журналу",
            "tr": "Yoklama defterine git",
        },
        "Sillabuslara keç": {
            "en": "Go to the syllabi",
            "ru": "Перейти к силлабусам",
            "tr": "Ders izlencelerine git",
        },
        "Dərs yükünə keç": {
            "en": "Go to the teaching load",
            "ru": "Перейти к учебной нагрузке",
            "tr": "Ders yüküne git",
        },
        "Müraciətlərə keç": {"en": "Go to the applications", "ru": "Перейти к обращениям", "tr": "Başvurulara git"},
        "Növbəyə keç": {"en": "Go to the queue", "ru": "Перейти к очереди", "tr": "Sıraya git"},
        "Bölgüyə keç": {
            "en": "Go to the distribution",
            "ru": "Перейти к распределению",
            "tr": "Dağıtıma git",
        },
        "Pəncərələrə keç": {"en": "Go to the windows", "ru": "Перейти к окнам", "tr": "Pencerelere git"},
        "Statistikaya keç": {"en": "Go to the statistics", "ru": "Перейти к статистике", "tr": "İstatistiklere git"},
        "Apellyasiyalara keç": {"en": "Go to the appeals", "ru": "Перейти к апелляциям", "tr": "İtirazlara git"},
        "Bağlamaya keç": {
            "en": "Go to journal closing",
            "ru": "Перейти к закрытию журналов",
            "tr": "Defter kapatmaya git",
        },
        "İdxala keç": {"en": "Go to the intake", "ru": "Перейти к импорту", "tr": "Alıma git"},
        "Kataloqa keç": {"en": "Go to the catalogue", "ru": "Перейти к каталогу", "tr": "Kataloğa git"},
        # ── Statistika etiketləri ───────────────────────────────────────────
        "Bu gün": {"en": "Today", "ru": "Сегодня", "tr": "Bugün"},
        "Bu həftə": {"en": "This week", "ru": "Эта неделя", "tr": "Bu hafta"},
        "Həftədə": {"en": "Per week", "ru": "За неделю", "tr": "Haftada"},
        "Cari dövr": {"en": "Current period", "ru": "Текущий период", "tr": "Mevcut dönem"},
        "Növbəti": {"en": "Next", "ru": "Следующее", "tr": "Sonraki"},
        "Yazılan bal": {"en": "Marks recorded", "ru": "Выставленные баллы", "tr": "Girilen puan"},
        "Qayıb": {"en": "Absence", "ru": "Пропуски", "tr": "Devamsızlık"},
        "Fənn": {"en": "Subjects", "ru": "Дисциплины", "tr": "Dersler"},
        "Limit": {"en": "Limit", "ru": "Лимит", "tr": "Sınır"},
        "İllik cəmi": {"en": "Annual total", "ru": "Годовой итог", "tr": "Yıllık toplam"},
        "Norma": {"en": "Norm", "ru": "Норма", "tr": "Norm"},
        "Doluluq": {"en": "Load fill", "ru": "Заполненность", "tr": "Doluluk"},
        "Gözləyən": {"en": "Pending", "ru": "В ожидании", "tr": "Bekleyen"},
        "Növbədə": {"en": "In the queue", "ru": "В очереди", "tr": "Sırada"},
        "Kafedra": {"en": "Departments", "ru": "Кафедры", "tr": "Bölümler"},
        "Qrup": {"en": "Groups", "ru": "Группы", "tr": "Gruplar"},
        "Status": {"en": "Status", "ru": "Статус", "tr": "Durum"},
        "Aktiv": {"en": "Active", "ru": "Активные", "tr": "Aktif"},
        "Açıq": {"en": "Open", "ru": "Открытые", "tr": "Açık"},
        "Tələbə": {"en": "Students", "ru": "Студенты", "tr": "Öğrenciler"},
        "Müəllim": {"en": "Teachers", "ru": "Преподаватели", "tr": "Öğretim elemanları"},
        # ── Rəqəmdən sonra gələn vahid/qeyd sözləri (kiçik hərflə) ──────────
        "dərs": {"en": "lessons", "ru": "занятий", "tr": "ders"},
        "slot": {"en": "slots", "ru": "слотов", "tr": "slot"},
        "saat": {"en": "hours", "ru": "часов", "tr": "saat"},
        "açılış": {"en": "offerings", "ru": "потоков", "tr": "ders açılışı"},
        "sillabus": {"en": "syllabi", "ru": "силлабусов", "tr": "ders izlencesi"},
        "müraciət": {"en": "applications", "ru": "обращений", "tr": "başvuru"},
        "apellyasiya": {"en": "appeals", "ru": "апелляций", "tr": "itiraz"},
        "düzəliş": {"en": "corrections", "ru": "правок", "tr": "düzeltme"},
        "bildiriş": {"en": "notices", "ru": "уведомлений", "tr": "bildirim"},
        "pəncərə": {"en": "windows", "ru": "окон", "tr": "pencere"},
        "imtahan": {"en": "exams", "ru": "экзаменов", "tr": "sınav"},
        "sonuncu": {"en": "most recent", "ru": "последних", "tr": "sonuncu"},
        "cari dövr": {"en": "current period", "ru": "текущий период", "tr": "mevcut dönem"},
        "proqram üzrə": {"en": "by programme", "ru": "по программе", "tr": "programa göre"},
        "əhatədə": {"en": "in scope", "ru": "в охвате", "tr": "kapsamda"},
        "səlahiyyət sahənizdə": {
            "en": "in your area of authority",
            "ru": "в вашей зоне полномочий",
            "tr": "yetki alanınızda",
        },
        "tapşırıq yoxdur": {"en": "no task", "ru": "нет задания", "tr": "görev yok"},
        "yoxdur": {"en": "none", "ru": "нет", "tr": "yok"},
        "aktiv": {"en": "active", "ru": "активно", "tr": "aktif"},
        "deaktiv": {"en": "inactive", "ru": "неактивно", "tr": "pasif"},
        "açıq": {"en": "open", "ru": "открыто", "tr": "açık"},
        "bağlı": {"en": "closed", "ru": "закрыто", "tr": "kapalı"},
        "planlanıb": {"en": "scheduled", "ru": "запланировано", "tr": "planlandı"},
        "qurulmayıb": {"en": "not configured", "ru": "не настроено", "tr": "yapılandırılmadı"},
        "Planlanıb": {"en": "Scheduled", "ru": "Запланировано", "tr": "Planlandı"},
        # ── Boş vəziyyət mətnləri ───────────────────────────────────────────
        "Akademik qeydiniz tapılmadı — RİM-ə müraciət edin.": {
            "en": "Your academic record was not found — contact the Digital Development Centre (RİM).",
            "ru": "Ваша академическая запись не найдена — обратитесь в Центр цифрового развития (RİM).",
            "tr": "Akademik kaydınız bulunamadı — Dijital Gelişim Merkezi (RİM) ile iletişime geçin.",
        },
        "Aktiv jurnal bağlama bildirişi yoxdur.": {
            "en": "There are no active journal-closing notices.",
            "ru": "Активных уведомлений о закрытии журналов нет.",
            "tr": "Aktif yoklama defteri kapatma bildirimi yok.",
        },
        "Bu gün üçün cədvəldə dərs yoxdur.": {
            "en": "There are no lessons in the timetable for today.",
            "ru": "На сегодня в расписании занятий нет.",
            "tr": "Bugün için programda ders yok.",
        },
        "Bu gün üçün cədvəldə dərsiniz yoxdur.": {
            "en": "You have no lessons in the timetable for today.",
            "ru": "На сегодня у вас нет занятий в расписании.",
            "tr": "Bugün için programda dersiniz yok.",
        },
        "Bu həftə düzəliş edilməyib.": {
            "en": "No corrections have been made this week.",
            "ru": "На этой неделе правок не было.",
            "tr": "Bu hafta düzeltme yapılmadı.",
        },
        "CSV ilə toplu tələbə hesabı yaradın.": {
            "en": "Create student accounts in bulk from a CSV file.",
            "ru": "Создайте учётные записи студентов массово из CSV-файла.",
            "tr": "CSV ile toplu öğrenci hesabı oluşturun.",
        },
        "Cari dövr üçün pəncərə qurulmayıb.": {
            "en": "No window has been configured for the current period.",
            "ru": "Для текущего периода окно не настроено.",
            "tr": "Mevcut dönem için pencere yapılandırılmadı.",
        },
        "Cari dövrdə qeydiyyat yoxdur.": {
            "en": "There is no enrolment in the current period.",
            "ru": "В текущем периоде записей нет.",
            "tr": "Mevcut dönemde kayıt yok.",
        },
        "Cari dövrdə sizə fənn təyin olunmayıb.": {
            "en": "No subject has been assigned to you in the current period.",
            "ru": "В текущем периоде вам не назначена дисциплина.",
            "tr": "Mevcut dönemde size ders atanmadı.",
        },
        "Cari semestr üçün qrup cədvəliniz tapılmadı.": {
            "en": "Your group's timetable for the current semester was not found.",
            "ru": "Расписание вашей группы на текущий семестр не найдено.",
            "tr": "Mevcut dönem için grup programınız bulunamadı.",
        },
        "Hələ heç bir bal yazılmayıb.": {
            "en": "No marks have been recorded yet.",
            "ru": "Баллы ещё не выставлены.",
            "tr": "Henüz hiç puan girilmedi.",
        },
        "Hərəkət gözləyən müraciət yoxdur.": {
            "en": "There are no applications awaiting action.",
            "ru": "Обращений, ожидающих действия, нет.",
            "tr": "İşlem bekleyen başvuru yok.",
        },
        "Planlanmış imtahan yoxdur.": {
            "en": "There are no scheduled exams.",
            "ru": "Запланированных экзаменов нет.",
            "tr": "Planlanmış sınav yok.",
        },
        "Qaralama və ya düzəliş gözləyən sillabus yoxdur.": {
            "en": "There is no syllabus in draft or awaiting revision.",
            "ru": "Нет силлабусов в черновике или ожидающих доработки.",
            "tr": "Taslak veya düzeltme bekleyen ders izlencesi yok.",
        },
        "Qərar gözləyən apellyasiya yoxdur.": {
            "en": "There are no appeals awaiting a decision.",
            "ru": "Апелляций, ожидающих решения, нет.",
            "tr": "Karar bekleyen itiraz yok.",
        },
        "Struktur əhatəniz təyin edilməyib — növbə boşdur.": {
            "en": "Your structural scope has not been set — the queue is empty.",
            "ru": "Ваш структурный охват не задан — очередь пуста.",
            "tr": "Yapısal kapsamınız belirlenmedi — sıra boş.",
        },
        "Səlahiyyət sahənizdə qrup yoxdur.": {
            "en": "There are no groups in your area of authority.",
            "ru": "В вашей зоне полномочий групп нет.",
            "tr": "Yetki alanınızda grup yok.",
        },
        "Təsdiq gözləyən sillabus yoxdur.": {
            "en": "There is no syllabus awaiting approval.",
            "ru": "Силлабусов, ожидающих утверждения, нет.",
            "tr": "Onay bekleyen ders izlencesi yok.",
        },
        "Təsdiqlənmiş dərs yükü yoxdur.": {
            "en": "There is no approved teaching load.",
            "ru": "Утверждённой учебной нагрузки нет.",
            "tr": "Onaylanmış ders yükü yok.",
        },
        "Əhatənizdə kafedra tapılmadı.": {
            "en": "No department was found in your scope.",
            "ru": "В вашем охвате кафедр не найдено.",
            "tr": "Kapsamınızda bölüm bulunamadı.",
        },
    },
    # ── FAZA 28: qalıq `source_missing` girişləri (dashboard-dan kənar) ──────
    "exams.final_center.permission": {
        "Bu bölmə yalnız imtahan mərkəzi və nəzarətçilər üçündür.": {
            "en": "This section is only for the exam centre and the invigilators.",
            "ru": "Этот раздел предназначен только для экзаменационного центра и наблюдателей.",
            "tr": "Bu bölüm yalnızca sınav merkezi ve gözetmenler içindir.",
        },
    },
    "registrar.journal": {
        "Otaq": {"en": "Room", "ru": "Аудитория", "tr": "Derslik"},
    },
    # Kontekstsiz (PDF/çap altlığı və yekun nəticə başlığı).
    "": {
        "Bu sənəd sistem tərəfindən yaradılıb və elektron formada etibarlıdır.": {
            "en": "This document was generated by the system and is valid in electronic form.",
            "ru": "Этот документ сформирован системой и действителен в электронном виде.",
            "tr": "Bu belge sistem tarafından oluşturulmuştur ve elektronik biçimde geçerlidir.",
        },
        "Yekun nəticə": {"en": "Final result", "ru": "Итоговый результат", "tr": "Nihai sonuç"},
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def existing_keys(lang):
    """Mövcud (msgctxt, msgid) cütləri — polib ilə DƏQİQ oxunur.

    Mətn üzərində `in` yoxlaması kontekstsiz girişlərdə yanlış müsbət verir
    (eyni msgid başqa kontekstdə ola bilər), ona görə burada parser işlədilir.
    """
    import polib

    return {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(po_path(lang)) if not entry.obsolete}


def fill(lang):
    path = po_path(lang)
    present = existing_keys(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in present:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            header = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            blocks.append(f'{header}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)

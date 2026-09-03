#!/usr/bin/env python3
"""EMSArena i18n — insanlar kataloqunun ANALİTİKA sətirləri (statistika + AI). İdempotent.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silə bilir) — skript
yalnız ƏLAVƏ edir və mövcud girişə toxunmur.

İstifadə:  python scripts/i18n_fill_people_analytics.py && python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "accounts.people.analytics"

ENTRIES = {
    CTX: {
        # ── status / cins səbətləri ──────────────────────────────────────────
        "Aktiv": {"en": "Active", "ru": "Активные", "tr": "Aktif"},
        "Dayandırılıb": {"en": "Suspended", "ru": "Приостановлены", "tr": "Askıya alınmış"},
        "Arxiv": {"en": "Archived", "ru": "Архив", "tr": "Arşiv"},
        "Silinib": {"en": "Deleted", "ru": "Удалённые", "tr": "Silinmiş"},
        "Kişi": {"en": "Male", "ru": "Мужчины", "tr": "Erkek"},
        "Qadın": {"en": "Female", "ru": "Женщины", "tr": "Kadın"},
        "Göstərilməyib": {"en": "Not specified", "ru": "Не указано", "tr": "Belirtilmemiş"},
        "Təyin edilməyib": {"en": "Not assigned", "ru": "Не назначено", "tr": "Atanmamış"},
        "Digərləri": {"en": "Others", "ru": "Прочие", "tr": "Diğerleri"},
        # ── yaş səbətləri ────────────────────────────────────────────────────
        "25-dən kiçik": {"en": "Under 25", "ru": "Младше 25", "tr": "25 yaş altı"},
        # ⚠️ Səbət etiketlərinə «yaş» sözü QƏSDƏN əlavə olunub: «25–34» rəqəm
        # sətri dörd dildə eyni olur və i18n qapısı onu «tərcümə olunmamış
        # identity» borcu sayır.
        "25–34 yaş": {"en": "Ages 25–34", "ru": "25–34 года", "tr": "25–34 yaş arası"},
        "35–44 yaş": {"en": "Ages 35–44", "ru": "35–44 года", "tr": "35–44 yaş arası"},
        "45–54 yaş": {"en": "Ages 45–54", "ru": "45–54 года", "tr": "45–54 yaş arası"},
        "55–64 yaş": {"en": "Ages 55–64", "ru": "55–64 года", "tr": "55–64 yaş arası"},
        "65 və yuxarı": {"en": "65 and over", "ru": "65 и старше", "tr": "65 ve üzeri"},
        # ── bölgü başlıqları ─────────────────────────────────────────────────
        "Fakültə üzrə bölgü": {
            "en": "Distribution by faculty",
            "ru": "Распределение по факультетам",
            "tr": "Fakülteye göre dağılım",
        },
        "Kafedra üzrə bölgü": {
            "en": "Distribution by department",
            "ru": "Распределение по кафедрам",
            "tr": "Bölüme göre dağılım",
        },
        "Rol üzrə bölgü": {
            "en": "Distribution by role",
            "ru": "Распределение по ролям",
            "tr": "Role göre dağılım",
        },
        "Akademik dərəcə / vəzifə": {
            "en": "Academic degree / position",
            "ru": "Учёная степень / должность",
            "tr": "Akademik derece / görev",
        },
        "Qrup üzrə bölgü": {
            "en": "Distribution by group",
            "ru": "Распределение по группам",
            "tr": "Gruba göre dağılım",
        },
        "İxtisas üzrə bölgü": {
            "en": "Distribution by program",
            "ru": "Распределение по специальностям",
            "tr": "Programa göre dağılım",
        },
        "Kurs üzrə bölgü": {
            "en": "Distribution by year of study",
            "ru": "Распределение по курсам",
            "tr": "Sınıfa göre dağılım",
        },
        "Qəbul ili üzrə bölgü": {
            "en": "Distribution by admission year",
            "ru": "Распределение по году приёма",
            "tr": "Kayıt yılına göre dağılım",
        },
        "Akademik status üzrə bölgü": {
            "en": "Distribution by academic status",
            "ru": "Распределение по академическому статусу",
            "tr": "Akademik duruma göre dağılım",
        },
        "%(course)s. kurs": {
            "en": "Year %(course)s",
            "ru": "%(course)s курс",
            "tr": "%(course)s. sınıf",
        },
        "Kursdan kənar / məzun mərhələsi": {
            "en": "Outside the standard years / graduating stage",
            "ru": "Вне стандартных курсов / выпускной этап",
            "tr": "Standart sınıf dışı / mezuniyet aşaması",
        },
        # ── dərs yükü göstəriciləri ──────────────────────────────────────────
        "Dərs açılışı (semestr-fənn)": {
            "en": "Course offerings (semester × subject)",
            "ru": "Учебные назначения (семестр × предмет)",
            "tr": "Ders açılışı (dönem × ders)",
        },
        "Fərqli fənn": {"en": "Distinct subjects", "ru": "Различных предметов", "tr": "Farklı ders"},
        "Dərs deyilən qrup": {"en": "Groups taught", "ru": "Обучаемых групп", "tr": "Ders verilen grup"},
        "Dərs yükü olan müəllim": {
            "en": "Teachers with a teaching load",
            "ru": "Преподаватели с нагрузкой",
            "tr": "Ders yükü olan öğretim elemanı",
        },
        "Dərs yükü olmayan müəllim": {
            "en": "Teachers without a teaching load",
            "ru": "Преподаватели без нагрузки",
            "tr": "Ders yükü olmayan öğretim elemanı",
        },
        "Müəllim başına orta açılış": {
            "en": "Average offerings per teacher",
            "ru": "В среднем назначений на преподавателя",
            "tr": "Öğretim elemanı başına ortalama açılış",
        },
        "Tələbə-yer (qeydiyyat)": {
            "en": "Student seats (enrollments)",
            "ru": "Студенто-места (записи)",
            "tr": "Öğrenci kontenjanı (kayıt)",
        },
        # ── UI / şablon ──────────────────────────────────────────────────────
        "Statistika və analiz": {
            "en": "Statistics and analysis",
            "ru": "Статистика и анализ",
            "tr": "İstatistik ve analiz",
        },
        "Bütün göstəricilər və qrafiklər yuxarıdakı filtrə görə yenilənir — nə süzürsünüzsə, rəqəmlər onu göstərir.": {
            "en": (
                "Every figure and chart follows the filters above — the numbers always describe "
                "exactly what you filtered."
            ),
            "ru": ("Все показатели и графики следуют фильтрам выше — цифры описывают именно " "отфильтрованный набор."),
            "tr": (
                "Tüm göstergeler ve grafikler yukarıdaki filtreye göre güncellenir — rakamlar "
                "tam olarak süzdüğünüz kümeyi gösterir."
            ),
        },
        "Ümumi": {"en": "Total", "ru": "Всего", "tr": "Toplam"},
        "Cədvəl şəklində": {"en": "As a table", "ru": "В виде таблицы", "tr": "Tablo olarak"},
        "Göstərici": {"en": "Indicator", "ru": "Показатель", "tr": "Gösterge"},
        "Say": {"en": "Count", "ru": "Количество", "tr": "Sayı"},
        "Faiz": {"en": "Percent", "ru": "Процент", "tr": "Yüzde"},
        "Bu filtr üçün göstəriləcək məlumat yoxdur.": {
            "en": "There is no data to display for this filter.",
            "ru": "Для этого фильтра нет данных.",
            "tr": "Bu filtre için gösterilecek veri yok.",
        },
        "Doğum tarixi doldurulub": {
            "en": "Birth date filled in",
            "ru": "Дата рождения заполнена",
            "tr": "Doğum tarihi dolu",
        },
        "Dərs yükü göstəriciləri": {
            "en": "Teaching-load indicators",
            "ru": "Показатели учебной нагрузки",
            "tr": "Ders yükü göstergeleri",
        },
        "Hesab statusu üzrə": {
            "en": "By account status",
            "ru": "По статусу учётной записи",
            "tr": "Hesap durumuna göre",
        },
        "Cins üzrə bölgü": {
            "en": "Distribution by gender",
            "ru": "Распределение по полу",
            "tr": "Cinsiyete göre dağılım",
        },
        "Yaş qrupları üzrə bölgü": {
            "en": "Distribution by age band",
            "ru": "Распределение по возрастным группам",
            "tr": "Yaş gruplarına göre dağılım",
        },
        "AI analizi": {"en": "AI analysis", "ru": "ИИ-анализ", "tr": "Yapay zekâ analizi"},
        "AI ilə analiz et": {
            "en": "Analyze with AI",
            "ru": "Проанализировать с ИИ",
            "tr": "Yapay zekâ ile analiz et",
        },
        "AI analizi hazırlanır…": {
            "en": "Preparing the AI analysis…",
            "ru": "Готовится ИИ-анализ…",
            "tr": "Yapay zekâ analizi hazırlanıyor…",
        },
        "AI analizi alınmadı. Bir az sonra yenidən cəhd edin.": {
            "en": "The AI analysis failed. Please try again shortly.",
            "ru": "Не удалось получить ИИ-анализ. Повторите попытку позже.",
            "tr": "Yapay zekâ analizi alınamadı. Kısa süre sonra tekrar deneyin.",
        },
        "Qalan AI limiti": {"en": "Remaining AI quota", "ru": "Остаток лимита ИИ", "tr": "Kalan yapay zekâ limiti"},
        "keşdən": {"en": "from cache", "ru": "из кэша", "tr": "önbellekten"},
        "Analiz üçün düyməni sıxın — nəticə bir neçə saniyəyə hazırlanır.": {
            "en": "Press the button to run the analysis — the result takes a few seconds.",
            "ru": "Нажмите кнопку для анализа — результат готовится за несколько секунд.",
            "tr": "Analiz için düğmeye basın — sonuç birkaç saniyede hazırlanır.",
        },
        (
            "Süni intellekt yuxarıdakı AQREQAT rəqəmləri şərh edir. AI-a yalnız saylar və faizlər "
            "göndərilir — ad, e-poçt, telefon və FİN GÖNDƏRİLMİR. Eyni məlumat üçün cavab keşdən "
            "gəlir, limit sərf olunmur."
        ): {
            "en": (
                "The AI interprets the AGGREGATE figures above. Only counts and percentages are sent "
                "— names, e-mail addresses, phone numbers and ID numbers are NOT sent. For unchanged "
                "data the answer comes from the cache and no quota is spent."
            ),
            "ru": (
                "ИИ интерпретирует АГРЕГИРОВАННЫЕ показатели выше. Отправляются только количества и "
                "проценты — имена, адреса эл. почты, телефоны и коды ИНН НЕ отправляются. При "
                "неизменных данных ответ берётся из кэша и лимит не расходуется."
            ),
            "tr": (
                "Yapay zekâ yukarıdaki TOPLU rakamları yorumlar. Yalnızca sayılar ve yüzdeler "
                "gönderilir — ad, e-posta, telefon ve kimlik numarası GÖNDERİLMEZ. Veri değişmediğinde "
                "yanıt önbellekten gelir ve limit harcanmaz."
            ),
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
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

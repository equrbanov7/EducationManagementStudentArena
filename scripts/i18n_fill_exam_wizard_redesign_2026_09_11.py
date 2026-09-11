#!/usr/bin/env python3
"""EMSArena i18n — «Yeni imtahan yarat» sehrbazının redizaynı (kabinet, 2026-09-11).

Sahib tələbi: «rəngləri, digər hissələri düzəlt, təkmilləşdir ki qəşəng olsun;
heç bir sorun da olmasın». İki iş görülür:

1. ƏLAVƏ (`exams.wizard`): rel ipucu (ulduzlu sahələr), dərc statusu sətri
   (`is_active` forma tərəfindən söndürülüb — toggle deyil, status göstərilir),
   addım validasiyası mesajları və yaratma-təsdiq icmalının sətirləri. Sonuncu
   iki qrup əvvəl JS-də çılpaq `gettext()` idi və `djangojs` kataloqunda YOX idi
   — EN/RU/TR-də azərbaycanca görünürdü. İndi `profile.html`-dəki `json_script`
   lüğətindən (`EXAM_WIZARD_I18N` / `EXAM_CREATE_EDIT_MODAL_I18N`) gəlir.

2. DÜZƏLİŞ (mövcud msgstr-lər): kataloq auditi sehrbazda GÖRÜNƏN korlanmış
   tərcümələr tapdı — məs. «İmtahan yarat» düyməsi RU/TR-də «Создать курс» /
   «Kurs Oluştur», modal başlığı «Meta created at», «Sual təkrarını azalt»
   açarı «Delete question bank». Yalnız sadalanan (dil, kontekst, msgid)
   üçlükləri dəyişir.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
əlavə/düzəliş edir və idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən
fərqlidir — i18n qapısı `msgstr == msgid` sətrini «tərcümə olunmamış» sayır.

İstifadə:  python scripts/i18n_fill_exam_wizard_redesign_2026_09_11.py
           python manage.py compilemessages
"""

import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

WZ = "exams.wizard"

# msgid = AZ mətn; msgstr: az = msgid, digərləri lüğətdən.
ENTRIES = {
    WZ: {
        # ── şablon (rel, dərc statusu) ──
        "Sehrbaz addımları": {"en": "Wizard steps", "ru": "Шаги мастера", "tr": "Sihirbaz adımları"},
        "Ulduzlu (*) sahələr mütləqdir. Qalan parametrləri sonra «Redaktə» ilə də dəyişə bilərsiniz.": {
            "en": "Fields marked with * are required. Everything else can also be changed later via “Edit”.",
            "ru": "Поля со звёздочкой (*) обязательны. Остальные параметры можно изменить и позже через «Редактировать».",
            "tr": "Yıldızlı (*) alanlar zorunludur. Diğer ayarları daha sonra «Düzenle» ile de değiştirebilirsiniz.",
        },
        "Dərc statusu": {"en": "Publish status", "ru": "Статус публикации", "tr": "Yayın durumu"},
        "Aktiv": {"en": "Active", "ru": "Активен", "tr": "Etkin"},
        "Qaralama": {"en": "Draft", "ru": "Черновик", "tr": "Taslak"},
        "Status bu formadan dəyişmir — imtahan səhifəsindəki «Aktiv et» / «Deaktiv et» düyməsi ilə idarə olunur.": {
            "en": "The status is not changed from this form — use the “Activate” / “Deactivate” button on the exam page.",
            "ru": "Статус из этой формы не меняется — используйте кнопку «Активировать» / «Деактивировать» на странице экзамена.",
            "tr": "Durum bu formdan değişmez — sınav sayfasındaki «Aktifleştir» / «Devre dışı bırak» düğmesiyle yönetilir.",
        },
        "İmtahan qaralama kimi yaradılır. Suallar əlavə edildikdən sonra imtahan səhifəsindəki «Aktiv et» düyməsi ilə tələbələrə açılır.": {
            "en": "The exam is created as a draft. After adding questions, open it to students with the “Activate” button on the exam page.",
            "ru": "Экзамен создаётся как черновик. После добавления вопросов откройте его студентам кнопкой «Активировать» на странице экзамена.",
            "tr": "Sınav taslak olarak oluşturulur. Sorular eklendikten sonra sınav sayfasındaki «Aktifleştir» düğmesiyle öğrencilere açılır.",
        },
        # ── addım validasiyası (exam_wizard.js, EXAM_WIZARD_I18N) ──
        "Kateqoriyanı seçin.": {"en": "Choose a category.", "ru": "Выберите категорию.", "tr": "Kategori seçin."},
        "Fənn seçilməlidir.": {
            "en": "A subject must be selected.",
            "ru": "Нужно выбрать предмет.",
            "tr": "Ders seçilmelidir.",
        },
        "Başlama vaxtını seçin.": {
            "en": "Choose the start time.",
            "ru": "Укажите время начала.",
            "tr": "Başlangıç zamanını seçin.",
        },
        "Bitmə vaxtını seçin.": {
            "en": "Choose the end time.",
            "ru": "Укажите время окончания.",
            "tr": "Bitiş zamanını seçin.",
        },
        "İmtahanın ümumi müddətini yazın.": {
            "en": "Enter the total exam duration.",
            "ru": "Укажите общую длительность экзамена.",
            "tr": "Sınavın toplam süresini yazın.",
        },
        # ── yaratma təsdiqi icmalı (form.js, EXAM_CREATE_EDIT_MODAL_I18N) ──
        "İmtahanı təsdiqlə": {"en": "Confirm the exam", "ru": "Подтвердите экзамен", "tr": "Sınavı onayla"},
        "İmtahan aşağıdakı məlumatlarla yaradılıb təyin olunacaq.": {
            "en": "The exam will be created and assigned with the details below.",
            "ru": "Экзамен будет создан и назначен с указанными ниже данными.",
            "tr": "Sınav aşağıdaki bilgilerle oluşturulup atanacak.",
        },
        "Təsdiqlə və yarat": {"en": "Confirm and create", "ru": "Подтвердить и создать", "tr": "Onayla ve oluştur"},
        "hesablanır…": {"en": "calculating…", "ru": "подсчёт…", "tr": "hesaplanıyor…"},
        "İmtahan adı": {"en": "Exam title", "ru": "Название экзамена", "tr": "Sınav adı"},
        "Tip": {"en": "Type", "ru": "Тип", "tr": "Tür"},
        "Kateqoriya": {"en": "Category", "ru": "Категория", "tr": "Kategori"},
        "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
        "Başlama": {"en": "Start", "ru": "Начало", "tr": "Başlangıç"},
        "Bitmə": {"en": "End", "ru": "Окончание", "tr": "Bitiş"},
        "Müddət (dəq)": {"en": "Duration (min)", "ru": "Длительность (мин)", "tr": "Süre (dk)"},
        "Sual sayı": {"en": "Question count", "ru": "Число вопросов", "tr": "Soru sayısı"},
        "Nəzarət": {"en": "Proctoring", "ru": "Контроль", "tr": "Gözetim"},
        "Deaktiv": {"en": "Off", "ru": "Выключен", "tr": "Kapalı"},
        "Alıcılar": {"en": "Recipients", "ru": "Получатели", "tr": "Atananlar"},
        "Hamıya açıq": {"en": "Open to everyone", "ru": "Открыт для всех", "tr": "Herkese açık"},
        "Qruplar": {"en": "Groups", "ru": "Группы", "tr": "Gruplar"},
        "Fərdi tələbələr": {"en": "Individual students", "ru": "Отдельные студенты", "tr": "Bireysel öğrenciler"},
        "Seçilməyib": {"en": "Not selected", "ru": "Не выбрано", "tr": "Seçilmedi"},
        "Tələbə sayı (ümumi)": {"en": "Students (total)", "ru": "Студентов (всего)", "tr": "Öğrenci sayısı (toplam)"},
    },
}

# (kontekst, msgid) → {dil: düzgün msgstr}. Yalnız korlanmış sətirlər.
FIXES = {
    ("exams.template.create_edit_exam", "heading_create_exam"): {
        "ru": "Создать новый экзамен",
        "tr": "Yeni sınav oluştur",
    },
    ("exams.template.create_edit_exam", "heading_edit_exam"): {"ru": "Редактировать экзамен", "tr": "Sınavı düzenle"},
    ("exams.template.create_exam_modal", "heading_create_exam"): {
        "ru": "Создать новый экзамен",
        "tr": "Yeni sınav oluştur",
    },
    ("exams.template.create_exam_modal", "aria_close"): {"ru": "Закрыть", "tr": "Kapat"},
    ("exams.template.create_exam_modal", "loading_form"): {"ru": "Форма загружается…", "tr": "Form yükleniyor…"},
    ("exams.template.create_exam_modal_form", "action_create"): {"ru": "Создать экзамен", "tr": "Sınav oluştur"},
    ("exams.template.create_exam_modal_form", "action_cancel"): {"ru": "Отменить"},
    ("exams.template.create_exam_modal_form", "search_group"): {"ru": "Поиск группы…"},
    ("exams.template.create_exam_modal_form", "search_name_or_username"): {
        "ru": "Имя пользователя или e-mail",
        "tr": "Kullanıcı adı veya e-posta",
    },
    ("exams.form.exam.label", "Sual təkrarını azalt"): {
        "en": "Reduce question repetition",
        "ru": "Уменьшить повторение вопросов",
        "tr": "Soru tekrarını azalt",
    },
    ("exams.form.exam.placeholder", "select_organization"): {"en": "Organization"},
    ("exams.model.exam.choice.exam_type_extended", "practice"): {"ru": "Практика", "tr": "Alıştırma"},
    ("exams.model.exam.choice.exam_type_extended", "quiz"): {"tr": "Quiz"},
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
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    fixed = 0
    for (ctx, msgid), per_lang in FIXES.items():
        new = per_lang.get(lang)
        if new is None:
            continue
        # Tək-sətirli msgstr-ə düzəliş; blok tapılmasa səssiz keçir (drift yox).
        pattern = re.compile(
            r'(msgctxt "' + re.escape(esc(ctx)) + r'"\nmsgid "' + re.escape(esc(msgid)) + r'"\nmsgstr ")([^"\n]*)(")',
        )
        text, count = pattern.subn(lambda m, rep=esc(new): m.group(1) + rep + m.group(3), text, count=1)
        fixed += count

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
    if blocks or fixed:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry, {fixed} düzəliş")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)

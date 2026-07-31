#!/usr/bin/env python3
"""EMSArena i18n — sual bankı redesign-i (2026-07-30/31) sətirləri. İdempotent.

Bank yaratma kartının yeni sahələri (kataloq fənni, göndərən müəllim, imtahan
növü), göndərişlər bölməsinin axtarışlı filtrləri, review sual siyahısının
lazy-load toolbar-ı (filtr pilləri + axtarış), detal workbench redaktəsi,
silmə modalı və yeni validasiya mesajları — 4 dildə.

Əlavə: köhnədən kataloqda boş qalmış legacy sətirlər də doldurulur:
  * accounts.first_login — 4 dildə də boş idi (EN/RU/TR istifadəçi AZ görürdü);
  * registrar/organizations EN-msgid seçimləri (Bachelor, Mandatory, …) —
    AZ/RU/TR istifadəçi ingiliscə görürdü;
  * az kataloqunda AZ-msgid boş girişlər (registrar.journal/correction/notify)
    — msgstr = msgid (kosmetik tamlıq).

İstifadə:  python scripts/i18n_fill_question_bank_redesign.py
Sonra:     msgfmt ilə .mo kompilyasiyası (deploy skripti/CI onsuz da edir).
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

BANK_CTX = "exams.template.question_bank_list"
SECTION_CTX = "accounts.profile.question_submissions"
TEMPLATE_CTX = "exams.template.question_submission"
VIEW_ERR_CTX = "exams.view.question_submission.error"
SERVICE_ERR_CTX = "exams.service.question_submission.error"

# ctx -> msgid -> {"en": ..., "ru": ..., "tr": ...}   (az üçün msgstr = msgid)
ENTRIES = {
    BANK_CTX: {
        "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
        "fənn axtar…": {"en": "search subject…", "ru": "поиск предмета…", "tr": "ders ara…"},
        "Kataloqdakı fənlərdən axtarıb seçin (opsional).": {
            "en": "Search and pick from the catalogue subjects (optional).",
            "ru": "Найдите и выберите предмет из каталога (необязательно).",
            "tr": "Katalogdaki derslerden arayıp seçin (isteğe bağlı).",
        },
        "Sualı göndərən müəllim": {
            "en": "Submitting teacher",
            "ru": "Преподаватель, приславший вопросы",
            "tr": "Soruları gönderen öğretmen",
        },
        "müəllim axtar…": {"en": "search teacher…", "ru": "поиск преподавателя…", "tr": "öğretmen ara…"},
        "Bank hansı müəllimin suallarından yaranır (opsional).": {
            "en": "Which teacher's questions this bank is built from (optional).",
            "ru": "Из чьих вопросов формируется банк (необязательно).",
            "tr": "Banka hangi öğretmenin sorularından oluşuyor (isteğe bağlı).",
        },
        "İmtahan növü": {"en": "Exam type", "ru": "Тип экзамена", "tr": "Sınav türü"},
        "Ümumi (təyinatsız)": {"en": "General (unassigned)", "ru": "Общий (без назначения)", "tr": "Genel (atanmamış)"},
        "Bank hansı imtahan üçün toplanır: Final, Midterm və ya Quiz.": {
            "en": "What exam the bank is collected for: Final, Midterm or Quiz.",
            "ru": "Для какого экзамена собирается банк: Final, Midterm или Quiz.",
            "tr": "Banka hangi sınav için toplanıyor: Final, Midterm veya Quiz.",
        },
        "Sual formatı": {"en": "Question format", "ru": "Формат вопросов", "tr": "Soru formatı"},
        "Bank yalnız imtahan mərkəzinə görünür.": {
            "en": "The bank is visible only to the exam centre.",
            "ru": "Банк виден только экзаменационному центру.",
            "tr": "Banka yalnızca sınav merkezine görünür.",
        },
        "Bank adı, fənn və ya müəllim üzrə axtar...": {
            "en": "Search by bank name, subject or teacher...",
            "ru": "Поиск по названию банка, предмету или преподавателю...",
            "tr": "Banka adı, ders veya öğretmene göre ara...",
        },
        "İmtahan növü filtri": {"en": "Exam type filter", "ru": "Фильтр по типу экзамена", "tr": "Sınav türü filtresi"},
    },
    SECTION_CTX: {
        "Suallar «%(bank)s» bankına əlavə olunub": {
            "en": "Questions were added to the “%(bank)s” bank",
            "ru": "Вопросы добавлены в банк «%(bank)s»",
            "tr": "Sorular «%(bank)s» bankasına eklendi",
        },
        "fakültə axtar…": {"en": "search faculty…", "ru": "поиск факультета…", "tr": "fakülte ara…"},
        "kafedra axtar…": {"en": "search department…", "ru": "поиск кафедры…", "tr": "bölüm ara…"},
        "müəllim axtar…": {"en": "search teacher…", "ru": "поиск преподавателя…", "tr": "öğretmen ara…"},
    },
    TEMPLATE_CTX: {
        "Boş saxlasanız suallar göndərişin fənni və imtahan növü ilə yeni banka yazılacaq. ★ — fənnə/növə uyğun banklar.": {
            "en": "If left empty, the questions are saved to a new bank with the submission's subject and exam type. ★ — banks matching the subject/type.",
            "ru": "Если оставить пустым, вопросы будут записаны в новый банк с предметом и типом экзамена отправки. ★ — банки, соответствующие предмету/типу.",
            "tr": "Boş bırakırsanız sorular gönderimin dersi ve sınav türüyle yeni bir bankaya yazılır. ★ — derse/türe uyan bankalar.",
        },
        "Bu bank artıq mövcud deyil.": {
            "en": "This bank no longer exists.",
            "ru": "Этот банк больше не существует.",
            "tr": "Bu banka artık mevcut değil.",
        },
        "Bu qrup üçün fənn yoxdur": {
            "en": "No subjects for this group",
            "ru": "Для этой группы нет предметов",
            "tr": "Bu grup için ders yok",
        },
        "Bu şərtlərə uyğun sual tapılmadı.": {
            "en": "No questions match these filters.",
            "ru": "По заданным условиям вопросов не найдено.",
            "tr": "Bu koşullara uygun soru bulunamadı.",
        },
        "Bəli, sil": {"en": "Yes, delete", "ru": "Да, удалить", "tr": "Evet, sil"},
        "Daha çox yüklənir…": {"en": "Loading more…", "ru": "Загружается ещё…", "tr": "Daha fazlası yükleniyor…"},
        "Dil, fənn, imtahan növü və qrup mütləqdir": {
            "en": "Language, subject, exam type and group are required",
            "ru": "Язык, предмет, тип экзамена и группа обязательны",
            "tr": "Dil, ders, sınav türü ve grup zorunludur",
        },
        "Düzgün cavab": {"en": "Correct answer", "ru": "Правильный ответ", "tr": "Doğru cevap"},
        "Göndərişi redaktə et": {"en": "Edit submission", "ru": "Редактировать отправку", "tr": "Gönderimi düzenle"},
        "Hamısı": {"en": "All", "ru": "Все", "tr": "Tümü"},
        "Növü seçin…": {"en": "Select type…", "ru": "Выберите тип…", "tr": "Türü seçin…"},
        "Sual filtri": {"en": "Question filter", "ru": "Фильтр вопросов", "tr": "Soru filtresi"},
        "Sual və ya variant mətnində axtar…": {
            "en": "Search in question or option text…",
            "ru": "Поиск по тексту вопроса или варианта…",
            "tr": "Soru veya seçenek metninde ara…",
        },
        "Suallar hansı imtahan üçündür — mərkəz bankı bu təyinatla yaradır.": {
            "en": "What exam the questions are for — the centre creates the bank with this designation.",
            "ru": "Для какого экзамена вопросы — центр создаёт банк с этим назначением.",
            "tr": "Sorular hangi sınav için — merkez bankayı bu atamayla oluşturur.",
        },
        "Suallarda axtar": {"en": "Search questions", "ru": "Поиск по вопросам", "tr": "Sorularda ara"},
        "Sualları düzəldin və ya yenidən yükləyin, önizləyin — sonra təkrar göndərin.": {
            "en": "Fix the questions or upload them again, preview — then resubmit.",
            "ru": "Исправьте вопросы или загрузите заново, просмотрите — затем отправьте повторно.",
            "tr": "Soruları düzeltin veya yeniden yükleyin, önizleyin — sonra tekrar gönderin.",
        },
        "Təmiz": {"en": "Clean", "ru": "Чистые", "tr": "Temiz"},
        "məs. 5–8-ci suallar mühazirə 3-ə aiddir; final üçün nəzərdə tutulub…": {
            "en": "e.g. questions 5–8 belong to lecture 3; intended for the final…",
            "ru": "напр. вопросы 5–8 относятся к лекции 3; предназначены для финала…",
            "tr": "örn. 5–8. sorular 3. derse aittir; final için hazırlanmıştır…",
        },
        "məs. İnformatika — Final sual toplusu": {
            "en": "e.g. Informatics — Final question set",
            "ru": "напр. Информатика — набор вопросов для финала",
            "tr": "örn. Bilişim — Final soru seti",
        },
        "silinib": {"en": "deleted", "ru": "удалён", "tr": "silindi"},
        "İmtahan növü": {"en": "Exam type", "ru": "Тип экзамена", "tr": "Sınav türü"},
        "İmtina": {"en": "Cancel", "ru": "Отмена", "tr": "Vazgeç"},
    },
    VIEW_ERR_CTX: {
        "Fənni öz fənləriniz arasından seçin (məcburidir).": {
            "en": "Select the subject from your own subjects (required).",
            "ru": "Выберите предмет из своих предметов (обязательно).",
            "tr": "Dersi kendi dersleriniz arasından seçin (zorunlu).",
        },
        "İmtahan növünü seçin (məcburidir).": {
            "en": "Select the exam type (required).",
            "ru": "Выберите тип экзамена (обязательно).",
            "tr": "Sınav türünü seçin (zorunlu).",
        },
    },
    SERVICE_ERR_CTX: {
        "Vizual mənbə artıq əlçatan deyil və ya məzmunla uyğun gəlmir. Müəllim faylı yenidən yükləməlidir.": {
            "en": "The visual source is no longer available or does not match the content. The teacher must upload the file again.",
            "ru": "Визуальный источник больше недоступен или не соответствует содержимому. Преподаватель должен загрузить файл заново.",
            "tr": "Görsel kaynak artık erişilebilir değil veya içerikle uyuşmuyor. Öğretmen dosyayı yeniden yüklemelidir.",
        },
    },
    # ── Legacy: ilk-giriş axını (4 dildə də boş idi) ──
    "accounts.first_login": {
        "Xoş gəlmisiniz": {"en": "Welcome", "ru": "Добро пожаловать", "tr": "Hoş geldiniz"},
        "Email ünvanı": {"en": "Email address", "ru": "Адрес электронной почты", "tr": "E-posta adresi"},
        "Təsdiq kodu göndər": {
            "en": "Send verification code",
            "ru": "Отправить код подтверждения",
            "tr": "Doğrulama kodu gönder",
        },
        "Kod %(email)s ünvanına göndərildi.": {
            "en": "The code was sent to %(email)s.",
            "ru": "Код отправлен на %(email)s.",
            "tr": "Kod %(email)s adresine gönderildi.",
        },
        "Yeni parol": {"en": "New password", "ru": "Новый пароль", "tr": "Yeni şifre"},
        "Yeni parol (təkrar)": {
            "en": "New password (repeat)",
            "ru": "Новый пароль (повторно)",
            "tr": "Yeni şifre (tekrar)",
        },
        "Kodu yenidən göndər": {"en": "Resend code", "ru": "Отправить код повторно", "tr": "Kodu yeniden gönder"},
    },
}

# ── Legacy: EN-msgid seçimləri (AZ/RU/TR boş idi; en üçün msgstr = msgid) ──
EN_SOURCE_ENTRIES = {
    "organizations.unit_type": {
        "specialty": {"az": "İxtisas", "ru": "Специальность", "tr": "Uzmanlık"},
    },
    "registrar.degree": {
        "Bachelor": {"az": "Bakalavr", "ru": "Бакалавриат", "tr": "Lisans"},
    },
    "registrar.model.program.meta": {
        "programs": {"az": "proqramlar", "ru": "программы", "tr": "programlar"},
    },
    "registrar.model.subject.meta": {
        "subject": {"az": "fənn", "ru": "предмет", "tr": "ders"},
        "subjects": {"az": "fənlər", "ru": "предметы", "tr": "dersler"},
    },
    "registrar.enrollment_kind": {
        "Mandatory": {"az": "Məcburi", "ru": "Обязательный", "tr": "Zorunlu"},
        "Elective": {"az": "Seçmə", "ru": "По выбору", "tr": "Seçmeli"},
    },
    "registrar.model.offering.meta": {
        "course offerings": {"az": "fənn açılışları", "ru": "открытия предметов", "tr": "ders açılışları"},
    },
    "registrar.enrollment_status": {
        "Completed": {"az": "Tamamlanıb", "ru": "Завершено", "tr": "Tamamlandı"},
        "Dropped": {"az": "İmtina edilib", "ru": "Прекращено", "tr": "Bırakıldı"},
    },
    "registrar.model.enrollment.meta": {
        "enrollments": {"az": "fənnə yazılmalar", "ru": "записи на предметы", "tr": "ders kayıtları"},
    },
}

# ── Legacy: yalnız az kataloqunda boş qalan AZ-msgid girişləri (msgstr=msgid).
# (None)-ctx kitabxana sətirlərinə TOXUNMURUQ — boş qalanda Django öz core az
# kataloquna düşür; identity yazmaq həmin fallback-ı pozardı. Ay adları da
# core-a buraxılır.
AZ_IDENTITY_CTX_PREFIXES = (
    "registrar.journal",
    "registrar.correction",
    "registrar.notify",
)


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _append_missing(text, ctx, msgid, msgstr, blocks):
    probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
    if probe in text:
        return 0
    blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    return 1


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            msgstr = msgid if lang == "az" else translations[lang]
            added += _append_missing(text, ctx, msgid, msgstr, blocks)
    for ctx, messages in EN_SOURCE_ENTRIES.items():
        for msgid, translations in messages.items():
            msgstr = msgid if lang == "en" else translations[lang]
            added += _append_missing(text, ctx, msgid, msgstr, blocks)

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} yeni giriş")


def _parse_block(block):
    """Po blokundan (msgctxt, msgid, msgstr_boşdur?, fuzzy?, plural?) çıxarır.

    Bükülmüş (wrapped) msgid-ləri birləşdirir. Yalnız oxumaq üçündür — yazma
    blok mətnini lokal şəkildə yenidən qurur (qlobal re-wrap YOXDUR).
    """
    lines = block.split("\n")
    ctx = msgid = None
    fuzzy = plural = False
    msgstr_empty = True
    state = None
    parts = {"msgctxt": [], "msgid": [], "msgstr": []}
    for line in lines:
        if line.startswith("#,"):
            fuzzy = fuzzy or "fuzzy" in line
        elif line.startswith("msgid_plural"):
            plural = True
            state = None
        elif line.startswith("msgctxt "):
            state = "msgctxt"
            parts[state].append(line[len("msgctxt ") :])
        elif line.startswith("msgid "):
            state = "msgid"
            parts[state].append(line[len("msgid ") :])
        elif line.startswith("msgstr"):
            state = "msgstr"
            parts[state].append(line.split(" ", 1)[1] if " " in line else '""')
        elif line.startswith('"') and state:
            parts[state].append(line)

    def join(chunks):
        out = ""
        for chunk in chunks:
            chunk = chunk.strip()
            if chunk.startswith('"') and chunk.endswith('"'):
                out += chunk[1:-1]
        return out.replace('\\"', '"').replace("\\\\", "\\")

    if parts["msgctxt"]:
        ctx = join(parts["msgctxt"])
    if parts["msgid"]:
        msgid = join(parts["msgid"])
    msgstr_empty = not join(parts["msgstr"])
    return ctx, msgid, msgstr_empty, fuzzy, plural


def _rewrite_block(block, msgstr):
    """Blokun msgstr hissəsini tək sətirlə əvəz edir, fuzzy bayrağını silir."""
    lines = block.split("\n")
    out = []
    in_msgstr = False
    for line in lines:
        if line.startswith("msgstr"):
            in_msgstr = True
            out.append(f'msgstr "{esc(msgstr)}"')
            continue
        if in_msgstr and line.startswith('"'):
            continue  # köhnə bükülmüş msgstr davamı
        in_msgstr = False
        if line.startswith("#,"):
            flags = [f.strip() for f in line[2:].split(",") if f.strip() and f.strip() != "fuzzy"]
            if flags:
                out.append("#, " + ", ".join(flags))
            continue
        out.append(line)
    return "\n".join(out)


def fill_existing_empty_or_fuzzy():
    """Mövcud amma BOŞ və ya FUZZY (msgfmt-in atdığı, çox vaxt səhv
    avto-uyğunlaşdırılmış) girişləri yerindəcə düzəldir.

    * ENTRIES/EN_SOURCE-dakı cütlər: msgstr düzgün tərcümə ilə əvəzlənir,
      fuzzy silinir;
    * az: AZ_IDENTITY_CTX_PREFIXES altındakı boş girişlərə msgstr = msgid.
    Kontekstsiz kitabxana sətirlərinə toxunulmur (Django core fallback).
    """
    lookup = {}
    for ctx, messages in ENTRIES.items():
        for msgid, tr in messages.items():
            lookup[(ctx, msgid)] = {"az": msgid, **tr}
    for ctx, messages in EN_SOURCE_ENTRIES.items():
        for msgid, tr in messages.items():
            lookup[(ctx, msgid)] = {"en": msgid, **tr}

    for lang in LOCALES:
        path = po_path(lang)
        with open(path, encoding="utf-8") as handle:
            blocks = handle.read().split("\n\n")
        changed = 0
        for index, block in enumerate(blocks):
            if not block.strip() or block.lstrip().startswith("#~"):
                continue
            ctx, msgid, msgstr_empty, fuzzy, plural = _parse_block(block)
            if not ctx or msgid is None or plural:
                continue
            key = (ctx, msgid)
            if key in lookup and (msgstr_empty or fuzzy):
                blocks[index] = _rewrite_block(block, lookup[key][lang])
                changed += 1
            elif lang == "az" and msgstr_empty and not fuzzy and ctx.startswith(AZ_IDENTITY_CTX_PREFIXES):
                blocks[index] = _rewrite_block(block, msgid)
                changed += 1
        if changed:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n\n".join(blocks))
        print(f"{lang}: {changed} boş/fuzzy giriş düzəldildi")


if __name__ == "__main__":
    # Sıra vacibdir: əvvəl mövcud boş/fuzzy girişlər düzəldilir, sonra qalan
    # (heç olmayan) cütlər əlavə olunur — dublikat yaranmır.
    fill_existing_empty_or_fuzzy()
    for locale in LOCALES:
        fill(locale)

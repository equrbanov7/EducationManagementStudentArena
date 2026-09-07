#!/usr/bin/env python3
"""EMSArena i18n — «Müraciətlərim» DETAL MODALININ sətirləri (4 dil). İdempotent.

Detal sağdakı yapışqan sütundan MODAL-a keçdi: yazışma, cavab qutusunun fayl
seçicisi və «göndərilməmiş mətn» xəbərdarlığı yeni mətnlər gətirdi. Bundan
əlavə, fayl qaydası mətnə «bişirilmiş» ölçülərdən (10 MB / 5 fayl / uzantı
siyahısı) yer tutuculara keçdi — köhnə msgid-lər kataloqda qalır, sadəcə
işlədilmir.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və mövcud girişə TOXUNMUR. Yer tutucular (`{n}`, `{mb}`, `%(mb)s`, …)
tərcümədə də EYNİ qalmalıdır (`scripts/check_i18n_catalogs.py` bunu yoxlayır).

İstifadə:  python scripts/i18n_fill_applications_modal.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# ── Şablon: fayl seçicisinin düymə mətni (blocktrans → %(…)s) ───────────────
_TEMPLATE = {
    "Fayl seç — PDF, şəkil, DOCX və ya ZIP · maks. %(mb)s MB · ən çox %(n)s fayl": {
        "en": "Choose a file — PDF, image, DOCX or ZIP · max. %(mb)s MB · up to %(n)s files",
        "ru": "Выберите файл — PDF, изображение, DOCX или ZIP · макс. %(mb)s МБ · до %(n)s файлов",
        "tr": "Dosya seç — PDF, görsel, DOCX veya ZIP · en fazla %(mb)s MB · en çok %(n)s dosya",
    },
}

# ── JS kataloqu: modal, yazışma, fayl qaydaları ─────────────────────────────
_MODAL = {
    "ən son": {"en": "latest", "ru": "последнее", "tr": "en son"},
    "PDF, şəkil, DOCX və ya ZIP · maks. {mb} MB · ən çox {n} fayl": {
        "en": "PDF, image, DOCX or ZIP · max. {mb} MB · up to {n} files",
        "ru": "PDF, изображение, DOCX или ZIP · макс. {mb} МБ · до {n} файлов",
        "tr": "PDF, görsel, DOCX veya ZIP · en fazla {mb} MB · en çok {n} dosya",
    },
    "«{action}» əməli sənəd qəbul etmir — faylları silin və ya başqa əməl seçin.": {
        "en": "“{action}” does not accept documents — remove the files or choose another action.",
        "ru": "«{action}» не принимает документы — удалите файлы или выберите другое действие.",
        "tr": "“{action}” belge kabul etmiyor — dosyaları kaldırın ya da başka bir işlem seçin.",
    },
    "Cavab göndərilməyib": {
        "en": "The reply has not been sent",
        "ru": "Ответ не отправлен",
        "tr": "Yanıt gönderilmedi",
    },
    "Yazdığınız mətn və seçdiyiniz sənədlər hələ göndərilməyib — pəncərəni bağlasanız itəcək. Bağlayaq?": {
        "en": "Your text and the files you picked have not been sent yet — closing the window discards them. Close it?",
        "ru": "Ваш текст и выбранные файлы ещё не отправлены — при закрытии окна они будут потеряны. Закрыть?",
        "tr": "Yazdığınız metin ve seçtiğiniz dosyalar henüz gönderilmedi — pencereyi kapatırsanız kaybolur. Kapatalım mı?",
    },
    "Cavab mətni ən azı {n} simvol olmalıdır — müraciət sahibi məhz bu mətni görəcək.": {
        "en": "The reply must be at least {n} characters — the applicant sees exactly this text.",
        "ru": "Ответ должен содержать не менее {n} символов — заявитель увидит именно этот текст.",
        "tr": "Yanıt metni en az {n} karakter olmalı — başvuru sahibi tam olarak bu metni görecek.",
    },
    "«{name}» {mb} MB-dan böyükdür.": {
        "en": "“{name}” is larger than {mb} MB.",
        "ru": "«{name}» больше {mb} МБ.",
        "tr": "“{name}” {mb} MB’den büyük.",
    },
    "«{name}» dəstəklənmir — icazəli formatlar: {list}.": {
        "en": "“{name}” is not supported — allowed formats: {list}.",
        "ru": "«{name}» не поддерживается — допустимые форматы: {list}.",
        "tr": "“{name}” desteklenmiyor — izin verilen biçimler: {list}.",
    },
    "Bir əməldə ən çoxu {n} fayl əlavə edilə bilər.": {
        "en": "At most {n} files can be attached in one action.",
        "ru": "За одно действие можно приложить не более {n} файлов.",
        "tr": "Bir işlemde en çok {n} dosya eklenebilir.",
    },
}

# ── «Razı deyiləm» (reopen) + tarix aralığı süzgəci ─────────────────────────
_REOPEN = {
    "Cavabdan razı qalmadı — yenidən baxışa göndərdi": {
        "en": "Was not satisfied with the answer — sent back for review",
        "ru": "Не согласился с ответом — вернул на рассмотрение",
        "tr": "Yanıttan memnun kalmadı — yeniden incelemeye gönderdi",
    },
    "Razı deyiləm — yenidən bax": {
        "en": "Not satisfied — review again",
        "ru": "Не согласен — рассмотреть заново",
        "tr": "Memnun değilim — yeniden incele",
    },
    "Razı deyiləm — yenidən baxılsın": {
        "en": "Not satisfied — please review again",
        "ru": "Не согласен — прошу рассмотреть заново",
        "tr": "Memnun değilim — yeniden incelensin",
    },
    "Nə həll olunmadı?": {
        "en": "What was left unresolved?",
        "ru": "Что осталось нерешённым?",
        "tr": "Ne çözülmedi?",
    },
    "Cavab gəldi. Razısınızsa təsdiqləyib bağlayın; problem həll olunmayıbsa səbəbini yazın — "
    "müraciət eyni nömrə ilə həmin şöbəyə qayıdacaq.": {
        "en": "The answer has arrived. Confirm and close it if you are satisfied; if the problem is still "
        "unresolved, write why — the application returns to the same unit under the same number.",
        "ru": "Ответ получен. Если вы согласны — подтвердите и закройте; если проблема не решена, укажите "
        "причину — обращение вернётся в то же подразделение под тем же номером.",
        "tr": "Yanıt geldi. Memnunsanız onaylayıp kapatın; sorun çözülmediyse nedenini yazın — başvuru aynı "
        "numarayla aynı birime geri döner.",
    },
}

_DATES = {
    "Başlanğıc tarix": {"en": "Start date", "ru": "Дата начала", "tr": "Başlangıç tarihi"},
    "Son tarix": {"en": "End date", "ru": "Дата окончания", "tr": "Bitiş tarihi"},
    "Tarix aralığını təmizlə": {
        "en": "Clear the date range",
        "ru": "Очистить диапазон дат",
        "tr": "Tarih aralığını temizle",
    },
}

ENTRIES = {"applications": {**_TEMPLATE, **_MODAL, **_REOPEN, **_DATES}}


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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n'
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

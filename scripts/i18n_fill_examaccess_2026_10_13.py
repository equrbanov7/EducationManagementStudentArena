#!/usr/bin/env python3
"""EMSArena i18n — gecə auditi 2026-10-13 (examaccess): final/midterm giriş zənciri.

Əlavə olunan mətnlər:
  * `exams.network` — final/midterm yalnız universitet şəbəkəsindən (servis mesajı + 403 səhifəsi);
  * `exams.final_center.entry` — kabinet PIN-i ilə davam edən cəhdə yenidən girişin rəddi
    (köhnə PIN etibarsızdır / başqa kompüter).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_examaccess_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = [lang for lang in ("az", "en", "ru", "tr", "de") if os.path.isdir(os.path.join(BASE, "locale", lang))]

NET = "exams.network"
ENTRY = "exams.final_center.entry"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    NET: {
        (
            "Final və midterm imtahanları yalnız universitet şəbəkəsindən verilir. "
            "Universitetin daxili şəbəkəsinə (imtahan zalı kompüterinə) qoşulun və səhifəni yeniləyin."
        ): {
            "en": (
                "Final and midterm exams can only be taken from the university network. Connect to the "
                "university's internal network (an exam hall computer) and reload the page."
            ),
            "ru": (
                "Финальные и промежуточные экзамены сдаются только из сети университета. Подключитесь к "
                "внутренней сети университета (компьютер экзаменационного зала) и обновите страницу."
            ),
            "tr": (
                "Final ve ara sınavlar yalnızca üniversite ağından verilebilir. Üniversitenin iç ağına (sınav "
                "salonu bilgisayarına) bağlanın ve sayfayı yenileyin."
            ),
            "de": (
                "Abschluss- und Zwischenprüfungen können nur aus dem Universitätsnetz abgelegt werden. "
                "Verbinden Sie sich mit dem internen Netz der Universität (Prüfungsraum-Computer) und laden "
                "Sie die Seite neu."
            ),
        },
        "Yalnız universitet şəbəkəsindən": {
            "en": "University network only",
            "ru": "Только из сети университета",
            "tr": "Yalnızca üniversite ağından",
            "de": "Nur aus dem Universitätsnetz",
        },
        "Final və midterm imtahanı": {
            "en": "Final and midterm exam",
            "ru": "Финальный и промежуточный экзамен",
            "tr": "Final ve ara sınav",
            "de": "Abschluss- und Zwischenprüfung",
        },
        "Cavablarınız serverdə saxlanılıb — daxili şəbəkədən imtahan qaldığı yerdən davam edəcək.": {
            "en": "Your answers are saved on the server — from the internal network the exam continues where you left off.",
            "ru": "Ваши ответы сохранены на сервере — из внутренней сети экзамен продолжится с того же места.",
            "tr": "Cevaplarınız sunucuda kayıtlı — iç ağdan sınav kaldığınız yerden devam edecek.",
            "de": "Ihre Antworten sind auf dem Server gespeichert — im internen Netz geht die Prüfung dort weiter, wo Sie aufgehört haben.",
        },
        "Universitet şəbəkəsi": {
            "en": "University network",
            "ru": "Сеть университета",
            "tr": "Üniversite ağı",
            "de": "Universitätsnetz",
        },
        "Səhifəni yenilə": {
            "en": "Reload the page",
            "ru": "Обновить страницу",
            "tr": "Sayfayı yenile",
            "de": "Seite neu laden",
        },
        "Şəbəkə yoxlaması serverdə aparılır və rəd hadisəsi jurnalda qeyd olunur.": {
            "en": "The network check runs on the server and every refusal is recorded in the log.",
            "ru": "Проверка сети выполняется на сервере, каждый отказ записывается в журнал.",
            "tr": "Ağ denetimi sunucuda yapılır ve her ret kayda geçer.",
            "de": "Die Netzprüfung erfolgt auf dem Server, jede Ablehnung wird protokolliert.",
        },
    },
    ENTRY: {
        "Sizə nəzarətçi tərəfindən yeni PIN verilib — köhnə PIN artıq etibarsızdır. Yeni PIN ilə daxil olun.": {
            "en": "The invigilator has issued you a new PIN — the old PIN is no longer valid. Sign in with the new PIN.",
            "ru": "Наблюдатель выдал вам новый PIN — старый PIN больше не действует. Войдите с новым PIN.",
            "tr": "Gözetmen size yeni bir PIN verdi — eski PIN artık geçersiz. Yeni PIN ile giriş yapın.",
            "de": "Die Aufsicht hat Ihnen eine neue PIN ausgestellt — die alte PIN ist ungültig. Melden Sie sich mit der neuen PIN an.",
        },
        (
            "İmtahanınız başqa kompüterdə davam edir. Kompüteri dəyişmək üçün nəzarətçidən yeni PIN istəyin — "
            "imtahan qaldığı yerdən davam edəcək."
        ): {
            "en": (
                "Your exam is in progress on another computer. To switch computers, ask the invigilator for a new "
                "PIN — the exam will continue where you left off."
            ),
            "ru": (
                "Ваш экзамен продолжается на другом компьютере. Чтобы сменить компьютер, попросите у наблюдателя "
                "новый PIN — экзамен продолжится с того же места."
            ),
            "tr": (
                "Sınavınız başka bir bilgisayarda devam ediyor. Bilgisayar değiştirmek için gözetmenden yeni PIN "
                "isteyin — sınav kaldığınız yerden devam edecek."
            ),
            "de": (
                "Ihre Prüfung läuft auf einem anderen Computer. Um den Computer zu wechseln, bitten Sie die Aufsicht "
                "um eine neue PIN — die Prüfung geht dort weiter, wo Sie aufgehört haben."
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
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("en") or translations.get("az", msgid)
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

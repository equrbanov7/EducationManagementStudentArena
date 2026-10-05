#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-05 (UX review): autosave vəziyyət sətri + stilli 503 səhifəsi.

Əlavə olunan mətnlər:
  * `exams.template.take_exam`: imtahan zamanı autosave «server yüklü / bağlantı yoxdur / bərpa /
    konflikt» daimi vəziyyət sətri (take_exam/sync_status.js, script_data.py);
  * `core.error.503`: «Server hazırda çox yüklüdür» stilli xəta səhifəsi (templates/errors/503.html).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_05_ux_review.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


TE = "exams.template.take_exam"
E503 = "core.error.503"

_TAKE_EXAM = [
    _t(
        "Server hazırda çox yüklüdür. Cavablarınız brauzerdə saxlanılır və avtomatik yenidən göndəriləcək — "
        "səhifəni bağlamayın.",
        "The server is very busy right now. Your answers are kept in the browser and will be sent again "
        "automatically — do not close the page.",
        "Сервер сейчас сильно загружен. Ваши ответы сохранены в браузере и будут отправлены повторно "
        "автоматически — не закрывайте страницу.",
        "Sunucu şu anda çok yoğun. Cevaplarınız tarayıcıda saklanıyor ve otomatik olarak yeniden "
        "gönderilecek — sayfayı kapatmayın.",
    ),
    _t(
        "Cavablar hələ serverə yazılmayıb. Onlar brauzerdə saxlanılır və bağlantı bərpa olunanda avtomatik "
        "göndəriləcək — internet bağlantısını yoxlayın, səhifəni bağlamayın.",
        "Your answers have not been saved to the server yet. They are kept in the browser and will be sent "
        "automatically once the connection is back — check your internet connection and do not close the page.",
        "Ответы ещё не записаны на сервер. Они сохранены в браузере и будут отправлены автоматически, как "
        "только связь восстановится — проверьте подключение к интернету и не закрывайте страницу.",
        "Cevaplar henüz sunucuya kaydedilmedi. Tarayıcıda saklanıyor ve bağlantı geri geldiğinde otomatik "
        "olarak gönderilecek — internet bağlantınızı kontrol edin, sayfayı kapatmayın.",
    ),
    _t(
        "Cavablarınız yenidən saxlanılır.",
        "Your answers are being saved again.",
        "Ваши ответы снова сохраняются.",
        "Cevaplarınız yeniden kaydediliyor.",
    ),
    _t(
        "Bu imtahan başqa tabda yenilənib — cavablar bu tabdan saxlanılmır. Səhifəni yeniləyin.",
        "This exam was updated in another tab — answers are not saved from this tab. Reload the page.",
        "Этот экзамен обновлён в другой вкладке — ответы из этой вкладки не сохраняются. " "Обновите страницу.",
        "Bu sınav başka bir sekmede güncellendi — cevaplar bu sekmeden kaydedilmiyor. Sayfayı yenileyin.",
    ),
]

_E503 = [
    _t("Server məşğuldur", "Server busy", "Сервер занят", "Sunucu meşgul"),
    _t("Müvəqqəti yüklənmə", "Temporary load", "Временная нагрузка", "Geçici yoğunluk"),
    _t(
        "Server hazırda çox yüklüdür",
        "The server is very busy right now",
        "Сервер сейчас сильно загружен",
        "Sunucu şu anda çok yoğun",
    ),
    _t(
        "Eyni anda çoxlu istifadəçi daxil olub. Bir neçə saniyə gözləyib səhifəni yenidən yükləyin — "
        "adətən dərhal açılır.",
        "Many users are online at the same time. Wait a few seconds and reload the page — it usually "
        "opens right away.",
        "Одновременно зашло много пользователей. Подождите несколько секунд и обновите страницу — "
        "обычно она открывается сразу.",
        "Aynı anda çok sayıda kullanıcı giriş yaptı. Birkaç saniye bekleyip sayfayı yeniden yükleyin — "
        "genellikle hemen açılır.",
    ),
    _t(
        "Əməliyyat yerinə yetirilmədi, çünki server hazırda çox yüklüdür. Bir neçə saniyə gözləyib əvvəlki "
        "səhifəyə qayıdın və əməliyyatı təkrarlayın.",
        "The action was not completed because the server is very busy right now. Wait a few seconds, go "
        "back to the previous page and repeat the action.",
        "Действие не выполнено, потому что сервер сейчас сильно загружен. Подождите несколько секунд, "
        "вернитесь на предыдущую страницу и повторите действие.",
        "İşlem tamamlanamadı çünkü sunucu şu anda çok yoğun. Birkaç saniye bekleyip önceki sayfaya dönün "
        "ve işlemi tekrarlayın.",
    ),
    _t("Yenidən cəhd et", "Try again", "Повторить попытку", "Tekrar dene"),
    _t(
        "Problem bir neçə dəqiqədən çox davam edərsə, RİM-ə müraciət edin.",
        "If the problem lasts more than a few minutes, contact the RİM.",
        "Если проблема не исчезает дольше нескольких минут, обратитесь в RİM.",
        "Sorun birkaç dakikadan uzun sürerse RİM'e başvurun.",
    ),
]

_START = [
    _t(
        "Müddət: %(minutes)s dəq",
        "Duration: %(minutes)s min",
        "Длительность: %(minutes)s мин",
        "Süre: %(minutes)s dk",
    ),
]

ENTRIES = {
    "exams.start_confirm": {row["en"]: row for row in _START},  # bu şablonda msgid İNGİLİSCƏdir
    TE: {row["az"]: row for row in _TAKE_EXAM},
    E503: {row["az"]: row for row in _E503},
}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
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

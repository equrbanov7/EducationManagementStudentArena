#!/usr/bin/env python3
"""EMSArena i18n — kurs resursu yükləməsi (tip üzrə format/ölçü, video) 2026-10-19.

Əlavə olunan mətnlər (hamısı ``django`` domeni):
  * `courses.resource_type` — resurs tiplərinin adları xəta mesajlarında (`apps/courses/resource_upload.py`);
  * `courses.resource_upload` — tip üzrə ipucu, server xətaları (`resource_upload.py`, `forms.py`,
    `views/teacher/resources.py`), modalın JS mətnləri (`partials/_resource_form_modal.html` data-atributları),
    video oynadıcı (`partials/_resource_video.html`, `_topic_accordion.html`).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan
blokları əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra
`compilemessages -i .claude -i venv`. `{...}` yer tutucuları `.format()` ilə doldurulur — tərcümədə saxlanmalıdır.

İstifadə:  python scripts/i18n_fill_course_resources_2026_10_19.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

TYPE = "courses.resource_type"
UPLOAD = "courses.resource_upload"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    TYPE: {
        "Fayl": {"en": "File", "ru": "Файл", "tr": "Dosya", "de": "Datei"},
        "Link": {"en": "Link", "ru": "Ссылка", "tr": "Bağlantı", "de": "Link"},
        "Video": {"en": "Video", "ru": "Видео", "tr": "Video", "de": "Video"},
        "Sənəd": {"en": "Document", "ru": "Документ", "tr": "Belge", "de": "Dokument"},
    },
    UPLOAD: {
        "Dəstəklənən formatlar: {formats} · maks. {max_mb} MB": {
            "en": "Supported formats: {formats} · max. {max_mb} MB",
            "ru": "Поддерживаемые форматы: {formats} · макс. {max_mb} МБ",
            "tr": "Desteklenen biçimler: {formats} · en fazla {max_mb} MB",
            "de": "Unterstützte Formate: {formats} · max. {max_mb} MB",
        },
        "iPhone videosu: mümkünsə MP4 seçin (MOV bəzi brauzerlərdə oynamır)": {
            "en": "iPhone video: choose MP4 if possible (MOV does not play in some browsers)",
            "ru": "Видео с iPhone: по возможности выбирайте MP4 (MOV воспроизводится не во всех браузерах)",
            "tr": "iPhone videosu: mümkünse MP4 seçin (MOV bazı tarayıcılarda oynatılmaz)",
            "de": "iPhone-Video: nach Möglichkeit MP4 wählen (MOV läuft nicht in allen Browsern)",
        },
        "Bu fayl üçün «{kind}» tipini seçin.": {
            "en": "Choose the «{kind}» type for this file.",
            "ru": "Для этого файла выберите тип «{kind}».",
            "tr": "Bu dosya için «{kind}» türünü seçin.",
            "de": "Wählen Sie für diese Datei den Typ «{kind}».",
        },
        "(uzantısız)": {
            "en": "(no extension)",
            "ru": "(без расширения)",
            "tr": "(uzantısız dosya)",
            "de": "(ohne Endung)",
        },
        "Bu format «{kind}» üçün qəbul edilmir: {ext}. İcazə verilənlər: {formats}": {
            "en": "This format is not accepted for «{kind}»: {ext}. Allowed: {formats}",
            "ru": "Этот формат не принимается для «{kind}»: {ext}. Разрешены: {formats}",
            "tr": "Bu biçim «{kind}» için kabul edilmiyor: {ext}. İzin verilenler: {formats}",
            "de": "Dieses Format ist für «{kind}» nicht zulässig: {ext}. Erlaubt: {formats}",
        },
        "Fayl boşdur.": {
            "en": "The file is empty.",
            "ru": "Файл пуст.",
            "tr": "Dosya boş.",
            "de": "Die Datei ist leer.",
        },
        "Fayl çox böyükdür: {size} MB (maks. {max_mb} MB)": {
            "en": "The file is too large: {size} MB (max. {max_mb} MB)",
            "ru": "Файл слишком большой: {size} МБ (макс. {max_mb} МБ)",
            "tr": "Dosya çok büyük: {size} MB (en fazla {max_mb} MB)",
            "de": "Die Datei ist zu groß: {size} MB (max. {max_mb} MB)",
        },
        "Faylın məzmunu {ext} formatına uyğun deyil — fayl zədələnib və ya uzantısı dəyişdirilib.": {
            "en": "The file content does not match the {ext} format — the file is damaged or its extension was changed.",
            "ru": "Содержимое файла не соответствует формату {ext} — файл повреждён или его расширение изменено.",
            "tr": "Dosya içeriği {ext} biçimine uymuyor — dosya bozuk ya da uzantısı değiştirilmiş.",
            "de": "Der Dateiinhalt passt nicht zum Format {ext} — die Datei ist beschädigt oder die Endung wurde geändert.",
        },
        "Link http:// və ya https:// ilə başlamalıdır.": {
            "en": "The link must start with http:// or https://.",
            "ru": "Ссылка должна начинаться с http:// или https://.",
            "tr": "Bağlantı http:// veya https:// ile başlamalıdır.",
            "de": "Der Link muss mit http:// oder https:// beginnen.",
        },
        "«Link» tipində fayl yüklənmir — fayl üçün «Fayl», «Video» və ya «Sənəd» seçin.": {
            "en": "The «Link» type takes no file — choose «File», «Video» or «Document» to upload one.",
            "ru": "Для типа «Ссылка» файл не загружается — для файла выберите «Файл», «Видео» или «Документ».",
            "tr": "«Bağlantı» türünde dosya yüklenmez — dosya için «Dosya», «Video» veya «Belge» seçin.",
            "de": "Beim Typ «Link» wird keine Datei hochgeladen — wählen Sie dafür «Datei», «Video» oder «Dokument».",
        },
        "Link üçün URL daxil edin (http:// və ya https://).": {
            "en": "Enter a URL for the link (http:// or https://).",
            "ru": "Введите URL ссылки (http:// или https://).",
            "tr": "Bağlantı için URL girin (http:// veya https://).",
            "de": "Geben Sie eine URL für den Link ein (http:// oder https://).",
        },
        "Bu tipdə fayl yüklənir — xarici link üçün «Link» tipini seçin.": {
            "en": "This type takes a file — choose the «Link» type for an external link.",
            "ru": "Для этого типа загружается файл — для внешней ссылки выберите тип «Ссылка».",
            "tr": "Bu türde dosya yüklenir — dış bağlantı için «Bağlantı» türünü seçin.",
            "de": "Bei diesem Typ wird eine Datei hochgeladen — für einen externen Link den Typ «Link» wählen.",
        },
        "«{kind}» üçün fayl seçin.": {
            "en": "Choose a file for «{kind}».",
            "ru": "Выберите файл для «{kind}».",
            "tr": "«{kind}» için dosya seçin.",
            "de": "Wählen Sie eine Datei für «{kind}».",
        },
        "Sessiyanız bitib — səhifəni yeniləyib yenidən daxil olun.": {
            "en": "Your session has expired — reload the page and sign in again.",
            "ru": "Сеанс истёк — обновите страницу и войдите снова.",
            "tr": "Oturumunuz sona erdi — sayfayı yenileyip tekrar giriş yapın.",
            "de": "Ihre Sitzung ist abgelaufen — laden Sie die Seite neu und melden Sie sich erneut an.",
        },
        "Xətalar": {"en": "Errors", "ru": "Ошибки", "tr": "Hatalar", "de": "Fehler"},
        "Yüklənir: {pct}": {
            "en": "Uploading: {pct}",
            "ru": "Загрузка: {pct}",
            "tr": "Yükleniyor: {pct}",
            "de": "Wird hochgeladen: {pct}",
        },
        "Fayl yükləndi, server yoxlayır…": {
            "en": "File uploaded, the server is checking it…",
            "ru": "Файл загружен, сервер проверяет его…",
            "tr": "Dosya yüklendi, sunucu kontrol ediyor…",
            "de": "Datei hochgeladen, der Server prüft sie…",
        },
        "Resurs adını yazın.": {
            "en": "Enter the resource title.",
            "ru": "Введите название ресурса.",
            "tr": "Kaynak adını yazın.",
            "de": "Geben Sie den Titel der Ressource ein.",
        },
        "Fayl serverin qəbul etdiyi ölçüdən böyükdür (maks. {max_mb} MB).": {
            "en": "The file is larger than the server accepts (max. {max_mb} MB).",
            "ru": "Файл больше, чем принимает сервер (макс. {max_mb} МБ).",
            "tr": "Dosya sunucunun kabul ettiği boyuttan büyük (en fazla {max_mb} MB).",
            "de": "Die Datei ist größer, als der Server annimmt (max. {max_mb} MB).",
        },
        "Təhlükəsizlik yoxlaması keçmədi — səhifəni yeniləyib yenidən cəhd edin.": {
            "en": "The security check failed — reload the page and try again.",
            "ru": "Проверка безопасности не пройдена — обновите страницу и попробуйте снова.",
            "tr": "Güvenlik denetimi geçilemedi — sayfayı yenileyip tekrar deneyin.",
            "de": "Die Sicherheitsprüfung ist fehlgeschlagen — laden Sie die Seite neu und versuchen Sie es erneut.",
        },
        "Bağlantı kəsildi — internetinizi yoxlayıb yenidən cəhd edin.": {
            "en": "The connection was lost — check your internet and try again.",
            "ru": "Соединение прервано — проверьте интернет и попробуйте снова.",
            "tr": "Bağlantı kesildi — internetinizi kontrol edip tekrar deneyin.",
            "de": "Die Verbindung wurde unterbrochen — prüfen Sie Ihr Internet und versuchen Sie es erneut.",
        },
        "Server vaxtında cavab vermədi (kod {status}). Bir az sonra yenidən cəhd edin.": {
            "en": "The server did not respond in time (code {status}). Try again a little later.",
            "ru": "Сервер не ответил вовремя (код {status}). Повторите попытку чуть позже.",
            "tr": "Sunucu zamanında yanıt vermedi (kod {status}). Biraz sonra tekrar deneyin.",
            "de": "Der Server hat nicht rechtzeitig geantwortet (Code {status}). Versuchen Sie es etwas später erneut.",
        },
        "Server xətası (kod {status}). Bir az sonra yenidən cəhd edin.": {
            "en": "Server error (code {status}). Try again a little later.",
            "ru": "Ошибка сервера (код {status}). Повторите попытку чуть позже.",
            "tr": "Sunucu hatası (kod {status}). Biraz sonra tekrar deneyin.",
            "de": "Serverfehler (Code {status}). Versuchen Sie es etwas später erneut.",
        },
        "Fayl seçin və ya bura atın": {
            "en": "Choose a file or drop it here",
            "ru": "Выберите файл или перетащите его сюда",
            "tr": "Dosya seçin veya buraya bırakın",
            "de": "Datei auswählen oder hierher ziehen",
        },
        "Faylı çıxar": {"en": "Remove file", "ru": "Убрать файл", "tr": "Dosyayı kaldır", "de": "Datei entfernen"},
        "Videoya bax": {"en": "Watch video", "ru": "Смотреть видео", "tr": "Videoyu izle", "de": "Video ansehen"},
        "Endir": {"en": "Download", "ru": "Скачать", "tr": "İndir", "de": "Herunterladen"},
        "iPhone (.MOV) videosu bəzi brauzerlərdə (Chrome, Android) oynamaya bilər — «Endir» ilə açın.": {
            "en": "iPhone (.MOV) videos may not play in some browsers (Chrome, Android) — open them via «Download».",
            "ru": "Видео с iPhone (.MOV) может не воспроизводиться в некоторых браузерах (Chrome, Android) — откройте через «Скачать».",
            "tr": "iPhone (.MOV) videosu bazı tarayıcılarda (Chrome, Android) oynatılmayabilir — «İndir» ile açın.",
            "de": "iPhone-Videos (.MOV) laufen in manchen Browsern (Chrome, Android) eventuell nicht — über «Herunterladen» öffnen.",
        },
        "Brauzer bu videonu oynada bilmir — «Endir» ilə kompüterə yükləyib açın.": {
            "en": "Your browser cannot play this video — download it via «Download» and open it.",
            "ru": "Браузер не может воспроизвести это видео — скачайте его через «Скачать» и откройте.",
            "tr": "Tarayıcı bu videoyu oynatamıyor — «İndir» ile indirip açın.",
            "de": "Der Browser kann dieses Video nicht abspielen — über «Herunterladen» speichern und öffnen.",
        },
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    """Çatışmayan blokları faylın SONUNA əlavə edir (mövcud mətn yenidən formatlanmır)."""
    path = po_path(lang)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    blocks = []
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = translations.get("az", msgid) if lang == "az" else translations.get(lang) or msgid
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    if blocks:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.rstrip("\n") + "\n\n" + "\n".join(blocks))
    print(f"{lang}/django: +{len(blocks)} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)

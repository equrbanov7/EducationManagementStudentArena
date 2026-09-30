#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 «Akademik fəaliyyət» səliqəsi + fayl qoşması + profil şəkli (sahib).

Əlavə olunan mətnlər:
  * `accounts.academic_item_kind` — 6 yeni qeyd növü (təhsil, təcrübə, kitab, layihə, patent, mükafat);
  * `accounts.academic_item_hint` — növ üzrə modal placeholder-ləri;
  * `accounts.academic_items.attachment` / `accounts.academic_items.error` — fayl yoxlama xətaları;
  * `profile.academic_items` / `profile.edit_v2` — idarəetmə siyahısı, «Boş bölmələr», fayl sahəsi;
  * `profile.avatar` — profil şəkli menyusu, önizləmə, silmə təsdiqi, API mesajları.

Qeyd: «Patent» en/tr-də həqiqi eyni sözdür (identity +1 en, +1 tr) — qapı onu
borc sayırsa `check_i18n_catalogs.py --update` ilə baseline sıxılmalıdır.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_acad_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

KIND = "accounts.academic_item_kind"
HINT = "accounts.academic_item_hint"
ATT = "accounts.academic_items.attachment"
ERR = "accounts.academic_items.error"
ITEMS = "profile.academic_items"
EDIT = "profile.edit_v2"
AVATAR = "profile.avatar"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_KINDS = [
    _t("Təhsil / dərəcə", "Education / degree", "Образование / степень", "Eğitim / derece"),
    _t("Peşəkar təcrübə", "Professional experience", "Профессиональный опыт", "Mesleki deneyim"),
    _t("Kitab / dərslik", "Book / textbook", "Книга / учебник", "Kitap / ders kitabı"),
    _t("Elmi layihə / qrant", "Research project / grant", "Научный проект / грант", "Bilimsel proje / hibe"),
    _t("Patent", "Patent", "Патент", "Patent"),
    _t("Mükafat / təltif", "Award / honour", "Награда / поощрение", "Ödül / takdir"),
]

_HINTS = [
    _t(
        "Məs.: Verilənlər bazası sistemləri",
        "E.g. Database systems",
        "Напр.: Системы баз данных",
        "Örn.: Veritabanı sistemleri",
    ),
    _t(
        "Kafedra, səviyyə (bakalavr / magistr)",
        "Department, level (bachelor / master)",
        "Кафедра, уровень (бакалавриат / магистратура)",
        "Bölüm, düzey (lisans / yüksek lisans)",
    ),
    _t(
        "Məs.: Kompüter elmləri üzrə magistr",
        "E.g. Master of Computer Science",
        "Напр.: Магистр компьютерных наук",
        "Örn.: Bilgisayar bilimleri yüksek lisansı",
    ),
    _t(
        "Universitet, fakültə, şəhər",
        "University, faculty, city",
        "Университет, факультет, город",
        "Üniversite, fakülte, şehir",
    ),
    _t("Məs.: Proqram mühəndisi", "E.g. Software engineer", "Напр.: Инженер-программист", "Örn.: Yazılım mühendisi"),
    _t(
        "Təşkilat, dövr (2019–2023)",
        "Organisation, period (2019–2023)",
        "Организация, период (2019–2023)",
        "Kurum, dönem (2019–2023)",
    ),
    _t("Məqalənin adı", "Article title", "Название статьи", "Makalenin adı"),
    _t(
        "Jurnal, cild / nömrə, həmmüəlliflər",
        "Journal, volume / issue, co-authors",
        "Журнал, том / номер, соавторы",
        "Dergi, cilt / sayı, ortak yazarlar",
    ),
    _t("Kitabın / dərsliyin adı", "Book / textbook title", "Название книги / учебника", "Kitabın / ders kitabının adı"),
    _t(
        "Nəşriyyat, ISBN, həmmüəlliflər",
        "Publisher, ISBN, co-authors",
        "Издательство, ISBN, соавторы",
        "Yayınevi, ISBN, ortak yazarlar",
    ),
    _t("Məruzənin adı", "Talk / paper title", "Название доклада", "Bildirinin adı"),
    _t("Konfransın adı, şəhər", "Conference name, city", "Название конференции, город", "Konferansın adı, şehir"),
    _t("Layihənin adı", "Project title", "Название проекта", "Projenin adı"),
    _t(
        "Maliyyələşdirən qurum, rolunuz (rəhbər / icraçı)",
        "Funding body, your role (lead / member)",
        "Финансирующая организация, ваша роль (руководитель / исполнитель)",
        "Destekleyen kurum, rolünüz (yürütücü / araştırmacı)",
    ),
    _t("İxtiranın adı", "Invention title", "Название изобретения", "Buluşun adı"),
    _t(
        "Patent nömrəsi, verən qurum",
        "Patent number, issuing office",
        "Номер патента, выдавшая организация",
        "Patent numarası, veren kurum",
    ),
    _t("Məs.: Cisco CCNA", "E.g. Cisco CCNA", "Напр.: Cisco CCNA", "Örn.: Cisco CCNA"),
    _t(
        "Verən qurum, sertifikat nömrəsi",
        "Issuer, certificate number",
        "Выдавшая организация, номер сертификата",
        "Veren kurum, sertifika numarası",
    ),
    _t("Mükafatın adı", "Award name", "Название награды", "Ödülün adı"),
    _t("Verən qurum, səbəb", "Awarding body, reason", "Кем вручена, за что", "Veren kurum, gerekçe"),
]

_ATTACHMENT = [
    _t(
        "Faylın məzmunu PDF və ya şəkil formatına uyğun deyil.",
        "The file content does not match a PDF or image format.",
        "Содержимое файла не соответствует формату PDF или изображения.",
        "Dosya içeriği PDF veya görsel biçimine uymuyor.",
    ),
    _t(
        "Şəklin ölçüsü çox böyükdür — daha kiçik şəkil seçin.",
        "The image is too large — please choose a smaller one.",
        "Изображение слишком большое — выберите изображение поменьше.",
        "Görsel çok büyük — daha küçük bir görsel seçin.",
    ),
    _t("Fayl seçilməyib.", "No file selected.", "Файл не выбран.", "Dosya seçilmedi."),
    _t("Fayl boşdur.", "The file is empty.", "Файл пуст.", "Dosya boş."),
    _t(
        "Fayl %(limit)s MB-dan böyük ola bilməz.",
        "The file cannot be larger than %(limit)s MB.",
        "Файл не может быть больше %(limit)s МБ.",
        "Dosya %(limit)s MB'tan büyük olamaz.",
    ),
    _t(
        "Yalnız PDF və ya şəkil (JPG, PNG, WEBP) yükləmək olar.",
        "Only PDF or image files (JPG, PNG, WEBP) can be uploaded.",
        "Можно загружать только PDF или изображения (JPG, PNG, WEBP).",
        "Yalnızca PDF veya görsel (JPG, PNG, WEBP) yüklenebilir.",
    ),
]

_ERRORS = [
    _t(
        "Bu qeyd növünə fayl əlavə etmək olmur.",
        "Files cannot be attached to this type of entry.",
        "К записи этого типа нельзя прикрепить файл.",
        "Bu kayıt türüne dosya eklenemez.",
    ),
]

_ITEMS = [
    _t("Əlavə et: %(kind)s", "Add: %(kind)s", "Добавить: %(kind)s", "Ekle: %(kind)s"),
    _t(
        "Hələ qeyd əlavə edilməyib. Aşağıdan bölmə seçib başlayın.",
        "No entries yet. Pick a section below to get started.",
        "Записей пока нет. Выберите раздел ниже, чтобы начать.",
        "Henüz kayıt eklenmedi. Başlamak için aşağıdan bir bölüm seçin.",
    ),
    _t(
        "Boş bölmələr (%(count)s)",
        "Empty sections (%(count)s)",
        "Пустые разделы (%(count)s)",
        "Boş bölümler (%(count)s)",
    ),
    _t("əlavə etmək üçün seçin", "choose one to add", "выберите, чтобы добавить", "eklemek için seçin"),
    _t("Faylı aç", "Open file", "Открыть файл", "Dosyayı aç"),
    _t("PDF sənəd", "PDF document", "PDF-документ", "PDF belge"),
    _t("Şəkil", "Image", "Изображение", "Görsel"),
    _t(
        "Fayl 10 MB-dan böyük ola bilməz.",
        "The file cannot be larger than 10 MB.",
        "Файл не может быть больше 10 МБ.",
        "Dosya 10 MB'tan büyük olamaz.",
    ),
    _ATTACHMENT[5],
    _t("Fayl seç", "Choose file", "Выбрать файл", "Dosya seç"),
    _t("Faylı dəyiş", "Change file", "Заменить файл", "Dosyayı değiştir"),
    _t(
        "Fayl (sənəd və ya şəkil)",
        "File (document or image)",
        "Файл (документ или изображение)",
        "Dosya (belge veya görsel)",
    ),
    _t("Faylı sil", "Remove file", "Удалить файл", "Dosyayı sil"),
    _t(
        "Fayl yadda saxlayanda silinəcək.",
        "The file will be removed when you save.",
        "Файл будет удалён при сохранении.",
        "Dosya kaydettiğinizde silinecek.",
    ),
    _t("Geri al", "Undo", "Отменить", "Silmeyi geri al"),
    _t(
        "PDF, JPG, PNG və ya WEBP · maksimum 10 MB",
        "PDF, JPG, PNG or WEBP · max 10 MB",
        "PDF, JPG, PNG или WEBP · максимум 10 МБ",
        "PDF, JPG, PNG veya WEBP · en fazla 10 MB",
    ),
]

_EDIT = [
    _t(
        "Təhsil və təcrübənizi, fənlərinizi, nəşr və layihələrinizi, sertifikat və mükafatlarınızı əlavə edin; "
        "lazım olan yerdə sənəd və ya şəkil də qoşa bilərsiniz. Bunlar profil səhifənizdə görünəcək.",
        "Add your education and experience, subjects, publications and projects, certificates and awards; "
        "where relevant you can also attach a document or image. These will appear on your profile page.",
        "Добавьте образование и опыт, дисциплины, публикации и проекты, сертификаты и награды; "
        "где нужно, можно прикрепить документ или изображение. Всё это будет видно на странице профиля.",
        "Eğitim ve deneyiminizi, derslerinizi, yayın ve projelerinizi, sertifika ve ödüllerinizi ekleyin; "
        "gerektiğinde belge veya görsel de ekleyebilirsiniz. Bunlar profil sayfanızda görünecek.",
    ),
]

_AVATAR = [
    _t("Profil şəkli", "Profile photo", "Фото профиля", "Profil fotoğrafı"),
    _t("Şəkli dəyiş / yüklə", "Change / upload photo", "Изменить / загрузить фото", "Fotoğrafı değiştir / yükle"),
    _t("Şəkli sil", "Remove photo", "Удалить фото", "Fotoğrafı sil"),
    _t("Şəkil yüklə", "Upload photo", "Загрузить фото", "Fotoğraf yükle"),
    _t("Şəkli dəyiş", "Change photo", "Изменить фото", "Fotoğrafı değiştir"),
    _t("Sil", "Remove", "Удалить", "Kaldır"),
    _t("Yadda saxla", "Save", "Сохранить", "Kaydet"),
    _t("Ləğv et", "Cancel", "Отмена", "İptal"),
    _t("Bağla", "Close", "Закрыть", "Kapat"),
    _t("Başqa şəkil", "Another photo", "Другое фото", "Başka fotoğraf"),
    _t("Profil şəkli silinsin?", "Remove profile photo?", "Удалить фото профиля?", "Profil fotoğrafı silinsin mi?"),
    _t(
        "Şəkil silinəcək, yerində adınızın baş hərfləri görünəcək.",
        "The photo will be removed and your initials will be shown instead.",
        "Фото будет удалено, вместо него будут показаны ваши инициалы.",
        "Fotoğraf silinecek, yerine adınızın baş harfleri görünecek.",
    ),
    _t(
        "Əməliyyat alınmadı. Yenidən cəhd edin.",
        "The action failed. Please try again.",
        "Не удалось выполнить действие. Попробуйте ещё раз.",
        "İşlem başarısız oldu. Lütfen tekrar deneyin.",
    ),
    _t(
        "Şəkil 10 MB-dan böyük ola bilməz.",
        "The photo cannot be larger than 10 MB.",
        "Фото не может быть больше 10 МБ.",
        "Fotoğraf 10 MB'tan büyük olamaz.",
    ),
    _t(
        "Yalnız JPG, PNG, WEBP və ya GIF şəkil seçin.",
        "Please choose a JPG, PNG, WEBP or GIF image.",
        "Выберите изображение JPG, PNG, WEBP или GIF.",
        "Yalnızca JPG, PNG, WEBP veya GIF görsel seçin.",
    ),
    _t(
        "JPG, PNG, WEBP və ya GIF · maksimum 10 MB",
        "JPG, PNG, WEBP or GIF · max 10 MB",
        "JPG, PNG, WEBP или GIF · максимум 10 МБ",
        "JPG, PNG, WEBP veya GIF · en fazla 10 MB",
    ),
    _t("Profil şəkli yeniləndi.", "Profile photo updated.", "Фото профиля обновлено.", "Profil fotoğrafı güncellendi."),
    _t("Profil şəkli silindi.", "Profile photo removed.", "Фото профиля удалено.", "Profil fotoğrafı silindi."),
    _t("Naməlum əməliyyat.", "Unknown action.", "Неизвестное действие.", "Bilinmeyen işlem."),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    KIND: {row["az"]: row for row in _KINDS},
    HINT: {row["az"]: row for row in _HINTS},
    ATT: {row["az"]: row for row in _ATTACHMENT},
    ERR: {row["az"]: row for row in _ERRORS},
    ITEMS: {row["az"]: row for row in _ITEMS},
    EDIT: {row["az"]: row for row in _EDIT},
    AVATAR: {row["az"]: row for row in _AVATAR},
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
                new_entry = polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want)
                if "%(" in msgid:
                    new_entry.flags.append("python-format")
                po.append(new_entry)
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

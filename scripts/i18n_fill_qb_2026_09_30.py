#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 QB: sual bankında «son aktiv suallar» təsdiq axını.

Əlavə olunan mətnlər:
  * `exams.service.lifecycle` — «son aktiv sual» mesajının DƏQİQ mətni (köhnə mətn
    «Aktiv imtahanın son aktiv sualı…» aktiv İSTİFADƏÇİ kimi başa düşülürdü; əslində
    söhbət imtahanın dərc olunmuş/aktiv olmasından gedir);
  * `exams.service.exam_usage` — imtahan hazırda istifadədədir (açıq cəhd / canlı
    sessiya / final zal oturumu) imtinaları;
  * `exams.view.questions_bank.guard` — EMSConfirm «imtahan deaktiv ediləcək — davam
    edilsin?» mətnləri, uğur/xəta bildirişləri.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_qb_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

LC = "exams.service.lifecycle"
EU = "exams.service.exam_usage"
QG = "exams.view.questions_bank.guard"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    LC: {
        (
            "Seçilmiş suallar bu dərc olunmuş (aktiv) imtahanın son aktiv suallarıdır. Onları silmək və ya "
            "deaktiv etmək üçün imtahan da deaktiv edilməlidir."
        ): {
            "az": (
                "Seçilmiş suallar bu dərc olunmuş (aktiv) imtahanın son aktiv suallarıdır. Onları silmək və ya "
                "deaktiv etmək üçün imtahan da deaktiv edilməlidir."
            ),
            "en": (
                "The selected questions are the last active questions of this published (active) exam. "
                "To delete or deactivate them, the exam must be deactivated as well."
            ),
            "ru": (
                "Выбранные вопросы — последние активные вопросы этого опубликованного (активного) экзамена. "
                "Чтобы удалить или деактивировать их, экзамен тоже нужно деактивировать."
            ),
            "tr": (
                "Seçilen sorular bu yayımlanmış (aktif) sınavın son aktif sorularıdır. Onları silmek veya "
                "devre dışı bırakmak için sınavın da devre dışı bırakılması gerekir."
            ),
        },
    },
    EU: {
        (
            "İmtahanı hazırda {count} tələbə yazır (başlanmış, bitməmiş cəhd). Onlar bitirənə qədər "
            "imtahan deaktiv edilə və bütün aktiv sualları silinə bilməz."
        ): {
            "az": (
                "İmtahanı hazırda {count} tələbə yazır (başlanmış, bitməmiş cəhd). Onlar bitirənə qədər "
                "imtahan deaktiv edilə və bütün aktiv sualları silinə bilməz."
            ),
            "en": (
                "{count} student(s) are taking this exam right now (started, unfinished attempts). Until they "
                "finish, the exam cannot be deactivated and all of its active questions cannot be deleted."
            ),
            "ru": (
                "Сейчас этот экзамен сдают студенты: {count} (начатые, незавершённые попытки). Пока они не "
                "закончат, экзамен нельзя деактивировать и нельзя удалить все его активные вопросы."
            ),
            "tr": (
                "Bu sınava şu anda {count} öğrenci giriyor (başlanmış, bitmemiş denemeler). Onlar bitirene "
                "kadar sınav devre dışı bırakılamaz ve tüm aktif soruları silinemez."
            ),
        },
        (
            "Bu imtahan üzrə canlı sessiya hələ bitməyib (PIN: {pin}). Əvvəl canlı sessiyanı bitirin, "
            "sonra sualları silin."
        ): {
            "az": (
                "Bu imtahan üzrə canlı sessiya hələ bitməyib (PIN: {pin}). Əvvəl canlı sessiyanı bitirin, "
                "sonra sualları silin."
            ),
            "en": (
                "A live session of this exam has not finished yet (PIN: {pin}). Finish the live session "
                "first, then delete the questions."
            ),
            "ru": (
                "Живая сессия этого экзамена ещё не завершена (PIN: {pin}). Сначала завершите живую "
                "сессию, затем удалите вопросы."
            ),
            "tr": (
                "Bu sınavın canlı oturumu henüz bitmedi (PIN: {pin}). Önce canlı oturumu bitirin, "
                "ardından soruları silin."
            ),
        },
        (
            "Bu imtahan üzrə final zal oturumu davam edir ({count} tələbə zalda). Oturum bitənə qədər "
            "imtahan deaktiv edilə bilməz."
        ): {
            "az": (
                "Bu imtahan üzrə final zal oturumu davam edir ({count} tələbə zalda). Oturum bitənə qədər "
                "imtahan deaktiv edilə bilməz."
            ),
            "en": (
                "A final exam hall session for this exam is in progress ({count} student(s) in the hall). "
                "The exam cannot be deactivated until the session ends."
            ),
            "ru": (
                "По этому экзамену идёт сессия в экзаменационном зале (студентов в зале: {count}). "
                "Экзамен нельзя деактивировать, пока сессия не завершится."
            ),
            "tr": (
                "Bu sınav için final salon oturumu devam ediyor (salonda {count} öğrenci). Oturum bitene "
                "kadar sınav devre dışı bırakılamaz."
            ),
        },
    },
    QG: {
        "Bu imtahanın bütün aktiv sualları silinəcək — imtahan deaktiv ediləcək. Davam edilsin?": {
            "az": "Bu imtahanın bütün aktiv sualları silinəcək — imtahan deaktiv ediləcək. Davam edilsin?",
            "en": "All active questions of this exam will be deleted — the exam will be deactivated. Continue?",
            "ru": "Все активные вопросы этого экзамена будут удалены — экзамен будет деактивирован. Продолжить?",
            "tr": "Bu sınavın tüm aktif soruları silinecek — sınav devre dışı bırakılacak. Devam edilsin mi?",
        },
        "Bu imtahanın bütün aktiv sualları deaktiv ediləcək — imtahan da deaktiv ediləcək. Davam edilsin?": {
            "az": "Bu imtahanın bütün aktiv sualları deaktiv ediləcək — imtahan da deaktiv ediləcək. Davam edilsin?",
            "en": (
                "All active questions of this exam will be deactivated — the exam will be deactivated too. " "Continue?"
            ),
            "ru": (
                "Все активные вопросы этого экзамена будут деактивированы — экзамен тоже будет "
                "деактивирован. Продолжить?"
            ),
            "tr": (
                "Bu sınavın tüm aktif soruları devre dışı bırakılacak — sınav da devre dışı bırakılacak. "
                "Devam edilsin mi?"
            ),
        },
        "İmtahan deaktiv ediləcək": {
            "az": "İmtahan deaktiv ediləcək",
            "en": "The exam will be deactivated",
            "ru": "Экзамен будет деактивирован",
            "tr": "Sınav devre dışı bırakılacak",
        },
        "Bəli, davam et": {
            "az": "Bəli, davam et",
            "en": "Yes, continue",
            "ru": "Да, продолжить",
            "tr": "Evet, devam et",
        },
        "Əməliyyat alınmadı. Səhifəni yeniləyib yenidən cəhd edin.": {
            "az": "Əməliyyat alınmadı. Səhifəni yeniləyib yenidən cəhd edin.",
            "en": "The operation failed. Refresh the page and try again.",
            "ru": "Операция не выполнена. Обновите страницу и повторите попытку.",
            "tr": "İşlem başarısız oldu. Sayfayı yenileyip tekrar deneyin.",
        },
        "İmtahan deaktiv edildi (dərcdən çıxarıldı). Yeni suallar əlavə edib yenidən dərc edə bilərsiniz.": {
            "az": "İmtahan deaktiv edildi (dərcdən çıxarıldı). Yeni suallar əlavə edib yenidən dərc edə bilərsiniz.",
            "en": "The exam was deactivated (unpublished). You can add new questions and publish it again.",
            "ru": (
                "Экзамен деактивирован (снят с публикации). Вы можете добавить новые вопросы и снова "
                "опубликовать его."
            ),
            "tr": (
                "Sınav devre dışı bırakıldı (yayından kaldırıldı). Yeni sorular ekleyip yeniden " "yayımlayabilirsiniz."
            ),
        },
    },
}

# Mövcud olan, amma yanlış/qarışıq dildə olan tərcümələr — həmişə üstələnir.
FORCE = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
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

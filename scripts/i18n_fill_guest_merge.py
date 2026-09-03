#!/usr/bin/env python3
"""EMSArena i18n — «alt qrup birləşməsi» (öz jurnalından azad et) sətirləri, 4 dil.

Servis xətaları, önbaxış paneli, qrid nişanı və düymə mətnləri. İdempotent:
mövcud girişə TOXUNMUR, yalnız çatışmayanı əlavə edir.

⚠️ `makemessages` İŞLƏDİLMİR (əl ilə yazılmış blokları silə bilir).

İstifadə:  python scripts/i18n_fill_guest_merge.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "registrar.guest_roster"

ENTRIES = {
    CTX: {
        # ── Servis qatı: birləşmə qapıları ──────────────────────────────────
        (
            "Tələbə bu fənn üzrə bu semestrdə öz qrupunun jurnalında aktivdir. "
            "Alt qrup birləşməsi üçün «öz jurnalından azad et» seçimini işarələyin — "
            "əvvəlki qeydiyyat tarixçəyə keçir, bal və davamiyyət saxlanılır."
        ): {
            "en": (
                "The student is active in their own group's journal for this subject this semester. "
                "To merge subgroups, tick “release from own journal” — the previous enrollment moves "
                "to history while marks and attendance are preserved."
            ),
            "ru": (
                "Студент активен в журнале своей группы по этому предмету в этом семестре. "
                "Для объединения подгрупп отметьте «освободить из своего журнала» — прежняя запись "
                "уходит в историю, баллы и посещаемость сохраняются."
            ),
            "tr": (
                "Öğrenci bu dönem bu ders için kendi grubunun günlüğünde etkin. "
                "Alt grup birleştirmesi için “kendi günlüğünden serbest bırak” seçeneğini işaretleyin — "
                "önceki kayıt geçmişe taşınır, notlar ve devam korunur."
            ),
        },
        "Tələbənin bu fənn üzrə birdən çox aktiv jurnalı var — birləşmə avtomatik aparıla bilməz.": {
            "en": "The student has more than one active journal for this subject — the merge cannot be automatic.",
            "ru": "У студента более одного активного журнала по этому предмету — объединение нельзя выполнить автоматически.",
            "tr": "Öğrencinin bu ders için birden fazla etkin günlüğü var — birleştirme otomatik yapılamaz.",
        },
        "Mənbə jurnalda bu tələbənin yekun qiyməti var — birləşmə əvəzinə rəsmi qrup köçürməsi tələb olunur.": {
            "en": (
                "The source journal already holds a final grade for this student — an official group "
                "transfer is required instead of a merge."
            ),
            "ru": (
                "В исходном журнале уже есть итоговая оценка этого студента — вместо объединения "
                "требуется официальный перевод группы."
            ),
            "tr": ("Kaynak günlükte bu öğrencinin final notu var — birleştirme yerine resmi grup nakli gerekir."),
        },
        "Mənbə jurnal bağlanıb — tələbəni ondan azad etmək üçün əvvəlcə RİM jurnalı açmalıdır.": {
            "en": "The source journal is closed — the registrar must reopen it before the student can be released.",
            "ru": "Исходный журнал закрыт — прежде чем освободить студента, его должен открыть учебный отдел.",
            "tr": "Kaynak günlük kapalı — öğrenciyi serbest bırakmadan önce öğrenci işleri günlüğü açmalıdır.",
        },
        "Birləşmə üçün səbəb yazılmalıdır (məs.: dekanlıq sərəncamı nömrəsi).": {
            "en": "A reason is required for the merge (e.g. the dean's office order number).",
            "ru": "Для объединения нужно указать причину (например, номер приказа деканата).",
            "tr": "Birleştirme için gerekçe yazılmalıdır (örn. dekanlık emri numarası).",
        },
        "Alt qrup birləşməsi — mənbə jurnal qeydiyyatı bərpa olundu.": {
            "en": "Subgroup merge — the source journal enrollment has been restored.",
            "ru": "Объединение подгрупп — запись в исходном журнале восстановлена.",
            "tr": "Alt grup birleştirmesi — kaynak günlük kaydı geri yüklendi.",
        },
        "Tələbə öz jurnalından azad edilib bu jurnala köçürüldü.": {
            "en": "The student was released from their own journal and moved into this one.",
            "ru": "Студент освобождён из своего журнала и переведён в этот.",
            "tr": "Öğrenci kendi günlüğünden serbest bırakılıp bu günlüğe taşındı.",
        },
        # ── Önbaxış paneli (modal) ──────────────────────────────────────────
        "Bu tələbənin öz qrupunda bu fənn üzrə aktiv jurnalı var": {
            "en": "This student has an active journal for this subject in their own group",
            "ru": "У этого студента есть активный журнал по этому предмету в своей группе",
            "tr": "Bu öğrencinin kendi grubunda bu ders için etkin bir günlüğü var",
        },
        (
            "Birləşmə təsdiqlənsə: əvvəlki qeydiyyat tarixçəyə keçir (silinmir), yığılmış bal və "
            "davamiyyət olduğu kimi saxlanılır, qayıb saatı bu jurnalın buraxılış həddinə köçürülür "
            "və sətirdə «əvvəlki jurnal» xülasəsi görünür. Geri götürəndə əvvəlki qeydiyyat bərpa olunur."
        ): {
            "en": (
                "If the merge is confirmed: the previous enrollment moves to history (it is not deleted), "
                "the marks and attendance already recorded are kept as they are, the absence hours carry "
                "over into this journal's exam-eligibility limit, and the row shows a “previous journal” "
                "summary. Undoing the addition restores the previous enrollment."
            ),
            "ru": (
                "Если объединение подтверждено: прежняя запись уходит в историю (не удаляется), "
                "выставленные баллы и посещаемость сохраняются без изменений, часы пропусков "
                "переносятся в лимит допуска этого журнала, а в строке появляется сводка «прежний "
                "журнал». При отмене прежняя запись восстанавливается."
            ),
            "tr": (
                "Birleştirme onaylanırsa: önceki kayıt geçmişe taşınır (silinmez), girilmiş notlar ve "
                "devam olduğu gibi korunur, devamsızlık saatleri bu günlüğün sınav giriş limitine "
                "aktarılır ve satırda “önceki günlük” özeti görünür. Geri alındığında önceki kayıt "
                "geri yüklenir."
            ),
        },
        "Öz jurnalından azad et və bu jurnala köçür": {
            "en": "Release from their own journal and move into this one",
            "ru": "Освободить из своего журнала и перевести в этот",
            "tr": "Kendi günlüğünden serbest bırak ve bu günlüğe taşı",
        },
        "Mənbə jurnal": {"en": "Source journal", "ru": "Исходный журнал", "tr": "Kaynak günlük"},
        "Yazılmış işarə / bal": {
            "en": "Marks recorded / scored",
            "ru": "Отметок / из них с баллом",
            "tr": "Girilen işaret / notlu",
        },
        "Qayıb": {"en": "Absence", "ru": "Пропуски", "tr": "Devamsızlık"},
        "Giriş balı": {"en": "Entry score", "ru": "Входной балл", "tr": "Giriş puanı"},
        "saat": {"en": "h", "ru": "ч", "tr": "sa."},
        # ── Qrid nişanı ─────────────────────────────────────────────────────
        "əvvəlki jurnal": {"en": "previous journal", "ru": "прежний журнал", "tr": "önceki günlük"},
        (
            "Əvvəlki jurnaldan (%(group)s) gətirilib: %(marks)s işarə, %(hours)s saat qayıb. "
            "Qayıb saatı buraxılış həddinə daxildir; ballar köçürülmür — əvvəlki qeydiyyatda saxlanılır."
        ): {
            "en": (
                "Carried over from the previous journal (%(group)s): %(marks)s marks, %(hours)s absence "
                "hours. The absence hours count toward the exam-eligibility limit; scores are not moved — "
                "they stay on the previous enrollment."
            ),
            "ru": (
                "Перенесено из прежнего журнала (%(group)s): отметок — %(marks)s, часов пропусков — "
                "%(hours)s. Часы пропусков учитываются в лимите допуска; баллы не переносятся — они "
                "остаются в прежней записи."
            ),
            "tr": (
                "Önceki günlükten (%(group)s) aktarıldı: %(marks)s işaret, %(hours)s saat devamsızlık. "
                "Devamsızlık saatleri sınav giriş limitine dahildir; notlar taşınmaz — önceki kayıtta kalır."
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

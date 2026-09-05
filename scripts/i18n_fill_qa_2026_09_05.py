#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-05 QA düzəlişlərinin istifadəçi mətnləri. İdempotent.

Jurnal (registrar/views.py — kontekstsiz `gettext`) və sillabus (`accounts.syllabus`
kontekstli TransitionDenied etiketləri) üçün 4 dil doldurulur.
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir, mövcud girişə toxunmur.
İstifadə:  python scripts/i18n_fill_qa_2026_09_05.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    None: {
        "Akademik qeydiniz hələ yaradılmayıb.": {
            "en": "Your academic record has not been created yet.",
            "ru": "Ваша академическая запись ещё не создана.",
            "tr": "Akademik kaydınız henüz oluşturulmamış.",
        },
        "Jurnal qrupa yazılışdan sonra görünür — tələbə xidmətlərinə müraciət edin.": {
            "en": "The journal appears after enrolment in a group — contact student services.",
            "ru": "Журнал появится после зачисления в группу — обратитесь в студенческую службу.",
            "tr": "Yoklama defteri gruba kayıttan sonra görünür — öğrenci hizmetlerine başvurun.",
        },
        "Seçilmiş müəllim bu təşkilatın tədris heyətində deyil.": {
            "en": "The selected teacher is not on this organisation's teaching staff.",
            "ru": "Выбранный преподаватель не входит в преподавательский состав организации.",
            "tr": "Seçilen öğretim elemanı bu kurumun öğretim kadrosunda değil.",
        },
        "Jurnal bağlıdır — dəyişikliklər yazılmadı.": {
            "en": "The journal is closed — the changes were not saved.",
            "ru": "Журнал закрыт — изменения не сохранены.",
            "tr": "Yoklama defteri kapalı — değişiklikler kaydedilmedi.",
        },
        "İmtahan/təkrar balını yalnız İmtahan Mərkəzi yaza bilər — bu sahələr yazılmadı.": {
            "en": "Only the Examination Centre may record exam/resit scores — those fields were not saved.",
            "ru": "Экзаменационные/пересдачные баллы вносит только Экзаменационный центр — эти поля не сохранены.",
            "tr": "Sınav/bütünleme puanını yalnızca Sınav Merkezi girebilir — bu alanlar kaydedilmedi.",
        },
        "Heç bir xana yazılmadı — dərs günü qaydası və ya xana kilidi buna imkan vermədi.": {
            "en": "No cell was saved — the lesson-day rule or a cell lock prevented it.",
            "ru": "Ни одна ячейка не сохранена — помешало правило дня занятия или блокировка ячейки.",
            "tr": "Hiçbir hücre kaydedilmedi — ders günü kuralı veya hücre kilidi buna izin vermedi.",
        },
    },
    "accounts.manage_roles.message": {
        "missing_member_management_permission": {
            "en": "You need the `role.assign` or `org.manage_members` permission for this action.",
            "ru": "Для этого действия требуется право `role.assign` или `org.manage_members`.",
            "tr": "Bu işlem için `role.assign` veya `org.manage_members` izni gerekir.",
        },
        "target_outside_structure_scope": {
            "en": "This user is outside your structural scope.",
            "ru": "Этот пользователь вне вашей структурной зоны ответственности.",
            "tr": "Bu kullanıcı yapısal yetki alanınızın dışındadır.",
        },
        "role_not_defined_in_organization": {
            "en": "The selected role is not defined in this organisation: %(roles)s.",
            "ru": "Выбранная роль не определена в этой организации: %(roles)s.",
            "tr": "Seçilen rol bu kurumda tanımlı değil: %(roles)s.",
        },
    },
    "student_intake": {
        "Ad/soyad/ata adı ən çox %(n)s simvol ola bilər.": {
            "en": "First/last/patronymic name may be at most %(n)s characters.",
            "ru": "Имя/фамилия/отчество — не более %(n)s символов.",
            "tr": "Ad/soyad/baba adı en fazla %(n)s karakter olabilir.",
        },
        "sahə uzunluğu həddi keçildi": {
            "en": "field length limit exceeded",
            "ru": "превышена допустимая длина поля",
            "tr": "alan uzunluğu sınırı aşıldı",
        },
    },
    "exams.view.bank.message": {
        "Bank adı ən çox %(n)s simvol ola bilər.": {
            "en": "The bank name may be at most %(n)s characters.",
            "ru": "Название банка — не более %(n)s символов.",
            "tr": "Banka adı en fazla %(n)s karakter olabilir.",
        },
    },
    "accounts.syllabus": {
        "Bölmə məzmununun formatı düzgün deyil (%(field)s).": {
            "en": "The section content has an invalid format (%(field)s).",
            "ru": "Содержимое раздела имеет неверный формат (%(field)s).",
            "tr": "Bölüm içeriğinin biçimi geçersiz (%(field)s).",
        },
        "Məzmun həddindən böyükdür — ən çox %(max)s (%(field)s).": {
            "en": "The content is too large — at most %(max)s (%(field)s).",
            "ru": "Содержимое слишком велико — не более %(max)s (%(field)s).",
            "tr": "İçerik çok büyük — en fazla %(max)s (%(field)s).",
        },
        "Bu açılış üçün sillabus artıq mövcuddur — siyahıdan açın.": {
            "en": "A syllabus already exists for this course offering — open it from the list.",
            "ru": "Для этого курса силлабус уже существует — откройте его из списка.",
            "tr": "Bu ders açılışı için zaten bir izlence var — listeden açın.",
        },
    },
}


#: Açar-tipli msgid-lər üçün AZ mətni (kataloq qapısı xam açar sızmasını rədd edir).
AZ_OVERRIDES = {
    "missing_member_management_permission": "Bu əməl üçün `role.assign` və ya `org.manage_members` icazəsi lazımdır.",
    "target_outside_structure_scope": "Bu istifadəçi sizin struktur əhatənizdən kənardadır.",
    "role_not_defined_in_organization": "Seçilmiş rol bu təşkilatda müəyyən edilməyib: %(roles)s.",
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
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            probe = f'{head}msgid "{esc(msgid)}"\nmsgstr'
            if probe in text:
                continue
            msgstr = AZ_OVERRIDES.get(msgid, msgid) if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)

#!/usr/bin/env python3
"""EMSArena i18n — sürüşmüş (səhv uyğunlaşdırılmış) tərcümələrin düzəlişi.

Problem: bir sıra SİMVOLİK msgid-lərin (məs. ``empty_option_text``) tərcüməsi
başqa mesajın mətni ilə dolmuşdu (köhnə ``makemessages`` fuzzy-match qurbanı).
Nəticədə placeholder dəsti mənbə ilə uyğun gəlmirdi:

    pgettext("exams.service.parsing.warning", "empty_option_text").format(option=lab)
    # EN tərcüməsi: "Duplicate option text: {labels} are identical."  → KeyError: 'labels'

Yəni EN/RU/TR interfeysdə boş variantlı sual parse edilərkən **çökmə** olurdu.
Bu skript belə 28 açarın hər 4 dildəki mətnini düzgün variantla əvəz edir.
Kitabxana (Django/click) sətirlərində isə səhv tərcümə BOŞALDILIR ki, Django
öz core kataloquna geri düşsün.

İdempotentdir. İstifadə:  python scripts/i18n_fix_placeholder_mismatches.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

# (ctx, msgid) -> {lang: msgstr}.  "" dəyəri = msgstr-i boşalt (core fallback).
FIXES = {
    ("exams.service.parsing.warning", "empty_option_text"): {
        "az": "{option} variantının mətni boşdur.",
        "en": "The text of option {option} is empty.",
        "ru": "Текст варианта {option} пуст.",
        "tr": "{option} seçeneğinin metni boş.",
    },
    ("exams.service.parsing.warning", "option_count_recommend_5"): {
        "az": "Sualda {count} variant var — tövsiyə olunan say 5-dir (A–E). E variantı əlavə etmək məsləhət görülür.",
        "en": "The question has {count} options — 5 (A–E) is recommended. Adding option E is advised.",
        "ru": "В вопросе {count} вариантов — рекомендуется 5 (A–E). Желательно добавить вариант E.",
        "tr": "Soruda {count} seçenek var — önerilen sayı 5'tir (A–E). E seçeneğini eklemeniz önerilir.",
    },
    ("exams.service.parsing.warning", "option_count_too_low"): {
        "az": "Sualda yalnız {count} variant tapıldı — minimum 4 variant (A–D) tələb olunur.",
        "en": "Only {count} options were found in the question — at least 4 options (A–D) are required.",
        "ru": "В вопросе найдено всего {count} вариантов — требуется минимум 4 варианта (A–D).",
        "tr": "Soruda yalnızca {count} seçenek bulundu — en az 4 seçenek (A–D) gerekir.",
    },
    ("exams.form.question.error", "minimum_two_options"): {
        "az": "Test sualı üçün ən azı 2 variant daxil edilməlidir.",
        "en": "At least 2 options must be entered for a multiple-choice question.",
        "ru": "Для тестового вопроса необходимо ввести минимум 2 варианта.",
        "tr": "Test sorusu için en az 2 seçenek girilmelidir.",
    },
    ("exams.view.results.message", "attempts_deleted"): {
        "az": "{count} cəhd silindi.",
        "en": "{count} attempts deleted.",
        "ru": "Удалено попыток: {count}.",
        "tr": "{count} deneme silindi.",
    },
    ("assignments.views.message", "submissions_deleted"): {
        "az": "{count} göndəriş silindi.",
        "en": "{count} submissions deleted.",
        "ru": "Удалено отправок: {count}.",
        "tr": "{count} gönderim silindi.",
    },
    ("projects.views.message", "submissions_deleted"): {
        "az": "{count} göndəriş silindi.",
        "en": "{count} submissions deleted.",
        "ru": "Удалено отправок: {count}.",
        "tr": "{count} gönderim silindi.",
    },
    ("accounts.manage_roles.message", "roles_updated_for_user"): {
        "az": "%(username)s üçün rollar yeniləndi: %(roles)s.",
        "en": "Roles updated for %(username)s: %(roles)s.",
        "ru": "Обновлены роли для %(username)s: %(roles)s.",
        "tr": "%(username)s için roller güncellendi: %(roles)s.",
    },
    ("accounts.permission_editor.message", "permission_added"): {
        "az": "`%(permission)s` permission-u əlavə edildi.",
        "en": "Permission `%(permission)s` was added.",
        "ru": "Добавлено разрешение `%(permission)s`.",
        "tr": "`%(permission)s` izni eklendi.",
    },
    ("accounts.permission_editor.message", "permission_removed"): {
        "az": "`%(permission)s` permission-u silindi.",
        "en": "Permission `%(permission)s` was removed.",
        "ru": "Разрешение `%(permission)s` удалено.",
        "tr": "`%(permission)s` izni kaldırıldı.",
    },
    ("accounts.superadmin_orgs.message", "organization_suspended"): {
        "az": "`%(organization_name)s` təşkilatı dayandırıldı.",
        "en": "Organization `%(organization_name)s` has been suspended.",
        "ru": "Организация `%(organization_name)s` приостановлена.",
        "tr": "`%(organization_name)s` organizasyonu askıya alındı.",
    },
    ("accounts.superadmin_orgs.message", "organization_unsuspended"): {
        "az": "`%(organization_name)s` təşkilatı yenidən aktiv edildi.",
        "en": "Organization `%(organization_name)s` has been reactivated.",
        "ru": "Организация `%(organization_name)s` снова активирована.",
        "tr": "`%(organization_name)s` organizasyonu yeniden etkinleştirildi.",
    },
    ("post_management.notification", "superadmin_deleted_post_title"): {
        "az": "Postunuz superadmin tərəfindən silindi: {title}",
        "en": "Your post was deleted by a superadmin: {title}",
        "ru": "Ваш пост удалён суперадминистратором: {title}",
        "tr": "Gönderiniz bir süper yönetici tarafından silindi: {title}",
    },
    ("post_management.notification", "superadmin_deleted_post_body"): {
        "az": "'{title}' başlıqlı postunuz superadmin tərəfindən silindi.\nSəbəb: {reason}",
        "en": "Your post titled '{title}' was deleted by a superadmin.\nReason: {reason}",
        "ru": "Ваш пост «{title}» удалён суперадминистратором.\nПричина: {reason}",
        "tr": "'{title}' başlıklı gönderiniz bir süper yönetici tarafından silindi.\nNeden: {reason}",
    },
    ("post_management.notification", "superadmin_deleted_org_post_title"): {
        "az": "Superadmin tərəfindən post silindi: {title}",
        "en": "A post was deleted by a superadmin: {title}",
        "ru": "Пост удалён суперадминистратором: {title}",
        "tr": "Bir gönderi süper yönetici tarafından silindi: {title}",
    },
    ("post_management.notification", "superadmin_deleted_org_post_body"): {
        "az": "Təşkilatınızdakı ({org_name}) '{title}' postu superadmin tərəfindən silindi.\nSəbəb: {reason}",
        "en": "The post '{title}' in your organization ({org_name}) was deleted by a superadmin.\nReason: {reason}",
        "ru": "Пост «{title}» в вашей организации ({org_name}) удалён суперадминистратором.\nПричина: {reason}",
        "tr": "Kurumunuzdaki ({org_name}) '{title}' gönderisi bir süper yönetici tarafından silindi.\nNeden: {reason}",
    },
    ("post_management.success", "post_deleted"): {
        "az": "'{title}' postu silindi.",
        "en": "The post '{title}' was deleted.",
        "ru": "Пост «{title}» удалён.",
        "tr": "'{title}' gönderisi silindi.",
    },
    ("post_management.notification", "org_admin_deleted_post_title"): {
        "az": "Postunuz silindi: {title}",
        "en": "Your post was deleted: {title}",
        "ru": "Ваш пост удалён: {title}",
        "tr": "Gönderiniz silindi: {title}",
    },
    ("post_management.notification", "org_admin_deleted_post_body"): {
        "az": "'{title}' başlıqlı postunuz təşkilat admini tərəfindən silindi.\nSəbəb: {reason}",
        "en": "Your post titled '{title}' was deleted by an organization admin.\nReason: {reason}",
        "ru": "Ваш пост «{title}» удалён администратором организации.\nПричина: {reason}",
        "tr": "'{title}' başlıklı gönderiniz kurum yöneticisi tarafından silindi.\nNeden: {reason}",
    },
    ("post_management.notification", "changes_requested_title"): {
        "az": "Postunuzda düzəliş tələb olunur: {title}",
        "en": "Changes are requested for your post: {title}",
        "ru": "По вашему посту запрошены правки: {title}",
        "tr": "Gönderiniz için düzeltme isteniyor: {title}",
    },
    ("post_management.notification", "changes_requested_body"): {
        "az": "'{title}' başlıqlı postunuzda düzəliş tələb olunur.\nFeedback: {feedback}",
        "en": "Changes are requested for your post titled '{title}'.\nFeedback: {feedback}",
        "ru": "По вашему посту «{title}» запрошены правки.\nОтзыв: {feedback}",
        "tr": "'{title}' başlıklı gönderiniz için düzeltme isteniyor.\nGeri bildirim: {feedback}",
    },
    ("exams.model.coding_submission.field", "selected_language"): {
        "az": "Seçilmiş dil",
        "en": "Selected language",
        "ru": "Выбранный язык",
        "tr": "Seçilen dil",
    },
    ("exams.template.student_exam_list", "live_card_pin_modal_exam"): {
        "az": "Canlı imtahan",
        "en": "Live exam",
        "ru": "Живой экзамен",
        "tr": "Canlı sınav",
    },
    ("exams.partial.exam_section", "status_not_started"): {
        "az": "İmtahan hələ başlamayıb. Başlama tarixi: {start_str}",
        "en": "This exam has not started yet. Start date: {start_str}",
        "ru": "Экзамен ещё не начался. Начало: {start_str}",
        "tr": "Sınav henüz başlamadı. Başlangıç tarihi: {start_str}",
    },
    ("exams.partial.exam_section", "status_not_started_yet"): {
        "az": "İmtahan hələ başlamayıb. Başlama tarixi: {start_str}",
        "en": "This exam has not started yet. Start date: {start_str}",
        "ru": "Экзамен ещё не начался. Начало: {start_str}",
        "tr": "Sınav henüz başlamadı. Başlangıç tarihi: {start_str}",
    },
    # Kitabxana (click / Django admin) sətirləri — səhv tərcümə boşaldılır ki,
    # Django öz core kataloqundakı düzgün mətnə geri düşsün.
    ("", "default: {default}"): {"en": "", "ru": "", "tr": ""},
    ("", "Error: {message}"): {"en": "", "ru": "", "tr": ""},
    ("", "No %(verbose_name_plural)s available"): {"en": "", "ru": "", "tr": ""},
}


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def parse_block(block):
    state = None
    parts = {"msgctxt": [], "msgid": []}
    for line in block.split("\n"):
        if line.startswith("#~") or line.startswith("msgid_plural") or line.startswith("msgstr["):
            return None
        if line.startswith("msgctxt "):
            state = "msgctxt"
            parts[state].append(line[8:])
        elif line.startswith("msgid "):
            state = "msgid"
            parts[state].append(line[6:])
        elif line.startswith("msgstr"):
            state = None
        elif line.startswith('"') and state:
            parts[state].append(line)

    def join(chunks):
        out = ""
        for chunk in chunks:
            chunk = chunk.strip()
            if chunk.startswith('"') and chunk.endswith('"'):
                out += chunk[1:-1]
        return out.replace('\\"', '"').replace("\\\\", "\\")

    if not parts["msgid"]:
        return None
    return join(parts["msgctxt"]), join(parts["msgid"])


def rewrite_block(block, msgstr):
    out, in_msgstr = [], False
    for line in block.split("\n"):
        if line.startswith("msgstr"):
            in_msgstr = True
            out.append(f'msgstr "{esc(msgstr)}"')
            continue
        if in_msgstr and line.strip().startswith('"'):
            continue
        in_msgstr = False
        if line.startswith("#,"):
            flags = [f.strip() for f in line[2:].split(",") if f.strip() and f.strip() != "fuzzy"]
            if flags:
                out.append("#, " + ", ".join(flags))
            continue
        out.append(line)
    return "\n".join(out)


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        with open(path, encoding="utf-8") as handle:
            blocks = handle.read().split("\n\n")
        changed = 0
        for index, block in enumerate(blocks):
            if not block.strip() or block.lstrip().startswith("#~"):
                continue
            parsed = parse_block(block)
            if parsed is None:
                continue
            key = (parsed[0], parsed[1])
            if key not in FIXES or lang not in FIXES[key]:
                continue
            blocks[index] = rewrite_block(block, FIXES[key][lang])
            changed += 1
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n\n".join(blocks))
        print(f"{lang}: {changed} sürüşmüş tərcümə düzəldildi")


if __name__ == "__main__":
    main()

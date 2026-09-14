#!/usr/bin/env python3
"""EMSArena i18n — W7 `w7cohort` (2026-09-14): köhnə imtahan-kohort səthinin əvəzlənmə kartı.

Sahibin 2026-09-07 qərarı: qrup reyestri əsasdır, köhnə kohort (`StudentGroup`)
səthi silinməyə gedir. Kohortu OLMAYAN təşkilatda `/exams/groups/` və
`/exams/groups/create/form/` boş siyahı/forma əvəzinə kiçik kart göstərir
(`exams/teacher/partials/_legacy_cohort_notice.html`). Yeni açarlar yalnız
`exams.template.legacy_cohort_notice` kontekstindədir.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. Msgid-lər AÇARDIR (`notice_title` kimi) — AZ msgstr aşağıdakı
`az` dəyəridir. TR qarşılığı QƏSDƏN AZ mənbədən fərqlidir (i18n qapısı
`msgstr == msgid` sətrini «tərcümə olunmamış» sayır).

İstifadə:  python scripts/i18n_fill_w7cohort_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "exams.template.legacy_cohort_notice"

ENTRIES = {
    CTX: {
        "notice_title": {
            "az": "Bu səth reyestr qrupları ilə əvəz olunub",
            "en": "This page has been replaced by registry groups",
            "ru": "Этот раздел заменён группами реестра",
            "tr": "Bu sayfa kayıt gruplarıyla değiştirildi",
        },
        "notice_body": {
            "az": (
                "İmtahana giriş üçün qruplar artıq qrup reyestrindən (akademik qruplar) seçilir: "
                "sehrbazın «Qruplar (reyestr)» seçicisi, giriş siyasəti, PIN və statistika reyestrlə "
                "işləyir. Bu təşkilatda köhnə imtahan kohortu yoxdur — yenisini yaratmağa ehtiyac yoxdur."
            ),
            "en": (
                "Exam access groups are now picked from the groups registry (academic groups): the "
                "wizard's “Groups (registry)” selector, the access policy, PIN and statistics all work "
                "with the registry. This organization has no legacy exam cohorts — there is no need to "
                "create one."
            ),
            "ru": (
                "Группы допуска к экзамену теперь выбираются из реестра групп (академические группы): "
                "селектор мастера «Группы (реестр)», политика доступа, PIN и статистика работают с "
                "реестром. В этой организации нет старых экзаменационных когорт — создавать их не нужно."
            ),
            "tr": (
                "Sınav erişim grupları artık grup kayıt defterinden (akademik gruplar) seçilir: "
                "sihirbazın «Gruplar (kayıt)» seçicisi, erişim politikası, PIN ve istatistikler kayıt "
                "defteriyle çalışır. Bu kurumda eski sınav kohortu yok — yenisini oluşturmaya gerek yok."
            ),
        },
        "action_open_registry": {
            "az": "Qrup reyestrinə keç",
            "en": "Open the groups registry",
            "ru": "Открыть реестр групп",
            "tr": "Grup kayıt defterini aç",
        },
        "action_open_exam_wizard": {
            "az": "İmtahan sehrbazına keç",
            "en": "Open the exam wizard",
            "ru": "Открыть мастер экзамена",
            "tr": "Sınav sihirbazını aç",
        },
        "secondary_still_need_cohort": {
            "az": "Köhnə kohort hələ də lazımdırsa:",
            "en": "If you still need a legacy cohort:",
            "ru": "Если старая когорта всё же нужна:",
            "tr": "Eski kohorta hâlâ ihtiyacınız varsa:",
        },
        "action_create_legacy_cohort": {
            "az": "köhnə kohort yarat (tövsiyə olunmur)",
            "en": "create a legacy cohort (not recommended)",
            "ru": "создать старую когорту (не рекомендуется)",
            "tr": "eski kohort oluştur (önerilmez)",
        },
        "summary_show_legacy_form": {
            "az": "Köhnə kohort formasını göstər (tövsiyə olunmur)",
            "en": "Show the legacy cohort form (not recommended)",
            "ru": "Показать форму старой когорты (не рекомендуется)",
            "tr": "Eski kohort formunu göster (önerilmez)",
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
            msgstr = translations.get(lang) or translations["az"]
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

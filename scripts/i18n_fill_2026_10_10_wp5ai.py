#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10: AI köməkçi düyməsini gizlətmək / sürüşdürmək (sahib, WP5).

Əlavə olunan mətnlər (hamısı `django.po`-dadır, kontekst `ai_assistant.fab`; `djangojs` kataloquna yeni
mətn YOXDUR — JS mətnləri şablondan data-atributla alır):
  * `templates/partials/_ai_assistant.html`: «Gizlət», bərpa nişanı, paneldəki «Gizlət», klaviatura ipucu,
    gizlətmə bildirişi + «Geri qaytar», yer dəyişmə elanları;
  * `templates/partials/_navbar.html`: istifadəçi menyusundakı «AI köməkçi düyməsi» açarı.

⚠️ Mətnlər HTML atributlarına düşür — tərcümələrdə ASCII qoşa dırnaq (") işlətməyin («», “” olar).
⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_wp5ai.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


FAB = "ai_assistant.fab"

_FAB = [
    _t("AI köməkçi", "AI assistant", "ИИ-помощник", "YZ asistanı"),
    _t("AI köməkçi düyməsi", "AI assistant button", "Кнопка ИИ-помощника", "Yapay zekâ asistanı düğmesi"),
    _t("AI köməkçini göstər", "Show the AI assistant", "Показать ИИ-помощника", "YZ asistanını göster"),
    _t("AI köməkçini gizlət", "Hide the AI assistant", "Скрыть ИИ-помощника", "Yapay zekâ asistanını gizle"),
    _t("Gizlət", "Hide", "Скрыть", "Gizle"),
    _t("Geri qaytar", "Undo", "Вернуть", "Geri al"),
    _t(
        "AI köməkçi gizlədildi. Ekranın kənarındakı «AI köməkçi» nişanı və ya istifadəçi menyusu ilə geri "
        "qaytara bilərsiniz.",
        "The AI assistant is hidden. You can bring it back with the “AI assistant” tab at the screen edge or "
        "from the user menu.",
        "ИИ-помощник скрыт. Вернуть его можно ярлыком «ИИ-помощник» у края экрана или через меню пользователя.",
        "Yapay zekâ asistanı gizlendi. Ekranın kenarındaki «YZ asistanı» sekmesiyle veya kullanıcı menüsünden "
        "geri getirebilirsiniz.",
    ),
    _t(
        "AI köməkçi sol kənara köçürüldü",
        "AI assistant moved to the left edge",
        "ИИ-помощник перемещён к левому краю",
        "Yapay zekâ asistanı sol kenara taşındı",
    ),
    _t(
        "AI köməkçi sağ kənara köçürüldü",
        "AI assistant moved to the right edge",
        "ИИ-помощник перемещён к правому краю",
        "Yapay zekâ asistanı sağ kenara taşındı",
    ),
    _t(
        "AI köməkçi yuxarı çəkildi",
        "AI assistant moved up",
        "ИИ-помощник перемещён выше",
        "Yapay zekâ asistanı yukarı taşındı",
    ),
    _t(
        "AI köməkçi aşağı endirildi",
        "AI assistant moved down",
        "ИИ-помощник перемещён ниже",
        "Yapay zekâ asistanı aşağı taşındı",
    ),
    _t(
        "Yerini dəyişmək üçün Alt ilə ox düymələrini basın: sol və sağ ox — kənar, yuxarı və aşağı ox — hündürlük. "
        "Delete — gizlətmək.",
        "To move it, press Alt with the arrow keys: left and right arrows — edge, up and down arrows — height. "
        "Delete — hide.",
        "Чтобы переместить, нажимайте Alt со стрелками: влево и вправо — край, вверх и вниз — высота. "
        "Delete — скрыть.",
        "Yerini değiştirmek için Alt ile ok tuşlarına basın: sol ve sağ ok — kenar, yukarı ve aşağı ok — yükseklik. "
        "Delete — gizle.",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    FAB: {row["az"]: row for row in _FAB},
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

#!/usr/bin/env python3
"""EMSArena i18n — «Fənn təhvili» panelinin yenidənqurma mətnləri (4 dil).

2026-09-09 sahib rəyi ilə bölmə SPA çərçivəsindən `ems_ui` server-render
panelinə keçdi: mərhələ zolağı, KPI kartları, avto filtr paneli, cədvəl
sətirləri, sətir çekmecəsi və «nə köçür / nə DƏYİŞMİR» xülasəsi yeni mətn
gətirdi. Hamısı `accounts.handover` kontekstindədir.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və idempotentdir. Yer tutucular (`%(n)d`, `%(name)s`, `%(scope)s`)
tərcümədə də EYNİ qalmalıdır (`scripts/check_i18n_catalogs.py` yoxlayır).

İstifadə:  python scripts/i18n_fill_handover_redesign_2026_09_09.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_HANDOVER = {
    # ── Mərhələ zolağı ──────────────────────────────────────────────────────
    "Təhvil mərhələləri": {
        "en": "Handover steps",
        "ru": "Этапы передачи",
        "tr": "Devir aşamaları",
    },
    "Kimin fənləri": {
        "en": "Whose subjects",
        "ru": "Чьи предметы",
        "tr": "Kimin dersleri",
    },
    "müəllim seçilib": {
        "en": "teacher selected",
        "ru": "преподаватель выбран",
        "tr": "öğretim elemanı seçildi",
    },
    "boş = səlahiyyət sahənizdəki bütün fənlər": {
        "en": "empty = every subject in your scope",
        "ru": "пусто = все предметы в вашей зоне полномочий",
        "tr": "boş = yetki alanınızdaki tüm dersler",
    },
    "%(n)d fənn təhvilə açıqdır": {
        "en": "%(n)d subject(s) can be handed over",
        "ru": "%(n)d предмет(ов) можно передать",
        "tr": "%(n)d ders devredilebilir",
    },
    "təsdiq pəncərəsində seçilir": {
        "en": "chosen in the confirmation dialog",
        "ru": "выбирается в окне подтверждения",
        "tr": "onay penceresinde seçilir",
    },
    "Təsdiqləyin": {"en": "Confirm", "ru": "Подтвердите", "tr": "Onaylayın"},
    "bal və davamiyyət dəyişmir": {
        "en": "grades and attendance stay unchanged",
        "ru": "баллы и посещаемость не меняются",
        "tr": "notlar ve devamsızlık değişmez",
    },
    # ── KPI kartları ────────────────────────────────────────────────────────
    "Əhatədəki fənn": {
        "en": "Subjects in scope",
        "ru": "Предметов в зоне полномочий",
        "tr": "Yetki alanındaki dersler",
    },
    "süzgəcə uyğun": {"en": "matching the filter", "ru": "по фильтру", "tr": "filtreye uygun"},
    "Təhvil verilə bilər": {
        "en": "Can be handed over",
        "ru": "Можно передать",
        "tr": "Devredilebilir",
    },
    "bloker yoxdur": {"en": "no blockers", "ru": "блокировок нет", "tr": "engel yok"},
    "Təhvil verilə bilməz": {
        "en": "Cannot be handed over",
        "ru": "Передать нельзя",
        "tr": "Devredilemez",
    },
    "hamısı açıqdır": {"en": "all are open", "ru": "все открыты", "tr": "tümü açık"},
    "Seçilmiş fənn": {"en": "Selected subjects", "ru": "Выбрано предметов", "tr": "Seçilen ders"},
    "təhvilə hazır": {"en": "ready to hand over", "ru": "готово к передаче", "tr": "devre hazır"},
    "Təsirlənən tələbə": {
        "en": "Students affected",
        "ru": "Затронуто студентов",
        "tr": "Etkilenen öğrenci",
    },
    "seçilmiş fənlərdə": {
        "en": "in the selected subjects",
        "ru": "в выбранных предметах",
        "tr": "seçilen derslerde",
    },
    # ── Bloker xülasəsi ─────────────────────────────────────────────────────
    "%(n)d bağlı jurnal": {
        "en": "%(n)d closed journal(s)",
        "ru": "%(n)d закрытый журнал",
        "tr": "%(n)d kapalı sınıf defteri",
    },
    "%(n)d keçmiş semestr": {
        "en": "%(n)d past semester(s)",
        "ru": "%(n)d прошедший семестр",
        "tr": "%(n)d geçmiş dönem",
    },
    "%(n)d arxiv açılış": {
        "en": "%(n)d archived offering(s)",
        "ru": "%(n)d архивная дисциплина",
        "tr": "%(n)d arşivlenmiş ders açılışı",
    },
    "%(n)d öz fənniniz": {
        "en": "%(n)d of your own subject(s)",
        "ru": "%(n)d ваш собственный предмет",
        "tr": "%(n)d kendi dersiniz",
    },
    "%(n)d fənn təhvil verilə bilməz": {
        "en": "%(n)d subject(s) cannot be handed over",
        "ru": "%(n)d предмет(ов) передать нельзя",
        "tr": "%(n)d ders devredilemez",
    },
    "Səbəb hər sətirdə yazılıb. Bağlı jurnal üçün əvvəlcə RİM semestri açmalıdır.": {
        "en": "The reason is written on each row. For a closed journal the registrar must reopen the semester first.",
        "ru": "Причина указана в каждой строке. Для закрытого журнала сначала откройте семестр в учебном отделе.",
        "tr": "Gerekçe her satırda yazılıdır. Kapalı sınıf defteri için önce öğrenci işleri dönemi açmalıdır.",
    },
    # ── Filtr paneli ────────────────────────────────────────────────────────
    "Vəziyyət": {"en": "Status", "ru": "Состояние", "tr": "Durum"},
    "Yalnız bloklananlar": {
        "en": "Blocked only",
        "ru": "Только заблокированные",
        "tr": "Yalnızca engellenenler",
    },
    "cari": {"en": "current", "ru": "текущий", "tr": "güncel"},
    "Nəticə: %(n)d fənn": {
        "en": "Result: %(n)d subject(s)",
        "ru": "Результат: %(n)d предмет(ов)",
        "tr": "Sonuç: %(n)d ders",
    },
    "Səlahiyyət sahəniz: %(scope)s": {
        "en": "Your scope: %(scope)s",
        "ru": "Ваша зона полномочий: %(scope)s",
        "tr": "Yetki alanınız: %(scope)s",
    },
    "Müəllim seçin…": {
        "en": "Choose a teacher…",
        "ru": "Выберите преподавателя…",
        "tr": "Öğretim elemanı seçin…",
    },
    # ── Cədvəl + boş vəziyyətlər ────────────────────────────────────────────
    "Əməliyyatı aparan": {"en": "Performed by", "ru": "Кто выполнил", "tr": "İşlemi yapan"},
    "Qüvvədədir": {"en": "In force", "ru": "Действует", "tr": "Yürürlükte"},
    "Süzgəci dəyişin və ya «Sıfırla» ilə tam siyahıya qayıdın.": {
        "en": "Change the filter or use “Reset” to return to the full list.",
        "ru": "Измените фильтр или нажмите «Сбросить», чтобы вернуться ко всему списку.",
        "tr": "Filtreyi değiştirin ya da “Sıfırla” ile tam listeye dönün.",
    },
    "Səlahiyyət sahənizdə dərs açılışı yoxdur": {
        "en": "There is no course offering in your scope",
        "ru": "В вашей зоне полномочий нет дисциплин",
        "tr": "Yetki alanınızda ders açılışı yok",
    },
    "Semestr açıldıqdan sonra fənlər burada görünəcək.": {
        "en": "Subjects appear here once the semester is opened.",
        "ru": "Предметы появятся здесь после открытия семестра.",
        "tr": "Dönem açıldıktan sonra dersler burada görünür.",
    },
    "İlk təhvildən sonra kim, nə vaxt və niyə dəyişdiyi burada qalır.": {
        "en": "After the first handover, who changed what, when and why stays here.",
        "ru": "После первой передачи здесь остаётся, кто, когда и почему внёс изменение.",
        "tr": "İlk devirden sonra kimin ne zaman ve neden değiştirdiği burada kalır.",
    },
    # ── Cədvəl sətri + seçim ────────────────────────────────────────────────
    "%(name)s — seç": {
        "en": "%(name)s — select",
        "ru": "%(name)s — выбрать",
        # ⚠️ TR-də «seç» AZ msgid ilə eyni olurdu (identity = tərcümə borcu);
        # checkbox üçün daha dəqiq feil işlədilir.
        "tr": "%(name)s — işaretle",
    },
    "Bu səhifədə təhvilə açıq olanların hamısını seç": {
        "en": "Select every subject on this page that can be handed over",
        "ru": "Выбрать на этой странице все предметы, которые можно передать",
        "tr": "Bu sayfada devredilebilir tüm dersleri seç",
    },
    "Seçimi ləğv et": {"en": "Clear selection", "ru": "Снять выбор", "tr": "Seçimi kaldır"},
    "Ətraflı": {"en": "Details", "ru": "Подробнее", "tr": "Ayrıntı"},
    "Bu fənni təhvil ver": {
        "en": "Hand over this subject",
        "ru": "Передать этот предмет",
        "tr": "Bu dersi devret",
    },
    "Bağla": {"en": "Close", "ru": "Закрыть", "tr": "Kapat"},
    # ── Çekmecə + təsdiq xülasəsi ───────────────────────────────────────────
    "Fənn haqqında": {"en": "About the subject", "ru": "О предмете", "tr": "Ders hakkında"},
    "Təhvil nəyə toxunur, nəyə toxunmur.": {
        "en": "What the handover touches and what it does not.",
        "ru": "Что затрагивает передача, а что — нет.",
        "tr": "Devir neyi etkiler, neyi etkilemez.",
    },
    "Təhvildə nə köçür": {
        "en": "What moves in the handover",
        "ru": "Что переходит при передаче",
        "tr": "Devirde ne aktarılır",
    },
    "Nə köçür": {"en": "What moves", "ru": "Что переходит", "tr": "Ne aktarılır"},
    "Nə DƏYİŞMİR": {"en": "What does NOT change", "ru": "Что НЕ меняется", "tr": "Ne DEĞİŞMEZ"},
    "Elektron jurnalın sahibliyi — bal yazma hüququ yeni müəllimə keçir.": {
        "en": "Ownership of the electronic journal — the right to enter grades moves to the new teacher.",
        "ru": "Владение электронным журналом — право выставлять баллы переходит новому преподавателю.",
        "tr": "Elektronik sınıf defterinin sahipliği — not girme yetkisi yeni öğretim elemanına geçer.",
    },
    "Yazılmış bal və davamiyyət olduğu kimi qalır.": {
        "en": "Grades and attendance already recorded stay as they are.",
        "ru": "Уже выставленные баллы и посещаемость остаются как есть.",
        "tr": "Girilmiş notlar ve devamsızlık olduğu gibi kalır.",
    },
    "Keçmiş dərslərin müəllimi dəyişmir — kim keçibsə, o qalır.": {
        "en": "The teacher of past lessons does not change — whoever taught them stays.",
        "ru": "Преподаватель прошедших занятий не меняется — кто вёл, тот и остаётся.",
        "tr": "Geçmiş derslerin öğretim elemanı değişmez — kim işlediyse o kalır.",
    },
    "Köhnə müəllim jurnalı yalnız-oxu rejimində görməyə davam edir.": {
        "en": "The previous teacher keeps read-only access to the journal.",
        "ru": "Прежний преподаватель продолжает видеть журнал в режиме только для чтения.",
        "tr": "Önceki öğretim elemanı defteri salt okunur olarak görmeye devam eder.",
    },
    "Sillabus müəllifinə bağlıdır — avtomatik köçürülmür.": {
        "en": "The syllabus belongs to its author — it is not transferred automatically.",
        "ru": "Силлабус привязан к автору — автоматически он не передаётся.",
        "tr": "İzlence yazarına bağlıdır — otomatik olarak aktarılmaz.",
    },
    "Seçilmiş fənlərin jurnal sahibliyi yeni müəllimə keçir. Yazılmış bal və davamiyyət olduğu kimi qalır.": {
        "en": (
            "Journal ownership of the selected subjects moves to the new teacher. "
            "Grades and attendance already recorded stay as they are."
        ),
        "ru": (
            "Владение журналом выбранных предметов переходит новому преподавателю. "
            "Уже выставленные баллы и посещаемость остаются как есть."
        ),
        "tr": (
            "Seçilen derslerin defter sahipliği yeni öğretim elemanına geçer. "
            "Girilmiş notlar ve devamsızlık olduğu gibi kalır."
        ),
    },
    "Jurnal sahibliyi əvvəlki müəllimə qayıdır. Bu əməl də auditə yazılır.": {
        "en": "Journal ownership returns to the previous teacher. This action is audited as well.",
        "ru": "Владение журналом возвращается прежнему преподавателю. Это действие также фиксируется в аудите.",
        "tr": "Defter sahipliği önceki öğretim elemanına döner. Bu işlem de denetim kaydına yazılır.",
    },
    "Siyahıda yalnız bu təşkilatda bal yazma səlahiyyəti olan aktiv müəllimlər var.": {
        "en": "The list only contains active teachers who may enter grades in this organization.",
        "ru": "В списке только активные преподаватели, имеющие право выставлять баллы в этой организации.",
        "tr": "Listede yalnızca bu kurumda not girme yetkisi olan aktif öğretim elemanları vardır.",
    },
    # ── JS mətn kataloqu ────────────────────────────────────────────────────
    "Bloklanmış sətir seçilmir.": {
        "en": "A blocked row cannot be selected.",
        "ru": "Заблокированную строку выбрать нельзя.",
        "tr": "Engellenen satır seçilemez.",
    },
    "Bir dəfəyə daha çox fənn seçilə bilməz.": {
        "en": "No more subjects can be selected at once.",
        "ru": "Больше предметов за один раз выбрать нельзя.",
        "tr": "Tek seferde daha fazla ders seçilemez.",
    },
    "Əvvəlcə ən azı bir fənn seçin.": {
        "en": "Select at least one subject first.",
        "ru": "Сначала выберите хотя бы один предмет.",
        "tr": "Önce en az bir ders seçin.",
    },
}

ENTRIES = {"accounts.handover": _HANDOVER}


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

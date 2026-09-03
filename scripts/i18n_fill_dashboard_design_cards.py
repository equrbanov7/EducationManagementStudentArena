#!/usr/bin/env python3
"""EMSArena i18n — ana səhifə (dashboard) dizayn-dalğası keçid kartları (4 dil).

Mənbə: `apps/accounts/views/profile/_sections/dashboard_staff_widgets.py`
`_DESIGN_LINK_CARDS` (QA dalğa-2 P2-1 düzəlişi). Kontekst: `accounts.dashboard`.
Append-only, idempotent — `scripts/i18n_fill_design_stage5_6.py` ilə eyni üsul.
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]
CTX = "accounts.dashboard"


def _e(en, ru, tr):
    return {"en": en, "ru": ru, "tr": tr}


ENTRIES = {
    # başlıqlar
    "Dərs yükü mərkəzi": _e("Teaching load centre", "Центр учебной нагрузки", "Ders yükü merkezi"),
    "Yük vizası": _e("Load visa", "Виза нагрузки", "Yük vizesi"),
    "Yük təsdiqi": _e("Load approval", "Утверждение нагрузки", "Yük onayı"),
    "Yük — ümumi baxış": _e("Load — overview", "Нагрузка — обзор", "Yük — genel bakış"),
    "Sual təsdiqi": _e("Question approval", "Утверждение вопросов", "Soru onayı"),
    "Tədris planı": _e("Curriculum", "Учебный план", "Öğretim planı"),
    "Semestr açılışı": _e("Semester opening", "Открытие семестра", "Dönem açılışı"),
    "Qruplar reyestri": _e("Groups registry", "Реестр групп", "Grup kaydı"),
    "Tələbə qəbulu": _e("Student admission", "Приём студентов", "Öğrenci kabulü"),
    "Tələbə reyestri": _e("Student registry", "Реестр студентов", "Öğrenci kaydı"),
    "Keçilmiş dərslər": _e("Lessons taught", "Проведённые занятия", "İşlenen dersler"),
    "Universitet strukturu": _e("University structure", "Структура университета", "Üniversite yapısı"),
    # izah mətnləri
    "Tədris planından dərs yükü tapşırığı yaradın, dilimlərə bölün, vizaları izləyin.": _e(
        "Create a teaching-load task from the curriculum, split it into slices and track the visas.",
        "Создайте задание по нагрузке из учебного плана, разбейте на части и отслеживайте визы.",
        "Öğretim planından ders yükü görevi oluşturun, dilimlere ayırın ve vizeleri izleyin.",
    ),
    "Fakültə diliminə koordinator vizası verin və ya geri qaytarın.": _e(
        "Grant the coordinator visa to the faculty slice or send it back.",
        "Поставьте визу координатора на факультетскую часть или верните её.",
        "Fakülte dilimine koordinatör vizesi verin veya geri gönderin.",
    ),
    "Dekanlıq təsdiqi gözləyən fakültə dilimləri.": _e(
        "Faculty slices awaiting the dean's office approval.",
        "Факультетские части, ожидающие утверждения деканата.",
        "Dekanlık onayı bekleyen fakülte dilimleri.",
    ),
    "Universitet üzrə dərs yükü zəncirinin gedişi.": _e(
        "Progress of the teaching-load chain across the university.",
        "Ход цепочки учебной нагрузки по университету.",
        "Üniversite genelinde ders yükü zincirinin ilerleyişi.",
    ),
    "İmtahan Mərkəzinə getməzdən əvvəl kafedra təsdiqi gözləyən sual göndərişləri.": _e(
        "Question submissions awaiting chair approval before they reach the Exam Centre.",
        "Отправки вопросов, ожидающие утверждения кафедры перед Экзаменационным центром.",
        "Sınav Merkezine gitmeden önce bölüm onayı bekleyen soru gönderimleri.",
    ),
    "İxtisas üzrə tədris planı sətirləri və təsdiq zənciri.": _e(
        "Curriculum rows per programme and the approval chain.",
        "Строки учебного плана по специальности и цепочка утверждения.",
        "Program bazında öğretim planı satırları ve onay zinciri.",
    ),
    "Təsdiqlənmiş plandan açılışları yaradın və semestri kilidləyin.": _e(
        "Generate offerings from the approved plan and lock the semester.",
        "Создайте открытия из утверждённого плана и заблокируйте семестр.",
        "Onaylı plandan açılışları oluşturun ve dönemi kilitleyin.",
    ),
    "Kurs/ixtisas üzrə qruplar və dil sektorları.": _e(
        "Groups and language sectors per year/programme.",
        "Группы и языковые секторы по курсу/специальности.",
        "Sınıf/program bazında gruplar ve dil sektörleri.",
    ),
    "ATİS qəbul siyahısından tələbə hesabı və akademik qeyd yaradın.": _e(
        "Create student accounts and academic records from the ATİS admission list.",
        "Создайте учётные записи и академические записи студентов из списка приёма ATİS.",
        "ATİS kabul listesinden öğrenci hesabı ve akademik kayıt oluşturun.",
    ),
    "Köçürmə, akademik məzuniyyət, xaric və bərpa hərəkətləri.": _e(
        "Transfer, academic leave, expulsion and reinstatement movements.",
        "Перевод, академический отпуск, отчисление и восстановление.",
        "Nakil, akademik izin, ihraç ve geri dönüş hareketleri.",
    ),
    "Plan saatı ilə faktiki keçilmiş dərslərin müqayisəsi.": _e(
        "Planned hours compared with the lessons actually taught.",
        "Сравнение плановых часов с фактически проведёнными занятиями.",
        "Plan saati ile fiilen işlenen derslerin karşılaştırması.",
    ),
    "Fakültə → kafedra → ixtisas ağacı və rəhbər təyinatları.": _e(
        "Faculty → chair → programme tree and head appointments.",
        "Дерево факультет → кафедра → специальность и назначения руководителей.",
        "Fakülte → bölüm → program ağacı ve yönetici atamaları.",
    ),
    # keçid etiketləri
    "Mərkəzə keç": _e("Go to the centre", "Перейти в центр", "Merkeze git"),
    "Vizaya keç": _e("Go to the visa", "Перейти к визе", "Vizeye git"),
    "Təsdiqə keç": _e("Go to approval", "Перейти к утверждению", "Onaya git"),
    "Baxışa keç": _e("Go to the overview", "Перейти к обзору", "Genel bakışa git"),
    "Plana keç": _e("Go to the plan", "Перейти к плану", "Plana git"),
    "Açılışa keç": _e("Go to the opening", "Перейти к открытию", "Açılışa git"),
    "Reyestrə keç": _e("Go to the registry", "Перейти к реестру", "Kayda git"),
    "Qəbula keç": _e("Go to admission", "Перейти к приёму", "Kabule git"),
    "Jurnala keç": _e("Go to the log", "Перейти к журналу", "Günlüğe git"),
    "Struktura keç": _e("Go to the structure", "Перейти к структуре", "Yapıya git"),
}


#: Qabıq xəbərdarlığı (W2-8) — `accounts/profile/_messages.html`, kontekst `profile.shell`.
SHELL_ENTRIES = {
    "Bu bölməyə icazəniz yoxdur.": _e(
        "You do not have access to this section.",
        "У вас нет доступа к этому разделу.",
        "Bu bölüme erişim izniniz yok.",
    ),
    "İstənilən bölmə mövcud deyil və ya rolunuz üçün açıq deyil — ana səhifəyə qaytarıldınız.": _e(
        "The requested section does not exist or is not open to your role — you were returned to the home page.",
        "Запрошенный раздел не существует или недоступен для вашей роли — вы возвращены на главную страницу.",
        "İstenen bölüm mevcut değil veya rolünüze açık değil — ana sayfaya yönlendirildiniz.",
    ),
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def existing_pairs(lang):
    import polib

    return {(e.msgctxt or "", e.msgid) for e in polib.pofile(po_path(lang)) if not e.obsolete}


def fill(lang):
    path = po_path(lang)
    existing = existing_pairs(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    blocks, added = [], 0
    for ctx, entries in ((CTX, ENTRIES), ("profile.shell", SHELL_ENTRIES)):
        for msgid, translations in entries.items():
            if (ctx, msgid) in existing:
                continue
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations[lang]
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

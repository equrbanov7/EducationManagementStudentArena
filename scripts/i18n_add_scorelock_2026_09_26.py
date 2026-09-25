#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-26: «İmtahan balının daxil edilməsi» bölməsində BİTMİŞ
DÖVR KİLİDİ, RİM rəhbərinin «Düzəliş rejimini aktivləşdir» açarı və təsdiq
dialoqunun məcburi fayl (təqdimat skanı) sahəsi.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_scorelock_2026_09_26.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_R = "registrar.exam_score_entry"
_A = "accounts.exam_score_entry"

_SUBMISSION = "Bitmiş dövrdə hər yazı təqdimat tələb edir — səbəb, qeyd və skan edilmiş sənəd məcburidir."
_SUBMISSION_T = (
    "In a finished period every write requires a submission — a reason, a note and a scanned document are mandatory.",
    "В завершённом периоде каждая запись требует представления — причина, примечание и скан документа обязательны.",
    "Tamamlanmış dönemde her kayıt başvuru gerektirir — gerekçe, not ve taranmış belge zorunludur.",
)

STRINGS = {
    (
        _R,
        "Bitmiş dövrün imtahan balları kilidlidir — yalnız RİM rəhbəri təqdimat əsasında düzəliş edə bilər.",
    ): (
        "Exam scores of a finished period are locked — only the head of the RIM can correct them based on a submission.",
        "Экзаменационные баллы завершённого периода заблокированы — исправлять их может только руководитель RİM на основании представления.",
        "Tamamlanmış dönemin sınav puanları kilitlidir — yalnızca RİM başkanı başvuru üzerine düzeltme yapabilir.",
    ),
    (
        _R,
        "Bitmiş dövrün balını yazmaq üçün əvvəlcə «Düzəliş rejimini aktivləşdir» düyməsini basın.",
    ): (
        "To write a score for a finished period, first press «Activate correction mode».",
        "Чтобы записать балл завершённого периода, сначала нажмите «Включить режим исправления».",
        "Tamamlanmış dönem için puan yazmak üzere önce «Düzeltme modunu etkinleştir» düğmesine basın.",
    ),
    (_R, _SUBMISSION): _SUBMISSION_T,
    (_A, _SUBMISSION): _SUBMISSION_T,
    (_R, "Düzəliş rejimi aktivdir"): ("Correction mode is active", "Режим исправления включён", "Düzeltme modu etkin"),
    (
        _R,
        "Bitmiş dövrün balları yalnız təqdimat əsasında yazılır — hər yazı üçün səbəb, qeyd və skan edilmiş sənəd məcburidir və audit olunur.",
    ): (
        "Scores of a finished period are written only based on a submission — every write requires a reason, a note and a scanned document and is audited.",
        "Баллы завершённого периода записываются только на основании представления — для каждой записи обязательны причина, примечание и скан документа; всё фиксируется в аудите.",
        "Tamamlanmış dönemin puanları yalnızca başvuru üzerine yazılır — her kayıt için gerekçe, not ve taranmış belge zorunludur ve denetlenir.",
    ),
    (_R, "Bitmiş dövr — ballar kilidlidir"): (
        "Finished period — scores are locked",
        "Завершённый период — баллы заблокированы",
        "Tamamlanmış dönem — puanlar kilitli",
    ),
    (
        _R,
        "Bu semestr başa çatıb: ilk daxiletmə, dəyişiklik və fayldan yükləmə bağlıdır. Düzəliş yalnız RİM rəhbəri tərəfindən təqdimat əsasında mümkündür.",
    ): (
        "This semester has ended: first entry, changes and file import are closed. Corrections are possible only by the head of the RIM based on a submission.",
        "Этот семестр завершён: первичный ввод, изменения и загрузка из файла закрыты. Исправление возможно только руководителем RİM на основании представления.",
        "Bu dönem sona erdi: ilk giriş, değişiklik ve dosyadan yükleme kapalıdır. Düzeltme yalnızca RİM başkanı tarafından başvuru üzerine yapılabilir.",
    ),
    (_R, "Düzəliş rejimindən çıx (kilidlə)"): (
        "Exit correction mode (lock)",
        "Выйти из режима исправления (заблокировать)",
        "Düzeltme modundan çık (kilitle)",
    ),
    (_R, "Düzəliş rejimini aktivləşdir"): (
        "Activate correction mode",
        "Включить режим исправления",
        "Düzeltme modunu etkinleştir",
    ),
    (
        _R,
        "Bitmiş dövrün düzəliş rejimi — hər yazı (ilk daxiletmə də) təqdimat əsasındadır: səbəb, qeyd və skan edilmiş sənəd üçü də məcburidir və audit olunur.",
    ): (
        "Correction mode for a finished period — every write (including a first entry) is based on a submission: a reason, a note and a scanned document are all mandatory and audited.",
        "Режим исправления завершённого периода — каждая запись (включая первичный ввод) делается на основании представления: причина, примечание и скан документа обязательны и фиксируются в аудите.",
        "Tamamlanmış dönemin düzeltme modu — her kayıt (ilk giriş dahil) başvuruya dayanır: gerekçe, not ve taranmış belgenin üçü de zorunludur ve denetlenir.",
    ),
    (_R, "Skan edilmiş sənəd (təqdimat)"): (
        "Scanned document (submission)",
        "Скан документа (представление)",
        "Taranmış belge (başvuru)",
    ),
    (_R, "Faylı seçmək üçün klikləyin və ya bura sürüşdürün"): (
        "Click to choose a file or drag it here",
        "Нажмите, чтобы выбрать файл, или перетащите его сюда",
        "Dosya seçmek için tıklayın veya buraya sürükleyin",
    ),
    (_R, "ən çox %(size)s MB"): ("up to %(size)s MB", "не более %(size)s МБ", "en fazla %(size)s MB"),
    (_R, "vərəq kartında seçilib"): (
        "selected on the sheet card",
        "выбран в карточке ведомости",
        "tutanak kartında seçildi",
    ),
    (_R, "Vərəq kartında skan seçilibsə, bu sahə boş qala bilər."): (
        "If a scan is selected on the sheet card, this field may stay empty.",
        "Если скан выбран в карточке ведомости, это поле можно оставить пустым.",
        "Tutanak kartında tarama seçildiyse bu alan boş kalabilir.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
            if "%(" in msgid:
                entry.flags.append("python-format")
            po.append(entry)
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()

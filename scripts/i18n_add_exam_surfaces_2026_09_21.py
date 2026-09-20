#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-21: imtahan səthləri (workbench keçid izahları, Word
şablonu təlimatı, DOCX başlıqları). Dörd kataloqa msgctxt+msgid əlavə edir; AZ
msgstr = msgid. İdempotent; sonra `compilemessages`.
İstifadə:  python scripts/i18n_add_exam_surfaces_2026_09_21.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

STRINGS = {
    ("exams.template.test_question_bank", "İmtahandakı mövcud sualları redaktə et, aktiv/deaktiv et və ya sil"): (
        "Edit, activate/deactivate or delete the exam's existing questions",
        "Редактировать, включать/выключать или удалять существующие вопросы экзамена",
        "Sınavdaki mevcut soruları düzenle, etkinleştir/devre dışı bırak veya sil",
    ),
    ("exams.template.test_question_bank", "Kafedranın qəbul olunmuş sual bankından hazır sualları seçib əlavə et"): (
        "Pick ready questions from the department's approved question bank",
        "Выбрать готовые вопросы из утверждённого банка вопросов кафедры",
        "Bölümün onaylanmış soru bankasından hazır soruları seçip ekle",
    ),
    (
        "exams.template.test_question_bank",
        "Word (.docx) şablonunu endir, Word-də aç, nümunə suallara bax və öz suallarını eyni formada yaz — sonra faylı bura yüklə. TXT variantı da eyni formatdadır.",
    ): (
        "Download the Word (.docx) template, open it in Word, look at the sample questions and write yours in the same format — then upload the file here. The TXT variant uses the same format.",
        "Скачайте шаблон Word (.docx), откройте его в Word, посмотрите примеры вопросов и напишите свои в том же формате — затем загрузите файл сюда. Вариант TXT имеет тот же формат.",
        "Word (.docx) şablonunu indirin, Word'de açın, örnek sorulara bakın ve kendi sorularınızı aynı biçimde yazın — sonra dosyayı buraya yükleyin. TXT sürümü de aynı biçimdedir.",
    ),
    (
        "exams.template.test_question_bank",
        "Aşağıdakı nümunə suallara baxın, öz suallarınızı EYNİ formada bu faylda yazın və faylı sistemə yükləyin. «#» ilə başlayan sətirlər izahdır — import zamanı nəzərə alınmır (silə də bilərsiniz).",
    ): (
        "Look at the sample questions below, write your own questions in this file in the SAME format and upload the file to the system. Lines starting with «#» are explanations — they are ignored on import (you may delete them).",
        "Посмотрите примеры вопросов ниже, напишите свои вопросы в этом файле в ТОМ ЖЕ формате и загрузите файл в систему. Строки, начинающиеся с «#», — пояснения; при импорте они игнорируются (их можно удалить).",
        "Aşağıdaki örnek sorulara bakın, kendi sorularınızı bu dosyada AYNI biçimde yazın ve dosyayı sisteme yükleyin. «#» ile başlayan satırlar açıklamadır — içe aktarmada yok sayılır (silebilirsiniz).",
    ),
    ("exams.template.test_question_bank", "Test sual bankı şablonu"): (
        "Test question bank template",
        "Шаблон банка тестовых вопросов",
        "Test soru bankası şablonu",
    ),
    ("exams.template.question_bank_detail", "Test sual bankı şablonu"): (
        "Test question bank template",
        "Шаблон банка тестовых вопросов",
        "Test soru bankası şablonu",
    ),
    ("accounts.network_zone", "Yalnız universitet şəbəkəsindən"): (
        "University network only",
        "Только из сети университета",
        "Yalnızca üniversite ağından",
    ),
    ("accounts.network_zone", "Şəbəkə məhdudiyyəti"): ("Network restriction", "Сетевое ограничение", "Ağ kısıtlaması"),
    ("accounts.network_zone", "Elektron jurnal yalnız universitet şəbəkəsində açılır"): (
        "The electronic journal opens only on the university network",
        "Электронный журнал открывается только из сети университета",
        "Elektronik günlük yalnızca üniversite ağında açılır",
    ),
    ("accounts.network_zone", "Bu hesabla giriş yalnız universitet şəbəkəsindən mümkündür"): (
        "This account can sign in only from the university network",
        "Вход с этой учётной записью возможен только из сети университета",
        "Bu hesapla giriş yalnızca üniversite ağından mümkündür",
    ),
    (
        "accounts.network_zone",
        "Jurnal qeydləri kampus daxilindən (universitet Wi-Fi/LAN) aparılır. Digər bölmələr — fənlər, imtahanlar, sillabuslar — kənardan da işləyir.",
    ): (
        "Journal entries are made from inside the campus (university Wi-Fi/LAN). Other sections — subjects, exams, syllabi — also work from outside.",
        "Записи в журнал ведутся из кампуса (Wi-Fi/LAN университета). Остальные разделы — предметы, экзамены, силлабусы — работают и извне.",
        "Günlük kayıtları kampüs içinden (üniversite Wi-Fi/LAN) yapılır. Diğer bölümler — dersler, sınavlar, izlenceler — dışarıdan da çalışır.",
    ),
    (
        "accounts.network_zone",
        "İnzibati hesablar təhlükəsizlik səbəbindən kənar şəbəkədən açılmır. Universitet şəbəkəsinə qoşulub yenidən daxil olun.",
    ): (
        "For security, administrative accounts do not open from outside networks. Connect to the university network and sign in again.",
        "В целях безопасности административные учётные записи не открываются из внешних сетей. Подключитесь к сети университета и войдите снова.",
        "Güvenlik nedeniyle yönetici hesapları dış ağlardan açılmaz. Üniversite ağına bağlanıp yeniden giriş yapın.",
    ),
    ("accounts.network_zone", "Universitet Wi-Fi / LAN"): (
        "University Wi-Fi / LAN",
        "Wi-Fi / LAN университета",
        "Üniversite Wi-Fi / LAN",
    ),
    ("accounts.network_zone", "Şəbəkə zonası qaydası"): (
        "Network zone rule",
        "Правило сетевой зоны",
        "Ağ bölgesi kuralı",
    ),
    ("accounts.network_zone", "Çıxış"): ("Sign out", "Выйти", "Çıkış"),
    (
        "accounts.network_zone",
        "Bu qayda sistem administratoru tərəfindən təyin olunub; sual olarsa RİM-ə müraciət edin.",
    ): (
        "This rule is set by the system administrator; contact the Digital Development Centre with questions.",
        "Это правило задано системным администратором; по вопросам обращайтесь в Центр цифрового развития.",
        "Bu kural sistem yöneticisi tarafından belirlenmiştir; sorularınız için Dijital Gelişim Merkezi'ne başvurun.",
    ),
    ("accounts.network_zone", "Sorğu kənar şəbəkədən gəldi; bu bölmə üçün daxili zona tələb olunur."): (
        "The request came from an outside network; this section requires the internal zone.",
        "Запрос пришёл из внешней сети; для этого раздела требуется внутренняя зона.",
        "İstek dış ağdan geldi; bu bölüm iç bölge gerektirir.",
    ),
    ("exams.crumbs", "Naviqasiya yolu"): ("Breadcrumb navigation", "Навигационная цепочка", "Gezinti yolu"),
    ("exams.template.question_bank_detail", "Yazılı sual bankı şablonu"): (
        "Written question bank template",
        "Шаблон банка письменных вопросов",
        "Yazılı soru bankası şablonu",
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
            po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()

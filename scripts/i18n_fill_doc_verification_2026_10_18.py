#!/usr/bin/env python3
"""EMSArena i18n — «Sənəd yoxlaması» (2026-10-18): QR + kodla möhürlənmiş rəsmi sənəd, publik `/yoxla/<kod>/`,
əməkdaş səhifəsi «Sənəd yoxlaması», `document_seal.manage` açarı, transkript PDF-inin yoxlama bloku.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. ⚠️ `makemessages` İŞLƏDİLMİR.
İstifadə:  python scripts/i18n_fill_doc_verification_2026_10_18.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

PUB = "verification.public"
STAFF = "verification.staff"
FACT = "verification.fact"
DOC = "verification.doc_type"
AUDIT = "verification.audit"
PDF = "registrar.pdf"
PERM = "organizations.permission.label"
SIDEBAR = "profile.sidebar"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    PUB: {
        "Sənəd yoxlaması": t("Document verification", "Проверка документа", "Belge doğrulama", "Dokumentenprüfung"),
        "Elektron sənəd yoxlaması": t(
            "Electronic document verification",
            "Электронная проверка документов",
            "Elektronik belge doğrulama",
            "Elektronische Dokumentenprüfung",
        ),
        "Sənəd etibarlıdır": t(
            "The document is valid", "Документ действителен", "Belge geçerlidir", "Das Dokument ist gültig"
        ),
        "Sənəd ləğv edilib": t(
            "The document has been revoked",
            "Документ аннулирован",
            "Belge iptal edildi",
            "Das Dokument wurde widerrufen",
        ),
        "Bu sənəd universitetin elektron sistemi tərəfindən verilib və hazırda qüvvədədir.": t(
            "This document was issued by the university's electronic system and is currently in force.",
            "Этот документ выдан электронной системой университета и в настоящее время действителен.",
            "Bu belge üniversitenin elektronik sistemi tarafından düzenlenmiştir ve şu anda yürürlüktedir.",
            "Dieses Dokument wurde vom elektronischen System der Universität ausgestellt und ist derzeit gültig.",
        ),
        "Sənəd universitet tərəfindən ləğv edilib — ona etibar etməyin.": t(
            "The university has revoked this document — do not rely on it.",
            "Университет аннулировал этот документ — не полагайтесь на него.",
            "Belge üniversite tarafından iptal edildi — bu belgeye güvenmeyin.",
            "Die Universität hat dieses Dokument widerrufen — verlassen Sie sich nicht darauf.",
        ),
        "Ləğv tarixi": t("Revoked on", "Дата аннулирования", "İptal tarihi", "Widerrufen am"),
        "Sənədin növü": t("Document type", "Тип документа", "Belge türü", "Dokumentart"),
        "Verən təşkilat": t("Issued by", "Выдавшая организация", "Düzenleyen kurum", "Ausstellende Einrichtung"),
        "Verilmə tarixi": t("Issue date", "Дата выдачи", "Düzenlenme tarihi", "Ausstellungsdatum"),
        "Sənədin sahibi": t("Holder", "Владелец документа", "Belge sahibi", "Inhaber/in"),
        "Yoxlama kodu": t("Verification code", "Код проверки", "Doğrulama kodu", "Prüfcode"),
        "Səhifə yalnız sənədin əsas göstəricilərini göstərir. Tam məzmunu sənədin özü ilə tutuşdurun və ya faylı "
        "aşağıda müqayisə edin.": t(
            "This page shows only the document's key figures. Compare the full content with the document itself "
            "or compare the file below.",
            "На странице показаны только основные показатели документа. Сверьте полное содержание с самим "
            "документом или сравните файл ниже.",
            "Bu sayfa yalnızca belgenin temel göstergelerini gösterir. Tam içeriği belgenin kendisiyle karşılaştırın "
            "veya dosyayı aşağıda karşılaştırın.",
            "Diese Seite zeigt nur die wichtigsten Angaben des Dokuments. Vergleichen Sie den vollständigen Inhalt "
            "mit dem Dokument selbst oder vergleichen Sie die Datei unten.",
        ),
        "Faylı müqayisə et": t("Compare a file", "Сравнить файл", "Dosyayı karşılaştır", "Datei vergleichen"),
        "Sizə verilmiş PDF faylı seçin — sistem onun rəqəmsal izini (SHA-256) universitetin verdiyi nüsxə ilə "
        "tutuşdurur. Fayl saxlanılmır. Ən çox %(mb)s MB.": t(
            "Choose the PDF file you were given — the system compares its digital fingerprint (SHA-256) with the "
            "copy the university issued. The file is not stored. At most %(mb)s MB.",
            "Выберите полученный PDF-файл — система сравнит его цифровой отпечаток (SHA-256) с копией, выданной "
            "университетом. Файл не сохраняется. Не более %(mb)s МБ.",
            "Size verilen PDF dosyasını seçin — sistem dijital parmak izini (SHA-256) üniversitenin düzenlediği "
            "nüshayla karşılaştırır. Dosya saklanmaz. En fazla %(mb)s MB.",
            "Wählen Sie die erhaltene PDF-Datei — das System vergleicht ihren digitalen Fingerabdruck (SHA-256) mit "
            "der von der Universität ausgestellten Kopie. Die Datei wird nicht gespeichert. Höchstens %(mb)s MB.",
        ),
        "Fayl verilmiş nüsxə ilə eynidir, lakin sənəd ləğv edilib.": t(
            "The file matches the issued copy, but the document has been revoked.",
            "Файл совпадает с выданной копией, но документ аннулирован.",
            "Dosya düzenlenen nüshayla aynıdır, ancak belge iptal edilmiştir.",
            "Die Datei stimmt mit der ausgestellten Kopie überein, das Dokument wurde jedoch widerrufen.",
        ),
        "Fayl universitetin verdiyi nüsxə ilə tam eynidir.": t(
            "The file is identical to the copy issued by the university.",
            "Файл полностью совпадает с копией, выданной университетом.",
            "Dosya üniversitenin düzenlediği nüshayla birebir aynıdır.",
            "Die Datei ist mit der von der Universität ausgestellten Kopie identisch.",
        ),
        "Fayl verilmiş nüsxə ilə eyni DEYİL — dəyişdirilmiş və ya başqa sənəd ola bilər.": t(
            "The file does NOT match the issued copy — it may have been altered or be a different document.",
            "Файл НЕ совпадает с выданной копией — он мог быть изменён или это другой документ.",
            "Dosya düzenlenen nüshayla aynı DEĞİL — değiştirilmiş veya başka bir belge olabilir.",
            "Die Datei stimmt NICHT mit der ausgestellten Kopie überein — sie wurde möglicherweise verändert oder "
            "ist ein anderes Dokument.",
        ),
        "Seçilən fayl PDF deyil.": t(
            "The selected file is not a PDF.",
            "Выбранный файл не является PDF.",
            "Seçilen dosya PDF değil.",
            "Die gewählte Datei ist keine PDF-Datei.",
        ),
        "Fayl çox böyükdür.": t(
            "The file is too large.", "Файл слишком большой.", "Dosya çok büyük.", "Die Datei ist zu groß."
        ),
        "Fayl seçilməyib.": t("No file selected.", "Файл не выбран.", "Dosya seçilmedi.", "Keine Datei ausgewählt."),
        "PDF fayl": t("PDF file", "PDF-файл", "PDF dosyası", "PDF-Datei"),
        "Müqayisə et": t("Compare", "Сравнить", "Karşılaştır", "Vergleichen"),
        "Başqa kodu yoxla": t(
            "Check another code", "Проверить другой код", "Başka bir kod doğrula", "Anderen Code prüfen"
        ),
        "Sənədin həqiqiliyini yoxlayın": t(
            "Verify a document",
            "Проверьте подлинность документа",
            "Belgenin gerçekliğini doğrulayın",
            "Echtheit prüfen",
        ),
        "Universitetin verdiyi rəsmi sənədin üzərindəki QR kodu skan edin və ya yoxlama kodunu yazın.": t(
            "Scan the QR code on the official document issued by the university or type in its verification code.",
            "Отсканируйте QR-код на официальном документе университета или введите код проверки.",
            "Üniversitenin düzenlediği resmî belgedeki QR kodu tarayın veya doğrulama kodunu yazın.",
            "Scannen Sie den QR-Code auf dem offiziellen Dokument der Universität oder geben Sie den Prüfcode ein.",
        ),
        "Sənəd tapılmadı": t("Document not found", "Документ не найден", "Belge bulunamadı", "Dokument nicht gefunden"),
        "Kodu yenidən yoxlayın. Kod düzgündürsə və sənəd yenə tapılmırsa, ona etibar etməyin və sənədi verən "
        "universitetlə əlaqə saxlayın.": t(
            "Check the code again. If the code is correct and the document is still not found, do not rely on it "
            "and contact the issuing university.",
            "Проверьте код ещё раз. Если код верен, а документ всё равно не найден, не полагайтесь на него и "
            "свяжитесь с выдавшим его университетом.",
            "Kodu tekrar kontrol edin. Kod doğruysa ve belge yine bulunamıyorsa, belgeye güvenmeyin ve belgeyi "
            "düzenleyen üniversiteyle iletişime geçin.",
            "Prüfen Sie den Code erneut. Ist der Code richtig und wird das Dokument trotzdem nicht gefunden, "
            "verlassen Sie sich nicht darauf und wenden Sie sich an die ausstellende Universität.",
        ),
        "Çox sayda sorğu": t("Too many requests", "Слишком много запросов", "Çok fazla istek", "Zu viele Anfragen"),
        "Bir neçə dəqiqə sonra yenidən cəhd edin.": t(
            "Please try again in a few minutes.",
            "Повторите попытку через несколько минут.",
            "Birkaç dakika sonra tekrar deneyin.",
            "Bitte versuchen Sie es in einigen Minuten erneut.",
        ),
        "Yoxla": t("Verify", "Проверить", "Doğrula", "Prüfen"),
        "Yoxlama səhifəsi sənəd sahibinin şəxsi məlumatlarını göstərmir; sorğular anonim qeydə alınır.": t(
            "The verification page does not show the holder's personal data; lookups are logged anonymously.",
            "Страница проверки не показывает личные данные владельца; запросы регистрируются анонимно.",
            "Doğrulama sayfası belge sahibinin kişisel verilerini göstermez; sorgular anonim olarak kaydedilir.",
            "Die Prüfseite zeigt keine personenbezogenen Daten des Inhabers; Abfragen werden anonym protokolliert.",
        ),
    },
    STAFF: {
        "Sənəd yoxlaması": t("Document verification", "Проверка документов", "Belge doğrulama", "Dokumentenprüfung"),
        "Sistemin verdiyi rəsmi sənədlər (QR + kod). Kod üzrə və ya tələbə adı ilə axtarın; səhv verilmiş sənədi "
        "ləğv edin.": t(
            "Official documents issued by the system (QR + code). Search by code or student name; revoke a "
            "document issued in error.",
            "Официальные документы, выданные системой (QR + код). Ищите по коду или имени студента; аннулируйте "
            "ошибочно выданный документ.",
            "Sistemin düzenlediği resmî belgeler (QR + kod). Kod veya öğrenci adıyla arayın; hatalı düzenlenen "
            "belgeyi iptal edin.",
            "Vom System ausgestellte offizielle Dokumente (QR + Code). Suchen Sie nach Code oder Namen; widerrufen "
            "Sie ein fehlerhaft ausgestelltes Dokument.",
        ),
        "Kod və ya tələbə": t("Code or student", "Код или студент", "Kod veya öğrenci", "Code oder Studierende/r"),
        "Kod (QKU-…) və ya tələbənin adı": t(
            "Code (QKU-…) or student name",
            "Код (QKU-…) или имя студента",
            "Kod (QKU-…) veya öğrencinin adı",
            "Code (QKU-…) oder Name der/des Studierenden",
        ),
        "Axtar": t("Search", "Найти", "Ara", "Suchen"),
        "Vəziyyət": t("Status", "Статус", "Durum", "Status"),
        "Publik yoxlama səhifəsi": t(
            "Public verification page", "Публичная страница проверки", "Açık doğrulama sayfası", "Öffentliche Prüfseite"
        ),
        "Kod": t("Code", "Код", "Kod", "Code"),
        "Sənəd": t("Document", "Документ", "Belge", "Dokument"),
        "Sahibi": t("Holder", "Владелец", "Belge sahibi", "Inhaber/in"),
        "Verilib": t("Issued", "Выдан", "Düzenlendi", "Ausgestellt"),
        "Əməllər": t("Actions", "Действия", "İşlemler", "Aktionen"),
        "Ləğv edilib": t("Revoked", "Аннулирован", "İptal edildi", "Widerrufen"),
        "Etibarlı": t("Valid", "Действителен", "Geçerli", "Gültig"),
        "Hamısı": t("All", "Все", "Tümü", "Alle"),
        "Ləğv et": t("Revoke", "Аннулировать", "İptal et", "Widerrufen"),
        "Səhifələr": t("Pages", "Страницы", "Sayfalar", "Seiten"),
        "Əvvəlki": t("Previous", "Предыдущая", "Önceki", "Zurück"),
        "Növbəti": t("Next", "Следующая", "Sonraki", "Weiter"),
        "Səhifə %(page)s / %(pages)s": t(
            "Page %(page)s / %(pages)s",
            "Страница %(page)s / %(pages)s",
            "Sayfa %(page)s / %(pages)s",
            "Seite %(page)s / %(pages)s",
        ),
        "Sənəd tapılmadı": t(
            "No documents found", "Документы не найдены", "Belge bulunamadı", "Keine Dokumente gefunden"
        ),
        "Axtarışı dəyişin və ya bütün sənədlərə qayıdın.": t(
            "Change the search or go back to all documents.",
            "Измените запрос или вернитесь ко всем документам.",
            "Aramayı değiştirin veya tüm belgelere dönün.",
            "Ändern Sie die Suche oder kehren Sie zu allen Dokumenten zurück.",
        ),
        "Möhürlənmiş sənəd transkript yüklənəndə avtomatik yaranır.": t(
            "A sealed document is created automatically when a transcript is downloaded.",
            "Документ с печатью создаётся автоматически при скачивании транскрипта.",
            "Mühürlü belge, transkript indirildiğinde otomatik olarak oluşur.",
            "Ein versiegeltes Dokument entsteht automatisch beim Herunterladen eines Transkripts.",
        ),
        "Sənədi ləğv et": t("Revoke the document", "Аннулировать документ", "Belgeyi iptal et", "Dokument widerrufen"),
        "Ləğv geri qaytarılmır. Səbəb yalnız əməkdaşlara görünür — publik səhifə yalnız ləğv tarixini göstərir.": t(
            "Revocation cannot be undone. The reason is visible to staff only — the public page shows only the "
            "revocation date.",
            "Аннулирование необратимо. Причина видна только сотрудникам — публичная страница показывает лишь дату "
            "аннулирования.",
            "İptal geri alınamaz. Gerekçe yalnızca personele görünür — açık sayfa yalnızca iptal tarihini gösterir.",
            "Der Widerruf kann nicht rückgängig gemacht werden. Der Grund ist nur für Mitarbeitende sichtbar — die "
            "öffentliche Seite zeigt nur das Widerrufsdatum.",
        ),
        "Məs.: səhv məlumatla verilib, yenisi ilə əvəz olunub": t(
            "E.g. issued with wrong data, replaced by a new one",
            "Напр.: выдан с ошибочными данными, заменён новым",
            "Örn.: hatalı bilgiyle düzenlendi, yenisiyle değiştirildi",
            "Z. B.: mit falschen Angaben ausgestellt, durch ein neues ersetzt",
        ),
        "Səbəb ən azı %(n)s simvol olmalıdır.": t(
            "The reason must be at least %(n)s characters long.",
            "Причина должна содержать не менее %(n)s символов.",
            "Gerekçe en az %(n)s karakter olmalıdır.",
            "Der Grund muss mindestens %(n)s Zeichen lang sein.",
        ),
        "Bu sənəd artıq ləğv edilib.": t(
            "This document has already been revoked.",
            "Этот документ уже аннулирован.",
            "Bu belge zaten iptal edildi.",
            "Dieses Dokument wurde bereits widerrufen.",
        ),
        "Sənəd ləğv edildi: %(code)s": t(
            "Document revoked: %(code)s",
            "Документ аннулирован: %(code)s",
            "Belge iptal edildi: %(code)s",
            "Dokument widerrufen: %(code)s",
        ),
    },
    FACT: {
        "İxtisas": t("Programme", "Специальность", "Bölüm", "Studiengang"),
        "Təhsil pilləsi": t("Degree level", "Ступень образования", "Öğrenim düzeyi", "Abschlussstufe"),
        "Toplanmış kredit": t("Credits earned", "Набранные кредиты", "Kazanılan kredi", "Erworbene Credits"),
        "Kumulyativ ÜOMG": t(
            "Cumulative GPA",
            "Совокупный средний балл (GPA)",
            "Kümülatif not ortalaması",
            "Kumulierter Notendurchschnitt",
        ),
        "Məzuniyyət yükü (ECTS)": t(
            "Graduation workload (ECTS)",
            "Нагрузка для выпуска (ECTS)",
            "Mezuniyet yükü (AKTS)",
            "Abschlussumfang (ECTS)",
        ),
        "Sənəd №": t("Document No.", "Документ №", "Belge No.", "Dokument-Nr."),
    },
    DOC: {
        "Akademik transkript": t(
            "Academic transcript", "Академический транскрипт", "Akademik not dökümü", "Akademisches Transkript"
        ),
    },
    AUDIT: {
        "Rəsmi sənəd möhürləndi (QR yoxlama kodu verildi).": t(
            "Official document sealed (QR verification code issued).",
            "Официальный документ заверен (выдан QR-код проверки).",
            "Resmî belge mühürlendi (QR doğrulama kodu verildi).",
            "Offizielles Dokument versiegelt (QR-Prüfcode vergeben).",
        ),
    },
    PDF: {
        "Yoxlama kodu": t("Verification code", "Код проверки", "Doğrulama kodu", "Prüfcode"),
        "Sənədin həqiqiliyini yoxlayın": t(
            "Verify this document",
            "Проверьте подлинность документа",
            "Belgenin gerçekliğini doğrulayın",
            "Echtheit prüfen",
        ),
        "Kod": t("Code", "Код", "Kod", "Code"),
        "Akademik transkript": t(
            "Academic transcript", "Академический транскрипт", "Akademik not dökümü", "Akademisches Transkript"
        ),
    },
    PERM: {
        "Verilmiş rəsmi sənədlərin siyahısı və sənədi ləğv etmək (QR yoxlaması)": t(
            "List of issued official documents and revoking a document (QR verification)",
            "Список выданных официальных документов и аннулирование документа (QR-проверка)",
            "Düzenlenen resmî belgelerin listesi ve belgeyi iptal etme (QR doğrulama)",
            "Liste ausgestellter offizieller Dokumente und Widerruf eines Dokuments (QR-Prüfung)",
        ),
    },
    SIDEBAR: {
        "Sənəd yoxlaması": t("Document verification", "Проверка документов", "Belge doğrulama", "Dokumentenprüfung"),
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)

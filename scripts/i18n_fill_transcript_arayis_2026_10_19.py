#!/usr/bin/env python3
"""i18n — `transcript.issue` + «Təhsil aldığı yer haqqında arayış» (sahib 2026-10-19).

Yeni açar «Transkript və arayış vermək», arayış PDF-inin mətni (``registrar.arayis``), publik yoxlama faktları
(kurs, təhsil forması, status), «Tələbə reyestri» dialoqu, «Müraciətlər»-də «Arayışı hazırla» bloku.

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`. ⚠️ `makemessages` İŞLƏDİLMİR.
Qeyd: arayış PDF-i həmişə Azərbaycan dilində qurulur (dövlət dilində rəsmi blank); ``registrar.arayis``
tərcümələri kataloqun tamlığı üçündür.
İstifadə:  python scripts/i18n_fill_transcript_arayis_2026_10_19.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ARAYIS = "registrar.arayis"
DOCS = "registrar.documents"
FACT = "verification.fact"
DOC = "verification.doc_type"
PERM = "organizations.permission.label"
ROLES = "organizations.roles_registry"
REG = "accounts.student_registry"
APP = "applications.arayis"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


CERT = t(
    "Certificate of enrolment",
    "Справка с места учёбы",
    "Öğrenci belgesi",
    "Immatrikulationsbescheinigung",
)

ENTRIES = {
    ARAYIS: {
        "qeyd deaktivdir": t("record is inactive", "запись деактивирована", "kayıt devre dışı", "Eintrag ist inaktiv"),
        "Arayış yalnız təhsil alan (aktiv) tələbəyə verilir — tələbənin statusu: «%(status)s».": t(
            "A certificate is issued only to a currently enrolled (active) student — the student's status: "
            "«%(status)s».",
            "Справка выдаётся только обучающемуся (активному) студенту — статус студента: «%(status)s».",
            "Belge yalnızca öğrenimine devam eden (aktif) öğrenciye verilir — öğrencinin durumu: «%(status)s».",
            "Die Bescheinigung wird nur an eingeschriebene (aktive) Studierende ausgestellt — Status: «%(status)s».",
        ),
        "Tələbənin hesabı arxivdədir (məzun və ya xaric) — arayış verilmir.": t(
            "The student's account is archived (graduated or expelled) — no certificate is issued.",
            "Учётная запись студента в архиве (выпускник или отчислен) — справка не выдаётся.",
            "Öğrencinin hesabı arşivde (mezun veya kaydı silinmiş) — belge verilmez.",
            "Das Konto ist archiviert (Absolvent/in oder exmatrikuliert) — keine Bescheinigung.",
        ),
        "Tələbənin qəbul ili məlum deyil — əvvəlcə akademik qeydi düzəldin.": t(
            "The student's admission year is unknown — correct the academic record first.",
            "Год поступления студента неизвестен — сначала исправьте академическую запись.",
            "Öğrencinin kayıt yılı bilinmiyor — önce akademik kaydı düzeltin.",
            "Das Aufnahmejahr ist unbekannt — korrigieren Sie zuerst den Studiendatensatz.",
        ),
        "Tələbənin oxu müddəti bitib — əvvəlcə statusunu rəsmiləşdirin (məzun, xaric və ya bərpa).": t(
            "The student's period of study has ended — formalise the status first (graduated, expelled or "
            "reinstated).",
            "Срок обучения студента истёк — сначала оформите статус (выпускник, отчислен или восстановлен).",
            "Öğrencinin öğrenim süresi doldu — önce durumunu resmîleştirin (mezun, kaydı silinmiş veya yeniden "
            "kayıt).",
            "Die Regelstudienzeit ist abgelaufen — klären Sie zuerst den Status (Abschluss, Exmatrikulation oder "
            "Wiederaufnahme).",
        ),
        "bakalavriat": t("bachelor's", "бакалавриата", "lisans", "Bachelor"),
        "magistratura": t("master's", "магистратуры", "yüksek lisans", "Master"),
        "doktorantura": t("doctoral", "докторантуры", "doktora", "Promotion"),
        "ali təhsil": t("higher education", "высшего образования", "yükseköğretim", "Hochschulbildung"),
        "fakültəsinin": t("faculty", "факультета", "fakültesinin", "Fakultät"),
        "ixtisası (şifr %(code)s)": t(
            "programme (code %(code)s)",
            "специальности (шифр %(code)s)",
            "bölümü (kod %(code)s)",
            "Studiengang (Kennziffer %(code)s)",
        ),
        "ixtisası": t("programme", "специальности", "bölümü", "Studiengang"),
        "%(group)s qrup ": t("group %(group)s ", "группы %(group)s ", "%(group)s grubu ", "Gruppe %(group)s "),
        "Bu arayış ona verilir ki, %(name)s həqiqətən %(where)s %(program)s üzrə %(degree)s təhsil pilləsinin "
        "%(course)s kurs, %(group)stələbəsidir.": t(
            "This is to certify that %(name)s is indeed a year %(course)s %(group)sstudent of the %(degree)s level "
            "of %(where)s, %(program)s.",
            "Настоящая справка выдана в том, что %(name)s действительно является студентом %(course)s курса, "
            "%(group)s%(degree)s, %(where)s, %(program)s.",
            "Bu belge, %(name)s adlı kişinin %(where)s %(program)s %(degree)s düzeyinde %(course)s. sınıf, "
            "%(group)söğrencisi olduğunu belgelemek için verilmiştir.",
            "Hiermit wird bescheinigt, dass %(name)s im %(course)s. Studienjahr, %(group)s, %(degree)s, %(where)s, "
            "%(program)s eingeschrieben ist.",
        ),
        "Təhsil forması: %(form)s.": t(
            "Mode of study: %(form)s.",
            "Форма обучения: %(form)s.",
            "Öğrenim şekli: %(form)s.",
            "Studienform: %(form)s.",
        ),
        "Qəbul ili: %(year)s.": t(
            "Year of admission: %(year)s.",
            "Год поступления: %(year)s.",
            "Kayıt yılı: %(year)s.",
            "Aufnahmejahr: %(year)s.",
        ),
        "Arayış %(place)s təqdim edilmək üçün verilir.": t(
            "This certificate is issued for submission to %(place)s.",
            "Справка выдана для предъявления в %(place)s.",
            "Bu belge %(place)s sunulmak üzere verilmiştir.",
            "Diese Bescheinigung wird zur Vorlage bei %(place)s ausgestellt.",
        ),
        "Arayış tələb olunan yerə təqdim edilmək üçün verilir.": t(
            "This certificate is issued for submission where required.",
            "Справка выдана для предъявления по месту требования.",
            "Bu belge ilgili makama sunulmak üzere verilmiştir.",
            "Diese Bescheinigung wird zur Vorlage bei der anfordernden Stelle ausgestellt.",
        ),
        "Aktiv tələbə": t("Active student", "Действующий студент", "Aktif öğrenci", "Eingeschriebene/r Studierende/r"),
        "Azərbaycan Respublikası Təhsil Nazirliyi": t(
            "Ministry of Education of the Republic of Azerbaijan",
            "Министерство образования Азербайджанской Республики",
            "Azerbaycan Cumhuriyeti Eğitim Bakanlığı",
            "Bildungsministerium der Republik Aserbaidschan",
        ),
        "Arayış № %(number)s": t(
            "Certificate No. %(number)s",
            "Справка № %(number)s",
            "Belge No. %(number)s",
            "Bescheinigung Nr. %(number)s",
        ),
        "Arayış №": t("Certificate No.", "Справка №", "Belge No.", "Bescheinigung Nr."),
        "Tarix: %(date)s": t("Date: %(date)s", "Дата: %(date)s", "Tarih: %(date)s", "Datum: %(date)s"),
        "Arayış": t("Certificate", "Справка", "Belge", "Bescheinigung"),
        "(imza)": t("(signature)", "(подпись)", "(imza)", "(Unterschrift)"),
        "Fakültə dekanı": t("Dean of the faculty", "Декан факультета", "Fakülte dekanı", "Dekan/in der Fakultät"),
        "Tədris şöbəsinin müdiri / Tələbə Xidmətləri": t(
            "Head of the Academic Affairs Office / Student Services",
            "Начальник учебного отдела / Служба по работе со студентами",
            "Öğrenci İşleri Daire Başkanı / Öğrenci Hizmetleri",
            "Leitung des Studienbüros / Studierendenservice",
        ),
        "M.Y.": t("Place of seal", "М.П.", "Mühür yeri", "Siegel"),
    },
    DOCS: {
        "«Başqasının adından» rejimində rəsmi sənəd verilmir — sənəd möhür yazır. Öz hesabınıza qayıdın.": t(
            "Official documents cannot be issued in «view as» mode — issuing writes a seal. Return to your own "
            "account.",
            "В режиме «от имени другого» официальные документы не выдаются — выдача создаёт печать. Вернитесь в "
            "свою учётную запись.",
            "«Başkası adına» modunda resmî belge verilmez — belge mühür kaydı oluşturur. Kendi hesabınıza dönün.",
            "Im Modus «Ansicht als» werden keine offiziellen Dokumente ausgestellt — die Ausstellung schreibt ein "
            "Siegel. Kehren Sie zu Ihrem eigenen Konto zurück.",
        ),
    },
    DOC: {"Təhsil aldığı yer haqqında arayış": CERT},
    FACT: {
        "Kurs": t("Year of study", "Курс", "Sınıf", "Studienjahr"),
        "Təhsil forması": t("Mode of study", "Форма обучения", "Öğrenim şekli", "Studienform"),
        "Tələbənin statusu": t("Student status", "Статус студента", "Öğrenci durumu", "Status der/des Studierenden"),
    },
    PERM: {
        "Transkript və arayış vermək": t(
            "Issue transcripts and certificates",
            "Выдача транскриптов и справок",
            "Transkript ve belge düzenleme",
            "Transkripte und Bescheinigungen ausstellen",
        ),
    },
    ROLES: {
        "Rəsmi sənədlər": t("Official documents", "Официальные документы", "Resmî belgeler", "Offizielle Dokumente"),
    },
    REG: {
        "Arayış ver": t("Issue certificate", "Выдать справку", "Belge ver", "Bescheinigung ausstellen"),
        "Təhsil aldığı yer haqqında arayış": CERT,
        "Arayış hazırlanmadı. Bir az sonra yenidən cəhd edin.": t(
            "The certificate could not be prepared. Please try again shortly.",
            "Не удалось подготовить справку. Повторите попытку чуть позже.",
            "Belge hazırlanamadı. Biraz sonra yeniden deneyin.",
            "Die Bescheinigung konnte nicht erstellt werden. Bitte versuchen Sie es gleich noch einmal.",
        ),
        "Arayış hazırlandı və yükləndi.": t(
            "The certificate has been prepared and downloaded.",
            "Справка подготовлена и загружена.",
            "Belge hazırlandı ve indirildi.",
            "Die Bescheinigung wurde erstellt und heruntergeladen.",
        ),
        "Təqdim ediləcəyi yer": t("To be submitted to", "Место предъявления", "Sunulacağı yer", "Vorzulegen bei"),
        "məs.: Səbail rayon hərbi komissarlığına": t(
            "e.g.: Sabail district military commissariat",
            "напр.: в военный комиссариат Сабаильского района",
            "örn.: Sabail ilçe askerlik şubesine",
            "z. B.: Militärkommissariat des Bezirks Sabail",
        ),
        "İstəyə bağlıdır. Yönlük halda yazın («… komissarlığına», «… bankına»); boş qalsa arayışda «tələb olunan "
        "yerə» yazılır.": t(
            "Optional. Write it in the Azerbaijani dative case («… komissarlığına», «… bankına»); if left empty, "
            "the certificate says «where required».",
            "Необязательно. Пишите в направительном падеже азербайджанского языка («… komissarlığına», "
            "«… bankına»); если пусто, в справке будет «по месту требования».",
            "İsteğe bağlı. Azerbaycanca yönelme hâlinde yazın («… komissarlığına», «… bankına»); boş bırakılırsa "
            "belgede «ilgili makama» yazılır.",
            "Optional. Im aserbaidschanischen Dativ schreiben («… komissarlığına», «… bankına»); leer bleibt "
            "«bei der anfordernden Stelle».",
        ),
        "Arayış yalnız aktiv tələbəyə verilir. Sənəd QR və yoxlama kodu ilə möhürlənir; verilmə «Sənəd yoxlaması» "
        "siyahısına düşür.": t(
            "Certificates are issued only to active students. The document is sealed with a QR and verification "
            "code; the issue appears in the «Document verification» list.",
            "Справка выдаётся только действующим студентам. Документ заверяется QR-кодом и кодом проверки; выдача "
            "попадает в список «Проверка документов».",
            "Belge yalnızca aktif öğrenciye verilir. Belge QR ve doğrulama kodu ile mühürlenir; düzenleme «Belge "
            "doğrulama» listesine düşer.",
            "Bescheinigungen erhalten nur aktive Studierende. Das Dokument wird mit QR- und Prüfcode versiegelt; "
            "die Ausstellung erscheint in der Liste «Dokumentenprüfung».",
        ),
        "Arayışı hazırla": t(
            "Prepare certificate", "Подготовить справку", "Belgeyi hazırla", "Bescheinigung erstellen"
        ),
    },
    APP: {
        "Təhsil aldığı yer haqqında arayış": CERT,
        "Arayış QR və yoxlama kodu ilə möhürlənir və müraciətə açıq qeyd kimi əlavə olunur — sahib onu "
        "müraciətdən endirir. «Təqdim ediləcəyi yer» istəyə bağlıdır (yönlük halda: «… bankına»).": t(
            "The certificate is sealed with a QR and verification code and attached to the request as a public "
            "note — the requester downloads it from the request. «To be submitted to» is optional (dative case: "
            "«… bankına»).",
            "Справка заверяется QR-кодом и кодом проверки и прикрепляется к обращению открытой заметкой — "
            "заявитель скачивает её из обращения. «Место предъявления» необязательно (направительный падеж: "
            "«… bankına»).",
            "Belge QR ve doğrulama kodu ile mühürlenir ve başvuruya açık not olarak eklenir — başvuru sahibi onu "
            "başvurudan indirir. «Sunulacağı yer» isteğe bağlıdır (yönelme hâli: «… bankına»).",
            "Die Bescheinigung wird mit QR- und Prüfcode versiegelt und dem Antrag als öffentliche Notiz "
            "angehängt — die antragstellende Person lädt sie dort herunter. «Vorzulegen bei» ist optional "
            "(Dativ: «… bankına»).",
        ),
        "Təqdim ediləcəyi yer": t("To be submitted to", "Место предъявления", "Sunulacağı yer", "Vorzulegen bei"),
        "məs.: Səbail rayon hərbi komissarlığına": t(
            "e.g.: Sabail district military commissariat",
            "напр.: в военный комиссариат Сабаильского района",
            "örn.: Sabail ilçe askerlik şubesine",
            "z. B.: Militärkommissariat des Bezirks Sabail",
        ),
        "Arayışı hazırla və əlavə et": t(
            "Prepare and attach the certificate",
            "Подготовить и прикрепить справку",
            "Belgeyi hazırla ve ekle",
            "Bescheinigung erstellen und anhängen",
        ),
        "«Başqasının adından» rejimində rəsmi sənəd verilmir — öz hesabınıza qayıdın.": t(
            "Official documents cannot be issued in «view as» mode — return to your own account.",
            "В режиме «от имени другого» официальные документы не выдаются — вернитесь в свою учётную запись.",
            "«Başkası adına» modunda resmî belge verilmez — kendi hesabınıza dönün.",
            "Im Modus «Ansicht als» werden keine offiziellen Dokumente ausgestellt — kehren Sie zu Ihrem Konto zurück.",
        ),
        "Arayış əlavə olunub": t(
            "Certificate attached",
            "Справка прикреплена",
            "Belge eklendi",
            "Bescheinigung angehängt",
        ),
        "Arayışı aç": t("Open certificate", "Открыть справку", "Belgeyi aç", "Bescheinigung öffnen"),
        "tələb olunan yerə": t("where required", "по месту требования", "ilgili makama", "bei der anfordernden Stelle"),
        "Kod": t("Code", "Код", "Kod", "Code"),
        "Yeni arayış hazırla (başqa yer üçün)": t(
            "Prepare a new certificate (for another place)",
            "Подготовить новую справку (для другого места)",
            "Yeni belge hazırla (başka bir yer için)",
            "Neue Bescheinigung erstellen (für eine andere Stelle)",
        ),
        "Eyni yer üçün yenidən hazırlasanız, artıq əlavə olunmuş arayış qaytarılır — ikinci fayl yaranmır.": t(
            "If you prepare it again for the same place, the already attached certificate is returned — no second "
            "file is created.",
            "Если подготовить справку повторно для того же места, вернётся уже прикреплённая — второй файл не "
            "создаётся.",
            "Aynı yer için yeniden hazırlarsanız, zaten eklenmiş belge döndürülür — ikinci dosya oluşmaz.",
            "Wenn Sie sie für dieselbe Stelle erneut erstellen, wird die bereits angehängte Bescheinigung "
            "zurückgegeben — es entsteht keine zweite Datei.",
        ),
        "Bu müraciətə arayış hazırlamaq mümkün deyil.": t(
            "A certificate cannot be prepared for this request.",
            "Для этого обращения нельзя подготовить справку.",
            "Bu başvuru için belge hazırlanamaz.",
            "Für diesen Antrag kann keine Bescheinigung erstellt werden.",
        ),
        "Təhsil aldığı yer haqqında arayış hazırlandı və əlavə olundu. Yoxlama kodu: %(code)s.": t(
            "The certificate of enrolment has been prepared and attached. Verification code: %(code)s.",
            "Справка с места учёбы подготовлена и прикреплена. Код проверки: %(code)s.",
            "Öğrenci belgesi hazırlandı ve eklendi. Doğrulama kodu: %(code)s.",
            "Die Immatrikulationsbescheinigung wurde erstellt und angehängt. Prüfcode: %(code)s.",
        ),
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

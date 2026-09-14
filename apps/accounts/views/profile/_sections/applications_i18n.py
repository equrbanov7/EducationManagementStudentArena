"""«Müraciətlərim» panelinin JS mətn kataloqu.

Xarici `.js` faylı Django template engine-dən KEÇMİR — orada `{% trans %}`
işləmir. Ona görə JS-in yazdığı bütün mətnlər burada `pgettext` ilə tərcümə
olunur və şablonda `json_script` ilə DOM-a verilir (CLAUDE.md «dinamik dəyər»
qaydası). Yer tutucular `{ad}` formatındadır — JS sadə əvəzləmə edir.

Ayrı modul saxlanılır ki, `applications.py` bölmə qurucusu kiçik qalsın.
"""

from django.utils.translation import pgettext

_CTX = "applications"


def _rows() -> dict:
    return {
        "rowOverdue": pgettext(_CTX, "cavab müddəti keçir"),
        "rowSla": pgettext(_CTX, "{n} iş günü müddət"),
        "rowClosed": pgettext(_CTX, "bağlanıb"),
        "more": pgettext(_CTX, "Daha çox"),
        "loading": pgettext(_CTX, "Yüklənir…"),
        "kindAll": pgettext(_CTX, "Bütün növlər"),
        "days": pgettext(_CTX, "{n} iş günü"),
        "emptyWatchingTitle": pgettext(_CTX, "İzlədiyiniz müraciət yoxdur"),
        "emptyWatchingNote": pgettext(_CTX, "Başqa şöbəyə yönləndirdiyiniz müraciətlər burada görünəcək."),
        "emptyOverdueTitle": pgettext(_CTX, "Müddəti keçən müraciət yoxdur"),
        "emptyTitle": pgettext(_CTX, "Müraciət tapılmadı"),
        "emptySenderNote": pgettext(
            _CTX, "Hələ müraciət göndərməmisiniz. «Yeni müraciət» düyməsi ilə başlaya bilərsiniz."
        ),
        "emptyHandlerNote": pgettext(_CTX, "Bu filtrə uyğun müraciət yoxdur — filtri dəyişin."),
    }


def _detail() -> dict:
    return {
        "secBody": pgettext(_CTX, "Müraciətin mətni"),
        "secFiles": pgettext(_CTX, "Əlavə olunan sənədlər"),
        "secTimeline": pgettext(_CTX, "Müraciətin gedişi"),
        "replyLabel": pgettext(_CTX, "Cavab ver"),
        "replyPlaceholder": pgettext(_CTX, "Müraciət sahibinin görəcəyi cavab"),
        # Hədd MƏTNƏ bişirilmir: `{n}` server qaydasından (`rules.min_note_length`) doldurulur.
        "replyHint": pgettext(_CTX, "Cavab mətni ən azı {n} simvol olmalıdır — müraciət sahibi məhz bu mətni görəcək."),
        "internal": pgettext(_CTX, "daxili qeyd"),
        "closeDetail": pgettext(_CTX, "Bağla"),
        # ── Modal (yazışma + cavab qutusu) ───────────────────────────────
        "msgLatest": pgettext(_CTX, "ən son"),
        "attachLabel": pgettext(_CTX, "Sənəd əlavə et"),
        "attachHint": pgettext(_CTX, "PDF, şəkil, DOCX və ya ZIP · maks. {mb} MB · ən çox {n} fayl"),
        "filesNotAllowed": pgettext(
            _CTX, "«{action}» əməli sənəd qəbul etmir — faylları silin və ya başqa əməl seçin."
        ),
        "closeDirtyTitle": pgettext(_CTX, "Cavab göndərilməyib"),
        "closeDirtyText": pgettext(
            _CTX,
            "Yazdığınız mətn və seçdiyiniz sənədlər hələ göndərilməyib — pəncərəni bağlasanız itəcək. " "Bağlayaq?",
        ),
        "slaOntime": pgettext(_CTX, "Cavab müddətinə {n} iş günü qalıb (norma {m} iş günü)"),
        "slaOverdue": pgettext(_CTX, "Cavab müddəti {n} gün keçib (norma {m} iş günü)"),
        "slaClosed": pgettext(_CTX, "Müraciət bağlanıb — {status}"),
        "noteSenderOpen": pgettext(
            _CTX,
            "Müraciətiniz hazırda {unit}-dədir. Cavab veriləndə bildiriş gələcək və mətn burada görünəcək.",
        ),
        "noteSenderResolved": pgettext(
            _CTX,
            "Cavab gəldi. Razısınızsa təsdiqləyib bağlayın; problem həll olunmayıbsa səbəbini yazın — "
            "müraciət eyni nömrə ilə həmin şöbəyə qayıdacaq.",
        ),
        "noteSenderClosed": pgettext(
            _CTX, "Müraciət bağlanıb. Razı deyilsinizsə, eyni mövzuda yeni müraciət göndərə bilərsiniz."
        ),
        "noteHandlerClosed": pgettext(_CTX, "Müraciət bağlanıb — yalnız oxuna bilər."),
        "noteHandlerWatching": pgettext(
            _CTX,
            "Müraciət hazırda {unit}-dədir. Siz yönləndirdiyiniz üçün gedişini izləyirsiniz, "
            "amma cavabı həmin şöbə verəcək.",
        ),
    }


def _actions() -> dict:
    return {
        "actResolve": pgettext(_CTX, "Həll olundu — bağla"),
        "actRequestInfo": pgettext(_CTX, "Əlavə məlumat istə"),
        "actForward": pgettext(_CTX, "Başqa şöbəyə yönləndir"),
        "actReject": pgettext(_CTX, "Rədd et"),
        "actReturn": pgettext(_CTX, "Düzəliş üçün qaytar"),
        "actAssign": pgettext(_CTX, "Təyin et"),
        "actComment": pgettext(_CTX, "Qeyd əlavə et"),
        "actClose": pgettext(_CTX, "Təsdiqləyirəm — bağla"),
        "actCancel": pgettext(_CTX, "Müraciəti ləğv et"),
        "actProvideInfo": pgettext(_CTX, "Əlavə məlumat göndər"),
        "actReopen": pgettext(_CTX, "Razı deyiləm — yenidən bax"),
        "actResubmit": pgettext(_CTX, "Düzəlişdən sonra yenidən göndər"),
    }


def _dialogs() -> dict:
    return {
        "dlgReturnTitle": pgettext(_CTX, "Düzəliş üçün qaytar"),
        "dlgReturnLabel": pgettext(_CTX, "Nə düzəldilməlidir?"),
        "dlgCancelTitle": pgettext(_CTX, "Müraciəti ləğv et"),
        "dlgCancelLabel": pgettext(_CTX, "Ləğv səbəbi"),
        "dlgProvideTitle": pgettext(_CTX, "Əlavə məlumat göndər"),
        "dlgProvideLabel": pgettext(_CTX, "İstənilən məlumat"),
        "dlgReopenTitle": pgettext(_CTX, "Razı deyiləm — yenidən baxılsın"),
        "dlgReopenLabel": pgettext(_CTX, "Nə həll olunmadı?"),
        "dlgResubmitTitle": pgettext(_CTX, "Düzəlişdən sonra yenidən göndər"),
        "dlgSend": pgettext(_CTX, "Göndər"),
        "confirmCloseTitle": pgettext(_CTX, "Müraciəti bağlayaq?"),
        "confirmCloseText": pgettext(_CTX, "Cavabı təsdiqləyirsiniz və müraciət bağlanır. Bu əməl geri qaytarılmır."),
        "counterShort": pgettext(_CTX, "Ən azı {min} simvol — hazırda {n}"),
        "counterOk": pgettext(_CTX, "{n} simvol"),
        "routeEmpty": pgettext(_CTX, "Növü seçəndə müraciətin hansı şöbəyə gedəcəyi burada görünəcək."),
        # Kataloq boş olanda (növ seeed edilməyib / rol üçün icazəli növ yoxdur)
        # dialoq əvvəl SƏSSİZCƏ boş qalırdı — istifadəçi «sahə itdi» görürdü.
        "kindsEmpty": pgettext(
            _CTX,
            "Sizin üçün açıq müraciət növü yoxdur. Müraciət kataloqu bu təşkilatda hələ "
            "doldurulmayıb — administratordan «seed_application_catalog» əmrini icra etməyi xahiş edin.",
        ),
        "noAssignee": pgettext(_CTX, "Bu şöbədə təyin ediləcək istifadəçi tapılmadı."),
        # Hədlər/uzantılar SERVER-dən gəlir (`rules_payload`) — mətnə bişirilmir.
        "fileTooBig": pgettext(_CTX, "«{name}» {mb} MB-dan böyükdür."),
        "fileBadType": pgettext(_CTX, "«{name}» dəstəklənmir — icazəli formatlar: {list}."),
        "tooManyFiles": pgettext(_CTX, "Bir əməldə ən çoxu {n} fayl əlavə edilə bilər."),
    }


def _toasts() -> dict:
    return {
        "toastCreated": pgettext(_CTX, "Müraciət {unit}-nə göndərildi — gedişini buradan izləyə bilərsiniz."),
        "toastForwarded": pgettext(_CTX, "{no} — {unit}-nə yönləndirildi · izləməkdə davam edirsiniz."),
        "toastForwardedOnly": pgettext(_CTX, "{no} — {unit}-nə yönləndirildi."),
        "toastDone": pgettext(_CTX, "{no} — {status}. Müraciət sahibinə bildiriş göndərildi."),
        "toastSaved": pgettext(_CTX, "{no} — yeniləndi."),
        "error": pgettext(_CTX, "Əməliyyat yerinə yetirilmədi."),
        "loadError": pgettext(_CTX, "Siyahı yüklənmədi, yenidən cəhd edin."),
    }


def build_applications_i18n() -> dict:
    """JS-in oxuduğu bütün mətnlər (şablonda ``json_script`` ilə verilir)."""
    catalog = {}
    for part in (_rows(), _detail(), _actions(), _dialogs(), _toasts()):
        catalog.update(part)
    return catalog


__all__ = ["build_applications_i18n"]

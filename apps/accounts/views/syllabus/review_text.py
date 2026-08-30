"""Təsdiq ekranının MƏTN qatı — etiketlər, izahlar, boş vəziyyət.

Mətn view məntiqindən ayrı saxlanılır: ``review.py`` yalnız hansı kartın hansı
tonla göründüyünü qərar verir, sözləri isə buradan götürür. Beləliklə həm modul
ölçüsü (SOFT_CAP=600) altında qalır, həm də tərcümə axtarışı bir fayla düşür.

⚠️ Rəng burada YOXDUR — yalnız «ton» adları (``success``/``warning``/…), CSS
onları ``static/css/design-tokens.css`` tokenlərinə bağlayır.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "accounts.syllabus"

#: Qərar səbəbinin minimum uzunluğu (dizayn §3.3 dialoqu: «Ən azı 20 simvol»).
#: Burada saxlanılır ki, HƏM server yoxlaması (`review_api`), HƏM də dialoqun
#: mətni EYNİ rəqəmi göstərsin — ikisi bir-birindən sürüşə bilməsin.
MIN_DECISION_REASON = 20

ACCESS_DENIED = pgettext_lazy(_CTX, "Sillabus təsdiqi bölməsi üçün icazəniz yoxdur.")

#: `noscope` boş vəziyyəti (README §3.3) — «əhatə yoxdur» ≠ «bütün universitet».
NOSCOPE = {
    "title": pgettext_lazy(_CTX, "Təşkilati əhatə təyin edilməmişdir"),
    "body": pgettext_lazy(
        _CTX,
        "Hesabınıza kafedra və ya fakültə əhatəsi verilməyib. Əhatə olmadan sillabus məlumatları göstərilmir — "
        "bu, «bütün universitet» kimi şərh edilmir. Səlahiyyət təyin edildikdən sonra yalnız aid olduğunuz "
        "struktur bölmə görünəcək.",
    ),
    "hint": pgettext_lazy(_CTX, "Əhatənin təyini üçün təşkilat administratoruna və ya tədris şöbəsinə müraciət edin."),
}

#: `scope_mode` → (panel adı, rol çipi).
IDENTITY = {
    "chair": (pgettext_lazy(_CTX, "Kafedra müdiri paneli"), pgettext_lazy(_CTX, "Kafedra müdiri")),
    "wide": (pgettext_lazy(_CTX, "Təsdiq paneli"), pgettext_lazy(_CTX, "Genişləndirilmiş əhatə")),
    "noscope": (pgettext_lazy(_CTX, "Təsdiq paneli"), pgettext_lazy(_CTX, "Əhatə yoxdur")),
}

INTRO = {
    "chair": pgettext_lazy(
        _CTX,
        "Yalnız öz kafedranızın müəllimlərinin təqdim etdiyi sillabuslar görünür. Təsdiqlənmiş versiya "
        "dəyişdirilmir — düzəliş yeni versiya ilə aparılır.",
    ),
    "wide": pgettext_lazy(
        _CTX,
        "Əhatənizdəki bütün kafedralar üzrə sillabus vəziyyəti. Təsdiqlənmiş versiya dəyişdirilmir — düzəliş "
        "yeni versiya ilə aparılır.",
    ),
    "noscope": pgettext_lazy(_CTX, "Əhatə təyin edilməyib."),
}

#: Növbə KPI kartları: (etiket, qeyd, dəyər şəkilçisi).
KPI_LABELS = {
    "queued": (
        pgettext_lazy(_CTX, "Növbədə gözləyən"),
        pgettext_lazy(_CTX, "baxış tələb edən sillabus"),
        "",
    ),
    "late": (
        pgettext_lazy(_CTX, "10 gündən çox gözləyir"),
        pgettext_lazy(_CTX, "gözləmə həddi aşılıb"),
        "",
    ),
    "incomplete": (
        pgettext_lazy(_CTX, "Çatışmayan bölməsi var"),
        pgettext_lazy(_CTX, "tam doldurulmayıb"),
        "",
    ),
    "average": (
        pgettext_lazy(_CTX, "Orta gözləmə"),
        pgettext_lazy(_CTX, "hədəf: 5 gündən az"),
        pgettext_lazy(_CTX, "gün"),
    ),
}

#: Coverage KPI kartları: (etiket, qeyd).
COVERAGE_KPI_LABELS = {
    "percent": (pgettext_lazy(_CTX, "Təsdiq faizi"), pgettext_lazy(_CTX, "təsdiqlənmiş / ümumi fənn")),
    "approved": (pgettext_lazy(_CTX, "Təsdiqlənmiş"), pgettext_lazy(_CTX, "jurnal açıla bilər")),
    "in_review": (pgettext_lazy(_CTX, "Baxışda"), pgettext_lazy(_CTX, "təsdiq gözləyir")),
    "revision": (pgettext_lazy(_CTX, "Düzəlişdə"), pgettext_lazy(_CTX, "müəllimdədir")),
    "late": (pgettext_lazy(_CTX, "Gecikib"), pgettext_lazy(_CTX, "semestr başlayıb, təsdiq yoxdur")),
}

QUEUE_SORT_LABELS = {
    "wait": pgettext_lazy(_CTX, "Gözləmə müddətinə görə"),
    "subject": pgettext_lazy(_CTX, "Fənn adına görə"),
    "completion": pgettext_lazy(_CTX, "Tamamlanmaya görə"),
}

#: Əhatə çipi — kafedra rejimində kafedranın ADI, geniş rejimdə say göstərilir.
SCOPE_COUNT = pgettext_lazy(_CTX, "Əhatə: %(count)s struktur bölmə")

STATUS_FILTER_ALL = pgettext_lazy(_CTX, "Bütün statuslar")
UNIT_FILTER_ALL = pgettext_lazy(_CTX, "Hamısı")
YEAR_FILTER_ALL = pgettext_lazy(_CTX, "Bütün illər")

UNIT_FILTER_LABELS = {
    "chair": pgettext_lazy(_CTX, "Təhsil proqramı"),
    "wide": pgettext_lazy(_CTX, "Kafedra"),
    "noscope": pgettext_lazy(_CTX, "Kafedra"),
}

_COVERAGE_TITLES = {
    "chair": (
        pgettext_lazy(_CTX, "Təhsil proqramı"),
        pgettext_lazy(_CTX, "Kafedra üzrə breakdown — təhsil proqramları"),
        pgettext_lazy(_CTX, "Yalnız sizin əhatənizdəki fənlər"),
    ),
    "wide": (
        pgettext_lazy(_CTX, "Kafedra"),
        pgettext_lazy(_CTX, "Əhatə üzrə breakdown — kafedralar"),
        pgettext_lazy(_CTX, "Əhatənizə düşən bütün struktur bölmələr"),
    ),
}


def coverage_titles(scope_mode: str) -> dict:
    """Breakdown cədvəlinin başlıq dəsti (`chair` / `wide`)."""
    column, title, subtitle = _COVERAGE_TITLES.get(scope_mode, _COVERAGE_TITLES["chair"])
    return {"col": column, "title": title, "subtitle": subtitle}


#: «Təsdiq marşrutu» kartı — universitet siyasətinin CARİ vəziyyəti.
#: ⚠️ Bu, konfiqurasiya EKRANI DEYİL: ikinci təsdiq (dekan) və tədris şöbəsinin
#: yekun yoxlaması hələ tətbiq olunmayıb, ona görə «aktiv» kimi göstərilmir —
#: uydurma parametr çipi yazmırıq. Parametr real olanda bu siyahı servisdən
#: gələcək.
POLICY_ROWS = (
    {
        "key": "chair",
        "label": pgettext_lazy(_CTX, "Kafedra müdiri təsdiqi"),
        "note": pgettext_lazy(_CTX, "Bütün sillabuslar üçün məcburidir — state maşını ilə tətbiq olunur."),
        "state": pgettext_lazy(_CTX, "aktiv"),
        "on": True,
    },
    {
        "key": "dean",
        "label": pgettext_lazy(_CTX, "İkinci təsdiq — dekan"),
        "note": pgettext_lazy(_CTX, "Universitet siyasətindən asılı ikinci mərhələ — hələ tətbiq olunmayıb."),
        "state": pgettext_lazy(_CTX, "tətbiq olunmur"),
        "on": False,
    },
    {
        "key": "registry",
        "label": pgettext_lazy(_CTX, "Tədris şöbəsinin son yoxlaması"),
        "note": pgettext_lazy(_CTX, "Semestr açılışından əvvəl toplu yoxlama — hələ tətbiq olunmayıb."),
        "state": pgettext_lazy(_CTX, "tətbiq olunmur"),
        "on": False,
    },
)

#: Qərar dialoqları (dizayn §3.3) — səbəb MƏCBURİ olan ikisi ayrıca işarələnir.
DECISION_DIALOGS = {
    "approve": {
        "title": pgettext_lazy(_CTX, "Sillabus təsdiqlənsin?"),
        "body": pgettext_lazy(
            _CTX,
            "Versiya təsdiqlənəcək və dəyişdirilməz sənəd kimi kilidlənəcək. Sonrakı düzəliş yalnız yeni "
            "versiya ilə mümkündür.",
        ),
        "ok": pgettext_lazy(_CTX, "Təsdiqlə"),
        "tone": "success",
        "reason_required": False,
        "lines": (
            pgettext_lazy(
                _CTX,
                "Təsdiqlənmiş versiya həftəlik mövzuların, qiymətləndirmə strukturunun və sərbəst iş "
                "konfiqurasiyasının yeganə mənbəyi olur",
            ),
            pgettext_lazy(_CTX, "Elektron jurnal bu versiyadan yaradılır və müəllim üçün açılır"),
            pgettext_lazy(_CTX, "Tələbə kabinetində sillabus dərhal görünür"),
            pgettext_lazy(_CTX, "Mövcud qiymət və davamiyyət qeydləri toxunulmaz qalır"),
        ),
    },
    "revise": {
        "title": pgettext_lazy(_CTX, "Düzəliş üçün geri qaytarılsın?"),
        "body": pgettext_lazy(
            _CTX,
            "Sillabus müəllimə qaytarılır və «Düzəliş tələb olunur» statusuna keçir. Səbəb məcburidir — müəllim "
            "onu birbaşa redaktorda görəcək.",
        ),
        "ok": pgettext_lazy(_CTX, "Geri qaytar"),
        "tone": "warning",
        "reason_required": True,
        "reason_label": pgettext_lazy(_CTX, "Düzəliş səbəbi"),
        "reason_placeholder": pgettext_lazy(_CTX, "Konkret yazın: hansı bölmədə nə düzəldilməlidir."),
        "lines": (),
    },
    "reject": {
        "title": pgettext_lazy(_CTX, "Sillabus rədd edilsin?"),
        "body": pgettext_lazy(
            _CTX,
            "Rədd edilən versiya bağlanır və yenidən göndərilə bilmir — müəllim yeni versiya yaratmalıdır. "
            "Səbəb məcburidir və audit izinə yazılır.",
        ),
        "ok": pgettext_lazy(_CTX, "Rədd et"),
        "tone": "danger",
        "reason_required": True,
        "reason_label": pgettext_lazy(_CTX, "Rədd səbəbi"),
        "reason_placeholder": pgettext_lazy(
            _CTX, "Məsələn: qiymətləndirmə strukturu universitet siyasətinə uyğun deyil."
        ),
        "lines": (
            pgettext_lazy(_CTX, "Mövcud təsdiqlənmiş versiya (varsa) aktiv qalır"),
            pgettext_lazy(_CTX, "Tələbələr köhnə təsdiqlənmiş versiyanı görməyə davam edir"),
            pgettext_lazy(_CTX, "Jurnal statusu dəyişmir"),
        ),
    },
}

#: Panelin DİNAMİK etiketləri — JS onları JSON blokundan oxuyur.
#: (Xarici `.js` Django template engine-dən keçmir; mətn kodda qalmır.)
PANEL_TEXTS = {
    "changed": pgettext_lazy(_CTX, "dəyişib"),
    "has_note": pgettext_lazy(_CTX, "şərh var"),
    "add_note": pgettext_lazy(_CTX, "Şərh əlavə et"),
    "hide_note": pgettext_lazy(_CTX, "Şərhi gizlət"),
    "note_label": pgettext_lazy(_CTX, "Bölmə üzrə şərh"),
    "note_placeholder": pgettext_lazy(_CTX, "Müəllimə göndəriləcək konkret qeyd"),
    "old_column": pgettext_lazy(_CTX, "təsdiqlənmiş versiya"),
    "new_column": pgettext_lazy(_CTX, "təqdim edilmiş versiya"),
    "no_diff": pgettext_lazy(_CTX, "Bu versiya üçün müqayisə oluna bilən əvvəlki təsdiq yoxdur."),
    "foot": pgettext_lazy(_CTX, "Şərh yazılmış bölmə: %(count)s · geri qaytarma və rədd üçün səbəb məcburidir"),
    "reason_ok": pgettext_lazy(_CTX, "Səbəb müəllimə göndərilir və audit izinə yazılır"),
    "reason_short": pgettext_lazy(_CTX, "Ən azı %(min)s simvol — səbəb məcburidir"),
    "error": pgettext_lazy(_CTX, "Əməliyyat yerinə yetirilmədi."),
    "loading": pgettext_lazy(_CTX, "Yüklənir…"),
}


def dialog_payload() -> dict:
    """``DECISION_DIALOGS`` → JSON-a yazıla bilən sadə dict (lazy proxy YOX).

    ⚠️ ``str()`` qəsdəndir: lazy translation proxy-si JSON-a serializasiya
    olunmur (bax `project_jsonfield_lazy_proxy_tx_poison` tələsi).
    """
    rows = {}
    for key, config in DECISION_DIALOGS.items():
        rows[key] = {
            "title": str(config["title"]),
            "body": str(config["body"]),
            "ok": str(config["ok"]),
            "tone": config["tone"],
            "reason_required": config["reason_required"],
            "reason_label": str(config.get("reason_label", "")),
            "reason_placeholder": str(config.get("reason_placeholder", "")),
            "lines": [str(line) for line in config["lines"]],
        }
    return rows


def panel_payload(*, min_reason: int) -> dict:
    """Panelin mətn xəritəsi + səbəbin minimum uzunluğu."""
    rows = {key: str(value) for key, value in PANEL_TEXTS.items()}
    rows["min_reason"] = min_reason
    return rows


__all__ = [
    "ACCESS_DENIED",
    "MIN_DECISION_REASON",
    "PANEL_TEXTS",
    "dialog_payload",
    "panel_payload",
    "COVERAGE_KPI_LABELS",
    "DECISION_DIALOGS",
    "IDENTITY",
    "INTRO",
    "KPI_LABELS",
    "NOSCOPE",
    "POLICY_ROWS",
    "QUEUE_SORT_LABELS",
    "SCOPE_COUNT",
    "STATUS_FILTER_ALL",
    "UNIT_FILTER_ALL",
    "UNIT_FILTER_LABELS",
    "YEAR_FILTER_ALL",
    "coverage_titles",
]

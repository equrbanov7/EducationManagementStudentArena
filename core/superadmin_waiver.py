"""Superadmin «sənədsiz düzəliş» — sənəd / əmr tələb edən qapılarda avtomatik əsas (sahib 2026-10-27).

Sahib: «əmr və s. nə isə yükləmədən rahatlıqla nə isə silib dəyişə bilim». Miqrasiyadan sonra məlumatı
tez düzəltmək üçün SUPERADMİN (``core.permissions.is_superadmin_user`` — daimi və ya
``grant_temporary_superuser`` ilə verilmiş müvəqqəti) sənəd / əmr / izahat YÜKLƏMƏDƏN keçə bilir.

Qayda (bütün qapılarda eyni):

* rəsmi servis yolu DƏYİŞMİR — köçürmə servisi, ledger, audit, DB trigger-ləri əvvəlki kimi işləyir;
* boş qalan sahə bu moduldan gələn avtomatik qeydlə doldurulur: ``«Superadmin düzəlişi — sənədsiz
  (Ad Soyad, 27.10.2026 21:05)»`` — tarixçədə və auditdə kimin sənədsiz dəyişdiyi görünür;
* əmr nömrəsi məcburi olan sətirlərdə — ``SA-20261027-2105`` (``ORDER_PREFIX``), tarix — bu gün;
* faylı DB / model səviyyəsində məcburi olan sətirlərdə (jurnal düzəlişi, xarici nəticənin tanınması) —
  :func:`waiver_pdf`: eyni qeydi daşıyan kiçik PDF. Saxta sübut deyil — sənədin OLMADIĞINI bildirir;
* superadmin sənəd yükləsə, o sənəd işlənir (avtomatik əsas yalnız boşluğu doldurur);
* qeyri-superadmin üçün heç nə dəyişmir — bu modulun funksiyaları ``waives(user)`` yalançıdırsa toxunmur.

Qeyd mətni QƏSDƏN tərcümə edilmir: DB-yə / audit sətrinə yazılan rəsmi izdir (``StudentMovement.reason``
kimi), aktiv interfeys dilindən asılı olmamalıdır.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from core.permissions import is_superadmin_user

NOTE_PREFIX = "Superadmin düzəlişi — sənədsiz"
ORDER_PREFIX = "SA-"
PDF_NAME = "superadmin-senedsiz.pdf"

#: Audit ``changes`` açarı — sənədsiz keçid axtarışla tapılsın.
AUDIT_FLAG = "superadmin_document_waiver"


#: Sahib 2026-11-05: «alt qrupları əlavə et … sənəd yükləmə yerini pass keç» — RİM rəhbəri (sahibin öz rolu) YALNIZ
#: alt qrup yerləşdirməsində (``scope=SUBGROUP``) superadmin kimi sənədsiz keçir; qeyd mətni rolu göstərir. Digər
#: sənədli qapılar (jurnal düzəlişi, imtahan balı, məzun əmri …) RİM rəhbəri üçün dəyişmir; RİM əməkdaşı
#: (``rim_staff``) və digər rollar üçün heç nə dəyişmir.
RIM_HEAD_ROLE = "ikt_rehber"
SUBGROUP = "subgroup"
RIM_NOTE_PREFIX = "RİM rəhbəri düzəlişi — sənədsiz"


def _is_rim_head(user) -> bool:
    from django.apps import apps as django_apps

    membership = django_apps.get_model("organizations", "Membership")
    return membership.objects.filter(user=user, is_active=True, role__is_active=True, role__name=RIM_HEAD_ROLE).exists()


def waives(user, *, scope=None) -> bool:
    """Aktor sənəd tələbindən azaddırmı — autentifikasiyalı superadmin; ``scope=SUBGROUP``-da aktiv RİM rəhbəri də."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if is_superadmin_user(user):
        return True
    return scope == SUBGROUP and _is_rim_head(user)


def actor_label(user) -> str:
    full = ""
    if user is not None and hasattr(user, "get_full_name"):
        full = (user.get_full_name() or "").strip()
    return full or str(getattr(user, "username", "") or "superadmin")


def _now(when=None):
    return timezone.localtime(when) if when is not None else timezone.localtime()


def note(user, *, when=None) -> str:
    """``Superadmin düzəlişi — sənədsiz (Ad Soyad, 27.10.2026 21:05)`` (RİM rəhbəri üçün öz prefiksi ilə)."""
    moment = _now(when)
    prefix = NOTE_PREFIX if is_superadmin_user(user) else RIM_NOTE_PREFIX
    return f"{prefix} ({actor_label(user)}, {moment:%d.%m.%Y %H:%M})"


def order_number(*, when=None) -> str:
    """Əmr nömrəsi məcburi sətir üçün: ``SA-20261027-2105`` (≤ 64 simvol)."""
    moment = _now(when)
    return f"{ORDER_PREFIX}{moment:%Y%m%d-%H%M}"


def order_date(*, when=None) -> dt.date:
    return _now(when).date()


def fill_text(value, user, *, min_length: int = 1, scope=None) -> str:
    """Superadmin üçün boş / qısa mətni avtomatik qeydlə əvəz edir; digərlərində dəyəri olduğu kimi qaytarır."""
    text = str(value or "").strip()
    if waives(user, scope=scope) and len(text) < max(1, int(min_length)):
        return f"{text} · {note(user)}" if text else note(user)
    return text


def stamp(value, user, *, scope=None) -> str:
    """Sənədsiz keçid üçün mətnə avtomatik qeyd əlavə edir (``mətn · Superadmin düzəlişi — …``); təkrar əlavə etmir.

    Yalnız sənədin HƏQİQƏTƏN olmadığı halda çağırılır — superadmin sənəd veribsə mətn toxunulmaz qalır.
    """
    text = str(value or "").strip()
    if not waives(user, scope=scope) or is_waiver_text(text):
        return text
    return f"{text} · {note(user)}" if text else note(user)


def is_waiver_text(value) -> bool:
    text = str(value or "")
    return any(text.startswith(prefix) or f" · {prefix}" in text for prefix in (NOTE_PREFIX, RIM_NOTE_PREFIX))


def _font_path() -> str:
    return str(settings.BASE_DIR / "static" / "fonts" / "DejaVuSans.ttf")


def waiver_pdf(user, *, subject: str = "", when=None) -> ContentFile:
    """Fayl məcburi olan sətir üçün kiçik PDF: «sənəd yoxdur — superadmin düzəlişi» qeydi.

    PyMuPDF (``fitz``) layihədə onsuz da var (transkript PDF-i); DejaVu şrifti AZ hərflərini göstərir.
    Şrift tapılmasa daxili Helvetica ilə (ASCII) yazılır — fayl yenə etibarlı PDF olur.
    """
    import fitz

    doc = fitz.open()
    try:
        page = doc.new_page(width=595, height=842)
        lines = [note(user, when=when)]
        if subject:
            lines.append(str(subject)[:300])
        lines.append("Bu sətir üçün sənəd / əmr yüklənməyib.")
        try:
            page.insert_font(fontname="dejavu", fontfile=_font_path())
            fontname = "dejavu"
        except Exception:  # pragma: no cover — şrift faylı yoxdursa daxili şriftə düş
            fontname = "helv"
        y = 72.0
        for line in lines:
            page.insert_text((56, y), line, fontsize=11, fontname=fontname)
            y += 20
        if fontname == "dejavu":
            doc.subset_fonts()  # tam DejaVu ~780 KB; alt dəst ~35 KB
        payload = doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()
    return ContentFile(payload, name=PDF_NAME)


def document_or_waiver(document, user, *, subject: str = "", when=None):
    """Yüklənmiş fayl varsa onu, yoxdursa superadmin üçün :func:`waiver_pdf`, digərləri üçün ``None``."""
    if document:
        return document
    if waives(user):
        return waiver_pdf(user, subject=subject, when=when)
    return document


__all__ = [
    "AUDIT_FLAG",
    "NOTE_PREFIX",
    "ORDER_PREFIX",
    "PDF_NAME",
    "SUBGROUP",
    "actor_label",
    "document_or_waiver",
    "fill_text",
    "is_waiver_text",
    "note",
    "order_date",
    "order_number",
    "stamp",
    "waiver_pdf",
    "waives",
]

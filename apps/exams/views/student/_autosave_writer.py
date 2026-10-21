"""Autosave OCC-nin «kim yazdı» yaddaşı — eyni tabın öz yazısı konflikt sayılmır.

2026-10-21 (sahib hesabatı, zal imtahanı): «Qaralama saxla» və ya nəzarətçinin
«Bərpa et»-indən sonra imtahanı bitirmək istəyəndə TƏK tabda «Bu imtahan başqa tabda
yenilənib» bannerı çıxırdı və cavablar saxlanmırdı. Səbəb: EXAM-P1-06 OCC yalnız
``autosave_revision`` rəqəmini müqayisə edirdi. Eyni tabın İKİ sorğusu (fonda gedən
autosave + «Qaralama saxla»/«Bitir») eyni base revision-u daşıyırdı; server birini
yazıb revision-u artırırdı, ikincisi isə «başqa tab yazıb» sayılıb 409 alırdı. Cavabı
itən (504) autosave-dən sonrakı yazı və yazı yolda ikən səhifə yenilənməsi eyni tələyə
düşürdü.

Həll: klient hər tab üçün təsadüfi ``autosave_writer`` id-si və artan ``autosave_seq``
göndərir. Server son yazının (revision, writer, writer-in fasiləsiz yazı seriyasının
başladığı revision, son seq) qeydini saxlayır. Base revision geridədirsə, amma aradakı
BÜTÜN yazılar həmin writer-indirsə (və seq irəliləyirsə — köhnə, gecikmiş sorğu deyil),
yazı qəbul olunur: tab yalnız öz yazısını «üstələyir». Başqa writer-in yazısı arada
olubsa — əvvəlki kimi 409 (çox-tab qoruması qalır), cavabda ``reason`` ilə.

Qeyd keşdədir (prod: Redis); keş itərsə davranış köhnə sərt OCC-yə qayıdır və klient
409-dan sonra serverlə sinxronlaşır (``take_exam/resync.js``).
"""

import re
import time

_WRITER_TTL = 12 * 60 * 60
#: Zal (final/midterm) imtahanında aktiv tabın «sahiblik» müddəti: son yazıdan bu qədər saniyə
#: ərzində BAŞQA writer-in yazısı (base cari olsa belə) 409 alır. Qısadır ki, kompüter/brauzer
#: çökəndən sonra (yenidən giriş adətən dəqiqələr çəkir) yeni tab gözləmədən işləsin.
CENTER_OWNER_LEASE_SECONDS = 30
_WRITER_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _writer_key(attempt):
    return f"exam:autosave:writer:{attempt.pk}"


def request_writer(request):
    """POST-dan ``(writer_id, seq)``; etibarsız/yoxdursa ``("", 0)``."""
    writer = (request.POST.get("autosave_writer") or "").strip()
    if not _WRITER_RE.match(writer):
        return "", 0
    try:
        seq = max(0, int(request.POST.get("autosave_seq") or "0"))
    except (TypeError, ValueError):
        seq = 0
    return writer, seq


def writer_state(attempt):
    """Son yazının qeydi ``{rev, writer, since, seq}`` və ya ``None`` (keş əlçatmaz/boş)."""
    from django.core.cache import cache

    try:
        state = cache.get(_writer_key(attempt))
    except Exception:  # noqa: BLE001 — keş yoxdursa sərt OCC
        return None
    return state if isinstance(state, dict) else None


def current_writer_state(attempt):
    """GET render üçün: qeyd yalnız cari revision-a aiddirsə."""
    state = writer_state(attempt)
    if not state or state.get("rev") != attempt.autosave_revision:
        return None
    return state


def own_stale_write_allowed(request, attempt, base_revision):
    """Base geridədir, amma ``(base, current]`` aralığının hamısı bu writer-indir?"""
    writer, seq = request_writer(request)
    if not writer or base_revision >= attempt.autosave_revision:
        return False
    state = current_writer_state(attempt)
    if not state or state.get("writer") != writer:
        return False
    if base_revision < int(state.get("since") or 0):
        return False
    # Köhnə (gecikmiş) sorğu — məs. yenilənmədən əvvəlki səhifənin yolda qalan yazısı —
    # tabın daha yeni yazısını əzməsin.
    return seq > int(state.get("seq") or 0)


def center_owner_lease_held(request, attempt):
    """2026-10-21 (sahib): zal imtahanında HƏQİQİ ikinci tab ümumiyyətlə yaza bilməz.

    Son yazı başqa (boş olmayan) writer-indirsə və ``CENTER_OWNER_LEASE_SECONDS`` keçməyibsə — True.
    Writer-siz (köhnə keşlənmiş JS) sorğuya və qeyri-zal imtahanına təsir etmir (onlarda birləşmə qalır).
    """
    writer, _seq = request_writer(request)
    if not writer:
        return False
    state = current_writer_state(attempt)
    if not state or not state.get("writer") or state.get("writer") == writer:
        return False
    if time.time() - float(state.get("at") or 0) > CENTER_OWNER_LEASE_SECONDS:
        return False
    from apps.exams.services.center_exams import is_center_exam

    return is_center_exam(attempt.exam)


def conflict_reason(request, attempt):
    """409 cavabı üçün: ``foreign_writer`` (başqa tab/cihaz) və ya ``unknown``."""
    writer, _seq = request_writer(request)
    state = current_writer_state(attempt)
    if state and state.get("writer") and state.get("writer") != writer:
        return "foreign_writer"
    return "unknown"


def remember_writer(request, attempt):
    """Uğurlu yazıdan (revision artandan) SONRA, sətir kilidi altında çağırılır."""
    from django.core.cache import cache

    writer, seq = request_writer(request)
    revision = attempt.autosave_revision
    previous = writer_state(attempt)
    since = revision - 1
    if previous and writer and previous.get("writer") == writer and previous.get("rev") == revision - 1:
        since = int(previous.get("since") or 0)
        seq = max(seq, int(previous.get("seq") or 0))
    try:
        cache.set(
            _writer_key(attempt),
            {"rev": revision, "writer": writer, "since": since, "seq": seq, "at": time.time()},
            _WRITER_TTL,
        )
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "CENTER_OWNER_LEASE_SECONDS",
    "center_owner_lease_held",
    "conflict_reason",
    "current_writer_state",
    "own_stale_write_allowed",
    "remember_writer",
    "request_writer",
    "writer_state",
]

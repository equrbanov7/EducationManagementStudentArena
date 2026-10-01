"""Proktorinq SİQNALLARI — aşağı/orta etibarlı evristik aşkarlamalar.

Qayda pozuntuları (tam ekrandan çıxma, tab dəyişmə …) ``SupervisionIncident``-ə
yazılır və pozuntu sayğacını artırır (mövcud axın). Buradakı siqnallar isə
brauzer genişlənməsi / DevTools / əlavə monitor / mətn inyeksiyası kimi
EVRİSTİKALARDIR: səhv-müsbət ehtimalı olduğu üçün tələbəni KİLİDLƏMİR, yalnız
``ProctoringLog``-a (mövcud, RLS-li cədvəl) yazılır və risk xalına düşür.

Etibar sərhədi: brauzerdən gələn hər şey saxtalaşdırıla bilər. Ona görə
server yalnız ağ siyahıdakı ``kind``-ları qəbul edir, ciddilik (severity)
SERVERDƏ təyin olunur (klient göndərə bilməz), detal yastı primitivlərə
endirilir, həm cəhd başına, həm də növ başına limit var.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from core.rate_limit import record_rate_limit_hit

_CTX = "exams.proctoring.signal"

#: kind → (ProctoringLog.event_type, severity). Severity YALNIZ serverdə.
CLIENT_SIGNAL_KINDS = {
    "devtools_open": ("browser_console", "medium"),
    "multi_monitor": ("multiple_windows", "medium"),
    "dom_injection": ("suspicious_activity", "low"),
    "extension_frame": ("suspicious_activity", "medium"),
    "extension_resource": ("suspicious_activity", "medium"),
    "ai_extension": ("suspicious_activity", "high"),
    "automation": ("suspicious_activity", "high"),
    "paste_input": ("copy_paste", "high"),
    "bulk_insert": ("copy_paste", "high"),
    "programmatic_input": ("copy_paste", "high"),
    "fast_input": ("suspicious_activity", "medium"),
    "print_attempt": ("screenshot_attempt", "medium"),
}

#: Yalnız serverin özünün yazdığı siqnallar (klientdən qəbul OLUNMUR).
SERVER_SIGNAL_KINDS = {
    "heartbeat_gap": ("network_disconnect", "low"),
}

ALL_SIGNAL_KINDS = {**CLIENT_SIGNAL_KINDS, **SERVER_SIGNAL_KINDS}

SIGNAL_LABELS = {
    "devtools_open": pgettext_lazy(_CTX, "Tərtibatçı alətləri (DevTools) açıq ola bilər"),
    "multi_monitor": pgettext_lazy(_CTX, "Əlavə monitor qoşulub"),
    "dom_injection": pgettext_lazy(_CTX, "Səhifəyə kənar element əlavə olunub"),
    "extension_frame": pgettext_lazy(_CTX, "Brauzer genişlənməsinin pəncərəsi aşkarlandı"),
    "extension_resource": pgettext_lazy(_CTX, "Brauzer genişlənməsinin izi aşkarlandı"),
    "ai_extension": pgettext_lazy(_CTX, "Süni intellekt köməkçisi (genişlənmə) aşkarlandı"),
    "automation": pgettext_lazy(_CTX, "Avtomatlaşdırılmış brauzer (bot)"),
    "paste_input": pgettext_lazy(_CTX, "Cavab xanasına yapışdırma cəhdi"),
    "bulk_insert": pgettext_lazy(_CTX, "Cavaba bir anda böyük mətn daxil edildi"),
    "programmatic_input": pgettext_lazy(_CTX, "Cavab skriptlə dəyişdirildi"),
    "fast_input": pgettext_lazy(_CTX, "Qeyri-adi sürətli yazı"),
    "print_attempt": pgettext_lazy(_CTX, "Çap cəhdi"),
    "heartbeat_gap": pgettext_lazy(_CTX, "Nəzarət siqnalı müvəqqəti kəsilmişdi"),
}

# Limitlər: cəhd başına ümumi axın + növ başına pəncərə + ömürlük tavan.
SIGNAL_RATE = "30/1m"
SIGNAL_KIND_RATE = "10/10m"
SIGNAL_TOTAL_CAP = 400
_TOTAL_WINDOW = "400/1d"

_DETAIL_MAX_KEYS = 10
_DETAIL_MAX_VALUE_LEN = 200


def sanitize_signal_detail(detail) -> dict:
    """Klient detalını yastı, qısa primitivlərə endirir (nested saxlanmır)."""
    if not isinstance(detail, dict):
        return {}
    clean = {}
    for key, value in list(detail.items())[:_DETAIL_MAX_KEYS]:
        key = str(key)[:40]
        if key in {"kind", "severity", "source"}:
            continue  # server sahələri — klient üstələyə bilməz
        if isinstance(value, bool) or value is None:
            clean[key] = value
        elif isinstance(value, (int, float)):
            clean[key] = max(-1_000_000_000, min(1_000_000_000, value))
        else:
            clean[key] = str(value)[:_DETAIL_MAX_VALUE_LEN]
    return clean


def signal_label(kind: str) -> str:
    label = SIGNAL_LABELS.get(kind)
    return str(label) if label is not None else kind


def signal_throttle(attempt_id: int, kind: str) -> str:
    """ "ok" | "rate" (429 — axın limiti) | "dedup" (səssiz atılır)."""
    exceeded, _retry = record_rate_limit_hit("proctor_signal", SIGNAL_RATE, attempt_id)
    if exceeded:
        return "rate"
    exceeded, _retry = record_rate_limit_hit("proctor_signal_kind", SIGNAL_KIND_RATE, attempt_id, kind)
    if exceeded:
        return "dedup"
    exceeded, _retry = record_rate_limit_hit("proctor_signal_total", _TOTAL_WINDOW, attempt_id)
    if exceeded:
        return "dedup"
    return "ok"


def log_proctoring_signal(attempt, kind: str, detail=None):
    """Siqnalı ``ProctoringLog``-a yazır. Naməlum ``kind`` → None (yazılmır)."""
    mapping = ALL_SIGNAL_KINDS.get(kind)
    if mapping is None:
        return None
    event_type, severity = mapping
    from apps.exams.models import ProctoringLog

    payload = sanitize_signal_detail(detail or {})
    payload["kind"] = kind
    payload["severity"] = severity
    return ProctoringLog.objects.create(exam_attempt=attempt, event_type=event_type, details=payload)


__all__ = [
    "ALL_SIGNAL_KINDS",
    "CLIENT_SIGNAL_KINDS",
    "SERVER_SIGNAL_KINDS",
    "SIGNAL_LABELS",
    "SIGNAL_TOTAL_CAP",
    "log_proctoring_signal",
    "sanitize_signal_detail",
    "signal_label",
    "signal_throttle",
]

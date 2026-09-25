"""Profil «exam-score-entry» — BİTMİŞ DÖVR KİLİDİ və RİM rəhbərinin düzəliş rejimi (2026-09-26).

Sahib: «köhnə ilin balını dəyişmək olmamalıdır, ancaq RİM rəhbəri tərəfindən
təqdimat əsasında ola bilər … jurnalda necə «düzəliş aktivləşdir» düyməsi var,
burada da elə olsun». Qayda və server qapısı
``apps/registrar/exam_score_period_lock.py``-dadır; bu modul yalnız səthin
kontekstini qurur:

* ``period_locked`` — seçilmiş semestr kilidlidir (sorğusuz, tarixə görə);
* ``can_unlock_period`` — aktor RİM rəhbəri / superadmin (yalnız kilidli
  dövrdə BİR sorğu — cari dövrün sorğu büdcəsi dəyişmir);
* ``correction_mode`` — ``?ese_correct=1`` + icazə (jurnalın ``?correct=1``
  güzgüsü); forma və idxal ``correction_mode=1`` daşıyır;
* ``read_only`` — kilidli, rejim aktiv deyil: siyahı yalnız oxunur, yadda
  saxlama / idxal gizlidir (server onsuz da rədd edir).
"""

from apps.accounts.views._helpers.formatting import _append_query_params


def fill_period_lock(request, section, *, period, organization, service, is_superadmin) -> None:
    """``section``-a kilid/rejim açarlarını yaz (açılış seçilibsə çağırılır)."""
    lock = service.exam_score_period_lock
    locked = lock.period_is_locked(period)
    can_unlock = locked and (is_superadmin or lock.can_unlock_past_period(request.user, organization))
    correction_mode = bool(can_unlock and lock.correction_mode_requested(request.GET))
    base_url = section["post_next_url"]
    section["period_locked"] = locked
    section["can_unlock_period"] = can_unlock
    section["correction_mode"] = correction_mode
    section["read_only"] = locked and not correction_mode
    section["correction_mode_field"] = lock.CORRECTION_MODE_FIELD
    section["justification_file_field"] = lock.JUSTIFICATION_FILE_FIELD
    section["evidence_accept"] = lock.EVIDENCE_ACCEPT
    section["evidence_max_mb"] = lock.EVIDENCE_MAX_MB
    section["correction_on_url"] = _append_query_params(base_url, **{lock.CORRECTION_MODE_QUERY: "1"})
    section["correction_off_url"] = base_url
    if correction_mode:
        # Yadda saxlamadan sonra səhifə düzəliş rejimində qalır (jurnal redirect-i kimi).
        section["post_next_url"] = section["correction_on_url"]
    if section["read_only"]:
        # Yalnız-oxu: «Fayldan yüklə» tabı yoxdur (idxal tətbiqi onsuz da 403-dür).
        section["tabs"] = [tab for tab in section.get("tabs", []) if tab.get("key") != "import"]


__all__ = ["fill_period_lock"]

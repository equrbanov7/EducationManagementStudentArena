"""«Akademik qeydlər» icmalının qısa müddətli keş qatı.

NİYƏ AYRICA MODUL? İcmalın iki bahalı dəyəri var — xülasə box-ları və süzgəc
sahəsindəki TƏKRARSIZ tələbə sayı — və hər ikisi EYNİ suala cavab verir:
«bu aktor, bu süzgəclə nə görür?». Ona görə açar da eyni olmalıdır; açar
qurma qaydası iki yerdə təkrarlansa, pager-dəki yekun ilə «Tələbə» qutusundakı
rəqəm bir gün mütləq ayrılar. Qayda burada TƏKDİR
(:mod:`apps.accounts.academic_records` yalnız istifadə edir).

NƏ KEŞLƏNİR VƏ NİYƏ?

* **Box-lar** — tərifən bütün süzgəc sahəsi üzrə aqreqatdır: org-səviyyəli
  aktorda 7 800 tələbənin bütün yazılışları qiymətləndirilir (7.8–9.5 s, QA
  2026-09-05 P2-19). Səhifədən-səhifəyə DƏYİŞMİR.
* **Tələbə sayı** — ``COUNT(DISTINCT student_id)``; scope-un ölçüsü ilə böyüyür,
  amma səhifə çevrilişində yenə dəyişmir. Əvvəl HƏR səhifə sorğusunda təkrar
  icra olunurdu.

AÇAR: aktorun **əhatəsi** (scope növü + unit id-ləri) + aktiv süzgəclər —
istifadəçi adı YOX. Eyni əhatəli iki dekan eyni rəqəmi görür, ona görə onları
ayrı-ayrı hesablamağın mənası yoxdur.

TTL qəsdən qısadır: bal yazısı bir neçə dəqiqə gecikə bilər, amma «dünənki»
rəqəm göstərilməməlidir.
"""

from __future__ import annotations

import hashlib
import json

from django.core.cache import cache

#: Keş müddəti (saniyə) — box-lar və sayğac üçün eyni.
TTL = 300

_PREFIX = "academic_records:"


def scope_key(organization, scope, filters) -> str:
    """(təşkilat, əhatə, süzgəclər) → sabit keş açarı; qurula bilməsə boş sətir.

    Boş sətir «keşləmə» deməkdir (fail-open): serialize oluna bilməyən süzgəc
    dəyəri gəlsə, nəticə səhv keşlənməkdənsə hər dəfə hesablanır."""
    try:
        raw = json.dumps(
            {
                "org": str(getattr(organization, "pk", "")),
                "scope": [scope.scope_type, sorted(str(u) for u in (scope.unit_ids or ()))],
                "filters": {k: str(v) for k, v in sorted((filters or {}).items()) if v},
            },
            sort_keys=True,
        )
    except (TypeError, ValueError):
        return ""
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def get_summary(organization, scope, filters):
    """Keşlənmiş box payload-u (yoxdursa ``None``)."""
    key = scope_key(organization, scope, filters)
    return cache.get(f"{_PREFIX}summary:{key}") if key else None


def set_summary(organization, scope, filters, payload) -> None:
    """Box payload-unu keşə yaz (açar qurulmadısa səssizcə keç)."""
    key = scope_key(organization, scope, filters)
    if key:
        cache.set(f"{_PREFIX}summary:{key}", payload, TTL)


def student_total(organization, scope, filters, compute) -> int:
    """Təkrarsız tələbə sayı — keşdən, yoxdursa ``compute()`` ilə hesablanıb yazılır.

    ``compute`` sıfır arqumentli çağırılandır ki, keş isti olanda sorğu
    ÜMUMİYYƏTLƏ qurulmasın."""
    key = scope_key(organization, scope, filters)
    cache_key = f"{_PREFIX}count:{key}" if key else ""
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    total = compute()
    if cache_key:
        cache.set(cache_key, total, TTL)
    return total


__all__ = ["TTL", "get_summary", "scope_key", "set_summary", "student_total"]

"""Dəqiqləşdirmə növbəsinin SAYĞACLARI — hamısı TƏK sorğuda.

NİYƏ AYRI MODUL
---------------
:mod:`apps.registrar.legacy_grade_review` sorğu qatıdır və modul-ölçü büdcəsinə
(600 sətir) yaxındır. Sayğaclar isə öz-özlüyündə bir mövzudur: «növbədə nə qədər
var, neçəsinə baxılıb, hansı çip neçə sətir göstərir».

NİYƏ TƏK SORĞU
--------------
Əvvəllər hər sayğac ayrıca ``COUNT`` idi: irəliləyiş 2 + kateqoriya 7×2 = **16
sorğu**, hər biri 169 min faktlıq cədvəli baştan sona oxuyurdu. Süzgəci
dəyişmək, səhifə çevirmək, çipə klikləmək — hamısı bu qiyməti ödəyirdi.

Halbuki bütün sayğaclar EYNİ bazadan çıxır və yalnız şərtləri ilə fərqlənir.
Postgres-in ``COUNT(*) FILTER (WHERE …)`` konstruksiyası (Django-da
``Count(filter=…)``) məhz bunun üçündür: cədvəl BİR DƏFƏ oxunur, hər sətir isə
eyni anda bütün şərtlərdən keçirilir.

⚠️ DOĞRULUQ: şərtlər burada YENİDƏN YAZILMIR. Hər sayğac
``CategorySpec.condition``-un ÖZÜNÜ işlədir — yəni süzgəcin tapdığı sətirlə
sayğacın saydığı sətir eyni ``Q`` obyektindən çıxır. Sayğac «təxmini» DEYİL,
dəqiqdir.

⚠️ ALIAS-LAR MÖVQEYƏ GÖRƏDİR (``t_0``, ``r_0``, …), kateqoriya koduna görə yox.
Kateqoriyaların bir hissəsi ``LegacyGradeMappingStatus`` enum-undan doğulur;
enum-a Python identifikatoru kimi yararsız kod (məsələn defisli) gələn gün
kod-əsaslı alias SQL-i səssizcə sındırardı. Mövqe həmişə etibarlıdır.
"""

from __future__ import annotations

from django.db.models import Count, Q

from .legacy_grade_review import (
    SEVERITY_LABELS,
    SEVERITY_ORDER,
    annotated_facts,
    apply_filters,
    category_specs,
    reviewed_condition,
)

_TOTAL = "t_"
_REVIEWED = "r_"
_QUEUE_TOTAL = "queue_total"
_QUEUE_REVIEWED = "queue_reviewed"

#: Heç bir sətri seçməyən neytral şərt (``|=`` üçün başlanğıc dəyər).
_NOTHING = Q(pk__in=())


def _any_of(specs) -> Q:
    condition = _NOTHING
    for spec in specs:
        condition |= spec.condition
    return condition


def counted_base(*, organization, user=None, filters=None):
    """Sayğacların ORTAQ bazası: struktur/fənn/müəllim/dövr/axtarış süzgəcləri.

    ``status`` və ``severity`` QƏSDƏN çıxarılır — onlar sayğacın bazası deyil,
    sayğacın ŞƏRTİ olur (aşağıda ``FILTER`` içinə düşür). Belə olmasa «baxılmayıb»
    seçiləndə məxrəc də daralar və faiz həmişə 0 görünərdi.
    """
    scoped = dict(filters or {})
    scoped.pop("status", None)
    scoped.pop("severity", None)
    return apply_filters(
        annotated_facts(organization=organization, user=user),
        organization=organization,
        filters=scoped,
    )


def _queue_condition(specs, filters) -> Q:
    """İrəliləyiş məxrəcinin şərti: seçilmiş kateqoriyalar (+ şiddət süzgəci)."""
    by_code = {spec.code: spec for spec in specs}
    selected = [by_code[code] for code in (filters.get("categories") or ()) if code in by_code]
    condition = _any_of(selected or specs)
    severity = str(filters.get("severity") or "").strip()
    if severity in SEVERITY_ORDER:
        condition &= _any_of([spec for spec in specs if spec.severity == severity])
    return condition


def queue_counts(*, organization, user=None, filters=None):
    """İrəliləyiş + hər kateqoriyanın (ümumi, baxılmış) cütü — BİR sorğu.

    Nəticə: ``{"progress": {...}, "categories": [...]}`` — səthin gözlədiyi
    formatın eynisi, sadəcə 16 sorğu əvəzinə bir dənə ilə.
    """
    filters = dict(filters or {})
    specs = category_specs(organization)
    reviewed = reviewed_condition(organization)

    aggregates = {
        _QUEUE_TOTAL: Count("pk", filter=_queue_condition(specs, filters)),
        _QUEUE_REVIEWED: Count("pk", filter=_queue_condition(specs, filters) & reviewed),
    }
    for index, spec in enumerate(specs):
        aggregates[f"{_TOTAL}{index}"] = Count("pk", filter=spec.condition)
        aggregates[f"{_REVIEWED}{index}"] = Count("pk", filter=spec.condition & reviewed)

    values = counted_base(organization=organization, user=user, filters=filters).aggregate(**aggregates)

    total = values[_QUEUE_TOTAL] or 0
    done = values[_QUEUE_REVIEWED] or 0
    return {
        "progress": {
            "total": total,
            "reviewed": done,
            "pending": max(total - done, 0),
            "percent": int(round(done * 100 / total)) if total else 0,
        },
        "categories": [
            {
                "code": spec.code,
                "label": str(spec.label),
                "hint": str(spec.hint),
                "severity": spec.severity,
                "severity_label": str(SEVERITY_LABELS[spec.severity]),
                "source": spec.source,
                "total": values[f"{_TOTAL}{index}"] or 0,
                "reviewed": values[f"{_REVIEWED}{index}"] or 0,
            }
            for index, spec in enumerate(specs)
        ],
    }


__all__ = ["counted_base", "queue_counts"]

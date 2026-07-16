"""Kollokvium pəncərəsi gating servisi.

Jurnal (müəllim bal yazır) və İmtahan Mərkəzi (pəncərəni idarə edir) bu servisi
paylaşır. Bir yerdə saxlanır ki, "açıqdır?" qərarı hər iki tərəfdə eyni olsun.

Vəziyyətlər (``entry_state`` → ``status``):
    not_configured — İmtahan Mərkəzi bu K üçün pəncərə YARATMAYIB (müəllim yaza bilməz)
    inactive       — pəncərə var, amma aktivləşdirilməyib (müəllim yaza bilməz)
    scheduled      — aktivdir, amma açılış tarixi hələ gəlməyib
    open           — açıqdır (müəllim SƏRBƏST yaza/dəyişə bilər)
    closed         — son tarix keçib (kilidli)
"""

import datetime

from django.apps import apps as django_apps


def window_for(offering, k_index):
    """(offering.organization, offering.period, k_index) üçün pəncərə və ya None."""
    KollokviumWindow = django_apps.get_model("registrar", "KollokviumWindow")
    return (
        KollokviumWindow.objects.filter(
            organization_id=offering.organization_id,
            period_id=offering.period_id,
            k_index=k_index,
        )
        .prefetch_related("extra_grants")
        .first()
    )


def _offering_unit_ids(offering):
    """offering.group + onun bütün ata OrgUnit-ləri (fakültə/kafedra grant uyğunluğu üçün)."""
    ids = set()
    unit = getattr(offering, "group", None)
    guard = 0
    while unit is not None and guard < 12:
        ids.add(unit.id)
        unit = unit.parent
        guard += 1
    return ids


def effective_extra_days(window, offering):
    """Bu offering-ə tətbiq olunan grant-ların ƏN BÖYÜK əlavə günü (yoxdursa 0).

    ``offering.group is None`` (bütün-ixtisas dərsi) — org-unit ağacı yoxdur, ona
    görə fakültə/kafedra grant-ını dəqiq uzlaşdıra bilmirik. Müəllimi verilmiş
    uzatma müddətində KİLİDLƏMƏMƏK üçün belə offering-lərə pəncərənin BÜTÜN
    grant-larının ən böyüyünü tətbiq edirik (kilidlənmə > az uzatma).
    """
    best = 0
    unit_ids = None
    group_less = getattr(offering, "group", None) is None
    for grant in window.extra_grants.all():
        if grant.scope == "organization" or group_less:
            best = max(best, grant.extra_days)
        elif grant.org_unit_id:
            if unit_ids is None:
                unit_ids = _offering_unit_ids(offering)
            if grant.org_unit_id in unit_ids:
                best = max(best, grant.extra_days)
    return best


def effective_deadline(window, offering):
    """closes_on + effektiv əlavə gün → müəllimin son bal-yazma günü (daxil)."""
    return window.closes_on + datetime.timedelta(days=effective_extra_days(window, offering))


def entry_state(offering, k_index, today):
    """Bu offering-in K{k_index+1}-i üçün bal-yazma vəziyyəti (yuxarıdakı status-lar).

    ``window`` None ola bilər (not_configured); açıq statuslarda ``deadline`` var.
    """
    window = window_for(offering, k_index)
    if window is None:
        return {"status": "not_configured", "window": None}
    if not window.is_active:
        return {"status": "inactive", "window": window, "opens_on": window.opens_on}

    deadline = effective_deadline(window, offering)
    if today < window.opens_on:
        return {"status": "scheduled", "window": window, "opens_on": window.opens_on, "deadline": deadline}
    if today > deadline:
        return {"status": "closed", "window": window, "deadline": deadline}
    return {"status": "open", "window": window, "opens_on": window.opens_on, "deadline": deadline}


def is_open(offering, k_index, today):
    """Müəllim indi bu K-ya bal yaza/dəyişə bilərmi?"""
    return entry_state(offering, k_index, today)["status"] == "open"

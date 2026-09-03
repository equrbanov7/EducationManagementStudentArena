"""RİM jurnal-bağlanma xəbərdarlığının gating servisi (jurnal ↔ RİM kabineti).

Kollokvium pəncərəsi servisinin (``kollokvium_windows``) eyni nümunəsi: RİM
bildirişi yaradır, jurnal isə burada hesablanmış vəziyyəti sürüşən zolaqda
göstərir. Bir yerdə saxlanılır ki, «görünürmü?» qərarı hər iki tərəfdə eyni olsun.

Vəziyyətlər (:func:`notice_state` → ``status``):
    none      — bu offering-ə uyğun AKTİV bildiriş yoxdur (zolaq göstərilmir)
    upcoming  — bildiriş var, bağlanma tarixi hələ gəlməyib (zolaq GÖRÜNÜR)
    passed    — bağlanma tarixi keçib (zolaq göstərilmir — jurnal onsuz da bağlanmalıdır)
"""

from django.apps import apps as django_apps


def _offering_unit_ids(offering):
    """offering.group + onun bütün ata OrgUnit-ləri (fakültə/kafedra uyğunluğu üçün)."""
    ids = set()
    unit = getattr(offering, "group", None)
    guard = 0
    while unit is not None and guard < 12:
        ids.add(unit.id)
        unit = unit.parent
        guard += 1
    return ids


def notices_for(offering):
    """Bu offering-in org + dövrü üçün AKTİV bildirişlər (əhatə süzgəcindən sonra).

    Əhatə qaydası kollokvium ``effective_extra_days``-in güzgüsüdür:
    org-əhatəli bildiriş HƏMİŞƏ tutur; fakültə/kafedra bildirişi yalnız
    offering-in qrup→ata zəncirinə düşürsə. ``offering.group is None``
    (bütün-ixtisas dərsi) — unit ağacı yoxdur, ona görə yalnız org-əhatəli
    bildiriş tətbiq olunur (yanlış bildiriş göstərməmək üçün).
    """
    JournalCloseNotice = django_apps.get_model("registrar", "JournalCloseNotice")
    rows = list(
        JournalCloseNotice.objects.filter(
            organization_id=offering.organization_id,
            period_id=offering.period_id,
            is_active=True,
        )
    )
    if not rows:
        return []
    unit_ids = None
    matched = []
    for notice in rows:
        if notice.scope == "organization":
            matched.append(notice)
            continue
        if not notice.org_unit_id:
            continue
        if unit_ids is None:
            unit_ids = _offering_unit_ids(offering)
        if notice.org_unit_id in unit_ids:
            matched.append(notice)
    return matched


def notice_state(offering, today):
    """Bu offering üçün göstəriləcək bildiriş vəziyyəti.

    Birdən çox bildiriş uyğun gəlirsə ƏN TEZ bağlanma tarixi seçilir — müəllim
    üçün bağlayıcı olan ən yaxın son tarixdir (fakültə bildirişi org bildirişindən
    tez ola bilər).
    """
    matched = notices_for(offering)
    if not matched:
        return {"status": "none", "notice": None}
    upcoming = [n for n in matched if n.closes_on >= today]
    if not upcoming:
        latest = max(matched, key=lambda n: n.closes_on)
        return {"status": "passed", "notice": latest, "closes_on": latest.closes_on}
    nearest = min(upcoming, key=lambda n: n.closes_on)
    return {"status": "upcoming", "notice": nearest, "closes_on": nearest.closes_on}


def journal_banner(offering, today):
    """Jurnal şablonu üçün sadələşdirilmiş kontekst (``None`` → zolaq yoxdur)."""
    state = notice_state(offering, today)
    if state["status"] != "upcoming":
        return None
    notice = state["notice"]
    return {
        "closes_on": notice.closes_on,
        "message": notice.message,
        "scope_display": notice.get_scope_display(),
    }

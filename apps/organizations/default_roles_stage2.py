"""Tədris planı / semestr açılışı / akademik qrup açarlarının rol paylanması.

Dizayn handoff Mərhələ 2 (ekran 05 «Tədris planı», 06 «Qruplar», 07 «Semestr
açılışı»). Rol YARATMIR — yalnız MÖVCUD rollara yeni açarları paylayır.

NİYƏ ``default_roles_teaching_office``-a yazılmadı? Həmin faylın xəritəsini
migration ``0038`` oxuyur və backward() məhz oradakı açarları geri çıxarır.
Yeni açarlar ora əlavə olunsaydı, Mərhələ 1 migrasiyasının geri qaytarılması
Mərhələ 2 icazələrini də səssizcə silərdi. Ayrı xəritə = ayrı migration = geri
dönüş dəqiq.

──────────────────────────────────────────────────────────────────────────────
SƏLAHİYYƏT AYRILIĞI (əsasnamə 5.5)
──────────────────────────────────────────────────────────────────────────────
Təsdiq zəncirinin hər halqası AYRI açardır və AYRI rola verilir:

    kafedra müdiri  → plan.approve_chair
    dekan           → plan.approve_council
    Tədris şöbəsi   → plan.approve_office

Yəni bir rol zənciri təkbaşına başdan-sona keçə bilmir. RİM (``ikt_rehber``) və
prorektor operator olduğu üçün ailənin hamısını daşıyır; rektorda ``*`` var.
"""

#: Rol adı → verilən açarlar. Rol yoxdursa (tenant onu işlətmirsə) atlanır.
STAGE2_ROLE_GRANTS: dict[str, tuple[str, ...]] = {
    "teaching_office_head": (
        "plan.view",
        "plan.edit",
        "plan.submit",
        "plan.approve_office",
        "semester.view",
        "semester.open",
        "semester.lock",
        "semester.unlock",
        "unit.group_manage",
    ),
    # Əməkdaş planı hazırlayır və göndərir, TƏSDİQLƏMİR; semestri açır, amma
    # KİLİDLƏMİR (kilid geri qaytarılmır — şöbə rəhbərinin qərarıdır).
    "teaching_office_staff": (
        "plan.view",
        "plan.edit",
        "plan.submit",
        "semester.view",
        "semester.open",
        "unit.group_manage",
    ),
    "chair_head": (
        "plan.view",
        "plan.edit",
        "plan.submit",
        "plan.approve_chair",
        "semester.view",
    ),
    "dean": (
        "plan.view",
        "plan.approve_council",
        "semester.view",
    ),
    "program_coordinator": (
        "plan.view",
        "semester.view",
        "unit.group_manage",
    ),
    "ikt_rehber": (
        "plan.view",
        "plan.edit",
        "plan.submit",
        "plan.approve_chair",
        "plan.approve_council",
        "plan.approve_office",
        "semester.view",
        "semester.open",
        "semester.lock",
        "semester.unlock",
        "unit.group_manage",
    ),
    "vice_rector": (
        "plan.view",
        "plan.edit",
        "plan.submit",
        "plan.approve_council",
        "plan.approve_office",
        "semester.view",
        "semester.open",
        "semester.lock",
        "semester.unlock",
        "unit.group_manage",
    ),
}


def apply_stage2_grants(roles):
    """``STAGE2_ROLE_GRANTS``-i rol siyahısına idempotent tətbiq edir."""
    for role in roles:
        wanted = STAGE2_ROLE_GRANTS.get(role.get("name"))
        if not wanted:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions:
            continue
        for permission in wanted:
            prefix_wildcard = f"{permission.split('.', 1)[0]}.*"
            if permission in permissions or prefix_wildcard in permissions:
                continue
            permissions.append(permission)
    return roles


__all__ = ["STAGE2_ROLE_GRANTS", "apply_stage2_grants"]

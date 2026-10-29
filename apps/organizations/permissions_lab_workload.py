"""Laborant — öz kafedrasının «Yük bölgüsü»nü görür və redaktə edir (sahib 2026-10-29).

Sahibin sözü: «Laborantlara bu hissəni aç, hər laborant özünə aid olan kafedranın yükləri görsün və editləyə də
bilsin».

* YENİ açar YOXDUR — kafedra müdirinin mövcud ``workload.manage`` (sətir redaktəsi) və ``workload.distribute``
  (müəllimə bölgü) açarları verilir. ``workload.view`` laborantda artıq var (``default_roles_stage4``).
* Əhatə: laborant rolu UNIT-əhatəlidir — üzvlüyün ``scope_unit``-i (kafedra) alt-ağacı. Hər yazı əməli
  ``apps.workload.services.scoping`` ilə kafedra üzrə fail-closed yenidən yoxlanılır; ``scope_unit``-siz laborant
  boş kafedra siyahısı görür.
* Zəncirin digər halqaları (``workload.submit`` / ``review`` / ``approve``) QƏSDƏN verilmir.

Mövcud tenantlar: miqrasiya ``organizations/0077``. NİYƏ AYRI MODUL? ``permissions_unit_view.py`` naxışı.
"""

LAB_WORKLOAD_ROLE = "lab_assistant"
LAB_WORKLOAD_GRANTS: tuple[str, ...] = ("workload.view", "workload.manage", "workload.distribute")


def _covered(permissions, key) -> bool:
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def apply_lab_workload_grants(roles):
    """Laborant rol şablonuna açarları idempotent əlavə edir (``*`` / ``workload.*`` daşıyana toxunmur)."""
    for role in roles:
        if role.get("name") != LAB_WORKLOAD_ROLE:
            continue
        permissions = role.setdefault("permissions", [])
        for key in LAB_WORKLOAD_GRANTS:
            if not _covered(permissions, key):
                permissions.append(key)
    return roles


__all__ = ["LAB_WORKLOAD_GRANTS", "LAB_WORKLOAD_ROLE", "apply_lab_workload_grants"]

"""Rol şablonlarının paylaşılan icazə dəstləri."""

#: RİM-in GÜNDƏLİK hesab əməliyyatları. ``user.*`` wildcard-ı QƏSDƏN
#: işlədilmir — o, ``user.grant_privileged``-i də əhatə edərdi
#: (bax permissions.py «users» kateqoriyası).
RIM_ACCOUNT_PERMISSIONS = [
    "user.search",
    "user.credentials",
    "user.block",
    "user.soft_delete",
    "user.edit",
]

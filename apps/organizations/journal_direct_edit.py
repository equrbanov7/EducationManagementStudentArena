"""``journal.direct_edit`` qapısı — RİM əməkdaşı başqa müəllimin jurnalında birbaşa redaktor (sahib 2026-11-12).

Kataloq etiketi və rol şablonu ``permissions_rim_staff.py``-dadır; bu modul açarı YOXLAYAN yerdir
(``registrar.journal_access`` ``organizations.public.journal_direct_edit_key`` vasitəsilə çağırır). Yalnız DƏQİQ
açar sayılır (``*`` / ``journal.*`` yox) — rektor/sədrin ``*`` şablonu jurnal redaktoru olmasın.
"""

PERM_JOURNAL_DIRECT_EDIT = "journal.direct_edit"


def has_direct_edit_key(user, organization) -> bool:
    """Aktorun ``organization``-da AKTİV üzvlüyünün rolunda DƏQİQ ``journal.direct_edit`` varmı (wildcard yox).

    Per-request memo ``user`` obyektində (təşkilat üzrə) — jurnal səhifəsi qapını bir neçə dəfə çağırır.
    """
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return False
    memo = getattr(user, "_journal_direct_edit_memo", None)
    if memo is None:
        memo = {}
        try:
            user._journal_direct_edit_memo = memo
        except AttributeError:  # pragma: no cover — yalnız-oxu proxy
            pass
    key = str(organization.pk)
    if key not in memo:
        from .models import Membership

        memo[key] = any(
            PERM_JOURNAL_DIRECT_EDIT in (permissions or [])
            for permissions in Membership.objects.filter(
                user=user, organization=organization, is_active=True, role__is_active=True
            ).values_list("role__permissions", flat=True)
        )
    return memo[key]


__all__ = ["PERM_JOURNAL_DIRECT_EDIT", "has_direct_edit_key"]

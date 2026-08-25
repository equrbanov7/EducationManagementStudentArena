"""Permission-editor template filter-ləri.

İcazə açarlarının insan-oxunaqlı AZ etiketləri server tərəfdə render olunur ki,
editor-da açar kodu + etiket birlikdə görünsün (məs. «Qrup yaratmaq/idarə etmək
(group.manage)»). Etiket mənbəyi: apps.organizations.permissions.PERMISSION_LABELS
(public fasad üzərindən).
"""

from django import template

from apps.organizations.public import get_permission_label

register = template.Library()


@register.filter(name="permission_label")
def permission_label(permission):
    """İcazənin AZ etiketi; kataloqda etiket yoxdursa boş sətir qaytarır."""
    return get_permission_label(str(permission or ""))

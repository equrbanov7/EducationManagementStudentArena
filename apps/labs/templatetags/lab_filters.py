# from django import template
# import os

# register = template.Library()

# @register.filter
# def get_item(dictionary, key):
#     """Dictionary-dən key ilə dəyər al"""
#     if dictionary is None:
#         return ''
#     if isinstance(dictionary, dict):
#         return dictionary.get(str(key), '')
#     return ''

# @register.filter
# def filename(value):
#     """Fayl yolundan yalnız fayl adını çıxarır"""
#     if value:
#         return os.path.basename(str(value))
#     return ''

"""
labs/templatetags/lab_filters.py
─────────────────────────────────
Custom template filters for labs app.
"""

import os

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag
def lab_crumbs(lab, last_label="", lab_url_name=""):
    """`partials/ems_ui/_content_header.html` üçün çörək qırıntıları: Kurs › Lab [› cari səhifə].

    Şablonda:
        {% trans "Bloklar və suallar" context "..." as crumb_last %}
        {% lab_crumbs lab crumb_last "labs:manage_blocks" as header_crumbs %}

    ``last_label`` boşdursa lab özü cari səhifədir (link olmur); ``lab_url_name`` boşdursa lab
    qırıntısı linksiz qalır.
    """
    crumbs = [
        {
            "label": lab.course.title,
            "url": reverse("courses:course_dashboard", kwargs={"course_id": lab.course_id}),
        },
        {"label": lab.title, "url": reverse(lab_url_name, args=[lab.pk]) if lab_url_name else ""},
    ]
    if last_label:
        crumbs.append({"label": str(last_label), "url": ""})
    return crumbs


@register.filter
def get_item(dictionary, key):
    """
    Dictionary-dən key ilə value almaq üçün custom filter.

    Template-də istifadə:
    {% load lab_filters %}
    {{ student_groups|get_item:student_id }}

    Args:
        dictionary: Dict obyekti
        key: Axtarılan açar

    Returns:
        Value və ya None
    """
    if not dictionary:
        return None

    # Integer key olarsa convert et
    try:
        key = int(key)
    except (ValueError, TypeError):
        pass

    return dictionary.get(key)


@register.filter
def multiply(value, arg):
    """
    İki rəqəmi vurma.

    {{ score|multiply:weight }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def percentage(value, total):
    """
    Faiz hesabla.

    {{ correct_count|percentage:total_count }}
    """
    try:
        if not total or total == 0:
            return 0
        return round((float(value) / float(total)) * 100, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def filename(value):
    """Fayl yolundan yalnız fayl adını çıxarır"""
    if value:
        return os.path.basename(str(value))
    return ""

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

from django import template
import os

register = template.Library()


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
    return ''
from django import template
import os

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Dictionary-dən key ilə dəyər al"""
    if dictionary is None:
        return ''
    if isinstance(dictionary, dict):
        return dictionary.get(str(key), '')
    return ''

@register.filter
def filename(value):
    """Fayl yolundan yalnız fayl adını çıxarır"""
    if value:
        return os.path.basename(str(value))
    return ''
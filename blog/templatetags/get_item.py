from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    if not isinstance(d, dict):
        return None
    return d.get(key)

from django import template

register = template.Library()

@register.filter
def getattr(obj, attr):
    """Dynamic attribute access for templates."""
    try:
        return getattr(obj, attr, '')
    except (AttributeError, TypeError):
        return ''
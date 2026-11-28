from django import template
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator

from ..journal_watch_config import watch_context

register = template.Library()


@register.simple_tag(takes_context=True)
def journal_watch_panel(context):
    request = context["request"]
    try:
        data = watch_context(request)
    except PermissionDenied:
        return {}
    watches = list(data["watches"])
    editing = next((row for row in watches if str(row.pk) == request.GET.get("watch_edit")), None)
    return {
        **data,
        "watches": watches,
        "editing": editing,
        "selected_routes": {r.recipient_id for r in editing.routes.all()} if editing else set(),
        "events": Paginator(data["events"], 25).get_page(request.GET.get("watch_page")),
        "has_access": True,
    }

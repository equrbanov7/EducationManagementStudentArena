"""Retired public media paths must stay closed even on an older static volume."""

from posixpath import normpath

from django.http import HttpResponseNotFound

from whitenoise.middleware import WhiteNoiseMiddleware


class StaticFilesMiddleware(WhiteNoiseMiddleware):
    def __call__(self, request):
        path = request.path_info
        if path.startswith(self.static_prefix) and normpath(path).startswith(self.static_prefix + "accounts/faq/"):
            return HttpResponseNotFound(headers={"Cache-Control": "no-store"})
        return super().__call__(request)

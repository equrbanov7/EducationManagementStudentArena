import pytest


@pytest.fixture(autouse=True)
def _reset_active_language(settings):
    """Test izolyasiyası (2026-09-21, CI shard-ları): LocaleMiddleware sorğu dilini
    thread-də AKTİV qoyur (deaktiv etmir) — `Accept-Language: tr` ilə bir test sonrakı
    testin tərcüməsini dəyişirdi («Fərdi» ≠ «Bireysel»). Hər testdən əvvəl/sonra
    dil standarta qaytarılır."""
    from django.utils import translation

    translation.activate(settings.LANGUAGE_CODE)
    yield
    translation.deactivate()

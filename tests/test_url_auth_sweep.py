"""Birbaşa URL bypass süpürgəsi — autentifikasiya əhatəsi (2026-07-31 auditi).

Nəyi qoruyur
------------
Audit tələbi: «Birbaşa URL bypass-ının qarşısı alınsın». Bunu əl ilə yoxlamaq
mümkün deyil — layihədə yüzlərlə marşrut var və hər yeni `path()` potensial
açıq qapıdır. Bir view-da `@login_required` unudulsa, kod review-da görünmür:
səhifə brauzerdə normal işləyir, çünki developer artıq daxil olub.

Bu test marşrut cədvəlini **avtomatik gəzir** və hər arqumentsiz URL-i
ANONİM olaraq vurur. Cavab 200 olarsa, həmin URL AÇIQ SİYAHIDA olmalıdır.
Yəni yeni açıq səth əlavə etmək **qəsdən** qərar tələb edir: testi düşürür və
adam siyahıya yazmalı olur.

Niyə «200 olmasın» yox, «siyahıda olsun»
----------------------------------------
Sadəcə «heç bir URL 200 verməsin» demək olmazdı — login səhifəsi, sağlamlıq
probu, blog kimi qəsdən açıq səthlər var. Qara siyahı (bunlar açıq olmasın)
yeni marşrutu buraxardı; ağ siyahı buraxmır.
"""

import re

from django.test import Client, TestCase
from django.urls import URLPattern, URLResolver, get_resolver

#: Qəsdən açıq səthlər. Yeni sətir əlavə etmək = «bu, autentifikasiyasız
#: görünə bilər» qərarını sənədləşdirmək.
PUBLIC_ALLOWLIST = {
    # ── Autentifikasiya axını ────────────────────────────────────────────────
    "accounts:login",  # rol seçici (bax [[project_login_portal_split]])
    "accounts:staff_login",  # /accounts/login/muellim/
    "accounts:student_login",  # /accounts/login/telebe/
    "accounts:register",
    "accounts:logout",
    "accounts:password_reset",
    "accounts:password_reset_done",
    "accounts:password_reset_complete",
    # ── İmtahan girişləri: SESSİYA ilə yox, PIN/BİLET ilə qorunur ────────────
    # Bunlar qəsdən anonimdir — tələbə imtahan otağında hesabla deyil, biletlə
    # daxil olur. Qorunma PIN yoxlaması + kompüter/MAC qapısındadır.
    "exams:final_exam_entry",  # /exams/final/
    "liveExam:pin_entry",  # /live/
    # ── Operativ problar (monitorinq autentifikasiyasız vurur) ──────────────
    "ping",
    "health",
    # ── İctimai marketinq/məzmun səthləri ───────────────────────────────────
    "home",
    "about",
    "contact",
    "technology",
    "subscribe",  # blog abunəsi — rate-limit ilə qorunur
    "robots_txt",
    "sitemap_xml",
    "site_webmanifest",
    "google_site_verification",
}

#: Bu prefikslər süpürgəyə düşmür.
SKIP_PREFIXES = ("admin:", "django", "javascript-catalog", "jsi18n", "set_language")

#: Arqumentli marşrutlar bu süpürgədən kənardadır: uydurma ID ilə vurmaq
#: 404 verir və 404 «qorunur» demək deyil. Obyekt səviyyəli əhatə ayrıca
#: testlərdədir (tenant izolyasiyası, view-as LIMITED).
_HAS_ARG = re.compile(r"<[^>]+>|\(\?P<")


def _walk(patterns, prefix="", namespace=""):
    """Marşrut ağacını gəz və `(ad, yol)` cütləri qaytar."""
    for entry in patterns:
        if isinstance(entry, URLResolver):
            ns = entry.namespace or namespace
            new_prefix = prefix + str(entry.pattern)
            yield from _walk(entry.url_patterns, new_prefix, ns)
        elif isinstance(entry, URLPattern):
            route = prefix + str(entry.pattern)
            if not entry.name:
                continue
            name = f"{namespace}:{entry.name}" if namespace else entry.name
            yield name, route


def _collect_argless_routes():
    routes = {}
    for name, route in _walk(get_resolver().url_patterns):
        if name.startswith(SKIP_PREFIXES):
            continue
        if _HAS_ARG.search(route):
            continue
        routes.setdefault(name, "/" + route.lstrip("/"))
    return routes


class AnonymousUrlSweepTest(TestCase):
    """Anonim istifadəçi qorunan səthlərdən 200 ala bilməz."""

    def test_no_unlisted_surface_answers_anonymous_requests(self):
        client = Client()
        leaked = []

        for name, url in sorted(_collect_argless_routes().items()):
            if name in PUBLIC_ALLOWLIST:
                continue
            try:
                response = client.get(url)
            except Exception:
                # View arqument/konfiqurasiya səbəbindən qalxa bilər — bu,
                # autentifikasiya boşluğu deyil, ona görə süpürgəni kəsmirik.
                continue
            if response.status_code == 200:
                leaked.append(f"  {name:<50} {url}")

        self.assertFalse(
            leaked,
            "Aşağıdakı marşrutlar ANONİM sorğuya 200 qaytardı. Ya autentifikasiya "
            "əlavə edin, ya da qəsdən açıqdırsa PUBLIC_ALLOWLIST-ə yazın:\n" + "\n".join(leaked),
        )

    def test_the_sweep_actually_covers_something(self):
        """Süpürgənin özü boşa düşməsin.

        Marşrut gəzintisi sınsa (Django daxili API dəyişsə) test səssizcə
        «heç nə tapmadım → keçdi» deyərdi. Bu, ən pis nəticədir: qapı yoxdur,
        amma varmış kimi görünür.
        """
        routes = _collect_argless_routes()
        self.assertGreater(len(routes), 30, f"süpürgə yalnız {len(routes)} marşrut tapdı — gəzinti sınıb")

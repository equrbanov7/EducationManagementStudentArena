/* language_switcher.js — dil seçici (`partials/_language_switcher.html`).
 * Mənbə: həmin partial-ın inline nonce script-i, 2026-09-21-də xarici fayla
 * çıxarıldı (CSP `script-src` yalnız SELF + NONCE).
 *
 * Partial səhifədə bir neçə dəfə (navbar, mobil, sidebar, üzən) include olunur;
 * `<script src>` hər dəfə dropdown-un DƏRHAL ARDINCA qoyulur və klassik
 * (defer-siz) skript olduğu üçün `document.currentScript.previousElementSibling`
 * öz dropdown-unu tapır — inline variantla eyni semantika. Hər instansiya yalnız
 * öz `.language-switcher`-ini bağlayır; `next` gizli sahələri cari URL-ə
 * (profil bölməsi `?section=` daxil) sinxronlanır.
 */
(function () {
    'use strict';
    var s = document.currentScript;
    if (!s) { return; }
    var dd = s.previousElementSibling;
    if (!dd || !dd.classList.contains('language-switcher')) { return; }

    function currentRelativeUrl() {
        try {
            var currentUrl = new URL(window.location.href);
            var activeProfileLink = document.querySelector('.profile-sidebar .js-profile-section-link.active[data-section]');
            if (activeProfileLink) {
                var activeHref = activeProfileLink.getAttribute('href') || '';
                if (activeHref) {
                    var activeUrl = new URL(activeHref, window.location.origin);
                    if (currentUrl.pathname === activeUrl.pathname) {
                        var activeSection = activeUrl.searchParams.get('section') || activeProfileLink.getAttribute('data-section');
                        if (activeSection) {
                            currentUrl.searchParams.set('section', activeSection);
                        }
                    }
                }
            }
            return currentUrl.pathname + currentUrl.search + currentUrl.hash;
        } catch (err) {
            return window.location.pathname + window.location.search + window.location.hash;
        }
    }

    function syncNextInputs() {
        var href = currentRelativeUrl();
        dd.querySelectorAll('.language-switcher__form input[name="next"]').forEach(function (inp) {
            inp.value = href;
        });
    }

    syncNextInputs();
    dd.addEventListener('show.bs.dropdown', syncNextInputs);
    dd.addEventListener('shown.bs.dropdown', syncNextInputs);
    dd.addEventListener('click', syncNextInputs);
    window.addEventListener('hashchange', syncNextInputs);
    window.addEventListener('popstate', syncNextInputs);
    window.addEventListener('pageshow', syncNextInputs);
    dd.querySelectorAll('.language-switcher__form').forEach(function (form) {
        form.addEventListener('submit', syncNextInputs);
    });
})();

/* Kabinet bölmə asset yükləyicisi — `window.EMSSectionAssets.ensure(assets)` (perf 2026-10-07).
 *
 * Qabıq ilk açılışda YALNIZ render olunan bölmənin CSS/JS-ini verir
 * (`apps/accounts/views/profile/section_assets.py`). AJAX keçidində fraqment cavabı
 * `assets: {css: [{href, order}], js: [src, …]}` qaytarır; `section_loader.js` paneli
 * swap etməzdən ƏVVƏL bu funksiyanı gözləyir:
 *
 *   • CSS: səhifədə olmayan link `<head>`-ə `data-ems-css-order` sırasına görə
 *     (`_section_assets.html`-dəki kaskad mövqeyi) qoşulur və YÜKLƏNƏNƏ qədər gözlənilir
 *     — üslubsuz panel yanıb-sönmür (FOUC). Xəta / 8 s → davam edir.
 *   • JS: səhifədə olmayan `src` `async=false` ilə ardıcıl (şablon sırası) və YALNIZ BİR
 *     DƏFƏ qoşulur; panel swap-dan sonra gələn `profile:section:loaded` bölmə init-ini
 *     işə salır (köhnə AJAX semantikası ilə eyni: skript panel gəlməmiş icra olunur).
 *
 * CSP: yalnız same-origin `link`/`script src` (`'self'`) — inline kod yoxdur.
 * Eyni URL üçün paralel çağırışlar eyni Promise-i bölüşür (iki dəfə yüklənmir).
 */
(function (window, document) {
    "use strict";

    var CSS_TIMEOUT_MS = 8000;
    var JS_TIMEOUT_MS = 20000;
    var pending = Object.create(null);

    function absolute(url) {
        try {
            return new URL(url, window.location.href).href;
        } catch (e) {
            return String(url || "");
        }
    }

    function findLoaded(selector, prop, url) {
        var target = absolute(url);
        var nodes = document.querySelectorAll(selector);
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i][prop] === target) {
                return nodes[i];
            }
        }
        return null;
    }

    function settle(node, timeoutMs) {
        return new Promise(function (resolve) {
            var done = false;
            var timer = null;
            function finish() {
                if (!done) {
                    done = true;
                    if (timer !== null) {
                        window.clearTimeout(timer);
                    }
                    resolve();
                }
            }
            node.addEventListener("load", finish);
            node.addEventListener("error", finish);
            timer = window.setTimeout(finish, timeoutMs);
        });
    }

    function placeStylesheet(link, order) {
        var head = document.head || document.getElementsByTagName("head")[0];
        var ordered = head.querySelectorAll("link[data-ems-css-order]");
        var last = null;
        for (var i = 0; i < ordered.length; i++) {
            if (Number(ordered[i].getAttribute("data-ems-css-order")) > order) {
                head.insertBefore(link, ordered[i]);
                return;
            }
            last = ordered[i];
        }
        if (last && last.parentNode) {
            last.parentNode.insertBefore(link, last.nextSibling);
        } else {
            head.appendChild(link);
        }
    }

    function ensureStylesheet(entry) {
        var href = typeof entry === "string" ? entry : entry && entry.href;
        if (!href) {
            return null;
        }
        var key = "css|" + absolute(href);
        if (pending[key]) {
            return pending[key];
        }
        if (findLoaded('link[rel="stylesheet"][href]', "href", href)) {
            return null;
        }
        var order = Number(entry && entry.order);
        if (!isFinite(order)) {
            order = 100000;
        }
        var link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = href;
        link.setAttribute("data-ems-css-order", String(order));
        pending[key] = settle(link, CSS_TIMEOUT_MS);
        placeStylesheet(link, order);
        return pending[key];
    }

    function ensureScript(src) {
        if (!src) {
            return null;
        }
        var key = "js|" + absolute(src);
        if (pending[key]) {
            return pending[key];
        }
        if (findLoaded("script[src]", "src", src)) {
            return null;
        }
        var script = document.createElement("script");
        script.src = src;
        script.async = false; // dinamik skriptlər defolt async-dir — sıra saxlanılsın
        script.setAttribute("data-ems-section-js", "1");
        pending[key] = settle(script, JS_TIMEOUT_MS);
        (document.body || document.documentElement).appendChild(script);
        return pending[key];
    }

    function ensure(assets) {
        if (!assets || typeof Promise !== "function") {
            return Promise.resolve();
        }
        var waits = [];
        (Array.isArray(assets.css) ? assets.css : []).forEach(function (entry) {
            var wait = ensureStylesheet(entry);
            if (wait) {
                waits.push(wait);
            }
        });
        (Array.isArray(assets.js) ? assets.js : []).forEach(function (src) {
            var wait = ensureScript(src);
            if (wait) {
                waits.push(wait);
            }
        });
        return Promise.all(waits).then(function () { return true; });
    }

    window.EMSSectionAssets = { ensure: ensure };
})(window, document);

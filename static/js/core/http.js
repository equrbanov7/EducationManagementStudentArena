/**
 * EMSCore.fetchJSON — layihə üçün standart fetch sarğısı (Faza 6.3).
 * ─────────────────────────────────────────────────────────────────────
 * YENİ kod fetch() əvəzinə bundan istifadə etməlidir (köhnə ~70 çağırış
 * tədricən miqrasiya olunur — docs/frontend/AJAX_SAFE_JS_PATTERN.md).
 *
 * Verir: CSRF başlığı (unsafe metodlarda avtomatik), X-Requested-With,
 * JSON body (options.data) + JSON parse, same-origin credentials,
 * normallaşdırılmış xəta (error.status / error.payload), AbortSignal dəstəyi.
 *
 * İstifadə:
 *   EMSCore.fetchJSON(url)                              // GET
 *   EMSCore.fetchJSON(url, { method: "POST", data: {...} })
 *     .then(function (payload) { ... })
 *     .catch(function (err) { err.status; err.payload; });
 */
(function (window) {
    "use strict";

    var EMSCore = (window.EMSCore = window.EMSCore || {});
    var UNSAFE_METHOD = /^(POST|PUT|PATCH|DELETE)$/i;

    EMSCore.fetchJSON = function fetchJSON(url, options) {
        options = options || {};
        var method = (options.method || "GET").toUpperCase();
        var headers = Object.assign(
            { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
            options.headers || {}
        );
        var body = options.body;
        if (options.data !== undefined && body === undefined) {
            headers["Content-Type"] = headers["Content-Type"] || "application/json";
            body = JSON.stringify(options.data);
        }
        if (UNSAFE_METHOD.test(method) && !headers["X-CSRFToken"]) {
            headers["X-CSRFToken"] = EMSCore.getCsrfToken() || "";
        }
        return window
            .fetch(url, {
                method: method,
                headers: headers,
                body: body,
                credentials: "same-origin",
                signal: options.signal,
            })
            .then(function (response) {
                return response.text().then(function (text) {
                    var payload = null;
                    if (text) {
                        try {
                            payload = JSON.parse(text);
                        } catch (parseError) {
                            payload = text;
                        }
                    }
                    if (!response.ok) {
                        var error = new Error("HTTP " + response.status + " — " + url);
                        error.status = response.status;
                        error.payload = payload;
                        error.response = response;
                        throw error;
                    }
                    return payload;
                });
            });
    };
})(window);

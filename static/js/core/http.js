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

    function notifyViewAsBlocked(detail) {
        var text = detail || "";
        if (!text) { return; }
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(text, "warning");
            return;
        }
        // Toast qatı hələ yüklənməyibsə səbəb yenə də itməməlidir.
        if (window.console && window.console.warn) { window.console.warn(text); }
    }

    function retryWithFreshToken(url, options) {
        var session = window.EMSSession;
        if (!session || typeof session.refreshToken !== "function") return null;
        return session.refreshToken().then(function (token) {
            token = token || EMSCore.getCsrfToken() || "";
            var body = options.body;
            // Gövdədəki `csrfmiddlewaretoken` başlıqdan ÜSTÜNDÜR (Django əvvəl POST sahəsinə baxır) — onu da yenilə.
            if (body && typeof body.set === "function" && typeof body.has === "function" && body.has("csrfmiddlewaretoken")) {
                body.set("csrfmiddlewaretoken", token);
            }
            var headers = Object.assign({}, options.headers || {}, { "X-CSRFToken": token });
            return EMSCore.fetchJSON(url, Object.assign({}, options, { headers: headers, body: body, _csrfRetried: true }));
        });
    }

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
                        // «Başqasının adından» rejimində bloklanan yazma: server
                        // 403 + {view_as_blocked:true} qaytarır. Hər çağırış yeri
                        // bunu ayrıca tutmadığı üçün istifadəçi səbəbi görmür və
                        // «məni jurnaldan atdı» hissi yaranır (sahib şikayəti
                        // 2026-09-06) — səbəbi MƏRKƏZDƏ bir dəfə göstəririk.
                        if (response.status === 403 && payload && payload.view_as_blocked) {
                            notifyViewAsBlocked(payload.detail);
                        }
                        // Sahib 2026-10-27: köhnəlmiş CSRF tokeni — təzə tokenlə BİR dəfə avtomatik təkrar
                        // (istifadəçi «səhifəni yeniləyin» görmür). Bitmiş sessiya — lokallaşdırılmış pəncərə
                        // (core/session_keepalive.js). Hər iki halda çağıran yenə xətanı alır.
                        if (response.status === 403 && payload && payload.csrf_failed && !options._csrfRetried) {
                            var retry = retryWithFreshToken(url, options);
                            if (retry) return retry;
                        }
                        if (response.status === 401 && payload && payload.session_expired && window.EMSSession) {
                            window.EMSSession.expired(payload.message);
                        }
                        throw error;
                    }
                    return payload;
                });
            });
    };
})(window);

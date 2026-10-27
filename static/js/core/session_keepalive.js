/**
 * EMSSession — açıq səhifənin sessiya pingi, CSRF tokeninin yenilənməsi və «sessiya başa çatdı» pəncərəsi.
 * ─────────────────────────────────────────────────────────────────────────────────────────────────────
 * Sahib 2026-10-27: «uzun açıq qalan səhifədə “səhifəni yeniləyin” çıxır (həm də ingiliscə)», «brauzer
 * bağlananda / kompüter sönəndə çıxış olsun». Markup + mətnlər: templates/partials/_session_keepalive.html.
 *
 * AXIN
 * * Hər `data-heartbeat` saniyədən bir GET `data-ping-url?active=0|1`. `active=1` — son pingdən bəri klik /
 *   yazı / sürüşdürmə olub (server fəaliyyətsizlik limitini uzadır); `active=0` yalnız «brauzer açıqdır».
 * * Cavabdakı TƏZƏ CSRF tokeni səhifədəki bütün `csrfmiddlewaretoken` sahələrinə və `meta[name=csrf-token]`-ə
 *   yazılır — başqa tabda yenidən daxil olandan sonra köhnə tabın formaları «Səhifə köhnəlib» vermir.
 * * Kompüter yuxudan oyananda (taymer boşluğu), tab görünəndə, şəbəkə qayıdanda — dərhal ping.
 * * Sessiya bitibsə (401 `session_expired` və ya `authenticated:false`) — lokallaşdırılmış pəncərə; sonrakı POST
 *   formaları göndərilmir (məlumat itməsin), pəncərə yenidən açılır. Brauzer uzun yatıbsa POST-dan ƏVVƏL ping.
 * * `EMSCore.fetchJSON` (core/http.js) 403 `csrf_failed` alanda `EMSSession.refreshToken()` ilə BİR dəfə
 *   təkrar edir, 401 `session_expired` alanda `EMSSession.expired()` çağırır.
 * CSP: inline yoxdur; mətnlər data-atributlardadır. Bir dəfə yüklənir (base.html), AJAX swap-dan asılı deyil.
 */
(function (window, document) {
    "use strict";

    if (window.EMSSession) return;
    var root = document.querySelector("[data-ems-session]");
    if (!root || !window.fetch) return;

    var pingUrl = root.getAttribute("data-ping-url") || "";
    var loginUrl = root.getAttribute("data-login-url") || "/accounts/login/";
    var heartbeatMs = Math.max(30, parseInt(root.getAttribute("data-heartbeat") || "600", 10) || 600) * 1000;
    var presenceMs = Math.max(0, parseInt(root.getAttribute("data-presence") || "0", 10) || 0) * 1000;
    var TICK_MS = 30000;
    var MIN_PING_GAP_MS = 45000;

    var state = { active: false, expired: false, lastOk: Date.now(), lastPing: 0, lastTick: Date.now(), inflight: null };

    // ── Fəaliyyət ─────────────────────────────────────────────────────────────
    function markActive() {
        state.active = true;
    }
    ["pointerdown", "keydown", "input", "wheel", "touchstart"].forEach(function (type) {
        document.addEventListener(type, markActive, { capture: true, passive: true });
    });
    var lastMove = 0;
    document.addEventListener(
        "mousemove",
        function () {
            var now = Date.now();
            if (now - lastMove > 5000) {
                lastMove = now;
                markActive();
            }
        },
        { passive: true }
    );

    // ── Token ─────────────────────────────────────────────────────────────────
    function applyToken(token) {
        if (!token) return;
        Array.prototype.forEach.call(document.querySelectorAll("input[name='csrfmiddlewaretoken']"), function (input) {
            input.value = token;
        });
        var meta = document.querySelector("meta[name='csrf-token']");
        if (meta) meta.setAttribute("content", token);
    }

    // ── Pəncərə ───────────────────────────────────────────────────────────────
    function nextUrl() {
        return window.location.pathname + window.location.search;
    }

    function showDialog(message) {
        var text = root.querySelector("[data-ems-session-text]");
        if (text) text.textContent = message || root.getAttribute("data-msg-expired") || "";
        var login = root.querySelector("[data-ems-session-login]");
        if (login) login.setAttribute("href", loginUrl + (loginUrl.indexOf("?") === -1 ? "?" : "&") + "next=" + encodeURIComponent(nextUrl()));
        root.hidden = false;
        document.documentElement.classList.add("ems-session-locked");
        if (login && typeof login.focus === "function") login.focus({ preventScroll: true });
    }

    function hideDialog() {
        root.hidden = true;
        document.documentElement.classList.remove("ems-session-locked");
    }

    function expired(message) {
        state.expired = true;
        showDialog(message);
        try {
            document.dispatchEvent(new CustomEvent("ems:session-expired", { detail: { message: message || "" } }));
        } catch (err) {
            /* köhnə brauzer — hadisəsiz davam */
        }
    }

    root.addEventListener("click", function (event) {
        if (event.target.closest("[data-ems-session-stay]")) hideDialog();
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !root.hidden) hideDialog();
    });

    // ── Ping ──────────────────────────────────────────────────────────────────
    function ping(force) {
        if (state.expired) return Promise.resolve(null);
        if (state.inflight) return state.inflight;
        var now = Date.now();
        if (!force && now - state.lastPing < MIN_PING_GAP_MS) return Promise.resolve(null);
        state.lastPing = now;
        var wasActive = state.active;
        state.active = false;
        var url = pingUrl + (pingUrl.indexOf("?") === -1 ? "?" : "&") + "active=" + (wasActive ? "1" : "0");
        state.inflight = window
            .fetch(url, {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
                headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
            })
            .then(function (response) {
                // Giriş qapıları (ilk giriş, profil tamamlama…) yönləndirir — sessiya var, sadəcə keç.
                if (response.redirected) return null;
                return response
                    .json()
                    .catch(function () {
                        return null;
                    })
                    .then(function (payload) {
                        if (response.status === 401 || (payload && payload.authenticated === false)) {
                            expired(payload && payload.message);
                            return null;
                        }
                        if (!response.ok || !payload) return null;
                        state.lastOk = Date.now();
                        applyToken(payload.csrf_token);
                        return payload;
                    });
            })
            .catch(function () {
                if (wasActive) state.active = true; // şəbəkə yoxdur — fəaliyyət növbəti pingə qalsın
                return null;
            })
            .then(function (payload) {
                state.inflight = null;
                return payload;
            });
        return state.inflight;
    }

    function refreshToken() {
        return ping(true).then(function (payload) {
            return payload && payload.csrf_token ? payload.csrf_token : null;
        });
    }

    function tick() {
        var now = Date.now();
        var slept = now - state.lastTick > TICK_MS * 3; // taymer gecikib — kompüter yuxudan oyanıb
        state.lastTick = now;
        if (slept || now - state.lastPing >= heartbeatMs) ping(slept);
    }
    window.setInterval(tick, TICK_MS);
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible") ping(false);
    });
    window.addEventListener("online", function () {
        ping(true);
    });
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) ping(true); // bfcache-dən qayıdış: köhnə token / bitmiş sessiya
    });

    // ── POST formaları: bitmiş sessiyada məlumat itməsin ──────────────────────
    var RESUBMIT = "emsSessionChecked";
    document.addEventListener(
        "submit",
        function (event) {
            var form = event.target;
            if (!form || (form.method || "").toLowerCase() !== "post" || form.hasAttribute("data-ems-session-skip")) return;
            if (/\/logout\/?$/.test(form.getAttribute("action") || "")) return;
            if (form.dataset[RESUBMIT] === "1") {
                delete form.dataset[RESUBMIT];
                return;
            }
            if (state.expired) {
                event.preventDefault();
                event.stopImmediatePropagation();
                showDialog();
                return;
            }
            var stale = presenceMs && Date.now() - state.lastOk > presenceMs / 2;
            if (!stale) return;
            // Uzun fasilə (yuxu rejimi): əvvəl sessiyanı yoxla + tokeni yenilə, sonra eyni formanı göndər.
            event.preventDefault();
            event.stopImmediatePropagation();
            var submitter = event.submitter || null;
            ping(true).then(function () {
                if (state.expired) return; // pəncərə açıqdır; forma məlumatı səhifədə qalır
                form.dataset[RESUBMIT] = "1";
                if (typeof form.requestSubmit === "function") form.requestSubmit(submitter || undefined);
                else form.submit();
            });
        },
        true
    );

    window.EMSSession = {
        ping: ping,
        refreshToken: refreshToken,
        expired: expired,
        isExpired: function () {
            return state.expired;
        },
    };
})(window, document);

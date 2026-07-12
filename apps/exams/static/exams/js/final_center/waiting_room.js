/**
 * Final imtahan gözləmə otağı.
 *
 * - WebSocket əsas kanaldır (yüksək tezlikli polling YOXDUR).
 * - Reconnect: eksponensial backoff + jitter.
 * - Heartbeat: konfiqurasiyalı interval (server presence TTL-i ilə uyğun).
 * - "room_started" gələndə hər müştəri KİÇİK təsadüfi gecikmə ilə begin
 *   endpoint-inə POST edir — start anında server yükü yayılır.
 * - WS uzun müddət qopuq qalsa, aşağı tezlikli fallback poll (state URL).
 */
(function () {
    "use strict";

    var root = document.getElementById("fexc-waiting-root");
    if (!root) return;

    var wsPath = root.dataset.wsPath;
    var stateUrl = root.dataset.stateUrl;
    var beginUrl = root.dataset.beginUrl;
    var heartbeatMs = (parseInt(root.dataset.heartbeatSeconds, 10) || 30) * 1000;
    var sessionAlreadyActive = root.dataset.sessionActive === "1";

    var connEl = document.getElementById("fexc-conn-state");
    var msgEl = document.getElementById("fexc-wait-message");
    var checkEl = document.getElementById("fexc-check-count");
    var manualStartBtn = document.getElementById("fexc-manual-start");

    var socket = null;
    var heartbeatTimer = null;
    var fallbackTimer = null;
    var reconnectAttempt = 0;
    var beginRequested = false;
    var finished = false;
    var checkCount = 0;

    var FALLBACK_POLL_MS = 30000; // yalnız WS qopuq olanda
    var MAX_RECONNECT_DELAY_MS = 30000;
    // Start "thundering herd"-ını yaymaq üçün kiçik jitter. Server tərəfdə
    // onsuz da concurrency semaforu + növbə var (EXAM_START_GLOBAL_CONCURRENCY),
    // ona görə 2.5s həddindən çox idi — proktor "başlat"a basanda tələbə
    // gözləyirdi. 700ms həm axını yayır, həm dərhal hiss olunur.
    var BEGIN_JITTER_MS = 700;

    function getCsrfToken() {
        var input = root.querySelector("input[name=csrfmiddlewaretoken]");
        if (input) return input.value;
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function setConn(state, label) {
        if (!connEl) return;
        connEl.dataset.state = state;
        connEl.textContent = label;
    }

    function setMessage(text) {
        if (msgEl) msgEl.textContent = text;
    }

    function bumpChecks() {
        checkCount += 1;
        if (checkEl) checkEl.textContent = String(checkCount);
    }

    var i18n = {
        connected: connEl ? connEl.dataset.labelConnected || "Bağlantı quruldu" : "",
        reconnecting: "Yenidən qoşulur…",
        offline: "Bağlantı yoxdur — fallback rejimi",
        starting: "İmtahan başlayır — yönləndirilirsiniz…",
        ended: "Oturum bitdi. Nəzarətçiyə müraciət edin.",
        removed: "İmtahandan çıxarıldınız. Nəzarətçiyə müraciət edin.",
        cancelled: "Oturum ləğv edildi."
    };

    function showManualStart() {
        // İmtahan başlayıb: əl ilə başlatma düyməsini göstər (avtomatik keçid
        // hər hansı səbəbdən alınmasa tələbə həmin kompüterdə yenidən cəhd etsin).
        if (manualStartBtn) manualStartBtn.hidden = finished;
    }

    function scheduleBegin() {
        showManualStart();
        if (beginRequested || finished) return;
        beginRequested = true;
        setMessage(i18n.starting);
        var jitter = Math.floor(Math.random() * BEGIN_JITTER_MS);
        window.setTimeout(function () { requestBegin(); }, jitter);
    }

    if (manualStartBtn) {
        manualStartBtn.addEventListener("click", function () {
            // Əl ilə cəhd: davam edən avtomatik cəhdi sıfırla və yenidən başlat.
            beginRequested = true;
            setMessage(i18n.starting);
            requestBegin();
        });
    }

    function requestBegin(retryCount) {
        retryCount = retryCount || 0;
        fetch(beginUrl, {
            method: "POST",
            headers: { "X-CSRFToken": getCsrfToken(), "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin"
        })
            .then(function (resp) { return resp.json().then(function (d) { return { ok: resp.ok, data: d }; }); })
            .then(function (result) {
                if (result.ok && result.data.success && result.data.redirect_url) {
                    finished = true;
                    window.location.assign(result.data.redirect_url);
                    return;
                }
                // 409 — oturum hələ aktiv deyil / bilet vəziyyəti dəyişib.
                if (retryCount < 3) {
                    window.setTimeout(function () { requestBegin(retryCount + 1); }, 2000 * (retryCount + 1));
                } else {
                    beginRequested = false;
                    showManualStart();
                }
            })
            .catch(function () {
                if (retryCount < 5) {
                    window.setTimeout(function () { requestBegin(retryCount + 1); }, 3000 * (retryCount + 1));
                } else {
                    beginRequested = false;
                    showManualStart();
                }
            });
    }

    function handleEvent(data) {
        if (!data || !data.event) return;
        switch (data.event) {
            case "room_started":
                scheduleBegin();
                break;
            case "room_ended":
                finished = true;
                setMessage(i18n.ended);
                break;
            case "session_cancelled":
                finished = true;
                setMessage(i18n.cancelled);
                break;
            case "removed":
                finished = true;
                setMessage(i18n.removed);
                break;
            default:
                break;
        }
    }

    function startHeartbeat() {
        stopHeartbeat();
        heartbeatTimer = window.setInterval(function () {
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ action: "heartbeat" }));
                bumpChecks();
            }
        }, heartbeatMs);
    }

    function stopHeartbeat() {
        if (heartbeatTimer) {
            window.clearInterval(heartbeatTimer);
            heartbeatTimer = null;
        }
    }

    function startFallbackPolling() {
        if (fallbackTimer || finished) return;
        fallbackTimer = window.setInterval(function () {
            fetch(stateUrl, { credentials: "same-origin" })
                .then(function (resp) { return resp.json(); })
                .then(function (data) {
                    bumpChecks();
                    if (data.session_state === "active") scheduleBegin();
                    if (data.session_state === "ended" || data.session_state === "cancelled") {
                        finished = true;
                        setMessage(data.session_state === "ended" ? i18n.ended : i18n.cancelled);
                        stopFallbackPolling();
                    }
                    if (data.ticket_status === "removed") {
                        finished = true;
                        setMessage(i18n.removed);
                        stopFallbackPolling();
                    }
                })
                .catch(function () { /* növbəti tsikldə yenidən */ });
        }, FALLBACK_POLL_MS);
    }

    function stopFallbackPolling() {
        if (fallbackTimer) {
            window.clearInterval(fallbackTimer);
            fallbackTimer = null;
        }
    }

    function connect() {
        if (finished) return;
        var scheme = window.location.protocol === "https:" ? "wss" : "ws";
        socket = new WebSocket(scheme + "://" + window.location.host + wsPath);

        socket.onopen = function () {
            reconnectAttempt = 0;
            setConn("online", i18n.connected);
            stopFallbackPolling();
            startHeartbeat();
            bumpChecks();
        };

        socket.onmessage = function (evt) {
            var data;
            try { data = JSON.parse(evt.data); } catch (err) { return; }
            handleEvent(data);
        };

        socket.onclose = function () {
            stopHeartbeat();
            if (finished) return;
            setConn("offline", i18n.reconnecting);
            reconnectAttempt += 1;
            // Backoff + jitter: 1s, 2s, 4s… max 30s; server eyni anda minlərlə
            // reconnect almasın deyə hər müştəri fərqli gecikmə alır.
            var base = Math.min(1000 * Math.pow(2, reconnectAttempt - 1), MAX_RECONNECT_DELAY_MS);
            var delay = base / 2 + Math.random() * (base / 2);
            window.setTimeout(connect, delay);
            if (reconnectAttempt >= 3) {
                setConn("offline", i18n.offline);
                startFallbackPolling();
            }
        };

        socket.onerror = function () {
            try { socket.close(); } catch (err) { /* noop */ }
        };
    }

    var cancelForm = document.querySelector(".fexc-cancel-form");
    if (cancelForm) {
        cancelForm.addEventListener("submit", function (evt) {
            var confirmText = cancelForm.dataset.confirm;
            if (confirmText && !window.confirm(confirmText)) {
                evt.preventDefault();
                return;
            }
            finished = true;
        });
    }

    if (sessionAlreadyActive) {
        // Oturum artıq başlayıb (gec giriş / yenidən qoşulma) — dərhal başla.
        scheduleBegin();
    }

    connect();
})();

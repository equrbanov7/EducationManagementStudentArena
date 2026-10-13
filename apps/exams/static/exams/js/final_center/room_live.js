/**
 * Zal monitorunun canlı nəqliyyatı + əlavə qatları (2026-10-13, gecə).
 *
 * `room_aggregate.js` render edir; bu fayl ONA XİDMƏT edir (window.FXCRoomLive):
 *
 *  1. Polling — sabit 10 s əvəzinə:
 *     · tab gizlidirsə DAYANIR, görünən kimi dərhal yenilənir (planşet batareyası/server);
 *     · eyni anda bir sorğu (in-flight guard), xətada geri çəkilmə 10→20→40→60 s;
 *     · `If-None-Match` → 304 olarsa JSON parse/render YOXDUR (300 hücrəli xəritə hər
 *       dəfə yenidən çəkilmir);
 *     · 403 → nəzarət növbəsi bitib: polling dayanır, aydın bildiriş göstərilir;
 *     · 429 → `Retry-After` qədər gözləyir.
 *  2. Hücrə əlavələri — qalan vaxt (server saatı ilə, `deadline_at`) və irəliləyiş
 *     (`answered`/`question_total`); dəqiqədə bir yerində yenilənir (yenidən render yox).
 *  3. Yeni «şübhəli» tələbə xəbərdarlığı — aria-live elan + başlıqda (!) nişanı.
 *  4. Pozuntu modalında nəzarətçi QEYDİ forması (POST, CSRF; server zal skopunu yoxlayır).
 *
 * Markup müqaviləsi: `#fxc-room-root[data-snapshot-url][data-snapshot-etag]
 * [data-note-url-template][data-rooms-url]`, `#fxc-room-alert`, `#fxc-room-expired`,
 * etiketlər `#fxc-room-live-i18n` JSON blokunda. AJAX-safe: `EMSReady` + idempotent.
 */
(function () {
    "use strict";

    var BASE_MS = 10000;
    var MAX_BACKOFF_MS = 60000;
    var L = {};

    function lbl(key, fallback) { return L[key] || fallback; }

    function esc(text) {
        var d = document.createElement("div");
        d.textContent = text == null ? "" : String(text);
        return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function csrf() {
        if (window.EMSCore && typeof window.EMSCore.getCookie === "function") {
            return window.EMSCore.getCookie("csrftoken") || "";
        }
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : "";
    }

    // ── Server saatı ilə «qalan vaxt» ─────────────────────────────────────────
    var clockSkewMs = 0;
    function syncClock(snapshot) {
        var t = snapshot && Date.parse(snapshot.server_now);
        if (t) clockSkewMs = t - Date.now();
    }
    function remainingLabel(deadlineIso) {
        var end = Date.parse(deadlineIso || "");
        if (!end) return "";
        var sec = Math.max(0, Math.round((end - (Date.now() + clockSkewMs)) / 1000));
        var min = Math.floor(sec / 60);
        if (min >= 60) return Math.floor(min / 60) + lbl("h", "s") + " " + (min % 60) + lbl("m", "dəq");
        if (min >= 1) return min + " " + lbl("m", "dəq");
        return sec + " " + lbl("s", "san");
    }

    function cellMetaHtml(row) {
        var parts = [];
        if (row.status === "active" && row.deadline_at) {
            parts.push('<span class="fxc-cell-time" data-deadline="' + esc(row.deadline_at) + '">' +
                esc(remainingLabel(row.deadline_at)) + "</span>");
        }
        if (row.status === "active" && row.question_total) {
            parts.push('<span class="fxc-cell-prog">' + esc(row.answered || 0) + "/" + esc(row.question_total) + "</span>");
        }
        return parts.length ? '<span class="fxc-cell-meta">' + parts.join(" · ") + "</span>" : "";
    }

    /** room_aggregate.renderMap-dan sonra çağırılır: hücrələrə vaxt/irəliləyiş əlavə edir. */
    function decorate(mapEl, snapshot) {
        if (!mapEl || !snapshot) return;
        syncClock(snapshot);
        var byAttempt = {};
        (snapshot.students || []).forEach(function (row) { if (row.attempt_id) byAttempt[row.attempt_id] = row; });
        Array.prototype.forEach.call(mapEl.querySelectorAll(".fxc-cell[data-attempt]"), function (cell) {
            var row = byAttempt[cell.dataset.attempt];
            if (!row || cell.querySelector(".fxc-cell-meta")) return;
            var html = cellMetaHtml(row);
            if (html) cell.insertAdjacentHTML("beforeend", html);
            if (row.status === "active" && row.deadline_at) {
                cell.setAttribute("title", (cell.getAttribute("title") || "") + " · " +
                    lbl("left", "Qalan vaxt") + ": " + remainingLabel(row.deadline_at));
            }
        });
    }

    function tickTimes() {
        Array.prototype.forEach.call(document.querySelectorAll(".fxc-cell-time[data-deadline]"), function (el) {
            el.textContent = remainingLabel(el.dataset.deadline);
        });
    }

    // ── Yeni şübhəli xəbərdarlığı ────────────────────────────────────────────
    var knownFlagged = null;
    var baseTitle = document.title;
    function announceFlags(snapshot) {
        var flagged = {};
        var fresh = [];
        (snapshot.students || []).forEach(function (row) {
            if (!row.flagged || !row.attempt_id) return;
            flagged[row.attempt_id] = true;
            if (knownFlagged && !knownFlagged[row.attempt_id]) fresh.push(row);
        });
        knownFlagged = flagged;
        var count = Object.keys(flagged).length;
        document.title = (count ? "(" + count + "!) " : "") + baseTitle;
        var box = document.getElementById("fxc-room-alert");
        if (!box || !fresh.length) return;
        box.hidden = false;
        box.innerHTML = '<i class="fas fa-flag" aria-hidden="true"></i> ' + esc(lbl("newFlagged", "Yeni şübhəli")) + ": " +
            fresh.slice(0, 3).map(function (row) {
                return "<b>" + esc(row.name) + "</b>" + (row.seat != null ? " (#" + esc(row.seat) + ")" : "");
            }).join(", ") + (fresh.length > 3 ? " +" + (fresh.length - 3) : "") +
            ' <button type="button" class="fxc-room-alert__x" data-fxc-alert-close aria-label="' +
            esc(lbl("close", "Bağla")) + '">&times;</button>';
    }

    // ── Polling ──────────────────────────────────────────────────────────────
    function create(opts) {
        var etag = opts.etag || "";
        var timer = null;
        var inflight = false;
        var stopped = false;
        var delay = BASE_MS;

        function schedule(ms) {
            if (stopped) return;
            if (timer) window.clearTimeout(timer);
            timer = window.setTimeout(function () { timer = null; load(false); }, ms);
        }

        function expire() {
            stopped = true;
            if (timer) window.clearTimeout(timer);
            var box = document.getElementById("fxc-room-expired");
            if (box) box.hidden = false;
            document.documentElement.classList.add("fxc-room-is-expired");
            if (opts.onState) opts.onState("expired");
        }

        function load(fresh) {
            if (stopped) return Promise.resolve();
            if (document.hidden && !fresh) return Promise.resolve(); // gizli tabda sorğu yox
            if (inflight && !fresh) return Promise.resolve();
            inflight = true;
            var url = opts.url + (fresh ? (opts.url.indexOf("?") === -1 ? "?" : "&") + "fresh=1" : "");
            var headers = { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" };
            if (etag && !fresh) headers["If-None-Match"] = etag;
            return fetch(url, { credentials: "same-origin", headers: headers, cache: "no-store" })
                .then(function (r) {
                    if (r.status === 403 || r.status === 401) { expire(); return null; }
                    if (r.status === 429) {
                        var wait = (parseInt(r.headers.get("Retry-After") || "", 10) || 15) * 1000;
                        delay = Math.min(MAX_BACKOFF_MS, wait);
                        return null;
                    }
                    if (r.status === 304) { delay = BASE_MS; if (opts.onState) opts.onState("online"); return null; }
                    if (!r.ok) throw new Error("http " + r.status);
                    etag = r.headers.get("ETag") || "";
                    return r.json().then(function (data) {
                        delay = BASE_MS;
                        announceFlags(data);
                        if (opts.onData) opts.onData(data);
                        if (opts.onState) opts.onState("online");
                    });
                })
                .catch(function () {
                    delay = Math.min(MAX_BACKOFF_MS, delay * 2);
                    if (opts.onState) opts.onState("offline");
                })
                .then(function () { inflight = false; schedule(delay); });
        }

        document.addEventListener("visibilitychange", function () {
            if (!document.hidden && !stopped) load(false);
        });

        return {
            start: function (initial) {
                if (initial) { syncClock(initial); announceFlags(initial); }
                schedule(BASE_MS);
            },
            refresh: function (fresh) { return load(fresh !== false); }
        };
    }

    // ── Nəzarətçi qeydi (pozuntu modalında) ──────────────────────────────────
    function noteFormHtml(attemptId) {
        var root = document.getElementById("fxc-room-root");
        if (!root || !root.dataset.noteUrlTemplate || !attemptId) return "";
        return '<form class="fxc-note-form" data-fxc-note-form data-attempt="' + esc(attemptId) + '">' +
            '<label class="fxc-note-form__label" for="fxc-note-text">' + esc(lbl("noteLabel", "Nəzarətçi qeydi")) + "</label>" +
            '<textarea id="fxc-note-text" name="text" maxlength="200" rows="2" class="ems-input" required ' +
                'placeholder="' + esc(lbl("notePlaceholder", "")) + '"></textarea>' +
            '<div class="fxc-note-form__foot"><span class="fxc-note-form__msg" role="status" aria-live="polite"></span>' +
            '<button type="submit" class="fxc-btn fxc-btn-sm fxc-btn-primary">' + esc(lbl("noteSave", "Qeydi yaz")) +
            "</button></div></form>";
    }

    function bindOnce() {
        var root = document.getElementById("fxc-room-root");
        if (!root || root.dataset.fxcLiveBound === "1") return;
        root.dataset.fxcLiveBound = "1";
        var i18n = document.getElementById("fxc-room-live-i18n");
        if (i18n) { try { L = JSON.parse(i18n.textContent) || {}; } catch (err) { L = {}; } }
        window.setInterval(tickTimes, 30000);

        document.addEventListener("click", function (evt) {
            if (!evt.target.closest || !evt.target.closest("[data-fxc-alert-close]")) return;
            var box = document.getElementById("fxc-room-alert");
            if (box) box.hidden = true;
        });

        document.addEventListener("submit", function (evt) {
            var form = evt.target.closest ? evt.target.closest("[data-fxc-note-form]") : null;
            if (!form) return;
            evt.preventDefault();
            var msg = form.querySelector(".fxc-note-form__msg");
            var btn = form.querySelector("button[type=submit]");
            var text = (form.querySelector("textarea").value || "").trim();
            if (!text) return;
            var url = root.dataset.noteUrlTemplate.replace("attempts/0/", "attempts/" + form.dataset.attempt + "/");
            if (btn) btn.disabled = true;
            fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-CSRFToken": csrf(),
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                body: "text=" + encodeURIComponent(text)
            }).then(function (r) { return r.json().catch(function () { return {}; }); })
                .then(function (d) {
                    if (d && d.success) {
                        form.querySelector("textarea").value = "";
                        if (msg) msg.textContent = lbl("noteSaved", "Qeyd yazıldı.");
                    } else if (msg) {
                        msg.textContent = (d && d.error) || lbl("noteFailed", "Qeyd yazılmadı.");
                    }
                })
                .catch(function () { if (msg) msg.textContent = lbl("noteFailed", "Qeyd yazılmadı."); })
                .then(function () { if (btn) btn.disabled = false; });
        });
    }

    window.FXCRoomLive = { create: create, decorate: decorate, noteFormHtml: noteFormHtml };

    if (typeof window.EMSReady === "function") {
        window.EMSReady(bindOnce);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bindOnce, { once: true });
    } else {
        bindOnce();
    }
})();

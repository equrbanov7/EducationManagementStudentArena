/**
 * Tələbə canlı görüntü ("çiyni üzərindən") modalı — PAYLAŞILAN modul.
 * session_monitor və room_monitor onu `window.FXCSnapshot.open(sessionId, ticketId)`
 * ilə çağırır. Fənn/imtahan adı, BÜTÜN suallar (variantlarla) və nəzarətçi
 * əməliyyatları (bərpa / dayandır / çıxar) göstərir.
 */
(function () {
    "use strict";

    var modal = document.getElementById("fxc-snapshot-modal");
    if (!modal) return;

    var snapshotTpl = modal.dataset.snapshotUrlTemplate; // .../sessions/0/tickets/0/snapshot/
    var resumeTpl = modal.dataset.resumeUrlTemplate;
    var reentryTpl = modal.dataset.reentryUrlTemplate;
    var removeTpl = modal.dataset.removeUrlTemplate;

    var current = { sessionId: null, ticketId: null };
    var onChange = null; // monitor bunu təyin edir — əməliyyatdan sonra snapshot yeniləmək üçün
    // Canlı "çiyni üzərindən" izləmə. Sistem yükünü azaltmaq üçün avtomatik
    // yenilənmə 30 saniyədədir; "Yenilə" düyməsi isə dərhal yeniləyir.
    var POLL_MS = 30000;
    var pollTimer = null;
    var requestSerial = 0;

    function esc(t) {
        var d = document.createElement("div");
        d.textContent = t == null ? "" : String(t);
        return d.innerHTML;
    }

    function csrf() {
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        if (m) return decodeURIComponent(m[1]);
        var inp = document.querySelector("input[name=csrfmiddlewaretoken]");
        return inp ? inp.value : "";
    }

    function fillUrl(tpl, sid, tid) {
        return tpl.replace("sessions/0/", "sessions/" + sid + "/").replace("tickets/0/", "tickets/" + tid + "/");
    }

    function setError(msg) {
        var el = document.getElementById("fxc-snapshot-error");
        if (!el) return;
        el.textContent = msg || "";
        el.hidden = !msg;
    }

    function hideReentryPin() {
        var el = document.getElementById("fxc-reentry-pin");
        if (el) el.hidden = true;
    }

    function open(sessionId, ticketId) {
        current.sessionId = sessionId;
        current.ticketId = ticketId;
        modal.hidden = false;
        // Arxa fon skroll etməsin: modal açıqkən həm <html>, həm <body> kilidlənir
        // (yalnız birini kilidləmək bəzi brauzerlərdə səhifəni tərpədir).
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
        setError("");
        hideReentryPin(); // əvvəlki tələbənin PIN-i qalmasın
        load(false);
        startPolling();
    }

    function close() {
        modal.hidden = true;
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
        stopPolling();
    }

    function startPolling() {
        stopPolling();
        pollTimer = window.setInterval(function () { load(true); }, POLL_MS);
    }

    function stopPolling() {
        if (pollTimer) { window.clearInterval(pollTimer); pollTimer = null; }
    }

    // silent=true → arxa-fon poll: "Yüklənir…" göstərmir və scroll mövqeyini saxlayır.
    function load(silent) {
        var body = document.getElementById("fxc-snapshot-body");
        if (body && !silent) {
            body.innerHTML =
                '<div class="fxc-snapshot-answers" aria-hidden="true">' +
                '<div class="fxc-snap-q"><span class="skeleton skeleton-line" style="width:70%"></span></div>' +
                '<div class="fxc-snap-q"><span class="skeleton skeleton-line" style="width:55%"></span></div>' +
                '<div class="fxc-snap-q"><span class="skeleton skeleton-line" style="width:65%"></span></div>' +
                "</div>";
        }
        var keepScroll = body ? body.scrollTop : 0;
        var mine = ++requestSerial;
        var snapshotUrl = fillUrl(snapshotTpl, current.sessionId, current.ticketId);
        snapshotUrl += (snapshotUrl.indexOf("?") === -1 ? "?" : "&") + "_snapshot_ts=" + Date.now();
        fetch(snapshotUrl, { credentials: "same-origin", cache: "no-store" })
            .then(function (r) {
                if (!r.ok) throw new Error("snapshot_failed");
                return r.json();
            })
            .then(function (d) {
                // Manual refresh and background poll overlap when the network is
                // slow: an older response must never overwrite the newer state.
                if (mine !== requestSerial) return;
                render(d);
                if (silent && body) body.scrollTop = keepScroll;
                // Cəhd bitibsə və ya hələ başlamayıbsa canlı poll-a ehtiyac yoxdur.
                if (d.is_finished || !d.has_attempt) stopPolling();
            })
            .catch(function () {
                if (mine !== requestSerial) return;
                if (body && !silent) body.innerHTML = '<p class="fxc-modal-error">Məlumat yüklənmədi.</p>';
            });
    }

    function render(d) {
        setError("");
        var nameEl = document.getElementById("fxc-snapshot-name");
        var subjectEl = document.getElementById("fxc-snapshot-subject");
        var metaEl = document.getElementById("fxc-snapshot-meta");
        var actionsEl = document.getElementById("fxc-snapshot-actions");
        var body = document.getElementById("fxc-snapshot-body");

        if (nameEl) nameEl.textContent = d.student_name || "—";
        if (subjectEl) subjectEl.textContent = d.exam_title ? ("📘 " + d.exam_title) : "";

        if (metaEl) {
            var meta = [];
            if (d.seat != null) meta.push('<span><i class="fas fa-desktop"></i> Kompüter ' + esc(d.seat) + "</span>");
            meta.push('<span><i class="fas fa-user"></i> ' + esc(d.student_username || "") + "</span>");
            if (d.has_attempt) {
                meta.push('<span><i class="fas fa-list-check"></i> ' + esc(d.answered) + " / " + esc(d.total_questions) + " cavab</span>");
                // Bal: bitmiş cəhd üçün yekun faiz, davam edən test üçün canlı
                // (müvəqqəti) faiz — imtahan indi bitsəydi neçə bal olardı.
                if (d.is_finished && d.score_percent != null) {
                    meta.push('<span class="fxc-pill fxc-pill--score"><i class="fas fa-award"></i> ' + esc(d.score_percent) + "%</span>");
                } else if (!d.is_finished && d.live_score != null) {
                    // Cari bal FAİZ deyil, BAL sayı ilə: keçid həddindən (17) aşağı
                    // qırmızı, ondan yuxarı yaşıl — nəzarətçi bir baxışda görsün.
                    var lv = parseFloat(d.live_score);
                    var lvCls = (!isNaN(lv) && lv >= 17) ? "fxc-pill--score-pass" : "fxc-pill--score-low";
                    meta.push('<span class="fxc-pill ' + lvCls + '"><i class="fas fa-gauge-high"></i> Cari bal: ' + esc(d.live_score) + " bal</span>");
                }
                if (d.supervision_status && d.supervision_status !== "active") {
                    meta.push('<span class="fxc-pill fxc-pill--warn">' + esc(supLabel(d.supervision_status)) + "</span>");
                }
                if (d.intervention_reason) {
                    meta.push('<span class="fxc-pill fxc-pill--warn"><i class="fas fa-circle-info"></i> Səbəb: ' +
                        esc(d.intervention_reason) + "</span>");
                }
                if (d.violation_count) meta.push('<span class="fxc-pill fxc-pill--warn">' + esc(d.violation_count) + " pozuntu</span>");
            }
            metaEl.innerHTML = meta.join("");
        }

        // Nəzarətçi əməliyyatları yalnız aktiv (bitməmiş) cəhd üçün.
        var isLive = d.has_attempt && !d.is_finished;
        if (actionsEl) {
            actionsEl.hidden = !isLive;
            var resumeBtn = actionsEl.querySelector('[data-snap-action="resume"]');
            if (resumeBtn) resumeBtn.hidden = !(d.supervision_status === "locked");
        }
        var liveEl = document.getElementById("fxc-snapshot-live");
        if (liveEl) liveEl.hidden = !isLive;

        if (!body) return;
        if (!d.has_attempt) {
            body.innerHTML = '<div class="fxc-snapshot-empty"><i class="fas fa-hourglass-half"></i>' +
                "<p>Tələbə hələ imtahana başlamayıb.</p></div>";
            return;
        }
        var answers = d.answers || [];
        if (!answers.length) {
            body.innerHTML = '<div class="fxc-snapshot-empty"><i class="far fa-file"></i>' +
                "<p>Hələ heç bir sual cavablanmayıb.</p></div>";
            return;
        }
        body.innerHTML = '<ol class="fxc-snapshot-answers">' + answers.map(renderQuestion).join("") + "</ol>";
    }

    function renderQuestion(a, i) {
        var cls = a.is_answered ? "answered" : "empty";
        var inner = "";
        var opts = a.options || [];
        if (opts.length) {
            // Test sualı — bütün variantları göstər, seçilən + düzgün işarələnir.
            inner = '<div class="fxc-snap-opts">' + opts.map(function (o) {
                var oc = "";
                if (o.is_selected) oc += " selected";
                if (o.is_correct) oc += " correct";
                if (o.is_selected && !o.is_correct) oc += " wrong";
                var badges = "";
                if (o.is_selected) badges += '<span class="fxc-snap-badge fxc-snap-badge--selected">Tələbənin cavabı</span>';
                if (o.is_correct) badges += '<span class="fxc-snap-badge fxc-snap-badge--correct">Düzgün cavab</span>';
                return '<div class="fxc-snap-opt' + oc + '">' +
                    '<span class="fxc-snap-opt-lbl">' + esc(o.label || "") + "</span>" +
                    '<span class="fxc-snap-opt-txt">' + esc(o.text || "") + "</span>" +
                    badges +
                    "</div>";
            }).join("") + "</div>";
        } else if (a.text_answer) {
            inner = '<div class="fxc-snap-q-ans">' + esc(a.text_answer) + "</div>";
        } else if (a.files && a.files.length) {
            inner = '<div class="fxc-snap-q-ans">' + a.files.length + " fayl yükləyib</div>";
        } else if (a.has_paint) {
            inner = '<div class="fxc-snap-q-ans">Rəsm / şəkil cavabı</div>';
        }
        return '<li class="fxc-snap-q fxc-snap-q--' + cls + '">' +
            '<div class="fxc-snap-q-head"><span class="fxc-snap-q-no">' + (i + 1) + "</span>" +
            '<span class="fxc-snap-q-text">' + esc(a.question_text || ("Sual " + (i + 1))) + "</span>" +
            (a.is_answered ? '<i class="fas fa-check fxc-snap-ok"></i>' : '<i class="far fa-circle fxc-snap-none"></i>') +
            "</div>" + inner + "</li>";
    }

    function supLabel(s) {
        return { locked: "Dayandırılıb", removed: "Çıxarılıb", warned: "Xəbərdarlıq", resumed: "Bərpa olunub" }[s] || s;
    }

    // ── Əməliyyatlar ──
    function postAction(url, body) {
        return fetch(url, {
            method: "POST",
            headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/x-www-form-urlencoded" },
            credentials: "same-origin",
            body: body || ""
        }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); });
    }

    modal.addEventListener("click", function (evt) {
        // Bağla düyməsi VƏ ya modalın kənarına (backdrop) klik → bağla.
        if (evt.target.closest("[data-close-snapshot]") || evt.target === modal) { close(); return; }
        var actBtn = evt.target.closest("[data-snap-action]");
        if (!actBtn) return;
        var action = actBtn.dataset.snapAction;
        if (action === "resume") {
            postAction(fillUrl(resumeTpl, current.sessionId, current.ticketId), "")
                .then(afterAction).catch(netErr);
        } else if (action === "reentry") {
            if (!window.confirm("Bu tələbəyə yeni giriş PIN-i verilsin? O, imtahana olduğu yerdən davam edəcək.")) return;
            postAction(fillUrl(reentryTpl, current.sessionId, current.ticketId), "")
                .then(afterReentry).catch(netErr);
        } else if (action === "suspend") {
            var reason = window.prompt("Dayandırma səbəbi:");
            if (!reason) return;
            postAction(fillUrl(removeTpl, current.sessionId, current.ticketId),
                "action=suspended&reason=" + encodeURIComponent(reason)).then(afterAction).catch(netErr);
        } else if (action === "remove") {
            var rReason = window.prompt("İmtahandan çıxarma səbəbi:");
            if (!rReason) return;
            postAction(fillUrl(removeTpl, current.sessionId, current.ticketId),
                "action=removed&reason=" + encodeURIComponent(rReason)).then(afterAction).catch(netErr);
        }
    });

    function afterAction(result) {
        if (result.ok && result.data.success !== false) {
            load(false);
            startPolling();
            if (typeof onChange === "function") onChange();
        } else {
            setError((result.data && result.data.error) || "Əməliyyat mümkün olmadı.");
        }
    }

    // Yenidən giriş: yeni PIN-i modalда BİR DƏFƏ göstər (nəzarətçi tələbəyə deyir).
    function afterReentry(result) {
        if (result.ok && result.data.success !== false && result.data.pin) {
            setError("");
            var box = document.getElementById("fxc-reentry-pin");
            var val = document.getElementById("fxc-reentry-pin-value");
            if (val) val.textContent = result.data.pin;
            if (box) box.hidden = false;
            if (typeof onChange === "function") onChange();
        } else {
            setError((result.data && result.data.error) || "Yenidən giriş mümkün olmadı.");
        }
    }

    function netErr() { setError("Şəbəkə xətası — yenidən cəhd edin."); }

    var refreshBtn = document.getElementById("fxc-snapshot-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", function () { load(false); startPolling(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });

    window.FXCSnapshot = {
        open: open,
        close: close,
        setOnChange: function (fn) { onChange = fn; }
    };
})();

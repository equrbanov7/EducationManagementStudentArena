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
    var removeTpl = modal.dataset.removeUrlTemplate;

    var current = { sessionId: null, ticketId: null };
    var onChange = null; // monitor bunu təyin edir — əməliyyatdan sonra snapshot yeniləmək üçün

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

    function open(sessionId, ticketId) {
        current.sessionId = sessionId;
        current.ticketId = ticketId;
        modal.hidden = false;
        setError("");
        load();
    }

    function close() {
        modal.hidden = true;
    }

    function load() {
        var body = document.getElementById("fxc-snapshot-body");
        if (body) body.innerHTML = '<p class="fxc-muted fxc-center">Yüklənir…</p>';
        fetch(fillUrl(snapshotTpl, current.sessionId, current.ticketId), { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(render)
            .catch(function () {
                if (body) body.innerHTML = '<p class="fxc-modal-error">Məlumat yüklənmədi.</p>';
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
                if (d.supervision_status && d.supervision_status !== "active") {
                    meta.push('<span class="fxc-pill fxc-pill--warn">' + esc(supLabel(d.supervision_status)) + "</span>");
                }
                if (d.violation_count) meta.push('<span class="fxc-pill fxc-pill--warn">' + esc(d.violation_count) + " pozuntu</span>");
            }
            metaEl.innerHTML = meta.join("");
        }

        // Nəzarətçi əməliyyatları yalnız aktiv (bitməmiş) cəhd üçün.
        if (actionsEl) {
            var showActions = d.has_attempt && !d.is_finished;
            actionsEl.hidden = !showActions;
            var resumeBtn = actionsEl.querySelector('[data-snap-action="resume"]');
            if (resumeBtn) resumeBtn.hidden = !(d.supervision_status === "locked");
        }

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
                return '<div class="fxc-snap-opt' + oc + '">' +
                    '<span class="fxc-snap-opt-lbl">' + esc(o.label || "") + "</span>" +
                    '<span class="fxc-snap-opt-txt">' + esc(o.text || "") + "</span>" +
                    (o.is_selected ? '<i class="fas fa-circle-check"></i>' : "") +
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
        if (evt.target.closest("[data-close-snapshot]")) { close(); return; }
        var actBtn = evt.target.closest("[data-snap-action]");
        if (!actBtn) return;
        var action = actBtn.dataset.snapAction;
        if (action === "resume") {
            postAction(fillUrl(resumeTpl, current.sessionId, current.ticketId), "")
                .then(afterAction).catch(netErr);
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
            load();
            if (typeof onChange === "function") onChange();
        } else {
            setError((result.data && result.data.error) || "Əməliyyat mümkün olmadı.");
        }
    }

    function netErr() { setError("Şəbəkə xətası — yenidən cəhd edin."); }

    var refreshBtn = document.getElementById("fxc-snapshot-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", load);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });

    window.FXCSnapshot = {
        open: open,
        close: close,
        setOnChange: function (fn) { onChange = fn; }
    };
})();

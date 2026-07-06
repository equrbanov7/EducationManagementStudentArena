/**
 * Final oturumu — canlı otaq monitoru.
 *
 * Yeniləmə strategiyası: WS eventləri "dəyişiklik siqnalı" kimi qəbul edilir
 * və DEBOUNCE olunmuş snapshot fetch-i işə salınır (event başına ağır payload
 * YOX). WS qopanda aşağı tezlikli polling (30s) fallback-i işləyir.
 * İdarəedici əməliyyatlar CSRF-li POST-lardır; server idempotentdir.
 */
(function () {
    "use strict";

    var root = document.getElementById("fxc-monitor-root");
    if (!root) return;

    var snapshotUrl = root.dataset.snapshotUrl;
    var startUrl = root.dataset.startUrl;
    var endUrl = root.dataset.endUrl;
    var removeUrlTemplate = root.dataset.removeUrlTemplate; // .../tickets/0/remove/
    var wsPath = root.dataset.wsPath;

    var rowsEl = document.getElementById("fxc-student-rows");
    var statsEl = document.getElementById("fxc-stats");
    var statePill = document.getElementById("fxc-state-pill");
    var wsState = document.getElementById("fxc-ws-state");
    var serverTimeEl = document.getElementById("fxc-server-time");
    var filterInput = document.getElementById("fxc-filter");
    var statusFilter = document.getElementById("fxc-status-filter");
    var startBtn = document.getElementById("fxc-start-btn");
    var endBtn = document.getElementById("fxc-end-btn");
    var mapEl = document.getElementById("fxc-computer-map");
    var mapView = document.getElementById("fxc-map-view");
    var tableView = document.getElementById("fxc-table-view");

    var snapshot = null;
    var socket = null;
    var reconnectAttempt = 0;
    var refreshTimer = null;
    var pollTimer = null;
    var removeTicketId = null;
    var currentView = "map";

    var initialEl = document.getElementById("fxc-initial-snapshot");
    if (initialEl) {
        try { snapshot = JSON.parse(initialEl.textContent); } catch (err) { snapshot = null; }
    }

    function csrfToken() {
        var input = root.querySelector("input[name=csrfmiddlewaretoken]");
        return input ? input.value : "";
    }

    var STATE_LABELS = {
        prepared: "Hazırlanır", entry_open: "Giriş açıq", active: "Aktiv",
        ended: "Bitib", cancelled: "Ləğv edilib"
    };
    var STATUS_LABELS = {
        assigned: "Təyin olunub", waiting: "Gözləyir", ready: "Hazır",
        active: "İmtahanda", completed: "Bitirib", removed: "Çıxarılıb", absent: "Gəlməyib"
    };
    var STAT_CARDS = [
        ["total", "Təyin olunmuş"], ["participated", "İmtahan verib"], ["connected", "Qoşulu"],
        ["waiting", "Gözləyir"], ["ready", "Hazır"], ["active", "İmtahanda"], ["completed", "Bitirib"],
        ["offline", "Oflayn"], ["removed", "Çıxarılıb"], ["absent", "Gəlməyib"]
    ];

    function esc(text) {
        var div = document.createElement("div");
        div.textContent = text == null ? "" : String(text);
        return div.innerHTML;
    }

    function formatRemaining(seconds) {
        if (seconds == null) return "—";
        var m = Math.floor(seconds / 60), s = seconds % 60;
        return m + ":" + (s < 10 ? "0" : "") + s;
    }

    function formatTime(iso) {
        if (!iso) return "—";
        var d = new Date(iso);
        return isNaN(d) ? "—" : d.toLocaleTimeString("az-AZ", { hour: "2-digit", minute: "2-digit" });
    }

    function renderStats() {
        if (!snapshot || !statsEl) return;
        var counts = snapshot.counts || {};
        var html = STAT_CARDS.map(function (pair) {
            var key = pair[0], label = pair[1];
            return '<div class="fxc-stat fxc-stat--' + key + '">' +
                '<div class="fxc-stat-value">' + esc(counts[key] != null ? counts[key] : 0) + "</div>" +
                '<div class="fxc-stat-label">' + esc(label) + "</div></div>";
        }).join("");
        statsEl.innerHTML = html;
    }

    function renderState() {
        if (!snapshot) return;
        if (statePill) {
            statePill.dataset.state = snapshot.state;
            statePill.className = "fxc-pill fxc-pill--state-" + snapshot.state;
            statePill.textContent = STATE_LABELS[snapshot.state] || snapshot.state;
        }
        if (serverTimeEl && snapshot.server_now) {
            serverTimeEl.textContent = "⏱ " + formatTime(snapshot.server_now);
        }
        var canManage = root.dataset.canManage === "1";
        if (startBtn) startBtn.hidden = !(snapshot.state === "entry_open");
        if (endBtn) endBtn.hidden = !(snapshot.state === "active");
        void canManage; // start/end nəzarətçiyə də açıqdır; server yenə yoxlayır
    }

    function rowMatchesFilters(student) {
        var text = (filterInput && filterInput.value || "").trim().toLowerCase();
        var status = statusFilter && statusFilter.value;
        if (status && student.status !== status) return false;
        if (text) {
            var hay = (student.name + " " + student.username).toLowerCase();
            if (hay.indexOf(text) === -1) return false;
        }
        return true;
    }

    function renderRows() {
        if (!snapshot || !rowsEl) return;
        var students = (snapshot.students || []).filter(rowMatchesFilters);
        if (!students.length) {
            rowsEl.innerHTML = '<tr><td colspan="9" class="fxc-muted fxc-center">Nəticə yoxdur</td></tr>';
            return;
        }
        var live = snapshot.state === "entry_open" || snapshot.state === "active";
        rowsEl.innerHTML = students.map(function (s) {
            var warn = [];
            if (s.pin_locked) warn.push('<span class="fxc-pill fxc-pill--warn">PIN kilidli</span>');
            if (s.supervision_status === "locked") warn.push('<span class="fxc-pill fxc-pill--warn">Dayandırılıb</span>');
            if (s.violation_count) warn.push('<span class="fxc-pill fxc-pill--warn">' + esc(s.violation_count) + " pozuntu</span>");
            if (s.removal_action) warn.push('<span class="fxc-pill fxc-pill--muted">' + esc(s.removal_action) + "</span>");
            var connCls = s.connected ? "online" : "offline";
            var connTxt = s.connected ? "Qoşulu" : "Oflayn";
            var actionable = live && (s.status === "waiting" || s.status === "ready" || s.status === "active");
            var actions = actionable
                ? '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-danger-ghost" data-remove-ticket="' +
                  esc(s.ticket_id) + '" data-student-name="' + esc(s.name) + " (" + esc(s.username) + ')">' +
                  '<i class="fas fa-user-slash"></i></button>'
                : "";
            return "<tr data-status='" + esc(s.status) + "' data-row-ticket='" + esc(s.ticket_id) + "'>" +
                '<td class="fxc-num">' + (s.seat != null ? esc(s.seat) : "—") + "</td>" +
                '<td class="fxc-strong">' + esc(s.name) +
                    ' <span class="fxc-muted">(' + esc(s.username) + ")</span></td>" +
                '<td><span class="fxc-conn" data-state="' + connCls + '">' + connTxt + "</span></td>" +
                '<td><span class="fxc-pill fxc-pill--t-' + esc(s.status) + '">' +
                    esc(STATUS_LABELS[s.status] || s.status) + "</span></td>" +
                '<td class="fxc-num">' + formatRemaining(s.remaining_seconds) + "</td>" +
                "<td>" + formatTime(s.last_seen_at) + "</td>" +
                '<td class="fxc-num">' + esc(s.reconnect_count || 0) + "</td>" +
                "<td>" + (warn.join(" ") || '<span class="fxc-muted">—</span>') + "</td>" +
                '<td class="fxc-row-actions">' + actions + "</td>" +
                "</tr>";
        }).join("");
    }

    // Kompüter xəritəsi hücrəsinin rəng sinfi (status + pozuntu prioriteti).
    function cellStateClass(s) {
        if (s.status === "removed") return "removed";
        if (s.status === "completed") return "completed";
        if (s.supervision_status === "locked" || s.violation_count) return "warn";
        if (s.status === "active") return "active";
        if (s.status === "ready") return "ready";
        if (s.status === "waiting") return "waiting";
        return "idle"; // assigned / absent / offline
    }

    function renderMap() {
        if (!snapshot || !mapEl) return;
        var students = (snapshot.students || []).filter(rowMatchesFilters);
        if (!students.length) {
            mapEl.innerHTML = '<p class="fxc-muted fxc-center">Nəticə yoxdur</p>';
            return;
        }
        mapEl.innerHTML = students.map(function (s, i) {
            var label = s.seat != null ? s.seat : (i + 1);
            var badges = "";
            if (s.violation_count) badges += '<span class="fxc-cell-vio">' + esc(s.violation_count) + "</span>";
            if (s.connected) badges += '<span class="fxc-cell-conn" title="Qoşulu"></span>';
            var initials = (s.name || "?").trim().charAt(0).toUpperCase();
            return '<button type="button" class="fxc-cell fxc-cell--' + cellStateClass(s) + '" ' +
                'data-ticket="' + esc(s.ticket_id) + '" ' +
                'title="' + esc(s.name) + " · " + esc(STATUS_LABELS[s.status] || s.status) + '">' +
                badges +
                '<span class="fxc-cell-num">' + esc(("0" + label).slice(-2)) + "</span>" +
                '<span class="fxc-cell-ini">' + esc(initials) + "</span>" +
                "</button>";
        }).join("");
    }

    function renderAll() {
        renderStats();
        renderState();
        renderRows();
        renderMap();
    }

    // ── Görünüş keçidi (kompüter xəritəsi ⇄ cədvəl) ──
    function setView(view) {
        currentView = view;
        if (mapView) mapView.hidden = view !== "map";
        if (tableView) tableView.hidden = view !== "table";
        document.querySelectorAll(".fxc-viewtoggle-btn").forEach(function (b) {
            var active = b.dataset.view === view;
            b.classList.toggle("is-active", active);
            b.setAttribute("aria-selected", active ? "true" : "false");
        });
    }

    document.querySelectorAll(".fxc-viewtoggle-btn").forEach(function (b) {
        b.addEventListener("click", function () { setView(b.dataset.view); });
    });

    // ── Tələbə canlı görüntü modalı — PAYLAŞILAN FXCSnapshot moduluna ötürülür ──
    function openSnapshot(ticketId) {
        var sid = (snapshot && snapshot.session_id) || null;
        if (sid && window.FXCSnapshot) window.FXCSnapshot.open(sid, ticketId);
    }
    if (window.FXCSnapshot) {
        // Snapshot-dakı əməliyyat (bərpa/dayandır/çıxar) monitor snapshot-ını yeniləsin.
        window.FXCSnapshot.setOnChange(function () { scheduleRefresh(); });
    }

    if (mapEl) {
        mapEl.addEventListener("click", function (evt) {
            var cell = evt.target.closest("[data-ticket]");
            if (cell) openSnapshot(cell.dataset.ticket);
        });
    }
    if (rowsEl) {
        rowsEl.addEventListener("click", function (evt) {
            // Çıxarma düyməsi öz işini görür; başqa yerə klik → canlı görüntü.
            if (evt.target.closest("[data-remove-ticket]")) return;
            var row = evt.target.closest("[data-row-ticket]");
            if (row) openSnapshot(row.dataset.rowTicket);
        });
    }

    function fetchSnapshot() {
        return fetch(snapshotUrl, { credentials: "same-origin" })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                snapshot = data;
                renderAll();
            })
            .catch(function () { /* növbəti siqnalda yenidən */ });
    }

    function scheduleRefresh() {
        if (refreshTimer) return;
        refreshTimer = window.setTimeout(function () {
            refreshTimer = null;
            fetchSnapshot();
        }, 1200);
    }

    // ── WebSocket ──────────────────────────────────────────────────────
    function setWsState(state, label) {
        if (!wsState) return;
        wsState.dataset.state = state;
        wsState.textContent = label;
    }

    function startPolling() {
        if (pollTimer) return;
        pollTimer = window.setInterval(fetchSnapshot, 30000);
    }

    function stopPolling() {
        if (pollTimer) {
            window.clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function connect() {
        var scheme = window.location.protocol === "https:" ? "wss" : "ws";
        socket = new WebSocket(scheme + "://" + window.location.host + wsPath);

        socket.onopen = function () {
            reconnectAttempt = 0;
            setWsState("online", "Canlı");
            stopPolling();
            scheduleRefresh();
        };
        socket.onmessage = function () {
            // Kompakt event → debounce olunmuş snapshot yeniləməsi.
            scheduleRefresh();
        };
        socket.onclose = function () {
            setWsState("offline", "Oflayn — polling");
            reconnectAttempt += 1;
            var base = Math.min(1000 * Math.pow(2, reconnectAttempt - 1), 30000);
            window.setTimeout(connect, base / 2 + Math.random() * (base / 2));
            startPolling();
        };
        socket.onerror = function () {
            try { socket.close(); } catch (err) { /* noop */ }
        };
    }

    // ── Modal idarəsi ──────────────────────────────────────────────────
    function openModal(id) {
        var modal = document.getElementById(id);
        if (modal) modal.hidden = false;
    }

    function closeModals() {
        document.querySelectorAll(".fxc-modal").forEach(function (m) { m.hidden = true; });
        var startError = document.getElementById("fxc-start-error");
        var endError = document.getElementById("fxc-end-error");
        var removeError = document.getElementById("fxc-remove-error");
        [startError, endError, removeError].forEach(function (el) { if (el) el.hidden = true; });
    }

    // Escape → açıq modalı bağla.
    document.addEventListener("keydown", function (evt) {
        if (evt.key === "Escape") closeModals();
    });

    document.addEventListener("click", function (evt) {
        // Bağla düyməsi VƏ ya modalın kənarına (backdrop) klik → bağla.
        if (evt.target.closest("[data-close-modal]") ||
            (evt.target.classList && evt.target.classList.contains("fxc-modal"))) {
            closeModals();
        }
        var removeBtn = evt.target.closest("[data-remove-ticket]");
        if (removeBtn) {
            removeTicketId = removeBtn.dataset.removeTicket;
            var nameEl = document.getElementById("fxc-remove-student");
            if (nameEl) nameEl.textContent = removeBtn.dataset.studentName || "";
            var reason = document.getElementById("fxc-remove-reason");
            if (reason) reason.value = "";
            openModal("fxc-remove-modal");
        }
    });

    document.addEventListener("keydown", function (evt) {
        if (evt.key === "Escape") closeModals();
    });

    function fillFacts(containerId) {
        var counts = (snapshot && snapshot.counts) || {};
        var container = document.getElementById(containerId);
        if (!container) return;
        container.querySelectorAll("[data-fact]").forEach(function (el) {
            var key = el.dataset.fact;
            if (key === "server_now") {
                el.textContent = formatTime(snapshot && snapshot.server_now);
            } else if (key === "waiting_ready") {
                el.textContent = (counts.waiting || 0) + (counts.ready || 0);
            } else {
                el.textContent = counts[key] != null ? counts[key] : "—";
            }
        });
    }

    if (startBtn) {
        startBtn.addEventListener("click", function () {
            fetchSnapshot().then(function () {
                fillFacts("fxc-start-facts");
                openModal("fxc-start-modal");
            });
        });
    }

    if (endBtn) {
        endBtn.addEventListener("click", function () {
            fetchSnapshot().then(function () {
                fillFacts("fxc-end-facts");
                openModal("fxc-end-modal");
            });
        });
    }

    function postAction(url, body, errorElId, confirmBtn) {
        if (confirmBtn) confirmBtn.disabled = true;
        return fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            credentials: "same-origin",
            body: body || ""
        })
            .then(function (resp) { return resp.json().then(function (d) { return { ok: resp.ok, data: d }; }); })
            .then(function (result) {
                if (result.ok && result.data.success !== false) {
                    closeModals();
                    fetchSnapshot();
                    return true;
                }
                var errEl = document.getElementById(errorElId);
                if (errEl) {
                    errEl.textContent = result.data.error || "Əməliyyat mümkün olmadı.";
                    errEl.hidden = false;
                }
                return false;
            })
            .catch(function () {
                var errEl = document.getElementById(errorElId);
                if (errEl) {
                    errEl.textContent = "Şəbəkə xətası — yenidən cəhd edin.";
                    errEl.hidden = false;
                }
                return false;
            })
            .finally(function () {
                if (confirmBtn) confirmBtn.disabled = false;
            });
    }

    var startConfirm = document.getElementById("fxc-start-confirm");
    if (startConfirm) {
        startConfirm.addEventListener("click", function () {
            var override = document.getElementById("fxc-override-check");
            var body = override && override.checked ? "override=1" : "";
            postAction(startUrl, body, "fxc-start-error", startConfirm).then(function (ok) {
                if (!ok) {
                    // Vaxt pəncərəsi xətasında override seçimini göstər.
                    var wrap = document.getElementById("fxc-override-wrap");
                    if (wrap) wrap.hidden = false;
                }
            });
        });
    }

    var endConfirm = document.getElementById("fxc-end-confirm");
    if (endConfirm) {
        endConfirm.addEventListener("click", function () {
            postAction(endUrl, "", "fxc-end-error", endConfirm);
        });
    }

    var removeConfirm = document.getElementById("fxc-remove-confirm");
    if (removeConfirm) {
        removeConfirm.addEventListener("click", function () {
            if (!removeTicketId) return;
            var action = (document.getElementById("fxc-remove-action") || {}).value || "removed";
            var reason = (document.getElementById("fxc-remove-reason") || {}).value || "";
            if (!reason.trim()) {
                var errEl = document.getElementById("fxc-remove-error");
                if (errEl) {
                    errEl.textContent = "Səbəb qeyd olunmalıdır.";
                    errEl.hidden = false;
                }
                return;
            }
            var reentry = document.getElementById("fxc-remove-reentry");
            var body = "action=" + encodeURIComponent(action) +
                "&reason=" + encodeURIComponent(reason) +
                (reentry && reentry.checked ? "&allow_reentry=1" : "");
            var url = removeUrlTemplate.replace("tickets/0/", "tickets/" + removeTicketId + "/");
            postAction(url, body, "fxc-remove-error", removeConfirm);
        });
    }

    if (filterInput) filterInput.addEventListener("input", renderRows);
    if (statusFilter) statusFilter.addEventListener("change", renderRows);

    renderAll();
    connect();
})();

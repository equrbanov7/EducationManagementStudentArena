/**
 * Zal-səviyyəli aqreqasiya monitoru.
 *
 * Zaldakı BÜTÜN canlı imtahan oturumlarını birləşdirir: kompüter xəritəsi
 * (hər hücrə fənn/imtahan ilə etiketlənir), aqreqat sayğaclar, "hamısını
 * başlat / girişi aç" düymələri. Hücrəyə klik → paylaşılan FXCSnapshot modalı
 * (tələbənin hansı fənndə olduğunu və canlı fəaliyyətini göstərir).
 *
 * Yenilənmə: aşağı tezlikli polling (zal aqreqasiyası çoxlu oturumdan ibarət
 * ola bildiyi üçün WS əvəzinə sadə poll — server yükü stabil qalır).
 */
(function () {
    "use strict";

    var root = document.getElementById("fxc-room-root");
    if (!root) return;

    var snapshotUrl = root.dataset.snapshotUrl;
    var startAllUrl = root.dataset.startAllUrl;
    var openAllUrl = root.dataset.openAllUrl;

    var statsEl = document.getElementById("fxc-stats");
    var mapEl = document.getElementById("fxc-computer-map");
    var sessionsEl = document.getElementById("fxc-room-sessions");
    var examFilter = document.getElementById("fxc-exam-filter");
    var statusFilter = document.getElementById("fxc-status-filter");
    var filterInput = document.getElementById("fxc-filter");
    var startAllBtn = document.getElementById("fxc-start-all-btn");
    var openAllBtn = document.getElementById("fxc-open-all-btn");

    var POLL_MS = 10000;
    var snapshot = null;
    var pollTimer = null;
    var refreshTimer = null;
    var examOptionsKey = "";

    var initialEl = document.getElementById("fxc-initial-room-snapshot");
    if (initialEl) {
        try { snapshot = JSON.parse(initialEl.textContent); } catch (err) { snapshot = null; }
    }

    function csrf() {
        var inp = root.querySelector("input[name=csrfmiddlewaretoken]");
        if (inp) return inp.value;
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : "";
    }

    function esc(t) {
        var d = document.createElement("div");
        d.textContent = t == null ? "" : String(t);
        return d.innerHTML;
    }

    var STAT_CARDS = [
        ["total", "Təyin olunmuş"], ["connected", "Qoşulu"], ["waiting", "Gözləyir"],
        ["ready", "Hazır"], ["active", "İmtahanda"], ["completed", "Bitirib"],
        ["offline", "Oflayn"], ["removed", "Çıxarılıb"], ["absent", "Gəlməyib"]
    ];
    var STATUS_LABELS = {
        assigned: "Təyin olunub", waiting: "Gözləyir", ready: "Hazır",
        active: "İmtahanda", completed: "Bitirib", removed: "Çıxarılıb", absent: "Gəlməyib"
    };

    function cellStateClass(s) {
        if (s.status === "removed") return "removed";
        if (s.status === "completed") return "completed";
        if (s.supervision_status === "locked" || s.violation_count) return "warn";
        if (s.status === "active") return "active";
        if (s.status === "ready") return "ready";
        if (s.status === "waiting") return "waiting";
        return "idle";
    }

    function renderStats() {
        if (!snapshot || !statsEl) return;
        var c = snapshot.counts || {};
        statsEl.innerHTML = STAT_CARDS.map(function (p) {
            return '<div class="fxc-stat fxc-stat--' + p[0] + '">' +
                '<div class="fxc-stat-value">' + esc(c[p[0]] != null ? c[p[0]] : 0) + "</div>" +
                '<div class="fxc-stat-label">' + esc(p[1]) + "</div></div>";
        }).join("");
    }

    function renderSessions() {
        if (!snapshot) return;
        var sessions = snapshot.sessions || [];
        if (sessionsEl) {
            sessionsEl.innerHTML = sessions.length
                ? sessions.map(function (s) {
                    return '<span class="fxc-room-exam-chip fxc-room-exam-chip--' + esc(s.state) + '">' +
                        esc(s.exam_title) + "</span>";
                }).join(" ")
                : "Zalda canlı imtahan yoxdur.";
        }
        // İmtahan filtri seçimlərini yalnız dəyişəndə yenilə.
        var key = sessions.map(function (s) { return s.session_id; }).join(",");
        if (examFilter && key !== examOptionsKey) {
            examOptionsKey = key;
            var cur = examFilter.value;
            examFilter.innerHTML = '<option value="">Bütün imtahanlar</option>' + sessions.map(function (s) {
                return '<option value="' + esc(s.session_id) + '">' + esc(s.exam_title) + "</option>";
            }).join("");
            examFilter.value = cur;
        }
        // Düymə görünürlüyü: hazır (entry_open) oturum varsa "başlat" göstər.
        var hasEntryOpen = sessions.some(function (s) { return s.state === "entry_open"; });
        if (startAllBtn) startAllBtn.hidden = !hasEntryOpen;
        if (openAllBtn) openAllBtn.hidden = true; // prepared oturumlar snapshot-da deyil; server yoxlayır
    }

    function matchesFilters(s) {
        var text = (filterInput && filterInput.value || "").trim().toLowerCase();
        var status = statusFilter && statusFilter.value;
        var exam = examFilter && examFilter.value;
        if (status && s.status !== status) return false;
        if (exam && String(s.session_id) !== String(exam)) return false;
        if (text) {
            var hay = (s.name + " " + s.username + " " + (s.exam_title || "")).toLowerCase();
            if (hay.indexOf(text) === -1) return false;
        }
        return true;
    }

    function renderMap() {
        if (!snapshot || !mapEl) return;
        var students = (snapshot.students || []).filter(matchesFilters);
        if (!students.length) {
            mapEl.innerHTML = '<p class="fxc-muted fxc-center">Nəticə yoxdur</p>';
            return;
        }
        mapEl.innerHTML = students.map(function (s, i) {
            var label = s.seat != null ? s.seat : (i + 1);
            var badges = "";
            if (s.violation_count) badges += '<span class="fxc-cell-vio">' + esc(s.violation_count) + "</span>";
            if (s.connected) badges += '<span class="fxc-cell-conn"></span>';
            // Fərqləndirici hissə: "—"-dən sonrakı fənn adı (yoxdursa tam ad).
            var subj = (s.exam_title || "");
            if (subj.indexOf("—") !== -1) subj = subj.split("—").pop();
            subj = subj.replace(/\(.*\)/, "").trim().slice(0, 12);
            return '<button type="button" class="fxc-cell fxc-cell--' + cellStateClass(s) + '" ' +
                'data-ticket="' + esc(s.ticket_id) + '" data-session="' + esc(s.session_id) + '" ' +
                'title="' + esc(s.name) + " · " + esc(s.exam_title || "") + '">' +
                badges +
                '<span class="fxc-cell-num">' + esc(("0" + label).slice(-2)) + "</span>" +
                '<span class="fxc-cell-ini">' + esc(subj) + "</span>" +
                "</button>";
        }).join("");
    }

    function renderAll() {
        renderStats();
        renderSessions();
        renderMap();
    }

    function fetchSnapshot() {
        return fetch(snapshotUrl, { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (d) { snapshot = d; renderAll(); })
            .catch(function () { /* növbəti tsiklde yenidən */ });
    }

    function scheduleRefresh() {
        if (refreshTimer) return;
        refreshTimer = window.setTimeout(function () { refreshTimer = null; fetchSnapshot(); }, 800);
    }

    function post(url) {
        return fetch(url, {
            method: "POST",
            headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin"
        }).then(function (r) { return r.json(); });
    }

    if (startAllBtn) {
        startAllBtn.addEventListener("click", function () {
            if (!window.confirm("Zaldakı bütün hazır imtahanlar eyni anda başladılsın?")) return;
            startAllBtn.disabled = true;
            post(startAllUrl).then(function () { fetchSnapshot(); }).finally(function () { startAllBtn.disabled = false; });
        });
    }
    if (openAllBtn) {
        openAllBtn.addEventListener("click", function () {
            openAllBtn.disabled = true;
            post(openAllUrl).then(function () { fetchSnapshot(); }).finally(function () { openAllBtn.disabled = false; });
        });
    }

    if (mapEl) {
        mapEl.addEventListener("click", function (evt) {
            var cell = evt.target.closest("[data-ticket]");
            if (cell && window.FXCSnapshot) {
                window.FXCSnapshot.open(cell.dataset.session, cell.dataset.ticket);
            }
        });
    }
    if (window.FXCSnapshot) window.FXCSnapshot.setOnChange(scheduleRefresh);

    if (filterInput) filterInput.addEventListener("input", renderMap);
    if (statusFilter) statusFilter.addEventListener("change", renderMap);
    if (examFilter) examFilter.addEventListener("change", renderMap);

    renderAll();
    pollTimer = window.setInterval(fetchSnapshot, POLL_MS);
    void pollTimer;
})();

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
    var vioListEl = document.getElementById("fxc-violations-list");
    var vioCountEl = document.getElementById("fxc-vio-count");
    var wsEl = document.getElementById("fxc-room-ws");
    var updatedEl = document.getElementById("fxc-room-updated");
    var lastVioCount = -1;

    // Snapshot modalının şablonlarından bərpa/çıxarma URL-lərini götürürük.
    var snapModal = document.getElementById("fxc-snapshot-modal");
    var resumeTpl = snapModal ? snapModal.dataset.resumeUrlTemplate : "";
    var removeTpl = snapModal ? snapModal.dataset.removeUrlTemplate : "";

    function fillUrl(tpl, sid, tid) {
        return tpl.replace("sessions/0/", "sessions/" + sid + "/").replace("tickets/0/", "tickets/" + tid + "/");
    }

    var POLL_MS = 10000;
    var snapshot = null;
    var pollTimer = null;
    var refreshTimer = null;
    var examOptionsKey = "";

    var initialEl = document.getElementById("fxc-initial-room-snapshot");
    if (initialEl) {
        try { snapshot = JSON.parse(initialEl.textContent); } catch (err) { snapshot = null; }
    }

    // Server-side tərcümə olunmuş etiketlər (dil seçiminə uyğun). JS-də sabit AZ
    // mətn qalmasın deyə buradan oxunur; tapılmasa AZ fallback işlənir.
    var I18N = {};
    var i18nEl = document.getElementById("fxc-monitor-i18n");
    if (i18nEl) {
        try { I18N = JSON.parse(i18nEl.textContent); } catch (err) { I18N = {}; }
    }
    function t(path, fallback) {
        var parts = path.split("."), cur = I18N, i;
        for (i = 0; i < parts.length; i++) {
            if (cur == null) return fallback;
            cur = cur[parts[i]];
        }
        return cur == null ? fallback : cur;
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
        ["total", "Təyin olunmuş"], ["participated", "İmtahan verib"], ["connected", "Qoşulu"],
        ["waiting", "Gözləyir"], ["ready", "Hazır"], ["active", "İmtahanda"], ["completed", "Bitirib"],
        ["offline", "Oflayn"], ["removed", "Çıxarılıb"], ["absent", "Gəlməyib"]
    ];

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
                '<div class="fxc-stat-label">' + esc(t("stat." + p[0], p[1])) + "</div></div>";
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
                : esc(t("noLiveExams", "Zalda canlı imtahan yoxdur."));
        }
        // İmtahan filtri seçimlərini yalnız dəyişəndə yenilə.
        var key = sessions.map(function (s) { return s.session_id; }).join(",");
        if (examFilter && key !== examOptionsKey) {
            examOptionsKey = key;
            var cur = examFilter.value;
            examFilter.innerHTML = '<option value="">' + esc(t("allExams", "Bütün imtahanlar")) + "</option>" + sessions.map(function (s) {
                return '<option value="' + esc(s.session_id) + '">' + esc(s.exam_title) + "</option>";
            }).join("");
            examFilter.value = cur;
            // Bootstrap select ilə zənginləşdirilibsə, dropdown-u yeni option-larla yenilə.
            if (typeof examFilter._refreshBootstrapSelect === "function") {
                examFilter._refreshBootstrapSelect();
            }
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
            mapEl.innerHTML = '<p class="fxc-muted fxc-center">' + esc(t("noResults", "Nəticə yoxdur")) + "</p>";
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

    function renderViolations() {
        if (!vioListEl) return;
        var list = (snapshot && snapshot.students || []).filter(function (s) {
            return (s.violation_count && s.violation_count > 0) || s.supervision_status === "locked";
        }).sort(function (a, b) { return (b.violation_count || 0) - (a.violation_count || 0); });

        if (vioCountEl) vioCountEl.textContent = list.length;
        // Yeni pozuntu meydana çıxanda paneli bir anlıq vurğula (diqqət çək).
        if (lastVioCount >= 0 && list.length > lastVioCount) {
            var panel = document.getElementById("fxc-violations-panel");
            if (panel) { panel.classList.remove("fxc-flash"); void panel.offsetWidth; panel.classList.add("fxc-flash"); }
        }
        lastVioCount = list.length;
        if (!list.length) {
            vioListEl.innerHTML = '<p class="fxc-vio-empty">' + esc(t("violations.empty", "Qayda pozan yoxdur")) + "</p>";
            return;
        }
        vioListEl.innerHTML = list.map(function (s) {
            var locked = s.supervision_status === "locked";
            var subj = (s.exam_title || "");
            if (subj.indexOf("—") !== -1) subj = subj.split("—").pop().trim();
            var mainBtn = locked
                ? '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-success" data-vio-act="grant" ' +
                    'data-session="' + esc(s.session_id) + '" data-ticket="' + esc(s.ticket_id) + '">' +
                    '<i class="fas fa-rotate-left"></i> ' + esc(t("violations.grantChance", "Şans ver")) + "</button>"
                : '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-danger-ghost" data-vio-act="block" ' +
                    'data-session="' + esc(s.session_id) + '" data-ticket="' + esc(s.ticket_id) + '">' +
                    '<i class="fas fa-ban"></i> ' + esc(t("violations.block", "Blokla")) + "</button>";
            return '<div class="fxc-vio-row' + (locked ? " fxc-vio-row--locked" : "") + '">' +
                '<div class="fxc-vio-top">' +
                    '<span class="fxc-vio-name">' + esc(s.name) + "</span>" +
                    '<span class="fxc-vio-count-badge">' + esc(s.violation_count || 0) + " " +
                        esc(t("violations.word", "pozuntu")) + "</span>" +
                "</div>" +
                '<div class="fxc-vio-sub">' + esc(subj) +
                    (locked ? ' · <b>' + esc(t("violations.locked", "Dayandırılıb")) + "</b>" : "") + "</div>" +
                '<div class="fxc-vio-actions">' +
                    '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-ghost" data-vio-act="view" ' +
                        'data-session="' + esc(s.session_id) + '" data-ticket="' + esc(s.ticket_id) + '">' +
                        '<i class="fas fa-eye"></i> ' + esc(t("violations.view", "Bax")) + "</button>" +
                    mainBtn +
                "</div></div>";
        }).join("");
    }

    function renderAll() {
        renderStats();
        renderSessions();
        renderMap();
        renderViolations();
    }

    function setConn(ok) {
        if (wsEl) {
            wsEl.dataset.state = ok ? "online" : "offline";
            wsEl.textContent = ok ? t("live", "Canlı") : t("disconnected", "Bağlantı kəsildi");
        }
        if (ok && updatedEl) {
            updatedEl.textContent = t("updatedAt", "Yeniləndi") + " " + new Date().toLocaleTimeString();
        }
    }

    function fetchSnapshot() {
        return fetch(snapshotUrl, { credentials: "same-origin" })
            .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
            .then(function (d) { snapshot = d; renderAll(); setConn(true); })
            .catch(function () { setConn(false); /* növbəti tsiklde yenidən */ });
    }

    function scheduleRefresh() {
        if (refreshTimer) return;
        refreshTimer = window.setTimeout(function () { refreshTimer = null; fetchSnapshot(); }, 800);
    }

    function post(url, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrf(),
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            credentials: "same-origin",
            body: body || ""
        }).then(function (r) { return r.json(); });
    }

    function doStartAll(modalUi) {
        modalUi.setLoading(true);
        modalUi.showError("");
        post(startAllUrl, modalUi.override ? "override=1" : "").then(function (d) {
            if (d && d.success) { modalUi.close(); fetchSnapshot(); return; }
            modalUi.showError((d && d.error) || t("start.failed", "Başlatmaq mümkün olmadı."));
            if (d && d.can_override) modalUi.showOverride(t("start.override", "Vaxt pəncərəsindən asılı olmayaraq məcburi başlat"));
            modalUi.setLoading(false);
        }).catch(function () { modalUi.showError(t("start.failed", "Başlatmaq mümkün olmadı.")); modalUi.setLoading(false); });
    }

    if (startAllBtn) {
        startAllBtn.addEventListener("click", function () {
            if (!window.FXCConfirm) {
                startAllBtn.disabled = true;
                post(startAllUrl).then(function () { fetchSnapshot(); }).finally(function () { startAllBtn.disabled = false; });
                return;
            }
            window.FXCConfirm.open({
                title: t("start.title", "İmtahanı başlat"),
                message: t("confirmStartAll", "Zaldakı bütün hazır imtahanlar eyni anda başladılsın?"),
                confirmText: t("start.confirm", "Başlat"),
                confirmClass: "fxc-btn-success",
                onConfirm: function (state, modalUi) { modalUi.override = state.override; doStartAll(modalUi); }
            });
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

    // Qayda pozanlar panelindəki əməliyyatlar: bax / şans ver (bərpa) / blokla.
    if (vioListEl) {
        vioListEl.addEventListener("click", function (evt) {
            var btn = evt.target.closest("[data-vio-act]");
            if (!btn) return;
            var sid = btn.dataset.session, tid = btn.dataset.ticket, act = btn.dataset.vioAct;
            if (act === "view") {
                if (window.FXCSnapshot) window.FXCSnapshot.open(sid, tid);
            } else if (act === "grant") {
                if (!window.confirm(t("violations.confirmGrant", "Tələbəyə əlavə şans verilib imtahan bərpa edilsin?"))) return;
                btn.disabled = true;
                post(fillUrl(resumeTpl, sid, tid), "grant_extra_chance=1")
                    .then(function () { fetchSnapshot(); })
                    .catch(function () { btn.disabled = false; });
            } else if (act === "block") {
                var reason = window.prompt(t("violations.blockReason", "Bloklama səbəbi:"));
                if (!reason) return;
                btn.disabled = true;
                post(fillUrl(removeTpl, sid, tid), "action=suspended&reason=" + encodeURIComponent(reason))
                    .then(function () { fetchSnapshot(); })
                    .catch(function () { btn.disabled = false; });
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

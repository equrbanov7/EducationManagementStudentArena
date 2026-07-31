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
    var endAllUrl = root.dataset.endAllUrl;
    var openAllUrl = root.dataset.openAllUrl;
    var violationsTpl = root.dataset.violationsUrlTemplate; // .../attempts/0/violations/

    var statsEl = document.getElementById("fxc-stats");
    var mapEl = document.getElementById("fxc-computer-map");
    var sessionsEl = document.getElementById("fxc-room-sessions");
    var examFilter = document.getElementById("fxc-exam-filter");
    var statusFilter = document.getElementById("fxc-status-filter");
    var filterInput = document.getElementById("fxc-filter");
    var startAllBtn = document.getElementById("fxc-start-all-btn");
    var endAllBtn = document.getElementById("fxc-end-all-btn");
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

    // ── Pozuntu detalları modalı (hansı qaydalar pozulub + uzaqlaşdırma səbəbi) ──
    var vioModal = document.getElementById("fxc-vio-modal");
    var vioModalSub = document.getElementById("fxc-vio-modal-sub");
    var vioModalBody = document.getElementById("fxc-vio-modal-body");
    var vioModalRemoved = document.getElementById("fxc-vio-modal-removed");

    function closeViolationsModal() {
        if (!vioModal) return;
        vioModal.hidden = true;
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
    }

    function renderViolationsModal(d) {
        if (vioModalSub) {
            vioModalSub.textContent = (d.student || "") + (d.exam_title ? " · " + d.exam_title : "");
        }
        if (vioModalRemoved) {
            if (d.removal && d.removal.is_terminal) {
                vioModalRemoved.hidden = false;
                vioModalRemoved.innerHTML = '<i class="fas fa-user-slash"></i> ' +
                    esc(t("violations.removedBanner", gettext("İmtahandan uzaqlaşdırılıb"))) +
                    (d.removal.reason ? " — " + esc(d.removal.reason) : "");
            } else {
                vioModalRemoved.hidden = true;
                vioModalRemoved.innerHTML = "";
            }
        }
        if (!vioModalBody) return;
        var incidents = d.incidents || [];
        if (!incidents.length) {
            vioModalBody.innerHTML = '<p class="fxc-vio-modal__empty">' +
                esc(t("violations.noRules", gettext("Qeydə alınmış qayda pozuntusu yoxdur."))) + "</p>";
            return;
        }
        vioModalBody.innerHTML =
            '<div class="fxc-vio-modal__count">' + esc(d.violation_count || incidents.length) + " " +
                esc(t("violations.word", gettext("pozuntu"))) + "</div>" +
            '<ul class="fxc-vio-modal__list">' +
            incidents.map(function (inc) {
                var when = inc.at || "";
                try { when = new Date(inc.at).toLocaleString(); } catch (e) { when = inc.at || ""; }
                return '<li class="fxc-vio-modal__item fxc-vio-sev--' + esc(inc.severity || "medium") + '">' +
                    '<span class="fxc-vio-modal__rule">' + esc(inc.event) + "</span>" +
                    '<span class="fxc-vio-modal__time">' + esc(when) + "</span>" +
                    "</li>";
            }).join("") +
            "</ul>";
    }

    function openViolationsModal(attemptId) {
        if (!vioModal || !violationsTpl || !attemptId) return;
        vioModal.hidden = false;
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
        if (vioModalSub) vioModalSub.textContent = "";
        if (vioModalRemoved) { vioModalRemoved.hidden = true; vioModalRemoved.innerHTML = ""; }
        if (vioModalBody) {
            vioModalBody.innerHTML = '<p class="fxc-vio-modal__empty">' + esc(t("loading", gettext("Yüklənir…"))) + "</p>";
        }
        var url = violationsTpl.replace("attempts/0/", "attempts/" + attemptId + "/");
        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) {
                if (!d) {
                    if (vioModalBody) {
                        vioModalBody.innerHTML = '<p class="fxc-vio-modal__empty">' +
                            esc(t("violations.loadError", gettext("Məlumat yüklənmədi."))) + "</p>";
                    }
                    return;
                }
                renderViolationsModal(d);
            })
            .catch(function () {
                if (vioModalBody) {
                    vioModalBody.innerHTML = '<p class="fxc-vio-modal__empty">' +
                        esc(t("violations.loadError", gettext("Məlumat yüklənmədi."))) + "</p>";
                }
            });
    }

    // Sayğac plitələri (2026-07-29 sadələşməsi): 10 plitə operatoru boğurdu.
    // * "Hazır" ayrıca plitə deyil — "Gözləyir"ə əlavə olunur (bax renderStats);
    // * "Oflayn" silindi — texniki bağlantı vəziyyətidir, əməliyyat qərarı vermir;
    // * "Qoşulu" silindi — eyni məlumatın əks tərəfi.
    var STAT_CARDS = [
        ["total", gettext("Təyin olunmuş")], ["participated", gettext("İmtahan verib")],
        ["waiting", gettext("Gözləyir")], ["active", gettext("İmtahanda")], ["completed", gettext("Bitirib")],
        ["removed", gettext("Çıxarılıb")], ["absent", gettext("Gəlməyib")]
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
            var value = c[p[0]] != null ? c[p[0]] : 0;
            // "Gözləyir" texniki waiting + ready-nin cəmidir (filtrlə eyni məntiq).
            if (p[0] === "waiting") value += (c.ready != null ? c.ready : 0);
            return '<div class="fxc-stat fxc-stat--' + p[0] + '">' +
                '<div class="fxc-stat-value">' + esc(value) + "</div>" +
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
                : esc(t("noLiveExams", gettext("Zalda canlı imtahan yoxdur.")));
        }
        // İmtahan filtri seçimlərini yalnız dəyişəndə yenilə.
        var key = sessions.map(function (s) { return s.session_id; }).join(",");
        if (examFilter && key !== examOptionsKey) {
            examOptionsKey = key;
            var cur = examFilter.value;
            examFilter.innerHTML = '<option value="">' + esc(t("allExams", gettext("Bütün imtahanlar"))) + "</option>" + sessions.map(function (s) {
                return '<option value="' + esc(s.session_id) + '">' + esc(s.exam_title) + "</option>";
            }).join("");
            examFilter.value = cur;
            // Bootstrap select ilə zənginləşdirilibsə, dropdown-u yeni option-larla yenilə.
            if (typeof examFilter._refreshBootstrapSelect === "function") {
                examFilter._refreshBootstrapSelect();
            }
        }
        // Qarşılıqlı-istisna idarə (2026-07-29): zalda AKTİV imtahan gedirsə
        // yalnız "bitir", getmirsə yalnız "başlat" görünür. Beləliklə düymə
        // heç vaxt tamam itmir (bitirdikdən sonra "başlat" qayıdır), amma
        // ikisi eyni anda da durmur.
        var hasActive = sessions.some(function (s) { return s.state === "active"; });
        if (startAllBtn) startAllBtn.hidden = hasActive;
        if (endAllBtn) endAllBtn.hidden = !hasActive;
        if (openAllBtn) openAllBtn.hidden = true; // prepared oturumlar snapshot-da deyil; server yoxlayır
    }

    function matchesFilters(s) {
        var text = (filterInput && filterInput.value || "").trim().toLowerCase();
        var status = statusFilter && statusFilter.value;
        var exam = examFilter && examFilter.value;
        if (status) {
            // "Gözləyir" filtri texniki waiting+ready statuslarının İKİSİNİ də
            // tutur — operator üçün fərqləri yoxdur (ikisi də start gözləyir).
            var effective = s.status === "ready" ? "waiting" : s.status;
            if (effective !== status) return false;
        }
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
            mapEl.innerHTML = '<p class="fxc-muted fxc-center">' + esc(t("noResults", gettext("Nəticə yoxdur"))) + "</p>";
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
            // Biletli cəhd → çiyin-üstü snapshot (data-ticket). Biletsiz (PIN)
            // cəhd də klikə cavab versin deyə data-attempt qoyulur — pozuntu/
            // fəaliyyət detalları modalı açılır (əvvəllər klik nəzərə alınmırdı).
            var ticketAttrs = s.ticket_id
                ? 'data-ticket="' + esc(s.ticket_id) + '" data-session="' + esc(s.session_id) + '" '
                : "";
            var attemptAttr = s.attempt_id ? 'data-attempt="' + esc(s.attempt_id) + '" ' : "";
            return '<button type="button" class="fxc-cell fxc-cell--' + cellStateClass(s) + '" ' +
                ticketAttrs + attemptAttr +
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
            vioListEl.innerHTML = '<p class="fxc-vio-empty">' + esc(t("violations.empty", gettext("Qayda pozan yoxdur"))) + "</p>";
            return;
        }
        vioListEl.innerHTML = list.map(function (s) {
            var locked = s.supervision_status === "locked";
            var subj = (s.exam_title || "");
            if (subj.indexOf("—") !== -1) subj = subj.split("—").pop().trim();
            // Biletsiz (PIN) cəhdlər: bilet-əsaslı əməliyyat düymələri yoxdur —
            // pozuntu sayı yalnız məlumat üçün göstərilir.
            var detailBtn = s.attempt_id
                ? '<div class="fxc-vio-actions">' +
                    '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-ghost" data-vio-act="detail" ' +
                        'data-attempt="' + esc(s.attempt_id) + '">' +
                        '<i class="fas fa-eye"></i> ' + esc(t("violations.view", gettext("Bax"))) + "</button></div>"
                : "";
            if (!s.ticket_id) {
                // Biletsiz (PIN) cəhd — bilet əməliyyatı yoxdur, amma "Bax" ilə
                // hansı qaydaların pozulduğu detal modalında göstərilir.
                return '<div class="fxc-vio-row' + (locked ? " fxc-vio-row--locked" : "") + '">' +
                    '<div class="fxc-vio-top">' +
                        '<span class="fxc-vio-name">' + esc(s.name) + "</span>" +
                        '<span class="fxc-vio-count-badge">' + esc(s.violation_count || 0) + " " +
                            esc(t("violations.word", gettext("pozuntu"))) + "</span>" +
                    "</div>" +
                    '<div class="fxc-vio-sub">' + esc(subj) +
                        (locked ? ' · <b>' + esc(t("violations.locked", gettext("Dayandırılıb"))) + "</b>" : "") + "</div>" +
                    detailBtn +
                    "</div>";
            }
            var mainBtn = locked
                ? '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-success" data-vio-act="grant" ' +
                    'data-session="' + esc(s.session_id) + '" data-ticket="' + esc(s.ticket_id) + '">' +
                    '<i class="fas fa-rotate-left"></i> ' + esc(t("violations.grantChance", gettext("Şans ver"))) + "</button>"
                : '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-danger-ghost" data-vio-act="block" ' +
                    'data-session="' + esc(s.session_id) + '" data-ticket="' + esc(s.ticket_id) + '">' +
                    '<i class="fas fa-ban"></i> ' + esc(t("violations.block", gettext("Blokla"))) + "</button>";
            return '<div class="fxc-vio-row' + (locked ? " fxc-vio-row--locked" : "") + '">' +
                '<div class="fxc-vio-top">' +
                    '<span class="fxc-vio-name">' + esc(s.name) + "</span>" +
                    '<span class="fxc-vio-count-badge">' + esc(s.violation_count || 0) + " " +
                        esc(t("violations.word", gettext("pozuntu"))) + "</span>" +
                "</div>" +
                '<div class="fxc-vio-sub">' + esc(subj) +
                    (locked ? ' · <b>' + esc(t("violations.locked", gettext("Dayandırılıb"))) + "</b>" : "") + "</div>" +
                '<div class="fxc-vio-actions">' +
                    '<button type="button" class="fxc-btn fxc-btn-sm fxc-btn-ghost" data-vio-act="detail" ' +
                        'data-attempt="' + esc(s.attempt_id || "") + '">' +
                        '<i class="fas fa-eye"></i> ' + esc(t("violations.view", gettext("Bax"))) + "</button>" +
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
            wsEl.textContent = ok ? t("live", gettext("Canlı")) : t("disconnected", gettext("Bağlantı kəsildi"));
        }
        if (ok && updatedEl) {
            updatedEl.textContent = t("updatedAt", gettext("Yeniləndi")) + " " + new Date().toLocaleTimeString();
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
        post(startAllUrl, "").then(function (d) {
            if (d && d.success) { modalUi.close(); fetchSnapshot(); return; }
            modalUi.showError((d && d.error) || t("start.failed", gettext("Başlatmaq mümkün olmadı.")));
            modalUi.setLoading(false);
        }).catch(function () { modalUi.showError(t("start.failed", gettext("Başlatmaq mümkün olmadı."))); modalUi.setLoading(false); });
    }

    if (startAllBtn) {
        startAllBtn.addEventListener("click", function () {
            if (!window.FXCConfirm) {
                startAllBtn.disabled = true;
                post(startAllUrl).then(function () { fetchSnapshot(); }).finally(function () { startAllBtn.disabled = false; });
                return;
            }
            window.FXCConfirm.open({
                title: t("start.title", gettext("İmtahanı başlat")),
                message: t("confirmStartAll", gettext("Zaldakı bütün hazır imtahanlar eyni anda başladılsın?")),
                confirmText: t("start.confirm", gettext("Başlat")),
                confirmClass: "fxc-btn-success",
                onConfirm: function (state, modalUi) { doStartAll(modalUi); }
            });
        });
    }
    function doEndAll(modalUi) {
        modalUi.setLoading(true);
        modalUi.showError("");
        post(endAllUrl).then(function (d) {
            if (d && d.success) { modalUi.close(); fetchSnapshot(); return; }
            modalUi.showError((d && d.error) || t("end.failed", gettext("Bitirmək mümkün olmadı.")));
            modalUi.setLoading(false);
        }).catch(function () { modalUi.showError(t("end.failed", gettext("Bitirmək mümkün olmadı."))); modalUi.setLoading(false); });
    }

    if (endAllBtn) {
        endAllBtn.addEventListener("click", function () {
            if (!window.FXCConfirm) {
                if (!window.confirm(t("confirmEndAll", gettext("Zaldakı bütün aktiv imtahanlar bitirilsin? Bu əməliyyat geri qaytarıla bilməz.")))) return;
                endAllBtn.disabled = true;
                post(endAllUrl).then(function () { fetchSnapshot(); }).finally(function () { endAllBtn.disabled = false; });
                return;
            }
            window.FXCConfirm.open({
                title: t("end.title", gettext("İmtahanı bitir")),
                message: t("confirmEndAll", gettext("Zaldakı bütün aktiv imtahanlar bitirilsin? Bu əməliyyat geri qaytarıla bilməz.")),
                confirmText: t("end.confirm", gettext("Bitir")),
                confirmClass: "fxc-btn-danger",
                onConfirm: function (state, modalUi) { doEndAll(modalUi); }
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
            var cell = evt.target.closest(".fxc-cell");
            if (!cell) return;
            // Biletli → çiyin-üstü canlı snapshot; biletsiz (PIN) → pozuntu/
            // fəaliyyət detalları modalı (klik artıq nəzərə alınır).
            if (cell.dataset.ticket && window.FXCSnapshot) {
                window.FXCSnapshot.open(cell.dataset.session, cell.dataset.ticket);
            } else if (cell.dataset.attempt) {
                openViolationsModal(cell.dataset.attempt);
            }
        });
    }

    // Qayda pozanlar panelindəki əməliyyatlar: bax / şans ver (bərpa) / blokla.
    if (vioListEl) {
        vioListEl.addEventListener("click", function (evt) {
            var btn = evt.target.closest("[data-vio-act]");
            if (!btn) return;
            var sid = btn.dataset.session, tid = btn.dataset.ticket, act = btn.dataset.vioAct;
            if (act === "detail") {
                openViolationsModal(btn.dataset.attempt);
            } else if (act === "grant") {
                if (!window.confirm(t("violations.confirmGrant", gettext("Tələbəyə əlavə şans verilib imtahan bərpa edilsin?")))) return;
                btn.disabled = true;
                post(fillUrl(resumeTpl, sid, tid), "grant_extra_chance=1")
                    .then(function () { fetchSnapshot(); })
                    .catch(function () { btn.disabled = false; });
            } else if (act === "block") {
                var reason = window.prompt(t("violations.blockReason", gettext("Bloklama səbəbi:")));
                if (!reason) return;
                btn.disabled = true;
                post(fillUrl(removeTpl, sid, tid), "action=suspended&reason=" + encodeURIComponent(reason))
                    .then(function () { fetchSnapshot(); })
                    .catch(function () { btn.disabled = false; });
            }
        });
    }
    if (window.FXCSnapshot) window.FXCSnapshot.setOnChange(scheduleRefresh);

    // Pozuntu modalını bağla: backdrop / bağla düyməsi / Escape.
    if (vioModal) {
        vioModal.addEventListener("click", function (evt) {
            if (evt.target.closest("[data-vio-close]")) closeViolationsModal();
        });
        document.addEventListener("keydown", function (evt) {
            if (evt.key === "Escape" && !vioModal.hidden) closeViolationsModal();
        });
    }

    if (filterInput) filterInput.addEventListener("input", renderMap);
    if (statusFilter) statusFilter.addEventListener("change", renderMap);
    if (examFilter) examFilter.addEventListener("change", renderMap);

    renderAll();
    pollTimer = window.setInterval(fetchSnapshot, POLL_MS);
    void pollTimer;
})();

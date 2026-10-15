/*
 * «Yük bölgüsü» — təsdiqlənmiş bölgünün redaktəsi (düzəliş axını), fəaliyyətin çıxarılması,
 * bölgünün redaktəsi və «Redaktə et» keçidinin sətir fokusu (`window.EMSWorkloadAmend`).
 *
 * 2026-10-15 (sahib: «RİM ya da kafedra müdiri edit edə bilsin, çıxarda, əlavə edə»): düzəliş dialoqu
 * şablonda VAR idi, amma onu açan heç nə yox idi. İndi hər yazı əvvəl adi sorğu ilə gedir; server
 * `workload.amendment_required` (409) qaytarsa — sənəd təsdiqlənib — açıq modal bağlanır, düzəliş
 * dialoqu (səbəb + qeyd) açılır və EYNİ sorğu `amend_reason` / `amend_note` ilə təkrarlanır.
 * `workload.total_below_assigned` (409) — təsdiq soruşulur və sorğu `shrink_assignments=1` ilə
 * təkrarlanır (bölgü yeni cəmə sığdırılır). Bitəndə «Bölgünü təsdiqlə» sənədi yenidən bağlayır.
 *
 * Əsas vəziyyət `window.EMSWorkloadDist`-dən oxunur (əsas modul); burada fetch yalnız yazı üçündür.
 * AJAX-safe: `EMSDelegate.on` (bir dəfə) + DOM hər çağırışda yenidən axtarılır.
 */
(function (window, document) {
    "use strict";

    var gettext = window.gettext || function (value) { return value; };
    var PENDING = null;

    function dist() {
        return window.EMSWorkloadDist || null;
    }

    function q(selector) {
        var D = dist();
        return D ? D.q(selector) : null;
    }

    function fmt(template, params) {
        if (typeof window.interpolate === "function") return window.interpolate(template, params, true);
        return template.replace(/%\((\w+)\)s/g, function (_, key) {
            return params[key] == null ? "" : String(params[key]);
        });
    }

    function isShown(selector) {
        var node = q(selector);
        return !!(node && node.classList.contains("show"));
    }

    /** Açıq modal bağlanandan SONRA düzəliş dialoqu açılır (Bootstrap üst-üstə modalı sevmir). */
    function showAmend(fromSelector) {
        var D = dist();
        var form = q("[data-wl-amend-form]");
        if (form) {
            form.elements.note.value = "";
            form.elements.target_kind.value = "";
            form.elements.target_id.value = "";
        }
        D.showError(q("[data-wl-amend-error]"), "");
        var open = function () {
            var instance = D.modal("[data-wl-amend-modal]");
            if (instance) instance.show();
        };
        var from = fromSelector && isShown(fromSelector) ? q(fromSelector) : null;
        if (!from) {
            open();
            return;
        }
        from.addEventListener("hidden.bs.modal", open, { once: true });
        D.modal(fromSelector).hide();
    }

    function hideAmend() {
        var D = dist();
        var instance = D && D.modal("[data-wl-amend-modal]");
        if (instance && isShown("[data-wl-amend-modal]")) instance.hide();
    }

    /**
     * Yazı: `{url, data, modal?, error?, done}`. Səhv mesajı — düzəliş dialoqu açıqdırsa orada,
     * yoxsa `error` seçicisində, o da yoxdursa `alert`.
     */
    function write(opts) {
        var D = dist();
        return window.EMSCore.fetchJSON(opts.url, { method: "POST", data: opts.data })
            .then(function (result) {
                if (PENDING === opts) {
                    PENDING = null;
                    hideAmend();
                }
                if (opts.done) opts.done(result);
            })
            .catch(function (err) {
                var payload = (err && err.payload) || {};
                if (payload.error === "workload.amendment_required" && PENDING !== opts) {
                    PENDING = opts;
                    showAmend(opts.modal);
                    return;
                }
                if (payload.error === "workload.total_below_assigned" && !opts.data.shrink_assignments) {
                    var body = (payload.message || "") + " " +
                        gettext("Bölgü yeni cəmə uyğun azaldılsın (ən son təyinatdan başlayaraq)?");
                    window.EMSConfirm.open({ body: body, danger: true }).then(function (ok) {
                        if (!ok) return;
                        opts.data.shrink_assignments = "1";
                        write(opts);
                    });
                    return;
                }
                var message = D.messageFor(payload);
                var node = PENDING === opts ? q("[data-wl-amend-error]") : opts.error ? q(opts.error) : null;
                if (node) {
                    D.showError(node, message);
                } else {
                    window.alert(message);
                }
            });
    }

    function submitAmend() {
        var D = dist();
        var form = q("[data-wl-amend-form]");
        if (!D || !form) return;
        var reason = form.elements.reason.value;
        var note = (form.elements.note.value || "").trim();
        if (!reason || !note) {
            D.showError(q("[data-wl-amend-error]"), gettext("Səbəb və qeyd məcburidir."));
            return;
        }
        if (PENDING) {
            PENDING.data.amend_reason = reason;
            PENDING.data.amend_note = note;
            write(PENDING);
            return;
        }
        // Köhnə yol: hədəfi əvvəlcədən seçilmiş birbaşa düzəliş (`/duzelis/`).
        var host = D.root();
        if (!host || !D.state.task || !form.elements.target_id.value) return;
        var data = window.EMSWorkloadForms ? window.EMSWorkloadForms.values(form) : {};
        data.task_id = D.state.task.id;
        window.EMSCore.fetchJSON(host.dataset.amendUrl, { method: "POST", data: data })
            .then(function () {
                hideAmend();
                D.loadRows();
            })
            .catch(function (err) {
                D.showError(q("[data-wl-amend-error]"), D.messageFor(err && err.payload));
            });
    }

    /** Hər sətir yüklənişindən sonra: düzəliş zolağı + «Redaktə et» keçidinin sətrinə fokus (bir dəfə). */
    function afterRows() {
        var D = dist();
        if (!D) return;
        var banner = q("[data-wl-amend-banner]");
        var status = D.state.task ? D.state.task.status : "";
        if (banner) {
            var text = status === "distributed" ? banner.dataset.textDistributed :
                status === "amended" ? banner.dataset.textAmended : "";
            banner.textContent = text || "";
            banner.hidden = !text;
            banner.setAttribute("data-state", status);
        }
        var host = D.root();
        var focus = host ? host.dataset.focusRow : "";
        if (!focus || D.state.focusedRow === focus) return;
        var card = q('[data-wl-row][data-row-id="' + focus.replace(/[^0-9a-fA-F-]/g, "") + '"]');
        if (!card) return;
        D.state.focusedRow = focus;
        card.classList.add("is-focus");
        card.tabIndex = -1;
        if (card.scrollIntoView) card.scrollIntoView({ block: "center" });
        if (card.focus) card.focus({ preventScroll: true });
    }

    function bind() {
        var EMSDelegate = window.EMSDelegate;
        if (!EMSDelegate) return;

        EMSDelegate.on("click", "[data-wl-do-amend]", submitAmend);

        EMSDelegate.on("hidden.bs.modal", "[data-wl-amend-modal]", function () {
            PENDING = null; // dialoq səbəbsiz bağlandı — gözləyən sorğu atılır
        });

        EMSDelegate.on("click", "[data-wl-activity-remove]", function (event, btn) {
            var D = dist();
            var host = D && D.root();
            if (!host || !D.state.task) return;
            var body = fmt(gettext("«%(activity)s» sətirdən çıxarılsın? Bu fəaliyyətin bölgüsü də silinəcək."), {
                activity: btn.dataset.activityLabel || btn.dataset.activity,
            });
            window.EMSConfirm.open({ body: body, danger: true }).then(function (ok) {
                if (!ok) return;
                write({
                    url: host.dataset.saveRowUrl,
                    data: { task_id: D.state.task.id, row_id: btn.dataset.rowId, activity_remove: btn.dataset.activity },
                    done: D.loadRows,
                });
            });
        });

        EMSDelegate.on("click", "[data-wl-assign-edit]", function (event, btn) {
            var D = dist();
            if (D) D.openAssign(btn.dataset.rowId, btn.dataset.assignmentId);
        });
    }

    window.EMSWorkloadAmend = { write: write, afterRows: afterRows };

    if (window.EMSReady) {
        window.EMSReady.once("workload-distribution-amend-bind", bind);
    }
})(window, document);

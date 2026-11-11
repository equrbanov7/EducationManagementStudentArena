/*
 * «Yük bölgüsü» — «Bölgünü təsdiqlə» dialoqu (`window.EMSWorkloadConfirm`).
 *
 * Sahib 2026-11-12: «kimsə təyin olunmasa, mən bölgünü təsdiqləyəndə aydın info versin və "aydındır"
 * deyəndən sonra təsdiqlənsin, onda vakantda qalsın». Dialoq tapşırığın BÜTÜN sətirləri üzrə hazırlığı
 * (`readiness`) oxuyur və natamam sətirləri fənnə görə qruplaşdırıb göstərir (qruplar · fəaliyyət üzrə qalıq
 * saat · ixtisas). Natamam sətir varsa düymə «Aydındır, Vakant saxla və təsdiqlə» olur və YALNIZ
 * «Aydındır» qutusu işarələnəndən sonra aktivləşir; sorğu `fill_vacant=1` ilə gedir. Artıq bölgü
 * (bölünmüş saat > cəm) sərt maneədir — düymə bağlı qalır. Fənnin adına klik — siyahı həmin fənnə görə süzülür.
 *
 * Əsas vəziyyət `window.EMSWorkloadDist`-dən oxunur. AJAX-safe: `EMSDelegate.on` (bir dəfə, delegated) +
 * DOM hər çağırışda yenidən axtarılır.
 */
(function (window, document) {
    "use strict";

    var gettext = window.gettext || function (value) { return value; };

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

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    /** «Mühazirə 30 s, Seminar 15 s» — qalıq (və ya artıq) saatlar. */
    function gapText(item, over) {
        return (item.gaps || [])
            .filter(function (gap) { return over ? gap.over > 0 : gap.remaining > 0; })
            .map(function (gap) {
                return fmt(gettext("%(label)s %(hours)s s"), { label: gap.label, hours: over ? gap.over : gap.remaining });
            })
            .join(", ");
    }

    function stateText(item) {
        var untouched = Object.keys(item.activities || {}).every(function (key) {
            return !(item.activities[key] || {}).assigned;
        });
        return untouched ? gettext("müəllim yoxdur") : gettext("qismən bölünüb");
    }

    /** Fənnə görə qruplaşdırılmış siyahı: fənn başlığı (süzgəc düyməsi) + sətir-sətir qruplar/qalıq/ixtisas. */
    function renderRows(host, items, over) {
        if (!host) return;
        var bySubject = {};
        var order = [];
        items.forEach(function (item) {
            if (!bySubject[item.subject]) {
                bySubject[item.subject] = [];
                order.push(item.subject);
            }
            bySubject[item.subject].push(item);
        });
        host.innerHTML = order
            .map(function (subject) {
                var lines = bySubject[subject]
                    .map(function (item) {
                        var tail = over
                            ? fmt(gettext("artıq: %(hours)s"), { hours: gapText(item, true) })
                            : gapText(item, false) + " — " + stateText(item);
                        return (
                            '<li class="wl-confirm__line">' +
                            '<span class="wl-confirm__groups">' + esc(item.groups || "—") + "</span> · " +
                            esc(tail) +
                            (item.specialty ? ' <span class="wl-confirm__specialty">' + esc(item.specialty) + "</span>" : "") +
                            "</li>"
                        );
                    })
                    .join("");
                return (
                    '<li class="wl-confirm__subject">' +
                    '<button type="button" class="wl-confirm__subject-btn" data-wl-confirm-subject="' + esc(subject) + '">' +
                    esc(subject) + "</button>" +
                    '<ul class="wl-confirm__lines">' + lines + "</ul></li>"
                );
            })
            .join("");
    }

    function button() {
        return q("[data-wl-do-confirm]");
    }

    /** Düymənin mətni + aktivliyi hazırlıqdan və «Aydındır» qutusundan asılıdır. */
    function syncButton() {
        var D = dist();
        var btn = button();
        if (!D || !btn) return;
        var readiness = D.state.readiness;
        var incomplete = (readiness && readiness.incomplete_rows) || [];
        var over = incomplete.filter(function (item) { return item.is_over; });
        var ack = q("[data-wl-confirm-ack]");
        var needsAck = incomplete.length > 0;
        btn.textContent = needsAck ? btn.dataset.labelVacant : btn.dataset.labelPlain;
        btn.disabled = !readiness || over.length > 0 || (needsAck && !(ack && ack.checked));
    }

    function render(readiness) {
        var D = dist();
        if (!D) return;
        D.state.readiness = readiness || null;
        var Render = window.EMSWorkloadRender;
        if (Render) Render.readiness(q("[data-wl-confirm-stats]"), readiness || null);
        var incomplete = (readiness && readiness.incomplete_rows) || [];
        var over = incomplete.filter(function (item) { return item.is_over; });
        var gaps = incomplete.filter(function (item) { return !item.is_over; });
        var gapsBox = q("[data-wl-confirm-gaps]");
        if (gapsBox) gapsBox.hidden = !gaps.length || over.length > 0;
        var title = q("[data-wl-confirm-gaps-title]");
        if (title) {
            title.textContent = fmt(gettext("%(count)s sətirdə %(hours)s saat müəllimə bölünməyib:"), {
                count: gaps.length,
                hours: readiness ? readiness.unassigned_hours || 0 : 0,
            });
        }
        renderRows(q("[data-wl-confirm-rows]"), gaps, false);
        var blocker = q("[data-wl-confirm-blocker]");
        if (blocker) blocker.hidden = !over.length;
        renderRows(q("[data-wl-confirm-over]"), over, true);
        var ack = q("[data-wl-confirm-ack]");
        if (ack) ack.checked = false;
        syncButton();
    }

    function open() {
        var D = dist();
        if (!D) return;
        var host = D.root();
        render(null);
        D.showError(q("[data-wl-confirm-error]"), "");
        // Sətirlər dilimlə gəldiyi üçün hazırlıq xülasəsi tapşırığın HAMISI üzrə ayrıca soruşulur.
        if (host && window.EMSWorkloadList) {
            window.EMSWorkloadList.loadReadiness(host.dataset.rowsUrl, D.filters()).then(render, function () {
                D.showError(q("[data-wl-confirm-error]"), gettext("Əməliyyat alınmadı."));
            });
        }
        var instance = D.modal("[data-wl-confirm-modal]");
        if (instance) instance.show();
    }

    function submit() {
        var D = dist();
        var host = D ? D.root() : null;
        var btn = button();
        if (!host || !D.state.task || (btn && btn.disabled)) return;
        var readiness = D.state.readiness;
        var fill = !!(readiness && (readiness.incomplete_rows || []).length);
        var data = { task_id: D.state.task.id, allow_vacant: "1" };
        if (fill) data.fill_vacant = "1";
        if (btn) btn.disabled = true;
        window.EMSCore.fetchJSON(host.dataset.confirmUrl, { method: "POST", data: data })
            .then(function (payload) {
                var instance = D.modal("[data-wl-confirm-modal]");
                if (instance) instance.hide();
                var sync = payload.sync || {};
                var vacant = payload.vacant_filled || {};
                var text = fmt(
                    gettext("Bölgü təsdiqləndi. Jurnal açılışı: %(created)s yeni, %(updated)s yeniləndi. Bildiriş: %(notified)s"),
                    { created: sync.created || 0, updated: sync.updated || 0, notified: payload.notified || 0 }
                );
                if (vacant.hours) {
                    text += "\n" + fmt(gettext("«Vakant» saxlanıldı: %(hours)s saat (%(rows)s sətir)."), {
                        hours: vacant.hours,
                        rows: vacant.rows || 0,
                    });
                }
                window.alert(text);
                D.loadRows();
            })
            .catch(function (err) {
                var payload = err && err.payload;
                if (payload && payload.readiness) render(payload.readiness); // vəziyyət dəyişib — siyahını yenilə
                else syncButton();
                D.showError(q("[data-wl-confirm-error]"), D.messageFor(payload));
            });
    }

    /** Fənnin adına klik — dialoq bağlanır, sətirlər həmin fənnə görə süzülür (axtarış qutusu). */
    function focusSubject(subject) {
        var D = dist();
        if (!D) return;
        var instance = D.modal("[data-wl-confirm-modal]");
        if (instance) instance.hide();
        var search = q("[data-wl-search]");
        if (!search) return;
        if (window.EMSSearchInput && window.EMSSearchInput.cancel) window.EMSSearchInput.cancel(search);
        search.value = subject;
        D.loadRows({ fresh: true });
        search.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function bind() {
        if (!window.EMSDelegate) return;
        window.EMSDelegate.on("click", "[data-wl-open-confirm]", open);
        window.EMSDelegate.on("click", "[data-wl-do-confirm]", submit);
        window.EMSDelegate.on("change", "[data-wl-confirm-ack]", syncButton);
        window.EMSDelegate.on("click", "[data-wl-confirm-subject]", function (event, btn) {
            focusSubject(btn.dataset.wlConfirmSubject || "");
        });
    }

    if (window.EMSReady && window.EMSReady.once) window.EMSReady.once("workload-distribution-confirm-bind", bind);

    window.EMSWorkloadConfirm = { open: open, render: render };
})(window, document);

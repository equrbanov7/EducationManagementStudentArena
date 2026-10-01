/* =========================================================================
   İmtahan zalı bayrağı — «İmtahan zalı kimi qeyd et» / «İmtahan zallarından
   çıxar» (sahib 2026-10-01).

   İşlədildiyi yerlər: İmtahan Nəzarət Sistemi → zallar
   (`exams/exam_center/room_list.html`) və kabinet «İmtahan zalları» bölməsi.
   Düymə şablonu: `exams/exam_center/halls/_toggle.html`.

   Axın: POST JSON {is_exam_hall, confirm} → `EMSCore.fetchJSON` (CSRF başlığı
   avtomatik). 200 → yerində yenilə (düymə, `[data-hall-item]` kökü, nişanlar,
   korpus sayğacı ±1, KPI dəqiq dəyər). 409 `needs_confirm` → `EMSConfirm`
   (planlaşdırılmış oturum) → `confirm: true` ilə təkrar. Digər 409 (canlı
   oturum / aktiv kompüter) və xətalar → `EMSToast`. Bütün mətnlər serverdən və
   ya düymənin data-atributlarından gəlir (xarici JS tərcümə olunmur).

   AJAX-SAFE: yalnız sənəd səviyyəli `EMSDelegate`; idempotent IIFE.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSExamHallToggle) {
        return;
    }
    var DELEGATE = window.EMSDelegate;
    var CORE = window.EMSCore;
    if (!DELEGATE || !CORE || typeof CORE.fetchJSON !== "function") {
        return;
    }
    window.EMSExamHallToggle = { version: 1 };

    function toast(message, level) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, level);
        }
    }

    function ask(btn, message) {
        var options = {
            title: btn.getAttribute("data-confirm-title") || "",
            body: message || "",
            confirmLabel: btn.getAttribute("data-confirm-ok") || undefined,
            danger: true,
        };
        if (window.EMSConfirm && typeof window.EMSConfirm.open === "function") {
            return window.EMSConfirm.open(options);
        }
        return Promise.resolve(window.confirm(message || ""));
    }

    function setHidden(nodes, hidden) {
        for (var i = 0; i < nodes.length; i += 1) {
            nodes[i].hidden = hidden;
        }
    }

    function bump(node, delta) {
        if (!node) {
            return;
        }
        var value = parseInt(node.textContent, 10);
        if (!isNaN(value)) {
            node.textContent = String(Math.max(0, value + delta));
        }
    }

    function applyState(btn, isHall, hallCount) {
        var wasHall = btn.getAttribute("data-hall") === "1";
        var flag = isHall ? "1" : "0";
        // Kök: kart/plitə (`[data-hall-item]`) və ya kabinet cədvəlinin sətri (`tr`).
        var item = btn.closest("[data-hall-item]") || btn.closest("tr");
        btn.setAttribute("data-hall", flag);
        if (item) {
            item.setAttribute("data-hall", flag);
            setHidden(item.querySelectorAll("[data-hall-badge]"), !isHall);
            setHidden(item.querySelectorAll("[data-hall-badge-off]"), isHall);
        }
        var label = btn.querySelector("[data-exam-hall-label]");
        if (label) {
            label.textContent = btn.getAttribute(isHall ? "data-label-unmark" : "data-label-mark") || label.textContent;
        }
        var icon = btn.querySelector("[data-exam-hall-icon]");
        if (icon) {
            icon.classList.toggle("fa-circle-minus", isHall);
            icon.classList.toggle("fa-circle-plus", !isHall);
        }
        if (wasHall !== isHall) {
            var group = btn.closest("[data-hall-group]");
            bump(group ? group.querySelector("[data-hall-count]") : null, isHall ? 1 : -1);
        }
        if (typeof hallCount === "number") {
            var kpis = document.querySelectorAll('[data-hall-kpi], [data-ems-kpi-key="exam-halls"] .ems-kpi__value');
            for (var i = 0; i < kpis.length; i += 1) {
                kpis[i].textContent = String(hallCount);
            }
        }
    }

    function send(btn, wantHall, confirmed) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        return CORE.fetchJSON(btn.getAttribute("data-url"), {
            method: "POST",
            data: { is_exam_hall: wantHall, confirm: Boolean(confirmed) },
        })
            .then(function (payload) {
                payload = payload || {};
                applyState(btn, Boolean(payload.is_exam_hall), payload.hall_count);
                toast(payload.message, "success");
            })
            .catch(function (err) {
                var payload = (err && err.payload && typeof err.payload === "object") ? err.payload : {};
                if (err && err.status === 409 && payload.needs_confirm && !confirmed) {
                    return ask(btn, payload.message).then(function (ok) {
                        return ok ? send(btn, wantHall, true) : null;
                    });
                }
                if (err && err.status === 403 && payload.view_as_blocked) {
                    return null; // səbəb mərkəzdə (EMSCore) göstərilib
                }
                toast(payload.message || btn.getAttribute("data-error") || "", err && err.status === 409 ? "warning" : "error");
                return null;
            })
            .then(function () {
                btn.disabled = false;
                btn.removeAttribute("aria-busy");
            });
    }

    DELEGATE.on("click", "[data-exam-hall-toggle]", function (event, btn) {
        event.preventDefault();
        if (btn.disabled || !btn.getAttribute("data-url")) {
            return;
        }
        send(btn, btn.getAttribute("data-hall") !== "1", false);
    });
})(window, document);

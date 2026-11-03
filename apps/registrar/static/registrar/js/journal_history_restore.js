/**
 * «Bu müəllimə bərpa et» — jurnal siyahısının tarixçə sətri (sahib 2026-11-03).
 * Source: registrar/partials/_journal_history_restore.html + _journal_history_restore_modal.html
 *
 * Sətirdəki düymə (`data-jl-hrestore-open`) modalı açır: nə dəyişəcəyi sətrin gizli siyahısından
 * (`data-jl-hrestore-steps`) köçürülür, səbəb məcburidir. Uğurdan sonra səhifə yenilənir — sətir
 * «Cari dərs yüküm»ə keçir. Xəta mesajı serverdəndir (sorğunun dilində).
 *
 * AJAX-SAFE: yalnız `EMSDelegate.on` (document səviyyəsində), bir dəfə bağlanır; URL düymənin
 * data-atributundadır; yazı `EMSCore.fetchJSON` ilə (CSRF başlığı avtomatik).
 */
(function (window, document) {
    "use strict";

    if (window.__jlHistoryRestoreBound) return;
    window.__jlHistoryRestoreBound = true;

    var state = { url: "", busy: false, lastFocused: null };

    function modalEl() {
        return document.querySelector("[data-jl-hrestore-modal]");
    }

    function part(modal, hook) {
        return modal ? modal.querySelector("[" + hook + "]") : null;
    }

    function setError(modal, text) {
        var box = part(modal, "data-jl-hrestore-error");
        if (!box) return;
        box.textContent = text || "";
        box.hidden = !text;
    }

    function openModal(button) {
        var modal = modalEl();
        if (!modal) return;
        state.url = button.getAttribute("data-url") || "";
        state.lastFocused = button;
        var subject = part(modal, "data-jl-hrestore-subject");
        var group = part(modal, "data-jl-hrestore-group");
        if (subject) subject.textContent = button.getAttribute("data-subject") || "";
        if (group) group.textContent = button.getAttribute("data-group") || "";
        var plan = part(modal, "data-jl-hrestore-plan");
        var source = button.parentNode ? button.parentNode.querySelector("[data-jl-hrestore-steps]") : null;
        if (plan) {
            while (plan.firstChild) plan.removeChild(plan.firstChild);
            if (source) {
                Array.prototype.forEach.call(source.children, function (item) {
                    plan.appendChild(item.cloneNode(true));
                });
            }
        }
        var reason = part(modal, "data-jl-hrestore-reason");
        if (reason) reason.value = "";
        setError(modal, "");
        modal.hidden = false;
        if (reason) reason.focus();
    }

    function closeModal() {
        var modal = modalEl();
        if (!modal || modal.hidden || state.busy) return;
        modal.hidden = true;
        state.url = "";
        if (state.lastFocused && document.contains(state.lastFocused)) state.lastFocused.focus();
        state.lastFocused = null;
    }

    function submit(button) {
        var modal = modalEl();
        if (!modal || state.busy || !state.url) return;
        var reason = part(modal, "data-jl-hrestore-reason");
        state.busy = true;
        button.disabled = true;
        setError(modal, "");
        window.EMSCore.fetchJSON(state.url, { method: "POST", data: { reason: reason ? reason.value : "" } })
            .then(function (payload) {
                if (payload && payload.message && window.EMSToast && typeof window.EMSToast.show === "function") {
                    window.EMSToast.show(payload.message, "success");
                }
                window.location.reload();
            })
            .catch(function (err) {
                var payload = err && err.payload;
                var text = payload && typeof payload === "object" && payload.message;
                setError(modal, text || modal.getAttribute("data-generic-error") || "Error");
                state.busy = false;
                button.disabled = false;
            });
    }

    var delegate = window.EMSDelegate;
    if (!delegate || typeof delegate.on !== "function" || !window.EMSCore) return;
    delegate.on("click", "[data-jl-hrestore-open]", function (event, button) {
        event.preventDefault();
        openModal(button);
    });
    delegate.on("click", "[data-jl-hrestore-close]", function (event) {
        event.preventDefault();
        closeModal();
    });
    delegate.on("click", "[data-jl-hrestore-submit]", function (event, button) {
        event.preventDefault();
        submit(button);
    });
    delegate.on("keydown", "[data-jl-hrestore-modal]", function (event) {
        if (event.key === "Escape") closeModal();
    });
})(window, document);

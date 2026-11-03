/**
 * «Bu müəllimə bərpa et» — jurnal siyahısının tarixçə sətri (sahib 2026-11-03).
 * Source: registrar/partials/_journal_history_restore.html + _journal_history_restore_modal.html
 *
 * Sətirdəki düymə (`data-jl-hrestore-open`) modalı açır: nə dəyişəcəyi sətrin gizli siyahısından
 * (`data-jl-hrestore-steps`) köçürülür. İndiki sahib sonradan yazıbsa xəbərdarlıq + məcburi səbəb, yazmayıbsa
 * səbəb istəyə bağlıdır (sahib 2026-11-04). Admin siyahısında müəllim `data-teacher-id`-dən POST-a gedir. Uğurdan sonra səhifə yenilənir — sətir
 * «Cari dərs yüküm»ə keçir. Xəta mesajı serverdəndir (sorğunun dilində).
 *
 * AJAX-SAFE: yalnız `EMSDelegate.on` (document səviyyəsində), bir dəfə bağlanır; URL düymənin
 * data-atributundadır; yazı `EMSCore.fetchJSON` ilə (CSRF başlığı avtomatik).
 */
(function (window, document) {
    "use strict";

    if (window.__jlHistoryRestoreBound) return;
    window.__jlHistoryRestoreBound = true;

    var state = { url: "", teacher: "", busy: false, lastFocused: null };

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

    function copyList(target, source) {
        if (!target) return;
        while (target.firstChild) target.removeChild(target.firstChild);
        if (!source) return;
        Array.prototype.forEach.call(source.children, function (item) {
            target.appendChild(item.cloneNode(true));
        });
    }

    function setText(modal, hook, value) {
        var node = part(modal, hook);
        if (node) node.textContent = value || "";
    }

    function openModal(button) {
        var modal = modalEl();
        if (!modal) return;
        var row = button.parentNode;
        state.url = button.getAttribute("data-url") || "";
        state.teacher = button.getAttribute("data-teacher-id") || "";
        state.lastFocused = button;
        setText(modal, "data-jl-hrestore-teacher", button.getAttribute("data-teacher"));
        setText(modal, "data-jl-hrestore-subject", button.getAttribute("data-subject"));
        setText(modal, "data-jl-hrestore-group", button.getAttribute("data-group"));
        copyList(part(modal, "data-jl-hrestore-plan"), row ? row.querySelector("[data-jl-hrestore-steps]") : null);
        // İndiki sahib sonradan yazıbsa: kim/nə qədər/nə vaxtdan + səbəb məcburi; yazmayıbsa səbəb istəyə bağlı.
        var written = button.getAttribute("data-written-since") === "1";
        copyList(part(modal, "data-jl-hrestore-warnlist"), row ? row.querySelector("[data-jl-hrestore-warnings]") : null);
        var box = part(modal, "data-jl-hrestore-warnbox");
        var required = part(modal, "data-jl-hrestore-required");
        var optional = part(modal, "data-jl-hrestore-optional");
        if (box) box.hidden = !written;
        if (required) required.hidden = !written;
        if (optional) optional.hidden = written;
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
        state.teacher = "";
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
        var data = { reason: reason ? reason.value : "", teacher: state.teacher };
        window.EMSCore.fetchJSON(state.url, { method: "POST", data: data })
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

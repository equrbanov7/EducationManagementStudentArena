/**
 * «Fəndən azad et» / «Bərpa et» — jurnal səhifəsi (sahib 2026-10-15).
 *
 * Tələbə qrupda qalır, yalnız BU fənnin jurnalından çıxır. Sətirdəki düymə (`data-jse-open`)
 * modalı açır; səbəb və sənəd istəyə bağlıdır. «Azad edilənlər» siyahısındakı «Bərpa et»
 * iki addımlıdır (birinci klik təsdiq istəyir). Uğurdan sonra səhifə yenilənir — cədvəl,
 * sayğaclar və siyahı server tərəfdə yenidən qurulur.
 *
 * AJAX-SAFE: yalnız `EMSDelegate.on` (document səviyyəsində, yığılmır); URL-lər modalın
 * data-atributlarındadır; yazılar `EMSCore.fetchJSON` ilə (CSRF başlığı avtomatik).
 */
(function (window, document) {
    "use strict";

    var CONFIRM = "is-confirm";
    var state = { enrollment: "", busy: false, lastFocused: null };

    function modalEl() {
        return document.querySelector("[data-jse-modal]");
    }

    function field(modal, hook) {
        return modal ? modal.querySelector("[" + hook + "]") : null;
    }

    function setError(modal, text) {
        var box = field(modal, "data-jse-error");
        if (!box) return;
        box.textContent = text || "";
        box.hidden = !text;
    }

    function errorText(modal, err) {
        var payload = err && err.payload;
        if (payload && typeof payload === "object" && payload.message) return payload.message;
        return (modal && modal.getAttribute("data-generic-error")) || "Error";
    }

    function openModal(button) {
        var modal = modalEl();
        if (!modal) return;
        state.enrollment = button.getAttribute("data-jse-open") || "";
        state.lastFocused = button;
        var name = field(modal, "data-jse-student-name");
        if (name) name.textContent = button.getAttribute("data-jse-student") || "";
        ["data-jse-reason", "data-jse-doc-number", "data-jse-doc-date"].forEach(function (hook) {
            var input = field(modal, hook);
            if (input) input.value = "";
        });
        setError(modal, "");
        modal.hidden = false;
        var reason = field(modal, "data-jse-reason");
        if (reason) reason.focus();
    }

    function closeModal() {
        var modal = modalEl();
        if (!modal || modal.hidden) return;
        modal.hidden = true;
        setError(modal, "");
        state.enrollment = "";
        if (state.lastFocused && document.contains(state.lastFocused)) state.lastFocused.focus();
        state.lastFocused = null;
    }

    function post(url, data) {
        return window.EMSCore.fetchJSON(url, { method: "POST", data: data });
    }

    function submit(button) {
        var modal = modalEl();
        if (!modal || state.busy || !state.enrollment) return;
        var value = function (hook) {
            var input = field(modal, hook);
            return input ? input.value : "";
        };
        state.busy = true;
        button.disabled = true;
        setError(modal, "");
        post(modal.getAttribute("data-apply-url"), {
            enrollment: state.enrollment,
            reason: value("data-jse-reason"),
            doc_number: value("data-jse-doc-number"),
            doc_date: value("data-jse-doc-date"),
        })
            .then(function () {
                window.location.reload();
            })
            .catch(function (err) {
                setError(modal, errorText(modal, err));
                state.busy = false;
                button.disabled = false;
            });
    }

    function restore(button) {
        var modal = modalEl();
        if (!modal || state.busy) return;
        var label = button.querySelector("[data-jse-restore-label]");
        if (!button.classList.contains(CONFIRM)) {
            button.classList.add(CONFIRM);
            if (label) {
                button.dataset.jseLabel = label.textContent;
                label.textContent = modal.getAttribute("data-confirm-label") || "?";
            }
            return;
        }
        state.busy = true;
        button.disabled = true;
        post(modal.getAttribute("data-restore-url"), { decision: button.getAttribute("data-jse-restore") })
            .then(function () {
                window.location.reload();
            })
            .catch(function (err) {
                state.busy = false;
                button.disabled = false;
                button.classList.remove(CONFIRM);
                if (label && button.dataset.jseLabel) label.textContent = button.dataset.jseLabel;
                var message = errorText(modal, err);
                if (window.EMSToast && typeof window.EMSToast.show === "function") {
                    window.EMSToast.show(message, "error");
                } else {
                    button.title = message;
                }
            });
    }

    function boot() {
        var delegate = window.EMSDelegate;
        if (!delegate || typeof delegate.on !== "function" || !window.EMSCore) return;
        delegate.on("click", "[data-jse-open]", function (event, button) {
            event.preventDefault();
            openModal(button);
        });
        delegate.on("click", "[data-jse-close]", function (event) {
            event.preventDefault();
            closeModal();
        });
        delegate.on("click", "[data-jse-submit]", function (event, button) {
            event.preventDefault();
            submit(button);
        });
        delegate.on("click", "[data-jse-restore]", function (event, button) {
            event.preventDefault();
            restore(button);
        });
        delegate.on("keydown", "[data-jse-modal]", function (event) {
            if (event.key === "Escape") closeModal();
        });
    }

    // Bir dəfə qeydiyyat (delegasiya document səviyyəsindədir — AJAX swap-dan sonra da işləyir).
    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("journal-subject-exempt", boot);
    } else if (!window.__jseBooted) {
        window.__jseBooted = true;
        boot();
    }
})(window, document);

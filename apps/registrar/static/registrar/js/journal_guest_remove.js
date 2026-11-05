/**
 * Alt qrupdan əlavə olunmuş tələbənin «Çıxar»-ı — səbəb paneli (sahib 2026-11-04).
 *
 * «Çıxar» (`data-jgs-remove`) dərhal silmir: modalın içindəki panel (`data-jgs-remove-panel`) açılır,
 * çıxarılma səbəbi siyahıdan MƏCBURİ seçilir («Digər» üçün qeyd də — journal_removal_reason.js), yalnız
 * «Jurnaldan çıxar» təsdiqindən sonra POST gedir. Uğurdan sonra cədvəl və siyahı yerində yenilənir
 * (journal_guest.js-in `window.EMSJournalGuest.refreshInPlace`). Server eyni qaydanı yenidən yoxlayır.
 *
 * AJAX-SAFE: hadisələr `EMSDelegate.on` ilə document səviyyəsində BİR dəfə bağlanır; hər klikdə modal
 * DOM-dan yenidən tapılır (null-safe).
 */
(function (window, document) {
    "use strict";

    var BUSY = "is-busy";

    function modalEl() {
        return document.querySelector("[data-jgs-modal]");
    }

    function guest() {
        return window.EMSJournalGuest || null;
    }

    function setError(modal, message) {
        var api = guest();
        if (api) api.setError(modal, message);
    }

    function panelOf(modal) {
        return modal ? modal.querySelector("[data-jgs-remove-panel]") : null;
    }

    function openPanel(button) {
        var modal = modalEl();
        var panel = panelOf(modal);
        var enrollmentId = button.getAttribute("data-jgs-remove") || "";
        if (!panel || !enrollmentId) return;
        var item = button.closest("[data-jgs-item]");
        var nameEl = item ? item.querySelector(".jgs-current-name") : null;
        var target = panel.querySelector("[data-jgs-remove-name]");
        if (target) target.textContent = nameEl ? nameEl.textContent : "";
        panel.setAttribute("data-enrollment", enrollmentId);
        if (window.EMSJournalRemovalReason) window.EMSJournalRemovalReason.reset(panel);
        setError(modal, "");
        panel.hidden = false;
        if (panel.scrollIntoView) panel.scrollIntoView({ block: "nearest" });
        var select = panel.querySelector("[data-jrr-reason]");
        if (select) select.focus();
    }

    function closePanel() {
        var panel = panelOf(modalEl());
        if (!panel) return;
        panel.hidden = true;
        panel.removeAttribute("data-enrollment");
    }

    function submit(trigger) {
        var modal = modalEl();
        var panel = panelOf(modal);
        var api = guest();
        var enrollmentId = panel ? panel.getAttribute("data-enrollment") || "" : "";
        if (!enrollmentId || !api || !window.EMSCore) return;
        var removal = window.EMSJournalRemovalReason
            ? window.EMSJournalRemovalReason.read(panel)
            : { reason: "", note: "", error: "" };
        if (removal.error) {
            setError(modal, removal.error);
            return;
        }
        var item = modal.querySelector('[data-jgs-item="' + enrollmentId + '"]');
        if (item) item.classList.add(BUSY);
        trigger.disabled = true;
        setError(modal, "");
        window.EMSCore.fetchJSON(api.attr(modal, "data-remove-url"), {
            method: "POST",
            data: { enrollment: enrollmentId, removal_reason: removal.reason, removal_note: removal.note },
        })
            .then(function (payload) {
                trigger.disabled = false;
                closePanel();
                api.refreshInPlace(modal, null, (payload && payload.message) || api.attr(modal, "data-removed-message"));
            })
            .catch(function (err) {
                if (item) item.classList.remove(BUSY);
                trigger.disabled = false;
                setError(modal, api.errorText(err));
            });
    }

    function boot() {
        var delegate = window.EMSDelegate;
        if (!delegate || typeof delegate.on !== "function") return;
        delegate.on("click", "[data-jgs-remove]", function (event, button) {
            event.preventDefault();
            openPanel(button);
        });
        delegate.on("click", "[data-jgs-remove-cancel]", function (event) {
            event.preventDefault();
            closePanel();
        });
        delegate.on("click", "[data-jgs-remove-confirm]", function (event, button) {
            event.preventDefault();
            submit(button);
        });
    }

    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("journal-guest-remove", boot);
    } else if (!window.__jgsRemoveBooted) {
        window.__jgsRemoveBooted = true;
        boot();
    }
})(window, document);

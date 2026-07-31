/**
 * Standart təsdiq modalı — brauzerin window.confirm/alert-i əvəzinə.
 * window.FXCConfirm.open(opts) ilə çağırılır; kənara klik / Escape / İmtina ilə
 * bağlanır. onConfirm(state, ui) geri-çağırışında POST + xəta idarəsi edilir.
 */
(function () {
    "use strict";

    var modal = document.getElementById("fxc-confirm-modal");
    if (!modal) return;

    var titleText = document.getElementById("fxc-confirm-title-text");
    var messageEl = document.getElementById("fxc-confirm-message");
    var errorEl = document.getElementById("fxc-confirm-error");
    var okBtn = document.getElementById("fxc-confirm-ok");
    var overrideWrap = document.getElementById("fxc-confirm-override-wrap");
    var overrideChk = document.getElementById("fxc-confirm-override");
    var overrideLabel = document.getElementById("fxc-confirm-override-label");
    var current = null;

    function close() { modal.hidden = true; current = null; }
    function showError(msg) { if (errorEl) { errorEl.textContent = msg || ""; errorEl.hidden = !msg; } }
    function setLoading(b) { if (okBtn) okBtn.disabled = !!b; }
    function showOverride(label) {
        if (overrideLabel) overrideLabel.textContent = label || "";
        if (overrideWrap) overrideWrap.hidden = false;
    }

    var ui = { showError: showError, showOverride: showOverride, setLoading: setLoading, close: close };

    function open(opts) {
        current = opts || {};
        if (titleText) titleText.textContent = current.title || "";
        if (messageEl) messageEl.textContent = current.message || "";
        if (okBtn) {
            okBtn.textContent = current.confirmText || gettext("Təsdiqlə");
            okBtn.className = "fxc-btn " + (current.confirmClass || "fxc-btn-primary");
        }
        showError("");
        setLoading(false);
        if (overrideWrap) { overrideWrap.hidden = true; }
        if (overrideChk) { overrideChk.checked = false; }
        modal.hidden = false;
    }

    if (okBtn) {
        okBtn.addEventListener("click", function () {
            if (!current || typeof current.onConfirm !== "function") { close(); return; }
            current.onConfirm({ override: !!(overrideChk && overrideChk.checked) }, ui);
        });
    }

    // Kənara (backdrop) klik VƏ ya İmtina → bağla.
    modal.addEventListener("click", function (evt) {
        if (evt.target.closest("[data-confirm-cancel]") || evt.target === modal) close();
    });
    document.addEventListener("keydown", function (evt) {
        if (evt.key === "Escape" && !modal.hidden) close();
    });

    window.FXCConfirm = { open: open, close: close };
})();

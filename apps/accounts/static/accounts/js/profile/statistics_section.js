(function (window, document) {
    "use strict";
    if (!window.EMSDelegate) return;
    window.EMSDelegate.on("click", "[data-stx-ai-toggle]", function (event, button) {
        event.preventDefault();
        var root = button.closest("[data-stx-root]");
        var panel = root && root.querySelector("[data-stx-ai-panel]");
        if (!panel) return;
        panel.hidden = !panel.hidden;
        button.setAttribute("aria-expanded", String(!panel.hidden));
    });
    window.EMSDelegate.on("click", "[data-stx-ai-load]", async function (event, button) {
        event.preventDefault();
        var root = button.closest("[data-stx-root]");
        if (!root || button.disabled) return;
        var output = root.querySelector("[data-stx-ai-result]");
        button.disabled = true;
        output.setAttribute("aria-busy", "true");
        try {
            var response = await fetch(root.dataset.stxAiUrl, {credentials: "same-origin", headers: {"X-Requested-With": "XMLHttpRequest"}});
            var data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || output.dataset.error);
            output.textContent = data.summary || data.text || output.dataset.error;
        } catch (error) {
            output.textContent = output.dataset.error;
        } finally {
            button.disabled = false;
            output.removeAttribute("aria-busy");
        }
    });
})(window, document);

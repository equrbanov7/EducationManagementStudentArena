/* ═══════════════════════════════════════════════════════════════════════════
   Sillabus — «Bir sillabus, bir neçə jurnal» (sahib 2026-10-27)
   ───────────────────────────────────────────────────────────────────────────
   Redaktorun paylaşım blokunda (`_share_banner.html`) seçilmiş qrup üçün
   «Bu qrupda da istifadə et» → POST `reuse_action` `{action: "share", source,
   offering}`. Uğurda redaktor yenidən yüklənir və mesaj bir dəfə göstərilir
   (`EMSSyllabusList.flash`); xəta bölmənin toast-ında görünür.
   «Ayır» düyməsi `syllabus_reuse.js`-in təsdiq pəncərəsini işlədir
   (`data-syl-action="unshare"`), burada deyil.

   AJAX-safe (docs/frontend/AJAX_SAFE_JS_PATTERN.md): klik `EMSDelegate.on` ilə
   document-ə BİR DƏFƏ deleqasiya olunur; mətnlər serverdən gəlir.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
    "use strict";

    var toastTimer = null;

    function panelOf(node) {
        return (node && node.closest("[data-profile-section-panel]")) || document;
    }

    function toast(panel, message) {
        var node = panel.querySelector("[data-syl-toast]");
        var text = panel.querySelector("[data-syl-toast-text]");
        if (!node || !text || !message) {
            return;
        }
        text.textContent = message;
        node.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(function () {
            node.hidden = true;
        }, 5000);
    }

    function reloadEditor(panel, message) {
        if (window.EMSSyllabusList && typeof window.EMSSyllabusList.flash === "function") {
            window.EMSSyllabusList.flash("syllabus-editor", message);
        }
        var host = panel.querySelector("[data-syllabus-editor]");
        var versionId = host && host.getAttribute("data-version");
        var urlHost = panel.querySelector("[data-profile-url]");
        if (!versionId || typeof window.EMSProfileLoadSection !== "function") {
            toast(panel, message);
            return;
        }
        var url = new URL((urlHost && urlHost.getAttribute("data-profile-url")) || window.location.pathname,
            window.location.origin);
        url.searchParams.set("section", "syllabus-editor");
        url.searchParams.set("version", versionId);
        window.EMSProfileLoadSection("syllabus-editor", url.pathname + url.search);
    }

    function addShare(button) {
        var block = button.closest("[data-syl-share]");
        var select = block && block.querySelector("[data-syl-share-select]");
        var panel = panelOf(button);
        if (!block || !select || !select.value || button.disabled) {
            return;
        }
        if (!window.EMSCore || typeof window.EMSCore.fetchJSON !== "function") {
            return;
        }
        button.disabled = true;
        window.EMSCore.fetchJSON(block.getAttribute("data-action-url"), {
            method: "POST",
            data: { action: "share", source: button.getAttribute("data-id"), offering: select.value }
        })
            .then(function (data) {
                reloadEditor(panel, (data && data.message) || "");
            })
            .catch(function (err) {
                button.disabled = false;
                toast(panel, (err && err.payload && err.payload.error) || "");
            });
    }

    function bindOnce() {
        if (!window.EMSDelegate || window.__emsSyllabusShareBound) {
            return;
        }
        window.__emsSyllabusShareBound = true;
        window.EMSDelegate.on("click", "[data-profile-section-panel] [data-syl-share-add]", function (event, button) {
            event.preventDefault();
            addShare(button);
        });
    }

    window.EMSReady(function () {
        bindOnce();
    });
})();

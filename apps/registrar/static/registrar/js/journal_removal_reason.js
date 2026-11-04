/**
 * Jurnaldan çıxarılma SƏBƏBİ — ortaq sahələr (`_jd_removal_reason.html`, sahib 2026-11-04).
 *
 * «Fəndən azad et» modalı (journal_subject_exempt.js) və alt qrup «Çıxar» paneli (journal_guest.js) bu
 * köməkçini işlədir: `EMSJournalRemovalReason.read(root)` seçimi və qeydi oxuyur, səhvi (səbəb seçilməyib /
 * «Digər» qeydsiz) qaytarır; `reset(root)` sahələri sıfırlayır. «Digər» seçiləndə qeydin «məcburi» nişanı
 * görünür. Server (`journal_removal.clean`) eyni qaydanı yenidən yoxlayır — səth kifayət deyil.
 *
 * AJAX-SAFE: hadisə `EMSDelegate.on` ilə document səviyyəsində BİR dəfə bağlanır; köməkçi null-safe-dir.
 */
(function (window, document) {
    "use strict";

    var OTHER = "other";

    function parts(root) {
        var box = root ? root.querySelector("[data-jrr]") || (root.matches && root.matches("[data-jrr]") ? root : null) : null;
        if (!box) return null;
        return {
            box: box,
            reason: box.querySelector("[data-jrr-reason]"),
            note: box.querySelector("[data-jrr-note]"),
            required: box.querySelector("[data-jrr-note-required]"),
            optional: box.querySelector("[data-jrr-note-optional]"),
        };
    }

    function sync(p) {
        if (!p) return;
        var isOther = Boolean(p.reason && p.reason.value === OTHER);
        if (p.required) p.required.hidden = !isOther;
        if (p.optional) p.optional.hidden = isOther;
        if (p.note) p.note.required = isOther;
    }

    function refreshSelect(select) {
        if (!select) return;
        if (window.EMSBootstrapSelect && typeof window.EMSBootstrapSelect.refresh === "function") {
            window.EMSBootstrapSelect.refresh(select);
        } else {
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }
    }

    /** `{reason, note, error}` — `error` boş deyilsə göndərmə dayandırılır. */
    function read(root) {
        var p = parts(root);
        if (!p) return { reason: "", note: "", error: "" };
        var reason = p.reason ? (p.reason.value || "").trim() : "";
        var note = p.note ? (p.note.value || "").trim() : "";
        var error = "";
        if (!reason) {
            error = p.box.getAttribute("data-msg-reason") || "?";
            if (p.reason) p.reason.focus();
        } else if (reason === OTHER && !note) {
            error = p.box.getAttribute("data-msg-note") || "?";
            if (p.note) p.note.focus();
        }
        return { reason: reason, note: note, error: error };
    }

    function reset(root) {
        var p = parts(root);
        if (!p) return;
        if (p.reason) {
            p.reason.value = "";
            refreshSelect(p.reason);
        }
        if (p.note) p.note.value = "";
        sync(p);
    }

    window.EMSJournalRemovalReason = { read: read, reset: reset };

    function boot() {
        var delegate = window.EMSDelegate;
        if (!delegate || typeof delegate.on !== "function") return;
        delegate.on("change", "[data-jrr-reason]", function (event, select) {
            sync(parts(select.closest("[data-jrr]")));
        });
    }

    if (window.EMSReady && typeof window.EMSReady.once === "function") {
        window.EMSReady.once("journal-removal-reason", boot);
    } else if (!window.__jrrBooted) {
        window.__jrrBooted = true;
        boot();
    }
})(window, document);

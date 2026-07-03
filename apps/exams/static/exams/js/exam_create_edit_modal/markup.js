/* Markup helpers and modal frame state for the exam create/edit modal. */
(function (ns, window) {
    "use strict";

    function getLoadingMarkup(ctx) {
        var loadingText = ctx.i18n.loadingForm || "Loading...";
        return '<div class="create-exam-modal-loading">' + loadingText + "</div>";
    }

    function getErrorMarkup(ctx) {
        var errorText = ctx.i18n.submitError || (window.COURSES_I18N && window.COURSES_I18N.retryError) || "Please try again.";
        return '<div class="create-exam-modal-error">' + errorText + "</div>";
    }

    function getSavingMarkup(ctx) {
        return '<span class="ew-spin" aria-hidden="true"></span> ' + (ctx.i18n.saving || gettext("Saxlanılır…"));
    }

    function getSavedMarkup(ctx) {
        return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg> ' + (ctx.i18n.saved || gettext("Yadda saxlanıldı"));
    }

    function buildModalUrl(rawUrl) {
        try {
            var parsed = new URL(rawUrl, window.location.origin);
            parsed.searchParams.set("modal", "1");
            return parsed.pathname + parsed.search;
        } catch (error) {
            return rawUrl + (rawUrl.indexOf("?") === -1 ? "?modal=1" : "&modal=1");
        }
    }

    function applyModalMode(ctx, mode) {
        var isEdit = mode === "edit";
        var titleText = isEdit ? ctx.i18n.editTitle : ctx.i18n.createTitle;

        if (ctx.modalTitle && titleText) {
            ctx.modalTitle.textContent = titleText;
        }

        if (ctx.modalHeader) {
            ctx.modalHeader.classList.remove("bg-primary", "bg-info");
            ctx.modalHeader.classList.add(isEdit ? "bg-primary" : "bg-info");
            ctx.modalHeader.classList.add("text-white");
        }
    }

    function resetModalBody(ctx) {
        ctx.modalLoadToken += 1;
        if (ctx.modalElement) {
            ctx.modalElement.dataset.examModalLoading = "0";
        }
        ctx.modalBody.innerHTML = getLoadingMarkup(ctx);
    }

    ns.markup = {
        applyModalMode: applyModalMode,
        buildModalUrl: buildModalUrl,
        getErrorMarkup: getErrorMarkup,
        getLoadingMarkup: getLoadingMarkup,
        getSavedMarkup: getSavedMarkup,
        getSavingMarkup: getSavingMarkup,
        resetModalBody: resetModalBody
    };
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, window);

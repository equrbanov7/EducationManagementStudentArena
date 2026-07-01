import { navigateAway } from './utils.js';

export function installApi(ctx) {
    ctx.requestJson = function requestJson(url, payload) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": ctx.config.csrfToken || "",
                "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify(payload || {})
        }).then(function (response) {
            return response.json().then(function (body) {
                if (!response.ok) {
                    var error = new Error(body.error || "Request failed");
                    error.payload = body;
                    throw error;
                }
                return body;
            });
        });
    };

    ctx.autosave = function autosave() {
        if (!ctx.hasUnsavedChanges || ctx.isSubmitting) {
            return Promise.resolve();
        }
        ctx.setStatus(ctx.i18n.saving || "Saving...");
        return ctx.requestJson(ctx.config.autosaveUrl, ctx.collectPayload())
            .then(function (body) {
                ctx.hasUnsavedChanges = false;
                if (body.finished && body.redirect_url) {
                    navigateAway(body.redirect_url);
                    return;
                }
                ctx.currentQuestion().latestSubmission = body.submission || ctx.currentQuestion().latestSubmission;
                ctx.setStatus(ctx.i18n.autoSaved || "Auto-saved");
            })
            .catch(function (error) {
                if (error.payload && error.payload.redirect_url) {
                    navigateAway(error.payload.redirect_url);
                    return;
                }
                ctx.setStatus(error.message || "Save failed");
            });
    };
}

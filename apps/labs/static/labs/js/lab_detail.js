/*
 * lab_detail.js — tələbənin lab səhifəsi: taymer, avto-saxlama, fayl önbaxışı, bitirmə (2026-10-17, Paket E).
 *
 * Davranış əvvəlki ilə eynidir (avto-saxlama 800 ms debounce, son 3 saniyədə avto-göndəriş,
 * bitirmə təsdiqi); dəyişən: konfiqurasiya `#labDetailConfig` data-* atributlarından birbaşa oxunur
 * (ayrıca `lab_detail_template.js` silindi), irəliləyiş zolağı `--ems-bar-pct` ilə, təsdiq dialoqu
 * ortaq `EMSOverlay` ilə, hadisələr `EMSDelegate` ilə bağlanır.
 */
(function () {
    "use strict";

    var AUTO_SUBMIT_LEAD_SECONDS = 3;
    var state = { ready: false, labId: 0, endTime: null, total: 0, startedAt: null, autoSubmitRequested: false, timer: null };
    var saveTimeouts = {};
    var I18N = {};

    function byId(id) {
        return document.getElementById(id);
    }

    function t(key, fallback) {
        return I18N[key] || fallback;
    }

    function csrf() {
        return window.EMSCore && window.EMSCore.getCsrfToken ? window.EMSCore.getCsrfToken() : "";
    }

    /* Audit 2026-09-28 FQ-FE-4: native alert() → EMSToast. */
    function notifyError(message) {
        if (!message) { return; }
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, "error");
        } else if (window.console) {
            window.console.error(message);
        }
    }

    function readJsonResponse(response) {
        return response.text().then(function (text) {
            var data = null;
            try {
                data = text ? JSON.parse(text) : null;
            } catch (e) {
                data = null;
            }
            if (!response.ok || !data) {
                var err = new Error("HTTP " + response.status);
                err.payload = data;
                throw err;
            }
            return data;
        });
    }

    function readConfig() {
        var el = byId("labDetailConfig");
        if (!el) { return false; }
        var d = el.dataset;
        state.labId = parseInt(d.labId, 10);
        state.endTime = new Date(d.endTime);
        state.total = parseInt(d.totalQuestions, 10) || 0;
        I18N = {
            statusSaved: d.i18nStatusSaved,
            statusSaving: d.i18nStatusSaving,
            statusError: d.i18nStatusError,
            confirmUnanswered: d.i18nConfirmUnanswered,
            confirmFinishDescription: d.i18nConfirmFinishDescription,
            actionSubmitting: d.i18nActionSubmitting,
            errorPrefix: d.i18nErrorPrefix,
            errorUnknown: d.i18nErrorUnknown,
            errorServer: d.i18nErrorServer,
            actionFinishLab: d.i18nActionFinishLab
        };
        return true;
    }

    /* ── Saxlanma vəziyyəti: ikon + mətn (HTML inyeksiyası yoxdur) ───────── */
    function setStatus(questionId, kind) {
        var el = byId("status-" + questionId);
        if (!el) { return; }
        var icons = { saved: "fas fa-check-circle", saving: "fas fa-spinner fa-spin", error: "fas fa-exclamation-circle" };
        var texts = { saved: t("statusSaved", "Saved"), saving: t("statusSaving", "Saving..."), error: t("statusError", "Error") };
        el.textContent = "";
        var icon = document.createElement("i");
        icon.className = icons[kind] + " lab-save__ic is-" + kind;
        icon.setAttribute("aria-hidden", "true");
        var text = document.createElement("span");
        text.className = "lab-save__txt is-" + kind;
        text.textContent = texts[kind];
        el.appendChild(icon);
        el.appendChild(text);
    }

    /* ── Taymerlər ───────────────────────────────────────────────────────── */
    function pad(n) {
        return String(n).padStart(2, "0");
    }

    function formatTime(seconds) {
        return pad(Math.floor(seconds / 3600)) + ":" + pad(Math.floor((seconds % 3600) / 60)) + ":" + pad(seconds % 60);
    }

    function formatDuration(seconds) {
        var days = Math.floor(seconds / 86400);
        if (days > 0) {
            var rest = seconds % 86400;
            return pad(days) + ":" + pad(Math.floor(rest / 3600)) + ":" + pad(Math.floor((rest % 3600) / 60)) + ":" + pad(rest % 60);
        }
        return formatTime(seconds);
    }

    function updateTimers() {
        var now = new Date();
        var elapsedEl = byId("elapsedTimer");
        if (elapsedEl) { elapsedEl.textContent = formatTime(Math.max(0, Math.floor((now - state.startedAt) / 1000))); }

        var remaining = Math.max(0, Math.floor((state.endTime - now) / 1000));
        var remainingEl = byId("remainingTimer");
        if (remainingEl) { remainingEl.textContent = formatDuration(remaining); }

        if (remaining <= AUTO_SUBMIT_LEAD_SECONDS && !state.autoSubmitRequested && byId("labForm")) {
            state.autoSubmitRequested = true;
            submitLabForm();
        }
    }

    function updateProgress() {
        var answeredEl = byId("answeredCount");
        var progressEl = byId("progressBar");
        if (!answeredEl || !progressEl) { return; }
        var answered = 0;
        Array.prototype.forEach.call(document.querySelectorAll(".answer-textarea"), function (ta) {
            if (ta.value.trim()) { answered += 1; }
        });
        answeredEl.textContent = answered;
        progressEl.style.setProperty("--ems-bar-pct", (state.total ? (answered / state.total) * 100 : 0) + "%");
    }

    /* ── Avto-saxlama ────────────────────────────────────────────────────── */
    function autoSave(questionId, answer) {
        setStatus(questionId, "saving");
        fetch("/labs/" + state.labId + "/auto-save/", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
            body: JSON.stringify({ question_id: questionId, answer: answer })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                setStatus(questionId, data.success ? "saved" : "error");
                updateProgress();
            })
            .catch(function () {
                setStatus(questionId, "error");
            });
    }

    function onFileChosen(input) {
        var questionId = input.id.replace("file-", "");
        var preview = byId("preview-" + questionId);
        if (!input.files || !input.files[0]) { return; }
        if (preview) {
            preview.hidden = false;
            var nameEl = preview.querySelector(".file-name");
            if (nameEl) { nameEl.textContent = input.files[0].name; }
        }
        var textarea = document.querySelector('[name="answer_' + questionId + '"]');
        var formData = new FormData();
        formData.append("question_id", questionId);
        formData.append("answer", textarea ? textarea.value : "");
        formData.append("answer_file", input.files[0]);
        setStatus(questionId, "saving");
        fetch("/labs/" + state.labId + "/auto-save/", { method: "POST", body: formData, headers: { "X-CSRFToken": csrf() } })
            .then(function (r) { return r.json(); })
            .then(function (data) { setStatus(questionId, data.success ? "saved" : "error"); })
            .catch(function () { setStatus(questionId, "error"); });
    }

    /* `csp_event_handlers.js` «×» düyməsində `removeFile(questionId)` qlobalını çağırır. */
    window.removeFile = function (questionId) {
        var input = byId("file-" + questionId);
        var preview = byId("preview-" + questionId);
        if (input) { input.value = ""; }
        if (preview) { preview.hidden = true; }
    };

    /* ── Bitirmə ─────────────────────────────────────────────────────────── */
    function getUnansweredCount() {
        var answeredEl = byId("answeredCount");
        var answered = answeredEl ? parseInt(answeredEl.textContent, 10) : 0;
        return state.total - (isNaN(answered) ? 0 : answered);
    }

    function setSubmitButtonState(isSubmitting) {
        var btn = byId("submitBtn");
        if (!btn) { return; }
        btn.disabled = isSubmitting;
        btn.textContent = "";
        var icon = document.createElement("i");
        icon.className = isSubmitting ? "fas fa-spinner fa-spin" : "fas fa-paper-plane";
        icon.setAttribute("aria-hidden", "true");
        btn.appendChild(icon);
        btn.appendChild(document.createTextNode(" " + (isSubmitting ? t("actionSubmitting", "Submitting...") : t("actionFinishLab", "Finish Lab"))));
    }

    function setConfirmButtonState(isSubmitting) {
        var confirmBtn = byId("confirmFinishLabBtn");
        if (confirmBtn) { confirmBtn.disabled = isSubmitting; }
    }

    function submitLabForm() {
        var labForm = byId("labForm");
        if (!labForm) { return; }
        setSubmitButtonState(true);
        setConfirmButtonState(true);

        fetch("/labs/" + state.labId + "/submit/", { method: "POST", body: new FormData(labForm), headers: { "X-CSRFToken": csrf() } })
            .then(readJsonResponse)
            .then(function (data) {
                if (data.success) {
                    try { window.localStorage.removeItem("lab_" + state.labId + "_start"); } catch (e) { /* keşsiz */ }
                    window.location.href = data.redirect_url || "/";
                    return;
                }
                notifyError(t("errorPrefix", "Error") + ": " + (data.error || t("errorUnknown", "Unknown error")));
                setSubmitButtonState(false);
                setConfirmButtonState(false);
            })
            .catch(function (err) {
                var payload = err && err.payload;
                notifyError(payload && payload.error ? t("errorPrefix", "Error") + ": " + payload.error : t("errorServer", "Server error"));
                setSubmitButtonState(false);
                setConfirmButtonState(false);
            });
    }

    function updateFinishConfirmContent(unanswered) {
        var message = byId("finishLabConfirmMessage");
        if (message) {
            message.textContent = t("confirmFinishDescription", "After finishing the lab, you will not be able to return and edit it.");
        }
        var notice = byId("finishLabUnansweredNotice");
        if (!notice) { return; }
        if (unanswered > 0) {
            notice.textContent = t("confirmUnanswered", "{count} questions are unanswered. Submit?").replace("{count}", unanswered);
            notice.hidden = false;
        } else {
            notice.textContent = "";
            notice.hidden = true;
        }
    }

    function askToFinish() {
        var unanswered = getUnansweredCount();
        if (window.EMSOverlay && byId("finishLabConfirmModal")) {
            updateFinishConfirmContent(unanswered);
            window.EMSOverlay.open("finishLabConfirmModal");
            return;
        }
        var text = t("confirmFinishDescription", "After finishing the lab, you will not be able to return and edit it.");
        if (unanswered > 0) {
            text += "\n\n" + t("confirmUnanswered", "{count} questions are unanswered. Submit?").replace("{count}", unanswered);
        }
        // 2026-09-14 (audit FE-F19): native confirm() → EMSConfirm; ləğv = sorğu yoxdur.
        window.EMSConfirm.open({ body: text }).then(function (ok) {
            if (ok) { submitLabForm(); }
        });
    }

    /* ── Başlanğıc ───────────────────────────────────────────────────────── */
    function init() {
        if (state.ready || !readConfig()) { return; }
        state.ready = true;

        var key = "lab_" + state.labId + "_start";
        var stored = null;
        try {
            stored = window.localStorage.getItem(key);
            if (!stored) {
                stored = new Date().toISOString();
                window.localStorage.setItem(key, stored);
            }
        } catch (e) {
            stored = stored || new Date().toISOString();
        }
        state.startedAt = new Date(stored);
        if (isNaN(state.startedAt.getTime())) { state.startedAt = new Date(); }

        updateTimers();
        state.timer = window.setInterval(updateTimers, 1000);
        updateProgress();
    }

    window.EMSReady(init);

    window.EMSDelegate.on("change", ".file-input", function (event, input) {
        onFileChosen(input);
    });

    window.EMSDelegate.on("input", ".answer-textarea", function (event, ta) {
        var card = ta.closest(".question-card");
        if (!card) { return; }
        var qId = card.dataset.questionId;
        window.clearTimeout(saveTimeouts[qId]);
        saveTimeouts[qId] = window.setTimeout(function () {
            autoSave(qId, ta.value);
        }, 800);
    });

    window.EMSDelegate.on("click", ".question-toggle-btn", function (event, btn) {
        var card = byId("question-" + btn.dataset.toggleQuestion);
        if (!card) { return; }
        var collapsed = card.classList.toggle("question-collapsed");
        btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
        var icon = btn.querySelector("i");
        if (icon) {
            icon.classList.toggle("fa-chevron-down", collapsed);
            icon.classList.toggle("fa-chevron-up", !collapsed);
        }
    });

    window.EMSDelegate.on("submit", "#labForm", function (event) {
        event.preventDefault();
        askToFinish();
    });

    window.EMSDelegate.on("click", "#confirmFinishLabBtn", function () {
        if (window.EMSOverlay) { window.EMSOverlay.close("finishLabConfirmModal"); }
        submitLabForm();
    });
})();

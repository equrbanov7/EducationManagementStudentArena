import { createCodingExamContext } from './context.js';
import { bindCodingExamEvents } from './events.js';
import { installApi } from './api.js';
import { installPreview } from './preview.js';
import { installRunner } from './runner.js';
import { installStateHelpers } from './state.js';
import { installUi } from './ui.js';
import { formatTime } from './utils.js';

document.addEventListener("DOMContentLoaded", function () {
    var ctx = createCodingExamContext();
    if (!ctx) {
        return;
    }

    installStateHelpers(ctx);
    installUi(ctx);
    installApi(ctx);
    installPreview(ctx);
    installRunner(ctx);
    bindCodingExamEvents(ctx);

    if (ctx.timerValue && ctx.config.remainingSeconds !== null && ctx.config.remainingSeconds !== undefined) {
        var remaining = parseInt(ctx.config.remainingSeconds, 10) || 0;
        // Sahib 2026-11-17: nəzarətçinin əlavə vaxtı — serverdəki CƏM gəlir, yalnız artım əlavə olunur.
        var knownExtra = parseInt(ctx.config.extraTimeSeconds, 10) || 0;
        var timeUp = false;
        document.addEventListener("ems:exam-time-extended", function (event) {
            var total = parseInt(event && event.detail ? event.detail.extraTimeSeconds : "", 10);
            if (isNaN(total) || total <= knownExtra) {
                return;
            }
            var added = total - knownExtra;
            knownExtra = total;
            if (!timeUp) {
                remaining += added;
            }
        });
        var timerId = window.setInterval(function () {
            ctx.timerValue.textContent = formatTime(remaining);
            if (ctx.timerNode) {
                ctx.timerNode.classList.toggle("is-danger", remaining > 0 && remaining <= 60);
            }
            if (ctx.timeWarning) {
                ctx.timeWarning.maybeShow(remaining);
            }
            if (remaining <= 0) {
                timeUp = true;
                window.clearInterval(timerId);
                ctx.setStatus(ctx.i18n.timeOver || "Time is over");
                ctx.submitCode();
                return;
            }
            remaining -= 1;
        }, 1000);
    }

    if (ctx.languageSelect) {
        ctx.languageSelect.value = ctx.currentQuestion().selectedLanguage || ctx.currentQuestion().language || ctx.config.selectedLanguage;
        ctx.syncBootstrapSelect(ctx.languageSelect);
    }

    // Show a one-time tip about shortcuts so students discover Ctrl+Enter.
    if (ctx.i18n.shortcutHint) {
        ctx.setStatus(ctx.i18n.shortcutHint);
    }

    ctx.syncLanguageToCurrentFile();
    ctx.renderProblem();
    ctx.renderFiles();
    ctx.setEditorForCurrentFile();
    if (ctx.stdinNode) {
        ctx.stdinNode.value = ctx.currentQuestion().stdin || "";
    }
    ctx.updateStdinHint();
    ctx.updateLanguagePreviewVisibility();
});

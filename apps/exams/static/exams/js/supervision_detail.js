/*
 * supervision_detail.js
 * Source: exams/teacher/supervision_detail.html
 *
 * Teacher supervision detail: confirm-modal driven resume / grant-extra-chance /
 * stop actions for a supervised attempt. i18n comes from the
 * #supervision-detail-i18n JSON island; CSRF from EMSCore.getCsrfToken().
 */
(function () {
    "use strict";

    var i18nEl = document.getElementById("supervision-detail-i18n");
    var DETAIL_I18N = i18nEl ? JSON.parse(i18nEl.textContent) : {};

    var confirmModal = document.getElementById("confirmModal");
    var confirmTitle = document.getElementById("confirmModalTitle");
    var confirmMsg = document.getElementById("confirmModalMessage");
    var confirmOk = document.getElementById("confirmModalOk");
    var confirmCancel = document.getElementById("confirmModalCancel");
    if (!confirmModal) { return; }
    var pendingAction = null;

    function csrfToken() {
        return (window.EMSCore && EMSCore.getCsrfToken) ? EMSCore.getCsrfToken() : "";
    }

    function showConfirmModal(title, message, btnText, btnClass, onConfirm) {
        confirmTitle.textContent = title;
        confirmMsg.textContent = message;
        confirmOk.textContent = btnText;
        confirmOk.className = btnClass;
        pendingAction = onConfirm;
        confirmModal.classList.add("show");
    }

    function hideConfirmModal() {
        confirmModal.classList.remove("show");
        pendingAction = null;
    }

    confirmCancel.addEventListener("click", hideConfirmModal);
    confirmModal.addEventListener("click", function(e) {
        if (e.target === confirmModal) hideConfirmModal();
    });
    confirmOk.addEventListener("click", function() {
        if (pendingAction) pendingAction();
        hideConfirmModal();
    });

    function resumeAttempt(attemptId, grantExtraChance) {
        fetch("/exams/supervision/api/resume/" + attemptId + "/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify({ grant_extra_chance: grantExtraChance })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                location.reload();
            } else {
                alert(DETAIL_I18N.errorPrefix + (data.error || ""));
            }
        })
        .catch(function() { alert(DETAIL_I18N.connectionError); });
    }

    function stopAttempt(attemptId) {
        fetch("/exams/supervision/api/stop/" + attemptId + "/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify({})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                location.reload();
            } else {
                alert(DETAIL_I18N.errorPrefix + (data.error || ""));
            }
        })
        .catch(function() { alert(DETAIL_I18N.connectionError); });
    }

    document.addEventListener("click", function(event) {
        var btn = event.target.closest("[data-action]");
        if (!btn) return;

        event.preventDefault();
        var action = btn.getAttribute("data-action");
        var attemptId = parseInt(btn.getAttribute("data-attempt-id"), 10);

        if (action === "resume") {
            showConfirmModal(
                DETAIL_I18N.resumeTitle,
                DETAIL_I18N.confirmResume,
                DETAIL_I18N.resumeTitle,
                "btn-confirm-success",
                function() { resumeAttempt(attemptId, false); }
            );
        } else if (action === "chance") {
            showConfirmModal(
                DETAIL_I18N.chanceTitle,
                DETAIL_I18N.confirmChance,
                DETAIL_I18N.chanceTitle,
                "btn-confirm-primary",
                function() { resumeAttempt(attemptId, true); }
            );
        } else if (action === "stop") {
            showConfirmModal(
                DETAIL_I18N.stopTitle,
                DETAIL_I18N.confirmStop,
                DETAIL_I18N.stopTitle,
                "btn-confirm-danger",
                function() { stopAttempt(attemptId); }
            );
        }
    });
})();

/*
 * groups_overview.js
 * Source: extracted verbatim from the inline <script> in
 * _groups_overview_content.html (CSP inline-removal, 2026-07).
 * Wires the group-detail modal (auto-show + close-URL reload) and the
 * remove-student confirm modal. Runs on initial load AND re-runs on every
 * profile AJAX section swap (the section loader re-executes this script), which
 * matches the original inline IIFE. i18n bridged via data-* on the modal.
 */
(function () {
    "use strict";

    function initProfileGroupDetailModals() {
        if (typeof window.bootstrap === "undefined") { return; }
        var activeGroupsPanel = document.querySelector('[data-profile-section-panel="groups"]');
        var detailModalEl = activeGroupsPanel
            ? activeGroupsPanel.querySelector("#profileGroupDetailModal")
            : document.getElementById("profileGroupDetailModal");
        var removeModalEl = activeGroupsPanel
            ? activeGroupsPanel.querySelector("#profileGroupRemoveStudentModal")
            : document.getElementById("profileGroupRemoveStudentModal");
        var removeBodyEl = null;
        var removeFormEl = null;
        var removeNextEl = null;
        var removeConfirmText = removeModalEl
            ? (removeModalEl.getAttribute("data-confirm-body-template") || "")
            : "";

        if (detailModalEl) {
            Array.from(document.querySelectorAll("#profileGroupDetailModal")).forEach(function (node) {
                if (node !== detailModalEl && node.parentNode) {
                    node.parentNode.removeChild(node);
                }
            });
            if (detailModalEl.parentElement !== document.body) {
                document.body.appendChild(detailModalEl);
            }
            var detailModal = window.bootstrap.Modal.getOrCreateInstance(detailModalEl);
            detailModal.show();

            if (detailModalEl.getAttribute("data-profile-group-detail-ready") !== "1") {
                detailModalEl.setAttribute("data-profile-group-detail-ready", "1");
                detailModalEl.addEventListener("hide.bs.modal", function () {
                    var closeUrl = detailModalEl.getAttribute("data-close-url");
                    if (closeUrl) {
                        if (typeof window.EMSProfileLoadSection === "function") {
                            window.EMSProfileLoadSection("groups", closeUrl, { updateUrl: true });
                        } else {
                            window.location.href = closeUrl;
                        }
                    }
                });
                detailModalEl.addEventListener("hidden.bs.modal", function () {
                    if (detailModalEl.parentNode) {
                        detailModalEl.parentNode.removeChild(detailModalEl);
                    }
                });
            }
        }

        if (removeModalEl) {
            Array.from(document.querySelectorAll("#profileGroupRemoveStudentModal")).forEach(function (node) {
                if (node !== removeModalEl && node.parentNode) {
                    node.parentNode.removeChild(node);
                }
            });
            if (removeModalEl.parentElement !== document.body) {
                document.body.appendChild(removeModalEl);
            }
            removeBodyEl = removeModalEl.querySelector("#profileGroupRemoveStudentBody");
            removeFormEl = removeModalEl.querySelector("#profileGroupRemoveStudentForm");
            removeNextEl = removeModalEl.querySelector("#profileGroupRemoveStudentNext");
            var removeModal = window.bootstrap.Modal.getOrCreateInstance(removeModalEl);

            window.EMSDelegate.on("click", ".jsOpenRemoveStudentFromGroup", function (event, btn) {
                event.preventDefault();
                var studentName = btn.getAttribute("data-student-name") || "";
                var removeUrl = btn.getAttribute("data-remove-url") || "";
                var nextUrl = btn.getAttribute("data-next-url") || "";

                if (removeBodyEl) {
                    removeBodyEl.textContent = removeConfirmText.replace("{student}", studentName);
                }
                if (removeFormEl) {
                    removeFormEl.setAttribute("action", removeUrl);
                }
                if (removeNextEl) {
                    removeNextEl.value = nextUrl;
                }
                removeModal.show();
            });
        }
    }

    initProfileGroupDetailModals();
})();

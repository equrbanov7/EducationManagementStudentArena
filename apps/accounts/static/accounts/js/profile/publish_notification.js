/*
 * publish_notification.js
 * Source: apps/accounts/templates/accounts/profile/sections/_publish_notification.html
 * Publish-notification profile section: exclusive target checkboxes, target search
 * filter, image preview + clear, reset handling. Static behavior (no template vars).
 * AJAX-safe: EMSReady-wrapped, null-safe, idempotent (dataset guard on #pnTargetList).
 */
(function () {
    "use strict";

    window.EMSReady(function () {
        var targetList = document.getElementById("pnTargetList");
        if (!targetList) { return; }
        if (targetList.dataset.pnBound === "1") { return; }
        targetList.dataset.pnBound = "1";

        var allCbs = targetList.querySelectorAll(".pn-target-cb");
        var exclusiveCbs = targetList.querySelectorAll(".pn-target-cb--exclusive");

        // ── Exclusive checkbox handling (e.g., "All users") ──
        // When an exclusive box is checked, uncheck everything else.
        // When any normal box is checked, uncheck the exclusive ones.
        allCbs.forEach(function (cb) {
            cb.addEventListener("change", function () {
                if (!cb.checked) { return; }

                if (cb.classList.contains("pn-target-cb--exclusive")) {
                    // Uncheck all non-exclusive boxes
                    allCbs.forEach(function (other) {
                        if (!other.classList.contains("pn-target-cb--exclusive")) {
                            other.checked = false;
                        }
                    });
                } else {
                    // Uncheck all exclusive boxes
                    exclusiveCbs.forEach(function (excl) { excl.checked = false; });
                }
            });
        });

        // ── Search filter — always present ──
        var searchInput = document.getElementById("pnTargetSearch");
        var noResults = document.getElementById("pnTargetNoResults");
        if (searchInput) {
            searchInput.addEventListener("input", function () {
                var q = searchInput.value.toLowerCase().trim();
                var visibleCount = 0;
                targetList.querySelectorAll(".pn-target-item").forEach(function (item) {
                    var label = (item.getAttribute("data-label") || "").toLowerCase();
                    var visible = (q === "" || label.indexOf(q) !== -1);
                    item.style.display = visible ? "" : "none";
                    if (visible) { visibleCount++; }
                });
                if (noResults) {
                    noResults.style.display = (q !== "" && visibleCount === 0) ? "" : "none";
                }
            });
        }

        // ── Image preview ──
        var imgInput = document.getElementById("notifImage");
        var imgPreview = document.getElementById("notifImagePreview");
        var imgPreviewWrap = document.getElementById("notifImagePreviewWrap");
        var imgClear = document.getElementById("notifImageClear");

        if (imgInput && imgPreview && imgPreviewWrap) {
            imgInput.addEventListener("change", function () {
                var file = imgInput.files[0];
                if (file) {
                    var reader = new FileReader();
                    reader.onload = function (e) {
                        imgPreview.src = e.target.result;
                        imgPreviewWrap.style.display = "";
                    };
                    reader.readAsDataURL(file);
                } else {
                    imgPreviewWrap.style.display = "none";
                    imgPreview.src = "";
                }
            });

            if (imgClear) {
                imgClear.addEventListener("click", function () {
                    imgInput.value = "";
                    imgPreview.src = "";
                    imgPreviewWrap.style.display = "none";
                });
            }
        }

        // ── Reset button clears image preview ──
        var resetBtn = document.getElementById("notifResetBtn");
        if (resetBtn && imgPreviewWrap) {
            resetBtn.addEventListener("click", function () {
                setTimeout(function () {
                    imgPreviewWrap.style.display = "none";
                    if (imgPreview) { imgPreview.src = ""; }
                }, 10);
            });
        }
    });
})();

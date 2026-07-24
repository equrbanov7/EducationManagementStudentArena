/*
 * profile_info_identity.js
 * Source: apps/accounts/templates/accounts/profile/sections/_profile_info_identity.html
 * Identity block: avatar image error → fallback swap, and avatar-upload live preview.
 * Static behavior (no template vars). AJAX-safe: EMSReady-wrapped, null-safe,
 * idempotent (per-element dataset guards so listeners are not stacked across swaps).
 */
(function () {
    "use strict";

    function showAvatarFallback(imageNode, fallbackNode) {
        if (imageNode) {
            imageNode.style.display = "none";
        }
        if (fallbackNode) {
            fallbackNode.style.display = "flex";
        }
    }

    window.EMSReady(function () {
        var identityAvatarImage = document.getElementById("profileIdentityAvatarImage");
        var identityAvatarFallback = document.getElementById("profileIdentityAvatarFallback");
        if (identityAvatarImage && identityAvatarImage.dataset.piiBound !== "1") {
            identityAvatarImage.dataset.piiBound = "1";
            identityAvatarImage.addEventListener("error", function () {
                showAvatarFallback(identityAvatarImage, identityAvatarFallback);
            });
            if (identityAvatarImage.complete && !identityAvatarImage.naturalWidth) {
                showAvatarFallback(identityAvatarImage, identityAvatarFallback);
            }
        }

        var avatarInput = document.getElementById("profileAvatarInput");
        var avatarPreviewImage = document.getElementById("profileAvatarPreviewImage");
        var avatarPreviewFallback = document.getElementById("profileAvatarPreviewFallback");
        if (avatarPreviewImage && avatarPreviewImage.dataset.piiBound !== "1") {
            avatarPreviewImage.dataset.piiBound = "1";
            avatarPreviewImage.addEventListener("error", function () {
                showAvatarFallback(avatarPreviewImage, avatarPreviewFallback);
            });
            if (avatarPreviewImage.complete && !avatarPreviewImage.naturalWidth) {
                showAvatarFallback(avatarPreviewImage, avatarPreviewFallback);
            }
        }

        if (avatarInput && avatarPreviewImage && avatarInput.dataset.piiBound !== "1") {
            avatarInput.dataset.piiBound = "1";
            avatarInput.addEventListener("change", function () {
                var file = avatarInput.files && avatarInput.files.length ? avatarInput.files[0] : null;
                if (!file) {
                    return;
                }
                if (avatarPreviewFallback) {
                    avatarPreviewFallback.style.display = "none";
                }
                avatarPreviewImage.src = URL.createObjectURL(file);
                avatarPreviewImage.style.display = "";
            });
        }
    });
})();

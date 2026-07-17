/* Superadmin — imtahan zalları bölməsi.
 *
 * Modallar (zal/kompüter yarat-redaktə), silmə təsdiqi, org seçicisinin
 * avto-submit-i, MAC inputunun canlı formatlaması, MAC kopyalama və
 * əməliyyatdan sonra sətir/kart vurğusu (flash).
 *
 * QEYD: profil SPA-sı bölmə swap-ında paneldəki <script> taqlarını yenidən
 * icra edir — dinləyicilər document səviyyəsində DELEGATED qoşulur və qlobal
 * bayraqla ikiqat qoşulma önlənir. Modal overlay-ları body-yə köçürülür
 * (transform-lu ata elementlər fixed-i sındırmasın); köhnə mount-lar hər
 * icrada təmizlənir.
 */
(function () {
    "use strict";

    function closeAllModals() {
        document.querySelectorAll(".sarm-overlay.is-open").forEach(function (overlay) {
            overlay.classList.remove("is-open");
        });
        document.body.classList.remove("sarm-lock");
        document.body.style.overflow = "";
    }

    function openModal(name) {
        var overlay = document.getElementById("sarm-" + name);
        if (!overlay) {
            return;
        }
        closeAllModals();
        overlay.classList.add("is-open");
        document.body.style.overflow = "hidden";
        var first = overlay.querySelector("input:not([type=hidden]), textarea, select");
        if (first) {
            window.setTimeout(function () { first.focus(); }, 30);
        }
    }

    function mountOverlays() {
        // Köhnə (əvvəlki swap-dan qalan) mount-ları sil, panelinkiləri body-yə köçür.
        document.querySelectorAll("body > .sarm-overlay").forEach(function (overlay) {
            overlay.remove();
        });
        document.querySelectorAll(".sar .sarm-overlay, .profile-section-panel .sarm-overlay").forEach(function (overlay) {
            document.body.appendChild(overlay);
        });
    }

    function formatMacInput(input) {
        var hex = (input.value || "").replace(/[^0-9a-fA-F]/g, "").toUpperCase().slice(0, 12);
        var pairs = hex.match(/.{1,2}/g) || [];
        input.value = pairs.join(":");
    }

    function flashFromUrl() {
        var params = new URLSearchParams(window.location.search);
        var comp = params.get("hl_comp");
        var room = params.get("hl_room");
        if (comp) {
            var row = document.querySelector('[data-comp-row="' + comp + '"]');
            if (row) {
                row.classList.add("sar-flash-row");
                if (row.scrollIntoView) { row.scrollIntoView({ block: "center" }); }
            }
        } else if (room) {
            var card = document.getElementById("sar-room-" + room);
            if (card) {
                card.classList.add("sar-flash-card");
            }
        }
    }

    if (!window.__sarInit) {
        window.__sarInit = true;

        document.addEventListener("click", function (event) {
            var target = event.target;
            if (!target || !target.closest) {
                return;
            }

            var opener = target.closest("[data-sar-open]");
            if (opener) {
                event.preventDefault();
                openModal(opener.getAttribute("data-sar-open"));
                return;
            }

            var closer = target.closest("[data-sar-close]");
            if (closer) {
                event.preventDefault();
                closeAllModals();
                return;
            }

            // Overlay-in boş sahəsinə klik → bağla (dialoqun özünə yox).
            if (target.classList && target.classList.contains("sarm-overlay")) {
                closeAllModals();
                return;
            }

            var confirmBtn = target.closest(".js-sar-confirm");
            if (confirmBtn && confirmBtn.dataset.confirm && !window.confirm(confirmBtn.dataset.confirm)) {
                event.preventDefault();
                return;
            }

            var copyBtn = target.closest(".js-sar-copy");
            if (copyBtn) {
                event.preventDefault();
                var value = copyBtn.getAttribute("data-copy") || "";
                if (value && navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(value).then(function () {
                        copyBtn.classList.add("is-copied");
                        window.setTimeout(function () { copyBtn.classList.remove("is-copied"); }, 1200);
                    });
                }
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeAllModals();
            }
        });

        document.addEventListener("change", function (event) {
            var select = event.target;
            if (select && select.classList && select.classList.contains("js-sar-orgselect")) {
                var form = select.closest("form");
                if (form) {
                    form.submit();
                }
            }
        });

        document.addEventListener("input", function (event) {
            var input = event.target;
            if (input && input.matches && input.matches("input[data-mac-input]")) {
                formatMacInput(input);
            }
        });
    }

    // Hər icrada (ilk yükləmə + SPA swap): overlay mount + URL vurğusu.
    mountOverlays();
    flashFromUrl();
})();

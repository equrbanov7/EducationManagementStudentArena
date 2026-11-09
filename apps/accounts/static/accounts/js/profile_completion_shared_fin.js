/* Eyni FİN — «hər iki hesab mənimdir?» təsdiq modalı (sahib 2026-11-09).
 * Şablon: accounts/profile_completion.html ([data-shared-fin]). «Bəli» adi form POST-udur (gizli təsdiq sahəsi ilə);
 * «Xeyr» modalı bağlayır və «başqa hesabda qeydə alınıb» imtinasını göstərir — heç nə yazılmır.
 */
(function () {
    "use strict";

    function init() {
        var overlay = document.querySelector("[data-shared-fin]");
        if (!overlay || overlay.dataset.sfInit === "1") {
            return;
        }
        overlay.dataset.sfInit = "1";
        document.documentElement.classList.add("sf-lock");

        var yes = overlay.querySelector("[data-shared-fin-yes]");
        if (yes) {
            yes.focus();
        }

        function close() {
            overlay.hidden = true;
            document.documentElement.classList.remove("sf-lock");
            var conflict = document.querySelector("[data-shared-fin-conflict]");
            if (conflict) {
                conflict.hidden = false;
            }
            var fin = document.getElementById("pc-fin");
            if (fin) {
                fin.focus();
                if (typeof fin.select === "function") {
                    fin.select();
                }
            }
        }

        overlay.addEventListener("click", function (event) {
            var no = event.target.closest ? event.target.closest("[data-shared-fin-no]") : null;
            if (no && overlay.contains(no)) {
                event.preventDefault();
                close();
            }
        });

        overlay.addEventListener("submit", function () {
            overlay.querySelectorAll("button").forEach(function (button) {
                button.disabled = true;
            });
        });

        // Diqqət tələyi: Tab modalın içində qalsın.
        overlay.addEventListener("keydown", function (event) {
            if (event.key !== "Tab") {
                return;
            }
            var buttons = Array.prototype.slice.call(overlay.querySelectorAll("button:not([disabled])"));
            if (!buttons.length) {
                return;
            }
            var first = buttons[0];
            var last = buttons[buttons.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });
    }

    if (typeof window.EMSReady === "function") {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

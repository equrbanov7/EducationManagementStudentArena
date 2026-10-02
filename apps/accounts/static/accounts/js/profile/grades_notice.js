/* «Köçürülmüş ballar» xəbərdarlığı — parol bərpasından sonra ilk girişdə bir dəfə (sahib 2026-10-02).
 * Şablon: accounts/profile/_grades_notice_modal.html. Modal yalnız düymə ilə bağlanır (fon kliki / Esc yox):
 * «Başa düşdüm» → POST ack (bayraq endirilir) → modal bağlanır; «Ballarıma indi baxım» → ack + bölməyə keçid.
 * Ack alınmasa da modal bağlanır — növbəti girişdə yenidən göstərilər (bayraq hələ qalxıqdır).
 */
(function () {
    "use strict";

    function init() {
        var overlay = document.querySelector("[data-grades-notice]");
        if (!overlay || overlay.dataset.gnInit === "1") {
            return;
        }
        overlay.dataset.gnInit = "1";
        document.documentElement.classList.add("gn-lock");

        var primary = overlay.querySelector('[data-grades-notice-ack][data-go="0"]');
        if (primary) {
            primary.focus();
        }

        function close(goToGrades) {
            overlay.hidden = true;
            document.documentElement.classList.remove("gn-lock");
            var target = overlay.dataset.gradesUrl || "";
            if (goToGrades && target) {
                window.location.href = target;
            }
        }

        function acknowledge(button) {
            var goToGrades = button.dataset.go === "1";
            overlay.querySelectorAll("[data-grades-notice-ack]").forEach(function (btn) {
                btn.disabled = true;
            });
            var url = overlay.dataset.ackUrl;
            var core = window.EMSCore;
            var request = core && typeof core.fetchJSON === "function" && url
                ? core.fetchJSON(url, { method: "POST", data: {} })
                : Promise.resolve();
            request.catch(function () {
                return null;
            }).then(function () {
                close(goToGrades);
            });
        }

        overlay.addEventListener("click", function (event) {
            var button = event.target.closest ? event.target.closest("[data-grades-notice-ack]") : null;
            if (button && overlay.contains(button) && !button.disabled) {
                acknowledge(button);
            }
        });

        // Diqqət tələyi: Tab modalın içində qalsın (fon elementlərinə keçməsin).
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

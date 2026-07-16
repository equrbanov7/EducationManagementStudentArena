import { ExamSupervision } from "./state.js?v=20260716-intervention";

function normalizedReason(value) {
    return String(value || "").trim();
}

Object.assign(ExamSupervision, {
        _renderInterventionReason: function (container, reason) {
            if (!container) return;
            var text = normalizedReason(reason);
            var box = container.querySelector("[data-supervision-intervention-reason]");
            if (!box) {
                box = document.createElement("div");
                box.setAttribute("data-supervision-intervention-reason", "");
                box.style.cssText =
                    "margin:1.25rem 0;padding:1rem;border-radius:10px;background:#fef2f2;" +
                    "border:1px solid #fecaca;text-align:left;color:#7f1d1d;";
                var label = document.createElement("strong");
                label.textContent = gettext("Səbəb") + ": ";
                var value = document.createElement("span");
                value.setAttribute("data-supervision-intervention-reason-value", "");
                box.appendChild(label);
                box.appendChild(value);
                var card = container.firstElementChild || container;
                var actionButton = card.querySelector("button");
                card.insertBefore(box, actionButton || null);
            }
            box.hidden = !text;
            var valueEl = box.querySelector("[data-supervision-intervention-reason-value]");
            if (valueEl) valueEl.textContent = text;
        },

        _showRemovalOverlay: function (reason, action) {
            var existing = document.getElementById("supervision-removal-overlay");
            if (existing) {
                this._renderInterventionReason(existing, reason);
                return;
            }

            this.destroy();
            [
                "supervision-warning-modal",
                "supervision-locked-overlay",
                "supervision-teacher-lock-overlay",
                "supervision-resume-overlay"
            ].forEach(function (id) {
                var node = document.getElementById(id);
                if (node) node.remove();
            });

            var isTechnical = action === "technical";
            var overlay = document.createElement("div");
            overlay.id = "supervision-removal-overlay";
            overlay.style.cssText =
                "position:fixed;inset:0;background:rgba(0,0,0,0.95);z-index:100002;" +
                "display:flex;justify-content:center;align-items:center;";

            var card = document.createElement("div");
            card.style.cssText =
                "background:#fff;border-radius:14px;padding:2.5rem;max-width:560px;width:90%;" +
                "text-align:center;box-shadow:0 24px 70px rgba(0,0,0,.35);";
            card.innerHTML =
                '<div style="font-size:4rem;color:#dc2626;margin-bottom:1rem;"><i class="fas fa-user-slash"></i></div>' +
                '<h2 style="color:#991b1b;margin-bottom:.75rem;"></h2>' +
                '<p style="color:#4b5563;margin-bottom:1rem;"></p>';
            card.querySelector("h2").textContent = isTechnical
                ? gettext("İmtahanınız texniki səbəblə dayandırıldı")
                : gettext("İmtahandan çıxarıldınız");
            card.querySelector("p").textContent = gettext(
                "Cari cavablarınız yadda saxlanılıb. Ətraflı nəticəyə keçə bilərsiniz."
            );

            var resultButton = document.createElement("button");
            resultButton.type = "button";
            resultButton.style.cssText =
                "margin-top:.5rem;padding:.8rem 1.8rem;background:#2563eb;color:#fff;border:0;" +
                "border-radius:9px;font-size:1rem;font-weight:700;cursor:pointer;";
            resultButton.innerHTML = '<i class="fas fa-chart-bar"></i> ';
            resultButton.appendChild(document.createTextNode(gettext("Nəticəyə keç")));
            resultButton.addEventListener("click", function () {
                var url = String(window.SUPERVISION_RESULT_URL || "").trim();
                if (url) window.location.assign(url);
                else window.location.reload();
            });

            card.appendChild(resultButton);
            overlay.appendChild(card);
            document.body.appendChild(overlay);
            this._renderInterventionReason(overlay, reason);
        },
});

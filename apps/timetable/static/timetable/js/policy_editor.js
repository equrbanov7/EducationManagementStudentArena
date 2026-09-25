/**
 * Qrup növbə siyasəti — çip keçidləri və sətir/kart üzrə yadda saxlama.
 * ─────────────────────────────────────────────────────────────────────
 * Hər `[data-tt-policy]` elementi (pillə kartı və ya qrup sətri) öz dəyərlərini
 * daşıyır: `[data-tt-band]` çipləri (aria-pressed), `[data-tt-max]`, `[data-tt-excluded]`.
 * AJAX-safe: yalnız EMSDelegate; səhifə yenilənmədən nəticə toast ilə göstərilir.
 */
(function (window, document) {
    "use strict";

    var TT = window.EMSTimetable;

    function rootOf(node) {
        return node.closest("[data-tt-policy-root]");
    }

    window.EMSDelegate.on("click", "[data-tt-band]", function (event, chip) {
        chip.setAttribute("aria-pressed", chip.getAttribute("aria-pressed") === "true" ? "false" : "true");
    });

    function values(item) {
        var bands = [];
        item.querySelectorAll("[data-tt-band]").forEach(function (chip) {
            if (chip.getAttribute("aria-pressed") === "true") {
                bands.push(chip.getAttribute("data-tt-band"));
            }
        });
        var max = item.querySelector("[data-tt-max]");
        var excluded = item.querySelector("[data-tt-excluded]");
        var data = {
            bands: bands,
            max_pairs_per_day: max ? max.value : "",
            is_excluded: !!(excluded && excluded.checked),
        };
        if (item.getAttribute("data-group")) {
            data.group = item.getAttribute("data-group");
        } else {
            data.level = item.getAttribute("data-level");
        }
        return data;
    }

    function send(button, data) {
        var root = rootOf(button);
        if (!root) {
            return;
        }
        TT.setBusy(button, true);
        TT.post(root.getAttribute("data-save-url"), data)
            .then(function (payload) {
                TT.toast(payload && payload.message, "success");
                if (data.reset) {
                    window.location.reload();
                }
            })
            .catch(function (error) {
                TT.toast(TT.errorText(error, root.getAttribute("data-msg-error")), "error");
            })
            .then(function () {
                TT.setBusy(button, false);
            });
    }

    window.EMSDelegate.on("click", "[data-tt-policy-save]", function (event, button) {
        var item = button.closest("[data-tt-policy]");
        if (item) {
            send(button, values(item));
        }
    });

    window.EMSDelegate.on("click", "[data-tt-policy-reset]", function (event, button) {
        var item = button.closest("[data-tt-policy]");
        if (item && item.getAttribute("data-group")) {
            send(button, { group: item.getAttribute("data-group"), reset: true });
        }
    });
})(window, document);

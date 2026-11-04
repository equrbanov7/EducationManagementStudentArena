/* RİM mərkəzi — detal kartının hadisələri (2026-11-04): inline yoxlama, vəzifə, fakültə → kafedra, «Məzun et».
 *
 * AJAX-safe: hamısı `EMSDelegate` ilə `document`-ə BİR dəfə bağlanır (`EMSReady.once`) — kart hər əməldən sonra
 * yenidən render olunsa da dinləyicilər yığılmır. Qapı serverdədir; burada yalnız UX.
 */
(function (window, document) {
    "use strict";

    var ns = (window.EMSRimCenter = window.EMSRimCenter || {});

    if (!window.EMSReady || !window.EMSDelegate) {
        return;
    }

    function showError(el, message) {
        if (el) {
            el.textContent = message || "";
            el.hidden = !message;
        }
    }

    /* ── Vəzifə ─────────────────────────────────────────────────────────── */

    function positionValue(host) {
        var select = host.querySelector("[data-rim-position-select]");
        var other = host.querySelector("[data-rim-position-other]");
        if (!select) {
            return "";
        }
        if (select.value === ns.detailView.OTHER) {
            return other ? other.value.trim() : "";
        }
        return select.value;
    }

    function syncPosition(host) {
        var select = host.querySelector("[data-rim-position-select]");
        var other = host.querySelector("[data-rim-position-other]");
        var save = host.querySelector("[data-rim-position-save]");
        var isOther = select && select.value === ns.detailView.OTHER;
        if (other) {
            other.hidden = !isOther;
        }
        if (save) {
            var value = positionValue(host);
            save.disabled = (isOther && !value) || value === (host.getAttribute("data-initial") || "");
        }
    }

    /* ── Bölmə ──────────────────────────────────────────────────────────── */

    function syncPlace(host) {
        var unit = host.querySelector("select[data-rim-place-unit]");
        var save = host.querySelector("[data-rim-place-save]");
        if (save && unit) {
            save.disabled = !unit.value || unit.value === (host.getAttribute("data-current-unit") || "");
        }
    }

    /* ── «Məzun et» dialoqu ─────────────────────────────────────────────── */

    function graduateModal() {
        return document.querySelector("[data-rim-graduate-modal]");
    }

    function todayIso() {
        var now = new Date();
        var pad = function (n) { return (n < 10 ? "0" : "") + n; };
        return now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
    }

    function openGraduate() {
        var user = ns.state.selectedUser;
        var modal = graduateModal();
        var card = user && user.graduation;
        if (!modal || !card || !(card.enrolled || []).length) {
            return;
        }
        var esc = ns.escape;
        var nameEl = modal.querySelector("[data-rim-graduate-name]");
        if (nameEl) {
            nameEl.textContent = user.full_name || user.username;
        }
        var recordBox = modal.querySelector("[data-rim-graduate-records]");
        if (recordBox) {
            recordBox.innerHTML = card.enrolled.map(function (record, index) {
                var label = [record.group, record.program, record.admission_year].filter(Boolean).join(" · ");
                return '<label class="rim-choice"><input type="radio" name="rim-graduate-record" value="' + esc(record.id) + '"' +
                    (index === 0 ? " checked" : "") + "> <span>" + esc(label || record.id) + "</span></label>";
            }).join("");
        }
        var number = modal.querySelector("[data-rim-graduate-number]");
        var date = modal.querySelector("[data-rim-graduate-date]");
        var reason = modal.querySelector("[data-rim-graduate-reason]");
        if (number) {
            number.value = "";
            number.required = !card.order_optional;
        }
        if (date) {
            date.value = todayIso();
            date.required = !card.order_optional;
        }
        if (reason) {
            reason.value = "";
        }
        var waiver = modal.querySelector("[data-rim-graduate-waiver]");
        if (waiver) {
            waiver.hidden = !card.order_optional;
        }
        showError(modal.querySelector("[data-rim-graduate-error]"), "");
        ns.modals.close("[data-rim-detail-modal]");
        modal.hidden = false;
        if (number) {
            number.focus();
        }
    }

    function closeGraduate(reopenDetail) {
        var modal = graduateModal();
        if (modal) {
            modal.hidden = true;
        }
        if (reopenDetail && ns.state.selectedUser && ns.root()) {
            ns.modals.open("[data-rim-detail-modal]");
        }
    }

    function submitGraduate(button) {
        var modal = graduateModal();
        var user = ns.state.selectedUser;
        if (!modal || !user) {
            return;
        }
        var card = user.graduation || {};
        var number = modal.querySelector("[data-rim-graduate-number]");
        var date = modal.querySelector("[data-rim-graduate-date]");
        var reason = modal.querySelector("[data-rim-graduate-reason]");
        var picked = modal.querySelector('input[name="rim-graduate-record"]:checked');
        var errorEl = modal.querySelector("[data-rim-graduate-error]");
        if (!card.order_optional && (!number.value.trim() || !date.value)) {
            showError(errorEl, ns.t("err_order_required"));
            (number.value.trim() ? date : number).focus();
            return;
        }
        button.disabled = true;
        showError(errorEl, "");
        ns.actions.post({
            action: "graduate",
            record_id: picked ? picked.value : "",
            order_number: number.value.trim(),
            order_date: date.value,
            reason: reason ? reason.value.trim() : ""
        }).then(function () {
            closeGraduate(true);
        }).catch(function (err) {
            showError(errorEl, ns.errorMessage(err));
        }).then(function () {
            button.disabled = false;
        });
    }

    window.EMSReady.once("rim-detail-events", function () {
        var D = window.EMSDelegate;

        /* Əsas məlumatlar — yazdıqca «dəyişiklik var», sahədən çıxanda inline yoxlama. */
        D.on("input", "[data-rim-edit-form] [data-rim-edit-field]", function () {
            ns.actions.syncEditState();
        });
        D.on("change", "[data-rim-edit-form] [data-rim-edit-field]", function () {
            ns.actions.syncEditState();
        });
        D.on("focusout", "[data-rim-edit-form] input[data-rim-edit-field]", function (event, input) {
            ns.actions.validateField(input);
        });

        D.on("change", "[data-rim-position-select]", function (event, select) {
            var host = select.closest("[data-rim-position]");
            if (!host) {
                return;
            }
            syncPosition(host);
            var other = host.querySelector("[data-rim-position-other]");
            if (other && !other.hidden) {
                other.focus();
            }
        });
        D.on("input", "[data-rim-position-other]", function (event, input) {
            var host = input.closest("[data-rim-position]");
            if (host) {
                syncPosition(host);
            }
        });
        D.on("click", "[data-rim-position-save]", function (event, button) {
            event.preventDefault();
            var host = button.closest("[data-rim-position]");
            if (!host) {
                return;
            }
            var errorEl = host.querySelector("[data-rim-position-error]");
            button.disabled = true;
            showError(errorEl, "");
            ns.actions.post({ action: "edit", staff_position: positionValue(host), reason: "" }).catch(function (err) {
                showError(errorEl, ns.errorMessage(err));
                button.disabled = false;
            });
        });

        D.on("change", "select[data-rim-place-faculty]", function (event, select) {
            var host = select.closest("[data-rim-place]");
            if (host) {
                ns.detailView.filterUnits(host);
                syncPlace(host);
            }
        });
        D.on("change", "select[data-rim-place-unit]", function (event, select) {
            var host = select.closest("[data-rim-place]");
            if (host) {
                syncPlace(host);
            }
        });
        D.on("click", "[data-rim-place-save]", function (event, button) {
            event.preventDefault();
            var host = button.closest("[data-rim-place]");
            var unit = host && host.querySelector("select[data-rim-place-unit]");
            if (!host || !unit || !unit.value) {
                return;
            }
            var errorEl = host.querySelector("[data-rim-place-error]");
            button.disabled = true;
            showError(errorEl, "");
            ns.actions.post({
                action: "place_unit",
                membership_id: host.getAttribute("data-rim-place"),
                unit_id: unit.value,
                expected_unit_id: host.getAttribute("data-current-unit") || "",
                reason: ""
            }).catch(function (err) {
                showError(errorEl, ns.errorMessage(err));
                button.disabled = false;
            });
        });

        D.on("click", "[data-rim-graduate-open]", function (event) {
            event.preventDefault();
            openGraduate();
        });
        D.on("click", "[data-rim-graduate-close]", function (event) {
            event.preventDefault();
            closeGraduate(true);
        });
        D.on("click", "[data-rim-graduate-submit]", function (event, button) {
            event.preventDefault();
            submitGraduate(button);
        });
    });
})(window, document);

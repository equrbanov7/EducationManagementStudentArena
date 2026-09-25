/**
 * İşləmənin baxışı — irəliləyiş (poll), hadisə dialoqu, kilid/köçürmə, dərc, ləğv.
 * ─────────────────────────────────────────────────────────────────────
 * Hadisə detalları `#tt-events` json_script adasındadır. Server HƏR köçürməni sərt
 * qaydalara görə yoxlayır; rədd olunsa səbəblər dialoqda siyahı kimi görünür.
 * AJAX-safe: EMSDelegate + EMSReady.once (poll bir dəfə qurulur).
 */
(function (window, document) {
    "use strict";

    var TT = window.EMSTimetable;
    var current = { key: "", event: null };

    function root() {
        return document.querySelector("[data-tt-review]");
    }

    function events() {
        var node = document.getElementById("tt-events");
        if (!node) {
            return {};
        }
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (error) {
            return {};
        }
    }

    function action(scope, data) {
        return TT.post(scope.getAttribute("data-action-url"), data);
    }

    // ── İrəliləyiş ───────────────────────────────────────────────────────
    function poll(scope) {
        TT.get(scope.getAttribute("data-status-url"))
            .then(function (payload) {
                var bar = scope.querySelector("[data-tt-progress-bar]");
                var text = scope.querySelector("[data-tt-progress-text]");
                var sync = scope.querySelector("[data-tt-sync]");
                var pct = Math.round((Number(payload.frac) || 0) * 100);
                if (bar) {
                    bar.style.setProperty("--ems-bar-pct", pct + "%");
                }
                if (text && payload.phase) {
                    text.textContent = payload.status_label + " · " + payload.phase + " · " + pct + "%";
                }
                if (sync) {
                    sync.hidden = !payload.stale;
                }
                if (!payload.is_active) {
                    window.location.reload();
                    return;
                }
                window.setTimeout(function () {
                    poll(scope);
                }, 2000);
            })
            .catch(function () {
                window.setTimeout(function () {
                    poll(scope);
                }, 5000);
            });
    }

    window.EMSReady.once("tt-review-poll", function () {
        var scope = root();
        if (scope && scope.getAttribute("data-active") === "1") {
            poll(scope);
        }
    });

    window.EMSDelegate.on("click", "[data-tt-sync]", function (event, button) {
        var scope = root();
        if (!scope) {
            return;
        }
        TT.setBusy(button, true);
        action(scope, { action: "sync" })
            .then(function () {
                window.location.reload();
            })
            .catch(function (error) {
                TT.setBusy(button, false);
                TT.toast(TT.errorText(error, scope.getAttribute("data-msg-error")), "error");
            });
    });

    // ── Hadisə dialoqu ───────────────────────────────────────────────────
    function weekLabel(scope, code) {
        return scope.getAttribute("data-label-" + (code || "all")) || code;
    }

    function fill(scope, item) {
        var dialog = document.getElementById("ttEvent");
        if (!dialog) {
            return;
        }
        var values = {
            subject: (item.subject_code ? item.subject_code + " · " : "") + item.subject,
            kind: item.kind_label,
            groups: (item.groups || []).join(", "),
            teacher: item.teacher || "—",
            room: item.room || "—",
            week: weekLabel(scope, item.week_type),
            reason: item.reason || "—",
        };
        Object.keys(values).forEach(function (key) {
            var node = dialog.querySelector('[data-tt-f="' + key + '"]');
            if (node) {
                node.textContent = values[key];
            }
        });
        var day = dialog.querySelector("[data-tt-move-day]");
        var pair = dialog.querySelector("[data-tt-move-pair]");
        if (day) {
            day.value = item.weekday ? String(item.weekday) : "";
            window.EMSBootstrapSelect.sync(day);
        }
        if (pair) {
            pair.value = item.pair ? String(item.pair) : "";
            window.EMSBootstrapSelect.sync(pair);
        }
        var weekWrap = dialog.querySelector("[data-tt-move-week-wrap]");
        if (weekWrap) {
            weekWrap.hidden = !item.is_biweekly;
            dialog.querySelectorAll("[data-tt-move-week]").forEach(function (radio) {
                radio.checked = radio.value === (item.week_type === "even" ? "even" : "odd");
            });
        }
        var conflicts = dialog.querySelector("[data-tt-conflicts]");
        if (conflicts) {
            TT.clear(conflicts);
        }
    }

    window.EMSDelegate.on("click", "[data-tt-event]", function (event, button) {
        var scope = root();
        var key = button.getAttribute("data-tt-event");
        var item = events()[key];
        if (!scope || !item) {
            return;
        }
        current.key = key;
        current.event = item;
        fill(scope, item);
        if (window.EMSOverlay) {
            window.EMSOverlay.open("ttEvent");
        }
    });

    window.EMSDelegate.on("click", "[data-tt-lock]", function (event, button) {
        var scope = root();
        if (!scope || !current.event) {
            return;
        }
        TT.setBusy(button, true);
        action(scope, { action: current.event.locked ? "unlock" : "lock", key: current.key })
            .then(function () {
                window.location.reload();
            })
            .catch(function (error) {
                TT.setBusy(button, false);
                TT.toast(TT.errorText(error, scope.getAttribute("data-msg-error")), "error");
            });
    });

    window.EMSDelegate.on("click", "[data-tt-move-submit]", function (event, button) {
        var scope = root();
        var dialog = document.getElementById("ttEvent");
        if (!scope || !dialog || !current.event) {
            return;
        }
        var week = dialog.querySelector("[data-tt-move-week]:checked");
        var data = {
            action: "move",
            key: current.key,
            weekday: (dialog.querySelector("[data-tt-move-day]") || {}).value,
            pair: (dialog.querySelector("[data-tt-move-pair]") || {}).value,
            week_type: current.event.is_biweekly && week ? week.value : "all",
        };
        TT.setBusy(button, true);
        action(scope, data)
            .then(function () {
                window.location.reload();
            })
            .catch(function (error) {
                TT.setBusy(button, false);
                var payload = (error && error.payload) || {};
                var rows = payload.conflicts && payload.conflicts.length ? payload.conflicts : [TT.errorText(error, "")];
                TT.listItems(dialog.querySelector("[data-tt-conflicts]"), rows);
            });
    });

    // ── Dərc et / Ləğv et ────────────────────────────────────────────────
    window.EMSDelegate.on("click", "[data-tt-publish]", function (event, button) {
        var scope = root();
        var dialog = document.getElementById("ttPublish");
        if (!scope || !dialog) {
            return;
        }
        var reason = dialog.querySelector("[data-tt-publish-reason]");
        TT.setBusy(button, true);
        action(scope, { action: "publish", reason: reason ? reason.value : "" })
            .then(function (payload) {
                TT.toast(payload && payload.message, "success");
                window.location.reload();
            })
            .catch(function (error) {
                TT.setBusy(button, false);
                var payload = (error && error.payload) || {};
                var rows = [TT.errorText(error, scope.getAttribute("data-msg-error"))];
                (payload.conflicts || []).forEach(function (row) {
                    rows.push(row.kind_label + ": " + row.subject + " · " + row.group + " — " + row.other);
                });
                TT.listItems(dialog.querySelector("[data-tt-publish-conflicts]"), rows);
            });
    });

    window.EMSDelegate.on("click", "[data-tt-discard]", function (event, button) {
        var scope = root();
        if (!scope) {
            return;
        }
        window.EMSConfirm.open({ body: scope.getAttribute("data-msg-discard"), danger: true }).then(function (ok) {
            if (!ok) {
                return;
            }
            TT.setBusy(button, true);
            action(scope, { action: "discard" })
                .then(function () {
                    window.location.reload();
                })
                .catch(function (error) {
                    TT.setBusy(button, false);
                    TT.toast(TT.errorText(error, scope.getAttribute("data-msg-error")), "error");
                });
        });
    });
})(window, document);

/**
 * Yeni işləmə — əhatə, parametrlər, müəllim prioriteti, «Məlumatı yoxla», «İşlət».
 * ─────────────────────────────────────────────────────────────────────
 * Yoxlama nəticəsi `<template>`-lərdən qurulur (textContent — HTML inyeksiyası yox).
 * Prioritet siyahısı: sürüklə-burax + ↑/↓/✕ düymələri (klaviatura ilə əlçatan).
 * AJAX-safe: yalnız EMSDelegate.
 */
(function (window, document) {
    "use strict";

    var TT = window.EMSTimetable;
    var drag = { item: null };

    function root() {
        return document.querySelector("[data-tt-new]");
    }

    function checkedKind(scope) {
        var input = scope.querySelector("[data-tt-scope-kind]:checked");
        return input ? input.value : "faculty";
    }

    window.EMSDelegate.on("change", "[data-tt-scope-kind]", function () {
        var scope = root();
        if (!scope) {
            return;
        }
        var kind = checkedKind(scope);
        scope.querySelectorAll("[data-tt-scope-panel]").forEach(function (panel) {
            panel.hidden = panel.getAttribute("data-tt-scope-panel") !== kind;
        });
    });

    window.EMSDelegate.on("input", "[data-tt-group-filter]", function (event, input) {
        var needle = String(input.value || "").trim().toLowerCase();
        document.querySelectorAll("[data-tt-group-item]").forEach(function (item) {
            item.hidden = needle !== "" && (item.getAttribute("data-name") || "").indexOf(needle) < 0;
        });
    });

    function collectScope(scope) {
        var kind = checkedKind(scope);
        if (kind === "groups") {
            var ids = [];
            scope.querySelectorAll("[data-tt-group]:checked").forEach(function (box) {
                ids.push(box.value);
            });
            return { kind: kind, group_ids: ids, unit_ids: [] };
        }
        var select = scope.querySelector('[data-tt-scope-unit="' + kind + '"]');
        return { kind: kind, unit_ids: select && select.value ? [select.value] : [], group_ids: [] };
    }

    function collectParams(scope) {
        var params = { weekdays: [], weights: {} };
        scope.querySelectorAll("[data-tt-param]").forEach(function (field) {
            var key = field.getAttribute("data-tt-param");
            params[key] = field.type === "checkbox" ? field.checked : field.value;
        });
        scope.querySelectorAll("[data-tt-weekday]:checked").forEach(function (box) {
            params.weekdays.push(Number(box.value));
        });
        scope.querySelectorAll("[data-tt-weight]").forEach(function (field) {
            params.weights[field.getAttribute("data-tt-weight")] = field.value;
        });
        return params;
    }

    function collectPriorities(scope) {
        var ids = [];
        scope.querySelectorAll("[data-tt-prio-item]").forEach(function (item) {
            ids.push(item.getAttribute("data-id"));
        });
        return { teachers: ids };
    }

    function hasScope(data) {
        return (data.unit_ids && data.unit_ids.length) || (data.group_ids && data.group_ids.length);
    }

    function status(scope, text) {
        var node = scope.querySelector("[data-tt-status]");
        if (node) {
            node.textContent = text || "";
        }
    }

    // ── Yoxlama hesabatı ─────────────────────────────────────────────────
    function renderReport(scope, report) {
        var section = scope.querySelector("[data-tt-report]");
        var labels = scope.querySelector("[data-tt-summary-labels]");
        var summary = scope.querySelector("[data-tt-report-summary]");
        var items = scope.querySelector("[data-tt-report-items]");
        var kpiTemplate = scope.querySelector("[data-tt-kpi-template]");
        var itemTemplate = scope.querySelector("[data-tt-item-template]");
        TT.clear(summary);
        ["groups", "events", "weekly_pairs", "teachers", "streams"].forEach(function (key) {
            var tile = kpiTemplate.content.firstElementChild.cloneNode(true);
            tile.querySelector(".ems-kpi__label").textContent = labels.getAttribute("data-" + key) || key;
            tile.querySelector(".ems-kpi__value").textContent = String(report.summary[key]);
            summary.appendChild(tile);
        });
        scope.querySelector("[data-tt-report-verdict]").textContent = report.ok
            ? scope.getAttribute("data-msg-ok")
            : scope.getAttribute("data-msg-has-errors");
        TT.clear(items);
        (report.items || []).forEach(function (row) {
            var li = itemTemplate.content.firstElementChild.cloneNode(true);
            var badge = li.querySelector(".ems-badge");
            var tone = row.level === "error" ? "danger" : row.level === "warning" ? "warning" : "info";
            badge.classList.add("ems-badge--" + tone);
            badge.textContent = labels.getAttribute("data-level-" + row.level) || row.level;
            li.classList.add("is-" + row.level);
            li.querySelector(".tt-report__title").textContent = row.title;
            li.querySelector(".tt-report__count").textContent = row.count ? "(" + row.count + ")" : "";
            li.querySelector(".tt-report__detail").textContent = row.detail || "";
            TT.listItems(li.querySelector(".tt-report__rows"), row.rows);
            items.appendChild(li);
        });
        section.hidden = false;
    }

    function fillTeacherSelect(scope, teachers) {
        var select = scope.querySelector("[data-tt-prio-select]");
        if (!select) {
            return;
        }
        while (select.options.length > 1) {
            select.remove(1);
        }
        (teachers || []).forEach(function (teacher) {
            var option = document.createElement("option");
            option.value = String(teacher.id);
            option.textContent = teacher.name + " · " + teacher.load;
            select.appendChild(option);
        });
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.refresh(select);
        }
        scope.querySelector("[data-tt-prio-add]").hidden = false;
    }

    window.EMSDelegate.on("click", "[data-tt-precheck]", function (event, button) {
        var scope = root();
        if (!scope) {
            return;
        }
        var target = collectScope(scope);
        if (!hasScope(target)) {
            TT.toast(scope.getAttribute("data-msg-no-scope"), "warning");
            return;
        }
        TT.setBusy(button, true);
        status(scope, scope.getAttribute("data-msg-checking"));
        TT.post(scope.getAttribute("data-precheck-url"), {
            period: scope.getAttribute("data-period"),
            scope: target,
            params: collectParams(scope),
        })
            .then(function (payload) {
                renderReport(scope, payload.report);
                fillTeacherSelect(scope, payload.teachers);
                status(scope, "");
            })
            .catch(function (error) {
                status(scope, "");
                TT.toast(TT.errorText(error, scope.getAttribute("data-msg-error")), "error");
            })
            .then(function () {
                TT.setBusy(button, false);
            });
    });

    window.EMSDelegate.on("click", "[data-tt-start]", function (event, button) {
        var scope = root();
        if (!scope) {
            return;
        }
        var target = collectScope(scope);
        if (!hasScope(target)) {
            TT.toast(scope.getAttribute("data-msg-no-scope"), "warning");
            return;
        }
        var seed = scope.querySelector("[data-tt-seed]");
        TT.setBusy(button, true);
        status(scope, scope.getAttribute("data-msg-starting"));
        TT.post(scope.getAttribute("data-start-url"), {
            period: scope.getAttribute("data-period"),
            scope: target,
            params: collectParams(scope),
            priorities: collectPriorities(scope),
            seed: seed ? seed.value : 1,
            source_run: scope.getAttribute("data-source-run") || "",
        })
            .then(function (payload) {
                window.location.assign(payload.url);
            })
            .catch(function (error) {
                status(scope, "");
                TT.setBusy(button, false);
                TT.toast(TT.errorText(error, scope.getAttribute("data-msg-error")), "error");
            });
    });

    // ── Prioritet siyahısı ───────────────────────────────────────────────
    function syncEmpty(scope) {
        var empty = scope.querySelector("[data-tt-prio-empty]");
        if (empty) {
            empty.hidden = !!scope.querySelector("[data-tt-prio-item]");
        }
    }

    window.EMSDelegate.on("change", "[data-tt-prio-select]", function (event, select) {
        var scope = root();
        if (!scope || !select.value) {
            return;
        }
        var list = scope.querySelector("[data-tt-prio-list]");
        if (!list.querySelector('[data-tt-prio-item][data-id="' + select.value + '"]')) {
            var item = scope.querySelector("[data-tt-prio-template]").content.firstElementChild.cloneNode(true);
            item.setAttribute("data-id", select.value);
            var option = select.options[select.selectedIndex];
            item.querySelector(".tt-prio__name").textContent = (option.textContent || "").split(" · ")[0];
            list.appendChild(item);
        }
        select.value = "";
        if (window.EMSBootstrapSelect) {
            window.EMSBootstrapSelect.sync(select);
        }
        syncEmpty(scope);
    });

    window.EMSDelegate.on("click", "[data-tt-prio-up]", function (event, button) {
        var item = button.closest("[data-tt-prio-item]");
        if (item && item.previousElementSibling) {
            item.parentNode.insertBefore(item, item.previousElementSibling);
            button.focus();
        }
    });

    window.EMSDelegate.on("click", "[data-tt-prio-down]", function (event, button) {
        var item = button.closest("[data-tt-prio-item]");
        if (item && item.nextElementSibling) {
            item.parentNode.insertBefore(item.nextElementSibling, item);
            button.focus();
        }
    });

    window.EMSDelegate.on("click", "[data-tt-prio-remove]", function (event, button) {
        var item = button.closest("[data-tt-prio-item]");
        var scope = root();
        if (item) {
            item.parentNode.removeChild(item);
        }
        if (scope) {
            syncEmpty(scope);
        }
    });

    window.EMSDelegate.on("dragstart", "[data-tt-prio-item]", function (event, item) {
        drag.item = item;
        item.classList.add("is-dragging");
        if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", item.getAttribute("data-id") || "");
        }
    });

    window.EMSDelegate.on("dragover", "[data-tt-prio-item]", function (event, item) {
        if (!drag.item || drag.item === item) {
            return;
        }
        event.preventDefault();
        var rect = item.getBoundingClientRect();
        var after = event.clientY > rect.top + rect.height / 2;
        item.parentNode.insertBefore(drag.item, after ? item.nextElementSibling : item);
    });

    window.EMSDelegate.on("dragend", "[data-tt-prio-item]", function (event, item) {
        item.classList.remove("is-dragging");
        drag.item = null;
    });

    window.EMSDelegate.on("drop", "[data-tt-prio-item]", function (event) {
        event.preventDefault();
    });
})(window, document);

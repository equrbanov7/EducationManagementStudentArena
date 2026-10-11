/* «Jurnal təmizliyi» (sahib 2026-10-10) — RENDER köməkçiləri. Şablon: sections/journal_hygiene/_content.html.
 * Təmiz funksiyalar: DOM yalnız createElement + textContent ilə qurulur (innerHTML yoxdur → server mətni
 * HTML kimi şərh olunmur), şəbəkəyə getmir, vəziyyət saxlamır. Kontroller: journal_hygiene.js.
 * jsdom testi: tests/js/journal_hygiene.test.js.
 */
(function (window) {
    "use strict";

    if (window.EMSJournalHygieneRender) {
        return;
    }

    function el(tag, className, text) {
        var node = window.document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null && text !== "") {
            node.textContent = String(text);
        }
        return node;
    }

    /* «{n} sətir» → «5 sətir»; tanınmayan yer tutucu olduğu kimi qalır. */
    function fill(template, values) {
        return String(template || "").replace(/\{(\w+)\}/g, function (match, key) {
            return values && Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match;
        });
    }

    function badge(text, tone) {
        return el("span", "ems-badge ems-badge--" + (tone || "neutral") + " jh-badge", text);
    }

    function stack(primary, secondary) {
        var box = el("div", "jh-stack");
        box.appendChild(el("span", "jh-stack__main", primary || "—"));
        if (secondary) {
            box.appendChild(el("span", "jh-stack__sub", secondary));
        }
        return box;
    }

    function td(child, className) {
        var cell = el("td", className || "");
        if (child) {
            cell.appendChild(child);
        }
        return cell;
    }

    function checkbox(id, checked, disabled, label) {
        var input = el("input", "jh-check");
        input.type = "checkbox";
        input.value = id;
        input.setAttribute("data-jh-check", id);
        input.checked = Boolean(checked);
        input.disabled = Boolean(disabled);
        input.setAttribute("aria-label", label || id);
        return input;
    }

    function reasonsCell(row, i18n) {
        var box = el("div", "jh-tags");
        box.appendChild(badge(row.reason_label, row.strong ? "danger" : "warning"));
        (row.tags || []).forEach(function (tag) {
            if (tag.code !== row.reason) {
                box.appendChild(badge(tag.label, "info"));
            }
        });
        if (row.journal_closed) {
            box.appendChild(badge(i18n.journal_closed, "muted"));
        }
        box.appendChild(el("span", row.strong ? "jh-strength is-strong" : "jh-strength", row.strength_label));
        return box;
    }

    function dataCell(row, i18n) {
        var box = el("div", "jh-tags");
        box.appendChild(badge(row.has_evidence ? i18n.has_data : i18n.no_data, row.has_evidence ? "primary" : "success"));
        if (row.absence_hours) {
            box.appendChild(el("span", "jh-stack__sub", fill(i18n.absence, { n: row.absence_hours })));
        }
        if (row.group_size) {
            box.appendChild(el("span", "jh-stack__sub", fill(i18n.group_size, { n: row.group_size })));
        }
        return box;
    }

    /* Ayrılmış tələbə / boş fənn sətirləri. `options.selection` — `has(id)` olan dəst. */
    function rowsBody(tbody, rows, options) {
        var i18n = options.i18n || {};
        tbody.textContent = "";
        (rows || []).forEach(function (row) {
            var tr = el("tr", row.strong ? "jh-row is-strong" : "jh-row");
            tr.setAttribute("data-jh-row", row.id);
            tr.appendChild(td(checkbox(row.id, options.selection.has(row.id), !options.canSelect, row.student), "jh-td--check"));
            tr.appendChild(td(stack(row.student, row.username)));
            tr.appendChild(td(stack(row.subject, row.group)));
            tr.appendChild(td(el("span", "jh-nowrap", row.period)));
            tr.appendChild(td(reasonsCell(row, i18n)));
            tr.appendChild(td(dataCell(row, i18n)));
            tr.appendChild(td(badge(row.status_label, "neutral")));
            tbody.appendChild(tr);
        });
    }

    function decisionCell(row) {
        var box = el("div", "jh-stack");
        var line = el("span", "jh-stack__main");
        line.appendChild(badge(row.from_label, "neutral"));
        line.appendChild(el("span", "jh-arrow", "→"));
        line.appendChild(badge(row.to_label, row.to_status === "dropped" ? "danger" : "warning"));
        box.appendChild(line);
        box.appendChild(el("span", "jh-stack__sub", row.category_label + " · " + row.reason_label));
        return box;
    }

    function stateCell(row, i18n) {
        if (row.reverted) {
            return stack(i18n.reverted, [row.reverted_at, row.reverted_by].filter(Boolean).join(" · "));
        }
        return stack(i18n.active, row.can_revert ? "" : i18n.not_revertable);
    }

    /* Tarixçə: yalnız geri qaytarıla bilən qərar seçilə bilər. */
    function historyBody(tbody, rows, options) {
        var i18n = options.i18n || {};
        tbody.textContent = "";
        (rows || []).forEach(function (row) {
            var tr = el("tr", row.reverted ? "jh-row is-reverted" : "jh-row");
            tr.setAttribute("data-jh-row", row.id);
            var selectable = options.canSelect && row.can_revert;
            tr.appendChild(td(checkbox(row.id, options.selection.has(row.id), !selectable, row.student), "jh-td--check"));
            tr.appendChild(td(el("span", "jh-nowrap", row.decided_at)));
            tr.appendChild(td(el("span", "jh-stack__main", row.student)));
            tr.appendChild(td(stack(row.subject, [row.group, row.period].filter(Boolean).join(" · "))));
            tr.appendChild(td(decisionCell(row)));
            var who = stack(row.decided_by, row.reason);
            who.classList.add("jh-reason-text");
            tr.appendChild(td(who));
            tr.appendChild(td(stateCell(row, i18n)));
            tbody.appendChild(tr);
        });
    }

    /* Boş / xəta vəziyyəti — cədvəlin içində, bütün sütunları tutan tək sətir (ems-state). */
    function stateRow(tbody, title, kind) {
        tbody.textContent = "";
        var tr = el("tr", "jh-row jh-row--state");
        var cell = el("td", "");
        cell.colSpan = 7;
        var box = el("div", kind === "error" ? "ems-state ems-state--error" : "ems-state");
        box.setAttribute("role", "status");
        var icon = el("i", "fas " + (kind === "error" ? "fa-triangle-exclamation" : "fa-broom") + " ems-state__icon");
        icon.setAttribute("aria-hidden", "true");
        box.appendChild(icon);
        box.appendChild(el("p", "ems-state__title", title));
        cell.appendChild(box);
        tr.appendChild(cell);
        tbody.appendChild(tr);
    }

    /* Səbəb/mənbə çipləri — say serverdən; sıfır saylı çip göstərilmir (aktiv olan istisna). */
    function chips(container, options, counts, active, i18n) {
        container.textContent = "";
        var all = el("button", "ems-chip jh-chip", i18n.chip_all + " · " + (counts.total || 0));
        all.type = "button";
        all.setAttribute("data-jh-chip", "");
        all.setAttribute("aria-pressed", active ? "false" : "true");
        container.appendChild(all);
        (options || []).forEach(function (option) {
            var count = counts[option.value];
            if (option.value === "review") {
                count = Math.max(0, (counts.total || 0) - (counts.strong || 0));
            }
            if (!count && option.value !== active) {
                return;
            }
            var chip = el("button", "ems-chip jh-chip", option.label + " · " + (count || 0));
            chip.type = "button";
            chip.setAttribute("data-jh-chip", option.value);
            chip.setAttribute("aria-pressed", option.value === active ? "true" : "false");
            container.appendChild(chip);
        });
    }

    function pager(container, data, i18n) {
        container.textContent = "";
        if (!data || !data.total) {
            return;
        }
        var prev = el("button", "ems-btn ems-btn--sm", i18n.prev);
        prev.type = "button";
        prev.disabled = !data.has_previous;
        prev.setAttribute("data-jh-page", String(data.page - 1));
        var next = el("button", "ems-btn ems-btn--sm", i18n.next);
        next.type = "button";
        next.disabled = !data.has_next;
        next.setAttribute("data-jh-page", String(data.page + 1));
        container.appendChild(prev);
        container.appendChild(
            el("span", "jh-pager__info", fill(i18n.page, { page: data.page, pages: data.num_pages, total: data.total }))
        );
        container.appendChild(next);
    }

    function metric(label, value) {
        var box = el("div", "jh-metric");
        box.appendChild(el("span", "jh-metric__value", value));
        box.appendChild(el("span", "jh-metric__label", label));
        return box;
    }

    /* Önizləmə xülasəsi: saylar, toxunulan jurnallar, sübut cəmi, bloklananlar. */
    function preview(container, data, i18n) {
        container.textContent = "";
        var grid = el("div", "jh-metrics");
        grid.appendChild(metric(i18n.rows, data.rows));
        grid.appendChild(metric(i18n.journals, data.journals));
        grid.appendChild(metric(i18n.students, data.students));
        grid.appendChild(metric(i18n.with_evidence, data.with_evidence));
        grid.appendChild(metric(i18n.new_status, data.to_label));
        container.appendChild(grid);

        if (data.missing) {
            container.appendChild(el("p", "ems-msg ems-msg--warning jh-preview__msg", fill(i18n.missing, { n: data.missing })));
        }
        if (data.partial_total) {
            container.appendChild(el("p", "ems-msg ems-msg--error jh-preview__msg", fill(i18n.partial, { n: data.partial_total })));
        }
        if (data.blocked_total) {
            container.appendChild(el("p", "ems-msg ems-msg--error jh-preview__msg", fill(i18n.blocked, { n: data.blocked_total })));
        }

        var sources = i18n.sources || {};
        var keys = Object.keys(data.evidence_totals || {});
        container.appendChild(el("h3", "jh-preview__title", i18n.evidence_totals));
        if (!keys.length) {
            container.appendChild(el("p", "jh-preview__note", i18n.no_evidence));
        } else {
            var evidence = el("ul", "jh-preview__list");
            keys.forEach(function (key) {
                evidence.appendChild(el("li", "", (sources[key] || key) + ": " + data.evidence_totals[key]));
            });
            container.appendChild(evidence);
        }

        container.appendChild(el("h3", "jh-preview__title", i18n.journal_list));
        var list = el("ul", "jh-preview__list");
        (data.journal_list || []).forEach(function (item) {
            var text = [item.subject, item.group, item.period].filter(Boolean).join(" · ");
            list.appendChild(el("li", "", text + " — " + item.rows + " " + i18n.rows_unit));
        });
        container.appendChild(list);
        var more = (data.journals || 0) - (data.journal_list || []).length;
        if (more > 0) {
            container.appendChild(el("p", "jh-preview__note", fill(i18n.journal_more, { n: more })));
        }
    }

    window.EMSJournalHygieneRender = {
        chips: chips,
        el: el,
        fill: fill,
        historyBody: historyBody,
        pager: pager,
        preview: preview,
        rowsBody: rowsBody,
        stateRow: stateRow,
    };
})(window);

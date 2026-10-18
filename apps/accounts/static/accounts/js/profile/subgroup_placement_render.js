/* «Alt qrupa tələbə əlavə et» (sahib 2026-10-18) — RENDER köməkçiləri. Şablon: sections/subgroup_placement/_content.html.
 *
 * Yalnız DOM qurur: mətnlər `textContent` ilə yazılır (server datası HTML kimi şərh olunmur), şəbəkəyə getmir,
 * vəziyyət saxlamır. Kontroller: subgroup_placement.js. jsdom testi: tests/js/subgroup_placement.test.js.
 */
(function (window, document) {
    "use strict";

    if (window.EMSSubgroupPlacementRender) {
        return;
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null && text !== "") {
            node.textContent = String(text);
        }
        return node;
    }

    function clear(node) {
        while (node && node.firstChild) {
            node.removeChild(node.firstChild);
        }
    }

    function badge(kind, text) {
        return el("span", "ems-badge ems-badge--" + kind, text);
    }

    function kpi(label, value, note, accent) {
        var box = el("div", "ems-kpi" + (accent ? " ems-kpi--accent-" + accent : ""));
        box.appendChild(el("div", "ems-kpi__label", label));
        box.appendChild(el("div", "ems-kpi__value", value));
        if (note) {
            box.appendChild(el("div", "ems-kpi__note", note));
        }
        return box;
    }

    function creditKpis(credit, s) {
        var row = el("div", "ems-kpis ems-kpis--4 sgp-kpis");
        var accent = credit.over_limit ? "danger" : credit.remaining <= 3 ? "warning" : "success";
        row.appendChild(
            kpi(s.this_semester, credit.total + " / " + credit.limit, s.credits, accent)
        );
        row.appendChild(kpi(s.own, String(credit.own), s.credits, "primary"));
        row.appendChild(kpi(s.subgroup, String(credit.subgroup), s.credits, credit.subgroup ? "warning" : ""));
        row.appendChild(kpi(s.remaining, String(credit.remaining), s.limit + ": " + credit.limit, ""));
        return row;
    }

    function historyItem(row, s, canWrite) {
        var item = el("li", "sgp-history__item" + (row.undone ? " is-undone" : ""));
        var head = el("div", "sgp-history__head");
        head.appendChild(el("strong", "sgp-history__who", row.student));
        head.appendChild(el("span", "sgp-history__what", row.subject_name + " · " + row.source_group + " → " + row.target_group));
        head.appendChild(row.undone ? badge("muted", s.undone) : badge("success", s.placed));
        if (row.retake) {
            head.appendChild(badge("warning", s.retake));
        }
        item.appendChild(head);
        var meta = el("div", "sgp-history__meta");
        meta.appendChild(el("span", "", s.at + ": " + row.created_at));
        meta.appendChild(el("span", "", s.by + ": " + (row.actor || "—")));
        meta.appendChild(el("span", "", s.credits + ": " + row.credits_before + " → " + row.credits_after + " / " + row.credit_limit));
        if (row.order_number || row.order_date) {
            meta.appendChild(el("span", "", s.order + ": " + [row.order_number, row.order_date].filter(Boolean).join(" · ")));
        }
        if (row.document_url) {
            var link = el("a", "sgp-history__doc", s.document);
            link.href = row.document_url;
            link.target = "_blank";
            link.rel = "noopener";
            meta.appendChild(link);
        }
        item.appendChild(meta);
        if (row.reason) {
            item.appendChild(el("p", "sgp-history__reason", s.reason + ": " + row.reason));
        }
        if (row.undo) {
            item.appendChild(
                el("p", "sgp-history__undo", s.undone + " — " + row.undo.created_at + " · " + row.undo.actor + " · " + row.undo.reason)
            );
        } else if (canWrite) {
            var button = el("button", "ems-btn ems-btn--sm ems-btn--ghost sgp-history__btn", s.undo);
            button.type = "button";
            button.setAttribute("data-sgp-undo", row.id);
            button.setAttribute("data-sgp-undo-label", row.student + " · " + row.subject_name + " (" + row.target_group + ")");
            item.appendChild(button);
        }
        return item;
    }

    function history(list, rows, s, options) {
        options = options || {};
        if (!options.append) {
            clear(list);
        }
        (rows || []).forEach(function (row) {
            list.appendChild(historyItem(row, s, !!options.canWrite));
        });
        if (!list.firstChild) {
            list.appendChild(el("li", "sgp-history__empty", options.emptyText || s.recent_none));
        }
    }

    function summary(container, data, s, canWrite) {
        clear(container);
        var ctx = el("div", "sgp-ctx");
        ctx.appendChild(el("span", "sgp-ctx__item sgp-ctx__name", data.name));
        if (data.group) {
            ctx.appendChild(el("span", "sgp-ctx__item", data.group));
        }
        ctx.appendChild(el("span", "sgp-ctx__item", data.program));
        if (data.period) {
            ctx.appendChild(el("span", "sgp-ctx__item", data.period));
        }
        container.appendChild(ctx);
        container.appendChild(creditKpis(data.credit, s));
        if (data.credit.over_limit) {
            container.appendChild(el("div", "ems-banner ems-banner--warning sgp-inline-msg", s.over_limit));
        }

        var failed = el("div", "sgp-block");
        failed.appendChild(el("h3", "sgp-block__title", s.failed_title));
        if (data.failed && data.failed.length) {
            var chips = el("div", "sgp-chips");
            data.failed.forEach(function (row) {
                var chip = el("button", "sgp-chip sgp-chip--failed");
                chip.type = "button";
                chip.title = s.failed_pick;
                chip.setAttribute("data-sgp-pick-subject", row.subject_id);
                chip.setAttribute("data-sgp-pick-text", row.name + " · " + row.code);
                chip.appendChild(el("span", "sgp-chip__name", row.name));
                chip.appendChild(el("span", "sgp-chip__meta", row.ects + " " + s.credits + " · " + row.last_period));
                chips.appendChild(chip);
            });
            failed.appendChild(chips);
        } else {
            failed.appendChild(el("p", "sgp-muted", s.failed_none));
        }
        container.appendChild(failed);

        var current = el("div", "sgp-block");
        current.appendChild(el("h3", "sgp-block__title", s.current_title));
        var list = el("ul", "sgp-subjects");
        (data.subjects || []).forEach(function (row) {
            var item = el("li", "sgp-subjects__item");
            item.appendChild(el("span", "sgp-subjects__name", row.subject_name));
            item.appendChild(el("span", "sgp-subjects__credit", row.credits + " " + s.credits));
            if (row.is_subgroup) {
                item.appendChild(badge("warning", s.subgroup + " · " + row.group_name));
            }
            list.appendChild(item);
        });
        current.appendChild(list);
        container.appendChild(current);

        var past = el("div", "sgp-block");
        past.appendChild(el("h3", "sgp-block__title", s.history_title));
        var plist = el("ul", "sgp-history sgp-history--compact");
        history(plist, data.placements, s, { canWrite: canWrite, emptyText: s.history_none });
        past.appendChild(plist);
        container.appendChild(past);
    }

    function slotText(slot) {
        return slot.weekday_label + " " + slot.start + "–" + slot.end + " · " + slot.kind_label + (slot.room ? " · " + slot.room : "");
    }

    function offering(row, s, selectedId) {
        var blocked = row.locked || row.full || row.already_enrolled;
        var card = el("button", "ems-pick sgp-pick" + (row.id === selectedId ? " is-selected" : "") + (blocked ? " is-disabled" : ""));
        card.type = "button";
        card.setAttribute("role", "radio");
        card.setAttribute("aria-checked", row.id === selectedId ? "true" : "false");
        card.setAttribute("data-sgp-offering", row.id);
        if (blocked) {
            card.disabled = true;
        }
        var title = el("div", "ems-pick__title sgp-pick__title");
        title.appendChild(el("span", "", row.group_name || "—"));
        if (row.locked) {
            title.appendChild(badge("muted", s.locked));
        } else if (row.already_enrolled) {
            title.appendChild(badge("info", s.already_here));
        } else if (row.full) {
            title.appendChild(badge("danger", s.full));
        }
        card.appendChild(title);
        card.appendChild(el("div", "ems-pick__note", s.teacher + ": " + (row.teacher || s.no_teacher)));
        var slots = row.slots && row.slots.length ? row.slots.map(slotText).join(" · ") : s.no_schedule;
        card.appendChild(el("div", "ems-pick__note", s.schedule + ": " + slots));
        var seats = row.enrolled + " " + s.students + (row.free !== null && row.free !== undefined ? " · " + row.free + " " + s.free : "");
        card.appendChild(el("div", "ems-pick__note", seats));
        var p = row.projection || {};
        var credit = el("div", "ems-pick__note sgp-pick__credit" + (p.fits === false ? " is-over" : ""));
        credit.textContent = s.credit_impact + ": +" + row.credits + " → " + p.total_after + " / " + p.limit;
        card.appendChild(credit);
        if (row.clashes && row.clashes.length) {
            row.clashes.forEach(function (clash) {
                card.appendChild(
                    el("div", "ems-pick__warn", s.clash + ": " + slotText(clash) + " — " + clash.with_subject + " (" + clash.with_time + ") " + s.clash_with)
                );
            });
        } else {
            card.appendChild(el("div", "ems-pick__note sgp-pick__ok", s.no_clash));
        }
        if (row.releases_own) {
            card.appendChild(el("div", "ems-pick__note", s.releases_own));
        }
        return card;
    }

    function offerings(container, rows, s, selectedId) {
        clear(container);
        if (!rows || !rows.length) {
            container.appendChild(el("p", "sgp-muted", s.no_offerings));
            return;
        }
        rows.forEach(function (row) {
            container.appendChild(offering(row, s, selectedId));
        });
    }

    function checks(container, preview, s) {
        clear(container);
        if (!preview) {
            return;
        }
        var ok = preview.ok;
        var box = el("div", "ems-banner " + (ok ? "ems-banner--success" : "ems-banner--danger") + " sgp-checks__box");
        var body = el("div", "");
        body.appendChild(el("div", "ems-banner__title", ok ? s.checks_ok : s.checks_fail));
        if (!ok) {
            var list = el("ul", "ems-banner__body sgp-checks__list");
            (preview.errors || []).forEach(function (error) {
                list.appendChild(el("li", "", error.message));
            });
            body.appendChild(list);
        }
        box.appendChild(body);
        container.appendChild(box);
        (preview.warnings || []).forEach(function (warning) {
            container.appendChild(el("div", "ems-banner ems-banner--warning sgp-inline-msg", s.warning + ": " + warning.message));
        });
        if (preview.projection) {
            var p = preview.projection;
            container.appendChild(
                el("p", "sgp-checks__credit" + (p.fits ? "" : " is-over"), s.after + ": " + p.total_after + " / " + p.limit + " " + s.credits)
            );
        }
        if (preview.retake) {
            container.appendChild(badge("warning", s.retake));
        }
    }

    function result(container, payload, s) {
        clear(container);
        container.hidden = false;
        var ok = !!payload.ok;
        var box = el("div", "ems-banner " + (ok ? "ems-banner--success" : "ems-banner--danger"));
        var body = el("div", "");
        body.appendChild(el("div", "ems-banner__title", payload.message || (ok ? s.placed : s.error)));
        if (ok && payload.credit) {
            body.appendChild(el("div", "ems-banner__body", s.credits + ": " + payload.credit.before + " → " + payload.credit.after + " / " + payload.credit.limit));
        }
        box.appendChild(body);
        container.appendChild(box);
    }

    window.EMSSubgroupPlacementRender = {
        el: el,
        clear: clear,
        summary: summary,
        offerings: offerings,
        checks: checks,
        history: history,
        result: result,
    };
})(window, document);

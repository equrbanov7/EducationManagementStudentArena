/**
 * «Fənn təhvili» — SAF RENDER alt modulu (`window.EMSHandoverRender`).
 *
 * Niyə ayrı fayl? Modul ölçü büdcəsi (SOFT_CAP = 600 sətir) + iş bölgüsü:
 * burada YALNIZ «data → DOM» funksiyaları var, vəziyyət (state) və şəbəkə
 * çağırışları YOXDUR. Əsas modul (`teaching_handover.js`) onu null-safe
 * çağırır, ona görə yüklənmə sırası pozulsa da səhifə çökmür.
 *
 * `people_academic_preview.js` ilə eyni naxış.
 */
(function () {
    "use strict";

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null) {
            node.textContent = String(text);
        }
        return node;
    }

    /** Yüklənmə skeleti — «boş cədvəl» təəssüratının qarşısını alır. */
    function skeleton(body, columns, rows) {
        if (!body) {
            return;
        }
        body.innerHTML = "";
        for (var i = 0; i < (rows || 4); i += 1) {
            var tr = document.createElement("tr");
            for (var c = 0; c < columns; c += 1) {
                var td = document.createElement("td");
                td.appendChild(el("div", "thx-skel"));
                tr.appendChild(td);
            }
            body.appendChild(tr);
        }
    }

    /** Boş/xəta vəziyyəti — tək sətirlik mənalı mesaj. */
    function message(body, columns, text) {
        if (!body) {
            return;
        }
        body.innerHTML = "";
        var tr = document.createElement("tr");
        var td = document.createElement("td");
        td.colSpan = columns;
        td.className = "thx-empty";
        td.textContent = text || "";
        tr.appendChild(td);
        body.appendChild(tr);
    }

    /** Səhifələmə — `onGo(pageNumber)` ilə geri çağırır. */
    function pager(host, data, labels, onGo) {
        if (!host) {
            return;
        }
        host.innerHTML = "";
        if (!data || !data.num_pages || data.num_pages <= 1) {
            return;
        }
        var prev = el("button", "thx-btn thx-btn--ghost", labels.prev);
        prev.type = "button";
        prev.disabled = !data.has_previous;
        prev.addEventListener("click", function () {
            onGo(data.page - 1);
        });
        var next = el("button", "thx-btn thx-btn--ghost", labels.next);
        next.type = "button";
        next.disabled = !data.has_next;
        next.addEventListener("click", function () {
            onGo(data.page + 1);
        });
        host.appendChild(prev);
        host.appendChild(el("span", "", labels.page + " " + data.page + " / " + data.num_pages));
        host.appendChild(next);
    }

    /** «Yeni müəllim» xanası — seçilmiş ad + seçim düyməsi. */
    function targetCell(row, chosen, labels) {
        var cell = document.createElement("td");
        var box = el("div", "thx-target");
        if (chosen) {
            box.appendChild(el("span", "thx-target__name", chosen.name));
        }
        var button = el("button", "thx-table__link", chosen ? labels.change : labels.choose);
        button.type = "button";
        button.dataset.thxPick = row.id;
        box.appendChild(button);
        cell.appendChild(box);
        return cell;
    }

    /**
     * Bloker xanası — «niyə təhvil verilə bilməz».
     * Status RƏNGDƏN BAŞQA MƏTNLƏ də verilir (a11y: rəng tək daşıyıcı deyil).
     */
    function blockerCell(row, labels) {
        var cell = document.createElement("td");
        var list = el("ul", "thx-blockers");
        (row.blockers || []).forEach(function (blocker) {
            var item = document.createElement("li");
            var icon = document.createElement("i");
            icon.className = "fas fa-lock";
            icon.setAttribute("aria-hidden", "true");
            item.appendChild(icon);
            item.appendChild(document.createTextNode(" " + blocker.label));
            list.appendChild(item);
        });
        if (!list.children.length) {
            list.appendChild(el("li", "", labels.blocked));
        }
        cell.appendChild(list);
        return cell;
    }

    /** Cədvəl sətri (seçim + fənn + qrup + semestr + təsir + müəllimlər). */
    function offeringRow(row, options) {
        var labels = options.labels;
        var tr = document.createElement("tr");
        tr.dataset.thxRow = row.id;
        if (!row.can_transfer) {
            tr.className = "is-blocked";
        } else if (options.isSelected) {
            tr.className = "is-selected";
        }

        var checkCell = document.createElement("td");
        var box = document.createElement("input");
        box.type = "checkbox";
        box.dataset.thxCheck = row.id;
        box.checked = !!options.isSelected;
        box.disabled = !row.can_transfer;
        box.setAttribute("aria-label", row.subject_name || row.subject_code || "");
        checkCell.appendChild(box);
        tr.appendChild(checkCell);

        var subjectCell = document.createElement("td");
        var wrap = el("div", "thx-subject");
        wrap.appendChild(el("span", "thx-subject__code", row.subject_code || ""));
        wrap.appendChild(el("span", "thx-subject__name", row.subject_name || ""));
        subjectCell.appendChild(wrap);
        tr.appendChild(subjectCell);

        tr.appendChild(el("td", "", row.group || "—"));
        tr.appendChild(el("td", "", row.period || "—"));

        var impactCell = document.createElement("td");
        var impact = el("div", "thx-impact");
        [
            [row.students, labels.students],
            [row.lessons, labels.lessons],
            [row.marks, labels.marks]
        ].forEach(function (pair) {
            impact.appendChild(el("span", "thx-impact__chip", (pair[0] || 0) + " " + (pair[1] || "")));
        });
        impactCell.appendChild(impact);
        tr.appendChild(impactCell);

        tr.appendChild(el("td", "", (row.instructor && row.instructor.name) || labels.noInstructor));
        tr.appendChild(
            row.can_transfer ? targetCell(row, options.chosen, labels) : blockerCell(row, labels)
        );
        return tr;
    }

    /**
     * Tarixçə sətri — geri qaytarma düyməsi yalnız SERVERİN qəbul edəcəyi sətirdə.
     *
     * ⚠️ Əvvəl `can_revert` yalnız «geri qaytarılmayıb + zəncir yerindədir»
     * demək idi, ona görə dövr bitmiş sətirdə də düymə AKTİV çəkilirdi və klik
     * hər dəfə 409 verirdi.  İndi server `revert_blockers` (kod + etiket)
     * göndərir; düymə yoxdursa səbəb «—» əvəzinə YAZILIR.
     */
    function historyRow(row, labels) {
        var tr = document.createElement("tr");
        tr.appendChild(el("td", "", (row.created_at || "").slice(0, 10)));
        tr.appendChild(el("td", "", (row.subject || "") + " · " + (row.group || "")));
        tr.appendChild(el("td", "", row.from_name + " → " + row.to_name));
        tr.appendChild(el("td", "", row.reason || ""));

        var actions = document.createElement("td");
        if (row.is_reverted) {
            actions.textContent = labels.reverted;
        } else if (row.can_revert) {
            var button = el("button", "thx-table__link", labels.revert);
            button.type = "button";
            button.dataset.thxRevert = row.id;
            button.dataset.thxRevertLabel = (row.subject || "") + " · " + (row.group || "");
            button.dataset.thxRevertMove = row.to_name + " → " + row.from_name;
            actions.appendChild(button);
        } else {
            actions.appendChild(revertBlockerList(row, labels));
        }
        tr.appendChild(actions);
        return tr;
    }

    /** Geri qaytarmanın MÜMKÜN OLMAMA səbəbləri (server kodları + etiketləri). */
    function revertBlockerList(row, labels) {
        var list = el("ul", "thx-blockers");
        (row.revert_blockers || []).forEach(function (blocker) {
            var item = document.createElement("li");
            var icon = document.createElement("i");
            icon.className = "fas fa-lock";
            icon.setAttribute("aria-hidden", "true");
            item.appendChild(icon);
            item.appendChild(document.createTextNode(" " + blocker.label));
            list.appendChild(item);
        });
        if (!list.children.length) {
            list.appendChild(el("li", "", labels.revertBlocked || "—"));
        }
        return list;
    }

    /** Təsdiq dialoqunun xülasə kartları. */
    function summaryCards(host, items) {
        if (!host) {
            return;
        }
        host.innerHTML = "";
        items.forEach(function (item) {
            var card = el("div", "thx-summary");
            card.appendChild(el("div", "thx-summary__head", item.head));
            card.appendChild(el("div", "thx-summary__meta", item.meta));
            card.appendChild(el("div", "thx-summary__move", item.move));
            host.appendChild(card);
        });
    }

    window.EMSHandoverRender = {
        el: el,
        skeleton: skeleton,
        message: message,
        pager: pager,
        offeringRow: offeringRow,
        targetCell: targetCell,
        historyRow: historyRow,
        summaryCards: summaryCards
    };
})();

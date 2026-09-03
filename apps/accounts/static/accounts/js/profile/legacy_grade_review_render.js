/**
 * «Köçürülmüş nəticələrin dəqiqləşdirilməsi» — SAF RENDER alt modulu.
 *
 * `window.EMSLegacyReviewRender` altında yalnız «data → DOM» funksiyaları var:
 * vəziyyət (state) və şəbəkə çağırışı YOXDUR. Əsas modul onu null-safe çağırır,
 * ona görə yüklənmə sırası pozulsa da bölmə çökmür.
 *
 * Niyə ayrı fayl? Modul ölçü büdcəsi (SOFT_CAP = 600 sətir) + iş bölgüsü —
 * `teaching_handover_render.js` ilə eyni naxış.
 *
 * ⚠️ MƏTN HƏMİŞƏ `textContent` ilə yazılır. Sətirlərdə tələbə adı, köhnə jurnal
 * referansı və operator qeydi var — `innerHTML` burada XSS qapısı olardı.
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

    /** Skeleton — «boş cədvəl» təəssüratının qarşısını alır. */
    function skeleton(body, columns, rows) {
        if (!body) {
            return;
        }
        body.innerHTML = "";
        for (var i = 0; i < (rows || 5); i += 1) {
            var tr = document.createElement("tr");
            for (var c = 0; c < columns; c += 1) {
                var td = document.createElement("td");
                td.appendChild(el("div", "lgr-skel"));
                tr.appendChild(td);
            }
            body.appendChild(tr);
        }
    }

    function message(body, columns, text) {
        if (!body) {
            return;
        }
        body.innerHTML = "";
        var tr = document.createElement("tr");
        var td = document.createElement("td");
        td.colSpan = columns;
        td.className = "lgr-empty";
        td.textContent = text || "";
        tr.appendChild(td);
        body.appendChild(tr);
    }

    /** Kateqoriya çipləri — say + şiddət rəngi; klik süzgəci dəyişir. */
    function categories(host, rows, active, onToggle) {
        if (!host) {
            return;
        }
        host.innerHTML = "";
        (rows || []).forEach(function (row) {
            var chip = el("button", "lgr-chip is-" + row.severity);
            chip.type = "button";
            chip.title = row.hint || "";
            chip.setAttribute("aria-pressed", active.indexOf(row.code) === -1 ? "false" : "true");
            if (active.indexOf(row.code) !== -1) {
                chip.classList.add("is-active");
            }
            chip.appendChild(el("span", "lgr-chip__label", row.label));
            chip.appendChild(el("span", "lgr-chip__count", row.total));
            // Baxılmışların sayı ayrıca göstərilir: operator hansı kateqoriyada
            // işin bitdiyini bir baxışda görsün.
            chip.appendChild(el("span", "lgr-chip__done", "· " + row.reviewed));
            chip.addEventListener("click", function () {
                onToggle(row.code);
            });
            host.appendChild(chip);
        });
    }

    /** İrəliləyiş — «N / M baxılıb» + zolaq. */
    function progress(fill, text, data, labels) {
        if (!data) {
            return;
        }
        if (fill) {
            fill.style.width = String(data.percent || 0) + "%";
        }
        if (text) {
            text.textContent =
                String(data.reviewed || 0) +
                " / " +
                String(data.total || 0) +
                " " +
                (labels.progressOf || "") +
                " " +
                (labels.progress || "") +
                " (" +
                String(data.percent || 0) +
                "%)";
        }
    }

    function pager(host, data, labels, onGo) {
        if (!host) {
            return;
        }
        host.innerHTML = "";
        if (!data || !data.num_pages || data.num_pages <= 1) {
            return;
        }
        var prev = el("button", "lgr-btn lgr-btn--ghost", labels.prev);
        prev.type = "button";
        prev.disabled = !data.has_previous;
        prev.addEventListener("click", function () {
            onGo(data.page - 1);
        });
        var next = el("button", "lgr-btn lgr-btn--ghost", labels.next);
        next.type = "button";
        next.disabled = !data.has_next;
        next.addEventListener("click", function () {
            onGo(data.page + 1);
        });
        host.appendChild(prev);
        host.appendChild(el("span", "lgr-pager__label", labels.page + " " + data.page + " / " + data.num_pages));
        host.appendChild(next);
    }

    /** Xam bal xanası — dəyərlər OLDUĞU KİMİ (clamp/round yoxdur). */
    function rawCell(row, labels) {
        var cell = document.createElement("td");
        var list = el("ul", "lgr-raw");
        [
            [labels.entry, row.entry_score],
            [labels.exam, row.exam_score],
            [labels.resit, row.resit_score],
            [labels.final, row.final_score]
        ].forEach(function (pair) {
            if (!pair[1]) {
                return;
            }
            var item = el("li", "lgr-raw__item");
            item.appendChild(el("span", "lgr-raw__key", pair[0]));
            item.appendChild(el("b", "lgr-raw__value", pair[1]));
            list.appendChild(item);
        });
        cell.appendChild(list);
        if (row.source_reference) {
            cell.appendChild(el("span", "lgr-source", row.source_reference));
        }
        return cell;
    }

    /** Canlı sistem güzgüsü — köçürmənin dəqiqliyi məhz burada görünür. */
    function liveCell(row, labels) {
        var cell = document.createElement("td");
        if (!row.is_live) {
            cell.appendChild(el("span", "lgr-muted", labels.noLive));
            return cell;
        }
        cell.appendChild(el("b", "lgr-live", row.live_exam_score));
        return cell;
    }

    /**
     * «Niyə burada» xanası — kateqoriya nişanları.
     * Status RƏNGDƏN BAŞQA MƏTNLƏ də verilir (a11y: rəng tək daşıyıcı deyil).
     */
    function reasonCell(row) {
        var cell = document.createElement("td");
        var list = el("ul", "lgr-reasons");
        (row.categories || []).forEach(function (category) {
            var item = el("li", "lgr-reason is-" + category.severity);
            item.appendChild(el("span", "lgr-reason__label", category.label));
            item.title = category.hint || "";
            list.appendChild(item);
        });
        cell.appendChild(list);
        return cell;
    }

    function reviewCell(row) {
        var cell = document.createElement("td");
        var state = row.review || {};
        cell.appendChild(el("span", "lgr-status is-" + (state.status || "pending"), state.status_label || ""));
        if (state.reviewed_by) {
            cell.appendChild(el("span", "lgr-status__by", state.reviewed_by + " · " + (state.reviewed_at || "")));
        }
        if (state.note) {
            cell.appendChild(el("span", "lgr-status__note", state.note));
        }
        return cell;
    }

    /** Əməl xanası — icazə YOXDURSA düymələr ÜMUMİYYƏTLƏ qurulmur. */
    function actionCell(row, labels, canReview) {
        var cell = document.createElement("td");
        cell.className = "lgr-td--actions";
        if (!canReview) {
            return cell;
        }
        var box = el("div", "lgr-actions");
        // Səbəb qeydi düymələrin ARASINA yox, SONUNA qoyulur: aralarına düşsə
        // flex sarğısı qrupu iki yerə bölür və qonşu sətirlərlə düzülüş pozulur.
        var why = null;
        [
            ["verify", labels.verify, "lgr-btn--ok"],
            ["correct", labels.correct, "lgr-btn--warn"],
            ["dispute", labels.dispute, "lgr-btn--ghost"]
        ].forEach(function (spec) {
            if (spec[0] === "correct" && !row.can_correct) {
                // Qeydiyyata bağlanmayan faktın düzəliş hədəfi yoxdur: düyməni
                // GÖSTƏRMİRİK (səssiz 403 əvəzinə anlaşılan səbəb).
                why = el("span", "lgr-muted", labels.unlinked);
                return;
            }
            var button = el("button", "lgr-btn " + spec[2], spec[1]);
            button.type = "button";
            button.dataset.lgrAction = spec[0];
            button.dataset.lgrFact = row.id;
            box.appendChild(button);
        });
        if (why) {
            box.appendChild(why);
        }
        cell.appendChild(box);
        return cell;
    }

    function rows(body, data, labels, canReview) {
        if (!body) {
            return;
        }
        body.innerHTML = "";
        data.forEach(function (row) {
            var tr = document.createElement("tr");
            tr.className = "lgr-row is-" + row.severity;
            tr.dataset.lgrRow = row.id;

            var who = document.createElement("td");
            who.appendChild(el("span", "lgr-student", row.student));
            if (row.student_username) {
                who.appendChild(el("span", "lgr-muted", row.student_username));
            }
            if (row.source_student_ref) {
                who.appendChild(el("span", "lgr-muted", "#" + row.source_student_ref));
            }
            tr.appendChild(who);

            var where = document.createElement("td");
            where.appendChild(el("span", "lgr-subject", [row.subject_code, row.subject].filter(Boolean).join(" — ")));
            if (row.group) {
                where.appendChild(el("span", "lgr-muted", row.group));
            }
            if (row.teacher) {
                where.appendChild(el("span", "lgr-muted", row.teacher));
            }
            if (row.period) {
                where.appendChild(el("span", "lgr-muted", row.period));
            }
            tr.appendChild(where);

            tr.appendChild(rawCell(row, labels));
            tr.appendChild(liveCell(row, labels));
            tr.appendChild(reasonCell(row));
            tr.appendChild(reviewCell(row));
            tr.appendChild(actionCell(row, labels, canReview));
            body.appendChild(tr);
        });
    }

    /** `<select>`-i serverdən gələn variantlarla doldurur (ilk «Hamısı» qalır). */
    function fillSelect(node, options) {
        if (!node) {
            return;
        }
        while (node.options.length > 1) {
            node.remove(1);
        }
        (options || []).forEach(function (option) {
            var item = document.createElement("option");
            item.value = option.id;
            item.textContent = option.label;
            node.appendChild(item);
        });
        if (window.jQuery && node.classList.contains("js-bootstrap-single-select")) {
            // bootstrap-select açılışı DOM-u güzgüləyir — yenidən qurulmalıdır.
            try {
                window.jQuery(node).selectpicker("refresh");
            } catch (error) {
                /* selectpicker yüklənməyibsə native select onsuz da işləyir */
            }
        }
    }

    window.EMSLegacyReviewRender = {
        categories: categories,
        fillSelect: fillSelect,
        message: message,
        pager: pager,
        progress: progress,
        rows: rows,
        skeleton: skeleton
    };
})();

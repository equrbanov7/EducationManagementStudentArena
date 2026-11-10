/* =========================================================================
   «Keçilmiş dərslər» (kabinet bölməsi `lessons-log`) — 2026-11-11

   1) TƏNBƏL HESAB: ağır KPI-lar (iştirak / boş / gec) və «Cədvəldə var, qeydə
      alınmayıb» kartı keşdə yoxdursa bölmə skeletlə gəlir; burada
      `data-insights-url`-dan bir sorğu ilə doldurulur.
   2) «Daha çox göstər»: gün siyahısının növbəti səhifəsi (`data-rows-url` +
      `ll_offset`) mövcud siyahının sonuna əlavə olunur.
   3) «Cədvəl formasında bax»: müəllimin icmal cədvəli (qrup / patok × fənn ×
      növ, cəmlər) və «Ətraflı bax» (sətrin dərsləri) — JSON uclarından.

   AJAX-SAFE: fayl panelin içindən hər swap-da yenidən icra oluna bilər —
   qeydiyyat BİR dəfədir (`window.EMSLessonsLog`); kliklər `EMSDelegate` ilə,
   bölmə init-i `EMSReady` ilə (null-safe, idempotent). İstifadəçi mətni DOM-a
   yalnız `textContent` ilə yazılır.
   ========================================================================= */
(function (window, document) {
    "use strict";

    if (window.EMSLessonsLog) {
        return;
    }
    window.EMSLessonsLog = { version: 1 };

    function root() {
        return document.querySelector("[data-llog-root]");
    }

    function withParam(url, key, value) {
        var parsed = new URL(url, window.location.origin);
        parsed.searchParams.set(key, value);
        return parsed.pathname + parsed.search;
    }

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

    function clear(node) {
        while (node && node.firstChild) {
            node.removeChild(node.firstChild);
        }
    }

    function getJSON(url) {
        return window.EMSCore.fetchJSON(url);
    }

    /* ---- 1) Tənbəl KPI + «qeydə alınmayıb» --------------------------------- */

    var TONES = ["primary", "success", "warning", "danger", "skeleton"];

    function fillKpi(host, tile) {
        var card = host.querySelector('[data-ems-kpi-key="' + tile.key + '"]');
        if (!card) {
            return;
        }
        for (var i = 0; i < TONES.length; i += 1) {
            card.classList.remove("ems-kpi--" + TONES[i]);
        }
        if (tile.tone) {
            card.classList.add("ems-kpi--" + tile.tone);
        }
        var value = card.querySelector(".ems-kpi__value");
        if (value) {
            clear(value);
            value.appendChild(document.createTextNode(String(tile.value)));
            if (tile.unit) {
                value.appendChild(el("span", "ems-kpi__unit", tile.unit));
            }
        }
        var note = card.querySelector(".ems-kpi__note");
        if (note) {
            note.textContent = tile.note || "";
        }
    }

    function loadInsights(host) {
        if (host.dataset.insightsPending !== "1" || !host.dataset.insightsUrl) {
            return;
        }
        host.dataset.insightsPending = "loading";
        getJSON(host.dataset.insightsUrl)
            .then(function (payload) {
                if (!document.contains(host) || !payload || !payload.ok) {
                    return;
                }
                (payload.kpi || []).forEach(function (tile) {
                    fillKpi(host, tile);
                });
                var slot = host.querySelector("[data-llog-unrecorded]");
                if (slot && typeof payload.unrecorded_html === "string") {
                    // Server-render olunmuş, avtomatik escape edilmiş şablon fraqmenti (eyni mənbə).
                    slot.innerHTML = payload.unrecorded_html;
                }
                host.dataset.insightsPending = "0";
            })
            .catch(function () {
                if (!document.contains(host)) {
                    return;
                }
                host.dataset.insightsPending = "error";
                var pending = host.querySelector(".llog-unrec--pending .llog-unrec__note");
                if (pending) {
                    pending.textContent = host.dataset.labelError || "";
                }
                var cards = host.querySelectorAll(".ems-kpi--skeleton");
                for (var i = 0; i < cards.length; i += 1) {
                    cards[i].classList.remove("ems-kpi--skeleton");
                }
            });
    }

    window.EMSReady(function () {
        var host = root();
        if (host) {
            loadInsights(host);
        }
    });

    /* ---- 2) «Daha çox göstər» ---------------------------------------------- */

    /** Yeni səhifəni siyahıya əlavə edir; səhifə günü yarıda kəsibsə davam sətirləri mövcud gün kartına düşür. */
    function appendDays(days, html) {
        var holder = document.createElement("template");
        holder.innerHTML = html || ""; // server şablonu (avtomatik escape olunub, eyni mənbə)
        var incoming = holder.content.querySelectorAll(".llog-day");
        for (var i = 0; i < incoming.length; i += 1) {
            var card = incoming[i];
            var last = days.lastElementChild;
            var sameDay = last && last.getAttribute("data-llog-day") === card.getAttribute("data-llog-day");
            var target = sameDay ? last.querySelector("tbody") : null;
            var source = card.querySelector("tbody");
            if (target && source) {
                while (source.firstChild) {
                    target.appendChild(source.firstChild);
                }
            } else {
                days.appendChild(card);
            }
        }
    }

    window.EMSDelegate.on("click", "[data-llog-more-btn]", function (event, btn) {
        event.preventDefault();
        var host = btn.closest("[data-llog-root]");
        var days = host ? host.querySelector("[data-llog-days]") : null;
        var offset = btn.getAttribute("data-offset");
        if (!host || !days || !offset || btn.disabled) {
            return;
        }
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        getJSON(withParam(host.dataset.rowsUrl, "ll_offset", offset))
            .then(function (payload) {
                if (!document.contains(days) || !payload || !payload.ok) {
                    return;
                }
                appendDays(days, payload.html);
                var wrap = btn.closest("[data-llog-more]");
                if (payload.next_offset) {
                    btn.setAttribute("data-offset", String(payload.next_offset));
                } else if (wrap) {
                    wrap.hidden = true;
                }
            })
            .catch(function () {
                if (window.EMSToast && typeof window.EMSToast.show === "function") {
                    window.EMSToast.show(host.dataset.labelError || "", "danger");
                }
            })
            .then(function () {
                btn.disabled = false;
                btn.removeAttribute("aria-busy");
            });
    });

    /* ---- 3) «Cədvəl formasında bax» ---------------------------------------- */

    function tableOverlay() {
        return document.getElementById("llogTeacherTable");
    }

    function state(node, text) {
        if (!node) {
            return;
        }
        node.textContent = text || "";
        node.hidden = !text;
    }

    function totalItem(item) {
        var li = el("li", "llog-tt__item");
        li.appendChild(el("span", "llog-tt__item-label", item.label));
        li.appendChild(el("b", "llog-tt__item-value", item.text));
        return li;
    }

    function renderTable(overlay, payload) {
        var body = overlay.querySelector("[data-llog-tt-rows]");
        var foot = overlay.querySelector("[data-llog-tt-foot]");
        var kinds = overlay.querySelector("[data-llog-tt-kinds]");
        var sectors = overlay.querySelector("[data-llog-tt-sectors]");
        clear(body);
        clear(foot);
        clear(kinds);
        clear(sectors);
        (payload.rows || []).forEach(function (row) {
            var tr = el("tr");
            var group = el("th", "llog-tt__group");
            group.setAttribute("scope", "row");
            group.appendChild(el("span", "llog-tt__group-name", row.groups));
            if (row.is_joint) {
                group.appendChild(el("span", "ems-badge ems-badge--info llog-tt__joint", overlay.dataset.labelJoint));
            }
            tr.appendChild(group);
            var subject = el("td");
            subject.appendChild(el("span", "llog-subject", row.subject));
            if (row.sector_label) {
                subject.appendChild(el("span", "llog-submeta", row.sector_label));
            }
            tr.appendChild(subject);
            tr.appendChild(el("td", "llog-tt__kind", row.kind_label));
            tr.appendChild(el("td", "llog-tt__hours", row.text));
            var action = el("td", "llog-tt__action");
            var button = el("button", "ems-btn ems-btn--sm", overlay.dataset.labelDetail);
            button.type = "button";
            button.setAttribute("data-llog-row", row.key);
            button.setAttribute("data-llog-row-title", row.groups + " · " + row.subject + " · " + row.kind_label);
            button.setAttribute("data-llog-row-sub", row.text);
            action.appendChild(button);
            tr.appendChild(action);
            body.appendChild(tr);
        });
        var totals = payload.totals || {};
        var totalRow = el("tr", "llog-tt__total");
        var label = el("th", null, overlay.dataset.labelTotal);
        label.setAttribute("scope", "row");
        label.colSpan = 3;
        totalRow.appendChild(label);
        totalRow.appendChild(el("td", "llog-tt__hours", totals.text || ""));
        totalRow.appendChild(el("td"));
        foot.appendChild(totalRow);
        (totals.by_kind || []).forEach(function (item) {
            kinds.appendChild(totalItem(item));
        });
        (totals.by_sector || []).forEach(function (item) {
            sectors.appendChild(totalItem(item));
        });
    }

    function errorLabel(overlay, err) {
        if (err && err.status === 403) {
            return overlay.dataset.labelDenied || overlay.dataset.labelError;
        }
        return overlay.dataset.labelError;
    }

    window.EMSDelegate.on("click", "[data-llog-table-open]", function (event) {
        event.preventDefault();
        var overlay = tableOverlay();
        if (!overlay || !window.EMSOverlay) {
            return;
        }
        var stateNode = overlay.querySelector("[data-llog-tt-state]");
        var content = overlay.querySelector("[data-llog-tt-content]");
        var sub = overlay.querySelector("[data-llog-tt-sub]");
        content.hidden = true;
        sub.textContent = "";
        state(stateNode, overlay.dataset.labelLoading);
        window.EMSOverlay.open(overlay);
        getJSON(overlay.dataset.tableUrl)
            .then(function (payload) {
                if (!document.contains(overlay) || !payload || !payload.ok) {
                    return;
                }
                sub.textContent = payload.teacher.name + " · " + payload.period.text;
                if (!payload.rows || !payload.rows.length) {
                    state(stateNode, overlay.dataset.labelEmpty);
                    return;
                }
                renderTable(overlay, payload);
                state(stateNode, "");
                content.hidden = false;
            })
            .catch(function (err) {
                if (document.contains(overlay)) {
                    state(stateNode, errorLabel(overlay, err));
                }
            });
    });

    function renderLessons(overlay, tableNode, payload) {
        var body = overlay.querySelector("[data-llog-tl-rows]");
        clear(body);
        (payload.lessons || []).forEach(function (item, index) {
            var tr = el("tr");
            tr.appendChild(el("td", "ems-table__num", index + 1));
            var date = el("th", "llog-tt__date");
            date.setAttribute("scope", "row");
            date.appendChild(el("span", "llog-time__main", item.date_text));
            date.appendChild(el("span", "llog-submeta", item.weekday));
            tr.appendChild(date);
            tr.appendChild(el("td", "llog-time", item.time || "—"));
            tr.appendChild(el("td", "ems-table__num", item.hours));
            var topic = el("td");
            if (item.topic) {
                topic.textContent = item.topic;
            } else {
                topic.appendChild(el("span", "llog-notopic", tableNode.dataset.labelNotopic));
            }
            tr.appendChild(topic);
            tr.appendChild(el("td", "llog-tt__room", item.room || "—"));
            tr.appendChild(el("td", "ems-table__num", item.attendance || "—"));
            body.appendChild(tr);
        });
    }

    window.EMSDelegate.on("click", "[data-llog-row]", function (event, btn) {
        event.preventDefault();
        var tableNode = tableOverlay();
        var overlay = document.getElementById("llogTeacherLessons");
        if (!tableNode || !overlay || !window.EMSOverlay) {
            return;
        }
        var stateNode = overlay.querySelector("[data-llog-tl-state]");
        var content = overlay.querySelector("[data-llog-tl-content]");
        overlay.querySelector("[data-llog-tl-title]").textContent = btn.getAttribute("data-llog-row-title") || "";
        overlay.querySelector("[data-llog-tl-sub]").textContent = btn.getAttribute("data-llog-row-sub") || "";
        content.hidden = true;
        state(stateNode, tableNode.dataset.labelLoading);
        window.EMSOverlay.open(overlay);
        getJSON(withParam(tableNode.dataset.lessonsUrl, "row", btn.getAttribute("data-llog-row")))
            .then(function (payload) {
                if (!document.contains(overlay) || !payload || !payload.ok) {
                    return;
                }
                renderLessons(overlay, tableNode, payload);
                state(stateNode, "");
                content.hidden = false;
            })
            .catch(function (err) {
                if (document.contains(overlay)) {
                    state(stateNode, errorLabel(tableNode, err));
                }
            });
    });
})(window, document);

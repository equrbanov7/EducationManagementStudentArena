/* «Müəllimlər» / «Tələbələr» kataloqu — cədvəl, filtrlər, toplu seçim, əməllər.
 *
 * REDİZAYN (sahib, 2026-09-07):
 *   • sətirdə status NİŞANLARI (hesab + akademik), əlaqə linkləri, ikon-əməllər;
 *   • TOPLU SEÇİM: tələbə → «Qrupa köçür», müəllim → «Kafedraya təyin et»,
 *     hər ikisi → «Dayandır»; hədəflər ardıcıl göndərilir, nəticə toast ilə;
 *   • `window.prompt` / `alert` YOXDUR — səbəb dialoqu (ems_ui overlay) + toast;
 *   • tələbəyə «müəllim statusu ver» düyməsi HEÇ YERDƏ render olunmur.
 *
 * Müqavilə DƏYİŞMİR: list/options/action endpoint-ləri, `people:filters` və
 * `people:refresh` hadisələri, `EMSPeopleDetail.open(root, urls, id, {runAction})`
 * və tələbə idarəetmə çekməcəsinin `[data-psm-open]` düyməsi əvvəlki kimidir.
 *
 * AJAX-safe: `EMSReady` + idempotent boot (panel SPA swap-ından sonra təkrar
 * qoşulmur). Şəbəkə `EMSCore.fetchJSON` (CSRF). Inline stil/script yoxdur (CSP).
 *
 * BÖLGÜ (2026-09-21, modul ölçü büdcəsi ≤ 550 sətir) — 3 fayl, sıra ilə yüklənir:
 *   1) people_directory.js          — köməkçilər + hüceyrə render + sıralama başlıqları
 *                                     (bu fayl; `window.EMSPeopleDirectory` ad sahəsini yaradır)
 *   2) people_directory_actions.js  — şəxs kartı + əməl dialoqları (`runAction`, `openDetail`)
 *   3) people_directory_setup.js    — `setup(root)` + `boot` (EMSReady)
 * Paylaşılan vəziyyət YOXDUR — yalnız funksiyalar `window.EMSPeopleDirectory`
 * üzərindən ötürülür (əməllər `ctx` ilə çağırılır).
 */
(function () {
    "use strict";

    /* ---- kiçik köməkçilər ------------------------------------------------ */

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

    function icon(name) {
        var i = el("i", "fas " + name);
        i.setAttribute("aria-hidden", "true");
        return i;
    }

    function toast(message, level) {
        if (window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, level || "success");
        }
    }

    function fmt(template, values) {
        return String(template || "").replace(/%[abcd]/g, function (key) {
            var value = values[key.charAt(1)];
            return value === undefined || value === null ? "" : String(value);
        });
    }

    function messageOf(error, fallback) {
        var payload = error && error.payload;
        return (payload && payload.message) || fallback || "";
    }

    function readDetailI18n(root) {
        var block = document.getElementById("people-detail-i18n-" + (root.dataset.kind || ""));
        if (!block) {
            return {};
        }
        try {
            return JSON.parse(block.textContent || "{}");
        } catch (err) {
            return {};
        }
    }

    function badge(labels, tones, value, fallbackTone) {
        var text = (labels && labels[value]) || value || "—";
        var tone = (tones && tones[value]) || fallbackTone || "neutral";
        return el("span", "ems-badge ems-badge--" + tone, text);
    }

    /* ---- hüceyrələr ----------------------------------------------------- */

    function textCell(row, value, className) {
        var cell = el("td", className);
        cell.textContent = value || "—";
        if (!value) {
            cell.classList.add("is-muted");
        }
        row.appendChild(cell);
        return cell;
    }

    function personCell(row, person, ctx) {
        var cell = el("td", "people__cell-person");

        var avatar = el("span", "people__avatar");
        if (person.avatar_url) {
            var img = document.createElement("img");
            img.src = person.avatar_url;
            img.alt = "";
            img.loading = "lazy";
            avatar.appendChild(img);
        } else {
            // Şəkil FAYLLARI köhnə sistemdən köçmür — baş hərflər fallback-dir.
            avatar.classList.add("people__avatar--initials");
            avatar.textContent = person.initials || "?";
        }

        var name = el("button", "people__name");
        name.type = "button";
        name.dataset.peopleOpen = person.id;
        name.title = ctx.t("openCard");
        name.textContent = [person.full_name, person.patronymic].filter(Boolean).join(" ") || person.username;

        var sub = el("span", "people__username", "@" + person.username);
        var stack = el("span", "people__name-stack");
        stack.appendChild(name);
        stack.appendChild(sub);
        if (person.kind === "student" && person.admission_year) {
            stack.appendChild(el("span", "people__meta", ctx.t("admission") + " " + person.admission_year));
        }

        cell.appendChild(avatar);
        cell.appendChild(stack);
        row.appendChild(cell);
    }

    function contactCell(row, person) {
        var cell = el("td", "people__cell-contact");
        var any = false;
        if (person.email) {
            var mail = el("a", "people__contact", person.email);
            mail.href = "mailto:" + person.email;
            mail.prepend(icon("fa-envelope"));
            cell.appendChild(mail);
            any = true;
        }
        if (person.phone) {
            var tel = el("a", "people__contact", person.phone);
            tel.href = "tel:" + String(person.phone).replace(/\s+/g, "");
            tel.prepend(icon("fa-phone"));
            cell.appendChild(tel);
            any = true;
        }
        if (!any) {
            cell.textContent = "—";
            cell.classList.add("is-muted");
        }
        row.appendChild(cell);
    }

    function statusCell(row, person, ctx) {
        var cell = el("td", "people__cell-status");
        cell.appendChild(badge(ctx.i18n.status, ctx.i18n.status_tone, person.status, "neutral"));
        if (person.kind === "student" && person.academic_status) {
            cell.appendChild(badge(ctx.i18n.academic_status, ctx.i18n.academic_status_tone, person.academic_status, "info"));
        }
        row.appendChild(cell);
    }

    function actionButton(className, iconName, label, attrs, iconOnly) {
        var button = el("button", "people__action " + (className || ""));
        button.type = "button";
        button.appendChild(icon(iconName));
        if (iconOnly) {
            button.classList.add("people__action--icon");
            button.title = label;
            button.setAttribute("aria-label", label);
        } else {
            button.appendChild(el("span", "", label));
        }
        Object.keys(attrs || {}).forEach(function (key) {
            button.dataset[key] = attrs[key];
        });
        return button;
    }

    function actionsCell(row, person, ctx) {
        var cell = el("td", "people__cell-actions");
        var flags = ctx.flags;
        /* «İdarə et» — tələbə idarəetmə çekməcəsini açır (people_academic.js).
         * Burada YALNIZ düymə qoyulur: bu modul çekməcədən xəbərsizdir, o modul
         * isə düyməni sənəd səviyyəsində delegasiya ilə tutur. */
        if (flags.canManageAcademic && person.kind === "student") {
            var manage = actionButton("people__action--manage", "fa-id-card", ctx.t("manage"), { psmOpen: person.id });
            cell.appendChild(manage);
            if (person.record_id) {
                cell.appendChild(
                    actionButton("", "fa-people-arrows", ctx.t("changeGroup"), { peopleAction: "transfer_group", peopleTarget: person.id })
                );
            }
        }
        if (flags.canManageTeacherRole && person.kind === "teacher") {
            cell.appendChild(
                actionButton("", "fa-building-columns", ctx.t("assignUnit"), { peopleAction: "assign_unit", peopleTarget: person.id })
            );
            cell.appendChild(
                actionButton("people__action--danger", "fa-user-minus", ctx.t("revokeTeacher"), { peopleAction: "revoke_teacher", peopleTarget: person.id }, true)
            );
        }
        if (flags.canManageStatus && person.status === "active") {
            cell.appendChild(
                actionButton("people__action--danger", "fa-user-slash", ctx.t("block"), { peopleAction: "block", peopleTarget: person.id }, true)
            );
        }
        if (flags.canManageStatus && person.status === "blocked") {
            cell.appendChild(
                actionButton("people__action--ok", "fa-user-check", ctx.t("unblock"), { peopleAction: "unblock", peopleTarget: person.id }, true)
            );
        }
        row.appendChild(cell);
    }

    /* QA 2026-09-05 (UX-17): "Şəxs"/"Kafedra"/"Qrup" başlıqları `data-people-sort-*`
     * ilə mövcud "Sıralama" select-inin (name="sort") dəyərlərinə bağlanır. */
    function initSortHeaders(root, form) {
        var sortSelect = form && form.querySelector('select[name="sort"]');
        var headers = root.querySelectorAll("[data-people-sort-asc]");
        if (!sortSelect || !headers.length) {
            return;
        }

        function refresh() {
            Array.prototype.forEach.call(headers, function (th) {
                var asc = th.dataset.peopleSortAsc;
                var desc = th.dataset.peopleSortDesc;
                if (sortSelect.value === asc) {
                    th.setAttribute("aria-sort", "ascending");
                } else if (desc && sortSelect.value === desc) {
                    th.setAttribute("aria-sort", "descending");
                } else {
                    th.setAttribute("aria-sort", "none");
                }
            });
        }

        Array.prototype.forEach.call(headers, function (th) {
            var button = th.querySelector(".people__th-sort");
            if (!button) {
                return;
            }
            button.addEventListener("click", function () {
                var asc = th.dataset.peopleSortAsc;
                var desc = th.dataset.peopleSortDesc;
                var next = sortSelect.value === asc && desc ? desc : asc;
                sortSelect.value = next;
                sortSelect.dispatchEvent(new Event("change", { bubbles: true }));
                refresh();
            });
        });

        sortSelect.addEventListener("change", refresh);
        refresh();
    }

    /* ---- ad sahəsi (digər iki fayl buradan oxuyur) --------------------------- */

    var P = (window.EMSPeopleDirectory = window.EMSPeopleDirectory || {});
    P.el = el;
    P.icon = icon;
    P.toast = toast;
    P.fmt = fmt;
    P.messageOf = messageOf;
    P.readDetailI18n = readDetailI18n;
    P.badge = badge;
    P.textCell = textCell;
    P.personCell = personCell;
    P.contactCell = contactCell;
    P.statusCell = statusCell;
    P.actionButton = actionButton;
    P.actionsCell = actionsCell;
    P.initSortHeaders = initSortHeaders;
})();

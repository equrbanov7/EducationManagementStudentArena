/*
 * people_detail.js — «Müəllimlər» / «Tələbələr» kataloqunda ŞƏXS KARTI (drawer).
 *
 * QA 2026-09-05 P1-2: əvvəl `openDetail` yalnız ad + «Profil səhifəsi» linki
 * göstərirdi (backend `/accounts/people/person/<id>/` isə üzvlük, akademik, tədris,
 * əlaqə və əməl bayraqlarını qaytarır). Bu modul həmin JSON-u ems_ui drawer-inə
 * tam render edir. Konteyner markup-ı `_people_directory.html`-dədir (ems_ui
 * `_drawer.html` naxışı: fokus tələsi, Escape, overlay kliki — `ems_ui/overlay.js`).
 *
 * Mətnlər `#people-detail-i18n-<kind>` JSON blokundan gəlir (CSP: inline JS yox).
 * AJAX-safe: heç bir qlobal listener yığmır; hər açılışda gövdə yenidən qurulur.
 */
(function () {
    "use strict";

    if (window.EMSPeopleDetail) {
        return;
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined && text !== null && text !== "") {
            node.textContent = text;
        }
        return node;
    }

    function readI18n(root) {
        var kind = root.dataset.kind || "";
        var block = document.getElementById("people-detail-i18n-" + kind) || root.querySelector("[data-people-detail-i18n]");
        if (!block) {
            return {};
        }
        try {
            return JSON.parse(block.textContent || "{}");
        } catch (err) {
            return {};
        }
    }

    function t(i18n, key, fallback) {
        return (i18n && i18n[key]) || fallback || key;
    }

    function statusBadge(i18n, family, value) {
        var labels = (i18n && i18n[family]) || {};
        var tones = (i18n && i18n[family + "_tone"]) || {};
        var badge = el("span", "ems-badge ems-badge--" + (tones[value] || "neutral"), labels[value] || value || "—");
        return badge;
    }

    function fact(dl, label, valueNode) {
        var row = el("div", "people-detail__fact");
        row.appendChild(el("dt", "people-detail__label", label));
        var dd = el("dd", "people-detail__value");
        if (typeof valueNode === "string" || valueNode === null || valueNode === undefined) {
            dd.textContent = valueNode || "—";
        } else {
            dd.appendChild(valueNode);
        }
        row.appendChild(dd);
        dl.appendChild(row);
    }

    function formatDate(iso) {
        if (!iso) {
            return "";
        }
        var d = new Date(iso);
        if (isNaN(d.getTime())) {
            return iso;
        }
        return d.toLocaleDateString("az-AZ", { year: "numeric", month: "2-digit", day: "2-digit" });
    }

    function section(body, title) {
        var wrap = el("section", "people-detail__section");
        wrap.appendChild(el("h3", "people-detail__heading", title));
        body.appendChild(wrap);
        return wrap;
    }

    function renderIdentity(body, person, caps, i18n) {
        var head = el("div", "people-detail__identity");
        var avatar = el("span", "people__avatar people-detail__avatar", person.initials || "");
        if (person.avatar_url) {
            var img = el("img", "people-detail__avatar-img");
            img.src = person.avatar_url;
            img.alt = "";
            avatar.textContent = "";
            avatar.appendChild(img);
        }
        head.appendChild(avatar);
        var meta = el("div", "people-detail__meta");
        meta.appendChild(statusBadge(i18n, "status", person.status));
        var dl = el("dl", "people-detail__facts");
        fact(dl, t(i18n, "username", "İstifadəçi adı"), person.username);
        if (caps.can_view_contacts) {
            fact(dl, t(i18n, "email", "E-poçt"), person.email);
            fact(dl, t(i18n, "phone", "Telefon"), person.phone);
            fact(dl, t(i18n, "fin", "FİN"), person.fin);
        }
        if (caps.can_view_demographics) {
            var genderLabels = (i18n && i18n.gender_labels) || {};
            fact(dl, t(i18n, "gender", "Cins"), genderLabels[person.gender] || "");
            var age = person.age !== null && person.age !== undefined ? person.age + " " + t(i18n, "age_suffix", "yaş") : "";
            fact(dl, t(i18n, "age", "Yaş"), [formatDate(person.birth_date), age].filter(Boolean).join(" · "));
        }
        fact(dl, t(i18n, "last_login", "Son giriş"), formatDate(person.last_login) || t(i18n, "never", "Heç vaxt"));
        fact(dl, t(i18n, "date_joined", "Qeydiyyat"), formatDate(person.date_joined));
        meta.appendChild(dl);
        head.appendChild(meta);
        body.appendChild(head);
    }

    function renderList(body, title, rows, columns, emptyText) {
        var wrap = section(body, title);
        if (!rows || !rows.length) {
            wrap.appendChild(el("p", "people-detail__empty", emptyText));
            return;
        }
        var list = el("ul", "people-detail__list");
        rows.forEach(function (row) {
            var item = el("li", "people-detail__item");
            columns.forEach(function (col) {
                var value = col.render ? col.render(row) : row[col.key];
                if (value === undefined || value === null || value === "") {
                    return;
                }
                if (typeof value === "string") {
                    item.appendChild(el("span", "people-detail__cell" + (col.strong ? " is-strong" : ""), value));
                } else {
                    value.classList.add("people-detail__cell");
                    item.appendChild(value);
                }
            });
            list.appendChild(item);
        });
        wrap.appendChild(list);
    }

    function renderActions(body, person, caps, i18n, opts) {
        var actions = person.actions || {};
        var defs = [
            ["block", caps.can_manage_status && actions.block, "ems-btn ems-btn--danger"],
            ["unblock", caps.can_manage_status && actions.unblock, "ems-btn ems-btn--ghost"],
            // Tələbəyə «müəllim statusu ver» YOXDUR — server `grant_teacher`-i
            // tələbə üçün false qaytarır (sahib, 2026-09-07); burada da ikiqat qapı.
            ["grant_teacher", caps.can_manage_teacher_role && actions.grant_teacher && person.kind !== "student", "ems-btn ems-btn--ghost"],
            ["assign_unit", caps.can_manage_teacher_role && actions.assign_unit, "ems-btn ems-btn--ghost"],
            ["revoke_teacher", caps.can_manage_teacher_role && actions.revoke_teacher, "ems-btn ems-btn--danger"]
        ];
        var available = defs.filter(function (d) { return d[1]; });
        var bar = el("div", "people-detail__actions");
        if (person.page_url) {
            var page = el("a", "ems-btn ems-btn--primary", "");
            var pageIcon = el("i", "fas fa-arrow-up-right-from-square");
            pageIcon.setAttribute("aria-hidden", "true");
            page.appendChild(pageIcon);
            page.appendChild(document.createTextNode(" " + t(i18n, "page_link", "Ətraflı səhifə")));
            page.href = person.page_url;
            page.target = "_blank";
            page.rel = "noopener";
            bar.appendChild(page);
        }
        if (person.profile_url) {
            var link = el("a", "ems-btn", t(i18n, "profile_page", "Profil səhifəsi"));
            link.href = person.profile_url;
            bar.appendChild(link);
        }
        available.forEach(function (d) {
            var btn = el("button", d[2], t((i18n && i18n.actions) || {}, d[0], d[0]));
            btn.type = "button";
            btn.addEventListener("click", function () {
                if (typeof opts.runAction === "function") {
                    opts.runAction(d[0], person.id, function () {
                        opts.reopen(person.id);
                    });
                }
            });
            bar.appendChild(btn);
        });
        body.appendChild(bar);
    }

    /* Akademik / tədris xülasəsi — səhifə ilə eyni rəqəmlər (`people/page.py`). */
    function renderSummary(body, person, i18n) {
        var a = person.academic_summary;
        var tch = person.teaching_summary;
        if (a) {
            var wrapA = section(body, t(i18n, "summary_academic", "Akademik xülasə"));
            var dlA = el("dl", "people-detail__facts people-detail__facts--grid");
            fact(dlA, t(i18n, "program", "İxtisas"), [a.program_code, a.program].filter(Boolean).join(" · "));
            fact(dlA, t(i18n, "structure", "Fakültə / kafedra"), [a.faculty, a.kafedra].filter(Boolean).join(" · "));
            fact(dlA, t(i18n, "group", "Qrup"), [a.group, a.course_label].filter(Boolean).join(" · "));
            fact(dlA, t(i18n, "education_form", "Təhsil forması"), [a.education_form_label, a.funding_label].filter(Boolean).join(" · "));
            fact(dlA, t(i18n, "uomg", "ÜOMG"), a.uomg_available && a.uomg ? a.uomg : "—");
            fact(dlA, t(i18n, "credits", "Kredit"), a.credits_earned + " / " + a.credits_gpa);
            var failed = el("span", "people-detail__pill" + (a.failed ? " is-warn" : " is-ok"), String(a.failed));
            fact(dlA, t(i18n, "failed", "Kəsr"), failed);
            wrapA.appendChild(dlA);
        }
        if (tch) {
            var wrapT = section(body, t(i18n, "summary_teaching", "Tədris xülasəsi"));
            var dlT = el("dl", "people-detail__facts people-detail__facts--grid");
            fact(dlT, t(i18n, "structure", "Fakültə / kafedra"), [tch.faculty, tch.kafedra].filter(Boolean).join(" · "));
            if (tch.title) { fact(dlT, t(i18n, "position", "Vəzifə"), tch.title); }
            var service = tch.years !== null && tch.years !== undefined
                ? tch.years + " " + t(i18n, "years_suffix", "il") + (tch.since ? " · " + formatDate(tch.since) : "")
                : "";
            fact(dlT, t(i18n, "service_since", "İş stajı"), service);
            fact(dlT, t(i18n, "subjects_groups", "Fənn / qrup / açılış"), tch.subjects + " / " + tch.groups + " / " + tch.offerings);
            fact(dlT, t(i18n, "hours_current", "Saat (cari il)"), String(tch.hours_current) + (tch.current_year ? " · " + tch.current_year : ""));
            if (tch.heads && tch.heads.length) { fact(dlT, t(i18n, "heads", "Rəhbərlik"), tch.heads.join(", ")); }
            wrapT.appendChild(dlT);
        }
    }

    function render(body, payload, i18n, opts) {
        var person = payload.person || {};
        var caps = payload.capabilities || {};
        body.textContent = "";
        renderIdentity(body, person, caps, i18n);
        renderSummary(body, person, i18n);
        var roleLabels = (i18n && i18n.membership_role_labels) || {};
        renderList(
            body,
            t(i18n, "memberships", "Üzvlüklər"),
            person.memberships || [],
            [
                { render: function (m) { return roleLabels[m.role_name] || m.role_label || m.role_name || ""; }, strong: true },
                { render: function (m) { return m.title || ""; } },
                { render: function (m) { return m.scope_unit || ""; } },
                { render: function (m) { return m.organization || ""; } }
            ],
            t(i18n, "no_memberships", "Aktiv üzvlük yoxdur")
        );
        if (person.kind === "student" || (person.academic && person.academic.length)) {
            renderList(
                body,
                t(i18n, "academic", "Akademik qeydlər"),
                person.academic || [],
                [
                    { render: function (r) { return [r.program_code, r.program].filter(Boolean).join(" · "); }, strong: true },
                    { render: function (r) { return r.group ? t(i18n, "group", "Qrup") + ": " + r.group : ""; } },
                    { render: function (r) { return r.admission_year ? t(i18n, "admission_year", "Qəbul ili") + ": " + r.admission_year : ""; } },
                    { render: function (r) { return statusBadge(i18n, "academic_status", r.status); } }
                ],
                t(i18n, "no_academic", "Akademik qeyd yoxdur")
            );
        }
        if (person.is_teacher || (person.teaching && person.teaching.length)) {
            renderList(
                body,
                t(i18n, "teaching", "Tədris"),
                person.teaching || [],
                [
                    { render: function (r) { return [r.subject_code, r.subject].filter(Boolean).join(" · "); }, strong: true },
                    { render: function (r) { return r.group || ""; } },
                    { render: function (r) { return r.period || ""; } }
                ],
                t(i18n, "no_teaching", "Cari dövrdə açılış yoxdur")
            );
        }
        renderActions(body, person, caps, i18n, opts);
    }

    function open(root, urls, userId, opts) {
        opts = opts || {};
        var modal = root.querySelector("[data-people-detail-modal]");
        var body = root.querySelector("[data-people-detail-body]");
        var title = root.querySelector("[data-people-detail-title]");
        var sub = root.querySelector("[data-people-detail-sub]");
        if (!modal || !body) {
            return;
        }
        var i18n = readI18n(root);
        body.textContent = "";
        body.appendChild(el("p", "people-detail__loading", t(i18n, "loading", "Yüklənir…")));
        if (title) {
            title.textContent = t(i18n, root.dataset.kind === "teachers" ? "title_teacher" : "title_student", "Şəxs kartı");
        }
        if (sub) {
            sub.textContent = "";
        }
        if (window.EMSOverlay && typeof window.EMSOverlay.open === "function" && modal.id) {
            window.EMSOverlay.open(modal.id);
        } else {
            modal.hidden = false;
        }
        opts.reopen = function (id) { open(root, urls, id, opts); };
        window.EMSCore.fetchJSON(urls.detail.replace(/0\/$/, userId + "/"))
            .then(function (payload) {
                if (!payload || !payload.has_access) {
                    body.textContent = "";
                    body.appendChild(el("p", "people-detail__error", t(i18n, "error", "Məlumat yüklənmədi.")));
                    return;
                }
                var person = payload.person || {};
                if (title) {
                    title.textContent = [person.full_name, person.patronymic].filter(Boolean).join(" ") || title.textContent;
                }
                if (sub) {
                    sub.textContent = person.kind === "teacher" ? t(i18n, "title_teacher", "Müəllim") : t(i18n, "title_student", "Tələbə");
                }
                render(body, payload, i18n, opts);
                try { body.focus(); } catch (err) { /* ignore */ }
            })
            .catch(function () {
                body.textContent = "";
                body.appendChild(el("p", "people-detail__error", t(i18n, "error", "Məlumat yüklənmədi.")));
            });
    }

    window.EMSPeopleDetail = { open: open, render: render };
})();

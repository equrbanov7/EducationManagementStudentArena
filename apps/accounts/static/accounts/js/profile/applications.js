/* «Müraciətlərim» kabinet bölməsi — NÜVƏ (siyahı, KPI, tablar, filtrlər).
 *
 * AJAX-safe: panel `[data-profile-section-panel="applications"]` içindədir və
 * swap-dan sonra bu fayl YENİDƏN icra olunur, ona görə:
 *   • qeydiyyatlar (EMSDelegate / EMSReady) YALNIZ bir dəfə qoşulur,
 *   • `boot()` idempotentdir (yeni DOM düyünündə bayraq yoxdur → yenidən qurur).
 *
 * Mətnlər `#apx-i18n` JSON blokundan, URL-lər `data-*` atributlarından gəlir —
 * xarici .js Django template engine-dən keçmir (CLAUDE.md). Paylaşılan
 * köməkçilər (`NS.t`, `NS.api`, `NS.toast`, …) `applications_core.js`-dədir.
 *
 * Düymələr SERVER-in `allowed_actions` siyahısına görə göstərilir; rol/status
 * məntiqi burada TƏKRARLANMIR (backend müqaviləsi §8.2).
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});


    /* ── Vəziyyət ───────────────────────────────────────────────────────── */
    function defaultState(root) {
        return {
            tab: root.dataset.isHandler === "1" ? "inbox" : "mine",
            stat: "open",
            kind: "",
            q: "",
            page: 1,
            rows: [],
            pages: 1,
            total: 0,
            counts: {},
            selectedId: "",
            loading: false,
        };
    }

    /* ── Render: KPI kartları (dizayn §4.3) ─────────────────────────────── */
    function renderKpis(payload) {
        if (!NS.root) {
            return;
        }
        var sender = payload.sender || {};
        var handler = payload.handler || {};
        NS.root.querySelectorAll("[data-apx-kpi]").forEach(function (card) {
            var key = card.getAttribute("data-apx-kpi");
            var value = key in handler ? handler[key] : sender[key];
            if (value === undefined || value === null) {
                value = 0;
            }
            var valueNode = card.querySelector("[data-apx-kpi-value]");
            if (valueNode) {
                var suffix = card.getAttribute("data-suffix");
                valueNode.textContent = suffix ? String(value) + " " + suffix : String(value);
            }
            var noteNode = card.querySelector("[data-apx-kpi-note]");
            if (noteNode) {
                var on = Number(value) > 0;
                noteNode.textContent = card.getAttribute(on ? "data-note-on" : "data-note-off") || "";
                // Kart 2 primary, kart 3 danger tonuna keçir — YALNIZ sayğac > 0.
                card.classList.toggle(key === "overdue" ? "apx-kpi--danger" : "apx-kpi--primary", on);
            }
        });
    }

    /* ── Render: tab sayğacları (dizayn §4.4) ───────────────────────────── */
    function renderTabs() {
        if (!NS.root) {
            return;
        }
        NS.root.querySelectorAll("[data-apx-tab]").forEach(function (tab) {
            var key = tab.getAttribute("data-apx-tab");
            var active = key === NS.state.tab;
            tab.setAttribute("aria-current", active ? "true" : "false");
            var badge = tab.querySelector("[data-apx-tab-count]");
            if (!badge) {
                return;
            }
            var count = NS.state.counts[key];
            if (count) {
                badge.textContent = String(count);
                badge.hidden = false;
            } else {
                badge.textContent = "";
                badge.hidden = true;
            }
        });
        NS.root.querySelectorAll("[data-apx-stat]").forEach(function (chip) {
            chip.setAttribute("aria-pressed", chip.getAttribute("data-apx-stat") === NS.state.stat ? "true" : "false");
        });
    }

    /* ── Render: siyahı sətirləri (dizayn §4.6) ─────────────────────────── */
    function rowHtml(row) {
        var overdue = row.is_overdue ? true : false;
        var classes = ["apx-row"];
        if (row.status && row.status.key === "submitted") {
            classes.push("apx-row--new");
        }
        if (overdue) {
            classes.push("apx-row--overdue");
        }
        // Sağ etiket: emalçıya «sizdədir / <şöbə>-də» (server hesablayır),
        // göndərənə isə normanın özü — norma kataloqdakı növdən oxunur.
        var ownerLabel = row.owner_label;
        if (!NS.isHandler) {
            var norm = NS.kindSlaDays(row.kind.code);
            ownerLabel = !row.is_open ? NS.t("rowClosed") : norm ? NS.t("rowSla", { n: norm }) : row.owner_label;
        }
        var fromLine = NS.isHandler
            ? NS.esc(row.requester.name) + (row.requester_scope ? " · " + NS.esc(row.requester_scope) : "")
            : NS.esc(row.current_unit.name);
        return (
            '<button type="button" class="' +
            classes.join(" ") +
            '" data-apx-row="' +
            NS.esc(row.id) +
            '" aria-current="' +
            (row.id === NS.state.selectedId ? "true" : "false") +
            '">' +
            '<span class="apx-row__top">' +
            '<span class="apx-no">' + NS.esc(row.number) + "</span>" +
            '<span class="apx-badge" data-bg="' + NS.esc(row.kind.bg) + '" data-fg="' + NS.esc(row.kind.fg) + '">' +
            NS.esc(row.kind.label) + "</span>" +
            (overdue ? '<span class="apx-badge apx-badge--overdue">' + NS.esc(NS.t("rowOverdue")) + "</span>" : "") +
            '<span class="apx-pill" data-bg="' + NS.esc(row.status.bg) + '" data-fg="' + NS.esc(row.status.fg) + '">' +
            NS.esc(row.status.label) + "</span>" +
            "</span>" +
            '<span class="apx-row__subject">' + NS.esc(row.subject) + "</span>" +
            '<span class="apx-row__meta">' +
            "<span>" + fromLine + "</span>" +
            '<span class="apx-ctx__dot" aria-hidden="true">·</span>' +
            "<span>" + NS.esc(NS.date(row.submitted_at)) + "</span>" +
            (row.attachment_count
                ? '<span class="apx-row__files"><i class="fas fa-paperclip" aria-hidden="true"></i>' +
                  NS.esc(row.attachment_count) + "</span>"
                : "") +
            '<span class="apx-row__owner">' + NS.esc(ownerLabel) + "</span>" +
            "</span>" +
            "</button>"
        );
    }

    /* Payload-dakı hazır rənglər `style`-a YAZILIR (şablonda inline stil yoxdur). */
    NS.paintSwatches = function (scope) {
        scope.querySelectorAll("[data-bg]").forEach(function (node) {
            node.style.background = node.getAttribute("data-bg") || "";
            node.style.color = node.getAttribute("data-fg") || "";
        });
    };

    function emptyHtml() {
        var title = NS.t("emptyTitle");
        var note = NS.isHandler ? NS.t("emptyHandlerNote") : NS.t("emptySenderNote");
        if (NS.state.tab === "watching") {
            title = NS.t("emptyWatchingTitle");
            note = NS.t("emptyWatchingNote");
        } else if (NS.state.stat === "overdue") {
            title = NS.t("emptyOverdueTitle");
            note = NS.t("emptyHandlerNote");
        }
        return (
            '<div class="apx-empty"><i class="fas fa-comment-dots fa-2x" aria-hidden="true"></i>' +
            '<div class="apx-empty__title">' + NS.esc(title) + "</div>" +
            '<div class="apx-empty__note">' + NS.esc(note) + "</div></div>"
        );
    }

    function skeletonHtml() {
        return (
            '<div class="apx-skeleton" aria-hidden="true">' +
            '<div class="apx-skeleton__row"></div><div class="apx-skeleton__row"></div>' +
            '<div class="apx-skeleton__row"></div></div>'
        );
    }

    function renderList() {
        var host = NS.root && NS.root.querySelector("[data-apx-list]");
        if (!host) {
            return;
        }
        if (!NS.state.rows.length) {
            host.innerHTML = emptyHtml();
            return;
        }
        var html = NS.state.rows.map(rowHtml).join("");
        if (NS.state.page < NS.state.pages) {
            html +=
                '<button type="button" class="apx-btn apx-more" data-apx-more>' + NS.esc(NS.t("more")) + "</button>";
        }
        host.innerHTML = html;
        NS.paintSwatches(host);
    }

    NS.renderList = renderList;
    NS.renderTabs = renderTabs;

    /* Növün normativ iş günü (kataloqdan; emalçıda kataloq boş ola bilər). */
    NS.kindSlaDays = function (code) {
        var kinds = (NS.catalog && NS.catalog.kinds) || [];
        for (var i = 0; i < kinds.length; i++) {
            if (kinds[i].code === code) {
                return kinds[i].sla_days;
            }
        }
        return 0;
    };

    /* ── Yükləmə ────────────────────────────────────────────────────────── */
    function loadList(options) {
        options = options || {};
        var host = NS.root && NS.root.querySelector("[data-apx-list]");
        if (!host) {
            return Promise.resolve();
        }
        if (!options.append) {
            host.innerHTML = skeletonHtml();
        }
        NS.state.loading = true;
        return NS.api
            .list({
                tab: NS.state.tab,
                stat: NS.state.stat,
                kind: NS.state.kind,
                q: NS.state.q,
                page: NS.state.page,
            })
            .then(function (payload) {
                NS.state.rows = options.append ? NS.state.rows.concat(payload.results) : payload.results;
                NS.state.pages = payload.pages;
                NS.state.total = payload.total;
                NS.state.counts = payload.counts || {};
                renderTabs();
                renderList();
                if (!options.keepSelection) {
                    autoSelect();
                }
            })
            .catch(function () {
                host.innerHTML = emptyHtml();
                NS.toast(NS.t("loadError"), "error");
            })
            .then(function () {
                NS.state.loading = false;
            });
    }

    function autoSelect() {
        var stillThere = NS.state.rows.some(function (row) {
            return row.id === NS.state.selectedId;
        });
        if (stillThere) {
            return;
        }
        if (!NS.state.rows.length) {
            NS.state.selectedId = "";
            if (NS.detail && NS.detail.clear) {
                NS.detail.clear();
            }
            return;
        }
        // Dar ekranda detal slide-over-dur — istifadəçi seçməyibsə AÇILMIR.
        if (window.matchMedia && window.matchMedia("(max-width: 1100px)").matches) {
            NS.state.selectedId = "";
            if (NS.detail && NS.detail.clear) {
                NS.detail.clear();
            }
            return;
        }
        NS.openApplication(NS.state.rows[0].id);
    }

    NS.loadList = loadList;

    NS.loadKpis = function () {
        return NS.api
            .kpis()
            .then(function (payload) {
                NS.state.counts = payload.counts || NS.state.counts;
                renderKpis(payload);
                renderTabs();
            })
            .catch(function () {
                /* fail-soft: KPI olmasa da siyahı işləyir */
            });
    };

    NS.openApplication = function (id) {
        if (!id) {
            return Promise.resolve();
        }
        NS.state.selectedId = id;
        renderList();
        return NS.api
            .detail(id)
            .then(function (payload) {
                if (NS.detail && NS.detail.render) {
                    NS.detail.render(payload.application);
                }
                // Emalçının ilk baxışı statusu dəyişir → siyahı/KPI təzələnir.
                NS.refreshCounts();
            })
            .catch(function (error) {
                NS.toast(NS.errorList(error)[0], "error");
            });
    };

    /* Əməldən sonra: detal payload-u hazırdır, siyahı və KPI-lar təzələnir. */
    NS.applyDetail = function (application) {
        if (NS.detail && NS.detail.render) {
            NS.detail.render(application);
        }
        loadList({ keepSelection: true });
        NS.loadKpis();
    };

    NS.refreshCounts = function () {
        NS.loadKpis();
        if (window.EMSProfile && window.EMSProfile.ctx && typeof window.EMSProfile.ctx.refreshBadges === "function") {
            window.EMSProfile.ctx.refreshBadges();
        }
    };

    /* ── Növ süzgəci (listbox, §4.5) ────────────────────────────────────── */
    function renderKindOptions() {
        var panel = NS.root && NS.root.querySelector("[data-apx-kind-panel]");
        if (!panel || !NS.catalog) {
            return;
        }
        var options = [{ code: "", label: NS.t("kindAll") }].concat(NS.catalog.kinds || []);
        panel.innerHTML = options
            .map(function (kind) {
                return (
                    '<div class="apx-kind__option" role="option" tabindex="0" data-apx-kind-option="' +
                    NS.esc(kind.code) +
                    '" aria-selected="' +
                    (kind.code === NS.state.kind ? "true" : "false") +
                    '">' +
                    NS.esc(kind.label) +
                    "</div>"
                );
            })
            .join("");
    }

    NS.renderKindOptions = renderKindOptions;

    function setKind(code) {
        NS.state.kind = code;
        var label = NS.root.querySelector("[data-apx-kind-label]");
        var chosen = (NS.catalog && NS.catalog.kinds ? NS.catalog.kinds : []).filter(function (kind) {
            return kind.code === code;
        })[0];
        if (label) {
            label.textContent = chosen ? chosen.label : NS.t("kindAll");
        }
        renderKindOptions();
        closeKindPanel();
        NS.state.page = 1;
        loadList();
    }

    function closeKindPanel() {
        var panel = NS.root && NS.root.querySelector("[data-apx-kind-panel]");
        var toggle = NS.root && NS.root.querySelector("[data-apx-kind-toggle]");
        if (panel) {
            panel.hidden = true;
        }
        if (toggle) {
            toggle.setAttribute("aria-expanded", "false");
        }
    }

    NS.closeKindPanel = closeKindPanel;

    /* ── Boot (hər swap-da yenidən; idempotent) ─────────────────────────── */
    function boot() {
        var root = document.querySelector("[data-apx-root]");
        if (!root || root.dataset.apxBooted === "1") {
            return;
        }
        root.dataset.apxBooted = "1";
        NS.root = root;
        NS.urls = {
            list: root.dataset.urlList,
            catalog: root.dataset.urlCatalog,
            kpis: root.dataset.urlKpis,
            create: root.dataset.urlCreate,
            detail: root.dataset.urlDetail,
            action: root.dataset.urlAction,
            assignees: root.dataset.urlAssignees,
        };
        NS.rules = {
            subject: Number(root.dataset.minSubject) || 5,
            body: Number(root.dataset.minBody) || 20,
            note: Number(root.dataset.minNote) || 10,
        };
        NS.family = root.dataset.family || "";
        NS.canCreate = root.dataset.canCreate === "1";
        NS.isHandler = root.dataset.isHandler === "1";
        var i18nNode = document.getElementById("apx-i18n");
        NS.i18n = i18nNode ? JSON.parse(i18nNode.textContent) : {};
        NS.state = defaultState(root);
        NS.catalog = null;

        renderTabs();
        loadList();
        NS.loadKpis();
        NS.api
            .catalog()
            .then(function (payload) {
                NS.catalog = payload;
                renderKindOptions();
                // «Yeni müraciət» dərin keçidi (`?section=applications&new_kind=…`).
                // Kataloq gəldikdən SONRA açılır — növ siyahısı boş dialoqda
                // seçim göstərə bilməzdi. Naməlum kod səssizcə atılır.
                openPresetKind(root);
                // Sətirlərin sağ etiketi növün normasına söykənir → kataloq
                // gələndən sonra siyahı bir dəfə yenidən boyanır.
                renderList();
            })
            .catch(function () {
                /* fail-soft: kataloqsuz siyahı yenə işləyir */
            });

        var deepLink = root.dataset.openApplication;
        if (deepLink) {
            NS.openApplication(deepLink);
        }
    }

    /** `?new_kind=` → «Yeni müraciət» dialoqu, növ öncədən seçilmiş. */
    function openPresetKind(root) {
        var code = root && root.dataset ? (root.dataset.newKind || "").trim() : "";
        if (!code || root.dataset.canCreate !== "1" || !NS.openCreate) {
            return;
        }
        var kinds = (NS.catalog && NS.catalog.kinds) || [];
        var known = kinds.filter(function (kind) {
            return kind.code === code;
        }).length > 0;
        if (!known) {
            return;
        }
        root.dataset.newKind = "";
        NS.openCreate("create", null, code);
    }

    NS.boot = boot;

    /* ── Delegasiya — bir dəfə qoşulur (`EMSDelegate` təkrarı özü udur) ──── */
    function start() {
        if (NS.__wired) {
            boot();
            return;
        }
        NS.__wired = true;

        window.EMSDelegate.on("click", "[data-apx-tab]", function (event, node) {
            NS.state.tab = node.getAttribute("data-apx-tab");
            if (NS.state.tab === "archive") {
                NS.state.stat = "all";
            }
            NS.state.page = 1;
            renderTabs();
            NS.loadList();
        });

        window.EMSDelegate.on("click", "[data-apx-stat]", function (event, node) {
            NS.state.stat = node.getAttribute("data-apx-stat");
            NS.state.page = 1;
            renderTabs();
            NS.loadList();
        });

        window.EMSDelegate.on("click", "[data-apx-kpi]", function (event, node) {
            var tab = node.getAttribute("data-tab");
            var stat = node.getAttribute("data-stat");
            if (tab) {
                NS.state.tab = tab;
            }
            if (stat) {
                NS.state.stat = stat;
            }
            NS.state.page = 1;
            renderTabs();
            NS.loadList();
        });

        window.EMSDelegate.on("click", "[data-apx-reset]", function () {
            NS.state.q = "";
            NS.state.stat = "open";
            NS.state.page = 1;
            var input = NS.root && NS.root.querySelector("[data-apx-q]");
            if (input) {
                input.value = "";
            }
            setKind("");
        });

        window.EMSDelegate.on("input", "[data-apx-q]", function (event, node) {
            window.clearTimeout(NS.__searchTimer);
            NS.__searchTimer = window.setTimeout(function () {
                NS.state.q = node.value.trim();
                NS.state.page = 1;
                NS.loadList();
            }, 260);
        });

        window.EMSDelegate.on("click", "[data-apx-kind-toggle]", function (event, node) {
            var panel = NS.root.querySelector("[data-apx-kind-panel]");
            if (!panel) {
                return;
            }
            var open = panel.hidden;
            panel.hidden = !open;
            node.setAttribute("aria-expanded", open ? "true" : "false");
        });

        window.EMSDelegate.on("click", "[data-apx-kind-option]", function (event, node) {
            setKind(node.getAttribute("data-apx-kind-option"));
        });

        window.EMSDelegate.on("keydown", "[data-apx-kind-option]", function (event, node) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setKind(node.getAttribute("data-apx-kind-option"));
            }
        });

        window.EMSDelegate.on("click", "[data-apx-row]", function (event, node) {
            NS.openApplication(node.getAttribute("data-apx-row"));
        });

        window.EMSDelegate.on("click", "[data-apx-more]", function () {
            if (NS.state.loading || NS.state.page >= NS.state.pages) {
                return;
            }
            NS.state.page += 1;
            NS.loadList({ append: true, keepSelection: true });
        });

        window.EMSReady.once("apx-esc", function () {
            document.addEventListener("keydown", function (event) {
                if (event.key !== "Escape" || !NS.root) {
                    return;
                }
                if (NS.dialogs && NS.dialogs.closeTop && NS.dialogs.closeTop()) {
                    return;
                }
                NS.closeKindPanel();
            });
            document.addEventListener("click", function (event) {
                if (!NS.root) {
                    return;
                }
                if (!event.target.closest || !event.target.closest("[data-apx-kind]")) {
                    NS.closeKindPanel();
                }
            });
        });

        window.EMSReady(function () {
            boot();
        });
    }

    /* Panel script-ləri `<body>` içindədir və `ems_ajax_init.js`-dən ƏVVƏL
     * parse oluna bilər (AJAX swap-da isə dinamik script sırası zəmanətli
     * deyil), ona görə qeydiyyat primitivlər hazır olana qədər gözləyir.
     * `defer` ilk yüklənmədə bunu onsuz da tez edir — bu, ikinci qapıdır. */
    (function ready(attempt) {
        if (window.EMSDelegate && window.EMSReady && NS.api) {
            start();
            return;
        }
        if (attempt > 200) {
            return;
        }
        window.setTimeout(function () {
            ready(attempt + 1);
        }, 25);
    })(0);
})();

/**
 * «Köçürülmüş imtahan nəticələrinin dəqiqləşdirilməsi» bölməsi.
 *
 * AJAX-safe (docs/frontend/AJAX_SAFE_JS_PATTERN.md): `window.EMSReady` sarğısı,
 * null-safe element axtarışları, idempotent init (köke bayraq qoyulur).
 * Bölmə SPA panelidir — swap-dan sonra init təzə kök üzərində yenidən qalxır.
 *
 * Server müqaviləsi: `apps/accounts/views/legacy_review/{api,actions}.py`.
 * Bütün dinamik dəyərlər `data-*` atributlarından oxunur (CSP: inline JS yoxdur).
 *
 * DİZAYN QƏRARI — SÜZGƏC DƏYİŞƏNDƏ SƏHİFƏ 1-ə QAYIDIR, əməldən sonra İSƏ YOX.
 * Operator 7-ci səhifədə bir sətri təsdiqləyəndə siyahının başına atılsa, növbə
 * ilə işləmək mümkünsüz olardı; ona görə əməldən sonra CARİ səhifə yenilənir.
 *
 * Saf render funksiyaları `legacy_grade_review_render.js`-dədir.
 */
(function () {
    "use strict";

    function init() {
        var root = document.querySelector("[data-lgr-root]");
        var R = window.EMSLegacyReviewRender;
        if (!root || root._lgrReady || !R) {
            return;
        }
        root._lgrReady = true;

        var COLUMNS = 7;
        var i18nNode = root.querySelector("[data-lgr-i18n]");
        var D = i18nNode ? i18nNode.dataset : {};
        var labels = {
            empty: D.empty || "",
            error: D.error || "",
            verify: D.verify || "",
            correct: D.correct || "",
            dispute: D.dispute || "",
            prev: D.prev || "",
            next: D.next || "",
            page: D.page || "",
            noLive: D.noLive || "—",
            unlinked: D.unlinked || "",
            entry: D.entry || "",
            exam: D.exam || "",
            resit: D.resit || "",
            final: D.final || "",
            progress: D.progress || "",
            progressOf: D.progressOf || ""
        };

        var canReview = root.dataset.canReview === "1";
        var rowsBody = root.querySelector("[data-lgr-rows]");
        var pagerHost = root.querySelector("[data-lgr-pager]");
        var catsHost = root.querySelector("[data-lgr-cats]");
        var progressFill = root.querySelector("[data-lgr-progress-fill]");
        var progressText = root.querySelector("[data-lgr-progress-text]");
        var filters = root.querySelector("[data-lgr-filters]");

        var state = { page: 1, categories: [], pickers: {}, pendingFact: "", lastPage: null };

        function fetchJSON(url, options) {
            if (window.EMSCore && window.EMSCore.fetchJSON) {
                return window.EMSCore.fetchJSON(url, options);
            }
            return fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } }).then(function (response) {
                return response.json();
            });
        }

        function toast(text, kind) {
            if (window.EMSToast && window.EMSToast.show) {
                window.EMSToast.show(text, kind || "success");
            }
        }

        function pickerValue(name) {
            var picker = state.pickers[name];
            if (!picker || !picker.value) {
                return "";
            }
            var value = picker.value();
            return Array.isArray(value) ? value[0] || "" : value || "";
        }

        function selectValue(name) {
            var node = filters ? filters.querySelector('[name="' + name + '"]') : null;
            return node && node.value ? node.value : "";
        }

        // ── Süzgəclər ───────────────────────────────────────────────────────
        function queryParams() {
            var params = new URLSearchParams();
            ["faculty", "kafedra", "specialty", "group", "subject", "teacher"].forEach(function (name) {
                var value = pickerValue(name);
                if (value) {
                    params.set(name, value);
                }
            });
            ["year", "period", "severity", "status", "q"].forEach(function (name) {
                var value = selectValue(name);
                if (value) {
                    params.set(name, value);
                }
            });
            state.categories.forEach(function (code) {
                params.append("category", code);
            });
            params.set("page", String(state.page));
            params.set("page_size", root.dataset.pageSize || "25");
            return params;
        }

        // ── Cədvəl ──────────────────────────────────────────────────────────
        function load() {
            if (!rowsBody) {
                return;
            }
            R.skeleton(rowsBody, COLUMNS);
            fetchJSON(root.dataset.queueUrl + "?" + queryParams().toString())
                .then(function (data) {
                    if (!data || !data.has_access) {
                        R.message(rowsBody, COLUMNS, labels.empty);
                        R.pager(pagerHost, null, labels, function () {});
                        return;
                    }
                    state.lastPage = data;
                    R.progress(progressFill, progressText, data.progress, labels);
                    R.categories(catsHost, data.categories, state.categories, toggleCategory);
                    if (!data.results.length) {
                        R.message(rowsBody, COLUMNS, labels.empty);
                    } else {
                        R.rows(rowsBody, data.results, labels, canReview && data.can_review);
                    }
                    R.pager(pagerHost, data, labels, function (page) {
                        state.page = page;
                        load();
                    });
                })
                .catch(function () {
                    R.message(rowsBody, COLUMNS, labels.error);
                });
        }

        function reload() {
            state.page = 1;
            load();
        }

        function toggleCategory(code) {
            var index = state.categories.indexOf(code);
            if (index === -1) {
                state.categories.push(code);
            } else {
                state.categories.splice(index, 1);
            }
            reload();
        }

        // ── Açılışlar + seçicilər ───────────────────────────────────────────
        function loadOptions() {
            fetchJSON(root.dataset.optionsUrl)
                .then(function (data) {
                    if (!data || !data.has_access || !filters) {
                        return;
                    }
                    R.fillSelect(
                        filters.querySelector('[name="year"]'),
                        (data.years || []).map(function (year) {
                            return { id: year, label: year };
                        })
                    );
                    R.fillSelect(filters.querySelector('[name="period"]'), data.periods);
                    R.fillSelect(filters.querySelector('[name="severity"]'), data.severities);
                    R.fillSelect(filters.querySelector('[name="status"]'), data.statuses);
                })
                .catch(function () {
                    /* açılışlar gəlməsə süzgəclər boş qalır — cədvəl işləyir */
                });
        }

        function makePicker(name, url, dependParam, parentName) {
            var host = root.querySelector(".js-lgr-" + name);
            if (!host || !window.EMSSearchableSelect) {
                return null;
            }
            return window.EMSSearchableSelect.create(host, {
                url: url,
                multi: false,
                skeleton: true,
                dependParam: dependParam || undefined,
                getDependValue: parentName
                    ? function () {
                          return pickerValue(parentName);
                      }
                    : undefined,
                onChange: reload
            });
        }

        function buildPickers() {
            var D0 = root.dataset;
            state.pickers.faculty = makePicker("faculty", D0.facultyUrl);
            state.pickers.kafedra = makePicker("kafedra", D0.kafedraUrl, "faculty", "faculty");
            state.pickers.specialty = makePicker("specialty", D0.specialtyUrl, "kafedra", "kafedra");
            state.pickers.group = makePicker("group", D0.groupUrl, "specialty", "specialty");
            state.pickers.subject = makePicker("subject", D0.subjectUrl);
            state.pickers.teacher = makePicker("teacher", D0.teacherUrl);
            // Valideyn dəyişəndə uşaq seçimi ETİBARSIZ olur — sıfırlanmasa
            // «başqa fakültənin kafedrası» süzgəcdə ilişib qalar.
            [
                ["faculty", ["kafedra", "specialty", "group"]],
                ["kafedra", ["specialty", "group"]],
                ["specialty", ["group"]]
            ].forEach(function (pair) {
                var parent = state.pickers[pair[0]];
                if (!parent || !parent.on) {
                    return;
                }
                parent.on("change", function () {
                    pair[1].forEach(function (childName) {
                        var child = state.pickers[childName];
                        if (child && child.reset) {
                            child.reset();
                        }
                    });
                });
            });
        }

        // ── Əməllər ─────────────────────────────────────────────────────────
        var actions = window.EMSLegacyReviewActions;
        if (actions) {
            actions.bind(root, {
                labels: labels,
                i18n: D,
                fetchJSON: fetchJSON,
                toast: toast,
                onDone: load,
                getRow: function (factId) {
                    var page = state.lastPage;
                    if (!page || !page.results) {
                        return null;
                    }
                    for (var i = 0; i < page.results.length; i += 1) {
                        if (page.results[i].id === factId) {
                            return page.results[i];
                        }
                    }
                    return null;
                }
            });
        }

        // ── Hadisələr ───────────────────────────────────────────────────────
        if (filters) {
            var search = filters.querySelector('[name="q"]');
            if (search) {
                var timer = null;
                search.addEventListener("input", function () {
                    window.clearTimeout(timer);
                    timer = window.setTimeout(reload, 300);
                });
            }
            ["year", "period", "severity", "status"].forEach(function (name) {
                var node = filters.querySelector('[name="' + name + '"]');
                if (node) {
                    node.addEventListener("change", reload);
                }
            });
        }
        var resetButton = root.querySelector("[data-lgr-reset]");
        if (resetButton) {
            resetButton.addEventListener("click", function () {
                state.categories = [];
                Object.keys(state.pickers).forEach(function (name) {
                    var picker = state.pickers[name];
                    if (picker && picker.reset) {
                        picker.reset();
                    }
                });
                if (filters) {
                    ["year", "period", "severity", "status"].forEach(function (name) {
                        var node = filters.querySelector('[name="' + name + '"]');
                        if (node) {
                            node.value = "";
                        }
                    });
                    var searchNode = filters.querySelector('[name="q"]');
                    if (searchNode) {
                        searchNode.value = "";
                    }
                }
                reload();
            });
        }

        buildPickers();
        loadOptions();
        load();
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else {
        document.addEventListener("DOMContentLoaded", init);
    }
})();

/* Fənn (subject) + Müəllim (jurnal) — tək seçimli axtarışlı siyahılar (qrup/tələbə siyahısı ilə eyni üslub).

   Siyahı açılanda ilk 10 sətir yüklənir, aşağı sürüşdürdükcə növbəti 10 gəlir,
   yaxud yazıb axtarmaq olar. Bir sətrə klik onu seçir (radio semantikası) və
   gizli `<select>`-ə yazır.

   2026-10-24 (sahib, «JS Loop» halı): müəllim → fənn ASILI seçimi. «Müəllim (jurnal)» seçiləndə fənn
   siyahısı `data-teacher-url` (exams:journal_teacher_subjects) endpoint-indən gəlir — yalnız həmin
   müəllimin cari dövrdə tədris etdiyi fənlər (seçilmiş reyestr qrupları `units` kimi ötürülür). Müəllim
   boşdursa adi `data-search-url` (exams:subject_search) — bütün fənlər. Seçili fənn yeni müəllimin
   fənni deyilsə seçim təmizlənir. Müəllim sahəsi yalnız Final / Midterm kateqoriyasında görünür.
   Server avtoritetdir (ExamForm yoxlayır); bu, yalnız rahatlıq süzgəcidir. */
(function (ns, document) {
    "use strict";

    var PAGE_SIZE = 10;
    var SECURE_CATEGORIES = { final: true, midterm: true };

    function cssEscape(value) {
        return String(value).replace(/"/g, '\\"');
    }

    function busy(input, on) {
        if (window.EMSSearchInput) {
            window.EMSSearchInput.busy(input, on);
        }
    }

    /* Ümumi tək seçimli axtarışlı siyahı. `opts.buildUrl(query, offset)` URL qaytarır (boşdursa yükləmə yoxdur),
       `opts.emptyText(query)` boş siyahı mətni, `opts.onChange(id, text)` seçim dəyişəndə. */
    function createSingleSelect(control, opts) {
        var searchInput = control.querySelector(".create-exam-search-input");
        var results = control.querySelector(opts.resultsSelector);
        var selectedText = control.querySelector(opts.selectedTextSelector);
        var nativeSelect = control.querySelector(opts.nativeSelector);
        if (!searchInput || !results || !nativeSelect) {
            return null;
        }

        var offset = 0;
        var hasMore = true;
        var loading = false;
        var query = "";
        var requestSeq = 0;

        // İlkin seçim (redaktə rejimi / server 400 cavabı).
        var preselected = nativeSelect.querySelector("option[value]");
        var selectedId = preselected ? String(preselected.value) : "";
        if (preselected && selectedText) {
            selectedText.textContent = preselected.textContent || "—";
        }

        function markActive() {
            results.querySelectorAll(".create-exam-list-item.is-active").forEach(function (r) {
                r.classList.remove("is-active");
            });
            if (selectedId) {
                var row = results.querySelector('[data-value="' + cssEscape(selectedId) + '"]');
                if (row) {
                    row.classList.add("is-active");
                }
            }
        }

        function setSelected(id, text, silent) {
            selectedId = id ? String(id) : "";
            nativeSelect.innerHTML = "";
            if (selectedId) {
                var opt = document.createElement("option");
                opt.value = selectedId;
                opt.textContent = text;
                opt.selected = true;
                nativeSelect.appendChild(opt);
            }
            if (selectedText) {
                selectedText.textContent = selectedId ? text : "—";
            }
            markActive();
            if (!silent) {
                nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
                if (opts.onChange) {
                    opts.onChange(selectedId, text);
                }
            }
        }

        function makeRow(item) {
            var id = String(item.id);
            var row = document.createElement("div");
            row.className = "create-exam-list-item" + (id === selectedId ? " is-active" : "");
            row.setAttribute("data-value", id);
            row.setAttribute("role", "option");
            var check = document.createElement("span");
            check.className = "create-exam-subject-check";
            check.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i>';
            var label = document.createElement("label");
            label.className = "create-exam-item-label";
            label.textContent = item.text;
            row.appendChild(check);
            row.appendChild(label);
            row.addEventListener("click", function () {
                setSelected(id, item.text);
            });
            return row;
        }

        function showEmpty() {
            if (!results.children.length) {
                var empty = document.createElement("div");
                empty.className = "create-exam-search-empty";
                empty.textContent = opts.emptyText(query);
                results.appendChild(empty);
            }
        }

        function loadPage(reset, quiet) {
            // 2026-10-14: yeni axtarış (reset) gedən sorğunu GÖZLƏMİR — əvvəl `loading`
            // olanda axtarış sakitcə atılırdı və nəticə köhnə mətnə aid qalırdı.
            if (loading && !reset) {
                return;
            }
            // Yazdıqca axtarış: köhnə sətirlər cavab gələnə qədər qalır (sakitcə solur).
            quiet = Boolean(quiet && reset && results.children.length);
            if (reset) {
                offset = 0;
                hasMore = true;
                if (!quiet) {
                    results.innerHTML = "";
                }
            }
            results.classList.toggle("ems-search-pending", quiet);
            busy(searchInput, quiet);
            var url = opts.buildUrl(query, offset);
            if (!hasMore || !url) {
                return;
            }
            loading = true;
            var seq = ++requestSeq;
            fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (r) { return r.ok ? r.json() : { results: [], has_more: false }; })
                .then(function (data) {
                    if (seq !== requestSeq) {
                        return;
                    }
                    if (quiet) {
                        results.innerHTML = "";
                        results.classList.remove("ems-search-pending");
                        busy(searchInput, false);
                    }
                    var items = (data && data.results) || [];
                    items.forEach(function (item) {
                        if (results.querySelector('[data-value="' + cssEscape(item.id) + '"]')) {
                            return;
                        }
                        results.appendChild(makeRow(item));
                    });
                    offset += items.length;
                    hasMore = Boolean(data && data.has_more);
                    showEmpty();
                    loading = false;
                    if (opts.onPage) {
                        opts.onPage(data || {});
                    }
                })
                .catch(function () {
                    if (seq === requestSeq) {
                        loading = false;
                        results.classList.remove("ems-search-pending");
                        if (quiet) {
                            busy(searchInput, false);
                        }
                    }
                });
        }

        // 2026-10-14: vahid EMSSearchInput (1500 ms, ≥ 2 simvol, Enter dərhal — forma
        // göndərilmir, IME); `query` yalnız sorğu gedəndə yenilənir.
        if (window.EMSSearchInput) {
            window.EMSSearchInput.bind(searchInput, {
                onSearch: function (value) {
                    query = value;
                    loadPage(true, true);
                }
            });
        }

        results.addEventListener("scroll", function () {
            if (loading || !hasMore) {
                return;
            }
            if (results.scrollTop + results.clientHeight >= results.scrollHeight - 40) {
                loadPage(false);
            }
        });

        return {
            reload: function () { loadPage(true); },
            clear: function () { setSelected("", "", false); },
            selectedId: function () { return selectedId; }
        };
    }

    function joinUrl(base, params) {
        var parts = [];
        Object.keys(params).forEach(function (key) {
            if (params[key] !== "" && params[key] !== null && params[key] !== undefined) {
                parts.push(key + "=" + encodeURIComponent(params[key]));
            }
        });
        return base + (base.indexOf("?") === -1 ? "?" : "&") + parts.join("&");
    }

    function selectedUnitIds(form) {
        var ids = [];
        form.querySelectorAll('select[name="allowed_units"] option:checked').forEach(function (opt) {
            if (opt.value) {
                ids.push(opt.value);
            }
        });
        return ids.join(",");
    }

    function initSubjectSelect(form) {
        if (!form) {
            return;
        }
        var control = form.querySelector("[data-exam-subject-control]");
        if (!control || control.hasAttribute("data-exam-subject-ready")) {
            return;  // idempotent: AJAX ilə yenidən bağlananda ikinci dəfə qoşulmur
        }
        control.setAttribute("data-exam-subject-ready", "1");

        var searchUrl = control.getAttribute("data-search-url") || "";
        var teacherUrl = control.getAttribute("data-teacher-url") || "";
        var teacherEmptyText = control.getAttribute("data-teacher-empty-text") || gettext("Fənn yoxdur");
        var teacherControl = form.querySelector("[data-exam-teacher-control]");
        var teacherNative = teacherControl ? teacherControl.querySelector("[data-exam-teacher-native]") : null;
        var teacherClear = teacherControl ? teacherControl.querySelector("[data-exam-teacher-clear]") : null;
        var subject = null;
        var verifySelection = false;

        function teacherId() {
            var opt = teacherNative ? teacherNative.querySelector("option[value]") : null;
            return opt ? String(opt.value) : "";
        }

        subject = createSingleSelect(control, {
            resultsSelector: "[data-exam-subject-results]",
            selectedTextSelector: "[data-exam-subject-selected-text]",
            nativeSelector: "[data-exam-subject-native]",
            emptyText: function (q) {
                if (q) {
                    return gettext("Nəticə tapılmadı");
                }
                return teacherId() ? teacherEmptyText : gettext("Fənn yoxdur");
            },
            buildUrl: function (q, offset) {
                var base = teacherId() && teacherUrl ? teacherUrl : searchUrl;
                if (!base) {
                    return "";
                }
                var params = { q: q, offset: offset, limit: PAGE_SIZE };
                if (teacherId() && teacherUrl) {
                    params.teacher = teacherId();
                    params.units = selectedUnitIds(form);
                    params.selected = subject ? subject.selectedId() : "";
                }
                return joinUrl(base, params);
            },
            onPage: function (data) {
                // Müəllim dəyişəndən sonra İLK səhifə: seçili fənn onun fənni deyilsə təmizlə.
                if (verifySelection && subject && subject.selectedId() && !data.selected_ok) {
                    subject.clear();
                }
                verifySelection = false;
            }
        });
        if (!subject) {
            return;
        }

        if (teacherControl && teacherNative) {
            var teacher = createSingleSelect(teacherControl, {
                resultsSelector: "[data-exam-teacher-results]",
                selectedTextSelector: "[data-exam-teacher-selected-text]",
                nativeSelector: "[data-exam-teacher-native]",
                emptyText: function () {
                    return teacherControl.getAttribute("data-empty-text") || gettext("Nəticə tapılmadı");
                },
                buildUrl: function (q, offset) {
                    var base = teacherControl.getAttribute("data-search-url") || "";
                    return base ? joinUrl(base, { q: q, offset: offset, limit: PAGE_SIZE }) : "";
                },
                onChange: function (id) {
                    if (teacherClear) {
                        teacherClear.hidden = !id;
                    }
                    verifySelection = Boolean(id);
                    subject.reload();
                }
            });
            if (teacher && teacherClear) {
                teacherClear.addEventListener("click", function () {
                    teacher.clear();
                });
            }
            if (teacher) {
                teacher.reload();
                bindTeacherVisibility(form, teacher);
            }
        }

        bindMidtermJournalNote(form);
        bindSubjectChangeGuard(form, control);
        subject.reload(); // ilk 10 fənni dərhal yüklə
    }

    /* 2026-10-25 (sahib): nəticəli midtermdə fənn dəyişəndə təsdiq + səbəb bloku görünür (köhnə → yeni fənn,
       tələbə sayı serverdən). Server avtoritetdir — blok gizli olsa da təsdiqsiz dəyişiklik 409 ilə qayıdır;
       server tələb edibsə (`data-server-required`) blok açıq qalır. */
    function bindSubjectChangeGuard(form, control) {
        var guard = form.querySelector("[data-ew-subject-guard]");
        var nativeSelect = control.querySelector("[data-exam-subject-native]");
        if (!guard || !nativeSelect) {
            return;
        }
        var original = guard.getAttribute("data-original-subject") || "";
        var serverRequired = guard.getAttribute("data-server-required") === "1";
        var newLabel = guard.querySelector("[data-ew-subject-guard-new]");
        function sync() {
            var opt = nativeSelect.querySelector("option[value]");
            var current = opt ? String(opt.value) : "";
            if (newLabel && (current || !serverRequired)) {
                newLabel.textContent = opt ? (opt.textContent || "—") : "—";
            }
            guard.hidden = !(serverRequired || current !== original);
        }
        nativeSelect.addEventListener("change", sync);
        sync();
    }

    /* 2026-10-24 (sahib): «nəticə jurnala avtomatik yazılacaq» qeydi yalnız Midterm-də görünür; mətn formatdan
       asılıdır — test: bitən kimi, yazılı / praktiki: yoxlanandan sonra (`data-ew-journal-note-format`). */
    function bindMidtermJournalNote(form) {
        var note = form.querySelector("[data-ew-midterm-journal-note]");
        var category = form.querySelector('[name="exam_type_extended"]');
        if (!note || !category) {
            return;
        }
        function examFormat() {
            var radio = form.querySelector(".js-create-exam-type-option:checked");
            var native = form.querySelector('select[name="exam_type"]');
            return (radio && radio.value) || (native && native.value) || "test";
        }
        function sync() {
            note.hidden = category.value !== "midterm";
            var key = examFormat() === "test" ? "test" : "graded";
            note.querySelectorAll("[data-ew-journal-note-format]").forEach(function (text) {
                text.hidden = text.getAttribute("data-ew-journal-note-format") !== key;
            });
        }
        form.addEventListener("change", function (event) {
            var target = event.target;
            if (target === category || (target && target.matches &&
                    target.matches('.js-create-exam-type-option, select[name="exam_type"]'))) {
                sync();
            }
        });
        sync();
    }

    /* Müəllim sahəsi yalnız Final / Midterm-də görünür; başqa kateqoriyaya keçəndə müəllim təmizlənir
       (fənn siyahısı yenidən bütün fənlərdir). */
    function bindTeacherVisibility(form, teacher) {
        var group = form.querySelector("[data-ew-journal-teacher-group]");
        var category = form.querySelector('[name="exam_type_extended"]');
        if (!group || !category) {
            return;
        }
        function sync() {
            var secure = Boolean(SECURE_CATEGORIES[category.value]);
            group.hidden = !secure;
            if (!secure && teacher.selectedId()) {
                teacher.clear();
            }
        }
        category.addEventListener("change", sync);
        sync();
    }

    ns.subjectSelect = { init: initSubjectSelect };
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, document);

/* Fənn (subject) — tək seçimli axtarışlı siyahı (qrup/tələbə siyahısı ilə eyni üslub).

   Siyahı açılanda ilk 10 fənn yüklənir, aşağı sürüşdürdükcə növbəti 10 gəlir,
   yaxud yazıb axtarmaq olar. Bir sətrə klik onu seçir (radio semantikası) və
   gizli `<select name="subject">`-ə yazır. Data `data-search-url`
   (exams:subject_search) endpoint-indən gəlir. */
(function (ns, document) {
    "use strict";

    var DEBOUNCE_MS = 300;
    var PAGE_SIZE = 10;

    function initSubjectSelect(form) {
        if (!form) {
            return;
        }
        var control = form.querySelector("[data-exam-subject-control]");
        if (!control) {
            return;
        }

        var searchUrl = control.getAttribute("data-search-url") || "";
        var searchInput = control.querySelector(".create-exam-search-input");
        var results = control.querySelector("[data-exam-subject-results]");
        var selectedText = control.querySelector("[data-exam-subject-selected-text]");
        var nativeSelect = control.querySelector("[data-exam-subject-native]");
        if (!searchInput || !results || !nativeSelect) {
            return;
        }

        var offset = 0;
        var hasMore = true;
        var loading = false;
        var query = "";
        var requestSeq = 0;
        var debounceTimer = null;

        // İlkin seçim (redaktə rejimi).
        var preselected = nativeSelect.querySelector("option[value]");
        var selectedId = preselected ? String(preselected.value) : "";
        if (preselected && selectedText) {
            selectedText.textContent = preselected.textContent || "—";
        }

        function setSelected(id, text) {
            selectedId = String(id);
            nativeSelect.innerHTML = "";
            var opt = document.createElement("option");
            opt.value = id;
            opt.textContent = text;
            opt.selected = true;
            nativeSelect.appendChild(opt);
            nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
            if (selectedText) {
                selectedText.textContent = text;
            }
            // Yeni seçimi işıqlandır, köhnəni söndür.
            results.querySelectorAll(".create-exam-list-item.is-active").forEach(function (r) {
                r.classList.remove("is-active");
            });
            var row = results.querySelector('[data-value="' + String(id).replace(/"/g, '\\"') + '"]');
            if (row) {
                row.classList.add("is-active");
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
                empty.textContent = query ? gettext("Nəticə tapılmadı") : gettext("Fənn yoxdur");
                results.appendChild(empty);
            }
        }

        function loadPage(reset) {
            if (!searchUrl || loading) {
                return;
            }
            if (reset) {
                offset = 0;
                hasMore = true;
                results.innerHTML = "";
            }
            if (!hasMore) {
                return;
            }
            loading = true;
            var seq = ++requestSeq;
            var url = searchUrl +
                (searchUrl.indexOf("?") === -1 ? "?" : "&") +
                "q=" + encodeURIComponent(query) +
                "&offset=" + offset + "&limit=" + PAGE_SIZE;
            fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (r) { return r.ok ? r.json() : { results: [], has_more: false }; })
                .then(function (data) {
                    if (seq !== requestSeq) {
                        return;
                    }
                    var items = (data && data.results) || [];
                    items.forEach(function (item) {
                        if (results.querySelector('[data-value="' + String(item.id).replace(/"/g, '\\"') + '"]')) {
                            return;
                        }
                        results.appendChild(makeRow(item));
                    });
                    offset += items.length;
                    hasMore = Boolean(data && data.has_more);
                    showEmpty();
                    loading = false;
                })
                .catch(function () {
                    if (seq === requestSeq) {
                        loading = false;
                    }
                });
        }

        searchInput.addEventListener("input", function () {
            if (debounceTimer) {
                clearTimeout(debounceTimer);
            }
            query = searchInput.value.trim();
            debounceTimer = setTimeout(function () {
                loadPage(true);
            }, DEBOUNCE_MS);
        });

        results.addEventListener("scroll", function () {
            if (loading || !hasMore) {
                return;
            }
            if (results.scrollTop + results.clientHeight >= results.scrollHeight - 40) {
                loadPage(false);
            }
        });

        loadPage(true); // ilk 10 fənni dərhal yüklə
    }

    ns.subjectSelect = { init: initSubjectSelect };
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, document);

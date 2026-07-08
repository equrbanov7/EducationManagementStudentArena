/* Lazy searchable group/user selectors — default 10 + infinite scroll.

   Server yalnız SEÇİLİ variantları render edir; qalanlar `data-search-url`
   (exams:group_search / exams:user_search) üzərindən səhifə-səhifə (10-luq)
   gətirilir: siyahı açılanda ilk 10 yüklənir, aşağı sürüşdürdükcə növbəti 10,
   yaxud yazıb axtarmaq olar. Qrup seçmək onsuz da bütün üzvlərinə giriş verir,
   ona görə köhnə qrup→tələbə avtomatik sinxronizasiyası yoxdur. */
(function (ns, document) {
    "use strict";

    var DEBOUNCE_MS = 300;
    var PAGE_SIZE = 10;

    function initSearchableSelect(form, config) {
        if (!form || !config) {
            return null;
        }

        var hiddenSelect = form.querySelector('select[name="' + config.selectName + '"]');
        var listContainer = form.querySelector(config.listSelector);
        var searchInput = form.querySelector(config.searchSelector);
        var counter = form.querySelector(config.counterSelector);
        if (!hiddenSelect || !listContainer) {
            return null;
        }

        var container = hiddenSelect.closest("[data-search-url]") ||
            (searchInput ? searchInput.closest("[data-search-url]") : null);
        var searchUrl = container ? container.getAttribute("data-search-url") : "";

        // Seçili variantlar (value -> text), server-side render-dən başlayır.
        var selected = Object.create(null);
        Array.prototype.slice.call(hiddenSelect.selectedOptions || []).forEach(function (o) {
            selected[String(o.value)] = o.textContent || String(o.value);
        });

        // İki alt-sahə: yuxarıda seçililər (sabit), aşağıda axtarış nəticələri.
        listContainer.innerHTML = "";
        var selectedWrap = document.createElement("div");
        selectedWrap.className = "create-exam-selected-rows";
        var resultsWrap = document.createElement("div");
        resultsWrap.className = "create-exam-result-rows";
        listContainer.appendChild(selectedWrap);
        listContainer.appendChild(resultsWrap);

        var offset = 0;
        var hasMore = true;
        var loading = false;
        var query = "";
        var requestSeq = 0;
        var debounceTimer = null;
        // Əlavə query fraqmenti (məs. sağ tələbə siyahısı üçün seçilmiş qrup
        // ID-ləri) və seçim dəyişəndə çağırılan callback (qrup→tələbə sinxronu).
        var extraParamsProvider = null;
        var selectionChangeHandler = null;

        function updateCounter() {
            if (counter) {
                counter.textContent = String(Object.keys(selected).length);
            }
        }

        function syncHiddenOption(value, text, isSelected) {
            var esc = String(value).replace(/"/g, '\\"');
            var option = hiddenSelect.querySelector('option[value="' + esc + '"]');
            if (isSelected) {
                if (!option) {
                    option = document.createElement("option");
                    option.value = value;
                    option.textContent = text;
                    hiddenSelect.appendChild(option);
                }
                option.selected = true;
            } else if (option) {
                option.parentNode.removeChild(option);
            }
        }

        function makeRow(value, text, checked, groupMember) {
            var v = String(value);
            var row = document.createElement("div");
            row.className = "create-exam-list-item";
            row.setAttribute("data-value", v);
            var checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "create-exam-item-checkbox";
            var label = document.createElement("label");
            label.className = "create-exam-item-label";
            label.textContent = text;
            row.appendChild(checkbox);
            row.appendChild(label);

            if (groupMember) {
                // Seçilmiş qrupun üzvü: qrupla təyin olunub — işarəli və
                // qeyri-aktiv göstərilir (ayrıca allowed_users-ə əlavə olunmur,
                // çünki qrup onsuz da bütün üzvlərini əhatə edir).
                checkbox.checked = true;
                checkbox.disabled = true;
                row.classList.add("is-group-member");
                row.setAttribute("title", gettext("Seçilmiş qrupla daxildir"));
                return row;
            }

            checkbox.checked = checked;
            function toggle(next) {
                if (next) {
                    selected[v] = text;
                    syncHiddenOption(v, text, true);
                } else {
                    delete selected[v];
                    syncHiddenOption(v, text, false);
                }
                updateCounter();
                renderSelected();
                // Seçilən element YALNIZ yuxarı (selectedWrap) siyahıda qalmalıdır.
                // Əvvəl nəticə sətri silinmirdi → eyni element iki yerdə (hər
                // ikisi işarəli) görünürdü və "başqa element də seçildi" təsiri
                // yaranırdı. İndi seçiləndə nəticələrdən silirik, seçim
                // götürüləndə isə geri qaytarırıq.
                var esc = v.replace(/"/g, '\\"');
                var resRow = resultsWrap.querySelector('[data-value="' + esc + '"]');
                if (next) {
                    if (resRow) {
                        resRow.parentNode.removeChild(resRow);
                    }
                } else if (resRow) {
                    var cb = resRow.querySelector(".create-exam-item-checkbox");
                    if (cb) {
                        cb.checked = false;
                    }
                } else {
                    resultsWrap.appendChild(makeRow(v, text, false));
                }
                if (typeof selectionChangeHandler === "function") {
                    selectionChangeHandler();
                }
            }
            checkbox.addEventListener("change", function () {
                toggle(checkbox.checked);
            });
            row.addEventListener("click", function (event) {
                if (event.target === checkbox || event.target === label) {
                    return;
                }
                checkbox.checked = !checkbox.checked;
                toggle(checkbox.checked);
            });
            return row;
        }

        function renderSelected() {
            selectedWrap.innerHTML = "";
            Object.keys(selected).forEach(function (v) {
                selectedWrap.appendChild(makeRow(v, selected[v], true));
            });
        }

        function appendResults(items) {
            // Qrup filtri aktivdirsə (sağ tələbə siyahısı seçilmiş qrupun
            // üzvləridir) — sətirlər işarəli/qeyri-aktiv (qrupla daxil) göstərilir.
            var asGroupMembers = Boolean(extraParamsProvider && extraParamsProvider());
            items.forEach(function (item) {
                var id = String(item.id);
                if (selected[id]) {
                    return; // artıq fərdi seçilibsə yuxarıda göstərilir
                }
                if (resultsWrap.querySelector('[data-value="' + id.replace(/"/g, '\\"') + '"]')) {
                    return; // dublikat
                }
                resultsWrap.appendChild(makeRow(id, item.text, false, asGroupMembers));
            });
        }

        function showEmpty() {
            if (!selectedWrap.children.length && !resultsWrap.children.length) {
                var empty = document.createElement("div");
                empty.className = "create-exam-search-empty";
                empty.textContent = query ? gettext("Nəticə tapılmadı") : gettext("Məlumat yoxdur");
                resultsWrap.appendChild(empty);
            }
        }

        function loadPage(reset) {
            if (!searchUrl || loading) {
                return;
            }
            if (reset) {
                offset = 0;
                hasMore = true;
                resultsWrap.innerHTML = "";
            }
            if (!hasMore) {
                return;
            }
            loading = true;
            var seq = ++requestSeq;
            var extra = (typeof extraParamsProvider === "function" && extraParamsProvider()) || "";
            var url = searchUrl +
                (searchUrl.indexOf("?") === -1 ? "?" : "&") +
                "q=" + encodeURIComponent(query) +
                "&offset=" + offset + "&limit=" + PAGE_SIZE + extra;
            fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (r) { return r.ok ? r.json() : { results: [], has_more: false }; })
                .then(function (data) {
                    if (seq !== requestSeq) {
                        return;
                    }
                    var results = (data && data.results) || [];
                    appendResults(results);
                    offset += results.length;
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

        if (searchInput) {
            searchInput.addEventListener("input", function () {
                if (debounceTimer) {
                    clearTimeout(debounceTimer);
                }
                query = searchInput.value.trim();
                debounceTimer = setTimeout(function () {
                    loadPage(true);
                }, DEBOUNCE_MS);
            });
        }

        // Infinite scroll: siyahının sonuna yaxınlaşanda növbəti səhifə.
        listContainer.addEventListener("scroll", function () {
            if (loading || !hasMore) {
                return;
            }
            if (listContainer.scrollTop + listContainer.clientHeight >= listContainer.scrollHeight - 40) {
                loadPage(false);
            }
        });

        renderSelected();
        updateCounter();
        loadPage(true); // ilk 10-u dərhal yüklə

        return {
            getSelectedValues: function () {
                return Object.keys(selected);
            },
            // Seçilmişlərin adları (təsdiq modalında qrup adlarını göstərmək üçün).
            getSelectedItems: function () {
                return Object.keys(selected).map(function (v) {
                    return { value: v, text: selected[v] };
                });
            },
            setValueSelected: function (value, isSelected) {
                var v = String(value);
                if (isSelected) {
                    selected[v] = selected[v] || v;
                    syncHiddenOption(v, selected[v], true);
                } else {
                    delete selected[v];
                    syncHiddenOption(v, v, false);
                }
                updateCounter();
                renderSelected();
            },
            // Nəticə siyahısını yenidən yüklə (seçilmiş qrup dəyişəndə çağırılır).
            reload: function () {
                loadPage(true);
            },
            // Axtarış URL-inə əlavə query fraqmenti verən callback (məs. qrup ID-ləri).
            setExtraParamsProvider: function (fn) {
                extraParamsProvider = fn;
            },
            // Seçim dəyişəndə (əlavə/çıxarma) çağırılan callback.
            setOnSelectionChange: function (fn) {
                selectionChangeHandler = fn;
            }
        };
    }

    /* Qrup→tələbə sinxronu: qrup seçiləndə sağ tələbə siyahısı yalnız həmin
       qrup(lar)ın üzvlərini göstərir (server `groups` filtri) və dəyişəndə
       yenidən yüklənir. Qrup seçilməyibsə bütün tələbələr göstərilir. */
    function initGroupUserSync(form, groupSelector, userSelector) {
        if (!groupSelector || !userSelector) {
            return;
        }
        userSelector.setExtraParamsProvider(function () {
            var ids = groupSelector.getSelectedValues();
            return ids.length ? "&groups=" + encodeURIComponent(ids.join(",")) : "";
        });
        groupSelector.setOnSelectionChange(function () {
            userSelector.reload();
        });
        // Redaktə rejimi: form açılanda qrup(lar) onsuz da seçilibsə, sağ siyahını
        // dərhal həmin üzvlərlə süz.
        if (groupSelector.getSelectedValues().length) {
            userSelector.reload();
        }
    }

    ns.searchableSelect = {
        initGroupUserSync: initGroupUserSync,
        initSearchableSelect: initSearchableSelect
    };
})(window.EMSExamCreateEditModal = window.EMSExamCreateEditModal || {}, document);

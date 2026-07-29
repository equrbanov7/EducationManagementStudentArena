/* Zala nəzarətçi təyini — AJAX (debounced) axtarış + çip seçimi.

   Bütün istifadəçilər eyni anda YÜKLƏNMİR: yalnız yazılan sorğuya uyğun 10-luq
   səhifə gətirilir (sistemi yükləməmək üçün); siyahının sonuna çatanda növbəti
   səhifə əlavə olunur. Kafedra adı sağda göstərilir.

   2026-07-30: bu kod template içində `<script nonce>` blokunda idi. Layihə
   qaydası inline/internal JS-ə icazə vermir (CSP: SELF + NONCE) — xarici fayla
   çıxarıldı. Xarici fayl Django template engine-dən keçmir, ona görə URL-lər və
   tərcümə mətnləri panelin data-atributlarından oxunur.

   Markup müqaviləsi — `[data-rma-invigilators]` paneli:
     data-search-url               namizəd axtarışı endpoint-i
     data-profile-url-template     "__U__" yer tutucusu ilə profil URL-i
     data-i18n-no-result / -view-profile / -add    tərcümə mətnləri
*/

(function () {
    "use strict";

    var DEBOUNCE_MS = 300;
    var PAGE_SIZE = 10;

    function init() {
        // Səhifədə bir neçə `.rma-panel` var (nəzarətçilər + kompüterlər) —
        // sənəd sırasına güvənmirik, panel öz atributu ilə seçilir.
        var panel = document.querySelector("[data-rma-invigilators]");
        if (!panel || panel.dataset.rmaInvigBound === "1") return;

        var search = panel.querySelector(".js-rma-search");
        var results = panel.querySelector(".js-rma-results");
        var chipsWrap = panel.querySelector(".js-rma-chips");
        if (!search || !results || !chipsWrap) return;

        panel.dataset.rmaInvigBound = "1"; // idempotent (AJAX swap / təkrar init)

        var countEl = panel.querySelector(".js-rma-count");
        var totalEl = panel.querySelector(".js-rma-total");
        var searchUrl = panel.getAttribute("data-search-url") || "";
        var profileTpl = panel.getAttribute("data-profile-url-template") || "";
        var T = {
            noResult: panel.getAttribute("data-i18n-no-result") || "",
            viewProfile: panel.getAttribute("data-i18n-view-profile") || "",
            add: panel.getAttribute("data-i18n-add") || ""
        };

        var timer = null;
        var seq = 0;
        var offset = 0;
        var hasMore = false;
        var loadingMore = false;
        var currentQuery = "";
        var opened = false;
        // Bütün indiyə qədər yüklənmiş namizədlər (səhifə-səhifə toplanır) —
        // "+" ilə əlavə edildikdə tam siyahı yenidən çəkilir ki, əvvəlki
        // səhifələrin sətirləri itməsin.
        var loadedItems = [];

        function profileUrl(username) {
            return profileTpl ? profileTpl.replace("__U__", encodeURIComponent(username)) : "";
        }

        function selectedIds() {
            return Array.prototype.map.call(chipsWrap.querySelectorAll(".rma-chip-sel"), function (chip) {
                return chip.getAttribute("data-id");
            });
        }

        function updateCounts() {
            var n = chipsWrap.querySelectorAll(".rma-chip-sel").length;
            if (countEl) countEl.textContent = n;
            if (totalEl) totalEl.textContent = n;
        }

        function nameNode(url, className, text, title) {
            var node = document.createElement(url ? "a" : "span");
            node.className = className;
            if (url) {
                node.href = url;
                node.target = "_blank";
                node.rel = "noopener";
                if (title) node.title = title;
            }
            node.textContent = text;
            return node;
        }

        function addChip(id, name, username) {
            if (selectedIds().indexOf(String(id)) !== -1) return;

            var chip = document.createElement("span");
            chip.className = "rma-chip-sel";
            chip.setAttribute("data-id", id);
            chip.appendChild(nameNode(profileUrl(username), "rma-chip-sel__name", name, T.viewProfile));

            var remove = document.createElement("button");
            remove.type = "button";
            remove.className = "rma-chip-sel__x js-rma-remove";
            remove.setAttribute("data-id", id);
            remove.textContent = "×";
            chip.appendChild(remove);

            var hidden = document.createElement("input");
            hidden.type = "hidden";
            hidden.name = "invigilators";
            hidden.value = id;
            chip.appendChild(hidden);

            chipsWrap.appendChild(chip);
            updateCounts();
        }

        function renderResults(items) {
            results.textContent = "";
            var chosen = selectedIds();
            var shown = 0;

            items.forEach(function (item) {
                if (chosen.indexOf(String(item.id)) !== -1) return;
                shown++;

                var row = document.createElement("div");
                row.className = "rma-result";
                row.setAttribute("role", "option");

                // Ada klik → profil (yeni tab); "+" düyməsi → nəzarətçi əlavə et.
                row.appendChild(
                    nameNode(
                        profileUrl(item.username),
                        item.username ? "rma-item__name rma-item__namelink" : "rma-item__name",
                        item.text + " · " + item.username,
                        T.viewProfile
                    )
                );

                var kafedra = document.createElement("span");
                kafedra.className = item.kafedra ? "rma-item__kaf" : "rma-item__kaf rma-item__kaf--none";
                kafedra.textContent = item.kafedra || "—";
                row.appendChild(kafedra);

                var add = document.createElement("button");
                add.type = "button";
                add.className = "rma-result__add js-rma-add";
                if (T.add) add.title = T.add;
                add.innerHTML = '<i class="fas fa-plus"></i>';
                add.addEventListener("click", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    addChip(item.id, item.text, item.username);
                    renderResults(loadedItems);
                    search.focus();
                });
                row.appendChild(add);

                results.appendChild(row);
            });

            if (!shown) {
                var empty = document.createElement("div");
                empty.className = "rma-empty rma-muted";
                empty.textContent = T.noResult;
                results.appendChild(empty);
            }
        }

        // `reset`=true → yeni axtarış (panel açılanda da ilk səhifə); `reset`=false
        // → aşağı sürüşdürdükcə növbəti səhifə (bütün namizədlər bir dəfəyə
        // yüklənmir).
        function doSearch(query, reset) {
            if (!searchUrl) return;
            if (reset) {
                offset = 0;
                hasMore = false;
                currentQuery = query;
                loadedItems = [];
            } else {
                if (loadingMore || !hasMore) return;
                loadingMore = true;
            }

            var mine = reset ? ++seq : seq;
            if (reset) {
                results.textContent = "";
                var loading = document.createElement("div");
                loading.className = "rma-loading";
                loading.textContent = "…";
                results.appendChild(loading);
            }

            var url =
                searchUrl +
                (searchUrl.indexOf("?") === -1 ? "?" : "&") +
                "q=" + encodeURIComponent(query) +
                "&offset=" + offset +
                "&limit=" + PAGE_SIZE;

            fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (response) {
                    return response.ok ? response.json() : { results: [], has_more: false };
                })
                .then(function (data) {
                    if (reset && mine !== seq) return; // köhnəlmiş sorğu
                    var items = (data && data.results) || [];
                    loadedItems = loadedItems.concat(items);
                    offset += items.length;
                    hasMore = Boolean(data && data.has_more);
                    if (!reset) loadingMore = false;
                    renderResults(loadedItems);
                })
                .catch(function () {
                    if (reset) {
                        if (mine === seq) results.textContent = "";
                    } else {
                        loadingMore = false;
                    }
                });
        }

        function ensureOpened() {
            // Panel açılanda ilk səhifə dərhal yüklənir — "yazın" ipucu yerinə.
            if (!opened) {
                opened = true;
                doSearch("", true);
            }
        }

        chipsWrap.addEventListener("click", function (event) {
            var button = event.target.closest && event.target.closest(".js-rma-remove");
            if (!button) return;
            var chip = button.closest(".rma-chip-sel");
            if (chip && chip.parentNode) {
                chip.parentNode.removeChild(chip);
                updateCounts();
            }
        });

        results.addEventListener("scroll", function () {
            if (loadingMore || !hasMore) return;
            if (results.scrollTop + results.clientHeight >= results.scrollHeight - 40) {
                doSearch(currentQuery, false);
            }
        });

        search.addEventListener("input", function () {
            if (timer) clearTimeout(timer);
            var query = search.value.trim();
            timer = setTimeout(function () {
                doSearch(query, true);
            }, DEBOUNCE_MS);
        });

        panel.addEventListener("toggle", function () {
            if (panel.open) ensureOpened();
        });
        search.addEventListener("focus", ensureOpened);

        updateCounts();
    }

    if (window.EMSReady) {
        window.EMSReady(init);
    } else if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();

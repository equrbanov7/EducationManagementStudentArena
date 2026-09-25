/* =========================================================================
   results_text.js — anonim şərhlər / ümumi təkliflər: dözümlü axtarış
   (EMSSearch: ı/i, ə/e/a, ş/s/sh, ç/c/ch, ğ/g, ö/o, ü/u; bütün sözlər VƏ ilə), açar söz çipləri,
   «Daha çox göstər» səhifələməsi və uyğunluğun vurğulanması.

   TƏHLÜKƏSİZLİK: mətnlər istifadəçi girişidir — vurğu YALNIZ mətn düyünləri və
   `<mark>` elementləri ilə qurulur (`textContent`), heç vaxt `innerHTML` ilə.
   AJAX-safe: `EMSReady` + konteynerdə `data-svr-text-init`; çekməcə fraqmenti
   yerləşəndən sonra `EMSSurveyResults.text.scan(konteyner)` çağırılır.
   ========================================================================= */
(function (window, document) {
    "use strict";

    var NS = (window.EMSSurveyResults = window.EMSSurveyResults || {});
    if (NS.text) {
        return;
    }

    function fold(text) {
        return String(text || "")
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .replace(/ə/g, "e")
            .replace(/ı/g, "i");
    }

    /* Hər simvolu ayrıca qatlayır → qatlanmış mətn + orijinal indekslərə xəritə. */
    function foldWithMap(text) {
        var folded = "";
        var map = [];
        for (var i = 0; i < text.length; i += 1) {
            var part = fold(text.charAt(i));
            for (var j = 0; j < part.length; j += 1) {
                folded += part.charAt(j);
                map.push(i);
            }
        }
        return { folded: folded, map: map };
    }

    function foldedTokens(query) {
        return fold(query)
            .split(/\s+/)
            .filter(function (token) {
                return token.length > 0;
            })
            .slice(0, 4);
    }

    /* Sorğu → axtarıcı. EMSSearch varsa onun regex-ləri (az↔en hərfləri, ə↔a,
       «sh»↔ş…; sərbəst mətn olduğu üçün compact YOX — vurğu sözlər arası
       boşluğa yayılmasın), yoxdursa köhnə `fold` + indeks xəritəsi. */
    function finder(query) {
        var api = window.EMSSearch;
        if (api) {
            var words = api.tokens(query);
            var sources = words.map(function (word) {
                return api.pattern(word, { compact: false });
            });
            var tests = sources.map(function (src) { return new RegExp(src, "i"); });
            var globals = sources.map(function (src) { return new RegExp(src, "gi"); });
            return {
                words: words,
                test: function (text) {
                    return tests.every(function (rx) { return rx.test(text); });
                },
                ranges: function (text) {
                    var out = [];
                    globals.forEach(function (rx) {
                        rx.lastIndex = 0;
                        var m = rx.exec(text);
                        while (m) {
                            if (m[0].length) {
                                out.push([m.index, m.index + m[0].length]);
                            } else {
                                rx.lastIndex += 1;
                            }
                            m = rx.exec(text);
                        }
                    });
                    return out;
                }
            };
        }
        var folded = foldedTokens(query);
        return {
            words: folded,
            test: function (text) {
                var hay = fold(text);
                return folded.every(function (word) { return hay.indexOf(word) !== -1; });
            },
            ranges: function (text) {
                var index = foldWithMap(text);
                var out = [];
                folded.forEach(function (word) {
                    var at = index.folded.indexOf(word);
                    while (at !== -1) {
                        out.push([index.map[at], index.map[at + word.length - 1] + 1]);
                        at = index.folded.indexOf(word, at + word.length);
                    }
                });
                return out;
            }
        };
    }

    function paint(item, find) {
        var original = item._svrText;
        item.textContent = "";
        if (!find.words.length) {
            item.textContent = original;
            return;
        }
        var ranges = find.ranges(original);
        ranges.sort(function (a, b) {
            return a[0] - b[0];
        });
        var cursor = 0;
        ranges.forEach(function (range) {
            if (range[0] < cursor) {
                return; // üst-üstə düşən uyğunluq — artıq vurğulanıb
            }
            if (range[0] > cursor) {
                item.appendChild(document.createTextNode(original.slice(cursor, range[0])));
            }
            var mark = document.createElement("mark");
            mark.className = "svr-mark";
            mark.textContent = original.slice(range[0], range[1]);
            item.appendChild(mark);
            cursor = range[1];
        });
        if (cursor < original.length) {
            item.appendChild(document.createTextNode(original.slice(cursor)));
        }
    }

    function apply(container) {
        var state = container._svrText;
        if (!state) {
            return;
        }
        var find = finder(state.query);
        var words = find.words;
        var total = 0;
        state.lists.forEach(function (entry) {
            var matched = entry.items.filter(function (item) {
                return !words.length || find.test(item._svrText);
            });
            total += matched.length;
            var limit = entry.page * entry.size;
            var shown = new Set(matched.slice(0, limit));
            entry.items.forEach(function (item) {
                var visible = shown.has(item);
                item.hidden = !visible;
                if (visible) {
                    paint(item, find);
                }
            });
            if (entry.more) {
                entry.more.hidden = matched.length <= limit;
            }
        });
        if (state.count) {
            var t = (container.closest("[data-i18n-n]") || container).dataset;
            state.count.textContent = words.length ? total + " " + (t.i18nMatches || "") : "";
        }
        container.querySelectorAll("[data-svr-word]").forEach(function (chip) {
            var active = words.length === 1 && fold(chip.getAttribute("data-svr-word")) === fold(words[0]);
            chip.setAttribute("aria-pressed", active ? "true" : "false");
        });
    }

    function scan(scope) {
        (scope || document).querySelectorAll("[data-svr-text]").forEach(function (container) {
            if (container.dataset.svrTextInit === "1") {
                return;
            }
            container.dataset.svrTextInit = "1";
            var lists = [];
            container.querySelectorAll("[data-svr-text-list]").forEach(function (list) {
                var items = Array.prototype.slice.call(list.querySelectorAll("[data-svr-text-item]"));
                items.forEach(function (item) {
                    item._svrText = item.textContent;
                });
                var next = list.nextElementSibling;
                lists.push({
                    items: items,
                    size: parseInt(list.getAttribute("data-page"), 10) || 20,
                    page: 1,
                    more: next && next.hasAttribute("data-svr-text-more") ? next : null
                });
            });
            container._svrText = {
                query: "",
                lists: lists,
                count: container.querySelector("[data-svr-text-count]")
            };
            apply(container);
        });
    }

    function containerOf(node) {
        return node.closest("[data-svr-text]");
    }

    function setQuery(container, value) {
        var state = container._svrText;
        if (!state) {
            return;
        }
        state.query = value || "";
        state.lists.forEach(function (entry) {
            entry.page = 1;
        });
        apply(container);
    }

    var timer = null;
    window.EMSDelegate.on("input", "[data-svr-text-search]", function (event, input) {
        var container = containerOf(input);
        if (!container) {
            return;
        }
        window.clearTimeout(timer);
        timer = window.setTimeout(function () {
            setQuery(container, input.value);
        }, 150);
    });

    window.EMSDelegate.on("click", "[data-svr-word]", function (event, chip) {
        var container = containerOf(chip);
        if (!container) {
            return;
        }
        var input = container.querySelector("[data-svr-text-search]");
        var word = chip.getAttribute("data-svr-word") || "";
        var value = chip.getAttribute("aria-pressed") === "true" ? "" : word;
        if (input) {
            input.value = value;
        }
        setQuery(container, value);
    });

    window.EMSDelegate.on("click", "[data-svr-text-more]", function (event, button) {
        var container = containerOf(button);
        var state = container ? container._svrText : null;
        if (!state) {
            return;
        }
        state.lists.forEach(function (entry) {
            if (entry.more === button) {
                entry.page += 1;
            }
        });
        apply(container);
    });

    window.EMSReady(function () {
        scan(document);
    });

    /** Çap üçün: axtarışı sıfırlayır və bütün mətnləri açır. */
    function reveal(container) {
        var state = container && container._svrText;
        if (state) {
            state.query = "";
            state.lists.forEach(function (entry) {
                entry.page = Math.max(1, Math.ceil(entry.items.length / entry.size));
            });
            apply(container);
        }
    }

    NS.text = { scan: scan, fold: fold, apply: apply, setQuery: setQuery, reveal: reveal };
})(window, document);

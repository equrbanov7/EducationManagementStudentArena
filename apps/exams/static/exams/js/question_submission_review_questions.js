/* Göndəriş baxışı — sual siyahısının lazy yüklənməsi + filtr + axtarış.
 *
 * Server ilkin səhifəni render edir; bu skript:
 *   • sonsuz sürüşmə (IntersectionObserver, sentinel-ə klik fallback-i) ilə
 *     növbəti səhifələri exams:question_submission_questions endpoint-dən çəkir;
 *   • Hamısı/Xətalı/Xəbərdarlıq/Təmiz pillərini və debounce-lu axtarışı idarə
 *     edir (hər dəyişiklik siyahını sıfırlayıb yenidən yükləyir);
 *   • köhnəlmiş cavabları seq nömrəsi ilə atır. CSP-təhlükəsiz (xarici fayl).
 */
(function () {
    "use strict";

    var DEBOUNCE_MS = 350;

    function init() {
        var root = document.querySelector(".js-qsubq");
        if (!root || root.dataset.qsubqReady === "1") {
            return;
        }
        root.dataset.qsubqReady = "1";

        var url = root.getAttribute("data-questions-url") || "";
        var pageSize = parseInt(root.getAttribute("data-page-size"), 10) || 20;
        var list = root.querySelector(".js-qsubq-list");
        var sentinel = root.querySelector(".js-qsubq-sentinel");
        var empty = root.querySelector(".js-qsubq-empty");
        var searchInput = root.querySelector(".js-qsubq-search");
        if (!url || !list || !sentinel) {
            return;
        }

        var state = {
            flag: "",
            q: "",
            offset: list.children.length,
            hasMore: root.getAttribute("data-has-more") === "1",
            busy: false,
            seq: 0
        };

        function syncUi() {
            sentinel.hidden = !state.hasMore;
            if (empty) {
                empty.hidden = list.children.length !== 0;
            }
        }

        function updateCounts(counts) {
            if (!counts) {
                return;
            }
            root.querySelectorAll("[data-count-key]").forEach(function (el) {
                var key = el.getAttribute("data-count-key");
                if (counts[key] != null) {
                    el.textContent = counts[key];
                }
            });
        }

        function fetchPage(reset) {
            if (state.busy) {
                return;
            }
            state.busy = true;
            sentinel.classList.add("is-loading");
            var seq = ++state.seq;
            var params = new URLSearchParams();
            params.set("offset", String(reset ? 0 : state.offset));
            params.set("limit", String(pageSize));
            if (state.flag) {
                params.set("flag", state.flag);
            }
            if (state.q) {
                params.set("q", state.q);
            }
            fetch(url + "?" + params.toString(), { headers: { "X-Requested-With": "XMLHttpRequest" } })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (d) {
                    if (!d || seq !== state.seq) {
                        return;
                    }
                    if (reset) {
                        list.innerHTML = "";
                        state.offset = 0;
                    }
                    list.insertAdjacentHTML("beforeend", d.html || "");
                    state.offset += d.returned || 0;
                    state.hasMore = !!d.has_more;
                    updateCounts(d.counts);
                    syncUi();
                })
                .catch(function () { /* şəbəkə xətası — sentinel klik ilə təkrar */ })
                .finally(function () {
                    state.busy = false;
                    sentinel.classList.remove("is-loading");
                });
        }

        function reload() {
            // Uçuşda olan cavab seq ilə etibarsızlaşır; busy kilidini açırıq ki,
            // filtr klikləri gecikmədən işləsin.
            state.seq++;
            state.busy = false;
            fetchPage(true);
        }

        // Sonsuz sürüşmə (IO yoxdursa sentinel düyməsinə klik işləyir).
        if ("IntersectionObserver" in window) {
            var observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting && state.hasMore && !state.busy) {
                        fetchPage(false);
                    }
                });
            }, { rootMargin: "600px 0px" });
            observer.observe(sentinel);
        }
        sentinel.addEventListener("click", function () {
            if (state.hasMore) {
                fetchPage(false);
            }
        });

        root.querySelectorAll(".qsubq-pill").forEach(function (btn) {
            btn.addEventListener("click", function () {
                root.querySelectorAll(".qsubq-pill").forEach(function (other) {
                    var active = other === btn;
                    other.classList.toggle("is-active", active);
                    other.setAttribute("aria-pressed", active ? "true" : "false");
                });
                state.flag = btn.getAttribute("data-flag") || "";
                reload();
            });
        });

        if (searchInput) {
            var timer = null;
            searchInput.addEventListener("input", function () {
                if (timer) {
                    clearTimeout(timer);
                }
                timer = setTimeout(function () {
                    var value = searchInput.value.trim();
                    if (value === state.q) {
                        return;
                    }
                    state.q = value;
                    reload();
                }, DEBOUNCE_MS);
            });
        }

        syncUi();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

/* Optional same-origin search for a native select whose initial list is bounded.
 * The native value, placeholder and all normal Bootstrap select events remain authoritative. */
(function () {
    "use strict";

    window.EMSBootstrapRemoteSearch = function (select, input, refresh) {
        var lastKey = null;
        var timer = null;
        var sequence = 0;

        function replace(rows, query) {
            var current = String(select.value || "");
            var seen = new Set(current ? [current] : []);
            Array.from(select.options).forEach(function (option, index) {
                if (!((index === 0 && !option.value) || (current && option.value === current))) {
                    option.remove();
                }
            });
            rows.slice(0, 50).forEach(function (row) {
                if (!row || !["string", "number"].includes(typeof row.id) || typeof row.text !== "string") return;
                var value = String(row.id);
                if (!value || seen.has(value)) return;
                seen.add(value);
                var option = document.createElement("option");
                option.value = value;
                option.textContent = row.text;
                // The server uses tolerant code/name matching; do not hide its result locally.
                option.setAttribute("data-search", query);
                select.appendChild(option);
            });
            refresh();
        }

        return function () {
            var field = input();
            var url = select.getAttribute("data-live-search-url");
            if (!url || !field) return;
            var query = field.value.trim();
            var key = url + "\n" + query;
            if (key === lastKey) return;
            lastKey = key;
            var request = ++sequence; // invalidate in-flight responses before the new debounce starts
            window.clearTimeout(timer);
            select._emsRemoteSearchStarted = true;
            timer = window.setTimeout(function () {
                var target;
                try {
                    target = new URL(url, window.location.href);
                    if (target.origin !== window.location.origin) return;
                } catch (_) { return; }
                target.searchParams.set("q", query);
                target.searchParams.set("limit", "50");
                fetch(target.toString(), { credentials: "same-origin", headers: { Accept: "application/json" } })
                    .then(function (response) {
                        return response.ok ? response.json() : Promise.reject(response.status);
                    })
                    .then(function (payload) {
                        if (request === sequence && select.isConnected && input().value.trim() === query &&
                            select.getAttribute("data-live-search-url") === url && Array.isArray(payload.results)) {
                            replace(payload.results, query);
                        }
                    })
                    .catch(function () {
                        if (request === sequence) lastKey = null;
                    });
            }, 250);
        };
    };
})();

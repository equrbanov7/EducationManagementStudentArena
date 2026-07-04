/*
 * Global ⌘K search (U8) — command-palette overlay.
 * CSP-safe (no inline handlers), progressive-enhancement: if JS fails the
 * overlay simply never opens and the rest of the app is unaffected.
 *
 * Behaviour:
 *   - Open  : ⌘K / Ctrl+K, or click [data-global-search-open].
 *   - Close : Esc, backdrop click, or picking a result.
 *   - Query : debounced GET to [data-search-url]?q= → grouped JSON results.
 *   - Keys  : ↑/↓ move the active option (wrap), Enter follows it.
 * A11y: role=dialog/listbox/option, aria-activedescendant on the input.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-global-search]");
  if (!root) return;

  var input = root.querySelector("[data-global-search-input]");
  var resultsEl = root.querySelector("[data-global-search-results]");
  var emptyEl = root.querySelector("[data-global-search-empty]");
  var searchUrl = root.getAttribute("data-search-url");

  var options = []; // flat list of <a role="option"> elements
  var activeIndex = -1;
  var debounceTimer = null;
  var requestToken = 0;
  var lastFocused = null;

  function isOpen() {
    return !root.hasAttribute("hidden");
  }

  function open() {
    if (isOpen()) return;
    lastFocused = document.activeElement;
    root.removeAttribute("hidden");
    document.body.classList.add("gsearch-open");
    input.value = "";
    input.focus();
    runQuery(""); // show nav quick-links immediately
  }

  function close() {
    if (!isOpen()) return;
    root.setAttribute("hidden", "");
    document.body.classList.remove("gsearch-open");
    clearResults();
    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
  }

  function clearResults() {
    resultsEl.textContent = "";
    options = [];
    activeIndex = -1;
    input.removeAttribute("aria-activedescendant");
  }

  function safeIcon(icon) {
    return /^fa-[a-z0-9-]+$/.test(icon || "") ? icon : "fa-circle";
  }

  function renderGroups(groups) {
    clearResults();
    var counter = 0;
    (groups || []).forEach(function (group) {
      var section = document.createElement("div");
      section.className = "gsearch__group";

      var label = document.createElement("div");
      label.className = "gsearch__group-label";
      label.textContent = group.label;
      section.appendChild(label);

      (group.items || []).forEach(function (item) {
        var a = document.createElement("a");
        a.className = "gsearch__item";
        a.href = item.url;
        a.setAttribute("role", "option");
        a.id = "gsearch-opt-" + counter++;

        var icon = document.createElement("i");
        icon.className = "fas " + safeIcon(item.icon) + " gsearch__item-icon";
        icon.setAttribute("aria-hidden", "true");
        a.appendChild(icon);

        var body = document.createElement("span");
        body.className = "gsearch__item-body";
        var title = document.createElement("span");
        title.className = "gsearch__item-title";
        title.textContent = item.title;
        body.appendChild(title);
        if (item.subtitle) {
          var sub = document.createElement("span");
          sub.className = "gsearch__item-subtitle";
          sub.textContent = item.subtitle;
          body.appendChild(sub);
        }
        a.appendChild(body);

        section.appendChild(a);
        options.push(a);
      });

      if (group.items && group.items.length) resultsEl.appendChild(section);
    });

    var hasResults = options.length > 0;
    emptyEl.hidden = hasResults;
    if (hasResults) setActive(0);
  }

  function setActive(index) {
    if (!options.length) return;
    if (index < 0) index = options.length - 1;
    if (index >= options.length) index = 0;
    options.forEach(function (o) {
      o.classList.remove("is-active");
    });
    activeIndex = index;
    var el = options[activeIndex];
    el.classList.add("is-active");
    input.setAttribute("aria-activedescendant", el.id);
    el.scrollIntoView({ block: "nearest" });
  }

  function runQuery(q) {
    var token = ++requestToken;
    fetch(searchUrl + "?q=" + encodeURIComponent(q), {
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) {
        return r.ok ? r.json() : { groups: [] };
      })
      .then(function (data) {
        if (token !== requestToken || !isOpen()) return; // stale response
        renderGroups(data.groups);
      })
      .catch(function () {
        if (token === requestToken) renderGroups([]);
      });
  }

  // ── Events ────────────────────────────────────────────────────────────────
  document.addEventListener("keydown", function (e) {
    var key = e.key ? e.key.toLowerCase() : "";
    if ((e.metaKey || e.ctrlKey) && key === "k") {
      e.preventDefault();
      isOpen() ? close() : open();
    } else if (key === "escape" && isOpen()) {
      e.preventDefault();
      close();
    }
  });

  document.addEventListener("click", function (e) {
    var trigger = e.target.closest("[data-global-search-open]");
    if (trigger) {
      e.preventDefault();
      open();
      return;
    }
    if (e.target.closest("[data-global-search-close]")) {
      close();
    }
  });

  input.addEventListener("input", function () {
    var q = input.value.trim();
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      runQuery(q);
    }, 180);
  });

  input.addEventListener("keydown", function (e) {
    if (!isOpen()) return;
    var key = e.key ? e.key.toLowerCase() : "";
    if (key === "arrowdown") {
      e.preventDefault();
      setActive(activeIndex + 1);
    } else if (key === "arrowup") {
      e.preventDefault();
      setActive(activeIndex - 1);
    } else if (key === "enter") {
      if (activeIndex >= 0 && options[activeIndex]) {
        e.preventDefault();
        window.location.href = options[activeIndex].href;
      }
    }
  });

  // Hover syncs the active option with the pointer.
  resultsEl.addEventListener("mousemove", function (e) {
    var item = e.target.closest(".gsearch__item");
    if (!item) return;
    var idx = options.indexOf(item);
    if (idx >= 0 && idx !== activeIndex) setActive(idx);
  });
})();

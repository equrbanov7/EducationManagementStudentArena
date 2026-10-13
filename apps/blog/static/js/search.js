(function () {
    // 2026-10-14: köhnə (yavaş) cavab yeni siyahının üstünə yazılmasın.
    let listingSeq = 0;

    function sanitizeContent(element) {
        const clone = element.cloneNode(true);

        const scripts = clone.querySelectorAll("script");
        scripts.forEach((script) => script.remove());

        const allElements = clone.querySelectorAll("*");
        allElements.forEach((el) => {
            Array.from(el.attributes).forEach((attr) => {
                if (attr.name.startsWith("on")) {
                    el.removeAttribute(attr.name);
                }
            });

            ["href", "src", "action", "formaction"].forEach((attrName) => {
                const attrValue = el.getAttribute(attrName);
                if (attrValue && attrValue.toLowerCase().trim().startsWith("javascript:")) {
                    el.removeAttribute(attrName);
                }
            });
        });

        return clone;
    }

    function getListingShell() {
        return document.getElementById("homeListingShell");
    }

    function setLoadingState(isLoading) {
        const listingShell = getListingShell();
        if (!listingShell) {
            return;
        }

        listingShell.style.opacity = isLoading ? "0.5" : "1";
        listingShell.style.transition = "opacity 0.3s";
    }

    function updateListing(html) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, "text/html");
        const newContentElement = doc.getElementById("homeListingShell");
        const listingShell = getListingShell();

        if (!newContentElement || !listingShell) {
            return;
        }

        const sanitizedContent = sanitizeContent(newContentElement);
        listingShell.innerHTML = sanitizedContent.innerHTML;
    }

    function loadListing(url, { pushHistory = false } = {}) {
        const listingShell = getListingShell();
        if (!listingShell) {
            return;
        }

        setLoadingState(true);
        if (pushHistory) {
            window.history.pushState({}, "", url);
        }
        const mine = ++listingSeq;

        fetch(url)
            .then((response) => response.text())
            .then((html) => {
                if (mine !== listingSeq) {
                    return;
                }
                updateListing(html);
                setLoadingState(false);
            })
            .catch((error) => {
                if (mine !== listingSeq) {
                    return;
                }
                console.error(gettext("Xəta:"), error);
                setLoadingState(false);
            });
    }

    function buildSearchUrl(searchInput) {
        const url = new URL(window.location.href);
        const query = searchInput.value.trim();

        if (query) {
            url.searchParams.set("q", query);
        } else {
            url.searchParams.delete("q");
        }

        url.searchParams.delete("page");
        return url;
    }

    const searchInput = document.getElementById("searchInput");
    if (!searchInput) {
        return;
    }

    // Vahid EMSSearchInput qaydası: yazı dayananda 1500 ms, ≥ 2 simvol, Enter dərhal, IME.
    window.EMSSearchInput.bind(searchInput, {
        onSearch: () => {
            loadListing(buildSearchUrl(searchInput), { pushHistory: true });
        },
    });

    window.addEventListener("popstate", () => {
        const url = new URL(window.location.href);
        searchInput.value = url.searchParams.get("q") || "";
        window.EMSSearchInput.sync(searchInput);
        loadListing(url);
    });
})();

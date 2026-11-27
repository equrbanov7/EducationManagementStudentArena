/* «Müraciətlərim» — axtarış başqa bölmədə tapılanda keçid (sahib 2026-11-28).
 *
 * «Mənə gələnlər»də «MR-886» axtarılırdı, müraciət isə kafedrada idi — siyahı sadəcə «tapılmadı» deyirdi.
 * Server (`/muracietler/api/list/` → `elsewhere`) cari tab boş qalanda axtarışın hansı tablarda tapıldığını
 * qaytarır; burada boş vəziyyətin altına «‹Tab› · N» düymələri çəkilir. Düymə tabı və statusu dəyişib
 * siyahını yenidən yükləyir. AJAX-safe: sənəd səviyyəli `EMSDelegate`, `applications.js`-dən əvvəl yüklənir.
 */
(function () {
    "use strict";

    var NS = (window.EMSApplications = window.EMSApplications || {});

    function tabLabel(key) {
        var tab = NS.root && NS.root.querySelector('[data-apx-tab="' + key + '"]');
        if (!tab) {
            return key;
        }
        var badge = tab.querySelector("[data-apx-tab-count]");
        var text = tab.textContent || "";
        if (badge && badge.textContent) {
            text = text.replace(badge.textContent, "");
        }
        return text.replace(/\s+/g, " ").trim() || key;
    }

    NS.elsewhereHtml = function () {
        var spots = (NS.state && NS.state.q && NS.state.elsewhere) || [];
        if (!spots.length) {
            return "";
        }
        var buttons = spots.map(function (spot) {
            return (
                '<button type="button" class="apx-btn apx-empty__jump" data-apx-jump data-tab="' + NS.esc(spot.tab) +
                '" data-stat="' + NS.esc(spot.stat) + '">' + NS.esc(tabLabel(spot.tab)) + " · " +
                NS.esc(String(spot.count)) + "</button>"
            );
        });
        return (
            '<div class="apx-empty__elsewhere"><div class="apx-empty__note">' + NS.esc(NS.t("emptyElsewhere")) +
            '</div><div class="apx-empty__jumps">' + buttons.join("") + "</div></div>"
        );
    };

    window.EMSReady(function () {
        if (NS.__searchWired) {
            return;
        }
        NS.__searchWired = true;
        window.EMSDelegate.on("click", "[data-apx-jump]", function (event, node) {
            NS.state.tab = node.getAttribute("data-tab") || NS.state.tab;
            NS.state.stat = node.getAttribute("data-stat") || NS.state.stat;
            NS.state.page = 1;
            if (NS.renderTabs) {
                NS.renderTabs();
            }
            if (NS.loadList) {
                NS.loadList();
            }
        });
    });
})();

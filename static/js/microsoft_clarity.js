/* microsoft_clarity.js — Microsoft Clarity session-replay teqi.
 * Mənbə: templates/partials/_microsoft_clarity.html (inline nonce script,
 * 2026-09-21-də xarici fayla çıxarıldı — CSP `script-src` yalnız SELF + NONCE;
 * Clarity mənbələri `config/settings/components/csp.py`-də ayrıca icazəlidir).
 *
 * Layihə id-si dinamikdir → `<script src=… data-clarity-id="…">` atributundan
 * oxunur (`document.currentScript`, klassik/defer-siz skript). Bayraq
 * (`microsoft_clarity_enabled`) şablonda yoxlanır — bu fayl yalnız icazə
 * olanda yüklənir; id boşdursa heç nə etmir.
 */
(function () {
    var current = document.currentScript;
    var projectId = current && current.dataset ? current.dataset.clarityId : "";
    if (!projectId) {
        return;
    }
    (function (c, l, a, r, i, t, y) {
        c[a] = c[a] || function () { (c[a].q = c[a].q || []).push(arguments); };
        t = l.createElement(r);
        t.async = 1;
        t.src = "https://www.clarity.ms/tag/" + i;
        y = l.getElementsByTagName(r)[0];
        y.parentNode.insertBefore(t, y);
    })(window, document, "clarity", "script", projectId);
})();

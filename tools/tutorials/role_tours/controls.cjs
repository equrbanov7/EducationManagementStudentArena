"use strict";

// Executes inside the demonstrator's browser, restricted to the open panel.
function controlsInPanel(root) {
    const source = root.querySelectorAll('a[href],button,summary,select,[role="tab"],[role="button"]');
    const groupedSettings = root.matches('[data-profile-section-panel="system-settings"][data-profile-section-sub]:not([data-profile-section-sub="overview"])');
    const used = new Set();
    const choices = [];
    for (const el of source) {
        if ((el.closest('details:not([open])') && !(el.tagName==='SUMMARY' && el.parentElement===el.closest('details:not([open])'))) || !el.getClientRects().length || el.disabled || el.closest('[hidden],.modal:not(.show),dialog:not([open])')) continue;
        if (groupedSettings && el.closest('.sysset-nav')) continue;
        if (el.closest('aside.profile-sidebar,[data-faq-item],.ems-faq-pages,.pagination')) continue;
        const label = (el.getAttribute('aria-label') || el.innerText || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
        if (!label || label.length > 95 || /^[\d\s…‹›»«|/]+$/.test(label)) continue;
        const url = el.getAttribute('href') || '';
        const cl = el.className?.toString() || '';
        const tab = el.getAttribute('role') === 'tab' || !!el.closest('[role=tablist],.ems-tabs,[class$="__tabs"],[class$="-tabs"],.nav-tabs') || /(?:^|[ _-])tab(?:s?__btn|[ -]|$)/i.test(cl);
        const details = el.tagName === 'SUMMARY' || el.hasAttribute('aria-controls') || el.getAttribute('data-bs-toggle') === 'modal' || el.hasAttribute('aria-haspopup');
        const opens = /aç|göstər|bax|yeni|yarat|əlavə et|redaktə|təfərrüat|detal|filtr|araşdır|statistika|məlumat|siyahı|axtar|ətraflı|önbaxış|tərtib|seç|izlə|bölüşdür/i.test(label);
        const link = el.tagName === 'A' && url && url !== '#' && !url.startsWith('javascript:');
        const blocked = /sil(?:mək)?(?:\s|$)|göndər(?:mək)?(?:\s|$)|təsdiq(?:lə| et)(?:\s|$)|ləğv et|çıxış|logout|log-out|delete|remove|signout|download|yüklə|export|parolu sıfırla|saxla|tətbiq et|run now|impersonat|\/switch\//i.test(label+' '+url);
        if ((!tab && !details && !opens && !link) || blocked) continue;
        if (el.matches('button[type=submit],input[type=submit]') && !tab && !/^(axtar|göstər|filtr)/i.test(label)) continue;
        if (el.tagName === 'SELECT' || (link && !url.startsWith('#') && new URL(url,location.href).origin !== location.origin)) continue;
        if (el.getAttribute('target') === '_blank' || el.hasAttribute('download')) continue;
        const key = label.replace(/\s+\d+$/, '').toLocaleLowerCase('az');
        if (used.has(key)) continue;
        used.add(key);
        const id = 'c' + Array.from(key).reduce((hash,c)=>Math.imul(hash,31)+c.codePointAt(0)|0,0).toString(36);
        el.setAttribute('data-tutorial-control', id);
        const selected = el.getAttribute('aria-selected');
        const current = el.getAttribute('aria-current')?.trim().toLowerCase();
        const active = selected !== null ? selected === 'true' :
            current !== undefined ? Boolean(current && current !== 'false') : el.classList.contains('active');
        choices.push({id, label, tab, details, link, url, active});
    }
    return choices;
}

module.exports = {controlsInPanel};

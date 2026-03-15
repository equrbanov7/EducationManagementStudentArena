(function () {
    const catalog = window.LiveAvatarCatalog || {};

    function esc(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function getProfile(profile) {
        const avatarKey = profile?.avatar_key || profile?.avatarKey || catalog.defaultAvatarKey || "avatar_1";
        const accessoryKey =
            profile?.accessory_key || profile?.accessoryKey || catalog.defaultAccessoryKey || "accessory_none";
        return {
            avatarKey: catalog.avatars?.[avatarKey] ? avatarKey : catalog.defaultAvatarKey || "avatar_1",
            accessoryKey: catalog.accessories?.[accessoryKey]
                ? accessoryKey
                : catalog.defaultAccessoryKey || "accessory_none"
        };
    }

    function renderAccessory(accessoryKey) {
        switch (accessoryKey) {
            case "glasses":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--glasses" fill="none" stroke="#0f172a" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="46" cy="63" r="12"></circle>
                        <circle cx="94" cy="63" r="12"></circle>
                        <path d="M58 63h24"></path>
                        <path d="M34 59l-8-4"></path>
                        <path d="M106 59l8-4"></path>
                    </g>
                `;
            case "cap":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--cap">
                        <path d="M26 42c10-20 28-30 44-30 22 0 40 9 48 30l-12 4c-4-12-17-22-36-22-16 0-30 8-36 22z" fill="#0f766e"></path>
                        <path d="M24 40c18-8 35-12 52-12 17 0 31 4 42 12-7 5-20 8-42 8-24 0-39-3-52-8z" fill="#14b8a6"></path>
                        <path d="M86 44c10 1 22 6 28 11-9 4-20 6-31 6-6 0-11-1-16-2 4-8 10-13 19-15z" fill="#0f766e"></path>
                    </g>
                `;
            case "crown":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--crown">
                        <path d="M28 42l12-18 16 16 15-20 16 20 16-16 12 18-8 20H36z" fill="#facc15" stroke="#b45309" stroke-width="4" stroke-linejoin="round"></path>
                        <circle cx="40" cy="28" r="4" fill="#f97316"></circle>
                        <circle cx="71" cy="20" r="5" fill="#38bdf8"></circle>
                        <circle cx="102" cy="28" r="4" fill="#14b8a6"></circle>
                    </g>
                `;
            case "mask":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--mask">
                        <path d="M36 72c10-9 22-14 34-14 13 0 25 5 34 14-3 14-18 28-34 28-16 0-31-14-34-28z" fill="#0f766e"></path>
                        <path d="M34 70c-6 1-11 4-15 8" fill="none" stroke="#0f766e" stroke-width="4" stroke-linecap="round"></path>
                        <path d="M108 70c6 1 11 4 15 8" fill="none" stroke="#0f766e" stroke-width="4" stroke-linecap="round"></path>
                    </g>
                `;
            case "sparkles":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--sparkles" fill="#fef08a">
                        <path d="M22 42l3 8 8 3-8 3-3 8-3-8-8-3 8-3z"></path>
                        <path d="M112 34l2 6 6 2-6 2-2 6-2-6-6-2 6-2z"></path>
                        <path d="M96 102l3 7 7 3-7 3-3 7-3-7-7-3 7-3z"></path>
                    </g>
                `;
            case "bowtie":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--bowtie">
                        <path d="M52 108l-14 10 3-18 14 4z" fill="#ef4444"></path>
                        <path d="M88 108l14 10-3-18-14 4z" fill="#ef4444"></path>
                        <circle cx="70" cy="108" r="7" fill="#7c3aed"></circle>
                    </g>
                `;
            case "headphones":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--headphones" fill="none" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M34 66c0-24 14-40 36-40s36 16 36 40" stroke="#1f2937" stroke-width="6"></path>
                        <rect x="24" y="62" width="14" height="30" rx="7" fill="#8b5cf6" stroke="#1f2937" stroke-width="4"></rect>
                        <rect x="102" y="62" width="14" height="30" rx="7" fill="#8b5cf6" stroke="#1f2937" stroke-width="4"></rect>
                    </g>
                `;
            case "flower":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--flower">
                        <circle cx="102" cy="28" r="7" fill="#facc15"></circle>
                        <circle cx="94" cy="28" r="6" fill="#f472b6"></circle>
                        <circle cx="110" cy="28" r="6" fill="#f472b6"></circle>
                        <circle cx="102" cy="20" r="6" fill="#f472b6"></circle>
                        <circle cx="102" cy="36" r="6" fill="#f472b6"></circle>
                        <path d="M100 36c-5 5-8 10-9 16" fill="none" stroke="#16a34a" stroke-width="3" stroke-linecap="round"></path>
                    </g>
                `;
            case "pirate_patch":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--pirate-patch">
                        <path d="M26 56c16-8 35-9 58-3 14 3 26 4 40 1" fill="none" stroke="#111827" stroke-width="4" stroke-linecap="round"></path>
                        <ellipse cx="52" cy="64" rx="13" ry="11" fill="#111827"></ellipse>
                    </g>
                `;
            case "halo":
                return `
                    <g class="live-avatar__accessory live-avatar__accessory--halo">
                        <ellipse cx="70" cy="16" rx="30" ry="10" fill="none" stroke="#facc15" stroke-width="5"></ellipse>
                        <ellipse cx="70" cy="16" rx="22" ry="5" fill="none" stroke="#fde68a" stroke-width="2.5"></ellipse>
                    </g>
                `;
            default:
                return "";
        }
    }

    function renderSpecies(cfg) {
        const common = `
            <g class="live-avatar__ears">
                ${renderEars(cfg)}
            </g>
            ${renderBackFeatures(cfg)}
            <circle cx="70" cy="72" r="42" fill="${cfg.shell}" stroke="${cfg.outline}" stroke-width="4"></circle>
            ${renderFaceFeatures(cfg)}
        `;
        return common;
    }

    function renderEars(cfg) {
        switch (cfg.species) {
            case "rabbit":
                return `
                    <ellipse cx="42" cy="27" rx="12" ry="24" fill="${cfg.shellLight}" stroke="${cfg.outline}" stroke-width="4" transform="rotate(-12 42 27)"></ellipse>
                    <ellipse cx="98" cy="27" rx="12" ry="24" fill="${cfg.shellLight}" stroke="${cfg.outline}" stroke-width="4" transform="rotate(12 98 27)"></ellipse>
                    <ellipse cx="42" cy="28" rx="5" ry="16" fill="${cfg.shellAlt}" opacity="0.7" transform="rotate(-12 42 28)"></ellipse>
                    <ellipse cx="98" cy="28" rx="5" ry="16" fill="${cfg.shellAlt}" opacity="0.7" transform="rotate(12 98 28)"></ellipse>
                `;
            case "unicorn":
            case "fox":
            case "tiger":
                return `
                    <path d="M28 48L38 20l18 20z" fill="${cfg.shell}" stroke="${cfg.outline}" stroke-width="4" stroke-linejoin="round"></path>
                    <path d="M112 48L102 20 84 40z" fill="${cfg.shell}" stroke="${cfg.outline}" stroke-width="4" stroke-linejoin="round"></path>
                    <path d="M37 41l4-11 7 8z" fill="${cfg.shellLight}"></path>
                    <path d="M103 41l-4-11-7 8z" fill="${cfg.shellLight}"></path>
                `;
            case "frog":
                return `
                    <circle cx="42" cy="36" r="10" fill="${cfg.shellLight}" stroke="${cfg.outline}" stroke-width="4"></circle>
                    <circle cx="98" cy="36" r="10" fill="${cfg.shellLight}" stroke="${cfg.outline}" stroke-width="4"></circle>
                `;
            case "octopus":
                return "";
            default:
                return `
                    <circle cx="35" cy="38" r="14" fill="${cfg.shellAlt}" stroke="${cfg.outline}" stroke-width="4"></circle>
                    <circle cx="105" cy="38" r="14" fill="${cfg.shellAlt}" stroke="${cfg.outline}" stroke-width="4"></circle>
                    <circle cx="35" cy="38" r="7" fill="${cfg.shellLight}" opacity="0.85"></circle>
                    <circle cx="105" cy="38" r="7" fill="${cfg.shellLight}" opacity="0.85"></circle>
                `;
        }
    }

    function renderBackFeatures(cfg) {
        switch (cfg.species) {
            case "lion":
                return `<circle cx="70" cy="72" r="52" fill="${cfg.shellAlt}" opacity="0.95"></circle>`;
            case "octopus":
                return `
                    <path d="M26 84c2 18 12 28 20 28 9 0 8-11 16-11s7 11 16 11 7-11 15-11 7 11 16 11c8 0 18-10 20-28" fill="${cfg.shellAlt}" stroke="${cfg.outline}" stroke-width="4" stroke-linecap="round"></path>
                `;
            case "unicorn":
                return `
                    <path d="M86 20l10-18 10 18z" fill="#facc15" stroke="#b45309" stroke-width="3" stroke-linejoin="round"></path>
                    <path d="M48 30c4-10 10-18 18-21 4 7 7 15 8 23-9-3-17-4-26-2z" fill="${cfg.shellAlt}" opacity="0.8"></path>
                `;
            default:
                return "";
        }
    }

    function renderFaceFeatures(cfg) {
        const eyeFill = cfg.species === "frog" ? "#0f172a" : "#1f2937";
        const base = `
            <ellipse cx="52" cy="63" rx="11" ry="13" fill="#ffffff"></ellipse>
            <ellipse cx="88" cy="63" rx="11" ry="13" fill="#ffffff"></ellipse>
            <circle cx="52" cy="65" r="5.5" fill="${eyeFill}"></circle>
            <circle cx="88" cy="65" r="5.5" fill="${eyeFill}"></circle>
            <ellipse class="live-avatar__eyelid" cx="52" cy="58" rx="12" ry="0.5" fill="${cfg.shell}"></ellipse>
            <ellipse class="live-avatar__eyelid" cx="88" cy="58" rx="12" ry="0.5" fill="${cfg.shell}"></ellipse>
            <path d="M57 92c4 5 9 7 13 7s9-2 13-7" fill="none" stroke="${cfg.mouth}" stroke-width="4" stroke-linecap="round"></path>
        `;

        switch (cfg.species) {
            case "panda":
                return `
                    <ellipse cx="50" cy="64" rx="16" ry="18" fill="#111827" opacity="0.9"></ellipse>
                    <ellipse cx="90" cy="64" rx="16" ry="18" fill="#111827" opacity="0.9"></ellipse>
                    ${base}
                    <ellipse cx="70" cy="88" rx="20" ry="16" fill="${cfg.shellLight}" stroke="${cfg.outline}" stroke-width="4"></ellipse>
                    <ellipse cx="70" cy="84" rx="8" ry="6" fill="#111827"></ellipse>
                `;
            case "pig":
                return `
                    ${base}
                    <ellipse cx="70" cy="84" rx="18" ry="14" fill="${cfg.shellLight}" stroke="${cfg.outline}" stroke-width="4"></ellipse>
                    <circle cx="64" cy="84" r="3.5" fill="${cfg.accent}"></circle>
                    <circle cx="76" cy="84" r="3.5" fill="${cfg.accent}"></circle>
                `;
            case "frog":
                return `
                    <ellipse cx="52" cy="63" rx="11" ry="13" fill="#ffffff"></ellipse>
                    <ellipse cx="88" cy="63" rx="11" ry="13" fill="#ffffff"></ellipse>
                    <circle cx="52" cy="66" r="4.5" fill="#0f172a"></circle>
                    <circle cx="88" cy="66" r="4.5" fill="#0f172a"></circle>
                    <ellipse class="live-avatar__eyelid" cx="52" cy="59" rx="12" ry="0.5" fill="${cfg.shellLight}"></ellipse>
                    <ellipse class="live-avatar__eyelid" cx="88" cy="59" rx="12" ry="0.5" fill="${cfg.shellLight}"></ellipse>
                    <path d="M58 88c3 5 8 7 12 7 6 0 11-2 14-7" fill="none" stroke="${cfg.mouth}" stroke-width="4" stroke-linecap="round"></path>
                `;
            case "octopus":
                return `
                    ${base}
                    <path d="M54 84c3 4 7 6 16 6 8 0 12-2 16-6" fill="none" stroke="${cfg.mouth}" stroke-width="4" stroke-linecap="round"></path>
                    <circle cx="42" cy="92" r="3" fill="${cfg.shellLight}"></circle>
                    <circle cx="98" cy="92" r="3" fill="${cfg.shellLight}"></circle>
                `;
            case "fox":
            case "tiger":
            case "hamster":
            case "monkey":
            case "koala":
            case "rabbit":
            case "unicorn":
            case "lion":
            default:
                return `
                    ${renderSpecialMarkings(cfg)}
                    ${base}
                    <ellipse cx="70" cy="84" rx="19" ry="15" fill="${cfg.shellLight}" stroke="${cfg.outline}" stroke-width="4"></ellipse>
                    <ellipse cx="70" cy="80" rx="7.5" ry="5.5" fill="${cfg.accent}"></ellipse>
                    ${cfg.species === "hamster" ? '<circle cx="45" cy="84" r="7" fill="#fecaca"></circle><circle cx="95" cy="84" r="7" fill="#fecaca"></circle>' : ""}
                    ${cfg.species === "monkey" ? '<ellipse cx="70" cy="88" rx="24" ry="18" fill="#f5d0a9"></ellipse><ellipse cx="70" cy="80" rx="7.5" ry="5.5" fill="#4b2e15"></ellipse>' : ""}
                `;
        }
    }

    function renderSpecialMarkings(cfg) {
        switch (cfg.species) {
            case "lion":
                return `<path d="M58 40c4-8 10-12 12-12 5 0 10 5 14 13-9-4-17-4-26-1z" fill="${cfg.shellLight}" opacity="0.9"></path>`;
            case "tiger":
                return `
                    <path d="M51 40l-7 12" fill="none" stroke="${cfg.accent}" stroke-width="4" stroke-linecap="round"></path>
                    <path d="M89 40l7 12" fill="none" stroke="${cfg.accent}" stroke-width="4" stroke-linecap="round"></path>
                    <path d="M69 34l-4 10" fill="none" stroke="${cfg.accent}" stroke-width="4" stroke-linecap="round"></path>
                    <path d="M74 34l4 10" fill="none" stroke="${cfg.accent}" stroke-width="4" stroke-linecap="round"></path>
                `;
            case "fox":
                return `<path d="M48 42c8-8 17-11 22-11 7 0 14 3 22 11-15-4-29-4-44 0z" fill="${cfg.shellLight}" opacity="0.8"></path>`;
            case "koala":
                return `<ellipse cx="70" cy="82" rx="10" ry="8" fill="${cfg.accent}"></ellipse>`;
            default:
                return "";
        }
    }

    function renderSvg(profile) {
        const normalized = getProfile(profile);
        const cfg = catalog.avatars?.[normalized.avatarKey] || catalog.avatars?.avatar_1;
        const svg = `
            <svg viewBox="0 0 140 140" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
                <defs>
                    <filter id="liveAvatarShadow" x="-20%" y="-20%" width="140%" height="140%">
                        <feDropShadow dx="0" dy="6" stdDeviation="6" flood-color="rgba(15,23,42,0.18)"></feDropShadow>
                    </filter>
                </defs>
                <g filter="url(#liveAvatarShadow)">
                    ${renderSpecies.call({ accessoryKey: normalized.accessoryKey }, cfg)}
                    ${renderAccessory(normalized.accessoryKey)}
                </g>
            </svg>
        `;
        return {
            markup: svg,
            config: cfg,
            profile: normalized
        };
    }

    function renderAvatarMarkup(profile, options) {
        const opts = options || {};
        const rendered = renderSvg(profile);
        const size = Number(opts.size) > 0 ? Number(opts.size) : 72;
        const label = esc(opts.label || catalog.avatars?.[rendered.profile.avatarKey]?.label || "Avatar");
        const className = opts.className ? ` ${opts.className}` : "";
        const interactive = opts.interactive === false ? " is-static" : "";
        const style = [
            `--live-avatar-size:${size}px`,
            `--live-avatar-bg-start:${rendered.config.bgStart}`,
            `--live-avatar-bg-end:${rendered.config.bgEnd}`,
            `--live-avatar-shell:${rendered.config.shell}`
        ].join(";");

        return `
            <span class="live-avatar${className}${interactive}" style="${style}" aria-label="${label}" role="img">
                <span class="live-avatar__backdrop"></span>
                ${rendered.markup}
            </span>
        `;
    }

    function renderAvatarDataUrl(profile) {
        const rendered = renderSvg(profile);
        const svg = `
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 140 140" aria-hidden="true" focusable="false">
                <defs>
                    <linearGradient id="avatarBg" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="${rendered.config.bgStart}"></stop>
                        <stop offset="100%" stop-color="${rendered.config.bgEnd}"></stop>
                    </linearGradient>
                    <radialGradient id="avatarGlow" cx="30%" cy="24%" r="56%">
                        <stop offset="0%" stop-color="#ffffff" stop-opacity="0.92"></stop>
                        <stop offset="0.34" stop-color="#ffffff" stop-opacity="0.38"></stop>
                        <stop offset="0.68" stop-color="#ffffff" stop-opacity="0"></stop>
                    </radialGradient>
                </defs>
                <rect width="140" height="140" rx="40" fill="url(#avatarBg)"></rect>
                <rect width="140" height="140" rx="40" fill="url(#avatarGlow)"></rect>
                ${rendered.markup}
            </svg>
        `.replace(/\s{2,}/g, " ").trim();

        return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
    }

    function mountAvatar(element, profile, options) {
        if (!element) return;
        element.innerHTML = renderAvatarMarkup(profile, options);
    }

    window.LiveAvatarRenderer = {
        getProfile,
        renderAvatarDataUrl,
        renderAvatarMarkup,
        mountAvatar
    };
})();

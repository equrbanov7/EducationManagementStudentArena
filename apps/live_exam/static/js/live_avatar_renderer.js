/* live_avatar_renderer.js — canlı oyun avatarlarının SVG rəssamı (2026-09-29 LX-FE-STAGE).
 *
 * İCTİMAİ API (geri uyğun — oyunçu/gözləmə səhifələri çağırır):
 *   LiveAvatarRenderer.getProfile(profile)               → {avatarKey, accessoryKey}
 *   LiveAvatarRenderer.renderAvatarMarkup(profile, opts) → <span class="live-avatar">…</span>
 *   LiveAvatarRenderer.renderAvatarDataUrl(profile, opts)→ "data:image/svg+xml,…" (siyahılar üçün)
 *   LiveAvatarRenderer.mountAvatar(el, profile, opts)
 * YENİ:
 *   renderAvatarSvg(profile, opts)   → yalnız <svg class="lva">…</svg>
 *   renderAccessoryIcon(key, size)   → aksesuarın kiçik SVG ikonu (seçici çipləri üçün)
 *   setDance(el, name) / DANCES      → rəqs API-si (bax live_avatar.css)
 *
 * opts: size (px, 72), className, interactive (false → .is-static), label,
 *       crop ("auto" | "full" | "portrait"; auto: size < 96 → portrait),
 *       backdrop (true), dance ("bounce|sway|spin|jump|wave|cheer|idle").
 *
 * CSS QARMAQLARI (sabit): .lva-rig .lva-shadow .lva-tail .lva-body .lva-feet
 *   .lva-arm(--l/--r) .lva-paw .lva-head .lva-ear(--l/--r) .lva-eyes .lva-eye
 *   .lva-mouth .lva-accessory(--<key>) .lva-sparkle
 * SVG-də id YOXDUR (bir səhifədə çoxlu inline SVG toqquşmasın); fon qradiyenti
 * yalnız data-URL variantındadır.
 */
(function () {
    const catalog = window.LiveAvatarCatalog || {};
    const DANCES = ["bounce", "sway", "spin", "jump", "wave", "cheer", "idle"];

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function getProfile(profile) {
        const avatarKey = profile?.avatar_key || profile?.avatarKey || catalog.defaultAvatarKey || "avatar_1";
        const accessoryKey =
            profile?.accessory_key || profile?.accessoryKey || catalog.defaultAccessoryKey || "accessory_none";
        return {
            avatarKey: catalog.avatars?.[avatarKey] ? avatarKey : catalog.defaultAvatarKey || "avatar_1",
            accessoryKey: catalog.accessories?.[accessoryKey]
                ? accessoryKey
                : catalog.defaultAccessoryKey || "accessory_none",
        };
    }

    /* ── Köməkçilər ─────────────────────────────────────────────────── */
    const sw = (line, w) => `stroke="${line}" stroke-width="${w || 3}" stroke-linejoin="round" stroke-linecap="round"`;
    const mirror = (inner) => `<g transform="matrix(-1 0 0 1 140 0)">${inner}</g>`;
    const pair = (cls, inner) =>
        `<g class="${cls} ${cls}--l">${inner}</g><g class="${cls} ${cls}--r">${mirror(inner)}</g>`;
    // Qalın (kontur + rəng) iki qatlı xətt — əl-qol, quyruq, çıxıntılar üçün.
    const limb = (d, color, line, w) =>
        `<path d="${d}" fill="none" stroke="${line}" stroke-width="${w + 5.5}" stroke-linecap="round" stroke-linejoin="round"/>` +
        `<path d="${d}" fill="none" stroke="${color}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/>`;

    const DEFAULT_ANCHOR = { eyeL: [56, 58], eyeR: [84, 58], top: 24.5, eyeKind: "dot", eyeScale: 1 };

    function eyeMarkup(x, y, kind, scale) {
        const s = scale || 1;
        if (kind === "panda") {
            return `<g class="lva-eye"><circle cx="${x}" cy="${y}" r="${4.7 * s}" fill="#fff"/><circle cx="${x + 0.8}" cy="${y + 0.4}" r="${2.8 * s}" fill="#1b1d29"/><circle cx="${x + 1.7}" cy="${y - 0.9}" r="1" fill="#fff"/></g>`;
        }
        if (kind === "frog") {
            return `<g class="lva-eye"><circle cx="${x}" cy="${y}" r="8.2" fill="#fff"/><circle cx="${x + 1}" cy="${y + 1}" r="4.6" fill="#1b1d29"/><circle cx="${x + 2.6}" cy="${y - 0.9}" r="1.7" fill="#fff"/></g>`;
        }
        return `<g class="lva-eye"><ellipse cx="${x}" cy="${y}" rx="${5.3 * s}" ry="${6.5 * s}" fill="#1b1d29"/><circle cx="${x + 1.9 * s}" cy="${y - 2.5 * s}" r="${2.1 * s}" fill="#fff"/><circle cx="${x - 1.6 * s}" cy="${y + 2.8 * s}" r="${1 * s}" fill="#fff" opacity=".7"/></g>`;
    }

    function eyes(a) {
        return `<g class="lva-eyes">${eyeMarkup(a.eyeL[0], a.eyeL[1], a.eyeKind, a.eyeScale)}${eyeMarkup(a.eyeR[0], a.eyeR[1], a.eyeKind, a.eyeScale)}</g>`;
    }

    const cheeks = (color, y, dx) =>
        `<ellipse cx="${70 - (dx || 25)}" cy="${y || 70}" rx="6.2" ry="3.8" fill="${color || "#ff8fab"}" opacity=".55"/>` +
        `<ellipse cx="${70 + (dx || 25)}" cy="${y || 70}" rx="6.2" ry="3.8" fill="${color || "#ff8fab"}" opacity=".55"/>`;
    const nose = (color, y) =>
        `<path d="M65.5 ${(y || 66.4)} Q70 ${(y || 66.4) - 2.8} 74.5 ${(y || 66.4)} Q73.4 ${(y || 66.4) + 4.2} 70 ${(y || 66.4) + 5} Q66.6 ${(y || 66.4) + 4.2} 65.5 ${(y || 66.4)}Z" fill="${color}"/>`;
    const mouthW = (line, y) => {
        const b = y || 73.5;
        return `<path class="lva-mouth" d="M63.5 ${b} Q66.8 ${b + 4} 70 ${b + 0.3} Q73.2 ${b + 4} 76.5 ${b}" fill="none" ${sw(line, 2.4)}/>`;
    };
    const whiskers = (line) =>
        `<path d="M43 67 L31 65 M43 71 L31 73 M97 67 L109 65 M97 71 L109 73" fill="none" stroke="${line}" stroke-width="1.4" stroke-linecap="round" opacity=".45"/>`;
    const headEllipse = (p, rx, ry, cy) =>
        `<ellipse cx="70" cy="${cy || 57}" rx="${rx || 36}" ry="${ry || 32.5}" fill="${p.main}" ${sw(p.line)}/>`;

    /* ── Növlər (species) ───────────────────────────────────────────── */
    const TAIL_BUSHY = "M86 121 C104 124 118 114 121 98 C123 88 119 79 112 74 C113 86 109 96 100 102 C95 106 90 108 86 108 Z";

    const SPECIES = {
        fox(p) {
            return {
                ears: pair("lva-ear", `<path d="M41 45 C38 31 37 20 39 11 C40.5 8.5 43 8.5 45 10.5 C52 18 58 26 62 33 Z" fill="${p.main}" ${sw(p.line)}/><path d="M43.8 38 C42.4 30 42 23 42.8 17 C47.6 22 51.6 27 55 32 Z" fill="${p.inner}"/><path d="M39.2 18 L39.8 11 Q42 8.4 45 10.5 L49.4 15.4 Q44 15.2 39.2 18Z" fill="${p.extra}"/>`),
                head: `<path d="M34.5 56 C34.5 36 50 25 70 25 C90 25 105.5 36 105.5 56 C105.5 63 107 69 113 75 C104 77 98 80 93 85 C86 90 78 91.5 70 91.5 C62 91.5 54 90 47 85 C42 80 36 77 27 75 C33 69 34.5 63 34.5 56 Z" fill="${p.main}" ${sw(p.line)}/><path d="M70 58 C63 58 58 61 54 66 C49 72 41 74.5 31 75.5 C38 78 44 81 48.5 85.5 C55 90 62.5 91.5 70 91.5 C77.5 91.5 85 90 91.5 85.5 C96 81 102 78 109 75.5 C99 74.5 91 72 86 66 C82 61 77 58 70 58 Z" fill="${p.light}"/>`,
                face: (a) => eyes(a) + cheeks() + nose(p.nose, 66) + mouthW(p.line),
                tail: `<path d="${TAIL_BUSHY}" fill="${p.main}" ${sw(p.line)}/><path d="M112 74 C119 79 123 88 121 98 C117 93 113 89.5 109.5 87.5 C111.5 83 112.5 78.5 112 74 Z" fill="${p.light}"/>`,
                body: { paw: p.dark, foot: p.extra },
            };
        },
        wolf(p) {
            return {
                ears: pair("lva-ear", `<path d="M40 46 C37 34 37 22 40 13 C41.5 10.5 44 10.5 46 12.5 C53 20 59 28 63 35 Z" fill="${p.main}" ${sw(p.line)}/><path d="M43 39 C41.8 32 41.6 25 42.6 19 C47.6 24 51.6 29 55 34 Z" fill="${p.inner}"/>`),
                head: `<path d="M34.5 55 C34.5 36 50 25 70 25 C90 25 105.5 36 105.5 55 C105.5 62 108 67 114 70 C108 73 106 75 109 79 C102 80 98 83 94 86 C87 90.5 78.5 92 70 92 C61.5 92 53 90.5 46 86 C42 83 38 80 31 79 C34 75 32 73 26 70 C32 67 34.5 62 34.5 55 Z" fill="${p.main}" ${sw(p.line)}/><path d="M70 26.5 C66 34 65 42 70 50 C75 42 74 34 70 26.5 Z" fill="${p.extra}" opacity=".55"/><path d="M70 60 C62 60 57 63 53.5 68 C49 74 43 77 35 78.5 C41 80.5 45 83 48.5 86.5 C55 90.5 62.5 92 70 92 C77.5 92 85 90.5 91.5 86.5 C95 83 99 80.5 105 78.5 C97 77 91 74 86.5 68 C83 63 78 60 70 60 Z" fill="${p.light}"/><ellipse cx="53" cy="46.5" rx="5.4" ry="3" fill="${p.light}"/><ellipse cx="87" cy="46.5" rx="5.4" ry="3" fill="${p.light}"/>`,
                face: (a) => eyes(a) + nose(p.nose, 66) + mouthW(p.line),
                tail: `<path d="M86 122 C102 128 118 122 122 106 C124 97 121 88 115 83 C115 94 110 102 101 107 C96 110 91 111 86 111 Z" fill="${p.main}" ${sw(p.line)}/><path d="M115 83 C121 88 124 97 122 106 C118 100 114 96 110 94 C113 91 115 87 115 83 Z" fill="${p.light}"/>`,
                body: { foot: p.dark, paw: p.dark },
            };
        },
        panda(p) {
            return {
                ears: pair("lva-ear", `<circle cx="41" cy="31" r="11.5" fill="${p.dark}" ${sw(p.line)}/><circle cx="41.5" cy="31.5" r="5.5" fill="${p.inner}"/>`),
                head: headEllipse(p) + `<ellipse cx="54" cy="59" rx="10" ry="12.5" transform="rotate(28 54 59)" fill="${p.dark}"/><ellipse cx="86" cy="59" rx="10" ry="12.5" transform="rotate(-28 86 59)" fill="${p.dark}"/><ellipse cx="70" cy="74" rx="13" ry="9.5" fill="${p.light}"/>`,
                face: (a) => eyes(a) + cheeks("#ff9db5", 72, 27) + nose(p.nose, 67) + mouthW(p.line, 74.5),
                anchor: { eyeL: [56, 58.5], eyeR: [84, 58.5], eyeKind: "panda" },
                body: { torso: p.main, belly: p.light, limb: p.dark, paw: p.dark, foot: p.dark },
            };
        },
        lion(p) {
            let mane = "";
            for (let i = 0; i < 14; i += 1) {
                const ang = (i / 14) * Math.PI * 2;
                mane += `<circle cx="${(70 + 38 * Math.cos(ang)).toFixed(1)}" cy="${(58 + 35 * Math.sin(ang)).toFixed(1)}" r="13" fill="${p.extra}" ${sw(p.line)}/>`;
            }
            return {
                back: `<g class="lva-mane">${mane}<circle cx="70" cy="58" r="37" fill="${p.extra}"/><circle cx="70" cy="58" r="33" fill="${p.inner}" opacity=".55"/></g>`,
                ears: pair("lva-ear", `<circle cx="45" cy="33" r="7.5" fill="${p.main}" ${sw(p.line)}/><circle cx="45" cy="33.5" r="3.6" fill="${p.dark}"/>`),
                head: headEllipse(p, 30, 28, 60) + `<path d="M60 36 C64 31 67 30 70 30 C73 30 76 31 80 36 C76 34.5 73 34 70 34 C67 34 64 34.5 60 36Z" fill="${p.light}"/><ellipse cx="70" cy="73" rx="13" ry="9.5" fill="${p.light}"/>`,
                face: (a) => eyes(a) + cheeks("#ff9d7a", 69, 20) + nose(p.nose, 67) + mouthW(p.line, 74.5),
                anchor: { eyeL: [58, 57], eyeR: [82, 57], top: 21, eyeScale: 0.92 },
                tail: limb("M88 120 C102 125 112 118 114 105", p.main, p.line, 4.5) + `<circle cx="114.5" cy="102" r="7" fill="${p.extra}" ${sw(p.line)}/>`,
                body: { paw: p.light },
            };
        },
        tiger(p) {
            const k = p.extra;
            return {
                ears: pair("lva-ear", `<circle cx="42" cy="31" r="10.5" fill="${p.main}" ${sw(p.line)}/><circle cx="42" cy="31.5" r="5.2" fill="${p.inner}"/>`),
                head: headEllipse(p) + `<ellipse cx="51" cy="75" rx="14" ry="10" fill="${p.light}"/><ellipse cx="89" cy="75" rx="14" ry="10" fill="${p.light}"/><ellipse cx="70" cy="74" rx="12" ry="10" fill="${p.light}"/><path d="M70 25.5 L70 37 M61 27 L63.5 36 M79 27 L76.5 36 M35.5 54 L45 56.5 M36 62.5 L45.5 62.5 M104.5 54 L95 56.5 M104 62.5 L94.5 62.5" fill="none" stroke="${k}" stroke-width="3.6" stroke-linecap="round"/>`,
                face: (a) => eyes(a) + nose(p.nose, 66.5) + mouthW(p.line, 74),
                tail: limb("M88 122 C104 126 114 116 118 100", p.main, p.line, 7) + `<path d="M104 122 L106 115 M113 113 L117 108" stroke="${k}" stroke-width="3" stroke-linecap="round"/>`,
                body: { stripes: k },
            };
        },
        koala(p) {
            return {
                ears: pair("lva-ear", `<circle cx="36" cy="41" r="17" fill="${p.main}" ${sw(p.line)}/><circle cx="37.5" cy="42" r="10" fill="${p.inner}"/><path d="M24 34 L28 36 M22 43 L27 43 M25 51 L29 49" stroke="${p.light}" stroke-width="2" stroke-linecap="round"/>`),
                head: headEllipse(p, 34, 31, 58) + `<ellipse cx="70" cy="77" rx="20" ry="11.5" fill="${p.light}"/>`,
                face: (a) => eyes(a) + cheeks("#f9a8c8", 71, 24) + `<ellipse cx="70" cy="67" rx="8" ry="10.5" fill="${p.nose}"/><ellipse cx="67.5" cy="62.5" rx="2.2" ry="3" fill="#fff" opacity=".35"/><path class="lva-mouth" d="M65 81 Q70 84.5 75 81" fill="none" ${sw(p.line, 2.4)}/>`,
                anchor: { eyeL: [54, 56], eyeR: [86, 56], eyeScale: 0.88 },
                body: { paw: p.dark, foot: p.dark },
            };
        },
        pig(p) {
            return {
                ears: pair("lva-ear", `<path d="M41 42 C36 32 36 21 40 13 C49 17 57 24 61 32 Z" fill="${p.main}" ${sw(p.line)}/><path d="M43.5 36 C41 30 41 23 43 18 C48 21 52 25 55 30 Z" fill="${p.inner}"/>`),
                head: headEllipse(p),
                face: (a) => eyes(a) + cheeks("#ff6f98", 70, 26) + `<ellipse cx="70" cy="70" rx="13" ry="9.5" fill="${p.extra}" ${sw(p.line, 2.6)}/><ellipse cx="65.4" cy="70" rx="2.4" ry="3.4" fill="${p.nose}"/><ellipse cx="74.6" cy="70" rx="2.4" ry="3.4" fill="${p.nose}"/><path class="lva-mouth" d="M64 82.5 Q70 86.5 76 82.5" fill="none" ${sw(p.line, 2.4)}/>`,
                anchor: { eyeL: [55, 54], eyeR: [85, 54] },
                tail: `<path d="M92 118 C101 119 103 110 98 108 C93 106 91 112 95 114 C101 117 107 110 105 103" fill="none" stroke="${p.line}" stroke-width="6.5" stroke-linecap="round"/><path d="M92 118 C101 119 103 110 98 108 C93 106 91 112 95 114 C101 117 107 110 105 103" fill="none" stroke="${p.main}" stroke-width="3" stroke-linecap="round"/>`,
                body: { foot: p.dark, paw: p.dark },
            };
        },
        frog(p) {
            return {
                head: `<path d="M28 66 C28 52 34 45 40 42 C37 30 45 23.5 52 24.5 C58 25.5 62 31 62 38 L78 38 C78 31 82 25.5 88 24.5 C95 23.5 103 30 100 42 C106 45 112 52 112 66 C112 82 94 91 70 91 C46 91 28 82 28 66 Z" fill="${p.main}" ${sw(p.line)}/><path d="M36 74 C44 86 56 90.5 70 90.5 C84 90.5 96 86 104 74 C94 80 82 82 70 82 C58 82 46 80 36 74 Z" fill="${p.light}"/>`,
                face: (a) => eyes(a) + cheeks(p.extra, 69, 30) + `<circle cx="66" cy="58" r="1.6" fill="${p.line}"/><circle cx="74" cy="58" r="1.6" fill="${p.line}"/><path class="lva-mouth" d="M47 68 Q70 84 93 68" fill="none" ${sw(p.line, 3)}/>`,
                anchor: { eyeL: [51, 35], eyeR: [89, 35], eyeKind: "frog", top: 23 },
                body: { foot: p.dark, paw: p.light },
            };
        },
        octopus(p) {
            const t = (d) => limb(d, p.main, p.line, 7.5);
            return {
                head: `<path d="M33 70 C31 40 47 21 70 21 C93 21 109 40 107 70 C106 84 92 91 70 91 C48 91 34 84 33 70 Z" fill="${p.main}" ${sw(p.line)}/><circle cx="52" cy="35" r="4" fill="${p.inner}"/><circle cx="89" cy="33" r="5" fill="${p.inner}"/><circle cx="97" cy="49" r="3.4" fill="${p.inner}"/><circle cx="43" cy="49" r="3" fill="${p.inner}"/>`,
                face: (a) => eyes(a) + cheeks(p.extra, 72, 24) + `<ellipse class="lva-mouth" cx="70" cy="77" rx="3.4" ry="4" fill="${p.line}"/>`,
                anchor: { eyeL: [56, 60], eyeR: [84, 60], top: 21 },
                torso: `<g class="lva-body">${t("M52 86 C48 100 40 108 44 120 C46 126 53 127 53 120")}${t("M63 89 C61 104 59 116 63 127")}${t("M77 89 C79 104 81 116 77 127")}${t("M88 86 C92 100 100 108 96 120 C94 126 87 127 87 120")}<circle cx="62.5" cy="112" r="1.6" fill="${p.light}"/><circle cx="78" cy="112" r="1.6" fill="${p.light}"/><circle cx="62.8" cy="120" r="1.6" fill="${p.light}"/><circle cx="77.8" cy="120" r="1.6" fill="${p.light}"/></g>`,
                arms: [
                    `<g transform="translate(43 86)"><g class="lva-arm lva-arm--l">${t("M0 0 C-9 6 -13 15 -10 24")}</g></g>`,
                    `<g transform="translate(97 86)"><g class="lva-arm lva-arm--r">${t("M0 0 C9 6 13 15 10 24")}</g></g>`,
                ],
            };
        },
        monkey(p) {
            return {
                ears: pair("lva-ear", `<circle cx="31" cy="58" r="12.5" fill="${p.main}" ${sw(p.line)}/><circle cx="32" cy="58" r="7" fill="${p.inner}"/>`),
                head: headEllipse(p, 35, 32) + `<path d="M64 27 C65 20 70 18 71.5 23 C73.5 18 79 20 76 27" fill="${p.main}" ${sw(p.line, 2.4)}/><path d="M70 42 C64 35 53 35 49 43 C45 50 46 57 49 61 C44 67 45 79 53 85 C60 90 80 90 87 85 C95 79 96 67 91 61 C94 57 95 50 91 43 C87 35 76 35 70 42 Z" fill="${p.light}"/>`,
                face: (a) => eyes(a) + cheeks("#f59e8b", 71, 20) + `<circle cx="67" cy="68" r="1.8" fill="${p.nose}"/><circle cx="73" cy="68" r="1.8" fill="${p.nose}"/><path class="lva-mouth" d="M60 75 Q70 83 80 75" fill="none" ${sw(p.line, 2.6)}/>`,
                anchor: { eyeL: [58, 55], eyeR: [82, 55], eyeScale: 0.92 },
                tail: `<path d="M90 118 C110 120 120 108 116 96 C113 88 104 90 106 97 C107 101 111 101 112 98" fill="none" stroke="${p.line}" stroke-width="9.5" stroke-linecap="round"/><path d="M90 118 C110 120 120 108 116 96 C113 88 104 90 106 97 C107 101 111 101 112 98" fill="none" stroke="${p.main}" stroke-width="4.5" stroke-linecap="round"/>`,
                body: { paw: p.light, foot: p.light, belly: p.light },
            };
        },
        unicorn(p) {
            const m1 = "#7dd8ff";
            const m2 = "#b794ff";
            const m3 = "#ff8fc7";
            return {
                back: `<path d="M50 28 C34 32 25 50 28 72 C33 66 36 60 38 54 C38 66 41 76 47 82 C46 66 50 50 58 38 Z" fill="${m1}" ${sw(p.line)}/><path d="M58 24 C44 26 36 40 36 56 C40 50 44 46 48 44 C46 54 48 64 53 70 C54 56 58 44 66 34 Z" fill="${m2}" ${sw(p.line)}/>`,
                ears: `<g class="lva-ear lva-ear--r"><path d="M84 36 L91 13 L101 34 Z" fill="${p.main}" ${sw(p.line)}/><path d="M88 32 L91.5 20 L96.5 31 Z" fill="${m3}"/></g>`,
                head: headEllipse(p) + `<path d="M64 27 L70 2 L76 27 Z" fill="${p.inner}" ${sw(p.extra, 2.6)}/><path d="M65.6 21 L74.6 18.6 M67 14 L73.4 12.3 M68.4 7.8 L72.2 6.8" stroke="${p.extra}" stroke-width="2" stroke-linecap="round"/><path d="M54 27 C60 20 73 18 82 24 C75 26 71 30 69 38 C65 32 60 30 55 35 Z" fill="${m3}" ${sw(p.line, 2.6)}/><ellipse cx="70" cy="75.5" rx="15" ry="10" fill="${p.light}" ${sw(p.dark, 2)}/>`,
                face: (a) => eyes(a) + `<path d="M49.5 53 L46 49.5 M90.5 53 L94 49.5" stroke="#1b1d29" stroke-width="2" stroke-linecap="round"/>` + cheeks("#ff9ccb", 68, 27) + `<ellipse cx="65" cy="74" rx="1.9" ry="1.5" fill="${p.nose}"/><ellipse cx="75" cy="74" rx="1.9" ry="1.5" fill="${p.nose}"/><path class="lva-mouth" d="M65 80 Q70 83.5 75 80" fill="none" ${sw(p.line, 2.2)}/>`,
                tail: limb("M88 118 C104 120 112 108 117 96", m3, p.line, 5) + `<path d="M91 121 C106 124 116 112 121 100" fill="none" stroke="${m2}" stroke-width="4" stroke-linecap="round"/><path d="M85 116 C99 116 107 105 112 94" fill="none" stroke="${m1}" stroke-width="4" stroke-linecap="round"/>`,
                body: { foot: p.dark, paw: p.dark },
            };
        },
        rabbit(p) {
            return {
                ears: pair("lva-ear", `<ellipse cx="54" cy="24" rx="9.5" ry="21" transform="rotate(-10 54 24)" fill="${p.main}" ${sw(p.line)}/><ellipse cx="54" cy="25.5" rx="4.6" ry="15" transform="rotate(-10 54 25.5)" fill="${p.inner}"/>`),
                head: headEllipse(p),
                face: (a) => eyes(a) + cheeks() + whiskers(p.line) + nose(p.nose, 65.5) + mouthW(p.line, 72.5) + `<rect x="66.2" y="74.6" width="3.6" height="5" rx="1" fill="#fff" ${sw(p.line, 1.3)}/><rect x="70.2" y="74.6" width="3.6" height="5" rx="1" fill="#fff" ${sw(p.line, 1.3)}/>`,
                tail: `<circle cx="96" cy="121" r="8" fill="${p.light}" ${sw(p.line)}/>`,
                body: { foot: p.dark },
            };
        },
        lop_rabbit(p) {
            return {
                ears: pair("lva-ear", `<path d="M45 34 C31 38 24 56 26 76 C27 84 34 86 37 80 C40 66 44 52 53 40 Z" fill="${p.main}" ${sw(p.line)}/><path d="M44.5 40.5 C35 45 30.5 58 31.5 73 C33 77 35 77 36 73.5 C38.5 62 41.5 52 47.5 44.5 Z" fill="${p.inner}"/>`),
                head: headEllipse(p) + `<path d="M64 26 C66 19.5 70 18.5 71.2 23.5 C73.2 18.5 78.4 20.5 76 27" fill="${p.main}" ${sw(p.line, 2.4)}/>`,
                face: (a) => eyes(a) + cheeks("#ff9fb8") + whiskers(p.line) + nose(p.nose, 65.5) + mouthW(p.line, 72.5) + `<rect x="68.2" y="74.6" width="3.6" height="4.6" rx="1" fill="#fff" ${sw(p.line, 1.3)}/>`,
                tail: `<circle cx="96" cy="121" r="8" fill="${p.light}" ${sw(p.line)}/>`,
                body: { foot: p.dark },
            };
        },
        hamster(p) {
            return {
                ears: pair("lva-ear", `<circle cx="45" cy="30" r="8.5" fill="${p.main}" ${sw(p.line)}/><circle cx="45" cy="30.5" r="4.3" fill="${p.inner}"/>`),
                head: `<path d="M32 62 C32 38 48 26 70 26 C92 26 108 38 108 62 C108 80 92 91 70 91 C48 91 32 80 32 62 Z" fill="${p.main}" ${sw(p.line)}/><path d="M33.5 66 C38 84 52 90.5 70 90.5 C88 90.5 102 84 106.5 66 C100 72 90 74 82 72 C78 68 74 66 70 66 C66 66 62 68 58 72 C50 74 40 72 33.5 66 Z" fill="${p.light}"/><path d="M70 27.5 C66.5 32 66.5 40 70 44 C73.5 40 73.5 32 70 27.5 Z" fill="${p.dark}" opacity=".35"/>`,
                face: (a) => eyes(a) + `<ellipse cx="44" cy="72" rx="8" ry="5" fill="${p.extra}" opacity=".55"/><ellipse cx="96" cy="72" rx="8" ry="5" fill="${p.extra}" opacity=".55"/>` + whiskers(p.line) + nose(p.nose, 65) + mouthW(p.line, 72),
                anchor: { eyeL: [55, 55], eyeR: [85, 55], top: 26 },
                body: { foot: p.dark, paw: p.inner },
            };
        },
        polar_bear(p) {
            return {
                ears: pair("lva-ear", `<circle cx="43" cy="31" r="9.5" fill="${p.main}" ${sw(p.line)}/><circle cx="43" cy="31.5" r="4.6" fill="${p.inner}"/>`),
                head: headEllipse(p) + `<path d="M35.5 64 C40 82 54 89 70 89 C86 89 100 82 104.5 64 C96 73 86 77 70 77 C54 77 44 73 35.5 64 Z" fill="${p.dark}" opacity=".5"/><ellipse cx="70" cy="72" rx="15" ry="11" fill="${p.light}" ${sw(p.line, 2.4)}/>`,
                face: (a) => eyes(a) + cheeks("#ffb3c6", 69, 26) + `<ellipse cx="70" cy="67.5" rx="6" ry="4.4" fill="${p.nose}"/><ellipse cx="68.4" cy="66.4" rx="1.8" ry="1.1" fill="#fff" opacity=".5"/>` + mouthW(p.line, 74.5),
                anchor: { eyeL: [55, 56], eyeR: [85, 56] },
                tail: `<circle cx="96" cy="122" r="6" fill="${p.main}" ${sw(p.line)}/>`,
                body: { foot: p.dark, paw: p.main },
            };
        },
        red_panda(p) {
            return {
                ears: pair("lva-ear", `<path d="M38 44 C34 32 36 20 42 16 C50 18 58 26 60 34 Z" fill="${p.main}" ${sw(p.line)}/><path d="M41 39 C39 31 40 24 44 21 C49 23 54 28 55 33 Z" fill="${p.inner}"/>`),
                head: headEllipse(p) + `<ellipse cx="54" cy="44.5" rx="6" ry="4" fill="${p.light}"/><ellipse cx="86" cy="44.5" rx="6" ry="4" fill="${p.light}"/><path d="M35.5 60 C35.5 76 46 88 60 90 C54 82 50 72 50 64 Z" fill="${p.light}"/><path d="M104.5 60 C104.5 76 94 88 80 90 C86 82 90 72 90 64 Z" fill="${p.light}"/><ellipse cx="70" cy="74" rx="13" ry="10" fill="${p.light}"/><path d="M53 65 C51.5 72 49.5 78 45.5 84 M87 65 C88.5 72 90.5 78 94.5 84" fill="none" stroke="${p.extra}" stroke-width="4.5" stroke-linecap="round"/>`,
                face: (a) => eyes(a) + nose(p.nose, 67) + mouthW(p.line, 74.5),
                tail: `<path d="M86 120 C102 126 116 118 120 102 C122 94 120 86 114 82 C114 94 108 104 98 108 C94 110 90 110 86 110 Z" fill="${p.main}" ${sw(p.line)}/><path d="M103 116.5 C107 112.5 109.5 108.5 110.5 104 M115.5 100 C117.5 96 118 92 117 88" fill="none" stroke="${p.extra}" stroke-width="5" stroke-linecap="round"/>`,
                body: { belly: p.dark, limb: p.dark, paw: p.dark, foot: p.dark },
            };
        },
    };

    /* ── Bədən (bütün növlər üçün ortaq skelet) ─────────────────────── */
    function bodyParts(p, o) {
        const torso = o.torso || p.main;
        const belly = o.belly || p.light;
        const arm = o.limb || p.main;
        const paw = o.paw || arm;
        const foot = o.foot || p.dark;
        const stripes = o.stripes
            ? `<path d="M52 104 L57 106 M88 104 L83 106 M50 113 L56 114 M90 113 L84 114" stroke="${o.stripes}" stroke-width="3" stroke-linecap="round"/>`
            : "";
        const armL = `<g transform="translate(53 97)"><g class="lva-arm lva-arm--l">${limb("M0 0 Q-9 7 -10.5 18.5", arm, p.line, 6.5)}<circle class="lva-paw" cx="-10.5" cy="19.5" r="5.6" fill="${paw}" ${sw(p.line, 2.6)}/></g></g>`;
        const armR = `<g transform="translate(87 97)"><g class="lva-arm lva-arm--r">${limb("M0 0 Q9 7 10.5 18.5", arm, p.line, 6.5)}<circle class="lva-paw" cx="10.5" cy="19.5" r="5.6" fill="${paw}" ${sw(p.line, 2.6)}/></g></g>`;
        return {
            feet: `<g class="lva-feet"><ellipse cx="58.5" cy="130.5" rx="9.5" ry="5.8" fill="${foot}" ${sw(p.line)}/><ellipse cx="81.5" cy="130.5" rx="9.5" ry="5.8" fill="${foot}" ${sw(p.line)}/></g>`,
            torso: `<g class="lva-body"><path d="M50 100 C50 91 58 86 70 86 C82 86 90 91 90 100 L93 118 C94 127 86 131.5 70 131.5 C54 131.5 46 127 47 118 Z" fill="${torso}" ${sw(p.line)}/><ellipse cx="70" cy="114" rx="13.5" ry="12" fill="${belly}"/>${stripes}</g>`,
            arms: [armL, armR],
        };
    }

    /* ── Aksesuarlar ───────────────────────────────────────────────── */
    function accessoryMarkup(key, a) {
        const dy = (a.top || 24.5) - 24.5;
        const [lx, ly] = a.eyeL;
        const [rx, ry] = a.eyeR;
        const wrap = (inner, extra) => `<g class="lva-accessory lva-accessory--${key}"${extra || ""}>${inner}</g>`;
        switch (key) {
            case "glasses":
                return wrap(`<g fill="rgba(186,230,253,.35)" stroke="#111827" stroke-width="3.2" stroke-linejoin="round"><circle cx="${lx}" cy="${ly}" r="10.5"/><circle cx="${rx}" cy="${ry}" r="10.5"/></g><path d="M${lx + 10.5} ${ly - 1} Q70 ${ly - 5} ${rx - 10.5} ${ry - 1} M${lx - 10.5} ${ly - 2} L34 ${ly - 6} M${rx + 10.5} ${ry - 2} L106 ${ry - 6}" fill="none" stroke="#111827" stroke-width="3.2" stroke-linecap="round"/><path d="M${lx - 5} ${ly - 5} l4 -2 M${rx - 5} ${ry - 5} l4 -2" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".8"/>`);
            case "cap":
                return wrap(`<g transform="translate(0 ${dy})"><path d="M36 45 Q37 17 70 16 Q103 17 104 45 Q70 36 36 45Z" fill="#14b8a6" stroke="#0f4d4a" stroke-width="3" stroke-linejoin="round"/><path d="M33 45 Q70 32 107 45 Q109 51 101 51.5 Q70 43 39 51.5 Q31 51 33 45Z" fill="#0f766e" stroke="#0f4d4a" stroke-width="3" stroke-linejoin="round"/><circle cx="70" cy="16.5" r="3.4" fill="#0f766e" stroke="#0f4d4a" stroke-width="2"/><path d="M70 23 l2.6 5.2 5.8.8-4.2 4 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.2-4 5.8-.8z" fill="#fef08a"/></g>`);
            case "crown":
                return wrap(`<g transform="translate(0 ${dy - 3})"><path d="M44 30 L49 9 L59.5 21 L70 5 L80.5 21 L91 9 L96 30 Z" fill="#ffd34d" stroke="#b7791f" stroke-width="3" stroke-linejoin="round"/><rect x="43" y="26" width="54" height="9" rx="3.5" fill="#f6b81c" stroke="#b7791f" stroke-width="3"/><circle cx="57" cy="30.5" r="2.8" fill="#ef4444"/><circle cx="70" cy="30.5" r="3.2" fill="#3b82f6"/><circle cx="83" cy="30.5" r="2.8" fill="#22c55e"/><circle cx="49" cy="9" r="2.4" fill="#fff7cc"/><circle cx="70" cy="5" r="2.6" fill="#fff7cc"/><circle cx="91" cy="9" r="2.4" fill="#fff7cc"/></g>`);
            case "mask": {
                const cy = (ly + ry) / 2;
                return wrap(`<path fill-rule="evenodd" d="M${lx - 22} ${cy - 2} Q${lx - 16} ${cy - 13} ${lx} ${cy - 10} Q${lx + 8} ${cy - 9} 70 ${cy - 5} Q${rx - 8} ${cy - 9} ${rx} ${cy - 10} Q${rx + 16} ${cy - 13} ${rx + 22} ${cy - 2} Q${rx + 20} ${cy + 10} ${rx} ${cy + 10} Q${rx - 10} ${cy + 10} 70 ${cy + 4} Q${lx + 10} ${cy + 10} ${lx} ${cy + 10} Q${lx - 20} ${cy + 10} ${lx - 22} ${cy - 2}Z M${lx} ${ly - 7.6} a7 7.6 0 1 0 0.01 0Z M${rx} ${ry - 7.6} a7 7.6 0 1 0 0.01 0Z" fill="#7c3aed" stroke="#3b1a7a" stroke-width="2.6" stroke-linejoin="round"/><path d="M${lx - 22} ${cy - 2} L${lx - 30} ${cy - 6} M${rx + 22} ${cy - 2} L${rx + 30} ${cy - 6}" stroke="#3b1a7a" stroke-width="3" stroke-linecap="round"/>`);
            }
            case "sparkles":
                return "";
            case "headphones":
                return wrap(`<g transform="translate(0 ${dy})"><path d="M33 58 Q32 17 70 17 Q108 17 107 58" fill="none" stroke="#1f2937" stroke-width="7" stroke-linecap="round"/><path d="M33 58 Q32 17 70 17 Q108 17 107 58" fill="none" stroke="#475569" stroke-width="2.6" stroke-linecap="round"/><rect x="24" y="48" width="14" height="24" rx="7" fill="#38bdf8" stroke="#1f2937" stroke-width="3"/><rect x="102" y="48" width="14" height="24" rx="7" fill="#38bdf8" stroke="#1f2937" stroke-width="3"/><rect x="27" y="52" width="4" height="11" rx="2" fill="#bae6fd"/></g>`);
            case "flower":
                return wrap(`<g transform="translate(0 ${dy})"><g fill="#fff" stroke="#db2777" stroke-width="1.8">${[0, 60, 120, 180, 240, 300].map((r) => `<ellipse cx="101" cy="21" rx="4.6" ry="8" transform="rotate(${r} 101 29)"/>`).join("")}</g><circle cx="101" cy="29" r="5" fill="#facc15" stroke="#b45309" stroke-width="1.8"/><path d="M96 36 Q92 42 93 47" fill="none" stroke="#16a34a" stroke-width="2.6" stroke-linecap="round"/></g>`);
            case "pirate_patch":
                return wrap(`<path d="M34 ${ly - 16} Q70 ${ly - 30} 106 ${ly - 10}" fill="none" stroke="#111827" stroke-width="3" stroke-linecap="round"/><ellipse cx="${lx}" cy="${ly}" rx="10" ry="9.5" fill="#111827" stroke="#000" stroke-width="1.5"/><path d="M${lx - 3} ${ly - 1} l6 0 M${lx} ${ly - 4} l0 6" stroke="#f8fafc" stroke-width="1.6" stroke-linecap="round" opacity=".85"/>`);
            case "halo":
                return wrap(`<g transform="translate(0 ${dy - 4})"><ellipse cx="70" cy="9" rx="26" ry="7" fill="none" stroke="#fde68a" stroke-width="8" opacity=".45"/><ellipse cx="70" cy="9" rx="26" ry="7" fill="none" stroke="#facc15" stroke-width="4.5"/><ellipse cx="70" cy="8" rx="20" ry="4.4" fill="none" stroke="#fff7cc" stroke-width="1.6"/></g>`);
            default:
                return "";
        }
    }

    function sparkleMarkup() {
        // Gecikmə sinifdədir (lva-sparkle--N) — inline style yoxdur (CSP).
        const star = (x, y, s, n) =>
            `<path class="lva-sparkle lva-sparkle--${n}" d="M${x} ${y - s} Q${x + s * 0.18} ${y - s * 0.18} ${x + s} ${y} Q${x + s * 0.18} ${y + s * 0.18} ${x} ${y + s} Q${x - s * 0.18} ${y + s * 0.18} ${x - s} ${y} Q${x - s * 0.18} ${y - s * 0.18} ${x} ${y - s}Z" fill="#fde047" stroke="#ca8a04" stroke-width="1.2"/>`;
        return `<g class="lva-accessory lva-accessory--sparkles">${star(24, 32, 8, 1)}${star(117, 25, 6.5, 2)}${star(113, 84, 5.5, 3)}${star(28, 88, 4.5, 4)}</g>`;
    }

    const bowtieMarkup = () =>
        `<g class="lva-accessory lva-accessory--bowtie"><path d="M70 90 L55 82.5 Q52 90 55 97.5 Z M70 90 L85 82.5 Q88 90 85 97.5 Z" fill="#ef4444" stroke="#7f1d1d" stroke-width="2.6" stroke-linejoin="round"/><circle cx="70" cy="90" r="4.6" fill="#b91c1c" stroke="#7f1d1d" stroke-width="2.2"/></g>`;

    /* ── Yığım ─────────────────────────────────────────────────────── */
    function resolveCrop(opts) {
        const crop = opts?.crop || "auto";
        if (crop === "full" || crop === "portrait") return crop;
        return Number(opts?.size) > 0 && Number(opts.size) < 96 ? "portrait" : "full";
    }

    const VIEWBOX = { full: "0 0 140 140", portrait: "21 1 98 98" };

    function characterMarkup(normalized, crop) {
        const cfg = catalog.avatars?.[normalized.avatarKey] || catalog.avatars?.avatar_1 || {};
        const draw = SPECIES[cfg.species] || SPECIES.fox;
        const art = draw(cfg);
        const anchor = Object.assign({}, DEFAULT_ANCHOR, art.anchor || {});
        const body = bodyParts(cfg, art.body || {});
        const torso = art.torso || `${body.feet}${body.torso}`;
        const arms = art.arms || body.arms;
        const acc = normalized.accessoryKey;
        const head =
            `<g class="lva-head">${art.back || ""}${art.ears || ""}${art.head || ""}` +
            `${typeof art.face === "function" ? art.face(anchor) : ""}${accessoryMarkup(acc, anchor)}</g>`;
        return {
            cfg,
            markup:
                (crop === "full" ? `<ellipse class="lva-shadow" cx="70" cy="134" rx="30" ry="4.5" fill="rgba(15,23,42,.22)"/>` : "") +
                // Əllər BAŞDAN SONRA çəkilir: yuxarı qaldırılanda (wave/cheer/jump) başın
                // arxasında itmir; aşağı sallananda başla üst-üstə düşmür.
                `<g class="lva-rig"><g class="lva-tail">${art.tail || ""}</g>${torso}` +
                `${acc === "bowtie" ? bowtieMarkup() : ""}${head}${arms[0]}${arms[1]}${acc === "sparkles" ? sparkleMarkup() : ""}</g>`,
        };
    }

    function renderSvg(profile, opts) {
        const normalized = getProfile(profile);
        const crop = resolveCrop(opts);
        const character = characterMarkup(normalized, crop);
        const svg =
            `<svg class="lva" viewBox="${VIEWBOX[crop]}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" data-species="${esc(character.cfg.species || "")}" data-crop="${crop}">` +
            `${character.markup}</svg>`;
        return { markup: svg, config: character.cfg, profile: normalized, crop };
    }

    function renderAvatarSvg(profile, options) {
        return renderSvg(profile, options || {}).markup;
    }

    function renderAvatarMarkup(profile, options) {
        const opts = options || {};
        const rendered = renderSvg(profile, opts);
        const size = Number(opts.size) > 0 ? Number(opts.size) : 72;
        const label = esc(opts.label || catalog.avatars?.[rendered.profile.avatarKey]?.label || "Avatar");
        const classes = ["live-avatar", `live-avatar--${rendered.crop}`];
        if (opts.className) classes.push(opts.className);
        if (opts.interactive === false) classes.push("is-static");
        if (opts.backdrop === false) classes.push("live-avatar--bare");
        const dance = DANCES.includes(opts.dance) ? ` data-dance="${opts.dance}"` : "";
        const style = [
            `--live-avatar-size:${size}px`,
            `--live-avatar-bg-start:${rendered.config.bgStart}`,
            `--live-avatar-bg-end:${rendered.config.bgEnd}`,
            `--live-avatar-shell:${rendered.config.main}`,
        ].join(";");
        const backdrop = opts.backdrop === false ? "" : '<span class="live-avatar__backdrop"></span>';
        return `<span class="${esc(classes.join(" "))}" style="${style}" role="img" aria-label="${label}" data-avatar="${esc(rendered.profile.avatarKey)}" data-accessory="${esc(rendered.profile.accessoryKey)}"${dance}>${backdrop}${rendered.markup}</span>`;
    }

    function renderAvatarDataUrl(profile, options) {
        const opts = Object.assign({ crop: "portrait" }, options || {});
        const normalized = getProfile(profile);
        const crop = opts.crop === "full" ? "full" : "portrait";
        const character = characterMarkup(normalized, crop);
        const [x, y, w, h] = VIEWBOX[crop].split(" ").map(Number);
        const bg =
            opts.backdrop === false
                ? ""
                : `<defs><linearGradient id="b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${character.cfg.bgStart}"/><stop offset="1" stop-color="${character.cfg.bgEnd}"/></linearGradient><radialGradient id="g" cx=".3" cy=".22" r=".6"><stop offset="0" stop-color="#fff" stop-opacity=".75"/><stop offset=".45" stop-color="#fff" stop-opacity=".15"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>` +
                  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${w * 0.28}" fill="url(#b)"/><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${w * 0.28}" fill="url(#g)"/>`;
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${VIEWBOX[crop]}">${bg}${character.markup}</svg>`;
        return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
    }

    const ACCESSORY_VIEWBOX = {
        glasses: "30 42 80 32",
        cap: "26 10 88 48",
        crown: "38 -2 64 42",
        mask: "22 38 96 34",
        sparkles: "10 14 120 86",
        bowtie: "48 76 44 28",
        headphones: "20 10 100 70",
        flower: "84 8 34 42",
        pirate_patch: "30 30 80 40",
        halo: "40 -4 60 26",
    };

    function renderAccessoryIcon(key, size) {
        const px = Number(size) > 0 ? Number(size) : 28;
        const anchor = Object.assign({}, DEFAULT_ANCHOR);
        let inner = "";
        if (key === "sparkles") inner = sparkleMarkup();
        else if (key === "bowtie") inner = bowtieMarkup();
        else inner = accessoryMarkup(key, anchor);
        if (!inner) {
            return `<svg class="lva-acc-icon" viewBox="0 0 24 24" width="${px}" height="${px}" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 3"/></svg>`;
        }
        return `<svg class="lva-acc-icon" viewBox="${ACCESSORY_VIEWBOX[key] || "0 0 140 140"}" width="${px}" height="${px}" aria-hidden="true" focusable="false">${inner}</svg>`;
    }

    function mountAvatar(element, profile, options) {
        if (!element) return;
        element.innerHTML = renderAvatarMarkup(profile, options);
    }

    function setDance(element, name) {
        if (!element) return;
        const root = element.classList?.contains("live-avatar") ? element : element.querySelector?.(".live-avatar");
        if (!root) return;
        if (DANCES.includes(name)) root.setAttribute("data-dance", name);
        else root.removeAttribute("data-dance");
    }

    window.LiveAvatarRenderer = {
        getProfile,
        renderAvatarDataUrl,
        renderAvatarMarkup,
        renderAvatarSvg,
        renderAccessoryIcon,
        mountAvatar,
        setDance,
        DANCES: DANCES.slice(),
    };
})();

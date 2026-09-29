/* live_avatar_catalog.js — canlı oyunun avatar / aksesuar / reaksiya kataloqu.
 *
 * AÇARLAR SABİTDİR (DB-də saxlanır: LivePlayer.avatar_key / accessory_key və
 * apps/live_exam/constants.py AVATARS / ACCESSORIES siyahıları ilə eynidir).
 * 2026-09-29 (LX-FE-STAGE): rəsm yeniləndi — hər heyvanın öz palitrası var
 * (`main`, `light`, `dark`, `line`, `inner`, `nose`, `extra`), fon qradiyenti
 * (`bgStart` → `bgEnd`). Köhnə sahələr (`shell`, `shellAlt`, `shellLight`,
 * `accent`, `outline`, `mouth`, `species`, `label`) geri uyğunluq üçün saxlanır.
 * Rəsm özü `live_avatar_renderer.js`-dədir.
 */
(function () {
    function avatar(label, species, palette, bg) {
        return Object.freeze({
            label: label,
            species: species,
            bgStart: bg[0],
            bgEnd: bg[1],
            main: palette.main,
            light: palette.light,
            dark: palette.dark,
            line: palette.line,
            inner: palette.inner || palette.light,
            nose: palette.nose || palette.line,
            extra: palette.extra || palette.dark,
            // Köhnə adlar (geri uyğunluq — xarici kod oxuya bilər).
            shell: palette.main,
            shellAlt: palette.dark,
            shellLight: palette.light,
            accent: palette.extra || palette.dark,
            outline: palette.line,
            mouth: palette.line,
        });
    }

    const avatars = {
        avatar_1: avatar("Fox", "fox",
            { main: "#f5892c", light: "#fff4e4", dark: "#c95f19", line: "#6b2e0e", inner: "#ffc79c", nose: "#2b1a12", extra: "#3b1d0e" },
            ["#7dd3fc", "#2563eb"]),
        avatar_2: avatar("Panda", "panda",
            { main: "#ffffff", light: "#eef1f6", dark: "#23262f", line: "#23262f", inner: "#454b5c", nose: "#23262f", extra: "#dde3ec" },
            ["#a7f3d0", "#0d9488"]),
        avatar_3: avatar("Lion", "lion",
            { main: "#f7c04a", light: "#ffeab8", dark: "#d98e1f", line: "#7a3e0c", inner: "#f3a93b", nose: "#6b2e14", extra: "#c2621a" },
            ["#6ee7b7", "#0ea5e9"]),
        avatar_4: avatar("Tiger", "tiger",
            { main: "#f7931e", light: "#fff4e6", dark: "#d9730c", line: "#6b3410", inner: "#ffd2a8", nose: "#2a1a12", extra: "#2a1a12" },
            ["#a5f3fc", "#16a34a"]),
        avatar_5: avatar("Koala", "koala",
            { main: "#9ca8b8", light: "#e9edf3", dark: "#7c8799", line: "#3f4a5c", inner: "#f6e7ee", nose: "#363b47", extra: "#c3cad6" },
            ["#bae6fd", "#6366f1"]),
        avatar_6: avatar("Pig", "pig",
            { main: "#f9a8c2", light: "#ffd6e3", dark: "#ec7fa3", line: "#9d3a62", inner: "#e56b93", nose: "#9d2f57", extra: "#f47ea3" },
            ["#bbf7d0", "#14b8a6"]),
        avatar_7: avatar("Frog", "frog",
            { main: "#58c45c", light: "#d3f5bd", dark: "#3c9b45", line: "#1f5e2a", inner: "#ffffff", nose: "#1f5e2a", extra: "#ff9fb0" },
            ["#bae6fd", "#0284c7"]),
        avatar_8: avatar("Octopus", "octopus",
            { main: "#9b7bf7", light: "#dcd0ff", dark: "#7657e0", line: "#3e2a8c", inner: "#c4b2ff", nose: "#3e2a8c", extra: "#ff9fc4" },
            ["#99f6e4", "#0ea5e9"]),
        avatar_9: avatar("Monkey", "monkey",
            { main: "#8a5a33", light: "#f3d3ae", dark: "#6a4222", line: "#3e2412", inner: "#e9b98a", nose: "#3e2412", extra: "#5a381c" },
            ["#a7f3d0", "#10b981"]),
        avatar_10: avatar("Unicorn", "unicorn",
            { main: "#ffffff", light: "#f4f0ff", dark: "#e4defa", line: "#6c5bb8", inner: "#ffd35c", nose: "#b79ce0", extra: "#e0a21b" },
            ["#c7d2fe", "#a855f7"]),
        avatar_11: avatar("Rabbit", "rabbit",
            { main: "#f4f5fa", light: "#ffffff", dark: "#d9dde8", line: "#5a6275", inner: "#ffb0c8", nose: "#ff7fa6", extra: "#d9dde8" },
            ["#fecdd3", "#fb7185"]),
        avatar_12: avatar("Hamster", "hamster",
            { main: "#f6b26b", light: "#fff4e3", dark: "#d88a3f", line: "#7a4318", inner: "#ffc2a3", nose: "#e2677f", extra: "#ff9e9e" },
            ["#ddd6fe", "#8b5cf6"]),
        avatar_13: avatar("Wolf", "wolf",
            { main: "#7d8ca6", light: "#e6ebf3", dark: "#5a6782", line: "#2e3850", inner: "#c9d2e3", nose: "#1f2533", extra: "#48546e" },
            ["#c7d2fe", "#1e3a8a"]),
        avatar_14: avatar("Polar Bear", "polar_bear",
            { main: "#f8fbff", light: "#ffffff", dark: "#d4e5f6", line: "#5b7896", inner: "#cfe3f5", nose: "#1e2a3a", extra: "#bcd6ee" },
            ["#a5f3fc", "#0891b2"]),
        avatar_15: avatar("Red Panda", "red_panda",
            { main: "#c9562a", light: "#fff6ec", dark: "#8a2e12", line: "#5a1e0b", inner: "#fff6ec", nose: "#2d130a", extra: "#6e2410" },
            ["#d9f99d", "#65a30d"]),
        avatar_16: avatar("Mint Rabbit", "lop_rabbit",
            { main: "#9fe8cb", light: "#e8fbf3", dark: "#5cc9a2", line: "#1f6e57", inner: "#ffd1de", nose: "#ff8fb0", extra: "#7fd9b6" },
            ["#fde68a", "#f59e0b"]),
    };

    // `icon` — köhnə mətn simvolu (seçici çipləri üçün geri uyğunluq). Yeni seçicilər
    // `LiveAvatarRenderer.renderAccessoryIcon(key)` SVG-sini işlədə bilər.
    const accessories = {
        accessory_none: { label: "None", icon: "○" },
        glasses: { label: "Glasses", icon: "◐" },
        cap: { label: "Cap", icon: "⌂" },
        crown: { label: "Crown", icon: "♛" },
        mask: { label: "Mask", icon: "▣" },
        sparkles: { label: "Sparkles", icon: "✦" },
        bowtie: { label: "Bowtie", icon: "🎀" },
        headphones: { label: "Headphones", icon: "🎧" },
        flower: { label: "Flower", icon: "🌼" },
        pirate_patch: { label: "Patch", icon: "🕶️" },
        halo: { label: "Halo", icon: "😇" },
    };

    const reactions = {
        like: { label: "Like", emoji: "👍" },
        clap: { label: "Clap", emoji: "👏" },
        love: { label: "Love", emoji: "❤️" },
        laugh: { label: "Laugh", emoji: "😂" },
        think: { label: "Think", emoji: "🤔" },
    };

    // Rəqs API-si (live_avatar.css): `data-dance` dəyərləri.
    const dances = ["bounce", "sway", "spin", "jump", "wave", "cheer", "idle"];

    window.LiveAvatarCatalog = Object.freeze({
        defaultAvatarKey: "avatar_1",
        defaultAccessoryKey: "accessory_none",
        avatarKeys: Object.freeze(Object.keys(avatars)),
        accessoryKeys: Object.freeze(Object.keys(accessories)),
        reactionKeys: Object.freeze(Object.keys(reactions)),
        danceKeys: Object.freeze(dances.slice()),
        avatars: Object.freeze(avatars),
        accessories: Object.freeze(accessories),
        reactions: Object.freeze(reactions),
    });
})();

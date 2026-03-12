(function () {
    const avatars = {
        avatar_1: {
            label: "Fox",
            species: "fox",
            bgStart: "#6ee7d8",
            bgEnd: "#2563eb",
            shell: "#f59e0b",
            shellAlt: "#fbbf24",
            shellLight: "#fde68a",
            accent: "#7c2d12",
            outline: "#7c2d12",
            mouth: "#78350f"
        },
        avatar_2: {
            label: "Panda",
            species: "panda",
            bgStart: "#93c5fd",
            bgEnd: "#14b8a6",
            shell: "#f8fafc",
            shellAlt: "#e2e8f0",
            shellLight: "#ffffff",
            accent: "#111827",
            outline: "#1f2937",
            mouth: "#334155"
        },
        avatar_3: {
            label: "Lion",
            species: "lion",
            bgStart: "#86efac",
            bgEnd: "#0ea5e9",
            shell: "#fde68a",
            shellAlt: "#f59e0b",
            shellLight: "#fff7c2",
            accent: "#92400e",
            outline: "#92400e",
            mouth: "#78350f"
        },
        avatar_4: {
            label: "Tiger",
            species: "tiger",
            bgStart: "#67e8f9",
            bgEnd: "#22c55e",
            shell: "#fb923c",
            shellAlt: "#f97316",
            shellLight: "#fdba74",
            accent: "#1f2937",
            outline: "#7c2d12",
            mouth: "#7c2d12"
        },
        avatar_5: {
            label: "Koala",
            species: "koala",
            bgStart: "#a5f3fc",
            bgEnd: "#34d399",
            shell: "#cbd5e1",
            shellAlt: "#94a3b8",
            shellLight: "#e2e8f0",
            accent: "#475569",
            outline: "#475569",
            mouth: "#334155"
        },
        avatar_6: {
            label: "Pig",
            species: "pig",
            bgStart: "#5eead4",
            bgEnd: "#3b82f6",
            shell: "#f9a8d4",
            shellAlt: "#f472b6",
            shellLight: "#fbcfe8",
            accent: "#be185d",
            outline: "#9d174d",
            mouth: "#9d174d"
        },
        avatar_7: {
            label: "Frog",
            species: "frog",
            bgStart: "#34d399",
            bgEnd: "#0ea5e9",
            shell: "#4ade80",
            shellAlt: "#22c55e",
            shellLight: "#bbf7d0",
            accent: "#166534",
            outline: "#166534",
            mouth: "#166534"
        },
        avatar_8: {
            label: "Octopus",
            species: "octopus",
            bgStart: "#60a5fa",
            bgEnd: "#2dd4bf",
            shell: "#a78bfa",
            shellAlt: "#8b5cf6",
            shellLight: "#ddd6fe",
            accent: "#5b21b6",
            outline: "#6d28d9",
            mouth: "#5b21b6"
        },
        avatar_9: {
            label: "Monkey",
            species: "monkey",
            bgStart: "#2dd4bf",
            bgEnd: "#2563eb",
            shell: "#a16207",
            shellAlt: "#854d0e",
            shellLight: "#f5d0a9",
            accent: "#4b2e15",
            outline: "#4b2e15",
            mouth: "#4b2e15"
        },
        avatar_10: {
            label: "Unicorn",
            species: "unicorn",
            bgStart: "#67e8f9",
            bgEnd: "#22c55e",
            shell: "#f8fafc",
            shellAlt: "#e9d5ff",
            shellLight: "#ffffff",
            accent: "#7c3aed",
            outline: "#7c3aed",
            mouth: "#6d28d9"
        },
        avatar_11: {
            label: "Rabbit",
            species: "rabbit",
            bgStart: "#6ee7b7",
            bgEnd: "#38bdf8",
            shell: "#f8fafc",
            shellAlt: "#e9d5ff",
            shellLight: "#ffffff",
            accent: "#7c3aed",
            outline: "#475569",
            mouth: "#64748b"
        },
        avatar_12: {
            label: "Hamster",
            species: "hamster",
            bgStart: "#99f6e4",
            bgEnd: "#3b82f6",
            shell: "#fdba74",
            shellAlt: "#fb923c",
            shellLight: "#ffedd5",
            accent: "#7c2d12",
            outline: "#7c2d12",
            mouth: "#7c2d12"
        },
        avatar_13: {
            label: "Wolf",
            species: "fox",
            bgStart: "#dbeafe",
            bgEnd: "#60a5fa",
            shell: "#cbd5e1",
            shellAlt: "#94a3b8",
            shellLight: "#f8fafc",
            accent: "#334155",
            outline: "#334155",
            mouth: "#1e293b"
        },
        avatar_14: {
            label: "Polar Bear",
            species: "panda",
            bgStart: "#ecfeff",
            bgEnd: "#38bdf8",
            shell: "#ffffff",
            shellAlt: "#dbeafe",
            shellLight: "#f8fafc",
            accent: "#0f172a",
            outline: "#475569",
            mouth: "#334155"
        },
        avatar_15: {
            label: "Red Panda",
            species: "fox",
            bgStart: "#fde68a",
            bgEnd: "#fb7185",
            shell: "#f97316",
            shellAlt: "#ea580c",
            shellLight: "#ffedd5",
            accent: "#7c2d12",
            outline: "#7c2d12",
            mouth: "#7c2d12"
        },
        avatar_16: {
            label: "Mint Rabbit",
            species: "rabbit",
            bgStart: "#bbf7d0",
            bgEnd: "#22d3ee",
            shell: "#f8fafc",
            shellAlt: "#86efac",
            shellLight: "#ffffff",
            accent: "#0f766e",
            outline: "#475569",
            mouth: "#0f766e"
        }
    };

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
        halo: { label: "Halo", icon: "😇" }
    };

    const reactions = {
        like: { label: "Like", emoji: "👍" },
        clap: { label: "Clap", emoji: "👏" },
        love: { label: "Love", emoji: "❤️" },
        laugh: { label: "Laugh", emoji: "😂" },
        think: { label: "Think", emoji: "🤔" }
    };

    window.LiveAvatarCatalog = Object.freeze({
        defaultAvatarKey: "avatar_1",
        defaultAccessoryKey: "accessory_none",
        avatarKeys: Object.freeze(Object.keys(avatars)),
        accessoryKeys: Object.freeze(Object.keys(accessories)),
        reactionKeys: Object.freeze(Object.keys(reactions)),
        avatars: Object.freeze(avatars),
        accessories: Object.freeze(accessories),
        reactions: Object.freeze(reactions)
    });
})();

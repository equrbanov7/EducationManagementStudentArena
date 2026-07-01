import { UI } from './dom.js';
import { state } from './state.js';
import { playFinalSound } from './audio.js';
import { avatarImageMarkup, esc, safeDisplay, topSignature, tr } from './utils.js';

export function renderPodium(top) {
    const finalRows = Array.isArray(top) ? top : [];
    const finalKey = topSignature(finalRows) || "final";
    if (state.finalSignature === finalKey) {
        return;
    }
    state.finalSignature = finalKey;

    // Ensure final podium is visible and game area is hidden
    safeDisplay(UI.finalPodium, "grid");
    safeDisplay(UI.gameArea, "none");

    playFinalSound(finalKey);

    UI.confetti.innerHTML = "";
    const othersSection = UI.othersList?.closest(".others-section");
    const colors = ["#fbbf24", "#fb7185", "#38bdf8", "#34d399", "#0ea5e9", "#f97316", "#fde047"];
    const appendConfetti = (variant, styles) => {
        const piece = document.createElement("div");
        piece.className = `confetti-piece ${variant}`;
        Object.entries(styles).forEach(([key, value]) => {
            piece.style.setProperty(key, value);
        });
        UI.confetti.appendChild(piece);
    };

    for (let index = 0; index < 26; index += 1) {
        appendConfetti("confetti-piece--side-left", {
            "--color": colors[index % colors.length],
            "--size": `${8 + Math.random() * 10}px`,
            "--delay": `${4.2 + Math.random() * 0.6}s`,
            "--duration": `${1.6 + Math.random() * 0.8}s`,
            "--burst-x": `${180 + Math.random() * 280}px`,
            "--burst-y": `${-240 + Math.random() * 420}px`,
            "--spin": `${360 + Math.random() * 540}deg`,
            "--origin-y": `${-110 + Math.random() * 220}px`,
            "--shape-radius": Math.random() > 0.45 ? "50%" : "3px",
        });
        appendConfetti("confetti-piece--side-right", {
            "--color": colors[(index + 2) % colors.length],
            "--size": `${8 + Math.random() * 10}px`,
            "--delay": `${4.2 + Math.random() * 0.6}s`,
            "--duration": `${1.6 + Math.random() * 0.8}s`,
            "--burst-x": `${-180 - Math.random() * 280}px`,
            "--burst-y": `${-240 + Math.random() * 420}px`,
            "--spin": `${-360 - Math.random() * 540}deg`,
            "--origin-y": `${-110 + Math.random() * 220}px`,
            "--shape-radius": Math.random() > 0.45 ? "50%" : "3px",
        });
    }

    for (let index = 0; index < 62; index += 1) {
        appendConfetti("confetti-piece--top", {
            "--color": colors[(index + 4) % colors.length],
            "--size": `${7 + Math.random() * 9}px`,
            "--delay": `${4.7 + Math.random() * 1.5}s`,
            "--duration": `${3 + Math.random() * 1.6}s`,
            "--left": `${6 + Math.random() * 88}%`,
            "--drift-x": `${-110 + Math.random() * 220}px`,
            "--drop-rotation": `${540 + Math.random() * 720}deg`,
            "--shape-radius": Math.random() > 0.4 ? "50%" : "3px",
        });
    }

    UI.podiumStage.innerHTML = "";
    const sortedTop = finalRows.slice().sort((left, right) => {
        const scoreDiff = Number(right?.score || 0) - Number(left?.score || 0);
        if (scoreDiff !== 0) return scoreDiff;
        return Number(left?.player_id || left?.id || 0) - Number(right?.player_id || right?.id || 0);
    });
    const podiumTop = {
        1: sortedTop[0] ? { ...sortedTop[0], place: 1, slot: "center" } : null,
        2: sortedTop[1] ? { ...sortedTop[1], place: 2, slot: "left" } : null,
        3: sortedTop[2] ? { ...sortedTop[2], place: 3, slot: "right" } : null,
    };
    const riseDelays = { 3: 0.1, 2: 0.34, 1: 0.58 };
    const celebrationDelays = { 3: 0.8, 2: 1.02, 1: 1.24 };
    const suffix = esc(tr("pointsSuffix", "pts"));

    [3, 2, 1].forEach(place => {
        const player = podiumTop[place];
        if (!player) return;

        const block = document.createElement("section");
        block.className = `podium-block podium-block--slot-${player.slot} podium-block--place-${player.place}`;
        block.style.setProperty("--podium-rise-delay", `${riseDelays[player.place]}s`);
        block.style.setProperty("--podium-celebrate-delay", `${celebrationDelays[player.place]}s`);
        block.dataset.accessory = player.accessory_key || player.accessoryKey || "accessory_none";
        block.innerHTML = `
            <div class="podium-card">
                <div class="podium-card__shine"></div>
                ${player.place === 1 ? '<div class="podium-crown-badge">👑</div>' : `<div class="podium-medal-badge">${player.place}</div>`}
                <div class="podium-avatar-shell">
                    <span class="podium-avatar-ring"></span>
                    <span class="podium-avatar-spark podium-avatar-spark--left"></span>
                    <span class="podium-avatar-spark podium-avatar-spark--right"></span>
                    ${avatarImageMarkup(
                        player,
                        player.place === 1 ? 132 : player.place === 2 ? 116 : 108,
                        "podium-avatar-image"
                    )}
                </div>
                <div class="podium-name">${esc(player.nickname || "")}</div>
                <div class="podium-score">${Number(player.score || 0)} <span>${suffix}</span></div>
            </div>
            <div class="podium-stand">
                <div class="podium-stand__glow"></div>
                <div class="podium-stand__place">${player.place}</div>
            </div>
        `;
        UI.podiumStage.appendChild(block);
    });

    UI.othersList.innerHTML = "";
    const others = sortedTop.slice(3);
    if (othersSection) {
        othersSection.style.display = others.length ? "" : "none";
    }
    others.forEach((player, index) => {
        const row = document.createElement("div");
        row.className = "other-row";
        row.style.setProperty("--other-delay", `${0.98 + index * 0.06}s`);
        row.innerHTML = `
            <div class="other-info">
                <span class="other-rank">${index + 4}</span>
                ${avatarImageMarkup(player, 44, "other-avatar-image")}
                <span class="other-name">${esc(player.nickname || "")}</span>
            </div>
            <span class="other-score">${Number(player.score || 0)} <small>${suffix}</small></span>
        `;
        UI.othersList.appendChild(row);
    });
}

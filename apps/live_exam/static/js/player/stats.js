// LX-FE-PLAYER (2026-09-29): yer (rank) yaddaşı — yalnız SERVERİN göndərdiyi rank saxlanılır
// (sual indeksi ilə); ardıcıl iki sualın server rank-ı məlumdursa ox (▲/▼) göstərilir.
// Heç bir xal/yer müştəri tərəfində hesablanmır.
import { BOOTSTRAP } from './config.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';

const memory = { byIndex: {} };
const storageKey = () => `lx.player.rank.${BOOTSTRAP.pin || ""}.${state.player.id || ""}`;

function load() {
    try {
        const raw = window.sessionStorage.getItem(storageKey());
        if (raw) Object.assign(memory.byIndex, JSON.parse(raw) || {});
    } catch (error) {
        // sessionStorage bağlıdır — yaddaş yalnız bu səhifə ömrü üçündür
    }
}

function save() {
    try {
        window.sessionStorage.setItem(storageKey(), JSON.stringify(memory.byIndex));
    } catch (error) {
        // yox saymaq olar
    }
}

load();

export function rememberRank(questionIndex, rank) {
    const index = Number(questionIndex);
    const value = Number(rank);
    if (!Number.isFinite(index) || index <= 0 || !Number.isFinite(value) || value <= 0) return;
    if (memory.byIndex[index] === value) return;
    memory.byIndex[index] = value;
    save();
}

export function previousRank(questionIndex) {
    const value = memory.byIndex[Number(questionIndex) - 1];
    return Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : null;
}

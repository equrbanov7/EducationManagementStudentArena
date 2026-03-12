(function () {
    function normalizeNickname(value) {
        return String(value || "")
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 32);
    }

    function validateNickname(value, messages) {
        const normalized = normalizeNickname(value);
        if (!normalized) {
            return { valid: false, value: normalized, message: messages?.required || "Nickname is required." };
        }
        if (normalized.length > 32) {
            return { valid: false, value: normalized.slice(0, 32), message: messages?.tooLong || "Nickname is too long." };
        }
        return { valid: true, value: normalized, message: "" };
    }

    window.LiveWaitRoomNicknameEditor = {
        normalizeNickname,
        validateNickname
    };
})();

document.addEventListener("DOMContentLoaded", () => {
  const timerBanners = document.querySelectorAll("[data-otp-expires-at]");

  timerBanners.forEach((banner) => {
    const valueNode = banner.querySelector("[data-otp-countdown]");
    const expiresAtRaw = banner.getAttribute("data-otp-expires-at");
    const expiredLabel = banner.getAttribute("data-expired-label") || "Vaxt bitib";

    if (!valueNode || !expiresAtRaw) {
      return;
    }

    const expiresAt = new Date(expiresAtRaw);
    if (Number.isNaN(expiresAt.getTime())) {
      valueNode.textContent = expiredLabel;
      banner.classList.add("is-expired");
      return;
    }

    const formatCountdown = (remainingSeconds) => {
      const minutes = Math.floor(remainingSeconds / 60);
      const seconds = remainingSeconds % 60;
      return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    };

    const tick = () => {
      const diffMs = expiresAt.getTime() - Date.now();
      if (diffMs <= 0) {
        valueNode.textContent = expiredLabel;
        banner.classList.add("is-expired");
        return false;
      }

      const remainingSeconds = Math.ceil(diffMs / 1000);
      valueNode.textContent = formatCountdown(remainingSeconds);
      banner.classList.remove("is-expired");
      return true;
    };

    const shouldContinue = tick();
    if (!shouldContinue) {
      return;
    }

    const intervalId = window.setInterval(() => {
      const keepRunning = tick();
      if (!keepRunning) {
        window.clearInterval(intervalId);
      }
    }, 1000);
  });
});

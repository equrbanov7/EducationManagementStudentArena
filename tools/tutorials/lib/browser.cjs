// Ümumi brauzer köməkçiləri: Chrome-un yeri, giriş, defoltlar.
// Parol YALNIZ mühit dəyişənindən (TUTORIAL_PASSWORD) gəlir — heç bir fayla yazılmır.
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright-core");

const ROOT = path.resolve(__dirname, "..");

function loadDefaults() {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "scenarios", "_defaults.json"), "utf8"));
}

function chromePath() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
  ].filter(Boolean);
  const found = candidates.find((p) => fs.existsSync(p));
  if (!found) throw new Error("Chrome/Chromium tapılmadı — PLAYWRIGHT_CHROMIUM verin (env.sh)");
  return found;
}

async function launch() {
  return chromium.launch({
    executablePath: chromePath(),
    headless: true,
    args: ["--hide-scrollbars", "--force-device-scale-factor=1", "--lang=az"],
  });
}

function password() {
  const pw = process.env.TUTORIAL_PASSWORD;
  if (!pw) throw new Error("TUTORIAL_PASSWORD mühit dəyişəni verilməyib");
  return pw;
}

// Giriş formu səhifədəki 2-ci formadır (1-ci dil seçicisi). Düymə klikləri bəzən
// POST yaratmır, ona görə forma JS ilə göndərilir.
async function loginOnPage(page, defaults, username) {
  // Tələbə demo hesabları tələbə giriş səhifəsindən daxil olur.
  const loginPath = /^video\.telebe/.test(username) ? defaults.studentLoginPath || "/accounts/login/telebe/" : defaults.loginPath;
  await page.goto(defaults.baseUrl + loginPath, { waitUntil: "domcontentloaded" });
  await page.evaluate(
    ([u, p]) => {
      const f = [...document.querySelectorAll("form")].find((x) => x.elements.username && x.elements.password);
      f.elements.username.value = u;
      f.elements.password.value = p;
      f.submit();
    },
    [username, password()]
  );
  try {
    await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15000 });
  } catch (e) {
    throw new Error("Giriş alınmadı: " + username);
  }
  // «Məlumatlarınızı tamamlayın» qapısı (FİN/telefon) — demo hesabda «Hələlik keç».
  if (page.url().includes("/complete-profile/")) {
    await page.getByRole("button", { name: "Hələlik keç" }).click();
    await page.waitForURL((u) => !u.pathname.includes("/complete-profile/"), { timeout: 15000 });
  }
}

// İnterfeys dili: Django `django_language` kukisi (brauzerin dilindən asılı qalmasın).
async function setAzerbaijani(ctx, defaults) {
  const host = new URL(defaults.baseUrl).hostname;
  await ctx.addCookies([{ name: "django_language", value: "az", domain: host, path: "/" }]);
}

async function authState(browser, defaults, username) {
  const ctx = await browser.newContext({ viewport: defaults.viewport, locale: "az-AZ" });
  await setAzerbaijani(ctx, defaults);
  const page = await ctx.newPage();
  await loginOnPage(page, defaults, username);
  const state = await ctx.storageState();
  await ctx.close();
  return state;
}

module.exports = { setAzerbaijani, ROOT, loadDefaults, launch, authState, loginOnPage, password };

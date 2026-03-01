# Language Dropdown Manual Checklist

## Scope
- Component: custom language switcher dropdown (`AZ`, `EN`, `RU`, `TR`)
- Locations:
  - Navbar (desktop)
  - Mobile nav panel
  - Profile sidebar (if enabled on page)

## Browsers
- Chrome (latest stable)
- Firefox (latest stable)
- Safari (latest stable, macOS)
- Edge (latest stable)

## Core Checks (Run in each browser)
1. Open any page with navbar language switcher.
   - Expected: trigger is visible, current language code is correct.
2. Click trigger once.
   - Expected: dropdown opens, options are visible, caret rotates.
3. Click outside dropdown.
   - Expected: dropdown closes.
4. Press `Escape` while dropdown is open.
   - Expected: dropdown closes.
5. Select each language (`AZ`, `EN`, `RU`, `TR`) one by one.
   - Expected: page reloads, UI language changes, selected option appears active.
6. After language change, navigate to another page.
   - Expected: selected language remains active (no unexpected reset).
7. Open mobile menu and use mobile language dropdown.
   - Expected: opens/closes correctly, language change works the same as desktop.

## Keyboard & Accessibility Checks
1. Focus trigger with `Tab`, press `Enter` (or `Space`).
   - Expected: dropdown opens.
2. Move focus through options and activate with `Enter`.
   - Expected: correct language is submitted.
3. Verify focus outline is visible on trigger and options.
   - Expected: clear focus state, no hidden focus.

## Regression Checks
1. Verify user profile menu still opens/closes correctly.
2. Verify mobile burger menu still opens/closes correctly.
3. Verify no console errors while opening/closing switcher.

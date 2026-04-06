# Session Persistence and Delivery Fix (April 2026)

## Scope

This document records the QR/session persistence investigation and the precision fix for message delivery failures caused by fragile chat-search selectors.

## Problem Statement

Observed in production logs:

1. WhatsApp login succeeds.
2. Send attempts fail repeatedly with `Element not found for locators` for search textbox selectors.
3. Bot retries and refreshes, but still fails for targets.
4. User concern: repeated manual QR scans over time.

Representative failure evidence:

- `bot.log` entries around 2026-04-06 21:35-21:39 show successful login followed by search-box misses.
- `send_failure_*.png` screenshot confirms WhatsApp is loaded, but selector match is brittle for current DOM variant.

## Root Cause Analysis

Two independent reliability issues were mixed:

1. **Delivery path fragility**
   - Targeting known direct contacts via sidebar search is unnecessarily brittle when a phone number is already available.
   - WhatsApp UI search DOM varies (`div[contenteditable]` vs `input[type="search"]` style variants).

2. **Session continuity risk**
   - Temporary/no-profile startup mode is intentionally ephemeral and can force QR each run.
   - Persistent startup should be preferred in production to avoid repeated QR scans.

## Implemented Fix

### A) Precision delivery routing (phone-first)

In `submission_bot.py`:

- Added `_choose_delivery_target(target_name, number)`.
- For valid numbers, bot now sends using URL phone route (`use_search=False`).
- If phone route fails, bot retries once by contact label search.

Why this is high precision:

- It uses deterministic phone targeting for strict configured recipients.
- It keeps a fallback for edge cases where URL route cannot open target chat.

### B) Stronger selector coverage for remaining search flows

In `src/whatsapp_service.py`:

- Expanded `WhatsAppSelectors.SEARCH_BOX` with modern variants:
  - `aria-placeholder`/`aria-label` based `div[role="textbox"]`
  - `input[placeholder*="Search or start"]`
  - `input[aria-label*="Search"]`
  - `input[type="search"]`

### C) Session persistence hardening

1. **Production startup policy**
   - `submission_bot.py` now instantiates service with:
     - `allow_ephemeral_fallback=False`
   - This prevents accidental temp-profile runs from becoming the default behavior.

2. **Persistent profile preference memory**
   - `src/whatsapp_service.py` now persists last successful persistent profile in:
     - `<selenium_data_dir>_active_profile.txt`
   - On next startup, attempts are reordered to try last-known-good persistent profile first.

This reduces repeated startup churn and lowers QR re-auth frequency.

## Code References

- `submission_bot.py`:
  - `_choose_delivery_target` helper
  - send loop updated to phone-first routing + label fallback
  - service startup now disables ephemeral fallback

- `src/whatsapp_service.py`:
  - expanded search selectors
  - profile hint load/save helpers
  - preferred-profile startup ordering

- Tests:
  - `tests/test_submission_bot_helpers.py` (delivery target routing tests)
  - `tests/test_whatsapp_search_fallback.py` (profile hint startup preference test)

## Verification Performed

Executed locally:

1. `python -m unittest tests.test_whatsapp_search_fallback tests.test_submission_bot_helpers`
   - Result: all tests passed.

2. `python -m py_compile submission_bot.py src/whatsapp_service.py tests/test_whatsapp_search_fallback.py tests/test_submission_bot_helpers.py`
   - Result: compile pass (no syntax errors).

3. Historical log inspection + screenshot confirmation
   - Confirmed issue occurs post-login and is tied to search locator path.

## Web Research Notes That Informed the Fix

1. Chrome security change (Chrome 136): remote-debugging restrictions and recommendation to use non-default user-data-dir.
   - Source: https://developer.chrome.com/blog/remote-debugging-port

2. Selenium issue discussions indicate default profile constraints and recommendation to avoid default browser user profile in automation.
   - Source: https://github.com/SeleniumHQ/selenium/issues/17096

3. WhatsApp libraries document the same persistence principle: without stored auth state, QR is required again.
   - Source: https://wwebjs.dev/guide/creating-your-bot/authentication.html
   - Source: https://baileys.wiki/docs/socket/connecting

## Operational Impact

Expected improvements:

1. Lower send failure rate for strict direct recipients.
2. Reduced dependency on fragile search UI.
3. Better persistent-session reuse across restarts.
4. Lower probability of repeated manual QR scans.

## Residual External Limits

Still outside full code control:

1. WhatsApp Web DOM changes.
2. Browser channel updates and local profile corruption.
3. Device-link revocation from mobile app side.

## Suggested Future Work

1. Add a startup preflight command that verifies active profile health before bot loop starts.
2. Add alerting for repeated `send_failure` or repeated login timeout.
3. Add a small canary send check to detect UI breakage earlier.

---

Last updated: 2026-04-07

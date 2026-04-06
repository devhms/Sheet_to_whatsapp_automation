# Web Research Summary (April 2026)

This summary captures externally sourced reliability guidance relevant to this project and translates each item into implementation action.

## 1) Selenium Wait Strategy Guidance

Source:
- https://www.selenium.dev/documentation/webdriver/waits/

Key takeaways:

1. Flakiness is commonly caused by race conditions between script actions and dynamic UI readiness.
2. Prefer explicit waits for concrete conditions over generic sleeps.
3. Do not mix implicit and explicit waits due to unpredictable timeout behavior.
4. Customize poll interval and ignored exceptions where needed.

Project actions:

- Multi-step waits around WhatsApp login, search box, and message composer readiness.
- Retry logic with bounded backoff on send attempts.
- Locator fallback strategy for UI variants.
- Avoided global implicit wait approach.

## 2) Selenium Error Troubleshooting Guidance

Source:
- https://www.selenium.dev/documentation/webdriver/troubleshooting/errors/

Key takeaways:

1. `SessionNotCreatedException` commonly indicates driver/browser mismatch or startup constraints.
2. `NoSuchElementException` indicates timing, wrong context, or changed locator.
3. Production stability requires robust locator validation and synchronization.

Project actions:

- Session-loss detection + recovery path.
- Startup fallback chain across profile modes.
- Expanded locator sets and search shortcuts.
- Failure screenshots for rapid diagnosis.

## 3) Chrome Security/Automation Profile Guidance

Source:
- https://developer.chrome.com/blog/remote-debugging-port

Key takeaways:

1. From Chrome 136, remote debugging switches behavior changed for default profile dirs.
2. Automation should use non-standard user-data-dir directories.
3. Dedicated automation profile directories improve reliability and security isolation.

Project actions:

- Enforced dedicated automation profile path in config validation.
- Explicitly block default `User Data` paths for Chrome/Brave/Edge.
- Added dual persistent profile fallback (`primary` + `backup`).

## 4) Chrome for Testing Guidance

Source:
- https://developer.chrome.com/blog/chrome-for-testing

Key takeaways:

1. Standard user Chrome auto-update can destabilize reproducible automation.
2. Pinned automation browser binaries improve deterministic behavior.
3. Matching browser + driver lifecycle is critical for startup reliability.

Project recommendation:

- Consider migrating long-term bot runtime from regular Brave to pinned Chrome-for-Testing in a controlled environment if policy allows.

## 5) Google Sheets API Limits & Backoff Guidance

Source:
- https://developers.google.com/workspace/sheets/api/limits

Key takeaways:

1. Per-minute read/write quotas exist and can produce 429.
2. Exponential backoff with jitter is recommended.
3. Keep payloads reasonably sized; reduce API call count where possible.

Project actions:

- Retry wrappers with exponential backoff in sheet service.
- Reduced final-write calls using row-level batch updates.

## 6) Sheets Batch Update Guidance

Source:
- https://developers.google.com/workspace/sheets/api/guides/batchupdate

Key takeaways:

1. Group updates to reduce request volume and improve consistency.
2. Batch requests are atomic per request body.

Project actions:

- Added `update_row_cells_safe()` to write status + delivery state together when finalizing row completion.

## 7) Reliability Gaps Still Governed by External Systems

Despite hardening, absolute reliability is still constrained by:

1. WhatsApp login and QR requirements.
2. Live WhatsApp UI changes.
3. Browser binary/channel updates and local OS constraints.
4. Network and remote API variability.

Mitigation posture:

- Fail-safe idempotent design
- Persistent state journals
- Structured heartbeat and event telemetry
- Multi-profile browser fallback
- Automated test suite and operational runbook

## 8) Next Improvements to Reach Higher Operational Maturity

1. Heartbeat watchdog auto-restart supervisor.
2. Alerting integration for repeated startup/send failures.
3. Periodic profile health check command.
4. Runtime SLO dashboard from `.bot_events.jsonl`.
5. Optional canary-mode sender to detect UI changes before production cycle.

---

Last updated: 2026-04-06

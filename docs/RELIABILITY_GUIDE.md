# Reliability Guide (April 2026)

This document explains the current reliability architecture, operational workflow, diagnostics, and hardening roadmap for the WhatsApp + Google Sheets bot.

## 1) Reliability Objectives

The bot is designed to ensure:

1. A submission row is delivered exactly once per configured target.
2. A row is marked `Bot Details Sent = TRUE` only after all required targets are delivered.
3. Duplicate sends are prevented across retries and process restarts.
4. Browser startup failures degrade gracefully through fallback profiles.
5. Runtime health and failures are observable from machine-readable files.

## 2) Current Guarantees

### 2.1 Delivery idempotency

- A durable journal (`.delivery_journal.json`) records per-row delivered targets.
- Runtime cache avoids re-send within the same process cycle.
- Existing sheet state (`Bot Delivery State`) is merged with journal and cache before deciding pending targets.

### 2.2 Completion criteria

- `Bot Details Sent` is set to `TRUE` only after both strict targets are delivered:
  - `Ibrahim` -> `+923300301917`
  - `Muazzam` -> `+923055375994`

### 2.3 Single process safety

- Lock file (`.submission_bot.lock`) prevents concurrent duplicate bot instances.
- Stale lock cleanup is supported when the recorded process is no longer running.

### 2.4 Browser startup fallback chain

Startup attempts in order:

1. Primary persistent profile: `selenium_data_dir`
2. Secondary persistent profile: `selenium_data_dir_backup`
3. Temporary profile (if enabled)
4. No-profile mode (if enabled)

This reduces hard failures from `SessionNotCreatedException`/`DevToolsActivePort` crashes.

### 2.5 Structured observability

- `.bot_heartbeat.json`: liveness, uptime, counters, last error.
- `.bot_events.jsonl`: append-only event stream for startup, send success/failure, row completion, and loop errors.
- Failure screenshots:
  - `chat_title_mismatch.png`
  - `send_failure_<target>_<attempt>.png`

## 3) Web-Researched Best Practices Applied

### Selenium (official docs)

Applied:

- Explicit wait style patterns for dynamic UIs.
- Retry + re-locate element pattern for unstable DOM states.
- Session recovery path for invalid/disconnected session conditions.
- Avoiding fixed sleeps as primary synchronization mechanism.

Reference:
- https://www.selenium.dev/documentation/webdriver/waits/
- https://www.selenium.dev/documentation/webdriver/troubleshooting/errors/

### Chrome/Chromium automation guidance

Applied:

- Use non-default user-data directories for automation profiles.
- Keep dedicated automation profile outside default browser `User Data` path.

Reference:
- https://developer.chrome.com/blog/remote-debugging-port
- https://developer.chrome.com/blog/chrome-for-testing

### Google Sheets quota/reliability guidance

Applied:

- Exponential backoff retry wrappers for sheet read/write/auth operations.
- Reduced write operations using row-level batch updates for final status writes.

Reference:
- https://developers.google.com/workspace/sheets/api/limits
- https://developers.google.com/workspace/sheets/api/guides/batchupdate

## 4) Runtime Files and Their Purpose

- `bot.log`: human-readable chronological logs.
- `.delivery_journal.json`: persistent idempotency state.
- `.bot_heartbeat.json`: current process health snapshot.
- `.bot_events.jsonl`: machine-readable event audit trail.
- `.submission_bot.lock`: active process lock.

## 5) Operational Runbook

### Start

1. Close extra bot terminals.
2. Start `run_bot.bat`.
3. If QR is requested (fallback profile), scan once.
4. Keep one bot instance running.

### Verify health

- Check `.bot_heartbeat.json` updates every ~10 seconds.
- Ensure `last_error` is empty during healthy operation.
- Inspect `.bot_events.jsonl` for `send_success` and `row_marked_done` events.

### Verify correctness per row

For each new row:

1. Exactly one success event for Ibrahim.
2. Exactly one success event for Muazzam.
3. Then one `row_marked_done` event.
4. Sheet row updates to `Bot Details Sent = TRUE`.

## 6) Current Known External Limits

These cannot be fully eliminated in code:

- WhatsApp login state and QR requirement are external/auth-state dependent.
- WhatsApp UI DOM can change without notice.
- Local browser installation can become unstable after updates or user profile corruption.
- Network outages and temporary API quota spikes.

## 7) Improvement Roadmap (Next Hardening Layer)

1. Add watchdog auto-restart wrapper driven by heartbeat staleness.
2. Add send attempt correlation IDs in logs/events for easier forensic tracing.
3. Add adaptive poll interval (slow down on empty cycles, speed up near active windows).
4. Add proactive profile validation command (startup preflight).
5. Add optional alert channel (desktop toast or Telegram) on repeated init failures.

## 8) Testing Strategy

### Automated tests

Current suite validates:

- strict target enforcement
- journal idempotency and restart semantics
- startup fallback logic
- sheet batch update call shape
- telemetry helper behavior

Run:

```bash
python ops_test_suite.py
```

### Manual acceptance (required)

1. Run bot and authenticate WhatsApp.
2. Submit at least 3 new rows.
3. Confirm no duplicate sends for either target.
4. Confirm each row marked `TRUE` only after both targets are sent.

## 9) Incident Playbook

### Symptom: repeated startup crash (`DevToolsActivePort`)

- Let bot fallback to secondary profile automatically.
- If both persistent profiles fail, temp fallback can run and request QR.
- If persistent failures continue, rotate profile directory manually and re-auth.

### Symptom: send retries/failures

- Check screenshots + `.bot_events.jsonl` for per-attempt context.
- Validate WhatsApp search UI is available and contacts exist by exact names.
- Verify no overlapping manual user actions during send attempts.

### Symptom: row not moving to TRUE

- Check `Bot Delivery State` and journal consistency.
- Verify both targets listed as delivered in logs/events.
- Verify Google Sheets write path is healthy (quota/backoff warnings).

## 10) Compliance Rules (Hard Safety)

- Recipients are locked to two targets only.
- Any config mismatch in target names/numbers causes startup validation failure.
- `.env` target override is blocked unless explicitly enabled with:
  - `ALLOW_TARGETS_ENV_OVERRIDE=1`

---

Last updated: 2026-04-06

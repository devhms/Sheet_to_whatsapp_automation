# Operations Runbook

This runbook is for daily operation, diagnostics, and recovery of the WhatsApp submission bot.

## 1) Start Procedure

1. Ensure no duplicate instance is running.
2. Launch: `run_bot.bat`
3. Watch logs in terminal and `bot.log`.
4. If QR is requested, scan once for the active profile window.

## 2) Live Health Checks

### Heartbeat

Read `./.bot_heartbeat.json`:

- `ts` should keep updating.
- `uptime_seconds` should increase.
- `last_error` should remain empty in healthy state.

### Event stream

Read `./.bot_events.jsonl`:

- expect `bot_started`
- expect `send_success` events for each target
- expect `row_marked_done` after both sends

## 3) Correctness Checks

For each new report row:

1. One send to Ibrahim.
2. One send to Muazzam.
3. Then row marked done (`Bot Details Sent = TRUE`).

If a row stalls, inspect `Bot Delivery State`, `.delivery_journal.json`, and events.

## 4) Common Failure Modes

### A) Startup crash (`DevToolsActivePort`)

Expected handling:

- primary profile fails
- secondary persistent profile starts
- if needed, fallback to temp profile

Actions:

1. Close all manual Brave windows.
2. Re-run bot.
3. Scan QR for fallback profile if requested.

### B) Login timeout

Cause:

- QR not scanned within timeout or session invalid.

Actions:

1. Re-run bot.
2. Scan QR in shown profile window quickly.

### C) Search-box element not found

Expected handling:

- fallback selector + keyboard shortcut attempts
- refresh/retry path in send loop

Actions:

1. Keep browser focused and avoid manual typing during send.
2. Review screenshots and event log for target attempt.

### D) Google Sheets quota / transient errors

Expected handling:

- retry + exponential backoff

Actions:

1. Keep bot running and allow retries.
2. If sustained failures, verify API quota dashboard.

## 5) Recovery Procedure

1. Stop bot.
2. Confirm no extra bot instance is active.
3. Restart bot.
4. Verify heartbeat + events resume.

Do not delete `.delivery_journal.json` unless you intentionally want to lose idempotency memory.

## 6) Files to Inspect During Incident

- `bot.log`
- `.bot_heartbeat.json`
- `.bot_events.jsonl`
- `.delivery_journal.json`
- `send_failure_*.png`
- `chat_title_mismatch.png`

## 7) Hard Safety Rules

- Targets are strict and validated at startup.
- Any mismatch in names/numbers should block startup.
- Only one bot process allowed.

## 8) Preventive Maintenance

Weekly:

1. Run `python ops_test_suite.py`
2. Confirm dependencies up to date in controlled manner.
3. Verify fallback profile can still log in.

Monthly:

1. Re-check browser/driver behavior after updates.
2. Review event log trends and recurring failure patterns.

---

Last updated: 2026-04-06

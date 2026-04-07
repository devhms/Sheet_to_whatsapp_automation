# Sheet to WhatsApp Automation

Production-focused automation that reads Google Sheets submissions and delivers WhatsApp notifications with strong delivery guarantees, profile/session persistence hardening, and operational observability.

## Why this project exists

This bot solves a common operations problem: submissions are logged in a Google Sheet, but people still need timely WhatsApp notifications and follow-up workflows.

This codebase is built to be resilient under real-world conditions:

- flaky browser startup
- WhatsApp Web DOM changes
- intermittent Google API failures
- accidental duplicate runs
- restart safety without duplicate sends

## Core workflows

- `submission_bot.py`
  - Polls Google Sheets for new rows
  - Sends structured WhatsApp notifications to strict recipients
  - Marks a row complete only after all required recipients receive delivery

- `jamiat_bot.py ghost`
  - Finds members who did not submit today
  - Sends group reminder list

- `jamiat_bot.py scanner`
  - Detects red-flag rows (missed prayers)
  - Notifies admin and marks `Admin_Notified`

- `jamiat_bot.py reminder`
  - Sends a generic daily reminder message to group

- `setup_sheet.py`
  - Applies formulas for scoring/flags in the target sheet

## Reliability features

- strict recipient safety checks at startup (`Ibrahim`, `Muazzam`)
- idempotent delivery journal (`.delivery_journal.json`)
- row-level completion semantics (`Bot Details Sent = TRUE` only after both targets)
- single-instance lock (`.submission_bot.lock`)
- dual persistent browser profiles (`selenium_data_dir` + `_backup`)
- last-working profile hint (`<selenium_data_dir>_active_profile.txt`)
- phone-first direct delivery with search fallback
- expanded selector strategy for WhatsApp UI variants
- exponential backoff for Google Sheets read/write/auth
- structured telemetry:
  - `.bot_heartbeat.json`
  - `.bot_events.jsonl`
  - failure screenshots (`send_failure_*.png`, `chat_title_mismatch.png`)

## Requirements

- Windows (project scripts are `.bat` based)
- Python 3.10+
- Google service account with Sheets + Drive API access
- A dedicated Selenium profile directory (outside default browser `User Data`)

## Quick start

1) Clone

```bash
git clone https://github.com/devhms/Sheet_to_whatsapp_automation.git
cd Sheet_to_whatsapp_automation
```

2) Setup environment

```bash
setup.bat
```

This creates `venv`, installs dependencies, and prepares `.env` from `.env.example` if needed.

3) Configure

- Place `service_account.json` in project root
- Edit `config.json`
- Optionally override with `.env`

Minimal `config.json` shape:

```json
{
  "sheet_url": "https://docs.google.com/spreadsheets/d/YOUR_ID/edit",
  "targets": {
    "Ibrahim": "+923300301917",
    "Muazzam": "+923055375994"
  },
  "all_members": ["Ibrahim", "Muazzam"],
  "group_target": "Your Group Name",
  "admin_number": "+923XXXXXXXXX",
  "form_link": "https://forms.google.com/your-form",
  "selenium_data_dir": "C:/Users/hafiz/.jamiat_bot_selenium_data_v2",
  "poll_interval_seconds": 30,
  "whatsapp_qr_timeout": 300,
  "log_level": "INFO"
}
```

4) Run

```bash
run_bot.bat
```

## Common commands

```bash
run_bot.bat
check_missing.bat
scan_flags.bat
send_reminder.bat
apply_formulas.bat
venv\Scripts\python.exe inspect_headers.py
venv\Scripts\python.exe ops_test_suite.py
```

## Project structure

```text
.
├── src/
│   ├── config.py
│   ├── logger.py
│   ├── messages.py
│   ├── sheet_service.py
│   └── whatsapp_service.py
├── tests/
├── docs/
├── submission_bot.py
├── jamiat_bot.py
├── setup_sheet.py
├── ops_test_suite.py
├── config.json
├── .env.example
└── README.md
```

## Configuration notes

- `config.json` is the primary source of truth.
- `.env` can override selected keys (see `src/config.py`).
- `TARGETS` env override is blocked by default for safety unless `ALLOW_TARGETS_ENV_OVERRIDE=1`.

## Security and compliance defaults

- credentials files are gitignored (`service_account.json`, `credentials.json`, `.env`)
- target recipient mismatch fails fast on startup
- default browser user-data directories are blocked for Selenium profile path

## Troubleshooting

### QR appears repeatedly

- Ensure startup is using persistent profile (check logs)
- Close all Brave windows before bot start
- Keep `selenium_data_dir` dedicated and stable
- Avoid temp-profile runs for production session continuity

### Startup crash: `DevToolsActivePort`

- Bot auto-attempts primary then backup persistent profile
- If both fail, inspect profile health and rotate broken directory manually

### Send failures due to search box

- Direct recipients now use phone route first
- Search is still used as fallback and for group/name-based flows
- Inspect `send_failure_*.png` for current DOM state

### Sheets write/read issues

- Built-in retries with exponential backoff are applied
- Confirm service account has access to the spreadsheet

## Testing and verification

Run full smoke tests:

```bash
venv\Scripts\python.exe ops_test_suite.py
```

Covers:

- syntax compile
- unit tests
- strict target validation
- idempotency journal restart behavior
- Selenium startup probe
- telemetry helper integrity

## Operations and deep docs

- `docs/RELIABILITY_GUIDE.md`
- `docs/OPERATIONS_RUNBOOK.md`
- `docs/WEB_RESEARCH_SUMMARY_APRIL_2026.md`
- `docs/SESSION_PERSISTENCE_AND_DELIVERY_FIX_APRIL_2026.md`

## Release

Current release tag: `v1.0.0`

## License

Private project. All rights reserved.

# Sheet_to_whatsapp_automation

Automated WhatsApp notifications for daily audit reports, powered by Google Sheets and Selenium.

Project codename in local folder: `fiery-mare`.

## Features

- **Submission Bot** - Monitors Google Sheets for new entries and sends WhatsApp notifications
- **Ghost Hunter** - Identifies members who haven't submitted their daily reports
- **Red Flag Scanner** - Detects missed prayers and alerts admins
- **Morning Bell** - Sends daily reminders to the group

## April 2026 Reliability Hotfix

- **No forced QR loop by default** - Startup now uses persistent profiles only (`primary` then `_backup`) in `submission_bot.py`
- **Sticky profile preference** - Last successful persistent profile is remembered in `<selenium_data_dir>_active_profile.txt`
- **Higher delivery precision** - Direct targets are sent phone-first (`/send?phone=...`) with chat-search fallback only when needed
- **Stronger WhatsApp selector coverage** - Search locator set now supports both `div[contenteditable]` and `input[type="search"]` variants
- **Operational safety** - Temporary/no-profile startup remains available in service code, but is disabled in production flow to preserve session continuity

## Quick Start

### 1. Setup
```bash
# Run the setup script
setup.bat

# Or manually:
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

**Copy and edit `.env`:**
```bash
copy .env.example .env
```

Fill in:
- `GOOGLE_SERVICE_ACCOUNT_FILE` - Path to your service account JSON
- `GOOGLE_SHEET_URL` - Your Google Sheet URL
- `WHATSAPP_GROUP_TARGET` - WhatsApp group name
- `WHATSAPP_ADMIN_NUMBER` - Admin phone number
- `SELENIUM_DATA_DIR` - Custom persistent browser profile path (must be outside AppData default browser profile)
- `TARGETS` - Name:phone pairs for notifications
- `ALL_MEMBERS` - Comma-separated member list

**Edit `config.json`:**
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
    "selenium_data_dir": "C:/Users/hafiz/.jamiat_bot_selenium_data_v2"
}
```

### 3. Get Google Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable Google Sheets API & Drive API
3. Create Service Account → Download JSON key
4. Save as `service_account.json` in project root
5. Share your Google Sheet with the service account email

### 4. Run

```bash
# Submission Bot (monitors sheet continuously)
run_bot.bat

# Ghost Hunter (check missing submissions)
check_missing.bat

# Red Flag Scanner (check missed prayers)
scan_flags.bat

# Send Reminder
send_reminder.bat

# Apply Formulas to Sheet
apply_formulas.bat

# Inspect Sheet Headers
venv\Scripts\python.exe inspect_headers.py
```

## Project Structure

```
fiery-mare/
├── src/                        # Core modules
│   ├── __init__.py
│   ├── config.py              # Configuration with .env support
│   ├── logger.py              # Logging setup
│   ├── sheet_service.py       # Google Sheets service (google-auth)
│   ├── whatsapp_service.py    # WhatsApp Web automation
│   └── messages.py            # Message templates
├── submission_bot.py          # Main submission monitor
├── jamiat_bot.py              # Ghost/Scanner/Reminder modules
├── setup_sheet.py             # Apply formulas to sheet
├── inspect_headers.py         # Utility to check sheet headers
├── config.json                # Configuration
├── .env                       # Environment variables (gitignored)
├── .env.example               # Template for .env
├── requirements.txt           # Python dependencies
├── setup.bat                  # One-click setup
├── run_bot.bat                # Run submission bot
├── check_missing.bat          # Run ghost hunter
├── scan_flags.bat             # Run red flag scanner
├── send_reminder.bat          # Send daily reminder
├── apply_formulas.bat         # Apply sheet formulas
└── .gitignore                 # Git ignore rules
```

## Architecture

### Modern Stack
- **google-auth** instead of deprecated `oauth2client`
- **python-dotenv** for environment variable management
- **RotatingFileHandler** for log management
- **Multi-selector fallback** for WhatsApp Web (handles UI changes)
- **Session persistence** via `user-data-dir` (scan QR once)
- **Error recovery** with exponential backoff and session re-init
- **Idempotent delivery tracking** using `Bot Delivery State` column
- **Single-instance lock** to prevent duplicate bot runs
- **Dual persistent profile fallback** (`selenium_data_dir` and `_backup`) with last-working profile hint
- **Phone-first delivery routing** with search fallback for resilient sends
- **Operational telemetry** via `.bot_heartbeat.json` and `.bot_events.jsonl`
- **Type hints** throughout codebase

### Security
- Credentials in `.env` (never committed)
- Service account JSON gitignored
- No hardcoded secrets
- Config validation on startup

## Troubleshooting

### QR Code not scanning
- Close all Brave windows completely and run bot again
- Keep `selenium_data_dir` on a dedicated folder (not Brave default AppData profile)
- If profile got corrupted: stop bot, rename `C:\Users\hafiz\.jamiat_bot_selenium_data_v2`, then login once again
- Confirm you are not launching temp-profile mode; production startup uses persistent profiles only

### QR shown every restart
- Check startup logs; you should see `primary persistent profile` or `secondary persistent profile`
- If you ever see `temporary profile`, that run is intentionally ephemeral and will require fresh QR
- Keep Brave closed before startup so lock files can be cleaned and persistent profile can open

### Sheet connection fails
- Verify `service_account.json` exists and is valid
- Share sheet with service account email
- Check sheet URL in config

### WhatsApp selectors not working
- The bot tries multiple selectors automatically
- Update selectors in `src/whatsapp_service.py` if WhatsApp UI changes
- Direct targets now bypass sidebar search by using phone URL route first

### Runtime observability
- ` .bot_heartbeat.json` shows current liveness, uptime, and send stats
- `.bot_events.jsonl` stores structured event records (`send_success`, `send_failure`, `row_marked_done`, `loop_error`)
- Failure screenshots are saved as `send_failure_<target>_<attempt>.png` and `chat_title_mismatch.png`

### Module not found errors
- Run `setup.bat` to ensure venv is created
- Activate venv: `venv\Scripts\activate`

## Deep Reliability Docs

- `docs/RELIABILITY_GUIDE.md` - End-to-end reliability architecture, guarantees, limits, and roadmap
- `docs/OPERATIONS_RUNBOOK.md` - Day-to-day operation and incident handling runbook
- `docs/WEB_RESEARCH_SUMMARY_APRIL_2026.md` - External research findings and how they map to implementation choices
- `docs/SESSION_PERSISTENCE_AND_DELIVERY_FIX_APRIL_2026.md` - Root cause analysis, implemented fix, and verification evidence

## License

Private project - All rights reserved

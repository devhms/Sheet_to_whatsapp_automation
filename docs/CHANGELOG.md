# Changelog

All notable changes to this project are documented in this file.

## [1.0.0] - 2026-04-07

### Added

- Initial production-ready release of the Google Sheets to WhatsApp automation system.
- Submission processing bot with idempotent row delivery and completion semantics.
- Ghost Hunter, Red Flag Scanner, and Reminder workflows.
- Dedicated Google Sheets service layer with retry and backoff support.
- WhatsApp Selenium service with startup fallback and recovery logic.
- Strict target validation and startup safety checks.
- Operational telemetry via heartbeat and event streams.
- Reliability documentation suite and operations runbook.
- CI workflow for compile and unit-test validation on push/PR.

### Improved

- Persistent session behavior hardened to reduce repeated QR scans.
- Delivery routing switched to phone-first with robust fallback behavior.
- Search selector coverage expanded for modern WhatsApp UI variants.

### Notes

- This is the first tagged baseline release for `main`.

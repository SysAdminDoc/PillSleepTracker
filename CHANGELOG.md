# Changelog

All notable changes to PillSleepTracker will be documented in this file.

## Unreleased

- Added per-medication schedules, grace-window adherence states, snooze/taken/skipped dose actions, reorder forecasting, and monthly adherence PDF export.
- Added Fitbit/Garmin/Oura sleep CSV import, REM/deep/light staging, bedtime coaching, distinct naps, and MEQ chronotype weighting.
- Added offline interaction screening, prescribing clinician and reference-photo fields, refill and dose-change history, and optional PIN-protected household profiles.
- Added optional passphrase-protected AES-GCM storage and lossless full JSON/CSV backup restore.
- Added active-profile FHIR R4 JSON export with MedicationStatement and sleep Observation resources.
- Added a configurable sync-folder pointer for file synchronizers while keeping local UI settings separate.
- Added a capped, profile-aware audit log with a recent-edits viewer in Settings and lossless backup coverage.
- Added a persisted compact today mode with a dashboard-only shell and guarded 1-5 page quick keys.
- Added optional Windows light/dark palette and accent-color following, applied safely at startup.
- Added optional mood and energy sliders to sleep entries with backward-compatible score weighting.
- Added dashboard Goal Cards for sleep and medication streaks with celebratory completion toasts.
- Added optional local Whisper tiny voice logging with temporary-audio cleanup and medication matching.
- Added configurable local SMTP delivery for a manual seven-day summary without storing passwords.
- Added startup-applied high-contrast mode, 100-150% font scaling, and explicit accessible names for focusable controls.

## [v0.1.0] - %Y->- (HEAD -> main, origin/main, origin/HEAD)

- Changed: Update README.md
- Added: Add files via upload

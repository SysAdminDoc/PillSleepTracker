# Changelog

All notable changes to PillSleepTracker will be documented in this file.

## [v2.1.0] - 2026-08-03

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

## Roadmap archive — 2026-08-10 — ROADMAP.md

<details>
<summary>Original roadmap snapshot</summary>

```markdown
# PillSleepTracker Pro Roadmap

Always-on-top desktop widget (CustomTkinter) that tracks medications and sleep with dashboard, analytics, and CSV/JSON export. Roadmap focuses on reminders, health-data integration, and trustworthy long-term tracking.

## Planned Features

### Reminders & Adherence

### Sleep

### Medications

### Data & Privacy

### UI / Widget

## Competitive Research
- **Medisafe** — mobile leader, reminders + refill + family. Lesson: adopt their snooze-from-notification UX.
- **Sleep as Android** — rich sleep analytics. Lesson: consider adding a simple sound-based sleep cycle detector via mic (opt-in).
- **CareClinic / MyTherapy** — symptom + medication combined. Lesson: optional symptom log boosts "hand this to my doctor" value.
- **Apple Health / Google Health Connect** — central stores. Lesson: export to CSV that Health Connect can import keeps the tool interoperable.

## Nice-to-Haves

## Open-Source Research (Round 2)

### Related OSS Projects
- https://github.com/sxdl/health_tracker — Multi-framework health tracker (PyQt support), steps/heart/sleep.
- https://github.com/raphaelvallat/yasa — Scientific sleep staging library, BSD-3, good algorithmic reference.
- https://github.com/vmiklos/plees-tracker — Android minimal sleep tracker, clean data model.
- https://github.com/thiswillbeyourgithub/SleepTk_pinetime_sleep_tracker — Privacy-first smart alarm for PineTime.
- https://github.com/florisboard/florisboard — Not related but canonical reference for Material 3 adaptive theming in KMP apps.
- https://github.com/EtchDroid/EtchDroid — Shows the sticky-note/compact UX pattern done well on Android.
- https://github.com/Medito/meditofoundation — Mental-wellness app with habit streak UI patterns worth studying.
- https://github.com/loop-habits/uhabits — Habit tracker with proven streak/adherence math.

### Features to Borrow
- Smart-alarm light-sleep detection window (SleepTk) — pair with existing Sleep summary card.
- Adherence/streak math from Loop Habits — proper weighted decay vs naive consecutive-day count.
- CSV + JSON export with ISO-8601 timestamps (plees-tracker).
- Sleep hypnogram visualization via YASA spectral features if phone accel+audio is added.
- Low-stock prediction from rolling 7-day take rate (not just "below threshold").
- Time-windowed adherence report: "taken within ±30 min of schedule" vs just "taken today".
- Apple Health / Google Fit import for passive sleep start/stop (plees-tracker model).
- "Why did I skip?" optional 1-tap tag on missed doses (travel/asleep/nausea/out-of-stock).

### Patterns & Architectures Worth Studying
- **Single SQLite table per entity + views for computed stats** — keeps queries fast for always-on-top widgets.
- **Deterministic streak calculation in SQL** — window-function based, survives timezone shifts (Loop Habits approach).
- **Passive-first UX** — plees-tracker's auto-stop timer on phone-pickup; avoids the "forgot to log sleep" problem.
- **Scientific backend optional** — YASA-as-library for power users, rule-based score for 95% case.
- **Compact widget sizing** (EtchDroid) — the "sticky-note" aesthetic already in-project benefits from strict 320x480 min-max breakpoints.
```

</details>

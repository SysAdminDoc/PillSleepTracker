# PillSleepTracker Pro Roadmap

Always-on-top desktop widget (CustomTkinter) that tracks medications and sleep with dashboard, analytics, and CSV/JSON export. Roadmap focuses on reminders, health-data integration, and trustworthy long-term tracking.

## Planned Features

### Reminders & Adherence
- Per-medication schedule with native Windows toast reminder
- Snooze / taken / skipped actions from toast
- Streak protection — allowable grace window before missed dose counts
- Monthly adherence export (PDF) suitable for handing to a doctor
- Low-stock reorder reminder with configurable lead time

### Sleep
- Wearable import (Fitbit / Garmin / Oura via CSV drop)
- Sleep staging (REM/Deep/Light) when imported
- Bedtime consistency coach — recommends target bedtime based on rolling variance
- Nap tracking distinct from main sleep block
- Chronotype quick-assessment quiz (MEQ) influencing score weights

### Medications
- Interaction checker (RxNorm + DrugBank free tier or offline dataset)
- Refill history + prescribing clinician field
- Dose titration tracker (log dose changes over time with notes)
- Photo of pill (for identification on travel)
- Multi-profile support (household members with PIN)

### Data & Privacy
- Optional AES-encrypted data file
- Full JSON round-trip import (already half present) + CSV round-trip
- HL7 FHIR `MedicationStatement` + `Observation` export
- iCloud / OneDrive / Syncthing folder pointer for multi-device sync
- Audit log (every edit with timestamp) viewable in Settings

### UI / Widget
- Compact "today" mode (even smaller than current widget) and expanded mode
- Per-page quick keys (1–5 jumps to Dashboard / Meds / Sleep / Stats / Settings)
- System theme follow (accent color from Windows)

## Competitive Research
- **Medisafe** — mobile leader, reminders + refill + family. Lesson: adopt their snooze-from-notification UX.
- **Sleep as Android** — rich sleep analytics. Lesson: consider adding a simple sound-based sleep cycle detector via mic (opt-in).
- **CareClinic / MyTherapy** — symptom + medication combined. Lesson: optional symptom log boosts "hand this to my doctor" value.
- **Apple Health / Google Health Connect** — central stores. Lesson: export to CSV that Health Connect can import keeps the tool interoperable.

## Nice-to-Haves
- Voice log ("took my vitamin D") via local whisper-tiny
- Mood / energy 1–5 slider tied to sleep score
- Weekly email summary (local SMTP send)
- Apple Watch / Fitbit "tap when taken" via companion
- Goal cards (e.g. "7 days of 7+ hours") with celebratory toast
- Accessibility: high-contrast theme, larger font scale, screen-reader labels

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

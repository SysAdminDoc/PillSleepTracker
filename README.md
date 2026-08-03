# PillSleepTracker Pro

Designed to sit on your desktop like Microsoft Sticky Notes -- compact, always-on-top.

## Features

### Dashboard (Home)
- Time-of-day greeting with today's date
- At-a-glance stat cards: Today's Meds, Last Sleep, Pill Streak
- **Quick Take** grid: one-click pill logging with undo, colour-coded by medication
- Sleep summary card with score badge and streak counter
- Low stock alerts for medications running low
- Scheduled dose reminders with grace windows, snooze/taken/skipped actions, and reorder forecasting

### Medications
- Full CRUD: add, edit, delete medications
- Fields: Name, Dosage, Frequency, Time of Day, Colour Tag, Supply Count, Low Stock Warning, Prescribing Clinician, Reference Photo, Notes
- 10 colour options for visual differentiation
- Supply tracking with automatic decrement on take
- Refill history and dose titration history with notes
- Small offline interaction screen with an explicit pharmacist-review disclaimer
- Household profiles with optional PIN protection and isolated medication, log, and sleep data
- Active/Inactive toggle for pausing medications
- One-click Take/Undo from both Dashboard and Meds page

### Sleep Tracker
- **Quick Log** presets: 5h, 6h, 7h, 8h, 9h buttons (ending now)
- Manual entry: date, bedtime, wake time, quality slider
- Sleep quality scale: 1-5 (Terrible to Excellent)
- **Sleep Factors** checkboxes: Caffeine, Alcohol, Exercise, Screen Time, Stress, Nap, Late Meal, Medication
- Notes field for each entry
- **Sleep Score** (0-100) calculated from duration, quality, and bedtime consistency
- Optional Mood and Energy 1-5 sliders are stored with each manual entry and gently tune the score
- Recent entries list with colour-coded quality and score
- Fitbit, Garmin, and Oura CSV import with REM/deep/light stage summaries
- Bedtime consistency coaching, distinct nap logging, and a five-question MEQ chronotype profile

### Analytics (Stats)
- Summary stat cards: Avg Sleep, Avg Quality, Adherence %, Avg Score
- Time range selector: 7 / 14 / 30 days
- **Medication Adherence** bar chart (green/amber/red by completion %)
- **Sleep Duration** line chart with area fill and 7-9h optimal zone
- **Sleep Quality & Score** dual overlay (scatter + line)
- **Sleep Factor Frequency** horizontal bar chart (colour-coded beneficial vs harmful)
- Monthly adherence PDF export formatted for clinician review

### Settings
- Window opacity slider (30-100%)
- Always-on-top toggle
- Optional Windows theme and accent following, applied on startup
- Profile switcher and optional PIN-protected household profiles
- Five-question MEQ chronotype quiz used to personalize sleep-score weighting
- Optional AES-GCM encrypted data file with a passphrase that is never stored
- Configurable data-folder pointer for local OneDrive, iCloud, or Syncthing-style synchronization
- Timestamped audit log of edits, imports, profile changes, and security settings, viewable per active profile in Settings
- Export data as JSON backup
- Export pill log as CSV
- Export/import a lossless full CSV backup
- Export the active profile as a clinician-ready FHIR R4 JSON collection (MedicationStatement + sleep Observation resources)
- Import data from JSON (supports v1 format migration)
- Open data folder shortcut
- Reset all data (danger zone)

### Widget Behaviour
- **Always-on-top** floating window with pin toggle
- **Compact today mode** for a smaller dashboard-only widget, with an Expand control for the full shell
- **Keyboard quick keys**: 1 Dashboard, 2 Meds, 3 Sleep, 4 Stats, 5 Settings (when a form field is not focused)
- **Draggable** custom title bar
- **Remembers** window position, size, opacity, and last active page
- **System tray** icon with show/quit menu (Windows)
- **Auto-saves** settings every 30 seconds
- **Toast notifications** for actions (taken, undone, logged, etc.)
- **Sidebar navigation** with live clock

## Requirements

- **Python 3.8+** (3.10+ recommended)
- **Windows 10/11** (also works on Linux/macOS)

All Python packages are auto-installed on first launch.

## Quick Start

### Option A: Batch File (Recommended)
```
Double-click:  Launch-PillSleepTracker.bat
```

### Option B: PowerShell
```powershell
.\Launch-PillSleepTracker.ps1
```

### Option C: Direct
```bash
pip install customtkinter matplotlib Pillow pystray cryptography
python PillSleepTracker.py
```

For a Windows distributable, build the onedir artifact with PyInstaller:
```powershell
python -m PyInstaller --noconfirm --clean --windowed --name PillSleepTracker --icon icon.ico --exclude-module setuptools_scm --hidden-import numpy._core._exceptions PillSleepTracker.py
```
The launcher installs the optional WinRT notification components when native Windows toast actions are available.

## Data Storage

| File | Location | Contents |
|------|----------|----------|
| `tracker_data.json` | `%APPDATA%\PillSleepTracker\` | Profiles, medications, pill log, sleep log; optionally AES-GCM encrypted |
| `settings.json` | `%APPDATA%\PillSleepTracker\` | Window state, preferences |

Settings > Choose sync folder can point `tracker_data.json` at a folder managed by OneDrive, iCloud Drive, Syncthing, or another file synchronizer. The settings file stays local. The app asks before adopting an existing canonical data file; do not edit the JSON concurrently on multiple devices.

Linux/macOS: `~/PillSleepTracker/`

## Architecture

```
PillSleepTrackerPro (CTk main window)
  +-- Custom title bar (drag, pin, minimize, close)
  +-- Sidebar (navigation + clock)
  +-- Content area (page switching)
       +-- DashboardPage (stat cards, quick take, sleep summary, alerts)
       +-- MedicationsPage (CRUD list, refills, dose history, interaction screen)
       +-- SleepPage (quick log, manual entry, history)
       +-- AnalyticsPage (4 matplotlib charts + summary stats)
       +-- SettingsPage (appearance, profiles, data management, about)
  +-- ToastManager (overlay notifications)
  +-- DataManager (JSON persistence, query helpers, scoring)
```

## Design Tokens

The app uses a centralised theme class `T` with GitHub-Dark inspired colours:

| Token | Hex | Usage |
|-------|-----|-------|
| `BG` | `#0d1117` | Main background |
| `SURFACE` | `#161b22` | Elevated surfaces |
| `CARD` | `#1c2333` | Card backgrounds |
| `BLUE` | `#58a6ff` | Primary accent |
| `GREEN` | `#3fb950` | Success / taken |
| `RED` | `#f85149` | Danger / alerts |
| `PURPLE` | `#bc8cff` | Sleep accent |
| `AMBER` | `#d29922` | Warnings / streaks |

## Sleep Score Algorithm

The sleep score (0-100) is a composite of three factors, with the duration and quality balance adjusted slightly by the optional MEQ chronotype profile:

- **Duration (0-40 pts)**: Gaussian curve centred on 8 hours (480 min) with sigma of 90 min. Sleeping exactly 8 hours scores maximum points; deviations reduce the score smoothly.
- **Quality (0-40 pts)**: Subjective rating multiplied by 8. An "Excellent" (5) rating gives the full 40 points.
- **Consistency (0-20 pts)**: Calculated from the standard deviation of your bedtimes over the past 7 nights. Lower variance (more consistent bedtime) gives higher points.

Without a chronotype profile, the default weights are 40/40/20. The quiz shifts those weights modestly toward a more morning- or evening-oriented pattern; it does not diagnose a sleep disorder.

When Mood or Energy is recorded, the core score is scaled to 80% and the average wellbeing rating contributes the remaining 20 points. Older entries and quick logs without those signals keep the original score calculation.

## Customisation Ideas

- Edit the `T` class to change any colour across the entire app
- Modify `PILL_COLOURS` to add custom medication colour options
- Adjust `SLEEP_FACTORS` list to add/remove factors relevant to you
- Change the sleep score weights in `calc_sleep_score()` to match your priorities

## Migration from v1

If you have data from the original PillSleepTracker (v1), use Settings > Import Data. The importer automatically handles:
- Renaming `pills` to `medications` and adding UUIDs
- Renaming `pill_log` to `med_log` with proper field mapping
- Preserving all `sleep_log` entries

The full CSV backup uses typed JSON records inside CSV rows so profiles, medication metadata, dose actions, and sleep-stage fields survive a CSV round trip. It is intended for backup/restore, while the shorter Pill Log CSV remains human-readable.

Settings > Export FHIR Bundle creates a FHIR R4 collection for the active profile only, keeping household profiles separate. It includes medication statements and sleep observations; review the generated file before sending it to a clinician or health system.

## License

MIT

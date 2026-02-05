# PillSleepTracker Pro

Designed to sit on your desktop like Microsoft Sticky Notes -- compact, always-on-top.

## Features

### Dashboard (Home)
- Time-of-day greeting with today's date
- At-a-glance stat cards: Today's Meds, Last Sleep, Pill Streak
- **Quick Take** grid: one-click pill logging with undo, colour-coded by medication
- Sleep summary card with score badge and streak counter
- Low stock alerts for medications running low

### Medications
- Full CRUD: add, edit, delete medications
- Fields: Name, Dosage, Frequency, Time of Day, Colour Tag, Supply Count, Low Stock Warning, Notes
- 10 colour options for visual differentiation
- Supply tracking with automatic decrement on take
- Active/Inactive toggle for pausing medications
- One-click Take/Undo from both Dashboard and Meds page

### Sleep Tracker
- **Quick Log** presets: 5h, 6h, 7h, 8h, 9h buttons (ending now)
- Manual entry: date, bedtime, wake time, quality slider
- Sleep quality scale: 1-5 (Terrible to Excellent)
- **Sleep Factors** checkboxes: Caffeine, Alcohol, Exercise, Screen Time, Stress, Nap, Late Meal, Medication
- Notes field for each entry
- **Sleep Score** (0-100) calculated from duration, quality, and bedtime consistency
- Recent entries list with colour-coded quality and score

### Analytics (Stats)
- Summary stat cards: Avg Sleep, Avg Quality, Adherence %, Avg Score
- Time range selector: 7 / 14 / 30 days
- **Medication Adherence** bar chart (green/amber/red by completion %)
- **Sleep Duration** line chart with area fill and 7-9h optimal zone
- **Sleep Quality & Score** dual overlay (scatter + line)
- **Sleep Factor Frequency** horizontal bar chart (colour-coded beneficial vs harmful)

### Settings
- Window opacity slider (30-100%)
- Always-on-top toggle
- Export data as JSON backup
- Export pill log as CSV
- Import data from JSON (supports v1 format migration)
- Open data folder shortcut
- Reset all data (danger zone)

### Widget Behaviour
- **Always-on-top** floating window with pin toggle
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
pip install customtkinter matplotlib Pillow pystray
python PillSleepTracker.py
```

## Data Storage

| File | Location | Contents |
|------|----------|----------|
| `tracker_data.json` | `%APPDATA%\PillSleepTracker\` | Medications, pill log, sleep log |
| `settings.json` | `%APPDATA%\PillSleepTracker\` | Window state, preferences |

Linux/macOS: `~/PillSleepTracker/`

## Architecture

```
PillSleepTrackerPro (CTk main window)
  +-- Custom title bar (drag, pin, minimize, close)
  +-- Sidebar (navigation + clock)
  +-- Content area (page switching)
       +-- DashboardPage (stat cards, quick take, sleep summary, alerts)
       +-- MedicationsPage (CRUD list with take/undo)
       +-- SleepPage (quick log, manual entry, history)
       +-- AnalyticsPage (4 matplotlib charts + summary stats)
       +-- SettingsPage (appearance, data management, about)
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

The sleep score (0-100) is a composite of three factors:

- **Duration (0-40 pts)**: Gaussian curve centred on 8 hours (480 min) with sigma of 90 min. Sleeping exactly 8 hours scores maximum points; deviations reduce the score smoothly.
- **Quality (0-40 pts)**: Subjective rating multiplied by 8. An "Excellent" (5) rating gives the full 40 points.
- **Consistency (0-20 pts)**: Calculated from the standard deviation of your bedtimes over the past 7 nights. Lower variance (more consistent bedtime) gives higher points.

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

## License

MIT

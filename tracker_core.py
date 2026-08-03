"""Pure data and scheduling helpers for PillSleepTracker.

The desktop UI deliberately keeps its persistence format as plain dictionaries.
These helpers operate on those dictionaries so scheduling and export behavior can
be tested without creating a Tk window.
"""

from __future__ import annotations

import csv
import math
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
TIME_ALIASES = {
    "morning": "08:00",
    "afternoon": "13:00",
    "evening": "19:00",
    "night": "22:00",
    "bedtime": "22:00",
}
WEEKDAY_ALIASES = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}
DEFAULT_TIMES = {
    "daily": ("09:00",),
    "twice daily": ("09:00", "21:00"),
    "3x daily": ("08:00", "14:00", "20:00"),
    "every other day": ("09:00",),
    "weekly": ("09:00",),
}


def _as_date(value: date | datetime | str | None, fallback: date | None = None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return fallback or datetime.now().date()


def _as_datetime(value: datetime | date | str | None, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
    return fallback or datetime.now()


def normalize_schedule_times(value: Any, frequency: str = "Daily") -> list[str]:
    """Return validated HH:MM schedule times, preserving user order."""

    if isinstance(value, str):
        parts = re.split(r"[,;\s]+", value.strip()) if value.strip() else []
    elif isinstance(value, Iterable):
        parts = [str(item).strip() for item in value]
    else:
        parts = []

    normalized: list[str] = []
    for part in parts:
        lower = part.lower()
        part = TIME_ALIASES.get(lower, part)
        if not TIME_RE.fullmatch(part):
            raise ValueError(f"Invalid schedule time: {part!r}. Use HH:MM.")
        if part not in normalized:
            normalized.append(part)

    if normalized:
        return normalized
    return list(DEFAULT_TIMES.get(frequency.strip().lower(), ()))


def normalize_schedule_days(value: Any) -> list[int]:
    if isinstance(value, str):
        parts = re.split(r"[,;\s]+", value.strip()) if value.strip() else []
    elif isinstance(value, Iterable):
        parts = list(value)
    else:
        parts = []
    result: list[int] = []
    for part in parts:
        if isinstance(part, int) or (isinstance(part, str) and part.strip().isdigit()):
            weekday = int(part)
        else:
            weekday = WEEKDAY_ALIASES.get(str(part).strip().lower(), -1)
        if weekday not in range(7):
            raise ValueError(f"Invalid weekday: {part!r}.")
        if weekday not in result:
            result.append(weekday)
    return sorted(result)


def _anchor_date(medication: Mapping[str, Any], fallback: date) -> date:
    return _as_date(
        medication.get("schedule_start_date")
        or medication.get("created")
        or medication.get("start_date"),
        fallback,
    )


@dataclass(frozen=True)
class ScheduledDose:
    medication_id: str
    medication_name: str
    scheduled_for: datetime

    @property
    def dose_id(self) -> str:
        return f"{self.medication_id}:{self.scheduled_for:%Y-%m-%d:%H:%M}"

    @property
    def date(self) -> str:
        return self.scheduled_for.strftime("%Y-%m-%d")

    def as_dict(self) -> dict[str, Any]:
        return {
            "dose_id": self.dose_id,
            "med_id": self.medication_id,
            "med_name": self.medication_name,
            "scheduled_for": self.scheduled_for.isoformat(timespec="minutes"),
            "date": self.date,
        }


def scheduled_doses_for_date(
    medication: Mapping[str, Any], day: date | datetime | str | None = None
) -> list[ScheduledDose]:
    """Expand one medication's frequency into concrete doses for a local day."""

    day_value = _as_date(day)
    if not medication.get("active", True):
        return []
    frequency = str(medication.get("frequency", "Daily")).strip().lower()
    if frequency == "as needed":
        return []

    if frequency == "weekly":
        days = normalize_schedule_days(medication.get("schedule_days"))
        if not days:
            days = [_anchor_date(medication, day_value).weekday()]
        if day_value.weekday() not in days:
            return []
    elif frequency == "every other day":
        anchor = _anchor_date(medication, day_value)
        if (day_value - anchor).days % 2:
            return []

    times = normalize_schedule_times(
        medication.get("schedule_times") or medication.get("schedule_time")
        or medication.get("time_of_day", ""),
        str(medication.get("frequency", "Daily")),
    )
    # A single user-provided time is expanded for common multi-dose frequencies.
    if len(times) == 1 and frequency in {"twice daily", "3x daily"}:
        start = datetime.combine(day_value, datetime.strptime(times[0], "%H:%M").time())
        offsets = (12,) if frequency == "twice daily" else (8, 16)
        times = [times[0]] + [(start + timedelta(hours=offset)).strftime("%H:%M") for offset in offsets]

    doses = [
        ScheduledDose(
            str(medication.get("id", "")),
            str(medication.get("name", "Medication")),
            datetime.combine(day_value, datetime.strptime(value, "%H:%M").time()),
        )
        for value in times
    ]
    return sorted({dose.dose_id: dose for dose in doses}.values(), key=lambda dose: dose.scheduled_for)


def _log_matches_dose(log: Mapping[str, Any], dose: ScheduledDose) -> bool:
    if str(log.get("med_id", "")) != dose.medication_id:
        return False
    if log.get("dose_id"):
        return str(log["dose_id"]) == dose.dose_id
    # v1/v2 entries had only a medication and date. Treat one such taken entry
    # as covering the day's first scheduled dose for backward compatibility.
    return str(log.get("date", "")) == dose.date


def latest_dose_action(logs: Sequence[Mapping[str, Any]], dose: ScheduledDose) -> Mapping[str, Any] | None:
    matching = [log for log in logs if _log_matches_dose(log, dose)]
    if not matching:
        return None
    return max(matching, key=lambda log: str(log.get("logged_at", f"{log.get('date', '')} {log.get('time', '')}")))


def _snooze_until(action: Mapping[str, Any]) -> datetime | None:
    value = action.get("snooze_until")
    return _as_datetime(value, None) if value else None


def dose_status(
    dose: ScheduledDose,
    logs: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
    grace_minutes: int = 30,
) -> str:
    now = now or datetime.now()
    action = latest_dose_action(logs, dose)
    if action:
        kind = str(action.get("action", "")).lower()
        if kind in {"taken", "skipped"}:
            return kind
        if kind == "snoozed":
            until = _snooze_until(action)
            if until and until > now:
                return "snoozed"
    if now < dose.scheduled_for:
        return "upcoming"
    if now <= dose.scheduled_for + timedelta(minutes=max(0, int(grace_minutes))):
        return "due"
    return "missed"


def due_doses(
    medications: Sequence[Mapping[str, Any]],
    logs: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
    grace_minutes: int = 30,
) -> list[dict[str, Any]]:
    now = now or datetime.now()
    result: list[dict[str, Any]] = []
    for medication in medications:
        for day in (now.date() - timedelta(days=1), now.date(), now.date() + timedelta(days=1)):
            for dose in scheduled_doses_for_date(medication, day):
                status = dose_status(dose, logs, now, grace_minutes)
                if status in {"due", "snoozed", "missed"}:
                    if status == "missed" and now - dose.scheduled_for > timedelta(hours=24):
                        continue
                    item = dose.as_dict()
                    item["status"] = status
                    item["snooze_until"] = None
                    action = latest_dose_action(logs, dose)
                    if action:
                        item["snooze_until"] = action.get("snooze_until")
                    result.append(item)
    return sorted(result, key=lambda item: item["scheduled_for"])


def adherence_for_day(
    medications: Sequence[Mapping[str, Any]],
    logs: Sequence[Mapping[str, Any]],
    day: date | datetime | str,
) -> tuple[int, int, int]:
    doses = [dose for med in medications for dose in scheduled_doses_for_date(med, day)]
    taken = sum(1 for dose in doses if dose_status(dose, logs, datetime.max, 0) == "taken")
    return taken, len(doses), sum(1 for dose in doses if dose_status(dose, logs, datetime.max, 0) == "skipped")


def adherence_rows(
    medications: Sequence[Mapping[str, Any]],
    logs: Sequence[Mapping[str, Any]],
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day_number in range(1, monthrange(year, month)[1] + 1):
        day = date(year, month, day_number)
        taken, total, skipped = adherence_for_day(medications, logs, day)
        rows.append(
            {
                "date": day.isoformat(),
                "taken": taken,
                "scheduled": total,
                "skipped": skipped,
                "percent": round(taken / total * 100, 1) if total else None,
            }
        )
    return rows


def rolling_take_rate(
    medication_id: str,
    logs: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
    days: int = 7,
) -> float:
    now = now or datetime.now()
    start = now.date() - timedelta(days=max(1, days) - 1)
    taken = 0
    for log in logs:
        if str(log.get("med_id", "")) != str(medication_id) or log.get("action") != "taken":
            continue
        logged = _as_date(log.get("date"), None)
        if logged and start <= logged <= now.date():
            taken += 1
    return taken / max(1, days)


def reorder_alerts(
    medications: Sequence[Mapping[str, Any]],
    logs: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
    lead_days: int = 7,
) -> list[dict[str, Any]]:
    now = now or datetime.now()
    alerts: list[dict[str, Any]] = []
    for medication in medications:
        supply = medication.get("supply")
        if supply is None:
            continue
        try:
            supply = max(0, int(supply))
        except (TypeError, ValueError):
            continue
        rate = rolling_take_rate(str(medication.get("id", "")), logs, now)
        if rate <= 0:
            rate = sum(len(scheduled_doses_for_date(medication, now.date() - timedelta(days=i))) for i in range(7)) / 7
        warning = max(0, int(medication.get("supply_warn", 7) or 0))
        threshold = max(warning, math.ceil(rate * max(0, int(lead_days))))
        if supply <= threshold:
            days_left = round(supply / rate, 1) if rate else None
            alerts.append(
                {
                    "med_id": medication.get("id"),
                    "name": medication.get("name", "Medication"),
                    "supply": supply,
                    "daily_rate": round(rate, 2),
                    "days_left": days_left,
                    "threshold": threshold,
                }
            )
    return sorted(alerts, key=lambda item: (item["days_left"] is None, item["days_left"] or 0, item["name"]))


def export_monthly_adherence_pdf(
    path: str | Path,
    medications: Sequence[Mapping[str, Any]],
    logs: Sequence[Mapping[str, Any]],
    year: int,
    month: int,
    profile_name: str = "Default profile",
) -> Path:
    """Create a compact, printable monthly adherence report."""

    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure

    output = Path(path)
    rows = adherence_rows(medications, logs, year, month)
    scheduled = sum(row["scheduled"] for row in rows)
    taken = sum(row["taken"] for row in rows)
    skipped = sum(row["skipped"] for row in rows)
    with PdfPages(output) as pdf:
        first = Figure(figsize=(8.5, 11), facecolor="white")
        ax = first.add_axes((0.08, 0.08, 0.84, 0.84))
        ax.axis("off")
        ax.text(0, 0.97, "PillSleepTracker Monthly Adherence", fontsize=18, weight="bold", va="top")
        ax.text(0, 0.925, f"{year:04d}-{month:02d}  |  {profile_name}", fontsize=11, va="top")
        ax.text(0, 0.86, "Summary", fontsize=13, weight="bold", va="top")
        overall = f"{taken / scheduled * 100:.1f}%" if scheduled else "No scheduled doses"
        ax.text(0, 0.825, f"Overall adherence: {overall}", fontsize=11, va="top")
        ax.text(0, 0.795, f"Taken: {taken}    Scheduled: {scheduled}    Skipped: {skipped}", fontsize=11, va="top")
        med_text = "\n".join(
            f"• {med.get('name', 'Medication')}  |  {med.get('dosage', '')}  |  {med.get('frequency', 'Daily')}"
            for med in medications
        ) or "No active medications"
        ax.text(0, 0.72, "Tracked medications", fontsize=13, weight="bold", va="top")
        ax.text(0, 0.685, med_text, fontsize=10, va="top", linespacing=1.5)
        ax.text(0, 0.46, "Daily record", fontsize=13, weight="bold", va="top")
        headers = ["Date", "Taken", "Scheduled", "Skipped", "Adherence"]
        table_data = [
            [row["date"], row["taken"], row["scheduled"], row["skipped"], f"{row['percent']:.1f}%" if row["percent"] is not None else "—"]
            for row in rows
            if row["scheduled"] or row["taken"] or row["skipped"]
        ]
        if table_data:
            ax.table(cellText=table_data, colLabels=headers, loc="upper left", bbox=(0, 0.03, 1, 0.39), cellLoc="left")
        else:
            ax.text(0, 0.40, "No scheduled doses were recorded for this month.", fontsize=10, va="top")
        ax.text(0, -0.01, "For personal tracking only. Review medication decisions with a qualified clinician.", fontsize=8, color="#555555", va="bottom")
        pdf.savefig(first, bbox_inches="tight")
    return output


def write_csv_rows(path: str | Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> Path:
    output = Path(path)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return output


def _normalized_row(row: Mapping[str, Any]) -> dict[str, tuple[str, Any]]:
    return {
        re.sub(r"[^a-z0-9]", "", str(key).lower()): (str(key), value)
        for key, value in row.items()
    }


def _row_value(row: Mapping[str, Any], aliases: Sequence[str]) -> tuple[Any, str]:
    normalized = _normalized_row(row)
    for alias in aliases:
        item = normalized.get(re.sub(r"[^a-z0-9]", "", alias.lower()))
        if item and str(item[1]).strip():
            return item[1], item[0]
    return None, ""


def _parse_wearable_datetime(value: Any) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    try:
        numeric = float(text)
        if numeric > 10_000_000_000:
            numeric /= 1000
        if numeric > 1_000_000_000:
            return datetime.fromtimestamp(numeric)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in (
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_duration_minutes(value: Any, field_name: str = "") -> int | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().lower()
    try:
        number = float(text)
        if "second" in field_name.lower() or "second" in text or number >= 10_000:
            return max(0, round(number / 60))
        if "hour" in field_name.lower() or "hour" in text:
            return max(0, round(number * 60))
        return max(0, round(number))
    except ValueError:
        hours = re.search(r"(\d+(?:\.\d+)?)\s*h", text)
        minutes = re.search(r"(\d+(?:\.\d+)?)\s*m", text)
        if hours or minutes:
            return round(float(hours.group(1)) * 60 if hours else 0) + round(float(minutes.group(1)) if minutes else 0)
    return None


def _parse_quality(value: Any) -> int:
    labels = {"terrible": 1, "very poor": 1, "poor": 2, "fair": 3, "good": 4, "excellent": 5, "very good": 5}
    text = str(value or "").strip().lower()
    if text in labels:
        return labels[text]
    try:
        number = float(text)
    except ValueError:
        return 3
    if number <= 1:
        return max(1, min(5, round(number * 5)))
    if number <= 5:
        return max(1, min(5, round(number)))
    return max(1, min(5, round(number / 20)))


def _stage_minutes(row: Mapping[str, Any], aliases: Sequence[str]) -> int | None:
    value, field = _row_value(row, aliases)
    return _parse_duration_minutes(value, field) if value is not None else None


def infer_wearable_provider(headers: Sequence[str], filename: str = "") -> str:
    keys = {re.sub(r"[^a-z0-9]", "", header.lower()) for header in headers}
    name = filename.lower()
    if "calendarDate".lower() in keys or "sleepstarttimestampgmt" in keys or "garmin" in name:
        return "garmin"
    if "bedtimestart" in keys or "totalSleepDuration".lower() in keys or "oura" in name:
        return "oura"
    if "minutesasleep" in keys or "fitbit" in name:
        return "fitbit"
    return "wearable"


def import_wearable_csv(path: str | Path, provider: str | None = None) -> list[dict[str, Any]]:
    """Normalize common Fitbit, Garmin, and Oura sleep CSV exports."""

    input_path = Path(path)
    with input_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        provider = (provider or infer_wearable_provider(headers, input_path.name)).lower()
        entries: list[dict[str, Any]] = []
        for index, row in enumerate(reader):
            start_value, _ = _row_value(row, [
                "start", "start_time", "Start Time", "sleepStartTimestampGMT", "bedtime_start", "sleep_start", "from"
            ])
            end_value, _ = _row_value(row, [
                "end", "end_time", "End Time", "sleepEndTimestampGMT", "bedtime_end", "sleep_end", "to"
            ])
            start = _parse_wearable_datetime(start_value)
            end = _parse_wearable_datetime(end_value)
            date_value, _ = _row_value(row, ["date", "sleep_date", "calendarDate", "Date", "Sleep Date"])
            day = _parse_wearable_datetime(date_value) or start
            if not day:
                continue
            duration_value, duration_field = _row_value(row, [
                "duration_min", "duration_minutes", "Minutes Asleep", "total_sleep_duration", "sleep_duration",
                "totalSleepTime", "sleepTime", "duration", "minutes_slept"
            ])
            duration = _parse_duration_minutes(duration_value, duration_field)
            if duration is None and start and end:
                if end < start:
                    end += timedelta(days=1)
                duration = max(0, round((end - start).total_seconds() / 60))
            if duration is None or duration <= 0:
                continue
            type_value, _ = _row_value(row, ["type", "sleep_type", "is_nap", "nap"])
            is_nap = str(type_value or "").strip().lower() in {"nap", "true", "yes", "1"}
            stages = {}
            for stage, aliases in {
                "rem": ["rem", "rem_minutes", "remSleepSeconds", "rem_sleep_duration", "remDuration"],
                "deep": ["deep", "deep_minutes", "deepSleepSeconds", "deep_sleep_duration", "deepDuration"],
                "light": ["light", "light_minutes", "lightSleepSeconds", "light_sleep_duration", "lightDuration"],
            }.items():
                value = _stage_minutes(row, aliases)
                if value is not None:
                    stages[stage] = value
            quality_value, _ = _row_value(row, ["quality", "Sleep Quality", "sleep_score", "score", "efficiency"])
            quality = _parse_quality(quality_value)
            date_text = day.strftime("%Y-%m-%d")
            bedtime = start.strftime("%H:%M") if start else "--"
            waketime = end.strftime("%H:%M") if end else "--"
            entry = {
                "id": f"wearable:{provider}:{index}:{date_text}",
                "date": date_text,
                "bedtime": bedtime,
                "waketime": waketime,
                "duration_min": duration,
                "quality": quality,
                "factors": [],
                "notes": f"Imported from {provider.title()}",
                "score": calculate_sleep_score(duration, quality),
                "source": provider,
                "source_id": str(index),
                "is_nap": is_nap,
            }
            if stages:
                entry["stages"] = stages
            entries.append(entry)
    return entries


def bedtime_consistency_coach(
    entries: Sequence[Mapping[str, Any]],
    today: date | datetime | str | None = None,
    window_days: int = 14,
) -> dict[str, Any]:
    cutoff = _as_date(today) if today else datetime.now().date()
    selected = [
        entry for entry in entries
        if not entry.get("is_nap") and _as_date(entry.get("date"), cutoff) <= cutoff
    ]
    selected = sorted(selected, key=lambda entry: str(entry.get("date", "")), reverse=True)[:max(1, window_days)]
    minutes: list[int] = []
    for entry in selected:
        try:
            hour, minute = map(int, str(entry.get("bedtime", "")).split(":")[:2])
            value = hour * 60 + minute
            minutes.append(value - 1440 if value > 720 else value)
        except (TypeError, ValueError):
            continue
    if not minutes:
        return {"sample_count": 0, "target_bedtime": None, "variance_minutes": None, "recommendation": "Log a few nights to unlock your bedtime coach."}
    mean = sum(minutes) / len(minutes)
    variance = math.sqrt(sum((value - mean) ** 2 for value in minutes) / len(minutes))
    target = int(round(mean)) % 1440
    target_text = f"{target // 60:02d}:{target % 60:02d}"
    if len(minutes) < 3:
        recommendation = f"Your early target is around {target_text}. Log {3 - len(minutes)} more night(s) for a consistency trend."
    elif variance <= 30:
        recommendation = f"Strong rhythm. Keep bedtime near {target_text} (±30 minutes)."
    else:
        recommendation = f"Bedtimes vary by about {variance:.0f} minutes. Aim for {target_text} within a 30-minute window."
    return {
        "sample_count": len(minutes),
        "target_bedtime": target_text,
        "variance_minutes": round(variance, 1),
        "recommendation": recommendation,
    }


MEQ_QUESTIONS = [
    {"prompt": "When would you feel most ready to start your day naturally?", "options": [("Before 06:30", 5), ("06:30–08:00", 4), ("08:00–09:30", 3), ("09:30–11:00", 2), ("After 11:00", 1)]},
    {"prompt": "When is your best window for focused work?", "options": [("Early morning", 5), ("Late morning", 4), ("Afternoon", 3), ("Evening", 2), ("Late night", 1)]},
    {"prompt": "How easy is it to wake up before 07:00?", "options": [("Very easy", 5), ("Fairly easy", 4), ("Neutral", 3), ("Somewhat difficult", 2), ("Very difficult", 1)]},
    {"prompt": "At what time would you choose your heaviest meal?", "options": [("Before noon", 5), ("Around noon", 4), ("Early afternoon", 3), ("Evening", 2), ("Late evening", 1)]},
    {"prompt": "When would you prefer to exercise?", "options": [("06:00–09:00", 5), ("09:00–12:00", 4), ("12:00–16:00", 3), ("16:00–20:00", 2), ("After 20:00", 1)]},
]


def score_chronotype(answers: Sequence[int]) -> dict[str, Any]:
    values = [max(1, min(5, int(answer))) for answer in answers]
    if not values:
        return {"score": 3.0, "category": "Intermediate"}
    average = sum(values) / len(values)
    if average >= 4.2:
        category = "Morning"
    elif average >= 3.4:
        category = "Mostly morning"
    elif average >= 2.6:
        category = "Intermediate"
    elif average >= 1.8:
        category = "Mostly evening"
    else:
        category = "Evening"
    return {"score": round(average, 2), "category": category}


def calculate_sleep_score(
    duration_min: int,
    quality: int,
    recent_bedtimes: Sequence[str] | None = None,
    chronotype: str | None = None,
) -> int:
    duration = math.exp(-0.5 * ((max(0, duration_min) - 480) / 90) ** 2)
    quality_value = max(1, min(5, int(quality))) / 5
    consistency = 0.5
    if recent_bedtimes and len(recent_bedtimes) >= 3:
        minutes: list[int] = []
        for bedtime in recent_bedtimes:
            try:
                hour, minute = map(int, str(bedtime).split(":")[:2])
                value = hour * 60 + minute
                minutes.append(value - 1440 if value > 720 else value)
            except (TypeError, ValueError):
                continue
        if len(minutes) >= 3:
            deviation = math.sqrt(sum((value - sum(minutes) / len(minutes)) ** 2 for value in minutes) / len(minutes))
            consistency = max(0, min(1, 1 - deviation / 120))
    weights = {
        "morning": (35, 35, 30),
        "mostly morning": (37, 38, 25),
        "intermediate": (40, 40, 20),
        "mostly evening": (37, 38, 25),
        "evening": (35, 35, 30),
    }.get(str(chronotype or "intermediate").lower(), (40, 40, 20))
    score = duration * weights[0] + quality_value * weights[1] + consistency * weights[2]
    return int(min(100, max(0, round(score))))

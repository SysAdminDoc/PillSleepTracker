from datetime import date, datetime, timedelta

from tracker_core import (
    adherence_for_day,
    dose_status,
    due_doses,
    export_monthly_adherence_pdf,
    reorder_alerts,
    scheduled_doses_for_date,
)


def medication(**overrides):
    value = {
        "id": "med-1",
        "name": "Vitamin D",
        "frequency": "Twice Daily",
        "schedule_times": ["08:00", "20:00"],
        "active": True,
        "supply": 20,
        "supply_warn": 4,
    }
    value.update(overrides)
    return value


def test_schedule_expands_and_respects_weekly_days():
    doses = scheduled_doses_for_date(medication(), date(2026, 8, 3))
    assert [dose.scheduled_for.strftime("%H:%M") for dose in doses] == ["08:00", "20:00"]

    weekly = medication(frequency="Weekly", schedule_times=["09:30"], schedule_days=[0, 4])
    assert len(scheduled_doses_for_date(weekly, date(2026, 8, 3))) == 1
    assert scheduled_doses_for_date(weekly, date(2026, 8, 4)) == []


def test_due_dose_supports_grace_and_action_states():
    now = datetime(2026, 8, 3, 8, 20)
    med = medication(frequency="Daily", schedule_times=["08:00"])
    dose = scheduled_doses_for_date(med, now.date())[0]
    assert dose_status(dose, [], now, grace_minutes=30) == "due"
    assert dose_status(dose, [], now, grace_minutes=10) == "missed"

    logs = [{
        "med_id": "med-1",
        "dose_id": dose.dose_id,
        "action": "snoozed",
        "snooze_until": "2026-08-03T08:35:00",
        "logged_at": "2026-08-03T08:20:00",
    }]
    assert due_doses([med], logs, now, grace_minutes=30)[0]["status"] == "snoozed"


def test_adherence_and_reorder_forecast():
    med = medication(frequency="Daily", schedule_times=["08:00"], supply=3, supply_warn=1)
    day = date(2026, 8, 3)
    logs = []
    for offset in range(7):
        logged_day = day - timedelta(days=offset)
        logged_dose = scheduled_doses_for_date(med, logged_day)[0]
        logs.append({
            "med_id": "med-1",
            "dose_id": logged_dose.dose_id,
            "date": logged_day.isoformat(),
            "action": "taken",
            "logged_at": f"{logged_day.isoformat()}T08:10:00",
        })
    assert adherence_for_day([med], logs, day) == (1, 1, 0)
    alerts = reorder_alerts([med], logs, datetime(2026, 8, 3, 12), lead_days=7)
    assert alerts[0]["name"] == "Vitamin D"
    assert alerts[0]["days_left"] == 3.0


def test_monthly_pdf_export(tmp_path):
    path = export_monthly_adherence_pdf(
        tmp_path / "adherence.pdf",
        [medication(frequency="Daily", schedule_times=["08:00"])],
        [],
        2026,
        8,
    )
    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")

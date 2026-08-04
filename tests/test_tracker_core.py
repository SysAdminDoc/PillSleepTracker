from datetime import date, datetime, timedelta

import pytest

from tracker_core import (
    adherence_for_day,
    bedtime_consistency_coach,
    calculate_sleep_score,
    check_interactions,
    build_fhir_bundle,
    decrypt_json_payload,
    dose_status,
    due_doses,
    encrypt_json_payload,
    export_monthly_adherence_pdf,
    export_tracker_csv,
    format_weekly_summary,
    goal_progress,
    hash_pin,
    import_tracker_csv,
    import_wearable_csv,
    normalize_tracker_data,
    reorder_alerts,
    score_chronotype,
    scheduled_doses_for_date,
    verify_pin,
    voice_take_match,
    weekly_summary,
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


def test_goal_progress_counts_sleep_and_adherence_streaks():
    sleep_entries = [
        {"date": "2026-08-03", "duration_min": 480, "is_nap": False},
        {"date": "2026-08-02", "duration_min": 430, "is_nap": False},
        {"date": "2026-08-01", "duration_min": 420, "is_nap": False},
        {"date": "2026-08-03", "duration_min": 60, "is_nap": True},
    ]
    sleep_goal = goal_progress(
        {"id": "sleep", "type": "sleep_duration_streak", "target_days": 3, "min_duration_min": 420},
        sleep_entries,
        today=date(2026, 8, 3),
    )
    assert sleep_goal["current"] == 3
    assert sleep_goal["complete"]

    med = medication(frequency="Daily", schedule_times=["08:00"])
    med_logs = []
    for offset in range(3):
        day = date(2026, 8, 3) - timedelta(days=offset)
        dose = scheduled_doses_for_date(med, day)[0]
        med_logs.append({"med_id": "med-1", "dose_id": dose.dose_id, "date": dose.date, "action": "taken"})
    med_goal = goal_progress({"type": "med_adherence_streak", "target_days": 3}, [ ], [med], med_logs, date(2026, 8, 3))
    assert med_goal["current"] == 3


def test_voice_take_match_requires_a_take_phrase_and_prefers_long_names():
    medications = [{"id": "a", "name": "D"}, {"id": "b", "name": "Vitamin D"}]
    assert voice_take_match("I took my vitamin d", medications)["id"] == "b"
    assert voice_take_match("I should take a walk", medications) is None


def test_weekly_summary_formats_adherence_sleep_and_wellbeing():
    med = medication(frequency="Daily", schedule_times=["08:00"])
    day = date(2026, 8, 3)
    dose = scheduled_doses_for_date(med, day)[0]
    summary = weekly_summary(
        [med],
        [{"med_id": "med-1", "dose_id": dose.dose_id, "date": day.isoformat(), "action": "taken"}],
        [{"date": day.isoformat(), "duration_min": 480, "quality": 4, "score": 88, "mood": 5, "energy": 4}],
        today=day,
    )
    assert summary["taken"] == 1
    assert summary["scheduled"] == 7
    assert summary["adherence_percent"] == 14.3
    assert summary["average_mood"] == 5.0
    body = format_weekly_summary(summary, "Alex")
    assert "Alex" in body
    assert "Average sleep score: 88/100" in body


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


def test_wearable_import_normalizes_fitbit_and_garmin_stages(tmp_path):
    fitbit = tmp_path / "fitbit.csv"
    fitbit.write_text(
        "Sleep Date,Start Time,End Time,Minutes Asleep,Sleep Quality\n"
        "2026-08-03,08/02/2026 10:30 PM,08/03/2026 06:30 AM,480,Good\n",
        encoding="utf-8",
    )
    fitbit_entries = import_wearable_csv(fitbit)
    assert fitbit_entries[0]["source"] == "fitbit"
    assert fitbit_entries[0]["duration_min"] == 480
    assert fitbit_entries[0]["quality"] == 4

    garmin = tmp_path / "garmin.csv"
    garmin.write_text(
        "calendarDate,sleepStartTimestampGMT,sleepEndTimestampGMT,deepSleepSeconds,lightSleepSeconds,remSleepSeconds\n"
        "2026-08-03,2026-08-02T22:00:00,2026-08-03T06:00:00,7200,14400,7200\n",
        encoding="utf-8",
    )
    garmin_entries = import_wearable_csv(garmin)
    assert garmin_entries[0]["source"] == "garmin"
    assert garmin_entries[0]["stages"] == {"rem": 120, "deep": 120, "light": 240}


def test_bedtime_coach_ignores_naps_and_meq_changes_weights():
    entries = [
        {"date": "2026-08-03", "bedtime": "22:00", "is_nap": False},
        {"date": "2026-08-02", "bedtime": "22:20", "is_nap": False},
        {"date": "2026-08-01", "bedtime": "22:10", "is_nap": False},
        {"date": "2026-08-03", "bedtime": "13:00", "is_nap": True},
    ]
    coach = bedtime_consistency_coach(entries, today="2026-08-03")
    assert coach["sample_count"] == 3
    assert coach["target_bedtime"] == "22:10"
    assert "Strong rhythm" in coach["recommendation"]

    assert score_chronotype([5, 5, 5, 5, 5])["category"] == "Morning"
    assert score_chronotype([1, 1, 1, 1, 1])["category"] == "Evening"
    morning_score = calculate_sleep_score(360, 3, ["22:00", "22:10", "22:05"], "Morning")
    intermediate_score = calculate_sleep_score(360, 3, ["22:00", "22:10", "22:05"], "Intermediate")
    assert morning_score != intermediate_score
    neutral_score = calculate_sleep_score(480, 4, ["22:00", "22:10", "22:05"], "Intermediate")
    assert calculate_sleep_score(480, 4, ["22:00", "22:10", "22:05"], "Intermediate", 1, 1) < neutral_score
    assert calculate_sleep_score(480, 4, ["22:00", "22:10", "22:05"], "Intermediate", 5, 5) > neutral_score


def test_offline_interaction_screen_requires_distinct_drug_matches():
    findings = check_interactions([{"name": "Warfarin 5 mg"}, {"name": "Ibuprofen"}])
    assert findings[0]["severity"] == "high"
    assert check_interactions([{"name": "Warfarin"}, {"name": "Vitamin D"}]) == []
    assert check_interactions([{"name": "Warfarin"}, {"name": "Warfarin 2 mg"}]) == []


def test_profile_pin_hash_is_salted_and_verifiable():
    encoded = hash_pin("2468")
    assert encoded and encoded != "2468"
    assert verify_pin("2468", encoded)
    assert not verify_pin("0000", encoded)
    assert verify_pin("", "")


def test_aes_gcm_payload_round_trips_and_rejects_wrong_passphrase():
    payload = {"profiles": [{"id": "default", "name": "Default"}], "secret": "medication"}
    encrypted = encrypt_json_payload(payload, "correct horse battery")
    assert encrypted.startswith("PST-AESGCM-1$")
    assert decrypt_json_payload(encrypted, "correct horse battery") == payload
    with pytest.raises(ValueError):
        decrypt_json_payload(encrypted, "wrong passphrase")


def test_full_csv_backup_preserves_typed_records(tmp_path):
    data = normalize_tracker_data({
        "profiles": [{"id": "default", "name": "Default", "pin_hash": ""}],
        "medications": [{"id": "med-1", "name": "Vitamin D", "profile_id": "default", "active": True}],
        "med_log": [{"med_id": "med-1", "med_name": "Vitamin D", "profile_id": "default", "date": "2026-08-03", "action": "taken"}],
        "sleep_log": [{"id": "sleep-1", "profile_id": "default", "date": "2026-08-03", "duration_min": 480, "is_nap": False}],
    })
    path = export_tracker_csv(tmp_path / "backup.csv", data)
    restored = import_tracker_csv(path)
    assert restored["medications"][0]["name"] == "Vitamin D"
    assert restored["med_log"][0]["action"] == "taken"
    assert restored["sleep_log"][0]["duration_min"] == 480


def test_sleep_mood_and_energy_migrate_with_optional_defaults():
    normalized = normalize_tracker_data({"sleep_log": [{"id": "sleep-1", "date": "2026-08-03"}]})
    assert normalized["sleep_log"][0]["mood"] is None
    assert normalized["sleep_log"][0]["energy"] is None


def test_fhir_bundle_contains_medication_and_sleep_resources():
    bundle = build_fhir_bundle(
        [{"id": "med-1", "name": "Vitamin D", "dosage": "1000 IU", "frequency": "Daily", "active": True}],
        [{"id": "sleep-1", "date": "2026-08-03", "duration_min": 480, "quality": 4, "score": 87, "stages": {"deep": 100}}],
        {"id": "profile-1", "name": "Alex"},
    )
    assert bundle["resourceType"] == "Bundle"
    assert bundle["total"] == 2
    medication, observation = [entry["resource"] for entry in bundle["entry"]]
    assert medication["resourceType"] == "MedicationStatement"
    assert medication["subject"]["reference"] == "Patient/profile-1"
    assert observation["resourceType"] == "Observation"
    assert observation["valueQuantity"]["unit"] == "min"
    assert {component["code"]["text"] for component in observation["component"]} == {"Sleep quality", "Sleep score", "Sleep stage: deep"}

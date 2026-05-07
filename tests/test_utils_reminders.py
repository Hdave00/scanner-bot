"""Tests for reminder-related functions in bots.utils."""

import pytest
from datetime import datetime, timezone

from bots.utils import (
    init_db,
    add_reminder,
    get_reminders,
    get_user_reminders,
    delete_reminder,
)


@pytest.fixture()
def db_path(tmp_path):
    db = tmp_path / "reminders_test.db"
    init_db(str(db))
    return str(db)


class TestAddReminder:
    def test_add_reminder_with_datetime(self, db_path):
        dt = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "Test reminder", dt, True, db_path)
        assert rid is not None
        assert rid > 0

    def test_add_reminder_with_iso_string(self, db_path):
        rid = add_reminder(100, 200, "ISO reminder", "2026-07-01T15:30:00+02:00", True, db_path)
        assert rid is not None
        assert rid > 0

    def test_add_reminder_stores_utc(self, db_path):
        dt = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "UTC reminder", dt, False, db_path)
        rows = get_user_reminders(100, db_path)
        assert len(rows) == 1
        # remind_time at index 4 should be UTC ISO string
        assert "+00:00" in rows[0][4] or "Z" in rows[0][4] or "UTC" in rows[0][4]

    def test_add_reminder_with_past_datetime(self, db_path):
        dt = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "Past reminder", dt, False, db_path)
        assert rid is not None

    def test_add_reminder_invalid_string_raises(self, db_path):
        with pytest.raises(ValueError):
            add_reminder(100, 200, "bad", "not-a-date", True, db_path)

    def test_add_reminder_stores_dm_flag(self, db_path):
        rid = add_reminder(100, 200, "DM reminder", datetime.now(timezone.utc), True, db_path)
        rows = get_user_reminders(100, db_path)
        assert len(rows) == 1
        assert rows[0][5] == 1  # dm column

        rid2 = add_reminder(100, 200, "Channel reminder", datetime.now(timezone.utc), False, db_path)
        rows = get_user_reminders(100, db_path)
        assert len(rows) == 2
        assert rows[1][5] == 0  # dm column


class TestGetReminders:
    def test_get_reminders_empty(self, db_path):
        assert get_reminders(db_path) == []

    def test_get_reminders_returns_all(self, db_path):
        dt = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        add_reminder(100, 200, "R1", dt, False, db_path)
        add_reminder(101, 200, "R2", dt, False, db_path)
        rows = get_reminders(db_path)
        assert len(rows) == 2

    def test_get_reminders_row_structure(self, db_path):
        dt = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "Structure test", dt, True, db_path)
        rows = get_reminders(db_path)
        row = rows[0]
        assert row[0] == rid  # id
        assert row[1] == 100  # user_id
        assert row[2] == 200  # channel_id
        assert row[3] == "Structure test"  # message
        assert row[4] is not None  # remind_time
        assert row[5] == 1  # dm


class TestGetUserReminders:
    def test_get_user_reminders_empty(self, db_path):
        assert get_user_reminders(999, db_path) == []

    def test_get_user_reminders_filters(self, db_path):
        dt = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        add_reminder(100, 200, "My reminder 1", dt, False, db_path)
        add_reminder(100, 200, "My reminder 2", dt, True, db_path)
        add_reminder(200, 200, "Other reminder", dt, False, db_path)

        rows = get_user_reminders(100, db_path)
        assert len(rows) == 2
        assert all(r[1] == 100 for r in rows)

    def test_get_user_reminders_row_format(self, db_path):
        dt = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "Format test", dt, False, db_path)
        rows = get_user_reminders(100, db_path)
        row = rows[0]
        assert row[0] == rid


class TestDeleteReminder:
    def test_delete_reminder_success(self, db_path):
        dt = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "Delete me", dt, False, db_path)
        assert delete_reminder(rid, 100, db_path) is True

    def test_delete_reminder_wrong_user_fails(self, db_path):
        dt = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "Not yours", dt, False, db_path)
        assert delete_reminder(rid, 999, db_path) is False

    def test_delete_reminder_nonexistent(self, db_path):
        assert delete_reminder(99999, 100, db_path) is False

    def test_delete_reminder_removes_from_db(self, db_path):
        dt = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "Gone", dt, False, db_path)
        delete_reminder(rid, 100, db_path)
        rows = get_user_reminders(100, db_path)
        assert len(rows) == 0

    def test_delete_reminder_already_deleted(self, db_path):
        dt = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        rid = add_reminder(100, 200, "Double delete", dt, False, db_path)
        delete_reminder(rid, 100, db_path)
        assert delete_reminder(rid, 100, db_path) is False

    def test_add_reminder_non_datetime_non_string_raises(self, db_path):
        with pytest.raises(TypeError, match="remind_time must be a datetime"):
            add_reminder(100, 200, "bad", 12345, True, db_path)

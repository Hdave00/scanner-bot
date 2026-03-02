# testing log_attendance function's state mutation for the attendance_log global dict
# We want to verify pseudo_id creation, correct key format and duplicate prevention

"""for testing the log_attendance function:
    
    function takes 'def log_attendance(user_id, username, event_id, response="accepted"):' args, so it;
        
        1. mutates the attendance_log global dict
        2. creates unique key (pseudo_id)
        3. Prevents duplicates and stores structured data"""

import pytest
from bots.attbot import log_attendance, attendance_log

# using pytest.fixture as setup/teardown helper method so it runs before every text, clears attendance_log for fresh data, the tests run and clears after 
# test is done running.
@pytest.fixture(autouse=True)
def clear_log():
    attendance_log.clear()
    yield
    attendance_log.clear()

# Test accepted and declines, also check if default response works ie, if "response =" is not passed, it should default to accepted
def test_log_accept():
    log_attendance(123, "Hastings", 999)
    assert len(attendance_log) == 1

    key = "999-123"
    assert key in attendance_log

    entry = attendance_log[key]   # this what the function actually builds "pseudo_id = f"{event_id}-{user_id_str}", check if that exact key exists

    assert entry["user_id"] == "123"    # the user_id_str = str(user_id) is being converted to string, so check for string not int
    assert entry["username"] == "Hastings"
    assert entry["response"] == "accepted"
    assert "timestamp" in entry

# since there is a different key for declined vs accepted, check that as well, along with a passed response type
def test_log_decline():
    log_attendance(123, "Mooses", 999, response="declined")

    key = "999-123-declined"
    assert key in attendance_log

    entry = attendance_log[key]
    assert entry["response"] == "declined"

# since the function has "if pseudo_id not in attendance_log:" calling it 2x should not create 2 entries, should not overwrite and keep length = 1 keeping idempotency
def test_no_duplicate_entries():
    log_attendance(123, "Miller", 999)
    log_attendance(123, "Miller", 999)

    assert len(attendance_log) == 1

# Now test that declined and accepted are separate ie, if a user's response isnt stored, it has to be different from when it is.
# Eg; user hastings has 2 types of responses, one default and one explicitly declined, they should count as 2 different entries in the dict
def test_accept_and_decline_are_separate():
    log_attendance(123, "Hastings", 999)
    log_attendance(123, "Hastings", 999, response="declined")

    assert len(attendance_log) == 2

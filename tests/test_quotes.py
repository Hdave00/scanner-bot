from bots.utils import (
    init_db,
    add_quote,
    delete_quote,
    get_random_quote,
    get_random_quote_by_user,
    get_user_quotes,
)


def test_add_quote_and_get_user_quotes(tmp_path):
    db_path = tmp_path / "quotes_test.db"
    init_db(str(db_path))

    quote_id = add_quote(101, "Hastings", "Check your sectors.", str(db_path))

    rows = get_user_quotes(101, str(db_path))
    assert len(rows) == 1
    assert rows[0][0] == quote_id
    assert rows[0][1] == 101
    assert rows[0][2] == "Hastings"
    assert rows[0][3] == "Check your sectors."
    assert rows[0][4]


def test_get_random_quote_returns_inserted_quote(tmp_path):
    db_path = tmp_path / "quotes_test.db"
    init_db(str(db_path))

    add_quote(201, "Miller", "Hold the flank.", str(db_path))

    row = get_random_quote(str(db_path))
    assert row is not None
    assert row[1] == 201
    assert row[2] == "Miller"
    assert row[3] == "Hold the flank."


def test_get_random_quote_by_user_filters_on_user(tmp_path):
    db_path = tmp_path / "quotes_test.db"
    init_db(str(db_path))

    add_quote(301, "Alpha", "Alpha quote", str(db_path))
    add_quote(302, "Bravo", "Bravo quote", str(db_path))

    row = get_random_quote_by_user(302, str(db_path))
    assert row is not None
    assert row[1] == 302
    assert row[2] == "Bravo"
    assert row[3] == "Bravo quote"


def test_delete_quote_only_deletes_own_quote(tmp_path):
    db_path = tmp_path / "quotes_test.db"
    init_db(str(db_path))

    quote_id = add_quote(401, "Mooses", "Stay frosty.", str(db_path))

    assert delete_quote(999, quote_id, str(db_path)) is False
    assert len(get_user_quotes(401, str(db_path))) == 1

    assert delete_quote(401, quote_id, str(db_path)) is True
    assert get_user_quotes(401, str(db_path)) == []

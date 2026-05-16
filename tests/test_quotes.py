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

    quote_id = add_quote(101, "Hastings", "Check your sectors.", 202, "Price", str(db_path))

    rows = get_user_quotes(101, str(db_path))
    assert len(rows) == 1
    assert rows[0][0] == quote_id
    assert rows[0][1] == 101
    assert rows[0][2] == "Hastings"
    assert rows[0][3] == "Check your sectors."
    assert rows[0][4]  # created_at exists


def test_get_random_quote_returns_inserted_quote(tmp_path):
    db_path = tmp_path / "quotes_test.db"
    init_db(str(db_path))

    add_quote(201, "Miller", "Hold the flank.", 301, "Price", str(db_path))

    row = get_random_quote(str(db_path))
    assert row is not None
    assert row[1] == 201       # adder user_id
    assert row[2] == "Miller"  # adder username
    assert row[3] == "Hold the flank."


def test_get_random_quote_by_user_filters_on_user(tmp_path):
    db_path = tmp_path / "quotes_test.db"
    init_db(str(db_path))

    # 401 added both, but quotes were said by 501 and 502
    add_quote(401, "Hastings", "Alpha quote", 501, "Alpha", str(db_path))
    add_quote(401, "Hastings", "Bravo quote", 502, "Bravo", str(db_path))

    row = get_random_quote_by_user(502, str(db_path))  # filter by who SAID it
    assert row is not None
    assert row[5] == "Bravo"   # quoted_username (index 5)
    assert row[3] == "Bravo quote"


def test_delete_quote_only_deletes_own_quote(tmp_path):
    db_path = tmp_path / "quotes_test.db"
    init_db(str(db_path))

    quote_id = add_quote(401, "Mooses", "Stay frosty.", 501, "Price", str(db_path))

    assert delete_quote(999, quote_id, str(db_path)) is False
    assert len(get_user_quotes(401, str(db_path))) == 1

    assert delete_quote(401, quote_id, str(db_path)) is True
    assert get_user_quotes(401, str(db_path)) == []


def test_get_random_quote_by_user_ignores_other_users(tmp_path):
    db_path = str(tmp_path / "quotes_test.db")
    init_db(db_path)

    add_quote(401, "Hastings", "Man, 300 meters front.", 301, "Price", db_path)
    add_quote(401, "Hastings", "Check left flank.", 302, "Mooses", db_path)

    row = get_random_quote_by_user(302, db_path)
    assert row[5] == "Mooses"  # quoted_username, should never return Price's quote


def test_delete_quote_prevents_cross_user_deletion(tmp_path):
    db_path = str(tmp_path / "quotes_test.db")
    init_db(db_path)

    add_quote(401, "Miller", "Lets run curahee", 501, "Price", db_path)
    rows = get_user_quotes(401, db_path)
    quote_id = rows[0][0]

    success = delete_quote(402, quote_id, db_path)
    assert success is False
    assert len(get_user_quotes(401, db_path)) == 1


def test_get_random_quote_empty_db_returns_none(tmp_path):
    db_path = str(tmp_path / "quotes_test.db")
    init_db(db_path)

    row = get_random_quote(db_path)
    assert row is None
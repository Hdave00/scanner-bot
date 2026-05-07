import asyncio
import importlib
from types import SimpleNamespace

import pytest


@pytest.fixture
def attbot_module(monkeypatch):
    monkeypatch.setenv("TOKEN", "test-token")
    monkeypatch.setenv("CHANNEL_ID", "12345678901234567")
    monkeypatch.setenv("GUILD_ID", "12345678901234567")

    import discord.ext.commands as commands
    monkeypatch.setattr(commands.Bot, "run", lambda self, *args, **kwargs: None)

    from bots import attbot
    return importlib.reload(attbot)


class MockResponse:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, message, ephemeral=False, view=None):
        self.sent_messages.append({
            "message": message,
            "ephemeral": ephemeral,
            "view": view,
        })


class MockInteraction:
    def __init__(self, user_id=1, display_name="Tester"):
        self.user = SimpleNamespace(id=user_id, display_name=display_name)
        self.response = MockResponse()


class MockCtx:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class MockDeferredResponse(MockResponse):
    def __init__(self):
        super().__init__()
        self.deferred = False
        self.modal = None

    async def defer(self, thinking=False):
        self.deferred = thinking

    async def send_modal(self, modal):
        self.modal = modal


class MockFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, message, ephemeral=False):
        self.messages.append({"message": message, "ephemeral": ephemeral})


class MockHistoryChannel:
    def __init__(self, messages, mention="#chan"):
        self._messages = messages
        self.mention = mention
        self.sent = []

    async def history(self, limit=None):
        items = self._messages[:limit] if limit is not None else self._messages
        for item in items:
            yield item

    async def send(self, message):
        self.sent.append(message)


class MockCommandInteraction:
    def __init__(self, roles=None, channel=None, guild=None, user_id=1):
        self.user = SimpleNamespace(id=user_id, roles=roles or [], display_name=f"User{user_id}")
        self.channel = channel
        self.guild = guild
        self.response = MockDeferredResponse()
        self.followup = MockFollowup()


def test_get_required_int_env_success(attbot_module, monkeypatch):
    monkeypatch.setenv("TEST_INT_ENV", "42")
    assert attbot_module._get_required_int_env("TEST_INT_ENV") == 42


def test_get_required_int_env_missing_raises(attbot_module, monkeypatch):
    monkeypatch.delenv("TEST_INT_ENV", raising=False)
    with pytest.raises(ValueError, match="Required environment variable TEST_INT_ENV is not set"):
        attbot_module._get_required_int_env("TEST_INT_ENV")


def test_get_required_int_env_invalid_raises(attbot_module, monkeypatch):
    monkeypatch.setenv("TEST_INT_ENV", "abc")
    with pytest.raises(ValueError, match="Environment variable TEST_INT_ENV must be an integer"):
        attbot_module._get_required_int_env("TEST_INT_ENV")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("12345678901234567", True),
        (12345678901234567890, True),
        ("1234567890123456", False),
        ("abc12345678901234", False),
    ],
)
def test_is_valid_snowflake(attbot_module, value, expected):
    assert attbot_module.is_valid_snowflake(value) is expected


def test_already_logged(attbot_module):
    attbot_module.attendance_log.clear()
    pseudo_id = "999-123"
    assert attbot_module.already_logged(pseudo_id) is False
    attbot_module.attendance_log[pseudo_id] = {"user_id": "123"}
    assert attbot_module.already_logged(pseudo_id) is True


def test_quote_with_user_when_none_found(attbot_module, monkeypatch):
    interaction = MockInteraction()
    user = SimpleNamespace(id=99, display_name="Mooses")

    monkeypatch.setattr(attbot_module, "get_random_quote_by_user", lambda user_id: None)

    asyncio.run(attbot_module.quote.callback(interaction, user))

    assert interaction.response.sent_messages == [{
        "message": "Mooses has no quotes yet.",
        "ephemeral": True,
        "view": None,
    }]


def test_quote_without_user_when_db_empty(attbot_module, monkeypatch):
    interaction = MockInteraction()

    monkeypatch.setattr(attbot_module, "get_random_quote", lambda: None)

    asyncio.run(attbot_module.quote.callback(interaction, None))

    assert interaction.response.sent_messages == [{
        "message": "No quotes in the database yet.",
        "ephemeral": True,
        "view": None,
    }]


def test_quote_without_user_returns_formatted_quote(attbot_module, monkeypatch):
    interaction = MockInteraction()
    row = (1, 5, "Hastings", "Check your sectors.", "2026-01-01T12:00:00+00:00")

    monkeypatch.setattr(attbot_module, "get_random_quote", lambda: row)

    asyncio.run(attbot_module.quote.callback(interaction, None))

    assert interaction.response.sent_messages == [{
        "message": '"Check your sectors." - Hastings, 2026',
        "ephemeral": False,
        "view": None,
    }]


def test_addquote_calls_add_quote_and_replies(attbot_module, monkeypatch):
    interaction = MockInteraction(user_id=77, display_name="Rydah")
    recorded = {}

    def fake_add_quote(user_id, username, quote):
        recorded["args"] = (user_id, username, quote)

    monkeypatch.setattr(attbot_module, "add_quote", fake_add_quote)

    asyncio.run(attbot_module.addquote.callback(interaction, "Hold the flank."))

    assert recorded["args"] == (77, "Rydah", "Hold the flank.")
    assert interaction.response.sent_messages == [{
        "message": 'Added: "Hold the flank."- Rydah',
        "ephemeral": True,
        "view": None,
    }]


def test_deletequote_no_user_quotes(attbot_module, monkeypatch):
    interaction = MockInteraction(user_id=22, display_name="Miller")
    monkeypatch.setattr(attbot_module, "get_user_quotes", lambda user_id: [])

    asyncio.run(attbot_module.deletequote.callback(interaction))

    assert interaction.response.sent_messages == [{
        "message": "You have no quotes to delete.",
        "ephemeral": True,
        "view": None,
    }]


def test_quote_with_user_returns_formatted_quote(attbot_module, monkeypatch):
    interaction = MockInteraction()
    user = SimpleNamespace(id=99, display_name="Mooses")
    row = (10, 99, "Mooses", "Stay frosty.", "2025-10-10T15:30:00+00:00")

    monkeypatch.setattr(attbot_module, "get_random_quote_by_user", lambda user_id: row)

    asyncio.run(attbot_module.quote.callback(interaction, user))

    assert interaction.response.sent_messages == [{
        "message": '"Stay frosty." - Mooses, 2025',
        "ephemeral": False,
        "view": None,
    }]


def test_deletequote_with_rows_builds_select_view(attbot_module, monkeypatch):
    interaction = MockInteraction(user_id=55, display_name="Alpha")
    rows = [(1, 55, "Alpha", "Alpha quote", "2026-02-01T10:00:00+00:00")]
    monkeypatch.setattr(attbot_module, "get_user_quotes", lambda user_id: rows)

    asyncio.run(attbot_module.deletequote.callback(interaction))

    assert len(interaction.response.sent_messages) == 1
    sent = interaction.response.sent_messages[0]
    assert sent["message"] == "Select a quote to delete:"
    assert sent["ephemeral"] is True
    assert sent["view"] is not None


def test_schedule_reminder_creates_task_once(attbot_module, monkeypatch):
    attbot_module.scheduled_reminders.clear()
    created = []

    class DummyTask:
        pass

    async def fake_reminder_task(*args, **kwargs):
        return None

    monkeypatch.setattr(attbot_module, "reminder_task", fake_reminder_task)

    def fake_create_task(coro):
        created.append(coro)
        coro.close()
        return DummyTask()

    monkeypatch.setattr(attbot_module.asyncio, "create_task", fake_create_task)

    attbot_module.schedule_reminder(1, 2, 3, "msg", "2026-01-01T00:00:00+00:00", False)
    attbot_module.schedule_reminder(1, 2, 3, "msg", "2026-01-01T00:00:00+00:00", False)

    assert len(created) == 1
    assert 1 in attbot_module.scheduled_reminders


def test_dump_attendance_reports_count(attbot_module):
    ctx = MockCtx()
    attbot_module.attendance_log.clear()
    attbot_module.attendance_log["x"] = {"user_id": "1"}
    attbot_module.attendance_log["y"] = {"user_id": "2"}

    asyncio.run(attbot_module.dump_attendance(ctx))

    assert ctx.messages == ["Current entries: 2"]


def test_parse_datetime_supports_multiple_formats(attbot_module):
    dt = attbot_module.ReminderModal.parse_datetime("2025-10-05 14:30")
    assert dt is not None
    assert dt.tzinfo is not None

    dt2 = attbot_module.ReminderModal.parse_datetime("2025-10-05T14:30")
    assert dt2 is not None


def test_parse_datetime_invalid_returns_none(attbot_module):
    assert attbot_module.ReminderModal.parse_datetime("not-a-date") is None


def test_remindme_sends_modal(attbot_module):
    interaction = MockCommandInteraction()
    asyncio.run(attbot_module.remindme.callback(interaction))
    assert interaction.response.modal is not None


def test_rand_sends_random_number(attbot_module, monkeypatch):
    interaction = MockCommandInteraction()
    monkeypatch.setattr(attbot_module.secrets, "randbelow", lambda n: 6)
    asyncio.run(attbot_module.rand.callback(interaction, 10))
    assert interaction.response.sent_messages[0]["message"] == "**7**"


def test_coin_single_and_multiple(attbot_module, monkeypatch):
    interaction = MockCommandInteraction()
    monkeypatch.setattr(attbot_module.random, "choice", lambda opts: "Heads")
    asyncio.run(attbot_module.coin.callback(interaction, 1))
    assert interaction.response.sent_messages[0]["message"] == "Heads"

    interaction2 = MockCommandInteraction()
    seq = iter(["Heads", "Tails", "Heads"])
    monkeypatch.setattr(attbot_module.random, "choice", lambda opts: next(seq))
    asyncio.run(attbot_module.coin.callback(interaction2, 3))
    msg = interaction2.response.sent_messages[0]["message"]
    assert "coin was flipped 3 times" in msg
    assert "**Heads:** 2" in msg
    assert "**Tails:** 1" in msg


def test_clear_cache_role_required(attbot_module):
    interaction = MockCommandInteraction(roles=[])
    asyncio.run(attbot_module.clear_cache.callback(interaction))
    assert interaction.response.sent_messages[0]["ephemeral"] is True


def test_clear_cache_success_clears_logs(attbot_module):
    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    attbot_module.event_log[:] = [{"x": 1}]
    attbot_module.attendance_log["k"] = {"v": 1}

    asyncio.run(attbot_module.clear_cache.callback(interaction))

    assert attbot_module.event_log == []
    assert attbot_module.attendance_log == {}
    assert interaction.response.sent_messages[0]["message"] == "Apollo scan cache cleared successfully."


def test_recent_authors_role_required(attbot_module):
    channel = MockHistoryChannel(messages=[])
    interaction = MockCommandInteraction(roles=[], channel=channel)
    asyncio.run(attbot_module.recent_authors.callback(interaction, 5))
    assert interaction.response.sent_messages[0]["message"] == "You must be an **NCO** to use this command."


def test_recent_authors_collects_names(attbot_module):
    role = SimpleNamespace(name="NCO")
    messages = [
        SimpleNamespace(author=SimpleNamespace(name="Alpha")),
        SimpleNamespace(author=SimpleNamespace(name="Bravo")),
    ]
    channel = MockHistoryChannel(messages=messages)
    interaction = MockCommandInteraction(roles=[role], channel=channel)

    asyncio.run(attbot_module.recent_authors.callback(interaction, 10))
    out = interaction.response.sent_messages[0]["message"]
    assert "Recent authors from last 10 messages:" in out
    assert "Alpha" in out and "Bravo" in out


def test_show_apollo_embeds_role_required(attbot_module):
    channel = MockHistoryChannel(messages=[])
    interaction = MockCommandInteraction(roles=[], channel=channel)
    asyncio.run(attbot_module.show_apollo_embeds.callback(interaction, 5))
    assert interaction.response.sent_messages[0]["ephemeral"] is True


def test_show_apollo_embeds_found_and_not_found(attbot_module):
    role = SimpleNamespace(name="NCO")
    non_apollo = [SimpleNamespace(author=SimpleNamespace(name="Other"), embeds=[])]
    interaction = MockCommandInteraction(roles=[role], channel=MockHistoryChannel(non_apollo))
    asyncio.run(attbot_module.show_apollo_embeds.callback(interaction, 5))
    assert interaction.response.sent_messages[0]["message"].startswith("No Apollo messages found")

    apollo_msg = SimpleNamespace(
        author=SimpleNamespace(name="Apollo"),
        embeds=[SimpleNamespace(description="hello embed")],
    )
    channel2 = MockHistoryChannel([apollo_msg])
    interaction2 = MockCommandInteraction(roles=[role], channel=channel2)
    asyncio.run(attbot_module.show_apollo_embeds.callback(interaction2, 5))
    assert channel2.sent == ["Embed description:\n```hello embed```"]
    assert interaction2.response.sent_messages[0]["message"] == "Found 1 Apollo messages."


def test_summary_role_required(attbot_module):
    interaction = MockCommandInteraction(roles=[], guild=SimpleNamespace(members=[]))
    asyncio.run(attbot_module.summary.callback(interaction, 8))
    assert interaction.followup.messages[0]["ephemeral"] is True


def test_summary_insufficient_events(attbot_module, monkeypatch):
    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role], guild=SimpleNamespace(members=[]))
    monkeypatch.setattr(attbot_module, "scan_apollo_events", lambda limit: asyncio.sleep(0, result=(12, 2)))
    attbot_module.event_log[:] = [{"accepted": [], "declined": []}]

    asyncio.run(attbot_module.summary.callback(interaction, 8))
    assert "Need at least 8 events" in interaction.followup.messages[0]["message"]


def test_leaderboard_role_and_empty(attbot_module):
    interaction = MockCommandInteraction(roles=[])
    asyncio.run(attbot_module.leaderboard.callback(interaction, 8))
    assert interaction.response.sent_messages[0]["ephemeral"] is True

    role = SimpleNamespace(name="NCO")
    interaction2 = MockCommandInteraction(roles=[role])
    attbot_module.event_log.clear()
    asyncio.run(attbot_module.leaderboard.callback(interaction2, 8))
    assert interaction2.response.sent_messages[0]["message"] == "No events have been scanned yet."


def test_leaderboard_outputs_rankings(attbot_module):
    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    attbot_module.event_log[:] = [
        {"accepted": [(1, "Miller"), (2, "Rydah")], "declined": [(3, "Mooses ")]},
        {"accepted": [(1, "Miller")], "declined": [(2, "Rydah")]},
    ]

    asyncio.run(attbot_module.leaderboard.callback(interaction, 2))
    out = interaction.followup.messages[0]["message"]
    assert "Attendance Leaderboard" in out
    assert "Miller" in out
